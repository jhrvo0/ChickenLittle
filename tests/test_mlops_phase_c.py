"""Regressões da integração: publicação, novas sessões e proxy HTTP, sem serial."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ml.collection.synthetic import generate_synthetic_session
from ml.deployment import publish_experiment, resolve_deployment
from ml.inference_api import InferenceService, create_server
from ml.mqtt_ingestion import persist_session
from ml.prediction_worker import PredictionWorker
from terminal.web.server import MotionPetServer
from tests.test_mlops import experiment


def test_published_model_reload_is_explicit_and_fails_closed(experiment, tmp_path):
    root, run = experiment
    pointer = tmp_path / "deployment.json"
    service = InferenceService(experiments_root=root / "runs", deployment=pointer)
    assert service.status()["status"] == "pending"
    spec = publish_experiment(run, pointer, root / "runs")
    assert resolve_deployment(pointer, root / "runs")[0] == run / "models/best_model.joblib"
    assert service.status()["model_sha256"] == spec["model_sha256"]
    spec["model_relpath"] = "../../outside.joblib"
    pointer.write_text(json.dumps(spec))
    assert service.status()["status"] == "pending"
    assert service.status()["deployment_status"] == "invalid"
    publish_experiment(run, pointer, root / "runs")
    assert service.status()["status"] == "ready"


def test_corrupt_published_bundle_reports_invalid_instead_of_crashing(experiment, tmp_path):
    import shutil
    _, run = experiment
    destination = tmp_path / "runs/synthetic" / run.name
    shutil.copytree(run, destination)
    (destination / "models/best_model.joblib").write_bytes(b'')
    pointer = tmp_path / "deployment.json"
    publish_experiment(destination, pointer, tmp_path / "runs")
    service = InferenceService(experiments_root=tmp_path / "runs", deployment=pointer)
    assert service.status()["status"] == "pending" and service.status()["deployment_status"] == "invalid"


def test_new_sessions_are_processed_and_predictions_survive_restart(experiment, tmp_path):
    root, run = experiment
    service = InferenceService(run / "models/best_model.joblib", predictions=tmp_path / "predictions.json")
    worker = PredictionWorker(service, tmp_path / "raw", tmp_path / "predictions.json")
    worker.tick()
    assert service.predictions()["status"] == "pending"
    rows = generate_synthetic_session("new_simulated_participant", "new_session", 900)
    payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}
    persist_session(payload, tmp_path / "raw")
    worker.tick()
    result = service.predictions()
    assert len(result["items"]) == 1
    prediction = result["items"][0]
    assert prediction["input_origin"] == "demo" and prediction["trained_on"] == ["synthetic_simulator"]
    assert prediction["scope"] == "last_window_of_session" and prediction["physical_validation"] == "pending"
    persist_session(payload, tmp_path / "raw")
    restarted = PredictionWorker(service, tmp_path / "raw", tmp_path / "predictions.json")
    restarted.tick()
    assert service.predictions() == result
    invalid = tmp_path / "raw/demo/invalid.jsonl"
    invalid.write_text('{"broken":true}\n')
    restarted.tick()
    assert len(service.predictions()["items"]) == 1 and service.predictions()["errors"]


def test_automatic_inference_does_not_use_labels_to_select_window(experiment, tmp_path):
    from dataclasses import replace
    from ml.schemas import CORE_GESTURE_CLASSES
    _, run = experiment
    service = InferenceService(run / "models/best_model.joblib", predictions=tmp_path / "predictions.json")
    original = generate_synthetic_session("p", "uniform_labels", 1000)
    for sid, labelled in (("uniform_labels", False), ("mixed_labels", True)):
        rows = [replace(r, session_id=sid, label=CORE_GESTURE_CLASSES[i % 4] if labelled else "NEUTRAL") for i, r in enumerate(original)]
        persist_session({"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}, tmp_path / "raw")
    PredictionWorker(service, tmp_path / "raw", tmp_path / "predictions.json").tick()
    a, b = service.predictions()["items"]
    for key in ("label", "confidence", "probabilities", "windows", "window_end_ts_ms"):
        assert a[key] == b[key]


def test_dashboard_proxy_uses_api_and_preserves_unavailable_state(experiment, tmp_path, monkeypatch):
    root, run = experiment
    monkeypatch.chdir(tmp_path)
    service = InferenceService(run / "models/best_model.joblib", root / "runs")
    api = create_server(service, port=0)
    api_thread = Thread(target=api.serve_forever, daemon=True)
    api_thread.start()
    web = MotionPetServer(0, ml_api_url=f"http://127.0.0.1:{api.server_port}")
    thread = Thread(target=web.serve_forever, daemon=True)
    thread.start()
    def get(path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        return urlopen(Request(web.origin + path, body, {"X-MotionPet-Key": web.api_key, "Content-Type": "application/json"}), timeout=4)
    try:
        with get("/api/ml/status") as response:
            assert json.load(response)["model_sha256"] == service.model_sha256
        with get("/api/ml/evaluations") as response:
            evaluations = json.load(response)
            assert evaluations["real"]["metrics"] is None
            assert evaluations["synthetic"]["eda"] and evaluations["synthetic"]["tuning"]
        payload = {"schema_version": 1, "input_origin": "demo", "samples": [
            {"ts_ms": i * 75, "distance_cm": 15, "valid_ultrasonic": True, "ir_detected": False} for i in range(10)]}
        with get("/api/ml/infer", payload) as response:
            assert json.load(response) == service.infer(payload)
        with pytest.raises(HTTPError) as error:
            urlopen(web.origin + "/api/ml/status", timeout=4)
        assert error.value.code == 403
        api.shutdown()
        api.server_close()
        with pytest.raises(HTTPError) as error:
            get("/api/ml/status")
        assert error.value.code == 503
        assert json.load(error.value)["metrics"] is None
        with get("/api/live") as response:
            assert json.load(response)["frames"] == []
    finally:
        web.shutdown(); web.server_close(); thread.join()
        if api_thread.is_alive():
            api.shutdown(); api.server_close()
        api_thread.join()


def test_snapshot_imports_outside_checkout(experiment, tmp_path):
    _, run = experiment
    env = {**os.environ, "PYTHONPATH": str(run / "source")}
    code = "import ml.experiment, ml.inference_api; from ml.collection.synthetic import generate_synthetic_session; assert generate_synthetic_session('p','s',42)"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_missing_far_does_not_receive_selection_credit():
    from ml.training.trainer import compute_embedded_selection_score
    args = dict(val_f1_macro=0.5, val_event_f1=0.5, estimated_flash_bytes=1000, estimated_sram_bytes=1000)
    assert compute_embedded_selection_score(**args, val_neutral_far=None) < compute_embedded_selection_score(**args, val_neutral_far=0.0)


def test_academic_baseline_is_learned_and_preserves_existing_candidates():
    from ml.training.models import TrainingConfig, build_candidate_models
    models = build_candidate_models(TrainingConfig(include_learned_baseline=True))
    assert set(models) == {"decision_stump_baseline", "decision_tree", "random_forest", "mlp_compact", "rule_baseline"}
    stump = models["decision_stump_baseline"].fit([[0] * 11, [1] * 11, [2] * 11, [3] * 11] * 3, [0, 0, 1, 1] * 3)
    assert stump.get_depth() == 1 and len(stump.classes_) == 2


def test_markdown_does_not_report_missing_far_as_zero(tmp_path):
    from ml.evaluation.report import save_evaluation_markdown
    report = {"models": {"model": {"false_activation_rate_neutral": 0, "false_activation_rate_neutral_status": "pending_no_neutral_samples"}}}
    target = tmp_path / "report.md"
    save_evaluation_markdown(report, target)
    assert "não estimável (sem neutros)" in target.read_text(encoding="utf-8")


def test_api_exposes_nullable_far_without_breaking_legacy_field(experiment, tmp_path):
    import shutil
    from ml.inference_api import evaluation_summary
    _, run = experiment
    destination = tmp_path / "runs/synthetic" / run.name
    shutil.copytree(run, destination)
    (destination.parent / "latest.json").write_text(json.dumps({"experiment_id": run.name}))
    report = json.loads((destination / "evaluation.json").read_text(encoding="utf-8"))
    metrics = report["models"]["rule_baseline"]
    metrics.update(false_activation_rate_neutral_status="pending_no_neutral_samples", false_activation_rate_neutral=0, neutral_support=0)
    (destination / "evaluation.json").write_text(json.dumps(report), encoding="utf-8")
    result = evaluation_summary(tmp_path / "runs")["synthetic"]["metrics"]["rule_baseline"]
    assert result["far_neutral"] == {"status": "pending_no_neutral_samples", "value": None, "support": 0}
    assert result["false_activation_rate_neutral"] == 0
