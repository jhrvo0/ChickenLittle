"""Aplicação principal de terminal do MotionPet (interativa em tempo real e modo demonstração)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import TextIO

from ml.classifiers import BaseGestureClassifier, create_gesture_classifier
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import DatasetReplaySource, SensorSimulator, SensorSource
from terminal.communication.protocol import (
    AppModeId,
    CommandType,
    GestureEventPayload,
    GestureSource,
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
    SerialEndpoint,
    create_virtual_serial_pair,
)
from terminal.games.pet_launch import PetLaunchMode
from terminal.modes.air_music import AirMusicMode
from terminal.modes.air_slides import AirSlidesMode
from terminal.modes.base import BaseAppMode
from terminal.pet.state import PetState
from terminal.renderer.ascii_terminal import HudTelemetry, TerminalAsciiRenderer
from terminal.renderer.lcd20x4 import Lcd20x4Renderer

_MODE_ROTATION: tuple[AppModeId, ...] = (
    AppModeId.MOTION_PET,
    AppModeId.PET_LAUNCH,
    AppModeId.AIR_MUSIC,
    AppModeId.AIR_SLIDES,
)


class TerminalHostClient:
    """Cliente de terminal conectado ao ESP32 (físico ou simulado) via protocolo JSON Lines v1."""

    def __init__(
        self,
        endpoint: SerialEndpoint,
        transport_label: str = "VIRTUAL_SERIAL_JSONL_V1",
    ) -> None:
        self.endpoint = endpoint
        self.transport_label = transport_label
        self.codec = ProtocolCodec()
        self.terminal_renderer = TerminalAsciiRenderer()
        self._fallback_lcd = Lcd20x4Renderer()

        self.pet_state = PetState()
        self.lcd_frame: LcdFramePayload = self._fallback_lcd.render(self.pet_state, 0)
        self.last_sensor: SensorFramePayload | None = None
        self.last_gesture: GestureEventPayload | None = None
        self.save_status: str = "NAO SALVO"
        self.classifier_summary: str = ""
        self.last_error: str | None = None

        self.tx_packets = 0
        self.rx_packets = 0
        self.frame_idx = 0

        self.active_mode: AppModeId = AppModeId.MOTION_PET
        self.aux_modes: dict[AppModeId, BaseAppMode] = {
            AppModeId.PET_LAUNCH: PetLaunchMode(),
            AppModeId.AIR_MUSIC: AirMusicMode(),
            AppModeId.AIR_SLIDES: AirSlidesMode(),
        }

    def send_command(self, command: CommandType, payload: dict[str, object] | None = None) -> None:
        msg = PetCommandPayload(command=command, payload=dict(payload or {}))
        line = self.codec.encode(MessageType.PET_COMMAND, msg.to_dict())
        self.endpoint.write_line(line)
        self.tx_packets += 1

        if command == CommandType.SAVE:
            self.save_status = "SALVO EM DISCO"
        elif command == CommandType.LOAD:
            self.save_status = "RECARREGADO DO DISCO"

    def send_simulated_gesture(self, gesture: GestureType, confidence: float = 0.95) -> None:
        evt = GestureEventPayload(
            gesture=gesture,
            confidence=confidence,
            source=GestureSource.SIM_KEYBOARD,
            window_ms=600,
        )
        line = self.codec.encode(MessageType.GESTURE_EVENT, evt.to_dict())
        self.endpoint.write_line(line)
        self.tx_packets += 1

    def cycle_mode(self) -> AppModeId:
        curr_idx = _MODE_ROTATION.index(self.active_mode)
        self.active_mode = _MODE_ROTATION[(curr_idx + 1) % len(_MODE_ROTATION)]
        self.send_command(CommandType.SWITCH_MODE, {"mode": self.active_mode.value})
        return self.active_mode

    def poll_serial(self) -> int:
        """Consome todas as mensagens pendentes vindas do dispositivo serial."""
        processed = 0
        for raw_line in self.endpoint.read_all_lines():
            self.rx_packets += 1
            processed += 1
            try:
                env = self.codec.decode(raw_line)
            except ProtocolError as exc:
                self.last_error = str(exc)
                continue

            if env.type == MessageType.PET_STATE:
                self.pet_state = PetState.from_dict(env.data)
            elif env.type == MessageType.LCD_FRAME:
                self.lcd_frame = LcdFramePayload.from_dict(env.data)
            elif env.type == MessageType.SENSOR_FRAME:
                self.last_sensor = SensorFramePayload.from_dict(env.data)
                if self.active_mode in self.aux_modes:
                    self.aux_modes[self.active_mode].on_sensor_frame(self.last_sensor)
            elif env.type == MessageType.GESTURE_EVENT:
                self.last_gesture = GestureEventPayload.from_dict(env.data)
                if self.active_mode in self.aux_modes:
                    mode_obj = self.aux_modes[self.active_mode]
                    if isinstance(mode_obj, AirSlidesMode):
                        mode_obj.on_gesture_event(self.last_gesture, ts_ms=env.ts_ms)
                    else:
                        mode_obj.on_gesture_event(self.last_gesture)
            elif env.type == MessageType.ERROR:
                self.last_error = f"{env.data.get('code')}: {env.data.get('message')}"

        return processed

    def handle_keypress(
        self,
        key: str,
        sensor_sim: SensorSimulator | None = None,
    ) -> bool:
        """Processa uma tecla de controle. Retorna `False` quando o usuário solicita sair."""
        k = key.lower()
        if k == "q":
            return False
        if k == "f":
            self.send_command(CommandType.FEED)
        elif k == "p":
            self.send_command(CommandType.PLAY)
        elif k == "r":
            self.send_command(CommandType.REST)
        elif k == "c":
            self.send_command(CommandType.HEAL)
        elif k == "i":
            self.send_command(CommandType.INTERACT)
        elif k == "t":
            self.send_command(CommandType.TICK)
        elif k == "s":
            self.send_command(CommandType.SAVE)
        elif k == "l":
            self.send_command(CommandType.LOAD)
        elif k == "n":
            self.send_command(CommandType.RESET)
        elif k == "m":
            self.cycle_mode()
        elif k == "1":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.APPROACH)
            else:
                self.send_simulated_gesture(GestureType.APPROACH)
        elif k == "2":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.RETREAT)
            else:
                self.send_simulated_gesture(GestureType.RETREAT)
        elif k == "3":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.HOLD)
            else:
                self.send_simulated_gesture(GestureType.HOLD)
        elif k == "4":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.NEUTRAL)
            else:
                self.send_simulated_gesture(GestureType.NEUTRAL)
        elif k == "+" and sensor_sim is not None:
            sensor_sim.adjust_potentiometer(0.1)
        elif k == "-" and sensor_sim is not None:
            sensor_sim.adjust_potentiometer(-0.1)
        return True

    def render_frame(self) -> str:
        self.frame_idx += 1
        banner = ""
        if self.active_mode in self.aux_modes:
            banner = self.aux_modes[self.active_mode].status_banner()

        telemetry = HudTelemetry(
            mode=self.active_mode,
            sensor=self.last_sensor,
            last_gesture=self.last_gesture,
            tx_packets=self.tx_packets,
            rx_packets=self.rx_packets,
            save_status=self.save_status,
            transport_label=self.transport_label,
            mode_banner=banner,
            classifier_summary=self.classifier_summary,
        )
        return self.terminal_renderer.render(
            state=self.pet_state,
            lcd_frame=self.lcd_frame,
            frame_idx=self.frame_idx,
            telemetry=telemetry,
        )


def run_demo(
    save_path: str | Path = "data/saves/demo_pet.save.json",
    pet_name: str = "Pip",
    out: TextIO | None = None,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
) -> int:
    """Executa uma demonstração determinística ponta a ponta sem hardware físico."""
    stream = out or sys.stdout
    host_ep, device_ep, wire_log = create_virtual_serial_pair()
    sensor_sim = SensorSimulator(seed=7, dropout_prob=0.0)
    clf: BaseGestureClassifier = create_gesture_classifier(
        kind=classifier_kind,
        model_path=model_path,
    )

    sim_node = SimulatedEsp32Node(
        endpoint=device_ep,
        sensor_source=sensor_sim,
        initial_state=PetState(name=pet_name),
        save_path=save_path,
        pet_tick_every_n_samples=6,
        classifier=clf,
    )
    client = TerminalHostClient(host_ep)

    sim_node.boot(auto_load=False)
    client.poll_serial()
    client.classifier_summary = clf.get_diagnostics().format_hud_line()

    stream.write("=== MOTIONPET CICLO 1 -- DEMONSTRACAO EXECUTAVEL (SEM HARDWARE FISICO) ===\n\n")
    stream.write(">>> [ETAPA 1] Estado inicial sincronizado via JSON Lines v1 (Ovo Nivel 1):\n")
    stream.write(client.render_frame() + "\n\n")

    # Etapa 2: Trajetória simulada HC-SR04 (APPROACH -> carinho automático via classificador)
    sensor_sim.queue_gesture_profile(GestureType.APPROACH)
    for _ in range(12):
        sim_node.step()
        client.poll_serial()

    # Etapa 3: Interações de cuidado e evolução para CHICK (Nível 2)
    for cmd in (CommandType.FEED, CommandType.PLAY, CommandType.PLAY, CommandType.FEED):
        client.send_command(cmd)
        sim_node.step()
        client.poll_serial()

    # Etapa 4: Persistência (Salvar -> Resetar -> Recarregar)
    client.send_command(CommandType.SAVE)
    sim_node.step()
    client.poll_serial()
    client.save_status = sim_node.save_status

    saved_level = client.pet_state.level
    client.send_command(CommandType.RESET)
    sim_node.step()
    client.poll_serial()

    client.send_command(CommandType.LOAD)
    sim_node.step()
    client.poll_serial()
    client.save_status = sim_node.save_status
    client.classifier_summary = clf.get_diagnostics().format_hud_line()

    stream.write(
        f">>> [ETAPA 2] Apos gesto HC-SR04 APPROACH, interacoes, evolucao (Nv {saved_level}) "
        "e roundtrip Salvar/Reset/Recarregar:\n"
    )
    stream.write(client.render_frame() + "\n\n")
    stream.write(
        f"Resumo do barramento Serial Virtual: {len(wire_log)} frames JSON Lines v1 trafegados "
        f"(Host TX={client.tx_packets}, Host RX={client.rx_packets}).\n"
    )
    return 0


def _read_nonblocking_windows_key() -> str | None:
    try:
        import msvcrt

        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                # Consome segundo código de teclas especiais (setas/F-keys)
                if msvcrt.kbhit():
                    msvcrt.getwch()
                return None
            return ch
    except ImportError:
        return None
    return None


def run_interactive(
    save_path: str | Path = "data/saves/pet_state.save.json",
    pet_name: str = "Pip",
    serial_port: str | None = None,
    baudrate: int = 115200,
    replay_path: str | Path | None = None,
    max_frames: int | None = None,
    refresh_sec: float = 0.25,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
) -> int:
    """Inicia a interface ASCII animada em tempo real no terminal do notebook."""
    sim_node: SimulatedEsp32Node | None = None
    sensor_sim: SensorSimulator | None = None
    active_clf: BaseGestureClassifier = create_gesture_classifier(
        kind=classifier_kind,
        model_path=model_path,
    )

    if serial_port:
        host_ep: SerialEndpoint = PySerialEndpoint(port=serial_port, baudrate=baudrate)
        transport_label = f"USB_SERIAL:{serial_port}"
    else:
        v_host, v_dev, _ = create_virtual_serial_pair()
        host_ep = v_host
        if replay_path is not None:
            source: SensorSource = DatasetReplaySource(replay_path, loop=True)
            transport_label = f"REPLAY:{Path(replay_path).name}"
        else:
            sensor_sim = SensorSimulator(seed=42)
            source = sensor_sim
            transport_label = "VIRTUAL_SERIAL_JSONL_V1"

        sim_node = SimulatedEsp32Node(
            endpoint=v_dev,
            sensor_source=source,
            initial_state=PetState(name=pet_name),
            save_path=save_path,
            classifier=active_clf,
        )
        sim_node.boot(auto_load=True)

    client = TerminalHostClient(endpoint=host_ep, transport_label=transport_label)
    client.poll_serial()
    client.classifier_summary = active_clf.get_diagnostics().format_hud_line()
    if sim_node is not None:
        client.save_status = sim_node.save_status

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    if is_tty and os.name == "nt":
        # Habilita sequências ANSI no console do Windows
        os.system("")

    frames = 0
    try:
        if is_tty:
            sys.stdout.write("\x1b[2J\x1b[?25l")
            sys.stdout.flush()

        while True:
            if sim_node is not None:
                sim_node.step()
            client.poll_serial()
            client.classifier_summary = active_clf.get_diagnostics().format_hud_line()
            if sim_node is not None:
                client.save_status = sim_node.save_status

            rendered = client.render_frame()
            if is_tty:
                sys.stdout.write("\x1b[H" + rendered + "\n")
                sys.stdout.flush()
            else:
                sys.stdout.write(rendered + "\n")
                sys.stdout.flush()

            frames += 1
            if max_frames is not None and frames >= max_frames:
                break

            if is_tty and os.name == "nt":
                deadline = time.monotonic() + refresh_sec
                keep_running = True
                while time.monotonic() < deadline:
                    key = _read_nonblocking_windows_key()
                    if key is not None:
                        keep_running = client.handle_keypress(key, sensor_sim=sensor_sim)
                        break
                    time.sleep(0.02)
                if not keep_running:
                    break
            elif is_tty:
                # Fallback POSIX simples por linha
                cmd_str = input("\nComando [f/p/r/c/i/1-4/s/l/m/n/q]: ").strip()
                if cmd_str and not client.handle_keypress(cmd_str[0], sensor_sim=sensor_sim):
                    break
            else:
                time.sleep(min(refresh_sec, 0.05))
    except KeyboardInterrupt:
        pass
    finally:
        if is_tty:
            sys.stdout.write("\x1b[?25h\n")
            sys.stdout.flush()
        host_ep.close()

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="motionpet",
        description="MotionPet — Terminal ASCII, Simulador ESP32/Sensores e Espelho LCD 20x4",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Executa demonstracao automatizada ponta a ponta sem hardware e encerra.",
    )
    parser.add_argument(
        "--name",
        default="Pip",
        help="Nome inicial do pet quando nao houver save previo (padrao: Pip).",
    )
    parser.add_argument(
        "--save-path",
        default="data/saves/pet_state.save.json",
        help="Caminho do arquivo JSON de persistencia do pet.",
    )
    parser.add_argument(
        "--serial-port",
        default=None,
        help="Porta USB Serial real do ESP32 (ex: COM3). Omitir para usar o simulador.",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baudrate da porta USB Serial (padrao: 115200).",
    )
    parser.add_argument(
        "--replay",
        default=None,
        help="Arquivo .jsonl ou .csv de leituras de sensores para reproduzir na simulacao.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Limita o numero de quadros renderizados antes de encerrar.",
    )
    parser.add_argument(
        "--classifier",
        choices=("sim", "ml", "embedded"),
        default="sim",
        help="Seleciona o classificador intercambiavel de gestos (padrao: sim).",
    )
    parser.add_argument(
        "--model-path",
        default="data/models/best_model.joblib",
        help="Caminho do modelo treinado para --classifier ml.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.demo:
        return run_demo(
            save_path=args.save_path,
            pet_name=args.name,
            classifier_kind=args.classifier,
            model_path=args.model_path,
        )
    return run_interactive(
        save_path=args.save_path,
        pet_name=args.name,
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        replay_path=args.replay,
        max_frames=args.frames,
        classifier_kind=args.classifier,
        model_path=args.model_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
