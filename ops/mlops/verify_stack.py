"""Verificação real HTTP/MQTT; --faults reinicia exclusivamente serviços deste Compose."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.collection.synthetic import generate_synthetic_session
from ml.experiment import dataset_digest
import paho.mqtt.client as mqtt


def wait_for(fn, timeout=180):
    deadline, last = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                return result
        except (OSError, ValueError, URLError) as exc:
            last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Condição não atingida em {timeout}s: {last}")


def verify(args):
    evidence = {"schema_version": 1, "software_only": True, "checks": [], "status": "running"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    def record(name, **data):
        evidence["checks"].append({"check": name, "status": "passed", **data})
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(evidence["checks"][-1], ensure_ascii=False), flush=True)

    def http(path, body=None, *, web=False):
        headers = {"Content-Type": "application/json"}
        if web:
            headers["X-MotionPet-Key"] = key
        request = Request((args.dashboard if web else args.api) + path,
                          json.dumps(body).encode() if body is not None else None, headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def compose(*command):
        result = subprocess.run(["wsl", "-d", "Ubuntu", "--", "docker", "compose", "-f", args.compose_file, *command], capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr[-2000:])
        return result.stdout

    receipts, ready = queue.Queue(), threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="motionlab-verify-" + uuid4().hex[:8])
    client.on_connect = lambda c, *_: c.subscribe("motionlab/v1/receipts/+", qos=1)
    client.on_subscribe = lambda *_: ready.set()
    client.on_message = lambda _c, _u, m: receipts.put(json.loads(m.payload))

    def publish(payload, *, topic="motionlab/v1/sessions/demo", receipt=True):
        info = client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish(10)
        assert info.is_published()
        if not receipt:
            return
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = receipts.get(timeout=max(0.1, deadline - time.monotonic()))
            if value["session_id"] == payload["records"][0]["session_id"]:
                return value
        raise RuntimeError("Persistência não confirmada.")

    try:
        state = wait_for(lambda: (s if s["status"] == "ready" else None) if (s := http("/v1/status")[1]) else None)
        assert state["trained_on"] == ["synthetic_simulator"]
        record("api_ready_after_airflow_publication", experiment_id=state["experiment_id"], model_sha256=state["model_sha256"])
        evaluations = http("/v1/evaluations")[1]
        assert evaluations["real"]["status"] == "pending" and evaluations["real"]["metrics"] is None
        assert evaluations["demo"]["status"] == "evaluated" and evaluations["demo"]["tracking"]["status"] == "logged"
        assert "decision_stump_baseline" in evaluations["demo"]["metrics"]
        record("evaluations_and_mlflow", models=list(evaluations["demo"]["metrics"]), run_id=evaluations["demo"]["tracking"]["run_id"], real="pending")
        orchestration = evaluations["demo"].get("orchestration")
        assert orchestration and orchestration["engine"] == "apache_airflow", "Experimento publicado não registra o DAG de origem."
        airflow_run = json.loads(compose("run", "--rm", "--no-deps", "--entrypoint", "python", "airflow", "/workspace/ops/mlops/inspect_airflow_run.py", orchestration["run_id"]))
        assert airflow_run["state"] == "success" and airflow_run["tasks"] == {name: "success" for name in ("configuration", "prepare", "experiment", "publish")}
        import mlflow
        tracking = mlflow.MlflowClient(tracking_uri=args.mlflow)
        parent = tracking.get_run(evaluations["demo"]["tracking"]["run_id"])
        assert parent.info.status == "FINISHED" and parent.data.tags["experiment_id"] == state["experiment_id"]
        children = tracking.search_runs([parent.info.experiment_id], filter_string="tags.mlflow.parentRunId = '" + parent.info.run_id + "'")
        # Um filho por modelo avaliado mais os três trials de profundidade da árvore (--tune).
        expected_models = len(evaluations["demo"]["metrics"])
        assert {"knn", "adaboost"} <= set(evaluations["demo"]["metrics"]), "KNN/AdaBoost ausentes da comparação."
        assert len(children) == expected_models + 3 and all(r.info.status == "FINISHED" for r in children)
        child_ids = {r.info.run_id for r in children}
        logged_models = [m for m in tracking.search_logged_models(experiment_ids=[parent.info.experiment_id]) if m.source_run_id in child_ids]
        assert len(logged_models) == expected_models
        search = tracking.get_experiment_by_name("MotionLab-demo-hiperparametros")
        assert search is not None and tracking.search_runs([search.experiment_id]), "Busca de hiperparâmetros não registrada no MLflow."
        record("hyperparameter_search_logged", experiment=search.experiment_id)
        record("identified_airflow_run_and_mlflow_children", airflow=airflow_run, finished_mlflow_children=len(children), saved_models=len(logged_models))
        with urlopen(args.dashboard + "/", timeout=5) as response:
            page = response.read().decode()
        key = re.search(r'name="motionpet-key" content="([^"]+)"', page).group(1)
        assert http("/api/ml/status", web=True)[1]["model_sha256"] == state["model_sha256"]
        assert http("/api/ml/evaluations", web=True)[1]["demo"]["experiment_id"] == state["experiment_id"]
        record("dashboard_backend_consumes_api", visual_integration="pending_claude")
        code, invalid = http("/v1/infer", {"schema_version": 1, "input_origin": "demo", "features": [float("nan")]})
        assert code == 400 and invalid["error"] == "invalid_request"
        record("invalid_http_input_rejected", http_status=code)
        client.connect(args.mqtt_host, args.mqtt_port)
        client.loop_start()
        assert ready.wait(10)
        raw_files = sorted((Path(args.data_root) / "raw/demo").glob("*.jsonl"))
        assert len(raw_files) >= 5
        rows = [json.loads(line) for line in raw_files[0].read_text(encoding="utf-8").splitlines() if line]
        infer_body = {"schema_version": 1, "input_origin": "demo", "samples": [
            {k: r[k] for k in ("ts_ms", "distance_cm", "valid_ultrasonic", "ir_detected")} for r in rows[:512]]}
        code, inferred = http("/v1/infer", infer_body)
        assert code == 200 and inferred["event_gate_applied"] is False and inferred["input_origin"] == "demo"
        proxy_code, proxied = http("/api/ml/infer", infer_body, web=True)
        assert proxy_code == 200 and inferred == proxied
        record("http_inference_and_dashboard_proxy_match", label=inferred["label"], input_origin=inferred["input_origin"], trained_on=inferred["trained_on"])
        payload = {"schema_version": 1, "cohort": "demo", "records": rows}
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw_files}
        receipt = publish(payload)
        assert receipt["status"] == "duplicate"
        assert hashlib.sha256(raw_files[0].read_bytes()).hexdigest() == before[raw_files[0].name]
        record("mqtt_duplicate_deduplicated", session_id=receipt["session_id"], dataset_sha256=receipt["dataset_sha256"])
        publish({"schema_version": 1, "cohort": "demo", "records": []}, receipt=False)
        wrong_rows = generate_synthetic_session("wrong_topic_participant", "wrong_topic_" + uuid4().hex[:8], 1001)
        wrong_payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in wrong_rows]}
        publish(wrong_payload, topic="motionlab/v1/sessions/synthetic", receipt=False)
        payload["records"][0]["distance_cm"] = 999.0
        publish(payload, receipt=False)
        time.sleep(2)
        assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(args.data_root) / "raw/demo").glob("*.jsonl")} == before
        assert not list((Path(args.data_root) / "raw").glob("*/" + wrong_rows[0].session_id + ".jsonl"))
        record("invalid_conflicting_and_wrong_topic_mqtt_do_not_change_corpus")
        new_rows = generate_synthetic_session("verify_new_participant", "verify_new_" + uuid4().hex[:8], 999)
        new_payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in new_rows]}
        receipt = publish(new_payload)
        assert receipt["status"] == "persisted" and receipt["dataset_sha256"] == dataset_digest(new_rows)
        def new_prediction():
            items = http("/api/ml/predictions", web=True)[1]["items"]
            return next((p for p in items if p["session_id"] == new_rows[0].session_id), None)
        prediction = wait_for(new_prediction, 30)
        assert prediction["dataset_sha256"] == receipt["dataset_sha256"] and prediction["input_origin"] == "demo"
        record("new_mqtt_session_automatically_reaches_dashboard_backend", session_id=prediction["session_id"], label=prediction["label"], model_sha256=prediction["model_sha256"])
        if args.faults:
            compose("restart", "ingest")
            wait_for(lambda: "(healthy)" in compose("ps", "ingest"), 30)
            receipt = publish(new_payload)
            assert receipt["status"] == "duplicate"
            record("consumer_restart_preserves_idempotency")
            compose("stop", "mqtt")
            compose("start", "mqtt")
            wait_for(lambda: "(healthy)" in compose("ps", "mqtt"), 30)
            wait_for(lambda: client.is_connected(), 30)
            receipt = publish(new_payload)
            assert receipt["status"] == "duplicate"
            record("broker_restart_reconnects_consumer")
            compose("stop", "api")
            assert http("/api/ml/status", web=True)[0] == 503
            assert http("/api/live", web=True)[0] == 200
            compose("start", "api")
            wait_for(lambda: http("/api/ml/status", web=True)[0] == 200, 30)
            restored = wait_for(new_prediction, 30)
            assert restored["model_sha256"] == prediction["model_sha256"]
            record("api_failure_and_restart_preserve_dashboard_and_predictions")
            compose("stop", "mlflow")
            assert http("/v1/status")[1]["status"] == "ready"
            compose("start", "mlflow")
            wait_for(lambda: "(healthy)" in compose("ps", "mlflow"), 60)
            record("mlflow_restart_does_not_interrupt_published_inference")
        evidence["status"] = "passed"
    except Exception as exc:
        evidence.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        client.disconnect(); client.loop_stop()
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8768")
    parser.add_argument("--dashboard", default="http://127.0.0.1:8767")
    parser.add_argument("--mlflow", default="http://127.0.0.1:5000")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--data-root", default="data/experiments/phase-c/stack")
    parser.add_argument("--compose-file", default="/mnt/y/src/ChickenLittle/ops/mlops/compose.yaml")
    parser.add_argument("--output", default="data/experiments/phase-c/integration.json")
    parser.add_argument("--faults", action="store_true")
    verify(parser.parse_args())
