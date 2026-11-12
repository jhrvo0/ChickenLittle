"""Host: contrato ESP32, persistência durável, falhas e integração API sem placa."""
import json
import sqlite3
from threading import Thread
from types import SimpleNamespace
from urllib.request import urlopen

import pytest

from ml.iot_ingestion import DEVICE_TOPIC, IotStore, validate_sample

DEVICE = "esp32_aabbccddeeff"
TOPIC = DEVICE_TOPIC + DEVICE + "/samples"


def sample(idx=0, **changes):
    return {"schema_version": 1, "kind": "sample", "device_id": DEVICE, "session_id": "boot_0123456789abcdef",
            "sample_idx": idx, "ts_ms": idx * 70 + 1000, "data_origin": "synthetic_simulator",
            "distance_cm": 40.0 - idx % 30, "valid_ultrasonic": True, "ir_detected": False, "valid_ir": True,
            "captured_at_iso": None, "clock_source": "monotonic_boot", "physical_validation": "pending",
            "dropped_total": 0, **changes}


def test_reordering_dedup_restart_conflict_and_isolation(tmp_path):
    path = tmp_path / "iot/telemetry.sqlite3"
    store = IotStore(path)
    for idx in (2, 0, 1):
        assert store.persist(TOPIC, sample(idx))["status"] == "persisted"
    store = IotStore(path)
    assert store.persist(TOPIC, sample(1))["status"] == "duplicate"
    assert [r["sample_idx"] for r in next(store.latest_windows())] == [0, 1, 2]
    with pytest.raises(ValueError, match="Conflito"):
        store.persist(TOPIC, sample(1, ir_detected=True))
    assert not (tmp_path / "raw").exists()
    with store.connect() as db:
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 3


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"kind": "status"}, {"device_id": "../attack"},
    {"session_id": "a/b"}, {"sample_idx": True}, {"sample_idx": -1}, {"sample_idx": 2**63},
    {"ts_ms": -2}, {"dropped_total": 1.5}, {"distance_cm": float("nan")},
    {"distance_cm": float("inf")}, {"distance_cm": 10**310}, {"distance_cm": True}, {"distance_cm": None},
    {"distance_cm": -1}, {"distance_cm": 401}, {"valid_ultrasonic": 1}, {"ir_detected": "false"}, {"valid_ir": 1},
    {"valid_ultrasonic": False, "distance_cm": 20}, {"data_origin": "untrusted"},
    {"data_origin": {}}, {"captured_at_iso": "1970-01-01T00:00:00Z"},
    {"clock_source": "utc"}, {"physical_validation": "validated"},
])
def test_strict_invalid_payloads(change):
    with pytest.raises(ValueError):
        validate_sample(TOPIC, sample(**change))


def test_physical_claim_requires_opt_in_but_never_attests_validation(tmp_path):
    store = IotStore(tmp_path / "telemetry.sqlite3")
    claimed = sample(data_origin="real_hardware")
    with pytest.raises(ValueError, match="allow-real"):
        store.persist(TOPIC, claimed)
    receipt = store.persist(TOPIC, claimed, allow_physical=True)
    assert receipt["physical_validation"] == "pending"
    with pytest.raises(ValueError, match="Origem alterada"):
        store.persist(TOPIC, sample(1))
    assert not any(tmp_path.glob("*.jsonl"))


def test_invalid_reading_same_usb_sentinel_and_topic():
    assert validate_sample(TOPIC, sample(distance_cm=-1, valid_ultrasonic=False))["distance_cm"] == -1
    with pytest.raises(ValueError, match="tópico"):
        validate_sample(DEVICE_TOPIC + "other/samples", sample())
    with pytest.raises(ValueError, match="incompleta"):
        validate_sample(TOPIC, {})


def test_temporal_consistency_gaps_and_bounded_windows(tmp_path):
    store = IotStore(tmp_path / "telemetry.sqlite3")
    for idx in (0, 1, 4, 5):
        store.persist(TOPIC, sample(idx))
    assert [r["sample_idx"] for r in next(store.latest_windows())] == [4, 5]
    with pytest.raises(ValueError, match="temporal"):
        store.persist(TOPIC, sample(3, ts_ms=sample(5)["ts_ms"]))
    with pytest.raises(ValueError, match="temporal"):
        store.persist(TOPIC, sample(3, dropped_total=3))
    for limit in (1, 513):
        with pytest.raises(ValueError, match="limitada"):
            list(store.latest_windows(limit=limit))
    for idx in range(6, 530):
        store.persist(TOPIC, sample(idx))
    tail = next(store.latest_windows())
    assert len(tail) == 512 and tail[-1]["sample_idx"] == 529


