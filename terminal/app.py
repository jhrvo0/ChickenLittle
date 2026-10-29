"""Aplicação principal de terminal do MotionPet (interativa em tempo real e modos demonstração)."""

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
from terminal.games.launch_renderer import (
    DifferentialTerminalWriter,
    detect_terminal_dimensions,
    should_use_compact_layout,
)
from terminal.games.pet_launch import LaunchPhase, PetLaunchMode
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
        compact_mode: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.transport_label = transport_label
        self.compact_mode = compact_mode
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
        self._return_to_pet_lcd_ttl = 0

        self.active_mode: AppModeId = AppModeId.MOTION_PET
        self._launch_mode = PetLaunchMode(animated_flight=True)
        self.aux_modes: dict[AppModeId, BaseAppMode] = {
            AppModeId.PET_LAUNCH: self._launch_mode,
            AppModeId.AIR_MUSIC: AirMusicMode(),
            AppModeId.AIR_SLIDES: AirSlidesMode(),
        }

    @property
    def pet_launch_mode(self) -> PetLaunchMode:
        return self._launch_mode

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

    def set_mode(self, target_mode: AppModeId) -> AppModeId:
        prev_mode = self.active_mode
        if prev_mode == AppModeId.PET_LAUNCH and target_mode != AppModeId.PET_LAUNCH:
            self._launch_mode.on_exit_mode(self.pet_state)
            self.lcd_frame = self._fallback_lcd.render_launch(
                state=self.pet_state,
                phase=LaunchPhase.RETURN_TO_PET.value,
                best_distance_m=self._launch_mode.best_distance_m,
                frame_idx=self.frame_idx,
            )
            self._return_to_pet_lcd_ttl = 2

        self.active_mode = target_mode
        if target_mode == AppModeId.PET_LAUNCH and prev_mode != AppModeId.PET_LAUNCH:
            self._launch_mode.on_enter_mode(self.pet_state)
            self._sync_launch_lcd()

        self.send_command(CommandType.SWITCH_MODE, {"mode": self.active_mode.value})
        return self.active_mode

    def cycle_mode(self) -> AppModeId:
        curr_idx = _MODE_ROTATION.index(self.active_mode)
        next_mode = _MODE_ROTATION[(curr_idx + 1) % len(_MODE_ROTATION)]
        return self.set_mode(next_mode)

    def _sync_launch_lcd(self) -> None:
        g = self._launch_mode.game
        self.lcd_frame = self._fallback_lcd.render_launch(
            state=self.pet_state,
            phase=g.phase.value,
            angle_deg=g.angle_deg,
            charge_norm=g.charge_norm,
            phys=g.physics.state,
            last_result=g.last_result,
            best_distance_m=g.best_distance_m,
            sweet_spot=g.is_in_sweet_spot(),
            frame_idx=self.frame_idx,
        )

    def _flush_launch_commands(self) -> None:
        for cmd_payload in self._launch_mode.pop_pending_pet_commands():
            self.send_command(CommandType.PLAY, cmd_payload)

    def update_game(self, dt_s: float) -> None:
        """Avança a simulação temporal do minijogo ativo (desacoplada do FPS do terminal)."""
        if self.active_mode == AppModeId.PET_LAUNCH:
            self._launch_mode.bind_pet_state(self.pet_state)
            self._launch_mode.update(dt_s)
            self._flush_launch_commands()
            self._sync_launch_lcd()

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
                self._launch_mode.bind_pet_state(self.pet_state)
                if self.active_mode == AppModeId.PET_LAUNCH:
                    self._sync_launch_lcd()
            elif env.type == MessageType.LCD_FRAME:
                if self.active_mode != AppModeId.PET_LAUNCH and self._return_to_pet_lcd_ttl <= 0:
                    self.lcd_frame = LcdFramePayload.from_dict(env.data)
            elif env.type == MessageType.SENSOR_FRAME:
                self.last_sensor = SensorFramePayload.from_dict(env.data)
                if self.active_mode in self.aux_modes:
                    self.aux_modes[self.active_mode].on_sensor_frame(self.last_sensor)
                    if self.active_mode == AppModeId.PET_LAUNCH:
                        self._sync_launch_lcd()
            elif env.type == MessageType.GESTURE_EVENT:
                self.last_gesture = GestureEventPayload.from_dict(env.data)
                if self.active_mode == AppModeId.PET_LAUNCH:
                    self._launch_mode.bind_pet_state(self.pet_state)
                    self._launch_mode.on_gesture_event(
                        self.last_gesture,
                        seq_id=env.seq,
                        ts_ms=env.ts_ms,
                    )
                    self._flush_launch_commands()
                    self._sync_launch_lcd()
                elif self.active_mode in self.aux_modes:
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
        if not key:
            return True

        k = key.lower()
        if k == "q":
            return False
        if k == "f":
            self.send_command(CommandType.FEED)
            return True
        if k == "p":
            self.send_command(CommandType.PLAY)
            return True
        if k == "r":
            self.send_command(CommandType.REST)
            return True
        if k == "c":
            self.send_command(CommandType.HEAL)
            return True
        if k == "i":
            self.send_command(CommandType.INTERACT)
            return True
        if k == "t":
            self.send_command(CommandType.TICK)
            return True
        if k == "s":
            self.send_command(CommandType.SAVE)
            return True
        if k == "l":
            self.send_command(CommandType.LOAD)
            return True
        if k == "n":
            self.send_command(CommandType.RESET)
            return True
        if k == "m":
            self.cycle_mode()
            return True
        if k == "1":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.APPROACH)
            else:
                self.send_simulated_gesture(GestureType.APPROACH)
            return True
        if k == "2":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.RETREAT)
            else:
                self.send_simulated_gesture(GestureType.RETREAT)
            return True
        if k == "3":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.HOLD)
            else:
                self.send_simulated_gesture(GestureType.HOLD)
            return True
        if k == "4":
            if sensor_sim is not None:
                sensor_sim.queue_gesture_profile(GestureType.NEUTRAL)
            else:
                self.send_simulated_gesture(GestureType.NEUTRAL)
            return True
        if k == "+" and sensor_sim is not None:
            sensor_sim.adjust_potentiometer(0.1)
            return True
        if k == "-" and sensor_sim is not None:
            sensor_sim.adjust_potentiometer(-0.1)
            return True

        # Atalhos dedicados do Pet Launch (ENTER, SPACE, ESC, e/h/v/b/w/z/u/7/8/9)
        if self.active_mode == AppModeId.PET_LAUNCH:
            self._launch_mode.bind_pet_state(self.pet_state)
            self._launch_mode.on_key_input(key)
            self._flush_launch_commands()
            self._sync_launch_lcd()

        return True

    def render_frame(
        self,
        term_cols: int | None = None,
        term_rows: int | None = None,
    ) -> str:
        self.frame_idx += 1
        banner = ""
        if self.active_mode in self.aux_modes:
            banner = self.aux_modes[self.active_mode].status_banner()

        if self.active_mode == AppModeId.PET_LAUNCH:
            self._sync_launch_lcd()

        use_compact = should_use_compact_layout(
            term_cols=term_cols,
            term_rows=term_rows,
            force_compact=self.compact_mode,
        )

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
        rendered = self.terminal_renderer.render(
            state=self.pet_state,
            lcd_frame=self.lcd_frame,
            frame_idx=self.frame_idx,
            telemetry=telemetry,
            compact=use_compact,
            launch_game=(
                self._launch_mode.game if self.active_mode == AppModeId.PET_LAUNCH else None
            ),
        )

        if self._return_to_pet_lcd_ttl > 0:
            self._return_to_pet_lcd_ttl -= 1

        return rendered


