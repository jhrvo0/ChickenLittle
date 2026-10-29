"""Treinamento dos modelos candidatos, seleção e serialização de bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
from sklearn.metrics import f1_score

from ml.schemas import (
    CORE_GESTURE_CLASSES,
    FEATURE_NAMES,
    DataOrigin,
    ExperimentalStatus,
    PreprocessingConfig,
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
        }


def train_candidate_models(
    windows: Sequence[WindowSample],
    training_config: TrainingConfig | None = None,
    preprocessing_config: PreprocessingConfig | None = None,
) -> tuple[dict[str, TrainedBundle], DatasetSplit]:
    """Particiona os dados sem vazamento, treina os 4 modelos candidatos e calcula F1 de validação."""
    cfg = training_config or TrainingConfig()
    p_cfg = preprocessing_config or PreprocessingConfig()

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
        if len(y_val) > 0:
            y_pred = model.predict(X_val)
            val_f1 = float(f1_score(y_val, y_pred, average="macro", zero_division=0))
        else:
            val_f1 = 0.0

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
        )

    return bundles, split


def select_best_embeddable_bundle(
    bundles: dict[str, TrainedBundle],
    prefer_compact_margin: float = 0.03,
) -> TrainedBundle:
    """Seleciona o modelo ótimo para embarque em microcontrolador (ESP32).

    Avalia os modelos aprendidos estatisticamente (decision_tree, random_forest, mlp_compact).
    Prioriza `decision_tree` se sua métrica F1 de validação estiver a até `prefer_compact_margin`
    do melhor modelo, dado o seu baixo consumo de Flash/SRAM e ausência de alocação dinâmica.
    """
    learned_names = ("decision_tree", "random_forest", "mlp_compact")
    learned_bundles = [b for name, b in bundles.items() if name in learned_names]

    if not learned_bundles:
        # Fallback caso apenas o rule_baseline esteja presente
        return max(bundles.values(), key=lambda b: b.val_f1_macro)

    best_learned = max(learned_bundles, key=lambda b: b.val_f1_macro)
    dt_bundle = bundles.get("decision_tree")

    if dt_bundle is not None:
        if dt_bundle.val_f1_macro >= (best_learned.val_f1_macro - prefer_compact_margin):
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
