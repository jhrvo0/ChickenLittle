"""Painel ASCII de diagnóstico em tempo real (Seção 8): sensores, série temporal e TinyML."""

from __future__ import annotations

import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from ml.classifiers import BaseGestureClassifier, create_gesture_classifier
from ml.preprocessing.windowing import load_raw_records_from_path
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.games.launch_renderer import DifferentialTerminalWriter
from terminal.bench.assistant import FirmwareDiagSnapshot, parse_diag_status
from terminal.communication.protocol import (
    AckPayload,
    GestureEventPayload,
    GestureType,
    MessageType,
    ProtocolCodec,
    ProtocolError,
    SensorFramePayload,
)
from terminal.communication.transport import (
    PySerialEndpoint,
    SerialEndpoint,
    create_virtual_serial_pair,
)


@dataclass
class DiagnosticPanelState:
    """Estado acumulado de observabilidade em tempo real para o painel de diagnóstico."""

    origin_banner: str = "SIMULADOR VIRTUAL (NAO VALIDADO EM HARDWARE)"
    connection_state: str = "CONNECTED"
    port_label: str = "VIRTUAL_LOOPBACK"
    fw_version: str = "0.5.0-sim"
    model_name: str = "sim_window_heuristic"
    experimental_status: str = "AWAITING_REAL_DATA"

    # Telemetria instantânea e série temporal recente
    current_distance_cm: float | None = None
    valid_ultrasonic: bool = False
    ir_detected: bool = False
    pot_norm: float = 0.0
    distance_history: deque[float | None] = field(default_factory=lambda: deque(maxlen=44))
    ts_history_ms: deque[int] = field(default_factory=lambda: deque(maxlen=32))

    # Reconhecimento de gestos e eventos
    recognized_class: str = "NEUTRAL"
    confidence: float = 0.0
    accepted_events_count: int = 0
    rejected_events_count: int = 0
    last_rejection_reason: str = "none"
    recent_events: deque[str] = field(default_factory=lambda: deque(maxlen=4))

    # Perda de amostras, timeouts e latência
    total_samples: int = 0
    ultrasonic_timeouts: int = 0
    seq_drops: int = 0
    parse_errors: int = 0
    last_seq: int | None = None
    host_latency_ms: float = 0.0
    device_infer_us: int = 0

    def effective_hz(self) -> float:
        if len(self.ts_history_ms) < 2:
            return 0.0
        ts = list(self.ts_history_ms)
        dts = [ts[i + 1] - ts[i] for i in range(len(ts) - 1) if ts[i + 1] > ts[i]]
        if not dts:
            return 0.0
        mean_dt = float(statistics.fmean(dts))
        return round(1000.0 / mean_dt, 2) if mean_dt > 0.0 else 0.0

    def timeout_ratio_pct(self) -> float:
        if self.total_samples <= 0:
            return 0.0
        return round((self.ultrasonic_timeouts / self.total_samples) * 100.0, 1)

    def ingest_diag(self, snap: FirmwareDiagSnapshot) -> None:
        self.fw_version = snap.fw_version
        self.model_name = snap.model_name
        self.experimental_status = snap.experimental_status
        self.device_infer_us = snap.last_infer_us
        if snap.windows_rejected > self.rejected_events_count:
            self.rejected_events_count = snap.windows_rejected

    def ingest_sensor_frame(
        self,
        frame: SensorFramePayload,
        ts_ms: int,
        host_classifier: BaseGestureClassifier | None = None,
    ) -> None:
        self.total_samples += 1
        self.valid_ultrasonic = frame.valid_ultrasonic and (frame.distance_cm is not None)
        self.current_distance_cm = frame.distance_cm if self.valid_ultrasonic else None
        self.ir_detected = frame.ir_detected
        self.pot_norm = frame.pot_norm
        self.distance_history.append(self.current_distance_cm)
        self.ts_history_ms.append(ts_ms)
        if not self.valid_ultrasonic:
            self.ultrasonic_timeouts += 1

        if host_classifier is not None:
            evt = host_classifier.push_frame(frame, ts_ms=ts_ms)
            diag = host_classifier.get_diagnostics()
            self.model_name = diag.model_name
            self.experimental_status = diag.experimental_status
            self.recognized_class = diag.last_class
            self.confidence = diag.last_confidence
            self.host_latency_ms = diag.last_latency_ms
            self.rejected_events_count = diag.rejected_events
            if diag.last_rejection_reason:
                self.last_rejection_reason = diag.last_rejection_reason
            if evt is not None:
                self.ingest_gesture_event(evt, ts_ms=ts_ms)

    def ingest_gesture_event(self, event: GestureEventPayload, ts_ms: int) -> None:
        self.recognized_class = event.gesture.value
        self.confidence = event.confidence
        self.accepted_events_count += 1
        self.recent_events.append(
            f"t={ts_ms:06d}ms ACEITO {event.gesture.value:<8} ({event.confidence * 100.0:4.0f}%) [{event.source.value}]"
        )

    def ingest_raw_line(
        self,
        raw_line: str,
        codec: ProtocolCodec,
        host_classifier: BaseGestureClassifier | None = None,
    ) -> None:
        if not raw_line.strip():
            return
        try:
            env = codec.decode(raw_line)
        except ProtocolError:
            self.parse_errors += 1
            return

        if self.last_seq is not None and env.seq > (self.last_seq + 1):
            self.seq_drops += env.seq - (self.last_seq + 1)
        self.last_seq = env.seq

        if env.type == MessageType.SENSOR_FRAME:
            try:
                sf = SensorFramePayload.from_dict(env.data)
            except ProtocolError:
                self.parse_errors += 1
                return
            self.ingest_sensor_frame(sf, ts_ms=env.ts_ms, host_classifier=host_classifier)
        elif env.type == MessageType.GESTURE_EVENT:
            try:
                ge = GestureEventPayload.from_dict(env.data)
            except ProtocolError:
                self.parse_errors += 1
                return
            # Evita contagem dupla caso o host_classifier já tenha emitido localmente
            if host_classifier is None:
                self.ingest_gesture_event(ge, ts_ms=env.ts_ms)
        elif env.type == MessageType.ACK:
            ack = AckPayload.from_dict(env.data)
            if ack.status.startswith("diag:"):
                self.ingest_diag(parse_diag_status(ack.status))


