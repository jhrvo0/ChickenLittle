"""Integração SOFTWARE com Mosquitto real/TLS/ACL. Só cria e remove recursos próprios.

Não abre serial, não envia firmware e não sobe a stack acadêmica. Requer imagem
Mosquitto já em cache, Docker Linux (WSL no Windows), Paho e OpenSSL do Git.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
IMAGE = "eclipse-mosquitto:2.0.22@sha256:81a6193ae693942a3231cd3ac52875b02b7e3a19da671b2fb4b55cc874c5b279"


def wait_for(condition, timeout=20):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            if condition():
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.15)
    raise RuntimeError("Timeout de integração; consulte os logs isolados.")


def run(output, firmware_sample=None):
    import paho.mqtt.client as mqtt
    from ml.iot_ingestion import IotStore
    from ml.inference_api import InferenceService, create_server
    from ml.prediction_worker import PredictionWorker
    from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, PreprocessingConfig
    from ml.training.models import RuleBaselineModel, TrainingConfig
    from ml.training.trainer import TrainedBundle, save_trained_bundle
    from terminal.web.server import MotionPetServer

    output = Path(output).resolve()
    work = output.parent / ("broker-" + uuid4().hex[:12])
    work.mkdir(parents=True)
    evidence = {"software_only": True, "physical_validation": "pending", "checks": [], "work_dir": str(work)}
    docker_prefix = ["wsl", "-d", "Ubuntu", "--", "docker"] if os.name == "nt" else ["docker"]
    def docker(*args, input=None):
        result = subprocess.run([*docker_prefix, *args], input=input, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError(f"Docker {args[0]} falhou: {result.stderr[-1500:]}")
        return result.stdout.strip()
    def check(name, **details):
        evidence["checks"].append({"name": name, "status": "passed", **details})
        print(name, flush=True)
    def count():
        if not db_path.exists():
            return 0
        with IotStore(db_path).connect() as db:
            return db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    clients, consumer, keeper, broker, servers = [], None, None, None, []
    consumer_log = None
    try:
        if os.name == "nt":
            keeper = subprocess.Popen(["wsl", "-d", "Ubuntu", "--", "sleep", "600"], creationflags=subprocess.CREATE_NO_WINDOW)
        docker("image", "inspect", IMAGE)
        openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(work / "server.key"),
                        "-out", str(work / "server.crt"), "-days", "1", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
        shutil.copyfile(work / "server.crt", work / "ca.crt")
        # Credenciais efêmeras de TESTE entram por stdin, nunca argv/log/repositório.
        password = uuid4().hex
        fixture = json.loads(Path(firmware_sample).read_text()) if firmware_sample else None
        device = fixture["device_id"] if fixture else "esp32_aabbccddeeff"
        (work / "passwords").write_text(f"{device}:{password}\nmotionlab_ingest:{password}\nmotionlab_simulator:{password}\n", encoding="utf-8")
        shutil.copyfile(ROOT / "ops/iot/mosquitto-lan.acl", work / "motionlab.acl")
        # Exercita a configuração LAN real; só adapta os caminhos ao volume isolado.
        config = (ROOT / "ops/iot/mosquitto-lan.conf").read_text(encoding="utf-8")
        config = config.replace("/mosquitto/local/", "/test/").replace("/mosquitto/config/motionlab.acl", "/test/motionlab.acl")
        (work / "mosquitto.conf").write_text(config, encoding="utf-8")
        linux_work = subprocess.check_output(["wsl", "-d", "Ubuntu", "--", "wslpath", "-a", "-u", str(work).replace("\\", "/")], text=True).strip() if os.name == "nt" else str(work)
        docker("run", "--rm", "--user", "0:0", "--network", "none", "-v", f"{linux_work}:/test", IMAGE,
               "mosquitto_passwd", "-U", "/test/passwords")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        broker = "motionlab-phase-e-" + uuid4().hex[:12]
        docker("run", "-d", "--rm", "--name", broker, "--memory", "64m", "--cpus", "0.5",
               "--user", "0:0", "-p", f"127.0.0.1:{port}:8883", "-v", f"{linux_work}:/test:ro", IMAGE,
               "mosquitto", "-c", "/test/mosquitto.conf")
        def connect(username, secret):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            event, result = threading.Event(), {}
            client.tls_set(ca_certs=str(work / "server.crt"))
            if username:
                client.username_pw_set(username, secret)
            def connected(_c, _u, _f, reason, _p):
                result["failure"] = reason.is_failure
                event.set()
            client.on_connect = connected
            client.connect("127.0.0.1", port)
            client.loop_start()
            clients.append(client)
            if not event.wait(10):
                raise RuntimeError("Sem CONNACK do broker TLS.")
            return client, result["failure"]
        wait_for(lambda: socket.create_connection(("127.0.0.1", port), timeout=1).close() is None)
        assert connect(None, None)[1]
        assert connect(device, "wrong-test-password")[1]
        check("tls_auth_rejects_anonymous_and_wrong_password")
        publisher, failed = connect(device, password)
        assert not failed
        check("tls_hostname_ca_and_authenticated_connection")

        db_path = work / "telemetry.sqlite3"
        ready = work / "consumer.ready"
        consumer_log = (work / "consumer.log").open("w", encoding="utf-8")
        env = {**os.environ, "MOTIONLAB_MQTT_USERNAME": "motionlab_ingest", "MOTIONLAB_MQTT_PASSWORD": password,
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
        args = [sys.executable, "-m", "ml.mqtt_ingestion", "consume", "--host", "127.0.0.1", "--port", str(port),
                "--mqtt-ca", str(work / "server.crt"), "--allow-devices", "--allow-real", "--data-root", str(work / "raw"),
                "--iot-db", str(db_path), "--ready-file", str(ready), "--client-id", broker + "-ingest"]
        consumer = subprocess.Popen(args, cwd=ROOT, env=env, stdout=consumer_log, stderr=subprocess.STDOUT)
        wait_for(ready.is_file)
        # Origem física declarada em payload de HOST continua pendente; nunca evidência da placa.
        base = fixture if fixture else {
            "schema_version": 1, "kind": "sample", "device_id": device, "session_id": "boot_software_integration",
            "sample_idx": 0, "ts_ms": 1000, "data_origin": "real_hardware", "distance_cm": 40,
            "valid_ultrasonic": True, "ir_detected": False, "valid_ir": True, "captured_at_iso": None,
            "clock_source": "monotonic_boot", "physical_validation": "pending", "dropped_total": 0}
        topic = f"motionlab/v1/devices/{device}/samples"
        def publish(payload, target=topic):
            info = publisher.publish(target, json.dumps(payload, separators=(",", ":")), qos=1)
            info.wait_for_publish(timeout=10)
            assert info.is_published()
        for idx in (0, 2, 1, *range(3, 20)):
            publish({**base, "sample_idx": idx, "ts_ms": 1000 + idx * 70})
        wait_for(lambda: count() == 20)
        check("mqtt_qos1_reordered_samples_persisted", firmware_serializer_fixture=bool(firmware_sample))
        publish({**base, "sample_idx": 1, "ts_ms": 1070})
        publish({**base, "sample_idx": 1, "ts_ms": 1070, "ir_detected": not base["ir_detected"]})
        publish({**base, "sample_idx": 20, "ts_ms": 2400, "distance_cm": 10**310})
        publish({**base, "sample_idx": 20, "ts_ms": 2400}, "motionlab/v1/devices/other/samples")
        # Mensagem autorizada posterior é barreira FIFO: verifica que as anteriores foram processadas.
        publish({**base, "sample_idx": 20, "ts_ms": 2400})
        wait_for(lambda: count() == 21)
        log = (work / "consumer.log").read_text()
        assert '"duplicate"' in log and '"rejected"' in log
        check("dedup_conflict_oversized_integer_rejection_and_acl_cross_device_denial")
        consumer.terminate()
        consumer.wait(timeout=10)
        ready.unlink(missing_ok=True)
        consumer = subprocess.Popen(args, cwd=ROOT, env=env, stdout=consumer_log, stderr=subprocess.STDOUT)
        wait_for(ready.is_file)
        publish({**base, "sample_idx": 20, "ts_ms": 2400})
        publish({**base, "sample_idx": 21, "ts_ms": 2470, "valid_ultrasonic": False, "distance_cm": -1})
        wait_for(lambda: count() == 22)
        check("consumer_restart_dedup_and_invalid_sensor_persistence")
        docker("restart", broker)
        wait_for(ready.is_file)
        wait_for(publisher.is_connected)
        publish({**base, "sample_idx": 22, "ts_ms": 2540})
        wait_for(lambda: count() == 23)
        check("broker_restart_reconnection_and_new_publication")

        from ml.collection.synthetic import generate_synthetic_session
        simulator, failed = connect("motionlab_simulator", password)
        assert not failed
        rows = generate_synthetic_session("host_simulated", "phase_e_legacy_session", 42)
        info = simulator.publish("motionlab/v1/sessions/demo", json.dumps({"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}), qos=1)
        info.wait_for_publish(timeout=10)
        wait_for(lambda: (work / "raw/demo/phase_e_legacy_session.jsonl").exists())
        check("phase_c_simulator_complete_session_compatibility")

        bundle = TrainedBundle("rule_baseline", RuleBaselineModel(), CORE_GESTURE_CLASSES, FEATURE_NAMES,
                               PreprocessingConfig(), TrainingConfig(), "none", (), ("synthetic_simulator",), "RULES_NO_TRAINING")
        model = save_trained_bundle(bundle, work / "model.joblib")
        service = InferenceService(model, experiments_root=work / "experiments", predictions=work / "predictions.json")
        PredictionWorker(service, None, work / "predictions.json", iot_db=db_path).tick()
        api = create_server(service, port=0)
        web = MotionPetServer(0, ml_api_url=f"http://127.0.0.1:{api.server_port}")
        for server in (api, web):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append((server, thread))
        request = Request(web.origin + "/api/ml/predictions", headers={"X-MotionPet-Key": web.api_key})
        with urlopen(request, timeout=5) as response:
            body = json.load(response)
        assert body["items"][0]["scope"] == "live_iot_unlabelled"
        assert body["physical_validation"] == "pending"
        assert not (work / "raw/real").exists() and not (work / "experiments").exists()
        check("mqtt_sqlite_inference_http_dashboard_proxy_no_training_or_holdout")
        evidence["status"] = "passed"
    except Exception as exc:
        evidence.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        for server, thread in reversed(servers):
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        if consumer and consumer.poll() is None:
            consumer.terminate()
            consumer.wait(timeout=10)
        if consumer_log:
            consumer_log.close()
        for client in clients:
            client.disconnect()
            client.loop_stop()
        if broker:
            try:
                (work / "broker.log").write_text(docker("logs", broker), encoding="utf-8")
                docker("rm", "-f", broker)  # Nome exclusivo desta execução; nunca compose down/prune.
            except RuntimeError:
                evidence["cleanup_broker"] = "inspect_required"
        if keeper:
            keeper.terminate()
            keeper.wait(timeout=10)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/experiments/phase-e/integration.json")
    parser.add_argument("--firmware-sample", help="Payload do serializador C++ real executado no host; não da placa.")
    parser.add_argument("--compile-firmware-host", action="store_true", help="Compila o bridge de testes C++ e usa bytes reais do serializador (requer pytest/compilador local).")
    args = parser.parse_args()
    if args.compile_firmware_host:
        import ctypes
        from tests.test_firmware_iot import iot_lib
        fixture = Path(args.output).resolve().parent / "firmware-sample.json"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        bridge = iot_lib.__wrapped__()
        try:
            lib = next(bridge)
            lib.iot_test_reset(1)
            assert lib.iot_test_push(1000, 40.0, 1, 0)
            buffer = ctypes.create_string_buffer(1024)
            assert lib.iot_test_peek(buffer, len(buffer))
            fixture.write_bytes(buffer.value + b"\n")
        finally:
            bridge.close()
        args.firmware_sample = str(fixture)
    run(args.output, args.firmware_sample)
