"""Ponto de entrada de linha de comando para treinamento e seleção de modelos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ml.preprocessing.windowing import load_windows_csv
from ml.training.models import TrainingConfig
from ml.training.trainer import (
    save_trained_bundle,
    select_best_embeddable_bundle,
    train_candidate_models,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline de treinamento e seleção de classificadores MotionPet.",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="data/processed/features_dataset.csv",
        help="Caminho para o dataset de janelas pré-processadas (CSV)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="data/models",
        help="Diretório onde os bundles treinados (.joblib e .meta.json) serão salvos",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Semente pseudoaleatória para particionamento e modelos",
    )
    parser.add_argument(
        "--prefer-compact-margin",
        type=float,
        default=0.03,
        help="Margem de tolerância F1 para priorizar DecisionTree para o ESP32",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"[ERRO] Dataset de entrada não encontrado: '{input_path}'", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Carregando janelas de '{input_path}'...")
    windows = load_windows_csv(input_path)
    print(f"[*] {len(windows)} janelas carregadas com sucesso.")

    cfg = TrainingConfig(seed=args.seed)

    print("[*] Particionando dataset sem vazamento e treinando os 4 modelos candidatos...")
    bundles, split = train_candidate_models(windows, training_config=cfg)

    print("\n" + "=" * 65)
    print("RESUMO DO PARTICIONAMENTO E INTEGRIDADE")
    print("=" * 65)
    print(f"Estratégia de Split: {split.strategy}")
    print(f"Grupos Treino ({len(split.train_groups)}): {split.train_groups}")
    print(f"Grupos Validação ({len(split.val_groups)}): {split.val_groups}")
    print(f"Grupos Teste ({len(split.test_groups)}): {split.test_groups}")
    print(f"Amostras: Treino={len(split.train)}, Validação={len(split.val)}, Teste={len(split.test)}")

    if split.warnings:
        print("\n[AVISOS DE SPLIT]")
        for w in split.warnings:
            print(f"  - {w}")

    first_bundle = next(iter(bundles.values()))
    print(f"\nStatus Experimental: {first_bundle.experimental_status}")
    if first_bundle.experimental_status == "AWAITING_REAL_DATA":
        print("  (!) AVISO: Dataset contém dados sintéticos. Os resultados validam apenas o código do pipeline.")

    print("\n" + "=" * 65)
    print("RESULTADOS DE TREINAMENTO (VALIDAÇÃO F1-MACRO)")
    print("=" * 65)
    for name, bundle in bundles.items():
        print(f"  - {name:<18}: Val F1-Macro = {bundle.val_f1_macro:.4f}")

    best_bundle = select_best_embeddable_bundle(bundles, prefer_compact_margin=args.prefer_compact_margin)
    print("\n" + "=" * 65)
    print(f"MODELO ÓTIMO PARA EMBARQUE NO ESP32: '{best_bundle.model_name}'")
    print(f"Val F1-Macro = {best_bundle.val_f1_macro:.4f}")
    print("=" * 65)

    print(f"\n[*] Salvando bundles em '{output_dir}'...")
    for name, bundle in bundles.items():
        p = save_trained_bundle(bundle, output_dir / f"{name}.joblib")
        print(f"  -> Salvo: {p.name}")

    best_path = save_trained_bundle(best_bundle, output_dir / "best_model.joblib")
    print(f"  -> Melhor modelo: {best_path.name}")
    print("\n[OK] Treinamento concluído com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