def test_two_store_instances_serialize_conflicting_writes(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / "telemetry.sqlite3"
    stores = IotStore(path), IotStore(path)
    def write(n):
        try:
            return stores[n].persist(TOPIC, sample(distance_cm=20 + n))["status"]
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(write, (0, 1))) == ["conflict", "persisted"]


@pytest.fixture
def service(tmp_path):
    from ml.inference_api import InferenceService
    from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, PreprocessingConfig
    from ml.training.models import RuleBaselineModel, TrainingConfig
    from ml.training.trainer import TrainedBundle, save_trained_bundle
    bundle = TrainedBundle("rule_baseline", RuleBaselineModel(), CORE_GESTURE_CLASSES, FEATURE_NAMES,
                           PreprocessingConfig(), TrainingConfig(), "none", (), ("synthetic_simulator",), "RULES_NO_TRAINING")
    path = save_trained_bundle(bundle, tmp_path / "model.joblib")
    return InferenceService(path, experiments_root=tmp_path / "experiments", predictions=tmp_path / "predictions.json")


def test_iot_to_predictions_api_and_dashboard_proxy_without_training(service, tmp_path):
    from ml.inference_api import create_server, evaluation_summary
    from ml.prediction_worker import PredictionWorker
    from terminal.web.ml_client import MlApiClient
    store = IotStore(tmp_path / "telemetry.sqlite3")
    for idx in range(20):
        store.persist(TOPIC, sample(idx))
    worker = PredictionWorker(service, None, tmp_path / "predictions.json", iot_db=store.path)
    worker.tick()
    item = service.predictions()["items"][0]
    direct = service.infer({"schema_version": 1, "input_origin": "synthetic", "samples": [sample(i) for i in range(20)]})
    assert item["probabilities"] == direct["probabilities"]
    assert item["scope"] == "live_iot_unlabelled" and item["device_id"] == DEVICE
    assert item["physical_validation"] == "pending" and "label" not in next(store.latest_windows())[0]
    assert all(v["status"] == "pending" for k, v in evaluation_summary(tmp_path / "experiments").items() if k in ("real", "demo", "synthetic"))
    api = create_server(service, port=0)
    thread = Thread(target=api.serve_forever, daemon=True)
    thread.start()
    try:
        code, response = MlApiClient(f"http://127.0.0.1:{api.server_port}").request("predictions")
        assert code == 200 and response["items"][0]["dataset_sha256"] == item["dataset_sha256"]
    finally:
        api.shutdown()
        api.server_close()
        thread.join()


def test_consumer_ack_after_commit_and_disk_failure_without_ack(monkeypatch, tmp_path):
    import paho.mqtt.client as mqtt
    from ml.mqtt_ingestion import consume
    clients = []
    failure = False
    class FakeClient:
        def __init__(self, *_args, **kwargs):
            assert kwargs["manual_ack"] is True
            self.acks = []
            clients.append(self)
        def reconnect_delay_set(self, **kwargs):
            assert kwargs == {"min_delay": 1, "max_delay": 60}
        def max_inflight_messages_set(self, n): pass
        def max_queued_messages_set(self, n): pass
        def connect_async(self, *_args): pass
        def subscribe(self, topics):
            assert (DEVICE_TOPIC + "+/samples", 1) in topics
            return mqtt.MQTT_ERR_SUCCESS, 7
        def loop_forever(self, **kwargs):
            assert kwargs["retry_first_connection"]
            self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)
            self.on_subscribe(self, None, 7, [SimpleNamespace(is_failure=False)], None)
            for idx, payload in enumerate((sample(), sample(), sample(1), sample(2, distance_cm=10**310))):
                assert len(json.dumps(payload).encode()) <= 1024
                if idx == 2 and failure:
                    monkeypatch.setattr(IotStore, "persist", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("disk full")))
                self.on_message(self, None, SimpleNamespace(topic=TOPIC, payload=json.dumps(payload).encode(), qos=1, mid=idx, retain=False))
        def ack(self, mid, qos):
            # Banco já está visível a outra conexão antes de cada ACK.
            with sqlite3.connect(tmp_path / "iot.sqlite3") as db:
                assert db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] >= 1
            self.acks.append(mid)
        def disconnect(self): pass
    monkeypatch.setattr(mqtt, "Client", FakeClient)
    monkeypatch.delenv("MOTIONLAB_MQTT_USERNAME", raising=False)
    monkeypatch.delenv("MOTIONLAB_MQTT_PASSWORD", raising=False)
    consume("localhost", 1883, tmp_path / "raw", allow_devices=True, iot_db=tmp_path / "iot.sqlite3")
    assert clients[-1].acks == [0, 1, 2, 3]
    failure = True
    with pytest.raises(sqlite3.OperationalError, match="disk full"):
        consume("localhost", 1883, tmp_path / "raw", allow_devices=True, iot_db=tmp_path / "iot.sqlite3")
    assert clients[-1].acks == [0, 1]


