"""Testes dos módulos de simulação (sensores, detector de janela) e integração ponta a ponta.

Cobre:
- SensorSimulator determinístico: reprodutibilidade por seed, perfis de trajetórias 1D,
  detecção reflexiva por TCRT5000, e simulação de perda de eco (timeout ultrassônico).
- DatasetReplaySource: carregamento de datasets gravados em .jsonl e .csv,
  tratamento de fim de arquivo (exhausted) e modo contínuo (loop=True).
- SimulatedWindowGestureDetector: detecção heurística de janelas deslizantes para
  APPROACH, RETREAT e HOLD sem falsos positivos em NEUTRAL, com cooldown e reset.
- Integração ponta a ponta SimulatedEsp32Node <-> TerminalHostClient via VirtualSerialEndpoint:
  sincronização de estado e LCD 20x4, propagação de erros de protocolo (BAD_FRAME),
  tratamento de atalhos de teclado (handle_keypress) e execução bem-sucedida de run_demo.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import pytest

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.gesture_detector_sim import SimulatedWindowGestureDetector
from simulator.sensors import DatasetReplaySource, SensorSimulator
from terminal.app import TerminalHostClient, run_demo
from terminal.communication.protocol import (
    AppModeId,
    CommandType,
    GestureEventPayload,
    GestureSource,
    GestureType,
    MessageType,
    SensorFramePayload,
)
from terminal.communication.transport import create_virtual_serial_pair
from terminal.pet.state import EvolutionStage, PetState


# ==============================================================================
# 1. Testes do SensorSimulator
# ==============================================================================


class TestSensorSimulator:
    """Valida geração estocástica e determinística de séries temporais de sensores."""

    def test_seed_determinism(self) -> None:
        sim1 = SensorSimulator(seed=123, sample_period_ms=50)
        sim2 = SensorSimulator(seed=123, sample_period_ms=50)

        for _ in range(30):
            ts1, frame1 = sim1.next_frame()
            ts2, frame2 = sim2.next_frame()
            assert ts1 == ts2
            assert frame1.distance_cm == frame2.distance_cm
            assert frame1.ir_detected == frame2.ir_detected
            assert frame1.pot_norm == frame2.pot_norm
            assert frame1.valid_ultrasonic == frame2.valid_ultrasonic

    def test_sample_period_progression(self) -> None:
        sim = SensorSimulator(sample_period_ms=60)
        ts1, _ = sim.next_frame()
        ts2, _ = sim.next_frame()
        assert ts1 == 60
        assert ts2 == 120

    def test_approach_gesture_trajectory(self) -> None:
        sim = SensorSimulator(seed=1, noise_std_cm=0.0, dropout_prob=0.0)
        sim.queue_gesture_profile(GestureType.APPROACH)

        distances: list[float] = []
        for _ in range(10):
            _, frame = sim.next_frame()
            assert frame.valid_ultrasonic is True
            assert frame.distance_cm is not None
            distances.append(frame.distance_cm)

        # Distância deve diminuir monotonicamente de ~44 para ~12
        assert distances[0] > distances[-1]
        assert distances[0] == pytest.approx(44.0, 0.1)
        assert distances[-1] == pytest.approx(12.5, 0.1)

    def test_retreat_gesture_trajectory(self) -> None:
        sim = SensorSimulator(seed=1, noise_std_cm=0.0, dropout_prob=0.0)
        sim.queue_gesture_profile(GestureType.RETREAT)

        distances: list[float] = []
        for _ in range(10):
            _, frame = sim.next_frame()
            assert frame.distance_cm is not None
            distances.append(frame.distance_cm)

        # Distância deve aumentar monotonicamente de ~12 para ~44
        assert distances[-1] > distances[0]
        assert distances[0] == pytest.approx(12.0, 0.1)

    def test_hold_gesture_trajectory(self) -> None:
        sim = SensorSimulator(seed=1, noise_std_cm=0.0, dropout_prob=0.0)
        sim.queue_gesture_profile(GestureType.HOLD)

        distances = [sim.next_frame()[1].distance_cm for _ in range(10)]
        for d in distances:
            assert d == pytest.approx(18.0, 0.1)

    def test_tcrt5000_ir_detection_threshold(self) -> None:
        # IR reflexivo dispara apenas para distâncias <= 12.5 cm
        sim = SensorSimulator(seed=1, noise_std_cm=0.0, dropout_prob=0.0)
        sim.queue_gesture_profile(GestureType.APPROACH)

        frames = [sim.next_frame()[1] for _ in range(10)]
        # Os primeiros frames (> 12.5cm) têm ir_detected=False
        assert not frames[0].ir_detected
        # O último frame (12.5cm) ativa ir_detected=True
        assert frames[-1].ir_detected is True

    def test_ultrasonic_echo_dropout(self) -> None:
        # Com dropout_prob=1.0, todos os frames devem simular falha de eco
        sim = SensorSimulator(dropout_prob=1.0)
        for _ in range(5):
            _, frame = sim.next_frame()
            assert frame.valid_ultrasonic is False
            assert frame.distance_cm is None
            assert frame.ir_detected is False

    def test_potentiometer_adjustments(self) -> None:
        sim = SensorSimulator()
        sim.set_potentiometer(0.5)
        assert sim.adjust_potentiometer(0.2) == pytest.approx(0.7, 0.01)
        assert sim.adjust_potentiometer(0.5) == 1.0  # clamp no máximo
        assert sim.adjust_potentiometer(-2.0) == 0.0  # clamp no mínimo


# ==============================================================================
# 2. Testes do DatasetReplaySource
# ==============================================================================


class TestDatasetReplaySource:
    """Valida reprodução de séries temporais reais ou sintéticas a partir de arquivos."""

    def test_replay_jsonl_file(self, tmp_path: Path) -> None:
        jsonl_file = tmp_path / "recordings.jsonl"
        lines = [
            json.dumps({"ts_ms": 60, "data": {"distance_cm": 35.0, "ir_detected": False, "pot_norm": 0.5, "valid_ultrasonic": True}}),
            json.dumps({"ts_ms": 120, "data": {"distance_cm": 25.0, "ir_detected": False, "pot_norm": 0.5, "valid_ultrasonic": True}}),
            json.dumps({"ts_ms": 180, "data": {"distance_cm": 11.0, "ir_detected": True, "pot_norm": 0.6, "valid_ultrasonic": True}}),
        ]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        replay = DatasetReplaySource(jsonl_file, loop=False)
        assert replay.total_frames == 3
        assert not replay.exhausted

        ts1, f1 = replay.next_frame()
        assert ts1 == 60 and f1.distance_cm == 35.0

        ts2, f2 = replay.next_frame()
        assert ts2 == 120 and f2.distance_cm == 25.0

        ts3, f3 = replay.next_frame()
        assert ts3 == 180 and f3.ir_detected is True
        assert replay.exhausted

        # Ao esgotar sem loop, repete o último frame
        ts4, f4 = replay.next_frame()
        assert ts4 == 180 and f4 == f3

    def test_replay_jsonl_with_loop(self, tmp_path: Path) -> None:
        jsonl_file = tmp_path / "loop.jsonl"
        lines = [
            json.dumps({"ts_ms": 100, "data": {"distance_cm": 20.0, "ir_detected": False, "pot_norm": 0.5}}),
            json.dumps({"ts_ms": 200, "data": {"distance_cm": 30.0, "ir_detected": False, "pot_norm": 0.5}}),
        ]
        jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        replay = DatasetReplaySource(jsonl_file, loop=True)
        assert replay.next_frame()[0] == 100
        assert replay.next_frame()[0] == 200
        # Faz loop e recomeça do primeiro frame
        assert replay.next_frame()[0] == 100
        assert not replay.exhausted

    def test_replay_csv_file(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "sensor_data.csv"
        rows = [
            ["ts_ms", "distance_cm", "ir_detected", "pot_norm", "valid_ultrasonic"],
            ["60", "42.5", "0", "0.4", "1"],
            ["120", "None", "false", "0.5", "0"],
            ["180", "10.2", "true", "0.8", "true"],
        ]
        with csv_file.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerows(rows)

        replay = DatasetReplaySource(csv_file, loop=False)
        assert replay.total_frames == 3

        _, f1 = replay.next_frame()
        assert f1.distance_cm == 42.5
        assert f1.ir_detected is False

        _, f2 = replay.next_frame()
        assert f2.distance_cm is None
        assert f2.valid_ultrasonic is False

        _, f3 = replay.next_frame()
        assert f3.distance_cm == 10.2
        assert f3.ir_detected is True

    def test_invalid_replay_file_cases(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            DatasetReplaySource(tmp_path / "nonexistent.jsonl")

        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Dataset vazio"):
            DatasetReplaySource(empty_file)

        unsupported_format = tmp_path / "data.xml"
        unsupported_format.write_text("<data></data>", encoding="utf-8")
        with pytest.raises(ValueError, match="Formato de dataset não suportado"):
            DatasetReplaySource(unsupported_format)


# ==============================================================================
# 3. Testes do SimulatedWindowGestureDetector
# ==============================================================================


class TestSimulatedWindowGestureDetector:
    """Valida a detecção heurística de janelas 1D no simulador."""

    def test_neutral_idle_produces_no_gestures(self) -> None:
        detector = SimulatedWindowGestureDetector(window_size=8)
        # Distância inativa (75cm)
        for _ in range(25):
            frame = SensorFramePayload(distance_cm=75.0, ir_detected=False, pot_norm=0.5)
            evt = detector.push(frame)
            assert evt is None, "Falso positivo gerado para estado NEUTRAL/ocioso"

    def test_detects_approach_gesture(self) -> None:
        detector = SimulatedWindowGestureDetector(window_size=8, cooldown_frames=5)
        # Sequência aproximando de 45cm para 12cm
        distances = [45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 12.0]
        detected_event: GestureEventPayload | None = None

        for d in distances:
            frame = SensorFramePayload(distance_cm=d, ir_detected=d <= 12.5, pot_norm=0.5)
            evt = detector.push(frame)
            if evt is not None:
                detected_event = evt

        assert detected_event is not None
        assert detected_event.gesture == GestureType.APPROACH
        assert detected_event.source == GestureSource.SIM_SENSOR
        assert detected_event.confidence >= 0.65

    def test_detects_retreat_gesture(self) -> None:
        detector = SimulatedWindowGestureDetector(window_size=8, cooldown_frames=5)
        # Sequência afastando de 12cm para 45cm
        distances = [12.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0]
        detected_event: GestureEventPayload | None = None

        for d in distances:
            frame = SensorFramePayload(distance_cm=d, ir_detected=False, pot_norm=0.5)
            evt = detector.push(frame)
            if evt is not None:
                detected_event = evt

        assert detected_event is not None
        assert detected_event.gesture == GestureType.RETREAT
        assert detected_event.source == GestureSource.SIM_SENSOR

    def test_detects_hold_gesture(self) -> None:
        detector = SimulatedWindowGestureDetector(window_size=8, cooldown_frames=5)
        # Sequência parada próxima (18cm estável)
        detected_event: GestureEventPayload | None = None

        for _ in range(8):
            frame = SensorFramePayload(distance_cm=18.0, ir_detected=False, pot_norm=0.5)
            evt = detector.push(frame)
            if evt is not None:
                detected_event = evt

        assert detected_event is not None
        assert detected_event.gesture == GestureType.HOLD
        assert detected_event.source == GestureSource.SIM_SENSOR
        assert detected_event.confidence == 0.88

    def test_detector_cooldown_and_reset(self) -> None:
        detector = SimulatedWindowGestureDetector(window_size=8, cooldown_frames=5)
        # Dispara um HOLD
        for _ in range(8):
            detector.push(SensorFramePayload(distance_cm=18.0, ir_detected=False, pot_norm=0.5))

        # Durante o cooldown, novas amostras não devem emitir novo evento
        for _ in range(4):
            evt = detector.push(SensorFramePayload(distance_cm=18.0, ir_detected=False, pot_norm=0.5))
            assert evt is None

        # Reset limpa histórico e cooldown
        detector.reset()
        assert len(detector._buffer) == 0
        assert detector._cooldown == 0


# ==============================================================================
# 4. Testes de Integração Ponta a Ponta: SimulatedEsp32Node <-> TerminalHostClient
# ==============================================================================


class TestEndToEndNodeAndClientIntegration:
    """Valida o funcionamento integrado do firmware simulado com o cliente do terminal."""

    def test_boot_and_initial_synchronization(self, tmp_path: Path) -> None:
        host_ep, device_ep, _ = create_virtual_serial_pair()
        save_file = tmp_path / "test_init.save.json"

        sim_node = SimulatedEsp32Node(
            endpoint=device_ep,
            initial_state=PetState(name="SynchroPet", stage=EvolutionStage.EGG),
            save_path=save_file,
        )
        client = TerminalHostClient(host_ep)

        sim_node.boot(auto_load=False)
        processed = client.poll_serial()

        assert processed >= 2  # PET_STATE e LCD_FRAME
        assert client.pet_state.name == "SynchroPet"
        assert client.pet_state.stage == EvolutionStage.EGG
        assert len(client.lcd_frame.lines) == 4
        assert "Synchro" in client.lcd_frame.lines[0]

    def test_command_execution_and_state_update(self, tmp_path: Path) -> None:
        host_ep, device_ep, _ = create_virtual_serial_pair()
        sim_node = SimulatedEsp32Node(
            endpoint=device_ep,
            initial_state=PetState(name="HungryPet", hunger=50.0),
            save_path=tmp_path / "feed.save.json",
        )
        client = TerminalHostClient(host_ep)
        sim_node.boot(auto_load=False)
        client.poll_serial()

        # Host envia comando FEED
        client.send_command(CommandType.FEED)
        # Nó simulado processa entrada serial e executa um ciclo
        sim_node.step()
        # Host lê atualizações do nó
        client.poll_serial()

        assert client.pet_state.hunger < 50.0
        assert client.pet_state.care_counters["feed"] == 1
        assert "FED" in client.pet_state.last_action

    def test_corrupted_frame_handling_returns_error_message(self, tmp_path: Path) -> None:
        host_ep, device_ep, _ = create_virtual_serial_pair()
        sim_node = SimulatedEsp32Node(
            endpoint=device_ep,
            save_path=tmp_path / "corrupt_comm.save.json",
        )
        client = TerminalHostClient(host_ep)
        sim_node.boot(auto_load=False)
        client.poll_serial()

        # Injeta lixo sintático no canal serial do dispositivo
        host_ep.write_line("INVALID_JSON_CORRUPTED_FRAME\n")
        sim_node.step()
        client.poll_serial()

        # O host deve registrar a mensagem de erro retornada pelo firmware simulado
        assert client.last_error is not None
        assert "BAD_FRAME" in client.last_error

    def test_client_keyboard_handlers(self, tmp_path: Path) -> None:
        host_ep, device_ep, _ = create_virtual_serial_pair()
        sensor_sim = SensorSimulator(seed=1)
        sim_node = SimulatedEsp32Node(
            endpoint=device_ep,
            sensor_source=sensor_sim,
            save_path=tmp_path / "keys.save.json",
        )
        client = TerminalHostClient(host_ep)
        sim_node.boot(auto_load=False)
        client.poll_serial()

        # Testa tecla de saída 'q'
        assert client.handle_keypress("q") is False

        # Testa teclas de comandos do pet
        for key, expected_action in [
            ("f", "FED"),
            ("i", "PETTED"),
            ("c", "HEALED"),
            ("r", "SLEEPING"),
        ]:
            assert client.handle_keypress(key) is True
            sim_node.step()
            client.poll_serial()
            assert expected_action in client.pet_state.last_action

        # Testa avanço de tick 't'
        old_age = client.pet_state.age_ticks
        assert client.handle_keypress("t") is True
        sim_node.step()
        client.poll_serial()
        assert client.pet_state.age_ticks > old_age

        # Testa alternância de modos 'm'
        assert client.active_mode == AppModeId.MOTION_PET
        assert client.handle_keypress("m") is True
        assert client.active_mode == AppModeId.PET_LAUNCH

        # Testa injeção de perfis de gestos via teclado numérico
        assert client.handle_keypress("1", sensor_sim=sensor_sim) is True
        assert len(sensor_sim._trajectory) == 10  # APPROACH tem 10 amostras

        # Testa ajuste de potenciômetro '+' e '-'
        old_pot = sensor_sim._pot_norm
        assert client.handle_keypress("+", sensor_sim=sensor_sim) is True
        assert sensor_sim._pot_norm == pytest.approx(old_pot + 0.1, 0.01)

    def test_run_demo_execution(self, tmp_path: Path) -> None:
        """Executa a demonstração automatizada do Ciclo 1 completa e valida saída."""
        demo_save = tmp_path / "demo_output.save.json"
        out_stream = io.StringIO()

        ret_code = run_demo(save_path=demo_save, pet_name="DemoPet", out=out_stream)
        assert ret_code == 0

        output = out_stream.getvalue()
        assert "=== MOTIONPET CICLO 1 -- DEMONSTRACAO EXECUTAVEL" in output
        assert "[ETAPA 1] Estado inicial" in output
        assert "[ETAPA 2] Apos gesto HC-SR04 APPROACH" in output
        assert "Resumo do barramento Serial Virtual:" in output
        assert demo_save.is_file()
