"""Orquestrador completo para Dados Físicos Reais (Seções 5 e 6 do Ciclo 5):

1. Valida integridade temporal e garante 100% `real_hardware` (bloqueando qualquer mistura sintética).
2. Aplica filtragem causal e extrai as 11 características.
3. Particiona sem vazamento (por participante/sessão) e treina `rule_baseline`, `decision_tree`,
   `random_forest` e `mlp_compact`.
4. Compara modelos na validação agrupada e seleciona pelo índice multicritério embarcado
   (F1 janela + F1 eventos contínuos + supressão de FAR Neutro + custo Flash/SRAM).
5. Avalia UMA ÚNICA VEZ no conjunto de teste independente (matrizes de confusão, métricas por classe,
   FAR em sequências NEUTRAL e eventos contínuos).
6. Exporta o modelo vencedor para C++ (`tinyml_model.h`), verifica paridade numérica Python/C++
   (`cl.exe` / `xtensa-esp32-elf-g++`) e, opcionalmente, valida build PlatformIO do firmware.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ml.collection.validator import validate_session_records
from ml.evaluation.report import (
    generate_evaluation_report,
    save_evaluation_json,
    save_evaluation_markdown,
)
from ml.export.cpp_exporter import export_model_to_cpp_header
from ml.export.parity import ParityCheckReport, run_cpp_parity_verification
from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records
from ml.schemas import PreprocessingConfig, StabilizerConfig
from ml.training.models import TrainingConfig
from ml.training.splitter import windows_to_xy
from ml.training.trainer import (
    SyntheticDataContaminationError,
    assert_strictly_real_data,
    save_trained_bundle,
    select_best_embeddable_bundle,
    train_candidate_models,
)
from terminal.bench.assistant import _detect_platformio_cli


@dataclass(frozen=True)
class RealPipelineExecutionSummary:
    """Resumo auditável da execução completa das Seções 5 e 6 sobre dataset físico."""

    raw_dir: str
    total_sessions: int
    total_raw_samples: int
    total_windows: int
    participants: tuple[str, ...]
    experimental_status: str
    split_strategy: str
    selected_model: str
    selected_selection_score: float
    selected_val_f1_macro: float
    selected_val_event_f1: float
    selected_test_f1_macro: float
    selected_test_event_f1: float
    selected_test_neutral_far: float
    exported_header_path: str
    estimated_flash_bytes: int
    estimated_stack_sram_bytes: int
    cpp_parity_passed: bool
    cpp_parity_agreement: float
    cpp_max_proba_diff: float
    firmware_build_verified: bool
    evaluation_json_path: str
    evaluation_md_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def execute_real_data_pipeline(
    raw_dir: str | Path = "data/raw/real",
    models_dir: str | Path = "data/models/real",
    reports_dir: str | Path = "data/reports",
    export_header_path: str | Path = "firmware/gestures/tinyml_model.h",
    allow_synthetic_for_dry_run: bool = False,
    verify_firmware_build: bool = False,
    seed: int = 42,
) -> RealPipelineExecutionSummary:
    """Executa o fluxo fim a fim das Seções 5 e 6 do Ciclo 5."""
    raw_path = Path(raw_dir)
    records = load_raw_records_from_path(raw_path)
    if not records:
        raise FileNotFoundError(
            f"Nenhuma sessao encontrada em '{raw_path}'. "
            "Capture dados reais do ESP32 primeiro com 'python -m ml.collection --serial-port COMx --guided'."
        )

    if not allow_synthetic_for_dry_run:
        assert_strictly_real_data(records, context=f"diretorio de dados reais '{raw_path}'")

    # 1. Validação de integridade sessão a sessão
    by_session: dict[str, list] = defaultdict(list)
    for r in records:
        by_session[r.session_id].append(r)

    invalid_sessions: list[str] = []
    for sid, s_recs in sorted(by_session.items()):
        rep_v = validate_session_records(s_recs)
        if not rep_v.valid:
            invalid_sessions.append(f"{sid}: {'; '.join(rep_v.errors)}")
    if invalid_sessions:
        raise ValueError(
            "Falha de integridade nas sessoes coletadas:\n  - " + "\n  - ".join(invalid_sessions)
        )

    # 2 e 3. Filtragem causal + extração das 11 características
    pre_cfg = PreprocessingConfig()
    stab_cfg = StabilizerConfig()
    train_cfg = TrainingConfig(seed=seed)
    windows = preprocess_records(records, config=pre_cfg)
    if len(windows) < 12:
        raise ValueError(
            f"Quantidade insuficiente de janelas extraidas ({len(windows)} < 12) para particionamento "
            "treino/validacao/teste."
        )

    if not allow_synthetic_for_dry_run:
        assert_strictly_real_data(windows, context="janelas extraidas do dataset real")

    # 4, 5 e 6. Treinamento dos 4 modelos + validação agrupada + seleção multicritério
    bundles, split = train_candidate_models(
        windows,
        training_config=train_cfg,
        preprocessing_config=pre_cfg,
        stabilizer_config=stab_cfg,
        require_real_data=(not allow_synthetic_for_dry_run),
    )
    selected = select_best_embeddable_bundle(bundles)

    out_models = Path(models_dir)
    out_models.mkdir(parents=True, exist_ok=True)
    for name, b in bundles.items():
        save_trained_bundle(b, out_models / f"{name}.joblib")
    save_trained_bundle(selected, out_models / "best_model.joblib")

    # 7, 8, 9 e 10. Avaliação ÚNICA no conjunto de teste independente
    eval_windows = split.test if split.test else split.val
    report = generate_evaluation_report(
        bundles=bundles,
        test_windows=eval_windows,
        stabilizer_config=stab_cfg,
    )
    out_reports = Path(reports_dir)
    json_rep_p = save_evaluation_json(report, out_reports / "real_model_evaluation.json")
    md_rep_p = save_evaluation_markdown(report, out_reports / "real_model_evaluation.md")

    # Seção 6. Exportação C++ estática + Paridade Python/C++ nativo e Xtensa
    exp_meta = export_model_to_cpp_header(
        estimator=selected.estimator,
        class_names=selected.class_names,
        output_path=export_header_path,
        preprocessing_config=pre_cfg,
        experimental_status=selected.experimental_status,
        model_name=selected.model_name,
    )
    X_eval, _ = windows_to_xy(eval_windows, class_names=selected.class_names)
    first_session_records = by_session[sorted(by_session.keys())[0]]
    parity: ParityCheckReport = run_cpp_parity_verification(
        estimator=selected.estimator,
        header_path=export_header_path,
        X_test=X_eval,
        raw_window_records=first_session_records,
        preprocessing_config=pre_cfg,
    )
    parity_json_p = Path(export_header_path).with_suffix(".parity.json")
    parity_json_p.write_text(json.dumps(parity.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not parity.passed:
        raise RuntimeError(f"Falha na verificacao de paridade Python/C++ do modelo exportado: {parity.notes}")

    fw_built = False
    if verify_firmware_build:
        pio_exe = _detect_platformio_cli()
        if pio_exe is None:
            raise RuntimeError("PlatformIO CLI ('pio') nao encontrado para --verify-firmware-build.")
        proc = subprocess.run(
            [pio_exe, "run", "-d", "firmware"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Falha ao recompilar firmware com novo tinyml_model.h:\n{proc.stderr}")
        fw_built = True

    sel_metrics = report["models"][selected.model_name]
    participants = tuple(sorted({r.participant_id for r in records}))

    return RealPipelineExecutionSummary(
        raw_dir=str(raw_path),
        total_sessions=len(by_session),
        total_raw_samples=len(records),
        total_windows=len(windows),
        participants=participants,
        experimental_status=selected.experimental_status,
        split_strategy=split.strategy,
        selected_model=selected.model_name,
        selected_selection_score=selected.selection_score,
        selected_val_f1_macro=round(selected.val_f1_macro, 4),
        selected_val_event_f1=round(selected.val_event_f1, 4),
        selected_test_f1_macro=float(sel_metrics["test_f1_macro"]),
        selected_test_event_f1=float(sel_metrics["event_level"]["event_f1"]),
        selected_test_neutral_far=float(sel_metrics["false_activation_rate_neutral"]),
        exported_header_path=str(export_header_path),
        estimated_flash_bytes=exp_meta.estimated_flash_bytes,
        estimated_stack_sram_bytes=exp_meta.estimated_stack_sram_bytes,
        cpp_parity_passed=parity.passed,
        cpp_parity_agreement=parity.class_agreement_rate,
        cpp_max_proba_diff=parity.max_abs_proba_diff,
        firmware_build_verified=fw_built,
        evaluation_json_path=str(json_rep_p),
        evaluation_md_path=str(md_rep_p),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.real_pipeline",
        description=(
            "MotionPet Ciclo 5 — Treinamento com dados fisicos reais, selecao multicriterio, "
            "avaliacao unica de teste e exportacao C++ TinyML com paridade."
        ),
    )
    parser.add_argument("--raw-dir", default="data/raw/real", help="Diretorio contendo sessoes fisicas reais.")
    parser.add_argument("--models-dir", default="data/models/real", help="Diretorio de saida dos bundles .joblib.")
    parser.add_argument("--reports-dir", default="data/reports", help="Diretorio dos relatorios JSON/MD.")
    parser.add_argument(
        "--export-header",
        default="firmware/gestures/tinyml_model.h",
        help="Caminho do header C++ TinyML gerado.",
    )
    parser.add_argument(
        "--verify-firmware-build",
        action="store_true",
        help="Recompila o firmware ESP32 via PlatformIO apos exportar o novo tinyml_model.h.",
    )
    parser.add_argument(
        "--allow-synthetic-dry-run",
        action="store_true",
        help="Permite testar o script em pasta temporaria sintetica (mantendo status AWAITING_REAL_DATA).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed deterministica.")
    args = parser.parse_args(argv)

    try:
        summary = execute_real_data_pipeline(
            raw_dir=args.raw_dir,
            models_dir=args.models_dir,
            reports_dir=args.reports_dir,
            export_header_path=args.export_header,
            allow_synthetic_for_dry_run=args.allow_synthetic_dry_run,
            verify_firmware_build=args.verify_firmware_build,
            seed=args.seed,
        )
    except (FileNotFoundError, SyntheticDataContaminationError, ValueError, RuntimeError) as exc:
        print(f"[BLOQUEADO/ERRO] {exc}")
        return 1

    print("=== PIPELINE TINYML CONCLUIDO ===")
    print(f"Status Experimental: {summary.experimental_status}")
    print(f"Sessoes / Amostras:  {summary.total_sessions} sessoes | {summary.total_raw_samples} amostras | {summary.total_windows} janelas")
    print(f"Participantes:       {', '.join(summary.participants)} (split={summary.split_strategy})")
    print(
        f"Modelo Selecionado:  {summary.selected_model} (score={summary.selected_selection_score:.4f}, "
        f"val_f1={summary.selected_val_f1_macro:.4f}, val_event_f1={summary.selected_val_event_f1:.4f})"
    )
    print(
        f"Avaliacao Teste:     test_f1={summary.selected_test_f1_macro:.4f} | "
        f"event_f1={summary.selected_test_event_f1:.4f} | FAR_Neutro={summary.selected_test_neutral_far:.4f}"
    )
    print(
        f"Header C++ TinyML:   {summary.exported_header_path} "
        f"(Flash~{summary.estimated_flash_bytes} B, Stack~{summary.estimated_stack_sram_bytes} B)"
    )
    print(
        f"Paridade Python/C++: {'APROVADA' if summary.cpp_parity_passed else 'FALHOU'} "
        f"(acordo={summary.cpp_parity_agreement:.4%}, max_diff={summary.cpp_max_proba_diff:.2e})"
    )
    if summary.firmware_build_verified:
        print("Build PlatformIO:    APROVADO (firmware.bin atualizado)")
    print(f"Relatorios:          {summary.evaluation_md_path} | {summary.evaluation_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
