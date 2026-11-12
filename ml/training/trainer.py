"""Treinamento dos modelos candidatos, seleção multicritério embarcada e serialização de bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
from sklearn.metrics import accuracy_score, f1_score

from ml.schemas import (
    CORE_GESTURE_CLASSES,
    FEATURE_NAMES,
    DataOrigin,
    ExperimentalStatus,
    PreprocessingConfig,
    RawSampleRecord,
    StabilizerConfig,
    WindowSample,
)
from ml.training.models import (
    TrainingConfig,
    build_candidate_models,
)
from ml.training.splitter import (
    DatasetSplit,
    split_windows_grouped,
    windows_to_xy,
)


class SyntheticDataContaminationError(ValueError):
    """Levantada quando amostras sintéticas são detectadas em um fluxo estritamente físico/real."""


def assert_strictly_real_data(
    items: Sequence[RawSampleRecord | WindowSample],
    context: str = "treinamento/avaliacao de modelo real",
) -> None:
    """Garante que 100% dos registros ou janelas tenham `data_origin == 'real_hardware'`.

    Atende à regra inegociável da Seção 4 do Ciclo 5:
    'Não misturar amostras sintéticas nos resultados de avaliação do modelo real.'
    """
    if not items:
        raise ValueError(f"Conjunto de dados vazio em {context}.")
    bad_origins = sorted({x.data_origin for x in items if x.data_origin != DataOrigin.REAL_HARDWARE.value})
    if bad_origins:
        raise SyntheticDataContaminationError(
            f"CONTAMINACAO SINTETICA BLOQUEADA em {context}: detectadas origens {bad_origins}. "
            "Remova qualquer arquivo 'synthetic_simulator' antes de treinar/avaliar o modelo fisico real."
        )


def compute_embedded_selection_score(
    val_f1_macro: float,
    val_event_f1: float,
    val_neutral_far: float | None,
    estimated_flash_bytes: int,
    estimated_sram_bytes: int,
    max_flash_budget_bytes: int = 32768,
    max_sram_budget_bytes: int = 4096,
) -> float:
    """Calcula índice multicritério para seleção TinyML no ESP32 (Seção 5 do Ciclo 5).

    Não escolhe exclusivamente pela acurácia de janelas! Pondera:
    - 45% F1-Macro de janelas na validação agrupada (`val_f1_macro`)
    - 35% F1 em nível de eventos contínuos com `EventStabilizer` (`val_event_f1`)
    - 15% Supressão de falsos acionamentos em sequências NEUTRAL (`1 - val_neutral_far`)
    -  5% Eficiência de memória Flash/SRAM embarcada (modelos <= 4 KiB Flash recebem nota máxima)
    """
    if estimated_flash_bytes > max_flash_budget_bytes or estimated_sram_bytes > max_sram_budget_bytes:
        return -1.0

    if estimated_flash_bytes <= 4096:
        compactness = 1.0
    else:
        compactness = max(
            0.0,
            1.0 - ((estimated_flash_bytes - 4096) / max(1, max_flash_budget_bytes - 4096)),
        )

    score = (
        0.45 * float(val_f1_macro)
        + 0.35 * float(val_event_f1)
        + (0.15 * max(0.0, 1.0 - float(val_neutral_far)) if val_neutral_far is not None else 0.0)
        + 0.05 * float(compactness)
    )
    return round(float(score), 6)


@dataclass
class TrainedBundle:
    """Artefato completo contendo o modelo ajustado, metadados de pré-processamento e rastreabilidade."""

    model_name: str
    estimator: Any
    class_names: tuple[str, ...]
    feature_names: tuple[str, ...]
    preprocessing_config: PreprocessingConfig
    training_config: TrainingConfig
    split_strategy: str
    split_warnings: tuple[str, ...]
    data_origins: tuple[str, ...]
    experimental_status: str
    val_f1_macro: float = 0.0
    val_accuracy: float = 0.0
    val_event_f1: float = 0.0
    val_neutral_far: float = 0.0
    estimated_flash_bytes: int = 0
    estimated_sram_bytes: int = 0
    selection_score: float = 0.0
    training_participants: tuple[str, ...] = ()
    training_sessions: tuple[str, ...] = ()
    development_participants: tuple[str, ...] = ()
    development_sessions: tuple[str, ...] = ()
    dataset_sha256: str = ""
    experiment_id: str = ""

    def to_meta_dict(self) -> dict[str, Any]:
        """Gera dicionário legível em JSON sem o objeto binário do estimador."""
        return {
            "model_name": self.model_name,
            "class_names": list(self.class_names),
            "feature_names": list(self.feature_names),
            "preprocessing_config": self.preprocessing_config.to_dict(),
            "training_config": self.training_config.to_dict(),
            "split_strategy": self.split_strategy,
            "split_warnings": list(self.split_warnings),
            "data_origins": list(self.data_origins),
            "experimental_status": self.experimental_status,
            "val_f1_macro": round(float(self.val_f1_macro), 4),
            "val_accuracy": round(float(self.val_accuracy), 4),
            "val_event_f1": round(float(self.val_event_f1), 4),
            "val_neutral_far": round(float(self.val_neutral_far), 4),
            "estimated_flash_bytes": int(self.estimated_flash_bytes),
            "estimated_sram_bytes": int(self.estimated_sram_bytes),
            "selection_score": round(float(self.selection_score), 6),
            "training_participants": list(self.training_participants),
            "training_sessions": list(self.training_sessions),
            "development_participants": list(self.development_participants),
            "development_sessions": list(self.development_sessions),
            "dataset_sha256": self.dataset_sha256,
            "experiment_id": self.experiment_id,
        }


def train_candidate_models(
    windows: Sequence[WindowSample],
    training_config: TrainingConfig | None = None,
    preprocessing_config: PreprocessingConfig | None = None,
    stabilizer_config: StabilizerConfig | None = None,
    require_real_data: bool = False,
) -> tuple[dict[str, TrainedBundle], DatasetSplit]:
    """Particiona os dados sem vazamento, treina os 4 modelos candidatos e calcula métricas multicritério."""
    from ml.evaluation.metrics import (
        estimate_esp32_memory,
        evaluate_classification_metrics,
        evaluate_event_level,
    )

    if require_real_data:
        assert_strictly_real_data(windows, context="train_candidate_models(require_real_data=True)")

    cfg = training_config or TrainingConfig()
    p_cfg = preprocessing_config or PreprocessingConfig()

    # Regra estrita de ML: split agrupado ANTES de ajustar qualquer pipeline/StandardScaler!
    split = split_windows_grouped(
        windows,
        seed=cfg.seed,
    )

    origins = tuple(sorted({w.data_origin for w in windows}))
    has_synthetic = any(o != DataOrigin.REAL_HARDWARE.value for o in origins)
    exp_status = (
        ExperimentalStatus.AWAITING_REAL_DATA.value
        if has_synthetic
        else ExperimentalStatus.EVALUATED_ON_REAL_DATA.value
    )

    X_train, y_train = windows_to_xy(split.train, class_names=cfg.class_names)
    X_val, y_val = windows_to_xy(split.val, class_names=cfg.class_names)

    models = build_candidate_models(cfg)
    bundles: dict[str, TrainedBundle] = {}

    for name, model in models.items():
        model.fit(X_train, y_train)
        mem = estimate_esp32_memory(model, cfg.class_names)
        flash_b = int(mem.get("estimated_esp32_flash_bytes", 0))
        sram_b = int(mem.get("estimated_esp32_sram_bytes", 0))

        if len(y_val) > 0:
            y_pred = model.predict(X_val)
            val_f1 = float(f1_score(y_val, y_pred, labels=list(range(len(cfg.class_names))), average="macro", zero_division=0))
            val_acc = float(accuracy_score(y_val, y_pred))
            cls_val = evaluate_classification_metrics(model, X_val, y_val, class_names=cfg.class_names)
            val_far = float(cls_val.get("false_activation_rate_neutral", 0.0))
            evt_val = evaluate_event_level(
                model,
                split.val,
                class_names=cfg.class_names,
                stabilizer_config=stabilizer_config,
            )
            val_evt_f1 = float(evt_val.get("event_f1", 0.0))
        else:
            val_f1 = 0.0
            val_acc = 0.0
            val_far = 0.0
            val_evt_f1 = 0.0

        sel_score = compute_embedded_selection_score(
            val_f1_macro=val_f1,
            val_event_f1=val_evt_f1,
            val_neutral_far=val_far if len(y_val) and cls_val.get("neutral_support", 0) else None,
            estimated_flash_bytes=flash_b,
            estimated_sram_bytes=sram_b,
        )

        bundles[name] = TrainedBundle(
            model_name=name,
            estimator=model,
            class_names=cfg.class_names,
            feature_names=FEATURE_NAMES,
            preprocessing_config=p_cfg,
            training_config=cfg,
            split_strategy=split.strategy,
            split_warnings=split.warnings,
            data_origins=origins,
            experimental_status=exp_status,
            val_f1_macro=val_f1,
            val_accuracy=val_acc,
            val_event_f1=val_evt_f1,
            val_neutral_far=val_far,
            estimated_flash_bytes=flash_b,
            estimated_sram_bytes=sram_b,
            selection_score=sel_score,
            training_participants=tuple(sorted({w.participant_id for w in split.train})),
            training_sessions=tuple(sorted({w.session_id for w in split.train})),
            development_participants=tuple(sorted({w.participant_id for w in split.train + split.val})),
            development_sessions=tuple(sorted({w.session_id for w in split.train + split.val})),
        )

    return bundles, split


def _effective_rank_score(bundle: TrainedBundle) -> float:
    """Retorna `selection_score` multicritério quando populado, ou `val_f1_macro` em mocks simples."""
    if bundle.selection_score != 0.0 or bundle.estimated_flash_bytes > 0:
        return float(bundle.selection_score)
    return float(bundle.val_f1_macro)


def select_best_embeddable_bundle(
    bundles: dict[str, TrainedBundle],
    prefer_compact_margin: float = 0.03,
) -> TrainedBundle:
    """Seleciona o modelo ótimo para embarque em microcontrolador (ESP32) por critério composto.

    Não seleciona apenas por acurácia de janela: combina F1-Macro de janelas, F1 de eventos
    contínuos (`EventStabilizer`), baixa taxa de falsos acionamentos em `NEUTRAL` e custo de
    memória Flash/SRAM. Prioriza `decision_tree` se seu índice multicritério estiver a até
    `prefer_compact_margin` do líder e sem degradação excessiva de FAR Neutro.
    """
    learned_names = ("decision_tree", "random_forest", "mlp_compact")
    learned_bundles = [b for name, b in bundles.items() if name in learned_names]

    if not learned_bundles:
        return max(bundles.values(), key=_effective_rank_score)

    best_learned = max(learned_bundles, key=_effective_rank_score)
    dt_bundle = bundles.get("decision_tree")

    if dt_bundle is not None and dt_bundle is not best_learned:
        dt_score = _effective_rank_score(dt_bundle)
        best_score = _effective_rank_score(best_learned)
        far_ok = dt_bundle.val_neutral_far <= (best_learned.val_neutral_far + 0.05)
        if dt_score >= (best_score - prefer_compact_margin) and far_ok:
            return dt_bundle

    return best_learned


def save_trained_bundle(bundle: TrainedBundle, path: str | Path) -> Path:
    """Serializa o bundle de modelo via joblib e grava seu descritor `.meta.json` adjacente."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(bundle, out_path)

    meta_path = (
        out_path.with_suffix(".meta.json")
        if out_path.suffix == ".joblib"
        else Path(str(out_path) + ".meta.json")
    )
    meta_path.write_text(
        json.dumps(bundle.to_meta_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def load_trained_bundle(path: str | Path) -> TrainedBundle:
    """Carrega um `TrainedBundle` serializado."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Bundle não encontrado no caminho: '{target}'")
    bundle: TrainedBundle = joblib.load(target)
    return bundle
