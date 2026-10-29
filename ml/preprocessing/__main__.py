"""CLI para executar o pré-processamento causal sobre sessões brutas (`python -m ml.preprocessing`)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ml.preprocessing.windowing import (
    load_raw_records_from_path,
    preprocess_records,
    save_windows_csv,
)
from ml.schemas import PreprocessingConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.preprocessing",
        description="MotionPet ML — Filtragem causal, janelamento e extracao de caracteristicas",
    )
    parser.add_argument(
        "--input",
        default="data/raw",
        help="Arquivo .jsonl/.csv ou diretorio com sessoes brutas (padrao: data/raw).",
    )
    parser.add_argument(
        "--output",
        default="data/processed/features_dataset.csv",
        help="Arquivo CSV de saida com janelas e caracteristicas.",
    )
    parser.add_argument("--window-size", type=int, default=10, help="Tamanho da janela em amostras.")
    parser.add_argument("--stride", type=int, default=2, help="Passo do janelamento em amostras.")
    parser.add_argument(
        "--saturation-cm",
        type=float,
        default=100.0,
        help="Distancia de saturacao para timeouts/leituras distantes.",
    )
    args = parser.parse_args(argv)

    cfg = PreprocessingConfig(
        window_size=args.window_size,
        stride=args.stride,
        saturation_cm=args.saturation_cm,
    )
    records = load_raw_records_from_path(args.input)
    windows = preprocess_records(records, config=cfg)
    out_path = save_windows_csv(windows, args.output)

    meta_path = Path(out_path).with_suffix(".meta.json")
    dist = Counter(w.label for w in windows)
    origins = sorted({w.data_origin for w in windows})
    meta = {
        "raw_samples": len(records),
        "windows_count": len(windows),
        "participants": sorted({w.participant_id for w in windows}),
        "sessions_count": len({w.session_id for w in windows}),
        "class_distribution": dict(dist),
        "data_origins": origins,
        "preprocessing_config": cfg.to_dict(),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(
        f"[OK] Pre-processadas {len(records)} amostras brutas -> {len(windows)} janelas em '{out_path}' "
        f"(classes={dict(dist)}, origens={origins})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
