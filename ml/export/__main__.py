"""CLI para exportar modelo treinado para `firmware/gestures/tinyml_model.h` e testar paridade C++."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.export.cpp_exporter import export_model_to_cpp_header
from ml.export.parity import run_cpp_parity_verification
from ml.preprocessing.windowing import load_windows_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.export",
        description="MotionPet ML — Exportacao C++ estatica (ESP32) e teste nativo de paridade",
    )
    parser.add_argument(
        "--model",
        default="data/models/best_model.joblib",
        help="Caminho do bundle .joblib treinado.",
    )
    parser.add_argument(
        "--dataset",
        default="data/processed/features_dataset.csv",
        help="Dataset de janelas para teste de paridade Python vs C++.",
    )
    parser.add_argument(
        "--output",
        default="firmware/gestures/tinyml_model.h",
        help="Caminho do header C/C++ exportado.",
    )
    args = parser.parse_args(argv)

    from ml.training.splitter import windows_to_xy
    from ml.training.trainer import load_trained_bundle

    bundle = load_trained_bundle(args.model)
    meta = export_model_to_cpp_header(
        estimator=bundle.estimator,
        class_names=bundle.class_names,
        output_path=args.output,
        preprocessing_config=bundle.preprocessing_config,
        experimental_status=bundle.experimental_status,
        model_name=bundle.model_name,
    )

    windows = load_windows_csv(args.dataset)
    X_all, _ = windows_to_xy(windows, class_names=bundle.class_names)
    X_sample = X_all[: min(100, len(X_all))]

    parity = run_cpp_parity_verification(
        estimator=bundle.estimator,
        header_path=args.output,
        X_test=X_sample,
        preprocessing_config=bundle.preprocessing_config,
    )

    report_path = Path(args.output).with_suffix(".parity.json")
    report_path.write_text(
        json.dumps(
            {"export": meta.__dict__, "parity": parity.to_dict()},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"[OK] Header C++ exportado em '{meta.header_path}' ({meta.model_type}, "
        f"Flash~{meta.estimated_flash_bytes}B, SRAM~{meta.estimated_stack_sram_bytes}B)"
    )
    print(
        f"[PARIDADE {parity.execution_backend}] passed={parity.passed} | "
        f"concordancia={parity.class_agreement_rate:.2%} | "
        f"max_diff_proba={parity.max_abs_proba_diff:.2e} | zero_heap={parity.zero_dynamic_alloc_verified}"
    )
    return 0 if parity.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
