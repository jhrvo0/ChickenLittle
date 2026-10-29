"""Gravador de sessões de sensores via protocolo Serial JSON Lines v1 (físico ou simulado)."""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from ml.collection.validator import SessionQualityReport, validate_session_records
from ml.schemas import (
    CORE_GESTURE_CLASSES,
    EXPERIMENTAL_GESTURE_CLASSES,
    DataOrigin,
    RawSampleRecord,
)
from simulator.esp32_sim_node import SIMULATED_FW_VERSION, SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.communication.protocol import (
    AckPayload,
    GestureType,
    MessageType,
    ProtocolCodec,
    ProtocolError,
    SensorFramePayload,
)
from terminal.communication.transport import SerialEndpoint, create_virtual_serial_pair

SAMPLE_CSV_FIELDS: tuple[str, ...] = (
    "participant_id",
    "session_id",
    "sample_idx",
    "ts_ms",
    "label",
    "distance_cm",
    "valid_ultrasonic",
    "ir_detected",
    "pot_norm",
    "data_origin",
    "captured_at_iso",
)

DEFAULT_GUIDED_REAL_SCHEDULE = (
    "NEUTRAL:20,APPROACH:16,NEUTRAL:16,RETREAT:16,NEUTRAL:16,HOLD:18,NEUTRAL:20"
)


def parse_gesture_schedule(schedule_spec: str) -> list[tuple[str, int]]:
    """Converte string como `'NEUTRAL:12,APPROACH:10,NEUTRAL:10'` em lista `[(label, count)]`."""
    segments: list[tuple[str, int]] = []
    for part in schedule_spec.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(
                f"Segmento inválido '{item}' no cronograma (use FORMATO 'CLASSE:AMOSTRAS')."
            )
        label_str, count_str = item.split(":", 1)
        count = int(count_str.strip())
        if count <= 0:
            raise ValueError(f"Contagem de amostras deve ser positiva em '{item}'.")
        segments.append((label_str.strip().upper(), count))
    if not segments:
        raise ValueError("Cronograma de captura vazio.")
    return segments


def probe_firmware_version_from_endpoint(
    endpoint: SerialEndpoint,
    step_callback: Callable[[], None] | None = None,
    timeout_sec: float = 1.2,
) -> str:
    """Consulta opcionalmente a versão do firmware via comando `DIAG` antes da sessão."""
    codec = ProtocolCodec()
    endpoint.read_all_lines()
    endpoint.write_line("DIAG")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() <= deadline:
        if step_callback is not None:
            step_callback()
        lines = endpoint.read_all_lines()
        if not lines:
            time.sleep(0.01)
            continue
        for line in lines:
            try:
                env = codec.decode(line)
            except ProtocolError:
                continue
            if env.type == MessageType.ACK:
                ack = AckPayload.from_dict(env.data)
                if ack.status.startswith("diag:"):
                    for tok in ack.status[5:].split(","):
                        if tok.startswith("fw="):
                            return tok.split("=", 1)[1].strip()
    return "unknown"


