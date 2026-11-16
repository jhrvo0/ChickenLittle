"""Figuras e tabelas do relatório SBC a partir de um experimento identificado.

Uso: python -m ml.report_assets data/experiments/synthetic/<id> --output reports/figuras-am

Gera as cinco figuras de EDA (copiadas do experimento), o gráfico treino × validação, as matrizes de
confusão do teste e `tabelas.json` com estatísticas descritivas, busca de hiperparâmetros, validação
cruzada, holdout e comparação estatística. Nada é recalculado a partir do teste além do que o
experimento já registrou; as estatísticas descritivas usam só os grupos de desenvolvimento.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

SHORT = {"NEUTRAL": "N", "APPROACH": "A", "RETREAT": "R", "HOLD": "H"}
LABELS = {"rule_baseline": "Regras", "decision_stump_baseline": "Árvore prof. 1", "decision_tree": "Árvore",
          "random_forest": "Random Forest", "mlp_compact": "MLP", "knn": "KNN", "adaboost": "AdaBoost"}
ORDER = ["decision_stump_baseline", "rule_baseline", "decision_tree", "random_forest", "knn", "adaboost", "mlp_compact"]


def _ordered(names):
    return [n for n in ORDER if n in names] + [n for n in names if n not in ORDER]


def descriptive_statistics(run):
    """Média, desvio, mínimo, mediana e máximo das 11 features nas janelas de desenvolvimento."""
    import numpy as np
    from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records
    from ml.schemas import FEATURE_NAMES, PreprocessingConfig
    from ml.training.splitter import split_windows_grouped

    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    rows = load_raw_records_from_path(run / "corpus.jsonl")
    windows = preprocess_records(rows, PreprocessingConfig.from_dict(manifest["preprocessing"]))
    split = split_windows_grouped(windows, seed=manifest["seed"])
    assert sorted(split.test_groups) == sorted(manifest["split"]["test_groups"]), "Split diverge do manifesto."
    X = np.array([w.features for w in split.train + split.val], dtype=float)
    return {name: {"mean": float(X[:, i].mean()), "std": float(X[:, i].std()), "min": float(X[:, i].min()),
                   "median": float(np.median(X[:, i])), "max": float(X[:, i].max())}
            for i, name in enumerate(FEATURE_NAMES)}


def build(run_dir, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    run, out = Path(run_dir), Path(output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((run / "evaluation.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Relatório exige experimento completo.")

    for figure in manifest["eda"]["figures"]:
        source = (run / figure["path"]).with_suffix(".png")
        shutil.copyfile(source, out / source.name)

    cv = manifest["validation"]["group_kfold"]["models"]
    names = _ordered([n for n in cv if cv[n].get("train_f1_macro_mean") is not None])
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.bar(x - 0.2, [cv[n]["train_f1_macro_mean"] for n in names], 0.4, label="Treino (fold)", color="#b9c7dc")
    ax.bar(x + 0.2, [cv[n]["f1_macro_mean"] for n in names], 0.4, yerr=[cv[n]["f1_macro_std"] for n in names],
           capsize=3, label="Validação (fold)", color="#2f5d9a")
    ax.set_xticks(x, [LABELS.get(n, n) for n in names], fontsize=8)
    ax.set(ylim=(0, 1.05), ylabel="F1-macro")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "06_ajuste.png", dpi=200)
    plt.close(fig)

    models = _ordered(list(report["models"]))
    classes = manifest["training"]["class_names"]
    cols = 4
    rows_n = int(np.ceil(len(models) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(7.2, 1.95 * rows_n))
    for ax in axes.flat:
        ax.axis("off")
    for ax, name in zip(axes.flat, models):
        matrix = np.array(report["models"][name]["confusion_matrix"])
        ax.axis("on")
        ax.imshow(matrix, cmap="Blues")
        ax.set_title(f"{LABELS.get(name, name)} (F1 {report['models'][name]['test_f1_macro']:.2f})", fontsize=7)
        ticks = [SHORT.get(c, c) for c in classes]
        ax.set_xticks(range(len(classes)), ticks, fontsize=6)
        ax.set_yticks(range(len(classes)), ticks, fontsize=6)
        for i, line in enumerate(matrix):
            for j, value in enumerate(line):
                ax.text(j, i, str(value), ha="center", va="center", fontsize=6,
                        color="white" if value > matrix.max() / 2 else "black")
    fig.tight_layout()
    fig.savefig(out / "07_matrizes.png", dpi=200)
    plt.close(fig)

    search = manifest.get("hyperparameter_search", {})
    tables = {
        "experiment_id": manifest["experiment_id"], "dataset_sha256": manifest["dataset_sha256"],
        "samples": manifest["samples"], "windows": manifest["windows"], "split": manifest["split"],
        "class_distribution_development": manifest["eda"]["class_distribution"],
        "descriptive_statistics_development": descriptive_statistics(run),
        "hyperparameter_search": {name: {"best_params": fam.get("best_params"), "best_cv_f1_macro": fam.get("best_cv_f1_macro"),
                                         "combinations": fam.get("evaluated_combinations")}
                                  for name, fam in search.get("models", {}).items()},
        "cross_validation": {method: {"method": manifest["validation"][method].get("method"),
                                      "n_splits": manifest["validation"][method].get("n_splits"),
                                      "models": {n: {k: m.get(k) for k in ("f1_macro_mean", "f1_macro_std", "train_f1_macro_mean",
                                                                         "generalization_gap", "fit_diagnosis")}
                                                 for n, m in manifest["validation"][method].get("models", {}).items()}}
                             for method in ("group_kfold", "leave_one_group_out") if manifest["validation"][method].get("models")},
        "holdout": {n: {"f1_macro": m["test_f1_macro"], "accuracy": m["accuracy"],
                        "far_neutral": m.get("false_activation_rate_neutral"),
                        "per_class": m["per_class"], "confusion_matrix": m["confusion_matrix"]}
                    for n, m in report["models"].items()},
        "model_comparison": manifest.get("model_comparison"),
        "selected_model": manifest["selected_model"], "export": manifest.get("export"),
    }
    (out / "tabelas.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--output", default="reports/figuras-am")
    args = parser.parse_args(argv)
    print(build(args.run_dir, args.output))


if __name__ == "__main__":
    main()
