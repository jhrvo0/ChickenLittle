"""Nó ESP32 simulado: executa sensores, estado autoritativo do Pet, LCD 20x4 e protocolo Serial."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.classifiers import BaseGestureClassifier, SimulatedGestureClassifier
from simulator.sensors import SensorSimulator, SensorSource
from terminal.communication.protocol import (
    AckPayload,
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


class SimulatedEsp32Node:
    """Simula o firmware do ESP32 comunicando-se exclusivamente via `SerialEndpoint` JSON Lines.

    Mantém a fonte única de verdade do `PetState` e do `LcdFramePayload`, garantindo que o
    terminal do notebook opere como cliente serial real sem duplicar regras de negócio.
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
        self.last_sensor: SensorFramePayload | None = None
        self.last_lcd: LcdFramePayload = self.lcd_renderer.render(self.engine.state, 0)
        self.save_status: str = "PRONTO"

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

    def step(self) -> None:
        """Executa um ciclo completo de recepção serial, aquisição de sensores e publicação."""
        self._step_counter += 1
        ts_ms, sensor_frame = self.sensor_source.next_frame()
        self.last_sensor = sensor_frame

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
            self.endpoint.write_line(
                self.codec.encode(MessageType.GESTURE_EVENT, detected.to_dict(), ts_ms=ts_ms)
            )
            applied = self.engine.apply_gesture(detected)
            if applied is not None:
                state_dirty = True

        # 4. Tick biológico periódico do pet
        if self._step_counter % self.pet_tick_every_n_samples == 0:
            self.engine.tick(1)
            state_dirty = True

        # 5. Publica estado do pet e frame 20x4 do LCD sempre que houver atualização
        if state_dirty:
            self._publish_state_and_lcd(ts_ms=ts_ms)

    def _process_incoming_serial(self, ts_ms: int) -> bool:
        dirty = False
        for raw_line in self.endpoint.read_all_lines():
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
                    cmd_payload = PetCommandPayload.from_dict(env.data)
                    dirty = self._handle_command(cmd_payload) or dirty
                    ack = AckPayload(ack_seq=env.seq, status="ok")
                    self.endpoint.write_line(
                        self.codec.encode(MessageType.ACK, ack.to_dict(), ts_ms=ts_ms)
                    )
                elif env.type == MessageType.GESTURE_EVENT:
                    gest = GestureEventPayload.from_dict(env.data)
                    # Ecoa o evento para manter todos os assinantes sincronizados
                    self.endpoint.write_line(
                        self.codec.encode(MessageType.GESTURE_EVENT, gest.to_dict(), ts_ms=ts_ms)
                    )
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
            self.engine.state.last_action = f"M:{target[:10]}"
            return True

        self.engine.apply_command(cmd)
        return True

    def _publish_state_and_lcd(self, ts_ms: int) -> None:
        self.last_lcd = self.lcd_renderer.render(
            self.engine.state,
            frame_idx=self._step_counter,
            sensor=self.last_sensor,
        )
        self.endpoint.write_line(
            self.codec.encode(MessageType.PET_STATE, self.engine.state.to_dict(), ts_ms=ts_ms)
        )
        self.endpoint.write_line(
            self.codec.encode(MessageType.LCD_FRAME, self.last_lcd.to_dict(), ts_ms=ts_ms)
        )
