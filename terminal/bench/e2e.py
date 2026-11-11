"""Validador Ponta a Ponta (Seção 7): Gestos -> Inferência -> Serial JSONL -> Pet Launch + LCD + Save."""

from __future__ import annotations

import datetime as dt
import json
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ml.classifiers import create_gesture_classifier
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.communication.protocol import (
    AppModeId,
    CommandType,
    GestureEventPayload,
    GestureType,
    LcdFramePayload,
    MessageType,
    PetCommandPayload,
    ProtocolCodec,
    ProtocolError,
    SensorFramePayload,
)
from terminal.communication.transport import (
    PySerialEndpoint,
    create_virtual_serial_pair,
)
from terminal.games.launch_renderer import PetLaunchAsciiRenderer
from terminal.games.pet_launch import LaunchPhase, PetLaunchGame
from terminal.pet.persistence import PetPersistence
from terminal.pet.state import PetState
from terminal.renderer.ascii_terminal import HudTelemetry
from terminal.renderer.lcd20x4 import Lcd20x4Renderer

DEFAULT_E2E_REPORT_PATH = Path("data/reports/e2e_validation_report.json")


@dataclass(frozen=True)
class E2EValidationReport:
    """Relatório consolidado do teste ponta a ponta (Gestos -> Serial -> Pet Launch -> LCD -> Save)."""

    generated_at_iso: str
    validation_origin: str  # "PHYSICAL_ESP32" | "SIMULATION"
    classifier_kind: str
    # None significa que o critério não foi verificado, não que tenha falhado.
    checks: dict[str, bool | None]
    all_passed: bool
    matches_completed: int
    best_distance_m: float
    coins_after_match: int | None
    xp_after_match: int | None
    mean_e2e_latency_ms: float | None
    p95_e2e_latency_ms: float | None
    duplicate_events_blocked: bool | None
    involuntary_noise_rejected: bool | None
    lcd_terminal_synced: bool | None
    persistence_verified: bool | None
    problems: tuple[str, ...]
    # Estes tempos medem apenas processamento local, não a latência sensor-resposta.
    mean_processing_ms: float | None = None
    p95_processing_ms: float | None = None
    processing_time_scope: str | None = None
    observations: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _save_e2e_report(report: E2EValidationReport, report_path: str | Path) -> Path:
    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def run_pet_launch_e2e_validation(
    serial_port: str | None = None,
    simulate: bool = True,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
    physical_listen_sec: float = 15.0,
    report_path: str | Path = DEFAULT_E2E_REPORT_PATH,
) -> E2EValidationReport:
    """Executa bateria ponta a ponta do Pet Launch respondendo a gestos na serial JSON Lines v1.

    Em modo `--simulate`, exercita deterministicamente todos os 8 requisitos da Seção 7 através do
    link serial virtual completo (`SensorSimulator` -> `SimulatedEsp32Node` -> `ProtocolCodec` ->
    `PetLaunchGame` + `Lcd20x4Renderer` + `PetLaunchAsciiRenderer` + `PetPersistence`), marcando
    honestamente `validation_origin="SIMULATION"`.
    Quando conectado a `--serial-port COMx` (`simulate=False`), consome pacotes reais do ESP32.
    """
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    if serial_port and not simulate:
        return _run_physical_serial_e2e(
            serial_port=serial_port,
            listen_sec=physical_listen_sec,
            report_path=report_path,
            now_iso=now_iso,
        )
    if not simulate:
        raise ValueError("Informe uma porta serial para executar a validação física.")

    codec = ProtocolCodec()
    lcd_renderer = Lcd20x4Renderer()
    ascii_renderer = PetLaunchAsciiRenderer()

    with tempfile.TemporaryDirectory(prefix="motionpet_e2e_save_") as tmp_dir:
        save_file = Path(tmp_dir) / "e2e_pet_state.save.json"
        host_ep, dev_ep, _ = create_virtual_serial_pair(max_wire_log=2000)
        sensor_sim = SensorSimulator(seed=105, sample_period_ms=60, noise_std_cm=0.35, dropout_prob=0.0)
        clf = create_gesture_classifier(kind=classifier_kind, model_path=model_path)
        # Se `ml` foi pedido mas nenhum `.joblib` está salvo ainda, faz fallback controlado p/ `sim`
        eff_clf_kind = classifier_kind
        if classifier_kind == "ml" and not getattr(clf, "is_loaded", False):
            clf = create_gesture_classifier(kind="sim")
            eff_clf_kind = "sim(fallback_no_joblib)"

        node = SimulatedEsp32Node(
            endpoint=dev_ep,
            sensor_source=sensor_sim,
            save_path=save_file,
            classifier=clf,
        )
        node.boot(auto_load=False)
        host_ep.read_all_lines()

        # Coloca o nó em modo PET_LAUNCH via comando serial real
        sw_cmd = PetCommandPayload(command=CommandType.SWITCH_MODE, payload={"mode": "PET_LAUNCH"})
        host_ep.write_line(codec.encode(MessageType.PET_COMMAND, sw_cmd.to_dict()))
        node.step()
        host_ep.read_all_lines()

        game = PetLaunchGame(flight_time_scale=2.5)
        pet_state = PetState.from_dict(node.engine.state.to_dict())
        latencies_ms: list[float] = []

        def _pump_gesture_profile(
            g_type: GestureType,
            repeats: int = 1,
            steps: int = 12,
            idle_after: int = 10,
        ) -> list[GestureEventPayload]:
            for _ in range(max(1, repeats)):
                sensor_sim.queue_gesture_profile(g_type)
            emitted: list[GestureEventPayload] = []
            for _ in range(steps):
                t0 = time.perf_counter()
                node.step()
                for line in host_ep.read_all_lines():
                    env = codec.decode(line)
                    if env.type == MessageType.SENSOR_FRAME:
                        sf = SensorFramePayload.from_dict(env.data)
                        game.on_sensor_frame(sf)
                    elif env.type == MessageType.GESTURE_EVENT:
                        ge = GestureEventPayload.from_dict(env.data)
                        game.handle_gesture(ge, pet_state, seq_id=env.seq, ts_ms=env.ts_ms)
                        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
                        emitted.append(ge)
                    elif env.type == MessageType.PET_STATE:
                        pet_state_new = PetState.from_dict(env.data)
                        pet_state.__dict__.update(pet_state_new.__dict__)
            for _ in range(max(0, idle_after)):
                node.step()
                for line in host_ep.read_all_lines():
                    env = codec.decode(line)
                    if env.type == MessageType.SENSOR_FRAME:
                        game.on_sensor_frame(SensorFramePayload.from_dict(env.data))
            return emitted

        # 1. Rejeição de movimentos involuntários / repouso NEUTRAL no MENU
        evts_neutral = _pump_gesture_profile(GestureType.NEUTRAL, steps=16, idle_after=4)
        involuntary_rejected = (len(evts_neutral) == 0) and (game.phase == LaunchPhase.MENU)

        # 2. Cooldown e prevenção de eventos duplicados dentro de um único perfil contínuo
        evts_approach_1 = _pump_gesture_profile(GestureType.APPROACH, steps=10, idle_after=10)
        dedup_cooldown_ok = len(evts_approach_1) == 1
        approach_select_ok = game.phase == LaunchPhase.SELECT_PET

        # Verifica também bloqueio de pacote duplicado com mesmo seq_id no LaunchInputAdapter
        if evts_approach_1:
            phase_before_dup = game.phase
            game.handle_gesture(evts_approach_1[0], pet_state, seq_id=777777, ts_ms=1000)
            phase_after_first = game.phase
            game.handle_gesture(evts_approach_1[0], pet_state, seq_id=777777, ts_ms=1000)
            dedup_seq_ok = (phase_before_dup == LaunchPhase.SELECT_PET) and (
                phase_after_first == LaunchPhase.PREP
            ) and (game.phase == LaunchPhase.PREP)
        else:
            dedup_seq_ok = False
        dedup_ok = dedup_cooldown_ok and dedup_seq_ok

        # Já estamos em PREP (confirmado pelo APPROACH único acima); se necessário, garante PREP:
        approach_confirm_ok = game.phase == LaunchPhase.PREP

        # 3. Aproxima mão sem retornar a 75 cm e sustenta HOLD contínuo carregando força:
        # Primeiro traz a mão para perto (~18 cm) e mantém estacionária por 3 blocos contínuos
        _pump_gesture_profile(GestureType.HOLD, repeats=3, steps=28, idle_after=0)
        hold_events_ok = game.phase == LaunchPhase.CHARGING and game.charge_norm > 0.20
        charge_mid = game.charge_norm
        _pump_gesture_profile(GestureType.HOLD, repeats=1, steps=10, idle_after=0)
        hold_charge_ok = hold_events_ok and (game.charge_norm > charge_mid)

        # 4. RETREAT a partir da posição próxima (~18 cm -> 44 cm) cancelando o carregamento!
        _pump_gesture_profile(GestureType.RETREAT, repeats=1, steps=10, idle_after=0)
        retreat_cancel_ok = (game.phase == LaunchPhase.PREP) and (game.charge_norm == 0.0)

        # 5. Carrega novamente com HOLD contínuo e dispara com APPROACH (PREP -> CHARGING -> FLIGHT -> RESULT)
        _pump_gesture_profile(GestureType.HOLD, repeats=3, steps=28, idle_after=8)

        # Verifica sincronização LCD 20x4 + Terminal ASCII durante CHARGING
        lcd_charging = lcd_renderer.render_launch(
            state=pet_state,
            phase=game.phase.value,
            angle_deg=game.angle_deg,
            charge_norm=game.charge_norm,
            best_distance_m=game.best_distance_m,
            sweet_spot=game.is_in_sweet_spot(),
            frame_idx=1,
        )
        term_charging = ascii_renderer.render(
            game=game,
            state=pet_state,
            lcd_frame=lcd_charging,
            frame_idx=1,
            telemetry=HudTelemetry(mode=AppModeId.PET_LAUNCH),
        )
        sync_charging_ok = (
            len(lcd_charging.lines) == 4
            and all(len(ln) == 20 for ln in lcd_charging.lines)
            and ("FORCA" in "\n".join(lcd_charging.lines) or "PWR" in "\n".join(lcd_charging.lines) or "%" in "\n".join(lcd_charging.lines))
            and lcd_charging.lines[0].strip() in term_charging
        )

        _pump_gesture_profile(GestureType.APPROACH, steps=12)
        # Avança física até pouso completo (`RESULT`)
        for _ in range(250):
            if game.phase == LaunchPhase.RESULT:
                break
            game.update(0.05, pet_state)

        full_match_ok = (
            game.phase == LaunchPhase.RESULT
            and game.matches_completed == 1
            and game.last_result is not None
            and game.last_result.distance_m > 0.0
        )

        # Sincroniza recompensas da partida com o nó autoritativo via protocolo serial JSONL
        for cmd_dict in game.pop_pending_pet_commands():
            pcmd = PetCommandPayload(command=CommandType.PLAY, payload=cmd_dict)
            host_ep.write_line(codec.encode(MessageType.PET_COMMAND, pcmd.to_dict()))
        save_cmd = PetCommandPayload(command=CommandType.SAVE)
        host_ep.write_line(codec.encode(MessageType.PET_COMMAND, save_cmd.to_dict()))
        node.step()
        for line in host_ep.read_all_lines():
            env = codec.decode(line)
            if env.type == MessageType.PET_STATE:
                updated = PetState.from_dict(env.data)
                pet_state.__dict__.update(updated.__dict__)

        lcd_result = lcd_renderer.render_launch(
            state=pet_state,
            phase=game.phase.value,
            angle_deg=game.angle_deg,
            charge_norm=game.charge_norm,
            last_result=game.last_result,
            best_distance_m=game.best_distance_m,
            frame_idx=2,
        )
        term_result = ascii_renderer.render(
            game=game,
            state=pet_state,
            lcd_frame=lcd_result,
            frame_idx=2,
            telemetry=HudTelemetry(mode=AppModeId.PET_LAUNCH),
        )
        lcd_terminal_synced = sync_charging_ok and (lcd_result.lines[0].strip() in term_result)

        # 6. Verifica persistência real em disco
        reloaded = PetPersistence(save_file).load()
        persistence_ok = (
            save_file.is_file()
            and reloaded.total_launches == 1
            and reloaded.best_launch_distance_m > 0.0
            and reloaded.coins > 0
            and reloaded.xp > 0
        )

        host_ep.close()
        dev_ep.close()

    checks = {
        "hold_charging_force": hold_charge_ok,
        "approach_select_confirm_and_launch": (approach_select_ok and approach_confirm_ok and full_match_ok),
        "retreat_canceling": retreat_cancel_ok,
        "involuntary_movement_rejection": involuntary_rejected,
        "cooldown_and_duplicate_prevention": dedup_ok,
        "lcd_and_terminal_sync": lcd_terminal_synced,
        "complete_match_loop": full_match_ok,
        "progress_persistence": persistence_ok,
    }
    problems = tuple(f"Falha no criterio E2E: {k}" for k, ok in checks.items() if not ok)
    mean_lat = round(float(statistics.fmean(latencies_ms)), 3) if latencies_ms else 0.0
    p95_lat = round(float(sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]), 3) if latencies_ms else 0.0

    rep = E2EValidationReport(
        generated_at_iso=now_iso,
        validation_origin="SIMULATION",
        classifier_kind=eff_clf_kind,
        checks=checks,
        all_passed=all(checks.values()),
        matches_completed=game.matches_completed,
        best_distance_m=round(reloaded.best_launch_distance_m if persistence_ok else 0.0, 2),
        coins_after_match=int(reloaded.coins if persistence_ok else 0),
        xp_after_match=int(reloaded.xp if persistence_ok else 0),
        mean_e2e_latency_ms=None,
        p95_e2e_latency_ms=None,
        duplicate_events_blocked=dedup_ok,
        involuntary_noise_rejected=involuntary_rejected,
        lcd_terminal_synced=lcd_terminal_synced,
        persistence_verified=persistence_ok,
        problems=problems,
        mean_processing_ms=mean_lat if latencies_ms else None,
        p95_processing_ms=p95_lat if latencies_ms else None,
        processing_time_scope="passo do simulador e processamento local do evento no host",
    )
    _save_e2e_report(rep, report_path)
    return rep


