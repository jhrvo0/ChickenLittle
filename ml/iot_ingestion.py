"""Telemetria IoT v1: amostras sem rótulos, fora dos corpora de treino/avaliação."""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

DEVICE_TOPIC = "motionlab/v1/devices/"
MAX_PACKET_BYTES = 1024
MAX_INTEGER = 2**63 - 1  # SQLite INTEGER; séculos de operação à taxa de aquisição atual.
ORIGINS = {"real_hardware": "real", "synthetic_simulator": "synthetic"}
_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


def validate_sample(topic, payload, *, allow_physical=False):
    """Não infere proveniência, relógio civil, participante nem verdade de gesto."""
    required = {"schema_version", "kind", "device_id", "session_id", "sample_idx", "ts_ms",
                "data_origin", "distance_cm", "valid_ultrasonic", "ir_detected", "valid_ir",
                "captured_at_iso", "clock_source", "physical_validation", "dropped_total"}
    if not isinstance(payload, dict) or not required <= payload.keys():
        raise ValueError("Amostra IoT incompleta.")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1 or payload["kind"] != "sample":
        raise ValueError("Amostra IoT exige schema_version=1, kind=sample.")
    for key in ("device_id", "session_id"):
        if not isinstance(payload[key], str) or not _ID.fullmatch(payload[key]):
            raise ValueError("Identificação IoT inválida.")
    if topic != DEVICE_TOPIC + payload["device_id"] + "/samples":
        raise ValueError("Dispositivo e tópico divergentes.")
    origin = payload["data_origin"]
    if not isinstance(origin, str) or origin not in ORIGINS:
        raise ValueError("Origem IoT inválida.")
    if origin == "real_hardware" and not allow_physical:
        raise ValueError("Ingestão de origem física exige --allow-real.")
    if payload["physical_validation"] != "pending":
        raise ValueError("Payload não pode atestar validação física.")
    if payload["clock_source"] != "monotonic_boot" or payload["captured_at_iso"] is not None:
        raise ValueError("Relógio IoT v1 exige monotonic_boot e captured_at_iso=null.")
    for key in ("sample_idx", "ts_ms", "dropped_total"):
        if type(payload[key]) is not int or not 0 <= payload[key] <= MAX_INTEGER:
            raise ValueError("Sequência, timestamp e perdas devem ser inteiros não negativos de 63 bits.")
    for key in ("valid_ultrasonic", "ir_detected", "valid_ir"):
        if type(payload[key]) is not bool:
            raise ValueError("Flags IoT devem ser booleanos JSON.")
    distance = payload["distance_cm"]
    # Limitar antes de isfinite evita OverflowError na conversão de inteiros JSON enormes.
    if (isinstance(distance, bool) or not isinstance(distance, (int, float)) or
            not -1 <= distance <= 400 or not math.isfinite(distance)):
        raise ValueError("Distância IoT deve ser finita.")
    if payload["valid_ultrasonic"]:
        if not 2 <= distance <= 400:
            raise ValueError("Distância válida fora de 2..400 cm.")
    elif distance != -1:
        raise ValueError("Leitura inválida exige distance_cm=-1, como no USB v1.")
    # Apenas campos contratados; extensões desconhecidas não viram dados acadêmicos.
    normalized = {key: payload[key] for key in sorted(required)}
    normalized["distance_cm"] = float(distance)
    return normalized


