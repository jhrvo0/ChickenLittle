"""Nó ESP32 simulado: executa sensores, estado autoritativo do Pet, LCD 20x4 e protocolo Serial."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.classifiers import BaseGestureClassifier, SimulatedGestureClassifier
from simulator.sensors import SensorSimulator, SensorSource
from terminal.communication.protocol import (
    AckPayload,
    AppModeId,
    CommandType,
    ErrorPayload,
    GestureEventPayload,
    LcdFramePayload,
    MessageType,
    PetCommandPayload,
    ProtocolCodec,
    ProtocolError,
    SensorFramePayload,
)
from terminal.communication.transport import SerialEndpoint
from terminal.pet.config import PetConfig
from terminal.pet.engine import PetEngine
from terminal.pet.persistence import PersistenceError, PetPersistence
from terminal.pet.state import PetState
from terminal.renderer.lcd20x4 import Lcd20x4Renderer

SIMULATED_FW_VERSION = "0.5.0-sim"


class SimulatedEsp32Node:
    """Simula o firmware do ESP32 comunicando-se exclusivamente via `SerialEndpoint` JSON Lines.

    Mantém a fonte única de verdade do `PetState` e do `LcdFramePayload`, garantindo que o
    terminal do notebook opere como cliente serial real sem duplicar regras de negócio.
    Responde aos mesmos comandos de bancada (`DIAG`, `START`, `STOP`, `PERIOD`, `IR`) do
    firmware C++ real, porém carimbando explicitamente `origin=SIMULATOR`.
    """

    def __init__(
        self,
        endpoint: SerialEndpoint,
        sensor_source: SensorSource | None = None,
        pet_config: PetConfig | None = None,
        initial_state: PetState | None = None,
        save_path: str | Path = "data/saves/pet_state.save.json",
        pet_tick_every_n_samples: int = 5,
        classifier: BaseGestureClassifier | Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.sensor_source: SensorSource = sensor_source or SensorSimulator(seed=42)
        self.persistence = PetPersistence(save_path)
        self.engine = PetEngine(state=initial_state, config=pet_config)
        self.lcd_renderer = Lcd20x4Renderer()
        self.detector: Any = classifier if classifier is not None else SimulatedGestureClassifier()
        self.codec = ProtocolCodec()
        self.pet_tick_every_n_samples = max(1, pet_tick_every_n_samples)

        self._step_counter = 0
        self._last_ts_ms = 0
        self.active_mode: AppModeId = AppModeId.MOTION_PET
        self.last_sensor: SensorFramePayload | None = None
        self.last_lcd: LcdFramePayload = self.lcd_renderer.render(self.engine.state, 0)
        self.save_status: str = "PRONTO"

        # Métricas de diagnóstico e controle de aquisição compatíveis com o firmware C++
        self.collection_active: bool = True
        self.ir_enabled: bool = True
        self.sample_period_ms: int = int(getattr(self.sensor_source, "sample_period_ms", 70))
        self.total_samples: int = 0
        self.ultrasonic_timeouts: int = 0
        self.total_events_emitted: int = 0
        self.total_windows_rejected: int = 0
        self.nvs_writes: int = 0
        self.lcd_frames_rendered: int = 0

    def boot(self, auto_load: bool = True) -> None:
        """Inicializa o nó simulado, carregando save se existir, e publica snapshot inicial."""
        if auto_load and self.persistence.exists():
            try:
                loaded = self.persistence.load()
                self.engine.replace_state(loaded)
                self.engine.state.last_action = "SAVE LOADED"
                self.save_status = f"CARREGADO ({self.persistence.save_path.name})"
            except PersistenceError as exc:
                self.save_status = f"ERRO LOAD: {exc}"

        self._publish_state_and_lcd(ts_ms=0)

    def format_diag_status(self) -> str:
        """Formata string `diag:...` idêntica em schema ao firmware C++, marcando `origin=SIMULATOR`."""
        diag = self.detector.get_diagnostics() if hasattr(self.detector, "get_diagnostics") else None
        mdl = diag.model_name if diag is not None else "sim_window_heuristic"
        exp = diag.experimental_status if diag is not None else "SIMULATION_ONLY"
        inf_us = int(round((diag.last_latency_ms if diag is not None else 0.0) * 1000.0))
        rej = int(diag.rejected_events) if diag is not None else self.total_windows_rejected
        return (
            f"diag:fw={SIMULATED_FW_VERSION},origin=SIMULATOR,pins=SIMULATED_VIRTUAL_BUS,"
            f"acq={'on' if self.collection_active else 'off'},"
            f"per_ms={self.sample_period_ms},acq_us=45,"
            f"samp={self.total_samples},to_us={self.ultrasonic_timeouts},"
            f"drop_inf=0,drop_tx=0,"
            f"mdl={mdl},exp={exp},"
            f"inf_us={inf_us},evt={self.total_events_emitted},rej={rej},"
            f"mode={self.active_mode.value},nvs_w={self.nvs_writes},"
            f"lcd_f={self.lcd_frames_rendered},heap=294912"
        )

    def step(self) -> None:
        """Executa um ciclo completo de recepção serial, aquisição de sensores e publicação."""
        self._step_counter += 1

        if not self.collection_active:
            self._last_ts_ms += self.sample_period_ms
            state_dirty = self._process_incoming_serial(self._last_ts_ms)
            if state_dirty:
                self._publish_state_and_lcd(ts_ms=self._last_ts_ms)
            return

        ts_ms, sensor_frame = self.sensor_source.next_frame()
        if not self.ir_enabled and sensor_frame.ir_detected:
            sensor_frame = SensorFramePayload(
                distance_cm=sensor_frame.distance_cm,
                ir_detected=False,
                pot_norm=sensor_frame.pot_norm,
                valid_ultrasonic=sensor_frame.valid_ultrasonic,
            )

        self._last_ts_ms = ts_ms
        self.last_sensor = sensor_frame
        self.total_samples += 1
        if not sensor_frame.valid_ultrasonic or sensor_frame.distance_cm is None:
            self.ultrasonic_timeouts += 1

        # 1. Processa comandos e gestos injetados pelo host via serial
        state_dirty = self._process_incoming_serial(ts_ms)

        # 2. Publica telemetria de sensores
        self.endpoint.write_line(
            self.codec.encode(MessageType.SENSOR_FRAME, sensor_frame.to_dict(), ts_ms=ts_ms)
        )

        # 3. Avalia classificador intercambiável de gestos (Simulado, ML ou Embarcado)
        if hasattr(self.detector, "push_frame"):
            detected = self.detector.push_frame(sensor_frame, ts_ms=ts_ms)
        else:
            detected = self.detector.push(sensor_frame)
        if detected is not None:
            self.total_events_emitted += 1
            self.endpoint.write_line(
                self.codec.encode(MessageType.GESTURE_EVENT, detected.to_dict(), ts_ms=ts_ms)
            )
            if self.active_mode == AppModeId.MOTION_PET:
                applied = self.engine.apply_gesture(detected)
                if applied is not None:
                    state_dirty = True

        # 4. Tick biológico periódico do pet (pausado durante partida ativa de Pet Launch)
        if (
            self.active_mode != AppModeId.PET_LAUNCH
            and self._step_counter % self.pet_tick_every_n_samples == 0
        ):
            self.engine.tick(1)
            state_dirty = True

        # 5. Publica estado do pet e frame 20x4 do LCD sempre que houver atualização
        if state_dirty:
            self._publish_state_and_lcd(ts_ms=ts_ms)

    def _set_period_ms(self, raw_ms: int) -> None:
        clamped = max(50, min(500, int(raw_ms)))
        self.sample_period_ms = clamped
        if hasattr(self.sensor_source, "sample_period_ms"):
            self.sensor_source.sample_period_ms = clamped

    def _try_handle_plain_bench_command(self, raw_line: str, ts_ms: int) -> bool:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("{"):
            return False
        upper = stripped.upper()
        status_out: str | None = None

        if upper in ("DIAG", "STATUS"):
            status_out = self.format_diag_status()
        elif upper == "START":
            self.collection_active = True
            status_out = "collection_started"
        elif upper == "STOP":
            self.collection_active = False
            status_out = "collection_stopped"
        elif upper == "IR ON":
            self.ir_enabled = True
            status_out = "ir_enabled"
        elif upper == "IR OFF":
            self.ir_enabled = False
            status_out = "ir_disabled"
        elif upper.startswith("PERIOD "):
            arg = stripped[7:].strip()
            if arg.isdigit():
                self._set_period_ms(int(arg))
                status_out = "period_updated"

        if status_out is None:
            return False

        ack = AckPayload(ack_seq=0, status=status_out)
        self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
        return True

    def _try_handle_extended_bench_json_cmd(self, env_seq: int, data: dict[str, Any], ts_ms: int) -> bool:
        raw_cmd = str(data.get("command", "")).strip().upper()
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}

        if raw_cmd in ("DIAG", "STATUS"):
            ack = AckPayload(ack_seq=env_seq, status=self.format_diag_status())
            self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
            return True

        if raw_cmd == "START_COLLECTION":
            p_ms = data.get("period_ms", payload.get("period_ms"))
            if isinstance(p_ms, (int, float)) and int(p_ms) > 0:
                self._set_period_ms(int(p_ms))
            self.collection_active = True
            ack = AckPayload(ack_seq=env_seq, status="collection_started")
            self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
            return True

        if raw_cmd == "STOP_COLLECTION":
            self.collection_active = False
            ack = AckPayload(ack_seq=env_seq, status="collection_stopped")
            self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
            return True

        if raw_cmd == "SET_PERIOD":
            p_ms = data.get("period_ms", payload.get("period_ms"))
            if not isinstance(p_ms, (int, float)) or int(p_ms) <= 0:
                raise ProtocolError("Campo 'period_ms' inválido em SET_PERIOD")
            self._set_period_ms(int(p_ms))
            ack = AckPayload(ack_seq=env_seq, status="period_updated")
            self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
            return True

        if raw_cmd == "SET_IR":
            en = data.get("enabled", payload.get("enabled"))
            if not isinstance(en, bool):
                raise ProtocolError("Campo booleano 'enabled' obrigatório em SET_IR")
            self.ir_enabled = en
            ack = AckPayload(ack_seq=env_seq, status="ir_enabled" if en else "ir_disabled")
            self.endpoint.write_line(self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms))
            return True

        return False

    def _process_incoming_serial(self, ts_ms: int) -> bool:
        dirty = False
        for raw_line in self.endpoint.read_all_lines():
            if self._try_handle_plain_bench_command(raw_line, ts_ms):
                continue

            try:
                env = self.codec.decode(raw_line)
            except ProtocolError as exc:
                err = ErrorPayload(code="BAD_FRAME", message=str(exc))
                self.endpoint.write_line(
                    self.codec.encode(MessageType.ERROR, err.to_dict(), ts_ms=ts_ms)
                )
                continue

            try:
                if env.type == MessageType.PET_COMMAND:
                    if self._try_handle_extended_bench_json_cmd(env.seq, env.data, ts_ms):
                        continue
                    cmd_payload = PetCommandPayload.from_dict(env.data)
                    dirty = self._handle_command(cmd_payload) or dirty
                    ack = AckPayload(ack_seq=env.seq, status="ok")
                    self.endpoint.write_line(
                        self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms)
                    )
                elif env.type == MessageType.GESTURE_EVENT:
                    gest = GestureEventPayload.from_dict(env.data)
                    self.total_events_emitted += 1
                    # Ecoa o evento para manter todos os assinantes sincronizados
                    self.endpoint.write_line(
                        self.codec.encode(MessageType.GESTURE_EVENT, gest.to_dict(), ts_ms=ts_ms)
                    )
                    if self.active_mode == AppModeId.MOTION_PET:
                        if self.engine.apply_gesture(gest) is not None:
                            dirty = True
                    ack = AckPayload(ack_seq=env.seq, status="ok")
                    self.endpoint.write_line(
                        self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms)
                    )
            except (ProtocolError, PersistenceError) as exc:
                err = ErrorPayload(code="EXEC_ERR", message=str(exc), ref_seq=env.seq)
                self.endpoint.write_line(
                    self.codec.encode(MessageType.ERROR, err.to_dict(), ts_ms=ts_ms)
                )

        return dirty

    def _handle_command(self, cmd_payload: PetCommandPayload) -> bool:
        cmd = cmd_payload.command
        if cmd == CommandType.SAVE:
            path = self.persistence.save(self.engine.state)
            self.nvs_writes += 1
            self.engine.state.last_action = "SAVED!"
            self.save_status = f"SALVO ({path.name})"
            return True

        if cmd == CommandType.LOAD:
            loaded = self.persistence.load()
            self.engine.replace_state(loaded)
            self.engine.state.last_action = "LOADED!"
            self.save_status = f"RECARREGADO ({self.persistence.save_path.name})"
            return True

        if cmd == CommandType.SWITCH_MODE:
            target = str(cmd_payload.payload.get("mode", "MOTION_PET"))
            try:
                self.active_mode = AppModeId(target)
            except ValueError:
                self.active_mode = AppModeId.MOTION_PET
            self.engine.state.last_action = f"M:{self.active_mode.value[:10]}"
            return True

        if cmd == CommandType.PLAY and cmd_payload.payload.get("minigame") == "PET_LAUNCH":
            action = str(cmd_payload.payload.get("action", ""))
            if action == "MATCH_RESULT":
                self.engine.apply_launch_match(
                    distance_m=float(cmd_payload.payload.get("distance_m", 0.0)),
                    score=int(cmd_payload.payload.get("score", 0)),
                    coins_earned=int(cmd_payload.payload.get("coins_earned", 0)),
                    xp_earned=int(cmd_payload.payload.get("xp_earned", 0)),
                    bounces=int(cmd_payload.payload.get("bounces", 0)),
                )
                return True
            if action == "UNLOCK_UPGRADE":
                self.engine.unlock_launch_upgrade(
                    upgrade_id=str(cmd_payload.payload.get("upgrade_id", "")),
                    cost=int(cmd_payload.payload.get("cost", 0)),
                )
                return True

        self.engine.apply_command(cmd)
        return True

    def _publish_state_and_lcd(self, ts_ms: int) -> None:
        self.last_lcd = self.lcd_renderer.render(
            self.engine.state,
            frame_idx=self._step_counter,
            sensor=self.last_sensor,
        )
        self.lcd_frames_rendered += 1
        self.endpoint.write_line(
            self.codec.encode(MessageType.PET_STATE, self.engine.state.to_dict(), ts_ms=ts_ms)
        )
        self.endpoint.write_line(
            self.codec.encode(MessageType.LCD_FRAME, self.last_lcd.to_dict(), ts_ms=ts_ms)
        )