def run_demo(
    save_path: str | Path = "data/saves/demo_pet.save.json",
    pet_name: str = "Pip",
    out: TextIO | None = None,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
) -> int:
    """Executa a demonstração determinística ponta a ponta do Ciclo 1 sem hardware físico."""
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


def run_pet_launch_demo(
    save_path: str | Path = "data/saves/demo_pet_launch.save.json",
    pet_name: str = "Pip",
    out: TextIO | None = None,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
    compact: bool = False,
) -> int:
    """Executa demonstração automatizada completa do Pet Launch (Ciclo 4) registrando eventos."""
    stream = out or sys.stdout
    host_ep, device_ep, wire_log = create_virtual_serial_pair()
    sensor_sim = SensorSimulator(seed=21, dropout_prob=0.0)
    sensor_sim.set_potentiometer(0.46)  # ~43 graus calibrados
    clf: BaseGestureClassifier = create_gesture_classifier(
        kind=classifier_kind,
        model_path=model_path,
    )

    sim_node = SimulatedEsp32Node(
        endpoint=device_ep,
        sensor_source=sensor_sim,
        initial_state=PetState(name=pet_name, coins=10),
        save_path=save_path,
        pet_tick_every_n_samples=8,
        classifier=clf,
    )
    client = TerminalHostClient(host_ep, compact_mode=compact)

    sim_node.boot(auto_load=False)
    client.poll_serial()
    client.classifier_summary = clf.get_diagnostics().format_hud_line()

    def pump_bus() -> None:
        sim_node.step()
        client.poll_serial()

    stream.write("=== MOTIONPET CICLO 4 -- DEMONSTRACAO AUTOMATIZADA PET LAUNCH ===\n\n")

    # Etapa 1: Entrar no modo Pet Launch
    client.set_mode(AppModeId.PET_LAUNCH)
    pump_bus()

    # Etapa 2 & 3: Selecionar pet e ir para rampa via gesto prioritário APPROACH
    client.send_simulated_gesture(GestureType.APPROACH)
    pump_bus()
    client.send_simulated_gesture(GestureType.APPROACH)
    pump_bus()

    # Etapa 4: Carregar força 4x com gesto HOLD até 88% (Sweet-Spot!)
    for _ in range(4):
        client.send_simulated_gesture(GestureType.HOLD)
        pump_bus()

    stream.write(">>> [QUADRO 1] Barra de Forca carregada via Gesto HOLD (Sweet-Spot 88%):\n")
    stream.write(client.render_frame() + "\n\n")

    # Etapa 5: Disparar o lançamento com gesto prioritário APPROACH (sem depender de IMPULSE)
    client.send_simulated_gesture(GestureType.APPROACH)
    pump_bus()

    # Etapas 6 & 7: Acompanhar trajetória balística animada (timestep fixo 0.02s)
    mid_flight_frame: str | None = None
    sim_steps = 0
    while client.pet_launch_mode.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT):
        client.update_game(0.08)
        sim_steps += 1
        if mid_flight_frame is None and client.pet_launch_mode.physics_state.y_m >= 5.0:
            mid_flight_frame = client.render_frame()
        if sim_steps > 500:
            break

    # Sincroniza recompensas (Etapas 8 & 9) no PetEngine autoritativo via JSON Lines v1
    pump_bus()

    if mid_flight_frame is not None:
        stream.write(">>> [QUADRO 2] Pet em pleno voo balistico com camera horizontal:\n")
        stream.write(mid_flight_frame + "\n\n")

    stream.write(">>> [QUADRO 3] Placar Final, Recompensas e Novo Recorde integrados ao PetState:\n")
    stream.write(client.render_frame() + "\n\n")

    # Etapa 10: Retornar ao Menu, desbloquear melhoria na loja e persistir estado
    client.send_simulated_gesture(GestureType.APPROACH)
    pump_bus()
    client.handle_keypress("u")  # Compra Estilingue Pro (15 moedas)
    pump_bus()
    client.send_command(CommandType.SAVE)
    pump_bus()
    client.save_status = sim_node.save_status

    game = client.pet_launch_mode.game
    res = game.last_result
    stream.write(">>> [LOG DE EVENTOS DA PARTIDA (10 ETAPAS)]:\n")
    for idx, ev in enumerate(game.event_log, start=1):
        stream.write(f"  {idx:02d}. {ev}\n")

    if res is not None:
        stream.write(
            f"\nResumo da Partida: Dist={res.distance_m:.2f}m | AltMax={res.max_height_m:.2f}m | "
            f"Quiques={res.bounces} | Estrelas={res.stars_collected} | Score={res.score} | "
            f"Moedas Pet={client.pet_state.coins} | Upgrades={client.pet_state.unlocked_upgrades} | "
            f"Frames Serial={len(wire_log)}.\n"
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
    refresh_sec: float = 0.20,
    classifier_kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
    initial_mode: AppModeId = AppModeId.MOTION_PET,
    compact: bool = False,
) -> int:
    """Inicia a interface ASCII animada em tempo real (com renderização diferencial anti-flicker)."""
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

    client = TerminalHostClient(
        endpoint=host_ep,
        transport_label=transport_label,
        compact_mode=compact,
    )
    client.poll_serial()
    if initial_mode != AppModeId.MOTION_PET:
        client.set_mode(initial_mode)
        if sim_node is not None:
            sim_node.step()
            client.poll_serial()

    client.classifier_summary = active_clf.get_diagnostics().format_hud_line()
    if sim_node is not None:
        client.save_status = sim_node.save_status

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    if is_tty and os.name == "nt":
        # Habilita sequências ANSI VT100 no console do Windows
        os.system("")

    diff_writer = DifferentialTerminalWriter(sys.stdout, is_tty=is_tty)
    frames = 0
    last_loop_ts = time.monotonic()
    sensor_accum_s = 0.0
    sensor_period_s = 0.08

    try:
        if is_tty:
            sys.stdout.write("\x1b[2J\x1b[H\x1b[?25l")
            sys.stdout.flush()

        while True:
            now = time.monotonic()
            dt_s = max(0.0, min(0.25, now - last_loop_ts))
            last_loop_ts = now
            sensor_accum_s += dt_s

            # Avança nó simulado em cadência realista de sensores (ou no 1º frame)
            if sim_node is not None and (frames == 0 or sensor_accum_s >= sensor_period_s):
                sensor_accum_s = 0.0
                sim_node.step()

            client.poll_serial()
            client.update_game(dt_s if frames > 0 else 0.02)
            client.poll_serial()

            client.classifier_summary = active_clf.get_diagnostics().format_hud_line()
            if sim_node is not None:
                client.save_status = sim_node.save_status

            t_cols, t_rows = detect_terminal_dimensions() if is_tty else (86, 34)
            rendered = client.render_frame(term_cols=t_cols, term_rows=t_rows)
            diff_writer.write_frame(rendered)

            frames += 1
            if max_frames is not None and frames >= max_frames:
                break

            # Taxa de atualização mais fluida durante o voo balístico, sem alterar fixed_dt=0.02s
            in_fast_flight = (
                client.active_mode == AppModeId.PET_LAUNCH
                and client.pet_launch_mode.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT)
            )
            frame_wait = 0.06 if in_fast_flight else refresh_sec

            if is_tty and os.name == "nt":
                deadline = time.monotonic() + frame_wait
                keep_running = True
                while time.monotonic() < deadline:
                    key = _read_nonblocking_windows_key()
                    if key is not None:
                        keep_running = client.handle_keypress(key, sensor_sim=sensor_sim)
                        if sim_node is not None:
                            sim_node.step()
                            client.poll_serial()
                        break
                    time.sleep(0.015)
                if not keep_running:
                    break
            elif is_tty:
                cmd_str = input("\nComando [enter/space/b/u/f/p/r/1-4/m/s/q]: ")
                if cmd_str == "":
                    key_to_send = "\r"
                else:
                    key_to_send = cmd_str[0]
                if not client.handle_keypress(key_to_send, sensor_sim=sensor_sim):
                    break
            else:
                time.sleep(min(frame_wait, 0.05))
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
        description="MotionPet — Terminal ASCII, Pet Launch, Simulador ESP32/TinyML e LCD 20x4",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Executa demonstracao automatizada do Ciclo 1 (Tamagotchi + Serial) e encerra.",
    )
    parser.add_argument(
        "--launch-demo",
        action="store_true",
        help="Executa demonstracao automatizada completa do Pet Launch (Ciclo 4) e encerra.",
    )
    parser.add_argument(
        "--mode",
        choices=("motion-pet", "pet-launch"),
        default="motion-pet",
        help="Modo inicial ao abrir a interface interativa (padrao: motion-pet).",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Forca layout compacto de 60 colunas para terminais estreitos.",
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
    if args.launch_demo:
        return run_pet_launch_demo(
            save_path=args.save_path,
            pet_name=args.name,
            classifier_kind=args.classifier,
            model_path=args.model_path,
            compact=args.compact,
        )
    start_mode = (
        AppModeId.PET_LAUNCH if args.mode == "pet-launch" else AppModeId.MOTION_PET
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
        initial_mode=start_mode,
        compact=args.compact,
    )


if __name__ == "__main__":
    raise SystemExit(main())