class IotStore:
    """COMMIT síncrono antes do PUBACK; chave única sobrevive a reinícios do consumidor.

    WAL permite snapshots de inferência concorrentes. Nunca produz RawSampleRecord nem
    grava nos diretórios real/demo/synthetic. Limites de janela restringem RAM do leitor.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS samples (
                device_id TEXT NOT NULL, session_id TEXT NOT NULL, sample_idx INTEGER NOT NULL,
                ts_ms INTEGER NOT NULL, data_origin TEXT NOT NULL, dropped_total INTEGER NOT NULL,
                payload TEXT NOT NULL, received_at_iso TEXT NOT NULL,
                PRIMARY KEY(device_id, session_id, sample_idx))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def persist(self, topic, payload, *, allow_physical=False):
        sample = validate_sample(topic, payload, allow_physical=allow_physical)
        canonical = json.dumps(sample, sort_keys=True, separators=(",", ":"), allow_nan=False)
        key = sample["device_id"], sample["session_id"], sample["sample_idx"]
        with self.connect() as db:
            # Serializa verificação de conflito e INSERT, inclusive entre processos.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM samples WHERE device_id=? AND session_id=? AND sample_idx=?", key).fetchone()
            if existing:
                if existing[0] != canonical:
                    raise ValueError("Conflito IoT: mesma chave com conteúdo diferente.")
                status = "duplicate"
            else:
                device, session, idx = key
                identity = db.execute("SELECT data_origin FROM samples WHERE device_id=? AND session_id=? LIMIT 1", (device, session)).fetchone()
                if identity and identity[0] != sample["data_origin"]:
                    raise ValueError("Origem alterada dentro da sessão IoT.")
                for op, order in (("<", "DESC"), (">", "ASC")):
                    neighbor = db.execute(f"SELECT ts_ms,dropped_total FROM samples WHERE device_id=? AND session_id=? AND sample_idx {op} ? ORDER BY sample_idx {order} LIMIT 1", key).fetchone()
                    if neighbor and ((op == "<" and (neighbor[0] >= sample["ts_ms"] or neighbor[1] > sample["dropped_total"])) or
                                     (op == ">" and (neighbor[0] <= sample["ts_ms"] or neighbor[1] < sample["dropped_total"]))):
                        raise ValueError("Ordem temporal/contador inconsistente com a sequência IoT.")
                received = dt.datetime.now(dt.timezone.utc).isoformat()
                db.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)", (*key, sample["ts_ms"], sample["data_origin"], sample["dropped_total"], canonical, received))
                status = "persisted"
        return {"status": status, "device_id": key[0], "session_id": key[1], "sample_idx": key[2],
                "sample_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "physical_validation": "pending", "scope": "unlabelled_telemetry"}

    def latest_windows(self, *, limit=512, max_sessions=64):
        if not 2 <= limit <= 512 or not 1 <= max_sessions <= 64:
            raise ValueError("Leitura IoT limitada a 512 amostras e 64 sessões.")
        with self.connect() as db:
            # Sessões mais recentes por recepção (não compara relógios de boots distintos).
            sessions = db.execute("SELECT device_id,session_id,MAX(received_at_iso) AS last FROM samples GROUP BY device_id,session_id ORDER BY last DESC LIMIT ?", (max_sessions,)).fetchall()
            for device, session, _ in sessions:
                rows = db.execute("SELECT payload FROM samples WHERE device_id=? AND session_id=? ORDER BY sample_idx DESC LIMIT ?", (device, session, limit)).fetchall()
                tail = []
                for row in rows:
                    sample = json.loads(row[0])
                    if tail and sample["sample_idx"] != tail[-1]["sample_idx"] - 1:
                        break  # Nunca interpolar perda de transporte ou misturar janelas através de lacuna.
                    tail.append(sample)
                yield list(reversed(tail))


def predict_iot_windows(store, service):
    """Reusa filtro/features e inferência da API; nenhum rótulo é criado ou usado."""
    from ml.preprocessing.features import extract_window_features
    from ml.preprocessing.filtering import CausalSignalFilter
    from ml.schemas import FEATURE_NAMES
    cfg = service.bundle.preprocessing_config
    results = []
    for rows in store.latest_windows():
        width = cfg.window_size
        if len(rows) < width or not all(row["valid_ir"] for row in rows[-width:]):
            continue
        sample = rows[-1]
        signal_filter = CausalSignalFilter(cfg)
        filtered = [signal_filter.step(row["distance_cm"], row["valid_ultrasonic"]) for row in rows]
        features = extract_window_features(
            [d for d, _ in filtered[-width:]], [row["ts_ms"] for row in rows[-width:]],
            [row["ir_detected"] for row in rows[-width:]], [invalid for _, invalid in filtered[-width:]],
            inversion_deadband_cm=cfg.inversion_deadband_cm)
        prediction = service.infer({"schema_version": 1, "input_origin": ORIGINS[sample["data_origin"]],
                                    "features": list(features), "feature_names": list(FEATURE_NAMES)})
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        results.append({**prediction, "device_id": sample["device_id"], "session_id": sample["session_id"],
                        "dataset_sha256": digest, "samples": len(rows), "windows": 1,
                        "window_end_ts_ms": sample["ts_ms"], "processing_version": 2,
                        "scope": "live_iot_unlabelled", "data_origin": sample["data_origin"],
                        "physical_validation": "pending", "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat()})
    return results
