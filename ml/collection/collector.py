"""Gravador de sessões de sensores via protocolo Serial JSON Lines v1 (físico ou simulado)."""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path
from typing import Callable, Sequence

from ml.schemas import DataOrigin, RawSampleRecord
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.communication.protocol import (
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
                    try:
                        env = self.codec.decode(line)
                    except ProtocolError:
                        continue

                    if env.type != MessageType.SENSOR_FRAME:
                        continue

                    frame = SensorFramePayload.from_dict(env.data)
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
        # Enfileira perfis suficientes para cobrir `count` amostras
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
        host_ep.close()
        dev_ep.close()