def _ascii_bar(ratio: float, width: int = 16) -> str:
    clamped = max(0.0, min(1.0, float(ratio)))
    filled = int(round(clamped * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _build_timeseries_chart(
    history: deque[float | None],
    cols: int = 44,
    rows: int = 6,
    max_cm: float = 60.0,
) -> list[str]:
    """Desenha gráfico ASCII multi-linha das leituras recentes de distância (0..60 cm)."""
    samples = list(history)[-cols:]
    pad_left = cols - len(samples)

    grid = [[" " for _ in range(cols)] for _ in range(rows)]
    for idx, val in enumerate(samples):
        x = pad_left + idx
        if val is None:
            grid[0][x] = "x"  # Timeout / leitura inválida real marcada no topo
            continue
        norm = max(0.0, min(1.0, float(val) / max_cm))
        # Linha 0 = topo (60 cm), linha rows-1 = base (0 cm)
        y = (rows - 1) - int(round(norm * (rows - 1)))
        y = max(0, min(rows - 1, y))
        grid[y][x] = "*"

    out: list[str] = []
    for r in range(rows):
        axis_cm = int(round(max_cm * (1.0 - (r / max(1, rows - 1)))))
        row_str = "".join(grid[r])
        out.append(f"{axis_cm:2d}cm |{row_str}|")
    out.append("     +" + ("-" * cols) + "+")
    return out


class DiagnosticPanelRenderer:
    """Renderizador ASCII puro (86 colunas padrão ou 60 colunas compacto) do painel de diagnóstico."""

    PANEL_WIDTH = 86
    COMPACT_WIDTH = 60

    def render(self, state: DiagnosticPanelState, compact: bool = False) -> str:
        w = self.COMPACT_WIDTH if compact else self.PANEL_WIDTH
        border = "+" + ("=" * (w - 2)) + "+"
        sep = "+" + ("-" * (w - 2)) + "+"

        def _row(text: str) -> str:
            clean = text.replace("\t", " ")
            return "| " + clean[: w - 4].ljust(w - 4) + " |"

        dist_str = (
            f"{state.current_distance_cm:5.1f} cm (OK)"
            if state.valid_ultrasonic and state.current_distance_cm is not None
            else "TIMEOUT / SEM ECO"
        )
        dist_ratio = (
            1.0 - min(1.0, max(0.0, (state.current_distance_cm or 60.0) / 60.0))
            if state.valid_ultrasonic and state.current_distance_cm is not None
            else 0.0
        )
        lat_str = (
            f"host={state.host_latency_ms:.2f}ms | esp32={state.device_infer_us}us"
            if state.device_infer_us > 0
            else f"{state.host_latency_ms:.3f} ms"
        )

        lines: list[str] = [
            border,
            _row(f"MOTIONPET DIAG PANEL | ORIGEM: {state.origin_banner}"),
            _row(
                f"CONEXAO: {state.connection_state} ({state.port_label}) | "
                f"FW: {state.fw_version} | FREQ: {state.effective_hz():4.1f} Hz"
            ),
            sep,
            _row(
                f"DISTANCIA INST.: {dist_str:<19} PROX:{_ascii_bar(dist_ratio, 12 if compact else 18)}"
            ),
            _row(
                f"SENSORES AUX.:   IR={'DETECTADO' if state.ir_detected else 'LIVRE    '} | "
                f"POT={state.pot_norm:5.3f} | AMOSTRAS={state.total_samples}"
            ),
            sep,
            _row("SERIE TEMPORAL RECENTE DE DISTANCIA ('*' = cm valido, 'x' = timeout):"),
        ]

        chart_cols = 42 if compact else 68
        for cline in _build_timeseries_chart(state.distance_history, cols=chart_cols, rows=5):
            lines.append(_row(cline))

        recent_vals = [
            f"{d:.1f}" if d is not None else "TO"
            for d in list(state.distance_history)[-8:]
        ]
        lines.append(_row("Ultimas leituras (cm): " + (", ".join(recent_vals) if recent_vals else "aguardando...")))
        lines.append(sep)
        lines.append(
            _row(
                f"MODELO TINYML: {state.model_name} | STATUS EXP.: {state.experimental_status}"
            )
        )
        lines.append(
            _row(
                f"CLASSE RECONHECIDA: {state.recognized_class:<10} | "
                f"CONFIANCA: {state.confidence * 100.0:5.1f}% {_ascii_bar(state.confidence, 10 if compact else 16)}"
            )
        )
        lines.append(
            _row(
                f"EVENTOS: Aceitos={state.accepted_events_count:<4} | "
                f"Rejeitados={state.rejected_events_count:<4} (motivo: {state.last_rejection_reason})"
            )
        )
        lines.append(
            _row(
                f"PERDAS/SAUDE: Drops seq={state.seq_drops} | "
                f"Timeouts US={state.ultrasonic_timeouts} ({state.timeout_ratio_pct():.1f}%) | "
                f"Erros JSON={state.parse_errors}"
            )
        )
        lines.append(_row(f"LATENCIA DE INFERENCIA: {lat_str}"))
        lines.append(sep)
        lines.append(_row("HISTORICO DE EVENTOS GESTUAIS RECENTES:"))
        if state.recent_events:
            for ev_line in state.recent_events:
                lines.append(_row("  " + ev_line))
        else:
            lines.append(_row("  (nenhum evento ativo emitido ate o momento)"))
        lines.append(border)
        return "\n".join(lines)


def run_diagnostic_session(
    serial_port: str | None = None,
    simulate: bool = False,
    replay_path: str | Path | None = None,
    baudrate: int = 115200,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
    max_frames: int = 30,
    compact: bool = False,
    output_stream: TextIO | None = None,
    interactive_differential: bool = False,
) -> tuple[DiagnosticPanelState, str]:
    """Executa o painel de diagnóstico com dados reais (`--serial-port`), simulados ou replay."""
    stream = output_stream or sys.stdout
    renderer = DiagnosticPanelRenderer()
    codec = ProtocolCodec()
    state = DiagnosticPanelState()
    writer = DifferentialTerminalWriter(stream=stream, is_tty=interactive_differential)

    # Caso 1: Replay determinístico de sessão `.jsonl` / `.csv`
    if replay_path is not None:
        records = load_raw_records_from_path(replay_path)
        origins = sorted({r.data_origin for r in records})
        is_real_file = origins == ["real_hardware"]
        state.origin_banner = (
            "REPLAY DE DATASET FISICO REAL"
            if is_real_file
            else "REPLAY SIMULADO / SINTETICO (NAO FISICO)"
        )
        state.port_label = f"FILE:{Path(replay_path).name}"
        clf = create_gesture_classifier(kind=classifier_kind, model_path=model_path)
        limit = min(len(records), max(1, max_frames))
        last_render = ""
        for rec in records[:limit]:
            sf = SensorFramePayload(
                distance_cm=rec.distance_cm,
                ir_detected=rec.ir_detected,
                pot_norm=rec.pot_norm,
                valid_ultrasonic=rec.valid_ultrasonic,
            )
            state.ingest_sensor_frame(sf, ts_ms=rec.ts_ms, host_classifier=clf)
            last_render = renderer.render(state, compact=compact)
            if interactive_differential:
                writer.write_frame(last_render)
        if not interactive_differential:
            stream.write(last_render + "\n")
            stream.flush()
        return state, last_render

    # Caso 2: Hardware físico via USB Serial
    if serial_port and not simulate:
        state.origin_banner = f"HARDWARE REAL ESP32 ({serial_port})"
        state.port_label = serial_port
        host_clf = (
            None
            if classifier_kind == "embedded"
            else create_gesture_classifier(kind=classifier_kind, model_path=model_path)
        )
        ep: SerialEndpoint = PySerialEndpoint(port=serial_port, baudrate=baudrate)
        last_render = ""
        try:
            ep.write_line("DIAG")
            deadline = time.monotonic() + max(2.0, max_frames * 0.08)
            while state.total_samples < max_frames and time.monotonic() < deadline:
                lines = ep.read_all_lines()
                if not lines:
                    time.sleep(0.01)
                    continue
                for ln in lines:
                    state.ingest_raw_line(ln, codec=codec, host_classifier=host_clf)
                last_render = renderer.render(state, compact=compact)
                if interactive_differential:
                    writer.write_frame(last_render)
            if not last_render:
                state.connection_state = "CONNECTED (SEM QUADROS SENSOR_FRAME)"
                last_render = renderer.render(state, compact=compact)
            if not interactive_differential:
                stream.write(last_render + "\n")
                stream.flush()
        finally:
            ep.close()
        return state, last_render

    # Caso 3: Simulador virtual completo
    state.origin_banner = "SIMULADOR VIRTUAL (DADOS SINTETICOS)"
    state.port_label = "VIRTUAL_SERIAL_JSONL_V1"
    host_ep, dev_ep, _ = create_virtual_serial_pair(max_wire_log=1000)
    sensor_sim = SensorSimulator(seed=77, sample_period_ms=65, noise_std_cm=0.45, dropout_prob=0.05)
    sim_clf = create_gesture_classifier(
        kind="sim" if classifier_kind == "embedded" else classifier_kind,
        model_path=model_path,
    )
    node = SimulatedEsp32Node(endpoint=dev_ep, sensor_source=sensor_sim, classifier=sim_clf)
    node.boot(auto_load=False)
    host_ep.read_all_lines()

    # Enfileira gestos variados para demonstrar séries temporais, aceites e rejeições
    sensor_sim.queue_gesture_profile(GestureType.APPROACH)
    sensor_sim.queue_gesture_profile(GestureType.HOLD)
    sensor_sim.queue_gesture_profile(GestureType.RETREAT)

    host_ep.write_line("DIAG")
    last_render = ""
    try:
        for _ in range(max(1, max_frames)):
            node.step()
            for ln in host_ep.read_all_lines():
                state.ingest_raw_line(ln, codec=codec, host_classifier=None)
            diag_now = sim_clf.get_diagnostics()
            state.model_name = diag_now.model_name
            state.experimental_status = diag_now.experimental_status
            state.host_latency_ms = diag_now.last_latency_ms
            state.rejected_events_count = diag_now.rejected_events
            if diag_now.last_rejection_reason:
                state.last_rejection_reason = diag_now.last_rejection_reason
            last_render = renderer.render(state, compact=compact)
            if interactive_differential:
                writer.write_frame(last_render)
        if not interactive_differential:
            stream.write(last_render + "\n")
            stream.flush()
    finally:
        host_ep.close()
        dev_ep.close()

    return state, last_render
