"""Publicação explícita e atômica de um experimento local, sem alterar firmware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4


def resolve_deployment(pointer, experiments_root):
    spec = json.loads(Path(pointer).read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1 or spec.get("cohort") not in ("demo", "synthetic", "real"):
        raise ValueError("Publicação incompatível.")
    root = Path(experiments_root).resolve()
    model = (root / spec["model_relpath"]).resolve()
    if not model.is_relative_to(root) or model.name != "best_model.joblib":
        raise ValueError("Modelo fora da raiz de experimentos.")
    manifest = json.loads((model.parent.parent / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["status"] != "complete" or
            any(manifest[k] != spec[k] for k in ("cohort", "experiment_id", "dataset_sha256")) or
            model.parent.parent.name != spec["experiment_id"] or
            model.parent.parent.parent.name != spec["cohort"]):
        raise ValueError("Publicação não corresponde a experimento completo.")
    if hashlib.sha256(model.read_bytes()).hexdigest() != spec["model_sha256"]:
        raise ValueError("Hash do modelo divergente.")
    return model, spec


def publish_experiment(run_dir, pointer, experiments_root):
    run = Path(run_dir).resolve()
    root = Path(experiments_root).resolve()
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    model = run / "models/best_model.joblib"
    spec = {"schema_version": 1, **{k: manifest[k] for k in ("cohort", "experiment_id", "dataset_sha256")},
            "model_relpath": model.relative_to(root).as_posix(),
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "physical_validation": "pending"}
    pointer = Path(pointer)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_name(f".{pointer.name}-{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        resolve_deployment(temporary, root)
        temporary.replace(pointer)
    finally:
        temporary.unlink(missing_ok=True)
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--pointer", required=True)
    parser.add_argument("--experiments-root", default="data/experiments")
    args = parser.parse_args(argv)
    print(json.dumps(publish_experiment(args.run_dir, args.pointer, args.experiments_root)))


if __name__ == "__main__":
    main()
