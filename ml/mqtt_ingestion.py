"""Sessões MQTT completas com persistência idempotente e origem obrigatória."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import threading

from ml.experiment import dataset_digest, validate_corpus
from ml.schemas import RawSampleRecord

TOPIC_PREFIX = "motionlab/v1/sessions/"
_LOCK = threading.Lock()


def persist_session(payload, data_root="data/raw", *, allow_real=False):
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1:
        raise ValueError("Envelope MQTT exige schema_version=1.")
    cohort = payload.get("cohort")
    if cohort not in ("real", "demo", "synthetic") or (cohort == "real" and not allow_real):
        raise ValueError("Origem inválida ou ingestão real não habilitada explicitamente.")
    raw = payload.get("records")
    if not isinstance(raw, list) or not 10 <= len(raw) <= 10000:
        raise ValueError("Sessão completa deve conter 10 a 10000 registros.")
    required = {"participant_id", "session_id", "sample_idx", "ts_ms", "label", "distance_cm",
                "valid_ultrasonic", "ir_detected", "data_origin", "captured_at_iso"}
    rows = []
    for record in raw:
        if not isinstance(record, dict) or not required <= record.keys():
            raise ValueError("Registro incompleto; proveniência não pode ser inferida.")
        if not isinstance(record["valid_ultrasonic"], bool) or not isinstance(record["ir_detected"], bool):
            raise ValueError("Flags devem ser booleanos JSON.")
        if any(isinstance(record[k], bool) or not isinstance(record[k], int) or record[k] < 0 for k in ("sample_idx", "ts_ms")):
            raise ValueError("Índices e timestamps devem ser inteiros não negativos.")
        rows.append(RawSampleRecord.from_dict(record))
    ids = {r.session_id for r in rows}
    if len(ids) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", rows[0].session_id):
        raise ValueError("Envelope exige uma sessão com identificador seguro.")
    if [r.sample_idx for r in rows] != list(range(len(rows))):
        raise ValueError("sample_idx deve ser contíguo a partir de zero.")
    validate_corpus(rows, cohort)
    fingerprint = dataset_digest(rows)  # Também rejeita NaN/Infinity.
    folder = Path(data_root) / ("real" if cohort == "real" else "demo" if cohort == "demo" else "synthetic")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{rows[0].session_id}.jsonl"
    with _LOCK:
        if target.exists():
            existing = [RawSampleRecord.from_dict(json.loads(line)) for line in target.read_text(encoding="utf-8").splitlines() if line]
            if dataset_digest(existing) != fingerprint:
                raise ValueError("Conflito: session_id já existe com conteúdo diferente.")
            return {"status": "duplicate", "cohort": cohort, "dataset_sha256": fingerprint}
        # Nome temporário não entra no loader, que só lê CSV/JSONL completos.
        from uuid import uuid4
        temporary = folder / f".{target.stem}-{uuid4().hex}.tmp"
        try:
            temporary.write_text("".join(json.dumps(asdict(r), allow_nan=False) + "\n" for r in rows), encoding="utf-8")
            # hard link publica sem substituir uma sessão de outro processo.
            import os
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = [RawSampleRecord.from_dict(json.loads(line)) for line in target.read_text(encoding="utf-8").splitlines() if line]
                if dataset_digest(existing) != fingerprint:
                    raise ValueError("Conflito concorrente de session_id.")
                return {"status": "duplicate", "cohort": cohort, "dataset_sha256": fingerprint}
        finally:
            temporary.unlink(missing_ok=True)
    return {"status": "persisted", "cohort": cohort, "samples": len(rows), "dataset_sha256": fingerprint}


def configure_client(client, *, ca_file=None):
    """Segredos somente no ambiente do processo; nenhuma senha em argv/logs."""
    username = os.environ.get("MOTIONLAB_MQTT_USERNAME")
    password = os.environ.get("MOTIONLAB_MQTT_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError("Configure usuário e senha MQTT juntos no ambiente.")
    if username:
        client.username_pw_set(username, password)
    if ca_file:
        client.tls_set(ca_certs=ca_file)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.max_inflight_messages_set(8)
    client.max_queued_messages_set(32)


def consume(host, port, data_root, *, allow_real=False, ready_file=None,
            allow_devices=False, iot_db=None, ca_file=None, client_id="motionlab-ingest-v1"):
    import paho.mqtt.client as mqtt
    from ml.iot_ingestion import DEVICE_TOPIC, MAX_PACKET_BYTES, IotStore
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=False, manual_ack=True)
    configure_client(client, ca_file=ca_file)
    store = IotStore(iot_db or Path(data_root).parent / "iot" / "telemetry.sqlite3") if allow_devices else None
    subscriptions = set()
    ready = Path(ready_file) if ready_file else None
    if ready:
        ready.unlink(missing_ok=True)

    def connected(client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            print(json.dumps({"status": "connection_rejected"}), flush=True)
            return
        subscriptions.clear()
        topics = [TOPIC_PREFIX + c for c in ("demo", "synthetic") + (("real",) if allow_real else ())]
        if allow_devices:
            topics.append(DEVICE_TOPIC + "+/samples")
        # Um SUBACK representa todas as inscrições; ready só após todas serem aceitas.
        result, mid = client.subscribe([(topic, 1) for topic in topics])
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("Falha ao solicitar inscrições MQTT.")
        subscriptions.add(mid)
        print(json.dumps({"status": "connected", "subscriptions_requested": True, "real_enabled": allow_real}), flush=True)

    def subscribed(_client, _userdata, _mid, reasons, _properties):
        subscriptions.discard(_mid)
        failed = any(r.is_failure for r in reasons)
        if ready and not failed and not subscriptions:
            ready.parent.mkdir(parents=True, exist_ok=True)
            ready.write_text("subscribed\n", encoding="utf-8")
        print(json.dumps({"status": "subscribed" if not failed else "subscription_rejected"}), flush=True)

    def disconnected(_client, _userdata, _flags, _reason, _properties):
        if ready:
            ready.unlink(missing_ok=True)

    def message(client, _userdata, msg):
        try:
            if len(msg.payload) > 4 * 1024 * 1024:
                raise ValueError("Mensagem maior que 4 MiB.")
            payload = json.loads(msg.payload)
            if msg.topic.startswith(DEVICE_TOPIC):
                if store is None or len(msg.payload) > MAX_PACKET_BYTES or msg.qos != 1 or msg.retain:
                    raise ValueError("Telemetria IoT exige habilitação, QoS 1, até 1024 bytes e retain=false.")
                receipt = store.persist(msg.topic, payload, allow_physical=allow_real)
                print(json.dumps(receipt), flush=True)
                # Confirmação ao broker ocorre somente depois do COMMIT SQLite FULL.
                client.ack(msg.mid, msg.qos)
                return
            if not isinstance(payload, dict) or msg.topic != TOPIC_PREFIX + str(payload.get("cohort")):
                raise ValueError("Tópico e origem divergentes.")
            receipt = {**persist_session(payload, data_root, allow_real=allow_real),
                       "session_id": payload["records"][0]["session_id"]}
            print(json.dumps(receipt), flush=True)
            client.publish("motionlab/v1/receipts/" + receipt["session_id"], json.dumps(receipt), qos=1)
        except (ValueError, KeyError, TypeError) as exc:
            print(json.dumps({"status": "rejected", "message": str(exc)}), flush=True)
        # Erros de disco escapam sem ACK. Mensagens inválidas são rejeitadas, sem retry infinito.
        client.ack(msg.mid, msg.qos)

    client.on_connect = connected
    client.on_subscribe = subscribed
    client.on_message = message
    client.on_disconnect = disconnected
    try:
        client.connect_async(host, port)
        client.loop_forever(retry_first_connection=True)
    finally:
        client.disconnect()
        if ready:
            ready.unlink(missing_ok=True)


def publish_demo(host, port, seed=42, *, ca_file=None):
    import paho.mqtt.client as mqtt
    from ml.collection.synthetic import generate_synthetic_session

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    configure_client(client, ca_file=ca_file)
    subscribed = threading.Event()
    confirmed = threading.Event()
    expected = {}

    def connected(client, *_args):
        client.subscribe("motionlab/v1/receipts/+", qos=1)

    def received(_client, _userdata, msg):
        receipt = json.loads(msg.payload)
        if (receipt.get("session_id") == expected.get("session_id") and
                receipt.get("dataset_sha256") == expected.get("dataset_sha256") and
                receipt.get("status") in ("persisted", "duplicate")):
            confirmed.set()

    client.on_connect = connected
    client.on_subscribe = lambda *_args: subscribed.set()
    client.on_message = received
    client.connect(host, port)
    client.loop_start()
    try:
        if not subscribed.wait(15):
            raise RuntimeError("Timeout ao assinar confirmações de persistência.")
        from uuid import uuid4
        batch = uuid4().hex[:8]
        for index in range(1, 6):
            rows = generate_synthetic_session(f"demo_p{index:02d}", f"mqtt_demo_p{index:02d}_{seed}_{batch}", seed + index)
            payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}
            expected.update(session_id=rows[0].session_id, dataset_sha256=dataset_digest(rows))
            confirmed.clear()
            info = client.publish(TOPIC_PREFIX + "demo", json.dumps(payload), qos=1, retain=False)
            info.wait_for_publish(timeout=15)
            if not info.is_published():
                raise RuntimeError("Timeout ao publicar sessão demo.")
            if not confirmed.wait(30):
                raise RuntimeError("Broker recebeu, mas consumidor não confirmou persistência da sessão.")
            print(json.dumps({"status": "persistence_confirmed", **expected}), flush=True)
    finally:
        client.disconnect()
        client.loop_stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("consume", "publish-demo"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--data-root", default="data/raw")
    parser.add_argument("--allow-real", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ready-file")
    parser.add_argument("--allow-devices", action="store_true", help="Assina amostras IoT sem incluí-las em corpora acadêmicos.")
    parser.add_argument("--iot-db", help="SQLite de telemetria isolada; padrão: irmão de raw, em iot/.")
    parser.add_argument("--mqtt-ca", help="CA PEM para TLS; valida certificado e hostname do broker.")
    parser.add_argument("--client-id", default="motionlab-ingest-v1", help="Único por consumidor/broker; preservar entre reinícios.")
    args = parser.parse_args(argv)
    if args.mode == "consume":
        consume(args.host, args.port, args.data_root, allow_real=args.allow_real, ready_file=args.ready_file,
                allow_devices=args.allow_devices, iot_db=args.iot_db, ca_file=args.mqtt_ca, client_id=args.client_id)
    else:
        publish_demo(args.host, args.port, args.seed, ca_file=args.mqtt_ca)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
