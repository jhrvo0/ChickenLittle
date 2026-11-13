"""Execuções acadêmicas isoladas; nenhum destino padrão escreve em firmware/."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import datetime as dt
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import subprocess
from uuid import uuid4

from ml.collection.validator import validate_session_records
from ml.eda import generate_eda
from ml.evaluation.report import generate_evaluation_report, save_evaluation_json, save_evaluation_markdown
from ml.export.cpp_exporter import export_model_to_cpp_header
from ml.export.parity import run_cpp_parity_verification
from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records, save_windows_csv
from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, PreprocessingConfig
from ml.training.models import TrainingConfig
from ml.training.splitter import split_windows_grouped, windows_to_xy
from ml.training.trainer import save_trained_bundle, select_best_embeddable_bundle, train_candidate_models
from ml.validation import cross_validate_grouped, search_hyperparameters, tune_tree_depth

COHORT_ORIGIN = {"real": "real_hardware", "synthetic": "synthetic_simulator", "demo": "synthetic_simulator"}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_corpus(records, cohort):
    if cohort not in COHORT_ORIGIN:
        raise ValueError("Origem esperada: real, synthetic ou demo.")
    if not records:
        raise ValueError("Corpus vazio; avaliação real permanece pendente.")
    if {r.data_origin for r in records} != {COHORT_ORIGIN[cohort]}:
        raise ValueError("Origem incompatível/misturada: separar real, synthetic e demo antes de executar.")
    sessions = defaultdict(list)
    for rec in records:
        if rec.label not in CORE_GESTURE_CLASSES:
            raise ValueError(f"Classe não suportada neste experimento: {rec.label}")
        sessions[rec.session_id].append(rec)
    quality = {}
    for sid, rows in sessions.items():
        result = validate_session_records(rows)
        if not result.valid:
            raise ValueError(f"Sessão inválida {sid}: {result.errors}")
        quality[sid] = result.to_dict()
    return quality


def dataset_digest(records):
    """Hash canônico de todo registro, incluindo proveniência e data de captura."""
    digest = hashlib.sha256()
    for rec in sorted(records, key=lambda r: (r.session_id, r.sample_idx)):
        digest.update(json.dumps(asdict(rec), sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def run_experiment(raw_dir, *, cohort, output_root="data/experiments", seed=42,
                   leave_one_out=False, tracking_uri=None, verify_cpp=False, training_config=None, tune=False, orchestration=None, search=None):
    records = load_raw_records_from_path(raw_dir)
    quality = validate_corpus(records, cohort)
    p_cfg = PreprocessingConfig()
    cfg = training_config or TrainingConfig(seed=seed)
    if cfg.seed != seed:
        raise ValueError("A seed do TrainingConfig deve corresponder à seed do experimento.")
    windows = preprocess_records(records, p_cfg)
    split = split_windows_grouped(windows, seed=seed)
    if {w.label for w in split.train} != set(cfg.class_names):
        raise ValueError("Treino não cobre todas as classes; coletar mais sessões independentes.")
    fingerprint = dataset_digest(records)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    root = Path(output_root) / cohort
    out = root / run_id
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "experiment_id": run_id, "status": "running", "cohort": cohort,
                "data_origin": COHORT_ORIGIN[cohort], "dataset_sha256": fingerprint, "seed": seed,
                "orchestration": orchestration,
                "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
                "physical_validation": "pending", "software_only": cohort != "real",
                "feature_names": list(FEATURE_NAMES), "preprocessing": p_cfg.to_dict(),
                "training": cfg.to_dict(), "samples": len(records), "windows": len(windows),
                "session_quality": quality,
                "split": {"strategy": split.strategy, "train_groups": split.train_groups,
                          "validation_groups": split.val_groups, "test_groups": split.test_groups,
                          "warnings": split.warnings}, "tracking": {"status": "disabled"}}
    write_json(out / "manifest.json", manifest)
    try:
        # Snapshot somente de código do pipeline e corpus normalizado, nunca .env/credenciais.
        import shutil
        source_root = Path(__file__).resolve().parent
        source_hashes = {}
        for module in (source_root, *(source_root / d for d in ("collection", "preprocessing", "training", "evaluation", "export"))):
            for source in sorted(module.glob("*.py")):
                relative = Path("ml") / source.relative_to(source_root)
                target = out / "source" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                source_hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
        # Imports de coleta/classificação dependem destes pacotes mesmo sem serial.
        for package in ("terminal", "simulator"):
            for source in sorted((source_root.parent / package).rglob("*.py")):
                relative = source.relative_to(source_root.parent)
                target = out / "source" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                source_hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
        for name in ("pyproject.toml", "requirements.txt", "requirements-mlops.lock"):
            source = source_root.parent / name
            if source.is_file():
                shutil.copyfile(source, out / "source" / name)
                source_hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest["source_sha256"] = source_hashes
        (out / "corpus.jsonl").write_text("".join(json.dumps(asdict(r), allow_nan=False) + "\n" for r in records), encoding="utf-8")
        packages = {}
        for name in ("numpy", "scikit-learn", "joblib", "matplotlib", "mlflow-skinny", "paho-mqtt"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False) if shutil.which("git") else None
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False) if git else None
        manifest["environment"] = {"python": platform.python_version(), "platform": platform.platform(),
                                   "packages": packages, "git_head": git.stdout.strip() if git and git.returncode == 0 else None,
                                   "git_dirty": bool(dirty.stdout.strip()) if dirty and dirty.returncode == 0 else None}
        development = split.train + split.val
        group_attr = "participant_id" if split.strategy == "by_participant" else "session_id"
        dev_sessions = {w.session_id for w in development}
        manifest["eda"] = generate_eda([r for r in records if r.session_id in dev_sessions], development, out / "eda", cohort)
        if tune:
            cfg, manifest["tuning"] = tune_tree_depth(development, cfg, group_attr)
            manifest["training"] = cfg.to_dict()
        else:
            manifest["tuning"] = {"status": "not_requested", "trials": []}
        if search:
            cfg, manifest["hyperparameter_search"] = search_hyperparameters(development, cfg, group_attr, method=search)
            manifest["training"] = cfg.to_dict()
        else:
            manifest["hyperparameter_search"] = {"status": "not_requested"}
        manifest["validation"] = {"group_kfold": cross_validate_grouped(development, cfg, group_attr=group_attr)}
        manifest["validation"]["leave_one_group_out"] = (
            cross_validate_grouped(development, cfg, group_attr=group_attr, leave_one_out=True)
            if leave_one_out else {"status": "not_requested", "reason": "Opcional; nunca LOO por janela sobreposta."})
        # O teste externo não participa da CV nem da seleção multicritério na validação.
        bundles, trained_split = train_candidate_models(windows, cfg, p_cfg, require_real_data=cohort == "real")
        assert trained_split == split
        selected = select_best_embeddable_bundle(bundles)
        for name, bundle in bundles.items():
            bundle.dataset_sha256 = fingerprint
            bundle.experiment_id = run_id
            save_trained_bundle(bundle, out / "models" / f"{name}.joblib")
        save_trained_bundle(selected, out / "models" / "best_model.joblib")
        save_windows_csv(windows, out / "features.csv")
        report = generate_evaluation_report(bundles, split.test)
        report.update({"schema_version": 1, "cohort": cohort, "dataset_sha256": fingerprint,
                       "experiment_id": run_id, "evaluation_scope": "grouped_holdout",
                       "physical_validation": "pending"})
        save_evaluation_json(report, out / "evaluation.json")
        save_evaluation_markdown(report, out / "evaluation.md")
        header = out / "export" / "tinyml_model.h"
        export_meta = export_model_to_cpp_header(selected.estimator, selected.class_names, header,
                                                 preprocessing_config=p_cfg, experimental_status=selected.experimental_status,
                                                 model_name=selected.model_name)
        manifest["export"] = {"header": "export/tinyml_model.h", "cpp_parity": {"status": "not_requested"},
                              "estimated_flash_bytes": export_meta.estimated_flash_bytes,
                              "estimated_stack_sram_bytes": export_meta.estimated_stack_sram_bytes}
        if verify_cpp:
            X, _ = windows_to_xy(split.test, selected.class_names)
            session = next(iter(quality))
            parity = run_cpp_parity_verification(selected.estimator, header, X,
                                                 raw_window_records=[r for r in records if r.session_id == session],
                                                 preprocessing_config=p_cfg)
            manifest["export"]["cpp_parity"] = parity.to_dict()
            if not parity.passed:
                raise RuntimeError(f"Paridade C++ falhou: {parity.notes}")
        manifest["selected_model"] = selected.model_name
        manifest["experimental_status"] = selected.experimental_status
        manifest["status"] = "complete"
        write_json(out / "manifest.json", manifest)
        if tracking_uri:
            from ml.tracking import log_experiment
            manifest["tracking"] = log_experiment(tracking_uri, f"MotionLab-{cohort}", out, manifest, bundles, report)
            if manifest["hyperparameter_search"].get("status") == "evaluated":
                from ml.tracking import log_hyperparameter_search
                manifest["tracking"]["hyperparameter_search"] = log_hyperparameter_search(
                    tracking_uri, f"MotionLab-{cohort}-hiperparametros", manifest)
            write_json(out / "manifest.json", manifest)
        # Publicação atômica só após todos os passos solicitados concluírem.
        temporary = root / f".latest-{run_id}.json"
        write_json(temporary, {"schema_version": 1, "experiment_id": run_id})
        temporary.replace(root / "latest.json")
        return out
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(out / "manifest.json", manifest)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--cohort", required=True, choices=tuple(COHORT_ORIGIN))
    parser.add_argument("--output-root", default="data/experiments")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--leave-one-group-out", action="store_true")
    parser.add_argument("--tracking-uri")
    parser.add_argument("--verify-cpp", action="store_true")
    parser.add_argument("--tune", action="store_true", help="Compara profundidades 3, 5 e 7 da árvore só na CV de desenvolvimento.")
    parser.add_argument("--search", choices=("grid", "random"),
                        help="Grid Search ou Random Search de hiperparâmetros por modelo, com GroupKFold no desenvolvimento.")
    parser.add_argument("--extended-models", action="store_true", help="Inclui KNN e AdaBoost na comparação.")
    parser.add_argument("--learned-baseline", action="store_true", help="Inclui o baseline aprendido (árvore de profundidade 1).")
    args = parser.parse_args(argv)
    cfg = TrainingConfig(seed=args.seed, include_extended_candidates=args.extended_models,
                         include_learned_baseline=args.learned_baseline)
    out = run_experiment(args.raw_dir, cohort=args.cohort, output_root=args.output_root, seed=args.seed,
                         leave_one_out=args.leave_one_group_out, tracking_uri=args.tracking_uri, verify_cpp=args.verify_cpp, tune=args.tune,
                         training_config=cfg, search=args.search)
    print(f"Experimento salvo em {out}; cohort={args.cohort}; validação física pendente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
