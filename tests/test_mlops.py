"""Contratos de origem, isolamento de teste, publicação e API sem hardware."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from ml.collection.synthetic import generate_synthetic_corpus, generate_synthetic_session
from ml.experiment import dataset_digest, run_experiment, validate_corpus
from ml.inference_api import InferenceService, create_server, evaluation_summary
from ml.mqtt_ingestion import persist_session
from ml.provenance import preview_provenance
from ml.schemas import FEATURE_NAMES
from ml.training.models import TrainingConfig
from ml.training.trainer import load_trained_bundle
from terminal.motionlab.dataset import evaluate_real_sessions


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    pytest.importorskip("matplotlib")
    root = tmp_path_factory.mktemp("mlops")
    generate_synthetic_corpus(root / "raw", n_participants=5, sessions_per_participant=1, write_csv=False)
    out = run_experiment(root / "raw", cohort="synthetic", output_root=root / "runs", leave_one_out=True,
                         training_config=TrainingConfig(rf_n_estimators=3, mlp_max_iter=80))
    return root, out


def test_experiment_holdout_cv_eda_and_export_are_isolated(experiment):
    root, out = experiment
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["physical_validation"] == "pending"
    assert manifest["cohort"] == "synthetic" and manifest["software_only"] is True
    split = manifest["split"]
    test = set(split["test_groups"])
    development = set(split["train_groups"] + split["validation_groups"])
    assert not test & development
    assert len(list((out / "eda").glob("*.svg"))) == 5
    assert len(manifest["eda"]["figures"]) == 5
    assert all(f["interpretation"] for f in manifest["eda"]["figures"])
    assert (out / "export" / "tinyml_model.h").is_file()
    assert (out / "source/ml/experiment.py").is_file() and manifest["source_sha256"]
    from ml.preprocessing.windowing import load_raw_records_from_path
    assert dataset_digest(load_raw_records_from_path(out / "corpus.jsonl")) == manifest["dataset_sha256"]
    for validation in manifest["validation"].values():
        assert validation["scope"] == "development_only"
        for model in validation["models"].values():
            assert model["valid_folds"] == validation["n_splits"]
            for fold in model["folds"]:
                used = set(fold["train_groups"] + fold["validation_groups"])
                assert used <= development and not used & test
                assert not set(fold["train_groups"]) & set(fold["validation_groups"])
    summary = evaluation_summary(root / "runs")
    assert summary["real"]["status"] == "pending" and summary["real"]["metrics"] is None
    assert summary["synthetic"]["status"] == "evaluated"
    assert summary["demo"]["status"] == "pending"


def test_hash_origin_and_invalid_corpus_are_not_silently_accepted():
    rows = generate_synthetic_session("p", "s", 42)
    assert dataset_digest(rows) == dataset_digest(list(rows))
    assert dataset_digest(rows) != dataset_digest([replace(rows[0], distance_cm=3.0)] + rows[1:])
    with pytest.raises(ValueError, match="Origem incompatível"):
        validate_corpus(rows, "real")
    with pytest.raises(ValueError, match="misturada"):
        validate_corpus([replace(rows[0], data_origin="real_hardware")] + rows[1:], "synthetic")
    with pytest.raises(ValueError, match="Sessão inválida"):
        validate_corpus([rows[0]] * 12, "synthetic")


def test_failed_run_does_not_replace_latest(experiment, monkeypatch):
    root, _ = experiment
    latest = (root / "runs/synthetic/latest.json").read_text()
    def fail(*_args, **_kwargs):
        raise RuntimeError("Tracking unavailable")
    monkeypatch.setattr("ml.experiment.generate_eda", fail)
    with pytest.raises(RuntimeError, match="Tracking unavailable"):
        run_experiment(root / "raw", cohort="synthetic", output_root=root / "runs")
    assert (root / "runs/synthetic/latest.json").read_text() == latest
    failed = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "runs/synthetic").glob("*/manifest.json")]
    assert any(r["status"] == "failed" for r in failed)


def test_mqtt_persistence_is_idempotent_and_preserves_origin(tmp_path):
    rows = generate_synthetic_session("p", "session_test", 42)
    payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}
    assert persist_session(payload, tmp_path)["status"] == "persisted"
    assert persist_session(payload, tmp_path)["status"] == "duplicate"
    assert (tmp_path / "demo/session_test.jsonl").is_file()
    assert not (tmp_path / "real").exists()
    payload["records"][0]["distance_cm"] = 11.0
    with pytest.raises(ValueError, match="Conflito"):
        persist_session(payload, tmp_path)
    payload["cohort"] = "real"
    with pytest.raises(ValueError, match="real"):
        persist_session(payload, tmp_path)
    with pytest.raises(ValueError, match="Origem incompatível"):
        persist_session(payload, tmp_path, allow_real=True)


@pytest.mark.parametrize("mutation", ["missing_origin", "traversal", "nan", "mixed_session", "bad_indices"])
def test_mqtt_rejects_unsafe_sessions(tmp_path, mutation):
    records = [r.to_dict() for r in generate_synthetic_session("p", "safe", 42)]
    if mutation == "missing_origin":
        records[0].pop("data_origin")
    elif mutation == "traversal":
        for r in records:
            r["session_id"] = "../outside"
    elif mutation == "nan":
        records[0]["distance_cm"] = float("nan")
    elif mutation == "bad_indices":
        records[0]["sample_idx"] = -1
    else:
        records[0]["session_id"] = "other"
    with pytest.raises((ValueError, TypeError)):
        persist_session({"schema_version": 1, "cohort": "demo", "records": records}, tmp_path)
    assert not list(tmp_path.rglob("*.jsonl"))


def test_inference_http_matches_local_model_and_exposes_provenance(experiment):
    root, out = experiment
    service = InferenceService(out / "models/best_model.joblib", root / "runs")
    server = create_server(service, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        samples = [{"ts_ms": i * 75, "distance_cm": 15.0, "valid_ultrasonic": True, "ir_detected": False} for i in range(10)]
        payload = {"schema_version": 1, "input_origin": "demo", "samples": samples}
        request = Request(base + "/v1/infer", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.load(response)
        assert result == service.infer(payload)
        assert result["trained_on"] == ["synthetic_simulator"] and result["input_origin"] == "demo"
        assert result["event_gate_applied"] is False and result["model_sha256"]
        with urlopen(base + "/v1/evaluations") as response:
            assert json.load(response)["real"]["status"] == "pending"
        preflight = Request(base + "/v1/infer", method="OPTIONS", headers={"Origin": "http://127.0.0.1:8767"})
        with urlopen(preflight) as response:
            assert response.status == 204 and response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:8767"
        payload["samples"][1]["ts_ms"] = 0
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/v1/infer", json.dumps(payload).encode()))
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "5"])
def test_api_validates_feature_values(experiment, value):
    _, out = experiment
    service = InferenceService(out / "models/best_model.joblib")
    features = [0.0] * len(FEATURE_NAMES)
    features[0] = value
    with pytest.raises(ValueError, match="finitos"):
        service.infer({"schema_version": 1, "input_origin": "synthetic", "features": features, "feature_names": list(FEATURE_NAMES)})


def test_pending_model_does_not_return_dummy_predictions():
    service = InferenceService()
    assert service.status()["status"] == "pending"
    with pytest.raises(RuntimeError, match="Modelo pendente"):
        service.infer({"schema_version": 1, "input_origin": "real", "features": []})


def test_preview_marks_old_models_and_development_overlap(experiment):
    root, out = experiment
    from ml.preprocessing.windowing import load_raw_records_from_path
    rows = load_raw_records_from_path(root / "raw")
    bundle = load_trained_bundle(out / "models/best_model.joblib")
    assert preview_provenance(bundle, rows)["independence"] == "overlaps_development"
    bundle.development_sessions = ()
    assert preview_provenance(bundle, rows)["independence"] == "independence_unknown"


def test_ui_blocks_contaminated_real_folder(tmp_path):
    folder = tmp_path / "real"
    folder.mkdir()
    rows = generate_synthetic_session("p", "s", 42)
    (folder / "s.jsonl").write_text("\n".join(json.dumps(r.to_dict()) for r in rows), encoding="utf-8")
    assert evaluate_real_sessions({}, tmp_path)["status"] == "invalid_data"


def test_report_origin_mismatch_is_not_displayed_as_real(experiment):
    root, out = experiment
    import shutil
    destination = root / "tampered/real" / out.name
    shutil.copytree(out, destination)
    (destination.parent / "latest.json").write_text(json.dumps({"experiment_id": out.name}))
    assert evaluation_summary(root / "tampered")["real"]["status"] == "invalid"


def test_mlflow_logs_parent_candidates_metrics_and_models(experiment, tmp_path):
    mlflow = pytest.importorskip("mlflow")
    pytest.importorskip("pandas")
    pytest.importorskip("sqlalchemy")
    from ml.tracking import log_experiment
    _, out = experiment
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    bundles = {p.stem: load_trained_bundle(p) for p in (out / "models").glob("*.joblib") if p.stem != "best_model"}
    uri = "sqlite:///" + (tmp_path / "tracking.db").as_posix()
    result = log_experiment(uri, "test-motionlab", out, manifest, bundles, report)
    assert result["status"] == "logged"
    client = mlflow.MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name("test-motionlab")
    runs = client.search_runs([exp.experiment_id])
    assert len(runs) == 5
    children = [r for r in runs if "mlflow.parentRunId" in r.data.tags]
    assert len(children) == 4 and all("test_f1_macro" in r.data.metrics for r in children)
    assert all(r.data.tags["cohort"] == "synthetic" for r in runs)
    models = client.search_logged_models(experiment_ids=[exp.experiment_id])
    assert len(models) == 4
    children_by_id = {r.info.run_id: r for r in children}
    for model in models:
        name = children_by_id[model.source_run_id].data.tags["mlflow.runName"]
        restored = mlflow.sklearn.load_model(f"models:/{model.model_id}")
        X = np.zeros((2, len(FEATURE_NAMES)))
        np.testing.assert_array_equal(restored.predict(X), bundles[name].estimator.predict(X))


def test_macro_f1_keeps_absent_classes_and_far_reports_missing_neutral():
    from ml.evaluation.metrics import evaluate_classification_metrics
    from ml.training.models import RuleBaselineModel
    X = np.zeros((3, len(FEATURE_NAMES)))
    X[:, 2] = 15.0
    model = RuleBaselineModel()
    y = model.predict(X)
    # Apenas uma classe prevista/presente: macro deve dividir pelas quatro classes do contrato.
    result = evaluate_classification_metrics(model, X, y)
    assert result["f1_macro"] == 0.25
    if y[0] != 0:
        assert result["false_activation_rate_neutral_status"] == "pending_no_neutral_samples"


def test_tree_tuning_uses_only_grouped_development(experiment):
    root, out = experiment
    from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records
    from ml.training.splitter import split_windows_grouped
    from ml.validation import tune_tree_depth
    split = split_windows_grouped(preprocess_records(load_raw_records_from_path(root / "raw")))
    cfg, tuning = tune_tree_depth(split.train + split.val, TrainingConfig(), "participant_id")
    assert tuning["status"] == "selected_on_development_cv"
    assert cfg.dt_max_depth in (3, 5, 7) and len(tuning["trials"]) == 3
    for trial in tuning["trials"]:
        for fold in trial["cv"]["models"]["decision_tree"]["folds"]:
            assert not set(split.test_groups) & set(fold["train_groups"] + fold["validation_groups"])
