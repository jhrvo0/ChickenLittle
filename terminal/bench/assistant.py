"""Implementação do Assistente de Bancada CLI e validação incremental (Etapas A, B, C e D)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.bench.pinout import (
    CANONICAL_PINOUT_TABLE,
    ESP32_GPIO_MAX_SAFE_V,
    PINOUT_RECONCILIATION_NOTE,
    PREFERRED_ECHO_R1_OHM,
    PREFERRED_ECHO_R2_OHM,
    EchoDividerAssessment,
    evaluate_echo_divider,
    verify_canonical_pinout_conflicts,
)
from terminal.communication.protocol import (
    AckPayload,
    GestureType,
    LcdFramePayload,
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

DEFAULT_BENCH_LOG_PATH = Path("data/reports/bench_validation_log.json")

_ESP32_USB_KEYWORDS: tuple[str, ...] = (
    "cp210",
    "ch340",
    "ch341",
    "ch9102",
    "ftdi",
    "ft232",
    "silicon labs",
    "wch.cn",
    "usb jtag",
    "usb-serial",
    "esp32",
    "uart",
)


@dataclass(frozen=True)
class DependencyCheckReport:
    """Resumo de prontidão das dependências de software, compilação e firmware."""

    python_version: str
    python_ok: bool
    packages: dict[str, bool]
    platformio_cli_path: str | None
    firmware_binary_exists: bool
    firmware_binary_path: str
    tinyml_header_exists: bool
    tinyml_model_name: str
    tinyml_experimental_status: str
    pinout_conflict_free: bool
    ready_for_bench: bool
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SerialPortDescriptor:
    """ Porta serial identificada no sistema operacional."""

    device: str
    description: str
    hwid: str
    likely_esp32: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FirmwareDiagSnapshot:
    """Dados estruturados extraídos da resposta `ack` ao comando `DIAG`."""

    raw_status: str
    fw_version: str
    origin: str  # "ESP32_HW" | "SIMULATOR" | "UNKNOWN"
    pinout_status: str
    acquisition_active: bool
    sample_period_ms: int
    last_acquire_us: int
    total_samples: int
    ultrasonic_timeouts: int
    dropped_infer_queue: int
    dropped_tx_queue: int
    model_name: str
    experimental_status: str
    last_infer_us: int
    events_emitted: int
    windows_rejected: int
    active_mode: str
    nvs_writes: int
    lcd_frames: int
    free_heap_bytes: int
    roundtrip_ms: float

    @property
    def is_physical_hardware(self) -> bool:
        return self.origin == "ESP32_HW"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_physical_hardware"] = self.is_physical_hardware
        return data


@dataclass(frozen=True)
class TelemetryInspectionReport:
    """Métricas estatísticas e de integridade coletadas do fluxo JSON Lines v1."""

    validation_origin: str  # "PHYSICAL_ESP32" | "SIMULATION"
    duration_sec: float
    expected_period_ms: int
    total_lines_rx: int
    parse_errors: int
    seq_gaps_detected: int
    sensor_frames_count: int
    valid_ultrasonic_count: int
    ultrasonic_timeouts_count: int
    timeout_ratio: float
    mean_dt_ms: float
    jitter_std_ms: float
    effective_hz: float
    period_within_tolerance: bool
    distance_min_cm: float | None
    distance_max_cm: float | None
    distance_mean_cm: float | None
    distance_std_cm: float | None
    reference_cm: float | None
    reference_abs_error_cm: float | None
    reference_within_tolerance: bool | None
    ir_true_count: int
    ir_false_count: int
    ir_transitions: int
    pot_min: float | None
    pot_max: float | None
    pot_span: float | None
    gesture_events_count: int
    lcd_frames_count: int
    last_lcd_lines: tuple[str, ...]
    passed: bool
    problems: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StageValidationResult:
    """Resultado auditável de uma etapa incremental de bancada (Etapas A, B, C ou D)."""

    stage: str
    validation_origin: str  # "PHYSICAL_ESP32" | "SIMULATION"
    passed: bool
    halted_for_electrical_safety: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    problems: tuple[str, ...] = ()
    next_manual_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_platformio_cli() -> str | None:
    import shutil

    found = shutil.which("pio")
    if found:
        return found
    candidate = (
        Path.home()
        / ".platformio"
        / "penv"
        / ("Scripts" if os.name == "nt" else "bin")
        / ("pio.exe" if os.name == "nt" else "pio")
    )
    return str(candidate) if candidate.is_file() else None


def _inspect_tinyml_header(header_path: Path) -> tuple[str, str]:
    if not header_path.is_file():
        return ("missing", "MISSING_HEADER")
    txt = header_path.read_text(encoding="utf-8")
    model_name = "unknown"
    exp_status = "AWAITING_REAL_DATA"
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("#define TINYML_MODEL_NAME "):
            parts = s.split('"')
            if len(parts) >= 2:
                model_name = parts[1]
        elif s.startswith("#define TINYML_EXPERIMENTAL_STATUS "):
            parts = s.split('"')
            if len(parts) >= 2:
                exp_status = parts[1]
    return (model_name, exp_status)


def check_dependencies(repo_root: str | Path = ".") -> DependencyCheckReport:
    """Verifica ambiente Python, pacotes seriais/ML, PlatformIO, binário do firmware e pinagem."""
    root = Path(repo_root)
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = (sys.version_info.major, sys.version_info.minor) >= (3, 11)

    req_pkgs = {
        "pyserial": "serial",
        "numpy": "numpy",
        "scikit-learn": "sklearn",
        "joblib": "joblib",
    }
    pkg_status = {
        label: (importlib.util.find_spec(mod_name) is not None)
        for label, mod_name in req_pkgs.items()
    }

    pio_path = _detect_platformio_cli()
    fw_bin = root / "firmware" / ".pio" / "build" / "esp32dev" / "firmware.bin"
    hdr_path = root / "firmware" / "gestures" / "tinyml_model.h"
    mdl_name, exp_status = _inspect_tinyml_header(hdr_path)
    pin_ok, pin_issues = verify_canonical_pinout_conflicts()

    notes: list[str] = []
    for pkg, ok in pkg_status.items():
        if not ok:
            notes.append(f"Pacote Python ausente: '{pkg}' (instale no .venv antes da bancada).")
    if pio_path is None:
        notes.append("PlatformIO CLI ('pio') nao localizado; necessario para gravar o ESP32.")
    if not fw_bin.is_file():
        notes.append("Binario firmware.bin ainda nao compilado (execute 'pio run -d firmware').")
    if exp_status != "EVALUATED_ON_REAL_DATA":
        notes.append(
            f"Modelo TinyML atual ('{mdl_name}') esta com status '{exp_status}' "
            "(aguardando coleta e retreinamento com dataset fisico real)."
        )
    notes.extend(pin_issues)

    ready = py_ok and all(pkg_status.values()) and hdr_path.is_file() and pin_ok
    return DependencyCheckReport(
        python_version=py_ver,
        python_ok=py_ok,
        packages=pkg_status,
        platformio_cli_path=pio_path,
        firmware_binary_exists=fw_bin.is_file(),
        firmware_binary_path=str(fw_bin),
        tinyml_header_exists=hdr_path.is_file(),
        tinyml_model_name=mdl_name,
        tinyml_experimental_status=exp_status,
        pinout_conflict_free=pin_ok,
        ready_for_bench=ready,
        notes=tuple(notes),
    )


def list_serial_ports() -> list[SerialPortDescriptor]:
    """Enumera portas seriais ativas no SO e destaca conversores USB-UART típicos de ESP32."""
    try:
        import serial.tools.list_ports as lp  # type: ignore[import-not-found]
    except ImportError:
        return []

    out: list[SerialPortDescriptor] = []
    for p in sorted(lp.comports(), key=lambda item: str(item.device)):
        desc = str(getattr(p, "description", "") or "")
        hwid = str(getattr(p, "hwid", "") or "")
        combined = f"{desc} {hwid}".lower()
        likely = any(kw in combined for kw in _ESP32_USB_KEYWORDS)
        out.append(
            SerialPortDescriptor(
                device=str(p.device),
                description=desc,
                hwid=hwid,
                likely_esp32=likely,
            )
        )
    return out


def parse_diag_status(status_str: str, roundtrip_ms: float = 0.0) -> FirmwareDiagSnapshot:
    """Converte string `diag:fw=...,origin=...,acq=...` em `FirmwareDiagSnapshot`."""
    clean = status_str.strip()
    body = clean[5:] if clean.startswith("diag:") else clean
    kv: dict[str, str] = {}
    for token in body.split(","):
        if "=" in token:
            k, v = token.split("=", 1)
            kv[k.strip()] = v.strip()

    def _int(key: str, default: int = 0) -> int:
        raw = kv.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    origin = kv.get("origin", "ESP32_HW" if "fw" not in kv and "heap" in kv else "UNKNOWN")
    return FirmwareDiagSnapshot(
        raw_status=clean,
        fw_version=kv.get("fw", "0.3.0-legacy"),
        origin=origin,
        pinout_status=kv.get("pins", "UNSPECIFIED"),
        acquisition_active=(kv.get("acq", "on").lower() == "on"),
        sample_period_ms=_int("per_ms", 70),
        last_acquire_us=_int("acq_us", 0),
        total_samples=_int("samp", 0),
        ultrasonic_timeouts=_int("to_us", 0),
        dropped_infer_queue=_int("drop_inf", 0),
        dropped_tx_queue=_int("drop_tx", 0),
        model_name=kv.get("mdl", "unknown"),
        experimental_status=kv.get("exp", "AWAITING_REAL_DATA"),
        last_infer_us=_int("inf_us", 0),
        events_emitted=_int("evt", 0),
        windows_rejected=_int("rej", 0),
        active_mode=kv.get("mode", "MOTION_PET"),
        nvs_writes=_int("nvs_w", 0),
        lcd_frames=_int("lcd_f", 0),
        free_heap_bytes=_int("heap", 0),
        roundtrip_ms=round(float(roundtrip_ms), 3),
    )


def query_device_diag(
    endpoint: SerialEndpoint,
    step_callback: Callable[[], None] | None = None,
    timeout_sec: float = 2.5,
) -> FirmwareDiagSnapshot:
    """Envia comando `DIAG` ao endpoint serial e aguarda o envelope `ack` correspondente."""
    codec = ProtocolCodec()
    # Limpa fila de entrada pendente antes do pedido de diagnóstico
    endpoint.read_all_lines()

    t0 = time.perf_counter()
    endpoint.write_line("DIAG")
    deadline = time.monotonic() + timeout_sec
    next_request = time.monotonic() + 0.5

    while time.monotonic() <= deadline:
        # Abrir a USB pode reiniciar a ESP32 e perder o primeiro comando durante
        # o boot. Reenvie a consulta idempotente dentro do mesmo prazo limitado.
        if time.monotonic() >= next_request:
            endpoint.write_line("DIAG")
            next_request = time.monotonic() + 0.5
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
                    rtt_ms = (time.perf_counter() - t0) * 1000.0
                    return parse_diag_status(ack.status, roundtrip_ms=rtt_ms)

    raise TimeoutError(
        "Timeout aguardando resposta 'ack' com 'diag:...' do dispositivo. "
        "Verifique cabo USB de dados, porta COM, baudrate 115200 e se o firmware foi gravado."
    )


def inspect_telemetry_stream(
    endpoint: SerialEndpoint,
    duration_sec: float = 3.0,
    expected_period_ms: int = 70,
    reference_cm: float | None = None,
    reference_tolerance_cm: float = 3.0,
    validation_origin: str = "PHYSICAL_ESP32",
    step_callback: Callable[[], None] | None = None,
    simulated_steps: int | None = None,
) -> TelemetryInspectionReport:
    """Inspeciona o fluxo JSON Lines v1: frequência, jitter, perdas, timeouts e sensores."""
    codec = ProtocolCodec()
    endpoint.read_all_lines()

    total_lines = 0
    parse_errors = 0
    seq_gaps = 0
    last_seq: int | None = None

    sensor_count = 0
    valid_us_count = 0
    timeout_us_count = 0
    ts_list: list[int] = []
    dists: list[float] = []
    ir_true = 0
    ir_false = 0
    ir_transitions = 0
    prev_ir: bool | None = None
    pots: list[float] = []
    gesture_count = 0
    lcd_count = 0
    last_lcd_lines: tuple[str, ...] = ()

    t_start = time.monotonic()
    steps_done = 0

    while True:
        if simulated_steps is not None:
            if steps_done >= simulated_steps:
                break
        elif (time.monotonic() - t_start) >= duration_sec:
            break

        if step_callback is not None:
            step_callback()
            steps_done += 1

        lines = endpoint.read_all_lines()
        if not lines:
            if step_callback is None:
                time.sleep(0.005)
            continue

        for line in lines:
            if not line.strip():
                continue
            total_lines += 1
            try:
                env = codec.decode(line)
            except ProtocolError:
                parse_errors += 1
                continue

            if last_seq is not None and env.seq > (last_seq + 1):
                seq_gaps += env.seq - (last_seq + 1)
            last_seq = env.seq

            if env.type == MessageType.SENSOR_FRAME:
                try:
                    sf = SensorFramePayload.from_dict(env.data)
                except ProtocolError:
                    parse_errors += 1
                    continue
                sensor_count += 1
                ts_list.append(env.ts_ms)
                if sf.valid_ultrasonic and sf.distance_cm is not None:
                    valid_us_count += 1
                    dists.append(float(sf.distance_cm))
                else:
                    timeout_us_count += 1

                if sf.ir_detected:
                    ir_true += 1
                else:
                    ir_false += 1
                if prev_ir is not None and sf.ir_detected != prev_ir:
                    ir_transitions += 1
                prev_ir = sf.ir_detected
                pots.append(float(sf.pot_norm))

            elif env.type == MessageType.GESTURE_EVENT:
                gesture_count += 1
            elif env.type == MessageType.LCD_FRAME:
                try:
                    lf = LcdFramePayload.from_dict(env.data)
                    lcd_count += 1
                    last_lcd_lines = tuple(lf.lines)
                except ProtocolError:
                    parse_errors += 1

    elapsed_wall = max(0.001, time.monotonic() - t_start)
    dts = [ts_list[i + 1] - ts_list[i] for i in range(len(ts_list) - 1) if ts_list[i + 1] >= ts_list[i]]
    mean_dt = float(statistics.fmean(dts)) if dts else 0.0
    jitter_std = float(statistics.pstdev(dts)) if len(dts) >= 2 else 0.0
    eff_hz = (1000.0 / mean_dt) if mean_dt > 0.0 else 0.0
    timeout_ratio = (timeout_us_count / sensor_count) if sensor_count > 0 else 1.0

    period_tol_ms = max(15.0, expected_period_ms * 0.25)
    period_ok = (len(dts) > 0) and (abs(mean_dt - expected_period_ms) <= period_tol_ms)

    d_min = round(min(dists), 2) if dists else None
    d_max = round(max(dists), 2) if dists else None
    d_mean = round(float(statistics.fmean(dists)), 2) if dists else None
    d_std = round(float(statistics.pstdev(dists)), 2) if len(dists) >= 2 else (0.0 if dists else None)

    ref_err: float | None = None
    ref_ok: bool | None = None
    if reference_cm is not None:
        if d_mean is not None:
            ref_err = round(abs(d_mean - float(reference_cm)), 2)
            allowed = max(float(reference_tolerance_cm), float(reference_cm) * 0.12)
            ref_ok = ref_err <= allowed
        else:
            ref_ok = False

    p_min = round(min(pots), 4) if pots else None
    p_max = round(max(pots), 4) if pots else None
    p_span = round(p_max - p_min, 4) if (p_min is not None and p_max is not None) else None

    problems: list[str] = []
    if sensor_count < 3:
        problems.append(
            f"Quantidade insuficiente de quadros 'sensor_frame' recebidos ({sensor_count} < 3). "
            "Envie 'START' ou verifique conexoes."
        )
    if parse_errors > 0:
        problems.append(f"Detectados {parse_errors} erros de decodificacao JSON Lines v1 na serial.")
    if seq_gaps > 0:
        problems.append(f"Detectada perda de {seq_gaps} pacotes na sequencia monotônica ('seq').")
    if sensor_count >= 3 and not period_ok:
        problems.append(
            f"Periodo medio de amostragem ({mean_dt:.1f} ms / {eff_hz:.1f} Hz) diverge do alvo "
            f"esperado ({expected_period_ms} ms +/- {period_tol_ms:.0f} ms)."
        )
    if sensor_count > 0 and timeout_ratio > 0.35:
        problems.append(
            f"Taxa elevada de timeouts ultrassônicos ({timeout_ratio:.1%} > 35%). "
            "Verifique VCC=5V do HC-SR04, TRIG=GPIO5, divisor ECHO->GPIO34 e alvo frontal."
        )
    if reference_cm is not None and ref_ok is False:
        problems.append(
            f"Medicao ultrassônica ({d_mean} cm) divergiu da referencia fisica ({reference_cm} cm; "
            f"erro={ref_err} cm)."
        )

    sim_duration = (
        round((ts_list[-1] - ts_list[0]) / 1000.0, 3)
        if simulated_steps is not None and len(ts_list) >= 2
        else round(elapsed_wall, 3)
    )

    return TelemetryInspectionReport(
        validation_origin=validation_origin,
        duration_sec=sim_duration,
        expected_period_ms=expected_period_ms,
        total_lines_rx=total_lines,
        parse_errors=parse_errors,
        seq_gaps_detected=seq_gaps,
        sensor_frames_count=sensor_count,
        valid_ultrasonic_count=valid_us_count,
        ultrasonic_timeouts_count=timeout_us_count,
        timeout_ratio=round(timeout_ratio, 4),
        mean_dt_ms=round(mean_dt, 2),
        jitter_std_ms=round(jitter_std, 2),
        effective_hz=round(eff_hz, 2),
        period_within_tolerance=period_ok,
        distance_min_cm=d_min,
        distance_max_cm=d_max,
        distance_mean_cm=d_mean,
        distance_std_cm=d_std,
        reference_cm=reference_cm,
        reference_abs_error_cm=ref_err,
        reference_within_tolerance=ref_ok,
        ir_true_count=ir_true,
        ir_false_count=ir_false,
        ir_transitions=ir_transitions,
        pot_min=p_min,
        pot_max=p_max,
        pot_span=p_span,
        gesture_events_count=gesture_count,
        lcd_frames_count=lcd_count,
        last_lcd_lines=last_lcd_lines,
        passed=(len(problems) == 0),
        problems=tuple(problems),
    )


def record_bench_log_entry(
    action: str,
    validation_origin: str,
    passed: bool,
    payload: dict[str, Any],
    problems: tuple[str, ...] | list[str] = (),
    log_path: str | Path = DEFAULT_BENCH_LOG_PATH,
) -> Path:
    """Registra resultados e problemas de bancada em `data/reports/bench_validation_log.json`."""
    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, Any]] = []
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except json.JSONDecodeError:
            history = []

    history.append(
        {
            "timestamp_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
            "action": action,
            "validation_origin": validation_origin,
            "passed": bool(passed),
            "problems": list(problems),
            "payload": payload,
        }
    )
    target.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def format_safety_and_wiring_checklist() -> str:
    """Formata tabela canônica única de pinos e checklist passo a passo para iniciantes."""
    lines: list[str] = [
        "=" * 86,
        " MOTIONPET CICLO 5 — TABELA CANONICA UNICA DE PINAGEM E CHECKLIST DE SEGURANCA",
        "=" * 86,
        f"NOTA: {PINOUT_RECONCILIATION_NOTE}",
        "",
        "1. TABELA CANONICA DE CONEXOES (ESP-WROOM-32):",
        "-" * 86,
        f"{'Periferico':<16} | {'Sinal':<20} | {'Pino ESP32':<26} | {'Dominio Eletrico'}",
        "-" * 86,
    ]
    for row in CANONICAL_PINOUT_TABLE:
        lines.append(
            f"{row.peripheral:<16} | {row.signal:<20} | {row.esp32_pin:<26} | {row.supply_domain}"
        )
    lines.extend(
        [
            "-" * 86,
            "",
            "2. REGRAS CRITICAS DE SEGURANCA ELETRICA (LEIA ANTES DE LIGAR O CABO USB!):",
            "  [ ] REGRA 1 (DIVISOR ECHO <= 3,30 V): O ESP32 NAO tolera 5 V e 3,5 V NAO E SEGURO!",
            "      Monte R1 = 1 kOhm (ECHO -> no) e R2 = 1 kOhm + 300 Ohm em serie (no -> GND).",
            "      Meça o divisor estatico antes do GPIO34: ~2,83 V com entrada de 5 V. Isso nao mede o pico real.",
            "  [ ] REGRA 2 (LCD I2C): VCC=3V3, GND comum, SDA=GPIO21, SCL=GPIO22.",
            "      Sem conversor, nunca alimente o backpack em 5 V. Use so os 4 pinos do adaptador.",
            "  [ ] REGRA 3 (TCRT5000 EM 3,3 V): Alimente pelo 3V3 do ESP32, NUNCA em 5V/VIN.",
            "      O potenciometro de entrada nao faz parte da montagem atual.",
            "  [ ] REGRA 4 (TERRA COMUM): Interligue todos os GNDs em um unico barramento comum.",
            "  [ ] REGRA 5 (TESTE ANTI-CURTO): Com o USB desconectado, meca resistencia entre 5V-GND",
            "      e entre 3V3-GND; nenhum deles pode apitar curto-circuito (0 Ohm).",
            "  [ ] REGRA 6 (GRAVACAO MANUAL): Este assistente NUNCA energiza nem grava firmware",
            "      sozinho. Grave manualmente apenas quando autorizado na Etapa A.",
            "=" * 86,
        ]
    )
    return "\n".join(lines)


def _open_bench_session(
    serial_port: str | None,
    simulate: bool,
    baudrate: int = 115200,
    sim_distance_cm: float | None = None,
) -> tuple[SerialEndpoint, Callable[[], None] | None, str, Callable[[], None]]:
    """Abre sessão serial real ou simulada retornando `(endpoint, step_cb, origin_tag, cleanup_cb)`."""
    if serial_port and not simulate:
        ep = PySerialEndpoint(port=serial_port, baudrate=baudrate)
        return (ep, None, "PHYSICAL_ESP32", ep.close)

    host_ep, dev_ep, _ = create_virtual_serial_pair(max_wire_log=1000)
    sensor_sim = SensorSimulator(
        seed=42,
        sample_period_ms=70,
        dropout_prob=0.0,
        idle_distance_cm=float(sim_distance_cm) if sim_distance_cm is not None else 75.0,
    )
    node = SimulatedEsp32Node(endpoint=dev_ep, sensor_source=sensor_sim)
    node.boot(auto_load=False)

    def _cleanup() -> None:
        host_ep.close()
        dev_ep.close()

    return (host_ep, node.step, "SIMULATION", _cleanup)


def run_stage_a(
    serial_port: str | None = None,
    simulate: bool = False,
    baudrate: int = 115200,
    log_path: str | Path = DEFAULT_BENCH_LOG_PATH,
) -> StageValidationResult:
    """Etapa A — ESP32 isolado por USB (sem sensores/LCD): DIAG, JSON Lines v1, memória e versão."""
    origin = "SIMULATION" if (simulate or not serial_port) else "PHYSICAL_ESP32"
    if not simulate and not serial_port:
        ports = list_serial_ports()
        msg = (
            "Nenhuma porta --serial-port informada para Etapa A fisica. "
            f"Portas detectadas agora: {[p.device for p in ports] or 'NENHUMA'}. "
            "Conecte APENAS o ESP32 via cabo USB de dados, identifique a porta COM com "
            "'python -m terminal.bench ports', grave o firmware manualmente com "
            "'pio run -d firmware -t upload --upload-port COMx' e reexecute."
        )
        res = StageValidationResult(
            stage="A",
            validation_origin="PHYSICAL_ESP32",
            passed=False,
            halted_for_electrical_safety=False,
            summary=msg,
            problems=(msg,),
            next_manual_action="Conectar ESP32 isolado via USB e gravar firmware manualmente.",
        )
        record_bench_log_entry("STAGE_A", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    ep, step_cb, origin_tag, cleanup = _open_bench_session(serial_port, simulate, baudrate)
    try:
        diag = query_device_diag(ep, step_callback=step_cb)
        stream = inspect_telemetry_stream(
            ep,
            duration_sec=1.5,
            expected_period_ms=diag.sample_period_ms,
            validation_origin=origin_tag,
            step_callback=step_cb,
            simulated_steps=15 if step_cb is not None else None,
        )
    except Exception as exc:
        cleanup()
        prob = f"Falha de comunicacao na Etapa A ({origin_tag}): {exc}"
        res = StageValidationResult(
            stage="A",
            validation_origin=origin_tag,
            passed=False,
            halted_for_electrical_safety=False,
            summary=prob,
            problems=(prob,),
            next_manual_action="Verificar cabo USB, driver CP210x/CH340 e gravacao manual do firmware.",
        )
        record_bench_log_entry("STAGE_A", origin_tag, False, res.to_dict(), res.problems, log_path)
        return res
    finally:
        cleanup()

    # Na Etapa A (ESP32 isolado), timeouts ultrassônicos são esperados caso o HC-SR04 esteja desconectado!
    non_us_problems = tuple(
        p for p in stream.problems if "timeouts ultrassônicos" not in p
    )
    problems_list = list(non_us_problems)
    if diag.free_heap_bytes < 32768:
        problems_list.append(f"Memoria heap livre critica no ESP32 ({diag.free_heap_bytes} B < 32 KiB).")

    passed = len(problems_list) == 0 and stream.sensor_frames_count >= 3
    summary = (
        f"Etapa A ({origin_tag}) {'APROVADA' if passed else 'REPROVADA'}: "
        f"fw={diag.fw_version}, origin={diag.origin}, heap={diag.free_heap_bytes} B, "
        f"quadros_jsonl={stream.sensor_frames_count}, freq={stream.effective_hz:.1f} Hz."
    )
    res = StageValidationResult(
        stage="A",
        validation_origin=origin_tag,
        passed=passed,
        halted_for_electrical_safety=False,
        summary=summary,
        details={"diag": diag.to_dict(), "telemetry": stream.to_dict()},
        problems=tuple(problems_list),
        next_manual_action=(
            "Desconectar o USB antes de montar o HC-SR04 e o divisor 1k/(1k+300 Ohm) da Etapa B."
            if passed
            else "Corrigir comunicacao serial/firmware antes de conectar qualquer periferico."
        ),
    )
    record_bench_log_entry("STAGE_A", origin_tag, passed, res.to_dict(), res.problems, log_path)
    return res


def run_stage_b(
    serial_port: str | None = None,
    simulate: bool = False,
    baudrate: int = 115200,
    r1_ohm: float = PREFERRED_ECHO_R1_OHM,
    r2_ohm: float = PREFERRED_ECHO_R2_OHM,
    measured_echo_v: float | None = None,
    reference_cm: float | None = None,
    log_path: str | Path = DEFAULT_BENCH_LOG_PATH,
) -> StageValidationResult:
    """Etapa B — HC-SR04 com barreira elétrica obrigatória no divisor do ECHO (`<= 3,30 V`)."""
    origin_tag = "SIMULATION" if simulate else "PHYSICAL_ESP32"
    divider: EchoDividerAssessment = evaluate_echo_divider(
        r1_ohm=r1_ohm,
        r2_ohm=r2_ohm,
        measured_peak_v=measured_echo_v,
    )

    if not divider.safe:
        msg = (
            "BLOQUEIO DE SEGURANCA ELETRICA NA ETAPA B! Divisor do ECHO reprovado: "
            + " | ".join(divider.reasons)
        )
        res = StageValidationResult(
            stage="B",
            validation_origin=origin_tag,
            passed=False,
            halted_for_electrical_safety=True,
            summary=msg,
            details={"divider": divider.to_dict()},
            problems=divider.reasons,
            next_manual_action=(
                "NUNCA conecte o ECHO ao GPIO34! Confira R1=1 kOhm e R2=1 kOhm + 300 Ohm em serie e "
                "confirme tensao <= 3,30 V no multimetro."
            ),
        )
        record_bench_log_entry("STAGE_B", origin_tag, False, res.to_dict(), res.problems, log_path)
        return res

    if not simulate and measured_echo_v is None:
        msg = (
            "Medicao previa obrigatoria ausente: meca a tensao de saida do divisor R1/R2 com "
            "multimetro ANTES de ligar ao GPIO34 e informe '--measured-echo-v <tensao>' "
            f"(deve estar entre 2,50 V e {ESP32_GPIO_MAX_SAFE_V:.2f} V)."
        )
        res = StageValidationResult(
            stage="B",
            validation_origin="PHYSICAL_ESP32",
            passed=False,
            halted_for_electrical_safety=True,
            summary=msg,
            details={"divider": divider.to_dict()},
            problems=(msg,),
            next_manual_action="Medir tensao no no R1/R2 desconectado do GPIO34 e passar --measured-echo-v.",
        )
        record_bench_log_entry("STAGE_B", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    if not simulate and not serial_port:
        msg = "Informe --serial-port COMx para validar o HC-SR04 fisico (ou --simulate)."
        res = StageValidationResult(
            stage="B",
            validation_origin="PHYSICAL_ESP32",
            passed=False,
            halted_for_electrical_safety=False,
            summary=msg,
            details={"divider": divider.to_dict()},
            problems=(msg,),
            next_manual_action="Conectar ECHO ao GPIO34 (apos divisor aprovado) e informar --serial-port.",
        )
        record_bench_log_entry("STAGE_B", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    ep, step_cb, actual_origin, cleanup = _open_bench_session(
        serial_port,
        simulate,
        baudrate,
        sim_distance_cm=reference_cm,
    )
    try:
        diag = query_device_diag(ep, step_callback=step_cb)
        stream = inspect_telemetry_stream(
            ep,
            duration_sec=2.5,
            expected_period_ms=diag.sample_period_ms,
            reference_cm=reference_cm,
            validation_origin=actual_origin,
            step_callback=step_cb,
            simulated_steps=20 if step_cb is not None else None,
        )
    finally:
        cleanup()

    passed = stream.passed and stream.valid_ultrasonic_count >= 3
    probs = list(stream.problems)
    if stream.valid_ultrasonic_count < 3:
        probs.append("Menos de 3 leituras ultrassônicas validas obtidas na Etapa B.")

    ref_txt = (
        f", ref={reference_cm} cm (medido={stream.distance_mean_cm} cm, erro={stream.reference_abs_error_cm} cm)"
        if reference_cm is not None
        else f", media={stream.distance_mean_cm} cm"
    )
    summary = (
        f"Etapa B ({actual_origin}) {'APROVADA' if passed else 'REPROVADA'}: "
        f"divisor R1={r1_ohm:.0f}/R2={r2_ohm:.0f} (Vmax={divider.vout_max_v:.2f} V <= 3.30 V), "
        f"validas={stream.valid_ultrasonic_count}/{stream.sensor_frames_count}, "
        f"timeouts={stream.timeout_ratio:.1%}, freq={stream.effective_hz:.1f} Hz{ref_txt}."
    )
    res = StageValidationResult(
        stage="B",
        validation_origin=actual_origin,
        passed=passed,
        halted_for_electrical_safety=False,
        summary=summary,
        details={"divider": divider.to_dict(), "diag": diag.to_dict(), "telemetry": stream.to_dict()},
        problems=tuple(probs),
        next_manual_action=(
            "HC-SR04 validado! Desconecte o USB antes de adicionar o TCRT5000 (3,3 V) na Etapa C."
            if passed
            else "Revisar fiação TRIG=GPIO5, divisor ECHO->GPIO34 e alimentacao 5 V do HC-SR04."
        ),
    )
    record_bench_log_entry("STAGE_B", actual_origin, passed, res.to_dict(), res.problems, log_path)
    return res


def run_stage_c(
    serial_port: str | None = None,
    simulate: bool = False,
    baudrate: int = 115200,
    component: str = "ir",  # "ir" | "pot" | "both"; potenciometro desativado na montagem atual
    vcc_measured_v: float | None = None,
    log_path: str | Path = DEFAULT_BENCH_LOG_PATH,
) -> StageValidationResult:
    """Etapa C — Validação individual e conjunta do TCRT5000 e Potenciômetro (estritamente 3,3 V)."""
    origin_tag = "SIMULATION" if simulate else "PHYSICAL_ESP32"
    comp = component.strip().lower()
    if comp not in ("ir", "pot", "both"):
        raise ValueError("Parametro 'component' invalido na Etapa C (use 'ir', 'pot' ou 'both').")

    if vcc_measured_v is not None and (not math.isfinite(vcc_measured_v) or vcc_measured_v > 3.45 or vcc_measured_v < 3.05):
        msg = (
            f"BLOQUEIO ELETRICO NA ETAPA C: Tensao de alimentacao medida ({vcc_measured_v:.2f} V) "
            "fora da faixa segura de 3,3 V (3,05..3,45 V)! TCRT5000 e potenciometro NUNCA "
            "podem ser ligados em 5 V."
        )
        res = StageValidationResult(
            stage=f"C({comp.upper()})",
            validation_origin=origin_tag,
            passed=False,
            halted_for_electrical_safety=True,
            summary=msg,
            problems=(msg,),
            next_manual_action="Mover alimentacao do TCRT5000 e potenciometro para o pino 3V3 do ESP32.",
        )
        record_bench_log_entry("STAGE_C", origin_tag, False, res.to_dict(), res.problems, log_path)
        return res

    if not simulate and not serial_port:
        msg = "Informe --serial-port COMx para validar Etapa C no hardware (ou --simulate)."
        res = StageValidationResult(
            stage=f"C({comp.upper()})",
            validation_origin="PHYSICAL_ESP32",
            passed=False,
            halted_for_electrical_safety=False,
            summary=msg,
            problems=(msg,),
            next_manual_action="Conectar periférico em 3V3 e informar --serial-port COMx.",
        )
        record_bench_log_entry("STAGE_C", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    if not simulate and vcc_measured_v is None:
        msg = "Medicao da alimentacao 3V3 ausente: informe --vcc-measured-v antes da validacao fisica."
        res = StageValidationResult(
            stage=f"C({comp.upper()})", validation_origin="PHYSICAL_ESP32", passed=False,
            halted_for_electrical_safety=True, summary=msg, problems=(msg,),
            next_manual_action="Medir a alimentacao do modulo com multimetro e informar o valor medido.",
        )
        record_bench_log_entry("STAGE_C", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    ep, step_cb, actual_origin, cleanup = _open_bench_session(serial_port, simulate, baudrate)
    try:
        # Se estiver validando apenas o potenciômetro primeiro, desativa IR temporariamente
        if comp == "pot":
            ep.write_line("IR OFF")
        else:
            ep.write_line("IR ON")
        if step_cb is not None:
            step_cb()
        ep.read_all_lines()

        stream = inspect_telemetry_stream(
            ep,
            duration_sec=2.5 if simulate else 8.0,
            expected_period_ms=70,
            validation_origin=actual_origin,
            step_callback=step_cb,
            simulated_steps=20 if step_cb is not None else None,
        )
    finally:
        cleanup()

    probs = list(stream.problems)
    if comp in ("pot", "both"):
        if stream.pot_min is None or stream.pot_max is None or not (0.0 <= stream.pot_min <= 1.0 and 0.0 <= stream.pot_max <= 1.0):
            probs.append("Leituras 'pot_norm' ausentes ou fora do intervalo normalizado [0.0, 1.0].")
        elif not simulate and (stream.pot_span is None or stream.pot_span < 0.10):
            probs.append("Nao houve variacao suficiente do potenciometro. Gire-o durante a captura; o firmware atual deixa esse canal desativado por padrao.")
    if not simulate and comp in ("ir", "both") and (
        stream.ir_true_count == 0 or stream.ir_false_count == 0 or stream.ir_transitions == 0
    ):
        probs.append("IR sem transicao observada: aproxime e afaste um objeto durante a captura e confira o sinal DO.")
    if comp == "pot" and stream.ir_true_count > 0:
        probs.append("Canal IR permaneceu ativo durante teste isolado do potenciometro ('IR OFF').")

    passed = len(probs) == 0 and stream.sensor_frames_count >= 3
    summary = (
        f"Etapa C [{comp.upper()}] ({actual_origin}) {'APROVADA' if passed else 'REPROVADA'}: "
        f"ir_true={stream.ir_true_count}, ir_false={stream.ir_false_count}, "
        f"transicoes_ir={stream.ir_transitions}, pot=[{stream.pot_min}..{stream.pot_max}]."
    )
    res = StageValidationResult(
        stage=f"C({comp.upper()})",
        validation_origin=actual_origin,
        passed=passed,
        halted_for_electrical_safety=False,
        summary=summary,
        details={"component": comp, "telemetry": stream.to_dict()},
        problems=tuple(probs),
        next_manual_action=(
            "Telemetria do componente respondeu durante a captura. Prossiga para a verificacao manual do LCD na Etapa D."
            if passed
            else "Confira 3V3 e DO=GPIO35; estimule o IR durante a captura. Se usar potenciometro, habilite seu canal e gire-o."
        ),
    )
    record_bench_log_entry("STAGE_C", actual_origin, passed, res.to_dict(), res.problems, log_path)
    return res


def run_stage_d(
    serial_port: str | None = None,
    simulate: bool = False,
    baudrate: int = 115200,
    rw_grounded: bool = True,
    lcd_vdd_v: float | None = None,
    rw_confirmed: bool = False,
    visual_confirmed: bool = False,
    log_path: str | Path = DEFAULT_BENCH_LOG_PATH,
    lcd_interface: str = "i2c",
    i2c_wiring_confirmed: bool = False,
) -> StageValidationResult:
    """Etapa D: quadro serial observado e confirmações físicas fornecidas pelo operador."""
    origin_tag = "SIMULATION" if simulate else "PHYSICAL_ESP32"
    if lcd_interface not in ("i2c", "parallel"):
        raise ValueError("lcd_interface deve ser i2c ou parallel")
    if lcd_interface == "parallel" and not rw_grounded:
        msg = (
            "BLOQUEIO ELETRICO NA ETAPA D: O pino 5 (RW) do LCD 2004A NAO esta aterrado em GND! "
            "Risco critico de injecao de 5 V nos barramentos GPIO21, 22, 23 e 27."
        )
        res = StageValidationResult(
            stage="D",
            validation_origin=origin_tag,
            passed=False,
            halted_for_electrical_safety=True,
            summary=msg,
            problems=(msg,),
            next_manual_action="Aterrar permanentemente o pino 5 (RW) do LCD em GND e confirmar 0 Ohm.",
        )
        record_bench_log_entry("STAGE_D", origin_tag, False, res.to_dict(), res.problems, log_path)
        return res

    vmin, vmax = (3.0, 3.35) if lcd_interface == "i2c" else (4.75, 5.25)
    if lcd_vdd_v is not None and (not math.isfinite(lcd_vdd_v) or not vmin <= lcd_vdd_v <= vmax):
        msg = (
            f"BLOQUEIO ELETRICO NA ETAPA D: VDD informado fora da faixa de verificacao "
            f"do perfil {lcd_interface} ({lcd_vdd_v:.2f} V; {vmin:.2f}..{vmax:.2f} V). "
            "No perfil I2C direto, VCC deve vir do 3V3, nunca de 5 V."
        )
        res = StageValidationResult(
            stage="D",
            validation_origin=origin_tag,
            passed=False,
            halted_for_electrical_safety=True,
            summary=msg,
            problems=(msg,),
            next_manual_action="Revisar VCC e GND conforme o perfil do LCD e o guia de montagem atual.",
        )
        record_bench_log_entry("STAGE_D", origin_tag, False, res.to_dict(), res.problems, log_path)
        return res

    if not simulate and not serial_port:
        msg = "Informe --serial-port COMx para inspecionar os quadros do LCD fisico (ou --simulate)."
        res = StageValidationResult(
            stage="D",
            validation_origin="PHYSICAL_ESP32",
            passed=False,
            halted_for_electrical_safety=False,
            summary=msg,
            problems=(msg,),
            next_manual_action="Conectar LCD conforme o guia atual e executar Etapa D com --serial-port COMx.",
        )
        record_bench_log_entry("STAGE_D", "PHYSICAL_ESP32", False, res.to_dict(), res.problems, log_path)
        return res

    ep, step_cb, actual_origin, cleanup = _open_bench_session(serial_port, simulate, baudrate)
    try:
        diag = query_device_diag(ep, step_callback=step_cb)
        stream = inspect_telemetry_stream(
            ep,
            duration_sec=2.2,
            expected_period_ms=diag.sample_period_ms,
            validation_origin=actual_origin,
            step_callback=step_cb,
            simulated_steps=16 if step_cb is not None else None,
        )
    finally:
        cleanup()

    probs = list(stream.problems)
    device_lines = stream.last_lcd_lines
    geometry_ok = stream.lcd_frames_count > 0 and len(device_lines) == 4 and all(len(ln) == 20 for ln in device_lines)
    if stream.lcd_frames_count <= 0:
        probs.append("Nenhum quadro LCD foi recebido pela serial; o contador de renderizacao nao comprova o conteudo.")
    elif not geometry_ok:
        probs.append("Geometria de quadro LCD invalida (esperadas exatas 4 linhas x 20 colunas).")

    if not simulate:
        if lcd_interface == "parallel" and not rw_confirmed:
            probs.append("Continuidade de RW ate GND nao confirmada pelo operador.")
        if lcd_interface == "i2c" and not i2c_wiring_confirmed:
            probs.append("VCC=3V3, GND comum, SDA=21 e SCL=22 nao confirmados pelo operador.")
        if lcd_vdd_v is None:
            probs.append("Tensao VDD do LCD nao informada pelo operador.")
        if not visual_confirmed:
            probs.append("Comparacao visual do LCD fisico com o quadro serial nao confirmada pelo operador.")

    passed = len(probs) == 0 and geometry_ok
    summary = (
        f"Etapa D ({actual_origin}) {'APROVADA' if passed else 'REPROVADA'}: "
        f"lcd_f={diag.lcd_frames}, quadro_serial_20x4={geometry_ok}. "
        + ("Confirmacoes eletricas e visuais sao informadas pelo operador."
           if not simulate else "Simulacao nao verifica o LCD fisico.")
    )
    res = StageValidationResult(
        stage="D",
        validation_origin=actual_origin,
        passed=passed,
        halted_for_electrical_safety=False,
        summary=summary,
        details={
            "diag": diag.to_dict(),
            "lcd_interface": lcd_interface,
            "device_lcd_20x4": list(device_lines),
            "rw_confirmed_by_operator": bool(rw_confirmed) if not simulate and lcd_interface == "parallel" else None,
            "i2c_wiring_confirmed_by_operator": bool(i2c_wiring_confirmed) if not simulate and lcd_interface == "i2c" else None,
            "lcd_vdd_v_reported": lcd_vdd_v if not simulate else None,
            "visual_confirmed_by_operator": bool(visual_confirmed) if not simulate else None,
        },
        problems=tuple(probs),
        next_manual_action=(
            "Etapa D simulada; realize as verificacoes fisicas antes de prosseguir."
            if passed and simulate else
            "Etapa D concluida conforme os dados e confirmacoes fornecidos pelo operador."
            if passed else
            "Confira VCC, GND, sinais e o quadro recebido; compare-o com o LCD fisico e informe as confirmacoes."
        ),
    )
    record_bench_log_entry("STAGE_D", actual_origin, passed, res.to_dict(), res.problems, log_path)
    return res
