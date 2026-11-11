"""Uma única conexão USB compartilhada pelas telas do aplicativo local."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
import math
from pathlib import Path
from queue import Empty, Queue
import threading
import time
from typing import Any

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.app import TerminalHostClient
from terminal.bench.assistant import list_serial_ports, query_device_diag
from terminal.communication.protocol import (
    AppModeId, CommandType, GestureEventPayload, GestureSource, GestureType,
    SensorFramePayload,
)
from terminal.communication.transport import PySerialEndpoint, create_virtual_serial_pair
from terminal.games.pet_launch import LAUNCH_UPGRADES, LaunchPhase
from terminal.pet.state import PetState

SLIDES = [
    {"eyebrow": "01 · Olá, mundo", "title": "Uma pequena criatura. Um grande vínculo.", "body": "Seu MotionPet responde ao mundo físico. Aproxime a mão do ultrassom ou um cartão do sensor infravermelho."},
    {"eyebrow": "02 · O que sentimos", "title": "Sua mão vira movimento.", "body": "O ultrassom mede a distância. O infravermelho reconhece a presença bem de perto. Os dois trabalham juntos."},
    {"eyebrow": "03 · Nosso pet", "title": "Cuidar também é brincar.", "body": "Alimente, dê carinho, descanse e cuide da saúde. Cada interação faz parte da evolução do seu companheiro."},
    {"eyebrow": "04 · Pet Launch", "title": "Pronto para ganhar o céu?", "body": "Mude o ângulo com a distância da mão. Aproxime o cartão para carregar e afaste para lançar."},
    {"eyebrow": "05 · Música no ar", "title": "Encontre sua própria melodia.", "body": "A distância escolhe a nota. Um toque sem contato no infravermelho pausa ou retoma o instrumento."},
    {"eyebrow": "06 · Evolução", "title": "Do ovo ao galo cibernético.", "body": "Experiência, cuidados e brincadeiras acompanham a evolução. O estado do pet continua na ESP32."},
    {"eyebrow": "07 · Dois mundos", "title": "Conectado ao que é real.", "body": "A ESP32 cuida dos sensores e do pet. O notebook desenha esse pequeno mundo e dá voz às interações."},
    {"eyebrow": "08 · Até logo", "title": "O próximo movimento é seu.", "body": "Continue explorando. Sem trocar fios, você pode cuidar, jogar, criar música e navegar pela apresentação."},
]

CONTROLS = {
    "MOTION_PET": "Aproxime um cartão do IR para alimentar. Aproxime a mão do ultrassom para fazer carinho.",
    "PET_LAUNCH": "O IR confirma as etapas. Segure o cartão perto do IR para carregar e afaste para lançar. A distância da mão ajusta o ângulo.",
    "AIR_MUSIC": "A distância da mão escolhe a nota. Aproxime o cartão do IR para pausar ou retomar o som.",
    "AIR_SLIDES": "Mão perto do ultrassom avança; longe volta. Aproxime o cartão do IR para avançar.",
}

PET_DISPLAY_NAME = "Piu-piu"


class MotionPetSession:
    """Executa o protocolo e os motores existentes sem abrir a USB no carregamento."""

    def __init__(self, *, allow_demo: bool = False) -> None:
        self.allow_demo = allow_demo
        self._lock = threading.RLock()
        self._jobs: Queue = Queue()
        self._stop = threading.Event()
        self._client: TerminalHostClient | None = None
        self._node: SimulatedEsp32Node | None = None
        self._status = "disconnected"
        self._port: str | None = None
        self._origin = "NONE"
        self._message = "Conecte sua ESP32 para começar."
        self._frames = 0
        self._last_frame: float | None = None
        self._pet_seen = False
        self._last_ir: bool | None = None
        self._zone: str | None = None
        self._last_input = 0.0
        self._last_charge = 0.0
        self._volume = .35
        self._events: deque = deque(maxlen=24)
        self._event_id = 0
        self._trajectory: deque = deque(maxlen=240)
        self._history: deque = deque(maxlen=90)
        self._thread = threading.Thread(target=self._run, daemon=True, name="motionpet-usb")
        self._thread.start()

    def ports(self) -> list[dict]:
        ports = [{"device": p.device, "description": p.description or "ESP32"} for p in list_serial_ports()]
        if self.allow_demo:
            ports.append({"device": "DEMO", "description": "Demonstração — sem ESP32"})
        return ports

    def connect(self, port: str) -> None:
        if not isinstance(port, str) or port not in {p["device"] for p in self.ports()}:
            raise ValueError("Escolha uma porta USB disponível.")
        with self._lock:
            if self._status == "connecting":
                raise ValueError("A conexão já está sendo iniciada.")
            self._status = "connecting"
            self._message = "Conectando à ESP32…"
            self._port = port
        self._jobs.put(("connect", port, None))

    def disconnect(self) -> None:
        self._jobs.put(("disconnect", None, None))

    def state(self) -> dict:
        with self._lock:
            return self._state_locked()

    def action(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Comando inválido.")
        action = payload.get("action")
        allowed = {"feed", "play", "rest", "heal", "interact", "save", "load", "reset", "mode", "launch_key", "volume", "slides_next", "slides_prev"}
        if action not in allowed:
            raise ValueError("Ação desconhecida.")
        if action == "mode" and payload.get("mode") not in {x.value for x in AppModeId}:
            raise ValueError("Escolha um modo válido.")
        if action == "launch_key" and payload.get("key") not in {"enter", "space", "esc", "e", "h", "v", "b", "w", "z", "u", "7", "8", "9"}:
            raise ValueError("Controle de jogo inválido.")
        if action == "volume":
            value = payload.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("O volume precisa estar entre 0 e 1.")
        with self._lock:
            if not self._live_locked():
                raise ValueError("Conecte a ESP32 e aguarde as leituras dos sensores.")
        done, result = threading.Event(), {}
        self._jobs.put(("action", dict(payload), (done, result)))
        if not done.wait(3):
            raise ValueError("A ESP32 está ocupada. Aguarde e tente novamente.")
        if "error" in result:
            raise ValueError(result["error"])
        return self.state()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=9)

    def _event(self, text: str, kind: str = "info") -> None:
        self._event_id += 1
        self._events.appendleft({"id": self._event_id, "type": kind, "text": text, "timestamp": time.time()})

    def _close_locked(self) -> None:
        if self._client is not None:
            try:
                self._client.endpoint.close()
            except Exception:
                pass
        self._client = None
        self._node = None
        self._last_frame = None
        self._last_ir = None
        self._zone = None
        self._pet_seen = False
        self._frames = 0
        self._history.clear()
        self._trajectory.clear()

    def _open(self, port: str) -> None:
        with self._lock:
            self._close_locked()
        endpoint = None
        try:
            node = None
            if port == "DEMO":
                if not self.allow_demo:
                    raise ValueError("Demonstração não habilitada.")
                endpoint, device, _ = create_virtual_serial_pair()
                node = SimulatedEsp32Node(
                    endpoint=device,
                    sensor_source=SensorSimulator(seed=17, dropout_prob=0),
                    initial_state=PetState(name="Pip"),
                    save_path=Path("data/saves/web_demo.save.json"),
                    pet_tick_every_n_samples=40,
                )
                node.boot(auto_load=False)
                origin = "DEMO"
            else:
                endpoint = PySerialEndpoint(port, baudrate=115200)
                try:
                    diag = query_device_diag(endpoint, timeout_sec=4)
                except TimeoutError:
                    diag = query_device_diag(endpoint, timeout_sec=3)
                if not diag.is_physical_hardware:
                    raise ValueError("A porta não respondeu como uma ESP32 MotionPet.")
                origin = "ESP32_HW"
            client = TerminalHostClient(endpoint, transport_label=origin, dispatch_gesture_events=False)
            endpoint.write_line("START")
            endpoint.write_line("IR ON")
            client.send_command(CommandType.SWITCH_MODE, {"mode": AppModeId.MOTION_PET.value})
            with self._lock:
                self._client = client
                self._node = node
                self._origin = origin
                self._status = "connected"
                self._message = "Demonstração local — sem sensores físicos." if node else "ESP32 conectada pela USB."
                self._event(self._message, "connection")
        except Exception as exc:
            if endpoint is not None:
                endpoint.close()
            with self._lock:
                self._status = "error"
                self._origin = "NONE"
                self._message = f"Não foi possível conectar. Feche o monitor serial que usa {port} e tente novamente. Detalhe: {exc}"
                self._event(self._message, "error")

    def _live_locked(self) -> bool:
        return self._status == "connected" and self._client is not None and self._last_frame is not None and time.monotonic() - self._last_frame < 2

    def _perform(self, payload: dict) -> None:
        if not self._live_locked():
            raise ValueError("Sem leituras recentes da ESP32.")
        client = self._client
        assert client is not None
        action = payload["action"]
        commands = {"feed": CommandType.FEED, "play": CommandType.PLAY, "rest": CommandType.REST, "heal": CommandType.HEAL, "interact": CommandType.INTERACT, "save": CommandType.SAVE, "load": CommandType.LOAD, "reset": CommandType.RESET}
        labels = {"feed": "Comidinha a caminho!", "play": "Hora de brincar!", "rest": "Uma pausa no ninho.", "heal": "Um cuidado especial.", "interact": "Um carinho para seu pet.", "save": "Pedido para salvar enviado.", "load": "Pedido para carregar enviado.", "reset": "Pedido de novo pet enviado."}
        if action in commands:
            client.send_command(commands[action])
            self._event(labels[action], "care")
        elif action == "mode":
            client.set_mode(AppModeId(payload["mode"]))
            self._last_ir = None
            self._zone = None
            self._trajectory.clear()
            self._event("Um novo jeito de brincar.", "mode")
        elif action == "launch_key":
            if client.active_mode != AppModeId.PET_LAUNCH:
                raise ValueError("Abra o Pet Launch primeiro.")
            key = {"enter": "\r", "space": " ", "esc": "\x1b"}.get(payload["key"], payload["key"])
            client.handle_keypress(key)
        elif action == "volume":
            self._volume = float(payload["value"])
        elif action in {"slides_next", "slides_prev"}:
            slides = client.aux_modes[AppModeId.AIR_SLIDES]
            slides.current_slide = max(1, min(slides.total_slides, slides.current_slide + (1 if action == "slides_next" else -1)))
            slides.last_status = "Avançou" if action == "slides_next" else "Voltou"

    def _sensor_controls(self, frame: SensorFramePayload, now: float) -> None:
        client = self._client
        assert client is not None
        rising = self._last_ir is False and frame.ir_detected
        falling = self._last_ir is True and not frame.ir_detected
        self._last_ir = frame.ir_detected
        zone = None
        if frame.valid_ultrasonic and frame.distance_cm is not None:
            zone = "near" if frame.distance_cm < 15 else "far" if frame.distance_cm > 35 else "middle"
        zone_changed = zone is not None and self._zone is not None and zone != self._zone
        if zone is not None:
            self._zone = zone
        mode = client.active_mode
        if mode == AppModeId.MOTION_PET:
            if rising and now - self._last_input > .8:
                client.send_command(CommandType.FEED)
                self._last_input = now
                self._event("O cartão trouxe uma comidinha.", "sensor")
            elif zone_changed and zone == "near" and now - self._last_input > 1:
                client.send_command(CommandType.INTERACT)
                self._last_input = now
                self._event("Seu pet sentiu a mão se aproximar.", "sensor")
        elif mode == AppModeId.PET_LAUNCH:
            game = client.pet_launch_mode.game
            if frame.valid_ultrasonic and frame.distance_cm is not None:
                norm = max(0.0, min(1.0, (45 - frame.distance_cm) / 37))
                adapted = SensorFramePayload(frame.distance_cm, frame.ir_detected, norm, True)
                client.pet_launch_mode.on_sensor_frame(adapted)
            if rising and game.phase in {LaunchPhase.MENU, LaunchPhase.SELECT_PET, LaunchPhase.RESULT}:
                client.handle_keypress("\r")
                self._last_charge = now
            elif frame.ir_detected and game.phase in {LaunchPhase.PREP, LaunchPhase.CHARGING} and now - self._last_charge > .25:
                client.handle_keypress(" ")
                self._last_charge = now
            elif falling and game.phase == LaunchPhase.CHARGING:
                client.handle_keypress("\r")
        elif mode == AppModeId.AIR_MUSIC:
            music = client.aux_modes[AppModeId.AIR_MUSIC]
            music.volume_pct = self._volume * 100
            if rising and now - self._last_input > .5:
                music.on_gesture_event(GestureEventPayload(GestureType.HOLD, 1, GestureSource.RULE_BASELINE))
                self._last_input = now
        elif mode == AppModeId.AIR_SLIDES and now - self._last_input > 1:
            gesture = GestureType.APPROACH if rising or (zone_changed and zone == "near") else GestureType.RETREAT if zone_changed and zone == "far" else None
            if gesture is not None:
                slides = client.aux_modes[AppModeId.AIR_SLIDES]
                slides.on_gesture_event(GestureEventPayload(gesture, 1, GestureSource.RULE_BASELINE), ts_ms=int(now * 1000))
                self._last_input = now

    def _run(self) -> None:
        previous = time.monotonic()
        next_demo = previous
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                dt = min(.1, now - previous)
                previous = now
                try:
                    job, payload, completion = self._jobs.get_nowait()
                except Empty:
                    job = None
                if job == "connect":
                    self._open(payload)
                elif job == "disconnect":
                    with self._lock:
                        self._close_locked()
                        self._status, self._origin = "disconnected", "NONE"
                        self._message = "USB desconectada do aplicativo."
                elif job == "action":
                    done, result = completion
                    try:
                        with self._lock:
                            self._perform(payload)
                    except Exception as exc:
                        result["error"] = str(exc)
                    finally:
                        done.set()
                with self._lock:
                    client = self._client
                    if client is not None:
                        try:
                            if self._node is not None and now >= next_demo:
                                self._node.step()
                                next_demo = now + .07
                            sensor_before, pet_before = client.last_sensor, client.pet_state
                            client.poll_serial()
                            if client.pet_state is not pet_before:
                                self._pet_seen = True
                            if client.last_sensor is not None and client.last_sensor is not sensor_before:
                                self._last_frame = time.monotonic()
                                self._frames += 1
                                self._sensor_controls(client.last_sensor, self._last_frame)
                                self._history.append({"distance_cm": client.last_sensor.distance_cm, "valid": client.last_sensor.valid_ultrasonic})
                            if self._live_locked():
                                client.update_game(dt)
                                game = client.pet_launch_mode.game
                                if game.phase == LaunchPhase.LAUNCHING:
                                    self._trajectory.clear()
                                if game.phase == LaunchPhase.FLIGHT:
                                    p = game.physics.state
                                    self._trajectory.append({"x_m": p.x_m, "y_m": p.y_m})
                        except Exception as exc:
                            self._close_locked()
                            self._status = "error"
                            self._message = f"A conexão USB foi interrompida: {exc}"
                            self._event(self._message, "error")
                self._stop.wait(.025)
        finally:
            with self._lock:
                self._close_locked()

    def _state_locked(self) -> dict[str, Any]:
        client = self._client
        age = round((time.monotonic() - self._last_frame) * 1000) if self._last_frame is not None else None
        connected_status = self._status
        message = self._message
        if self._status == "connected" and (age is None or age > 2000):
            message = "Aguardando leituras dos sensores…" if age is None else "Sem leituras recentes. Confira a USB."
        state = {
            "pet_name": PET_DISPLAY_NAME,
            "connection": {"status": connected_status, "port": self._port, "origin": self._origin, "message": message, "frames": self._frames, "age_ms": age},
            "mode": client.active_mode.value if client else "MOTION_PET",
            "pet": client.pet_state.to_dict() if client and self._pet_seen else None,
            "sensors": client.last_sensor.to_dict() if client and client.last_sensor else None,
            "gesture": client.last_gesture.to_dict() if client and client.last_gesture else None,
            "events": list(self._events),
            "controls": CONTROLS,
            "display_lines": list(client.lcd_frame.lines) if client else [],
            "metrics": {"rx_packets": client.rx_packets if client else 0, "tx_packets": client.tx_packets if client else 0, "history": list(self._history)},
            "launch": None, "music": None, "slides": None,
        }
        if state["pet"] is not None:
            # Nome da apresentação no notebook; preserva o save e as estatísticas na ESP32.
            state["pet"]["name"] = PET_DISPLAY_NAME
        if client is not None:
            g = client.pet_launch_mode.game
            flight = asdict(g.physics.state)
            if hasattr(flight["motion_phase"], "value"):
                flight["motion_phase"] = flight["motion_phase"].value
            state["launch"] = {
                "phase": g.phase.value, "angle_deg": g.angle_deg, "charge_norm": g.charge_norm,
                "sweet_spot": g.is_in_sweet_spot(), "flight": flight, "trajectory": list(self._trajectory),
                "result": asdict(g.last_result) if g.last_result else None,
                "best_distance_m": g.best_distance_m, "status_message": g.status_message,
                "upgrades": [dict(asdict(u), owned=u.upgrade_id in client.pet_state.unlocked_upgrades) for u in LAUNCH_UPGRADES],
            }
            music = client.aux_modes[AppModeId.AIR_MUSIC]
            state["music"] = {"note": music.current_note, "frequency_hz": music.current_freq_hz, "volume": self._volume, "muted": music.muted, "trigger": music.last_trigger}
            slides = client.aux_modes[AppModeId.AIR_SLIDES]
            state["slides"] = {"current": slides.current_slide, "total": slides.total_slides, "items": SLIDES, "status": slides.last_status}
        return state
