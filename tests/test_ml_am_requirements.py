"""Requisitos da disciplina de Aprendizado de Máquina: modelos, busca de hiperparâmetros,
diagnóstico de ajuste, MLflow e Compose único (docs/aprendizado_maquina.md)."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from sklearn.ensemble import AdaBoostClassifier

from ml.collection.synthetic import generate_synthetic_corpus
from ml.experiment import run_experiment
from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records
from ml.training.models import TrainingConfig, build_candidate_models
from ml.training.splitter import split_windows_grouped
from ml.training.trainer import select_best_embeddable_bundle, train_candidate_models
from ml.validation import SEARCH_SPACES, cross_validate_grouped, search_hyperparameters

ROOT = Path(__file__).resolve().parents[1]
FAST = TrainingConfig(rf_n_estimators=3, mlp_max_iter=80, ada_n_estimators=5, include_extended_candidates=True)


@pytest.fixture(scope="module")
def development(tmp_path_factory):
    root = tmp_path_factory.mktemp("am")
    generate_synthetic_corpus(root / "raw", n_participants=5, sessions_per_participant=1, write_csv=False)
    windows = preprocess_records(load_raw_records_from_path(root / "raw"))
    split = split_windows_grouped(windows, seed=42)
    return root, windows, split.train + split.val


def test_default_candidates_are_unchanged():
    assert set(build_candidate_models(TrainingConfig())) == {"rule_baseline", "decision_tree", "random_forest", "mlp_compact"}


def test_extended_candidates_add_knn_and_adaboost():
    models = build_candidate_models(FAST)
    assert {"knn", "adaboost"} <= set(models)
    assert models["knn"].named_steps["scaler"] is not None  # KNN exige padronização
    assert isinstance(models["adaboost"], AdaBoostClassifier)


def test_extended_models_are_compared_but_never_exported(development):
    _, windows, _ = development
    bundles, _ = train_candidate_models(windows, FAST)
    assert {"knn", "adaboost"} <= set(bundles)
    assert select_best_embeddable_bundle(bundles).model_name in ("decision_tree", "random_forest", "mlp_compact")


def test_cross_validation_reports_train_score_gap_and_diagnosis(development):
    _, _, dev = development
    cv = cross_validate_grouped(dev, FAST, group_attr="participant_id")
    for name, model in cv["models"].items():
        assert model["train_f1_macro_mean"] is not None, name
        assert model["generalization_gap"] == pytest.approx(model["train_f1_macro_mean"] - model["f1_macro_mean"])
        assert model["fit_diagnosis"] in ("overfitting", "underfitting", "balanced")
        assert all("train_f1_macro" in f for f in model["folds"] if f["status"] == "evaluated")


@pytest.mark.parametrize("method", ["grid", "random"])
def test_search_uses_development_groups_and_applies_best_params(development, method):
    _, _, dev = development
    cfg, result = search_hyperparameters(dev, FAST, "participant_id", method=method, n_iter=2,
                                         models=["decision_tree", "knn"])
    assert result["status"] == "evaluated" and result["scope"] == "development_only" and result["method"] == method
    tree = result["models"]["decision_tree"]
    expected = 2 if method == "random" else len(SEARCH_SPACES["decision_tree"]["dt_max_depth"]) * len(SEARCH_SPACES["decision_tree"]["dt_min_samples_leaf"])
    assert tree["evaluated_combinations"] == expected
    assert cfg.dt_max_depth == tree["best_params"]["dt_max_depth"]
    assert cfg.knn_n_neighbors == result["models"]["knn"]["best_params"]["knn_n_neighbors"]
    best = max(t["cv_f1_macro"] for t in tree["trials"] if t["cv_f1_macro"] is not None)
    assert tree["best_cv_f1_macro"] == best


def test_search_skips_extended_models_unless_enabled(development):
    _, _, dev = development
    _, result = search_hyperparameters(dev, replace(FAST, include_extended_candidates=False), "participant_id",
                                       method="random", n_iter=1, models=["decision_tree", "knn", "adaboost"])
    assert set(result["models"]) == {"decision_tree"}


def test_experiment_records_search_and_logs_separate_mlflow_experiment(development, tmp_path):
    mlflow = pytest.importorskip("mlflow")
    pytest.importorskip("matplotlib")
    root, _, _ = development
    uri = "sqlite:///" + (tmp_path / "tracking.db").as_posix()
    out = run_experiment(root / "raw", cohort="synthetic", output_root=tmp_path / "runs",
                         training_config=FAST, search="random", tracking_uri=uri)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["hyperparameter_search"]["status"] == "evaluated"
    assert manifest["tracking"]["hyperparameter_search"]["status"] == "logged"
    client = mlflow.MlflowClient(tracking_uri=uri)
    search = client.get_experiment_by_name("MotionLab-synthetic-hiperparametros")
    runs = client.search_runs([search.experiment_id])
    trials = sum(len(m["trials"]) for m in manifest["hyperparameter_search"]["models"].values())
    assert len(runs) == trials + 1  # um pai e um filho por combinação
    main = client.get_experiment_by_name("MotionLab-synthetic")
    names = {r.data.tags["mlflow.runName"] for r in client.search_runs([main.experiment_id])}
    assert {"knn", "adaboost"} <= names


def test_root_compose_runs_whole_stack_with_one_command():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "docker compose up --build" in text and "- ops/mlops/compose.yaml" in text
    stack = (ROOT / "ops/mlops/compose.yaml").read_text(encoding="utf-8")
    for service in ("mqtt:", "ingest:", "mlflow:", "airflow:", "api:", "dashboard:", "publisher:"):
        assert f"\n  {service}" in stack, service


def test_airflow_dag_runs_extended_comparison_and_search():
    dag = (ROOT / "ops/mlops/dags/motionlab_experiment.py").read_text(encoding="utf-8")
    assert 'search="grid"' in dag and "include_extended_candidates=True" in dag and "leave_one_out=True" in dag
