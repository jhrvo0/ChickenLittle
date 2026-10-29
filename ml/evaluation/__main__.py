"""Ponto de entrada de linha de comando para avaliação comparativa e relatórios."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ml.evaluation.report import (
    format_evaluation_markdown,
    generate_evaluation_report,
    save_evaluation_json,
    save_evaluation_markdown,
)
from ml.preprocessing.windowing import load_windows_csv
from ml.schemas import StabilizerConfig
from ml.training.models import TrainingConfig
from ml.training.splitter import split_windows_grouped
from ml.training.trainer import (
    TrainedBundle,
    load_trained_bundle,
    save_trained_bundle,
    select_best_embeddable_bundle,
    train_candidate_models,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline de avaliação e benchmarking de modelos MotionPet.",
    )
    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        default="data/processed/features_dataset.csv",
        help="Caminho para o dataset de janelas (CSV)",
    )
    parser.add_argument(
        "--models-dir",
        "-m",
        type=str,
        default="data/models",
        help="Diretório contendo os bundles treinados (.joblib) ou destino para salvá-los",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="data/reports",
        help="Diretório para salvar evaluation_report.json e evaluation_report.md",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Semente para reproduzir o particionamento",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.60,
        help="Limiar de confiança para o estabilizador",
    )
    parser.add_argument(
        "--min-consecutive-windows",
        type=int,
        default=2,
        help="Janelas consecutivas mínimas para validar o gesto",
    )
    parser.add_argument(
        "--cooldown-ms",
        type=int,
        default=700,
        help="Período de cooldown em milissegundos",
    )

    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        print(f"[ERRO] Dataset não encontrado: '{dataset_path}'", file=sys.stderr)
        return 1

    models_dir = Path(args.models_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Carregando janelas de '{dataset_path}'...")
    windows = load_windows_csv(dataset_path)
    print(f"[*] {len(windows)} janelas carregadas.")

    print(f"[*] Particionando conjunto agrupado (seed={args.seed})...")
    split = split_windows_grouped(windows, seed=args.seed)

    bundles: dict[str, TrainedBundle] = {}
    candidate_names = ("rule_baseline", "decision_tree", "random_forest", "mlp_compact")

    # Verifica se os modelos já estão salvos no diretório
    models_exist = all((models_dir / f"{name}.joblib").is_file() for name in candidate_names)

    if models_exist:
        print(f"[*] Carregando bundles treinados de '{models_dir}'...")
        for name in candidate_names:
            bundles[name] = load_trained_bundle(models_dir / f"{name}.joblib")
    else:
        print(f"[*] Modelos não encontrados em '{models_dir}'. Treinando novos candidatos...")
        models_dir.mkdir(parents=True, exist_ok=True)
        cfg = TrainingConfig(seed=args.seed)
        bundles, _ = train_candidate_models(windows, training_config=cfg)
        for name, b in bundles.items():
            save_trained_bundle(b, models_dir / f"{name}.joblib")
        best = select_best_embeddable_bundle(bundles)
        save_trained_bundle(best, models_dir / "best_model.joblib")
        print(f"[*] Bundles treinados e salvos em '{models_dir}'.")

    stab_cfg = StabilizerConfig(
        min_confidence=args.min_confidence,
        min_consecutive_windows=args.min_consecutive_windows,
        cooldown_ms=args.cooldown_ms,
    )

    print(f"[*] Avaliando {len(bundles)} modelos sobre {len(split.test)} janelas de teste...")
    report = generate_evaluation_report(
        bundles=bundles,
        test_windows=split.test,
        stabilizer_config=stab_cfg,
    )

    json_path = save_evaluation_json(report, output_dir / "evaluation_report.json")
    md_path = save_evaluation_markdown(report, output_dir / "evaluation_report.md")

    print("\n" + "=" * 65)
    print("RELATÓRIO DE AVALIAÇÃO GERADO COM SUCESSO")
    print("=" * 65)
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"Status Experimental: {report.get('experimental_status')}")
    print(f"Modelo Recomendado: {report.get('recommended_model')}")

    print("\n" + format_evaluation_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