class SerialSessionRecorder:
    """Captura quadros `sensor_frame` de um `SerialEndpoint` e anota metadados de sessão."""

    def __init__(
        self,
        endpoint: SerialEndpoint,
        data_origin: DataOrigin = DataOrigin.REAL_HARDWARE,
        step_callback: Callable[[], None] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.data_origin = data_origin
        self.step_callback = step_callback
        self.codec = ProtocolCodec()
        self.parse_errors: int = 0
        self.seq_drops: int = 0
        self.ultrasonic_timeouts: int = 0
        self._last_seq: int | None = None

    def record_schedule(
        self,
        participant_id: str,
        session_id: str,
        schedule: Sequence[tuple[str, int]],
        on_segment_start: Callable[[str, int], None] | None = None,
        timeout_sec: float = 30.0,
    ) -> list[RawSampleRecord]:
        """Grava uma sequência contínua de segmentos rotulados (incluindo NEUTRAL e transições)."""
        records: list[RawSampleRecord] = []
        sample_idx = 0
        last_ts_ms = -1
        captured_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        self.parse_errors = 0
        self.seq_drops = 0
        self.ultrasonic_timeouts = 0
        self._last_seq = None

        for label, target_count in schedule:
            norm_label = label.strip().upper()
            if on_segment_start is not None:
                on_segment_start(norm_label, target_count)

            collected_in_seg = 0
            deadline = time.monotonic() + timeout_sec

            while collected_in_seg < target_count:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Timeout aguardando quadros 'sensor_frame' na sessão '{session_id}' "
                        f"({collected_in_seg}/{target_count} amostras no segmento {norm_label})."
                    )

                if self.step_callback is not None:
                    self.step_callback()

                lines = self.endpoint.read_all_lines()
                if not lines:
                    time.sleep(0.005)
                    continue

                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        env = self.codec.decode(line)
                    except ProtocolError:
                        self.parse_errors += 1
                        continue

                    if self._last_seq is not None and env.seq > (self._last_seq + 1):
                        self.seq_drops += env.seq - (self._last_seq + 1)
                    self._last_seq = env.seq

                    if env.type != MessageType.SENSOR_FRAME:
                        continue

                    frame = SensorFramePayload.from_dict(env.data)
                    if not frame.valid_ultrasonic or frame.distance_cm is None:
                        self.ultrasonic_timeouts += 1
                    ts_ms = env.ts_ms if env.ts_ms > last_ts_ms else (last_ts_ms + 1)
                    last_ts_ms = ts_ms

                    records.append(
                        RawSampleRecord(
                            participant_id=participant_id,
                            session_id=session_id,
                            sample_idx=sample_idx,
                            ts_ms=ts_ms,
                            label=norm_label,
                            distance_cm=frame.distance_cm,
                            valid_ultrasonic=frame.valid_ultrasonic,
                            ir_detected=frame.ir_detected,
                            pot_norm=frame.pot_norm,
                            data_origin=self.data_origin.value,
                            captured_at_iso=captured_iso,
                        )
                    )
                    sample_idx += 1
                    collected_in_seg += 1
                    if collected_in_seg >= target_count:
                        break

        return records


def build_session_metadata(
    records: Sequence[RawSampleRecord],
    validation_report: SessionQualityReport | None = None,
    schedule: Sequence[tuple[str, int]] | None = None,
    conditions: str = "unspecified",
    firmware_version: str = "unknown",
    serial_port: str | None = None,
    parse_errors: int = 0,
    seq_drops: int = 0,
) -> dict[str, Any]:
    """Constrói metadados enriquecidos da sessão (Seção 4 do Ciclo 5), preservando chaves de `SessionValidationReport`."""
    rep = validation_report or validate_session_records(records)
    base = rep.to_dict()

    labels_present = sorted({r.label for r in records})
    exp_present = [c for c in labels_present if c in EXPERIMENTAL_GESTURE_CLASSES]
    core_present = [c for c in labels_present if c in CORE_GESTURE_CLASSES]
    timeouts_cnt = sum(1 for r in records if (not r.valid_ultrasonic or r.distance_cm is None))
    ir_active_cnt = sum(1 for r in records if r.ir_detected)

    base.update(
        {
            "participant_id": records[0].participant_id if records else "unknown",
            "firmware_version": firmware_version,
            "collection_conditions": conditions,
            "serial_port": serial_port or "SIMULATED_LOOPBACK",
            "target_schedule": (
                [{"label": lbl, "samples": cnt} for lbl, cnt in schedule]
                if schedule is not None
                else []
            ),
            "core_classes_recorded": core_present,
            "experimental_classes_recorded": exp_present,
            "experimental_classes_policy": (
                "CORE_4_CLASSES_ONLY (IMPULSE e DOUBLE mantidos como experimentais)"
                if not exp_present
                else "INCLUDES_EXPERIMENTAL_CLASSES"
            ),
            "failures_and_timeouts": {
                "ultrasonic_timeouts_count": timeouts_cnt,
                "invalid_ratio": rep.invalid_ratio,
                "serial_parse_errors": int(parse_errors),
                "serial_seq_drops": int(seq_drops),
            },
            "ir_sensor_summary": {
                "ir_detected_samples": ir_active_cnt,
                "ir_detected_ratio": round(ir_active_cnt / len(records), 4) if records else 0.0,
            },
        }
    )
    return base