def _run_physical_serial_e2e(
    serial_port: str,
    listen_sec: float,
    report_path: str | Path,
    now_iso: str,
) -> E2EValidationReport:
    """Executa sessão E2E conectada a um ESP32 físico real na porta COM informada."""
    codec = ProtocolCodec()
    game = PetLaunchGame(flight_time_scale=1.5)
    pet_state = PetState()
    seen_gestures: set[str] = set()
    latencies_ms: list[float] = []
    duplicates_seen = 0
    last_gesture_ts: dict[str, int] = {}
    lcd_seen = False

    ep = PySerialEndpoint(port=serial_port, baudrate=115200)
    try:
        sw_cmd = PetCommandPayload(command=CommandType.SWITCH_MODE, payload={"mode": "PET_LAUNCH"})
        ep.write_line(codec.encode(MessageType.PET_COMMAND, sw_cmd.to_dict()))
        t_end = time.monotonic() + max(3.0, listen_sec)
        last_tick = time.monotonic()

        while time.monotonic() < t_end:
            now_m = time.monotonic()
            dt_s = now_m - last_tick
            last_tick = now_m
            game.update(dt_s, pet_state)

            lines = ep.read_all_lines()
            if not lines:
                time.sleep(0.01)
                continue

            for line in lines:
                t0 = time.perf_counter()
                try:
                    env = codec.decode(line)
                except ProtocolError:
                    continue
                if env.type == MessageType.SENSOR_FRAME:
                    game.on_sensor_frame(SensorFramePayload.from_dict(env.data))
                elif env.type == MessageType.GESTURE_EVENT:
                    ge = GestureEventPayload.from_dict(env.data)
                    g_name = ge.gesture.value
                    seen_gestures.add(g_name)
                    prev_ts = last_gesture_ts.get(g_name, -999999)
                    if (env.ts_ms - prev_ts) < 350:
                        duplicates_seen += 1
                    last_gesture_ts[g_name] = env.ts_ms
                    game.handle_gesture(ge, pet_state)
                    latencies_ms.append((time.perf_counter() - t0) * 1000.0)
                elif env.type == MessageType.LCD_FRAME:
                    lf = LcdFramePayload.from_dict(env.data)
                    lcd_seen = len(lf.lines) == 4 and all(len(x) == 20 for x in lf.lines)
    finally:
        ep.close()

    # A presença de um evento ou quadro não demonstra o efeito correspondente.
    # Persistência exigiria salvar, reiniciar e reler; LCD exige comparação visual
    # com o display físico; rejeição/cooldown exigem estímulos de referência.
    checks = {
        "hold_charging_force": None,
        "approach_select_confirm_and_launch": None,
        "retreat_canceling": None,
        "involuntary_movement_rejection": None,
        "cooldown_and_duplicate_prevention": None,
        "lcd_and_terminal_sync": None,
        "complete_match_loop": None,
        "progress_persistence": None,
    }
    problems = tuple(
        f"Nao verificado na sessao fisica ({serial_port}): {k}"
        for k, ok in checks.items()
        if not ok
    )
    mean_lat = round(float(statistics.fmean(latencies_ms)), 3) if latencies_ms else 0.0
    p95_lat = round(float(sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]), 3) if latencies_ms else 0.0

    rep = E2EValidationReport(
        generated_at_iso=now_iso,
        validation_origin="PHYSICAL_ESP32",
        classifier_kind="embedded_esp32",
        checks=checks,
        all_passed=all(checks.values()),
        matches_completed=game.matches_completed,
        best_distance_m=round(game.best_distance_m, 2),
        # O estado local padrão não prova os valores persistidos no ESP32.
        coins_after_match=None,
        xp_after_match=None,
        mean_e2e_latency_ms=None,
        p95_e2e_latency_ms=None,
        duplicate_events_blocked=None,
        involuntary_noise_rejected=None,
        lcd_terminal_synced=None,
        persistence_verified=None,
        problems=problems,
        mean_processing_ms=mean_lat if latencies_ms else None,
        p95_processing_ms=p95_lat if latencies_ms else None,
        processing_time_scope="decodificacao e processamento do evento no host apos recepcao serial",
        observations={
            "gestures_received": sorted(seen_gestures),
            "events_same_gesture_within_350ms": duplicates_seen,
            "valid_lcd_frame_received": lcd_seen,
        },
    )
    _save_e2e_report(rep, report_path)
    return rep