def test_ir_disabled_prevents_inference_until_valid_window_recovers(service, tmp_path):
    from ml.iot_ingestion import predict_iot_windows
    store = IotStore(tmp_path / "iot.sqlite3")
    for idx in range(20):
        store.persist(TOPIC, sample(idx, valid_ir=idx != 15))
    assert predict_iot_windows(store, service) == []
    for idx in range(20, 26):
        store.persist(TOPIC, sample(idx))
    assert predict_iot_windows(store, service)[0]["window_end_ts_ms"] == sample(25)["ts_ms"]


def test_latest_odd_window_features_align_with_reported_timestamp(service, tmp_path):
    from ml.iot_ingestion import predict_iot_windows
    from ml.preprocessing import CausalSignalFilter, extract_window_features
    from ml.schemas import FEATURE_NAMES
    store = IotStore(tmp_path / "iot.sqlite3")
    for idx in range(21):
        store.persist(TOPIC, sample(idx))
    cfg = service.bundle.preprocessing_config
    signal_filter = CausalSignalFilter(cfg)
    filtered = [signal_filter.step(sample(i)["distance_cm"], True) for i in range(21)]
    features = extract_window_features([d for d, inv in filtered[-10:]], [sample(i)["ts_ms"] for i in range(11, 21)], [False]*10, [False]*10)
    expected = service.infer({"schema_version": 1, "input_origin": "synthetic", "feature_names": list(FEATURE_NAMES), "features": list(features)})
    result = predict_iot_windows(store, service)[0]
    assert result["probabilities"] == expected["probabilities"]
    assert result["window_end_ts_ms"] == sample(20)["ts_ms"]


def test_corrupt_iot_database_does_not_block_existing_raw_worker(service, tmp_path):
    from ml.prediction_worker import PredictionWorker
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"not a database")
    PredictionWorker(service, None, tmp_path / "predictions.json", iot_db=path).tick()
    assert service.predictions()["errors"][0]["error"] == "DatabaseError"


def test_mqtt_credentials_require_pair_and_enable_tls(monkeypatch):
    from unittest.mock import Mock
    from ml.mqtt_ingestion import configure_client
    monkeypatch.setenv("MOTIONLAB_MQTT_USERNAME", "test_user")
    monkeypatch.delenv("MOTIONLAB_MQTT_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="juntos"):
        configure_client(Mock())
    monkeypatch.setenv("MOTIONLAB_MQTT_PASSWORD", "ephemeral-test-only")
    client = Mock()
    configure_client(client, ca_file="test-ca.crt")
    client.tls_set.assert_called_once_with(ca_certs="test-ca.crt")
    client.username_pw_set.assert_called_once_with("test_user", "ephemeral-test-only")


def test_secure_broker_template_preserves_phase_c():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    conf = (root / "ops/iot/mosquitto-lan.conf").read_text()
    assert "allow_anonymous false" in conf and "listener 8883" in conf
    assert all(key in conf for key in ("password_file", "acl_file", "certfile", "keyfile", "memory_limit"))
    acl = (root / "ops/iot/mosquitto-lan.acl").read_text()
    assert "pattern write motionlab/v1/devices/%u/samples" in acl
    assert "127.0.0.1:1883:1883" in (root / "ops/mlops/compose.yaml").read_text()