def build_real_collection_campaign_plan(num_participants: int = 5) -> dict[str, Any]:
    """Gera plano estruturado de coleta real multi-participante (>= 5 participantes, zero mistura sintética)."""
    n_p = max(5, int(num_participants))
    participants: list[dict[str, Any]] = []
    variations = [
        ("frontal_central_vel_normal", "Mao alinhada ao eixo central (15..45 cm), velocidade natural"),
        ("frontal_central_vel_rapida", "Mao no eixo central, movimentos rapidos decididos"),
        ("leve_desvio_lateral_vel_lenta", "Desvio lateral ~5 cm, aproximacao/recuo suaves"),
    ]
    for idx in range(1, n_p + 1):
        pid = f"p{idx:02d}"
        if idx == n_p:
            role = "TEST_HELD_OUT_FINAL (reservado exclusivamente p/ avaliacao unica final)"
        elif idx == (n_p - 1):
            role = "VALIDATION_GROUP (selecao multicriterio de hiperparametros/modelo)"
        else:
            role = "TRAIN_GROUP (ajuste dos modelos candidatos)"
        sessions = [
            {
                "session_id": f"real_{pid}_s{s_idx:02d}",
                "conditions": cond_tag,
                "guidance": desc,
                "recommended_schedule": DEFAULT_GUIDED_REAL_SCHEDULE,
            }
            for s_idx, (cond_tag, desc) in enumerate(variations, start=1)
        ]
        participants.append({"participant_id": pid, "assigned_split_role": role, "sessions": sessions})

    return {
        "campaign_name": "MotionPet Ciclo 5 — Coleta Fisica Real de Gestos",
        "core_classes": list(CORE_GESTURE_CLASSES),
        "experimental_classes": list(EXPERIMENTAL_GESTURE_CLASSES),
        "strict_anti_synthetic_rule": (
            "PROIBIDO misturar arquivos 'synthetic_simulator' em 'data/raw/real'. "
            "Use um diretorio exclusivo para dados fisicos reais."
        ),
        "recommended_participants_count": n_p,
        "participants": participants,
    }


def save_session_jsonl(records: Sequence[RawSampleRecord], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.to_dict(), separators=(",", ":"), ensure_ascii=True) for r in records]
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out


def save_session_csv(records: Sequence[RawSampleRecord], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SAMPLE_CSV_FIELDS)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.to_dict())
    return out


def record_simulated_session(
    participant_id: str,
    session_id: str,
    schedule: Sequence[tuple[str, int]],
    seed: int = 42,
    sample_period_ms: int = 70,
    noise_std_cm: float = 0.55,
    dropout_prob: float = 0.03,
) -> list[RawSampleRecord]:
    """Executa uma captura completa usando `SimulatedEsp32Node` sobre `VirtualSerialEndpoint`."""
    host_ep, dev_ep, _ = create_virtual_serial_pair()
    sensor_sim = SensorSimulator(
        seed=seed,
        sample_period_ms=sample_period_ms,
        noise_std_cm=noise_std_cm,
        dropout_prob=dropout_prob,
    )
    node = SimulatedEsp32Node(endpoint=dev_ep, sensor_source=sensor_sim)
    node.boot(auto_load=False)
    # Limpa snapshot inicial de boot para focar nos sensor_frames da sessão
    host_ep.read_all_lines()

    def _inject_segment(label: str, count: int) -> None:
        try:
            g_type = GestureType(label)
        except ValueError:
            g_type = GestureType.NEUTRAL
        queued = 0
        while queued < count:
            sensor_sim.queue_gesture_profile(g_type)
            queued += 10

    recorder = SerialSessionRecorder(
        endpoint=host_ep,
        data_origin=DataOrigin.SYNTHETIC_SIMULATOR,
        step_callback=node.step,
    )
    try:
        return recorder.record_schedule(
            participant_id=participant_id,
            session_id=session_id,
            schedule=schedule,
            on_segment_start=_inject_segment,
        )
    finally:
        _ = SIMULATED_FW_VERSION
        host_ep.close()
        dev_ep.close()
