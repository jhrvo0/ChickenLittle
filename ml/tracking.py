"""MLflow opcional: uma execução pai e uma execução filha por candidato."""
from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path


def log_experiment(uri, experiment_name, run_dir, manifest, bundles, report):
    import mlflow
    import mlflow.sklearn

    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment_name)
    tags = {"cohort": manifest["cohort"], "dataset_sha256": manifest["dataset_sha256"],
            "physical_validation": "pending", "experiment_id": manifest["experiment_id"]}
    with mlflow.start_run(run_name=manifest["experiment_id"], tags=tags) as parent:
        mlflow.log_params({"seed": manifest["seed"], "split_strategy": manifest["split"]["strategy"],
                           "selection": "validation_embedded_score", "cv_scope": "development_only"})
        for name, bundle in bundles.items():
            learned_baseline = "decision_stump_baseline" in bundles
            role = ("baseline" if name == "decision_stump_baseline" else "domain_reference" if name == "rule_baseline" else "comparison") if learned_baseline else ("baseline" if name == "rule_baseline" else "comparison")
            with mlflow.start_run(run_name=name, nested=True, tags={**tags, "role": role}):
                mlflow.log_params({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                                   for k, v in bundle.training_config.to_dict().items()})
                mlflow.log_params({f"preprocessing_{k}": v for k, v in bundle.preprocessing_config.to_dict().items()})
                metrics = report["models"][name]
                mlflow.log_metrics({"val_f1_macro": bundle.val_f1_macro, "selection_score": bundle.selection_score,
                                    "test_f1_macro": metrics["test_f1_macro"], "test_accuracy": metrics["accuracy"],
                                    "test_event_f1": metrics["event_level"]["event_f1"]})
                far_status = metrics.get("false_activation_rate_neutral_status", "pending")
                mlflow.set_tag("test_neutral_far_status", far_status)
                mlflow.log_metric("test_neutral_support", metrics.get("neutral_support", 0))
                if far_status == "evaluated":
                    mlflow.log_metric("test_neutral_far", metrics["false_activation_rate_neutral"])
                for method, validation in manifest["validation"].items():
                    cv = validation.get("models", {}).get(name, {})
                    if cv.get("f1_macro_mean") is not None:
                        mlflow.log_metrics({f"{method}_f1_mean": cv["f1_macro_mean"], f"{method}_f1_std": cv["f1_macro_std"]})
                    if cv.get("train_f1_macro_mean") is not None:
                        mlflow.log_metrics({f"{method}_train_f1_mean": cv["train_f1_macro_mean"],
                                            f"{method}_generalization_gap": cv["generalization_gap"]})
                        mlflow.set_tag(f"{method}_fit_diagnosis", cv["fit_diagnosis"])
                mlflow.sklearn.log_model(bundle.estimator, name="model", serialization_format="cloudpickle",
                                        code_paths=[str(Path(run_dir) / "source" / "ml")],
                                        pip_requirements=[f"scikit-learn=={version('scikit-learn')}",
                                                          f"numpy=={version('numpy')}", f"cloudpickle=={version('cloudpickle')}"])
                mlflow.log_artifact(str(Path(run_dir) / "models" / f"{name}.joblib"), artifact_path="bundle")
        for trial in manifest.get("tuning", {}).get("trials", []):
            with mlflow.start_run(run_name=f"tuning-tree-depth-{trial['dt_max_depth']}", nested=True, tags={**tags, "role": "tuning"}):
                mlflow.log_params({"dt_max_depth": trial["dt_max_depth"], "seed": manifest["seed"], "scope": "development_only"})
                if trial["cv_f1_macro"] is not None:
                    mlflow.log_metric("cv_f1_macro", trial["cv_f1_macro"])
        tracking = {"status": "logged", "run_id": parent.info.run_id, "experiment_id": parent.info.experiment_id, "tracking_uri": uri}
        manifest["tracking"] = tracking
        (Path(run_dir) / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mlflow.log_artifacts(str(run_dir), artifact_path="experiment")
        return tracking


def log_hyperparameter_search(uri, experiment_name, manifest):
    """Experimento MLflow próprio para a otimização: um run pai por busca, um filho por combinação."""
    import mlflow

    search = manifest["hyperparameter_search"]
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment_name)
    tags = {"cohort": manifest["cohort"], "dataset_sha256": manifest["dataset_sha256"],
            "experiment_id": manifest["experiment_id"], "role": "hyperparameter_search",
            "physical_validation": "pending"}
    with mlflow.start_run(run_name=f"{search['method']}-search-{manifest['experiment_id']}", tags=tags) as parent:
        mlflow.log_params({"method": search["method"], "cv": search["cv"], "group_attr": search["group_attr"],
                           "selection_metric": search["selection_metric"], "seed": manifest["seed"]})
        for model, family in search["models"].items():
            if family.get("best_cv_f1_macro") is not None:
                mlflow.log_metric(f"{model}_best_cv_f1_macro", family["best_cv_f1_macro"])
                mlflow.log_dict(family["best_params"], f"best_params/{model}.json")
            for index, trial in enumerate(family["trials"]):
                with mlflow.start_run(run_name=f"{model}-{index:02d}", nested=True, tags={**tags, "model": model}):
                    mlflow.log_params({k: json.dumps(v) if isinstance(v, list) else v for k, v in trial["params"].items()})
                    for key in ("cv_f1_macro", "cv_f1_macro_std", "train_f1_macro", "generalization_gap"):
                        if trial.get(key) is not None:
                            mlflow.log_metric(key, trial[key])
        mlflow.log_dict(search, "hyperparameter_search.json")
        return {"status": "logged", "run_id": parent.info.run_id, "experiment_id": parent.info.experiment_id}
