"""Testes dos renderizadores (LCD 20x4, Terminal ASCII) e modos modulares de aplicação.

Cobre:
- Invariantes estritas do Lcd20x4Renderer para todas as combinações de estágios, humores,
  animações, paridades de frame e leituras válidas/timeout de sensor (exatamente 4x20 chars ASCII imprimíveis).
- TerminalAsciiRenderer: largura uniforme de todas as linhas (PANEL_WIDTH == 86),
  espelho idêntico do LCD 20x4, barras de progresso e banners de modos auxiliares.
- PetLaunchMode e simulate_launch_trajectory: física balística, monotonia de distância
  em função da potência, colisões, pontuação e recompensas.
- AirMusicMode: mapeamento de distância para escala pentatônica e controle de volume/mudo.
- AirSlidesMode: avanço/recuo de slides com proteção de debounce/cooldown temporal.
"""

from __future__ import annotations

import itertools
import pytest

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    GestureSource,
    GestureType,
    LcdFramePayload,
    SensorFramePayload,
)
from terminal.games.pet_launch import PetLaunchMode, simulate_launch_trajectory
from terminal.modes.air_music import AirMusicMode
from terminal.modes.air_slides import AirSlidesMode
from terminal.pet.state import (
    EvolutionStage,
    PetAnimation,
    PetMood,
    PetPersonality,
    PetState,
)
from terminal.renderer.ascii_terminal import (
    HudTelemetry,
    TerminalAsciiRenderer,
    _progress_bar,
)
from terminal.renderer.lcd20x4 import Lcd20x4Renderer, _sanitize_ascii


# ==============================================================================
# 1. Testes Estritos de Invariantes do LCD 20x4
# ==============================================================================


class TestLcd20x4RendererInvariants:
    """Garante que qualquer estado do pet e sensor resulte em 4 linhas de 20 caracteres ASCII válidos."""

    def test_sanitize_ascii_helper(self) -> None:
        raw = "Pèt-Córê 🚀 1234567890"
        sanitized = _sanitize_ascii(raw, 20)
        assert len(sanitized) == 20
        assert all(0x20 <= ord(c) <= 0x7E for c in sanitized)
        # Caracteres não-ASCII substituídos por '?'
        assert "?" in sanitized

    def test_all_state_combinations_satisfy_20x4_ascii_invariants(self) -> None:
        renderer = Lcd20x4Renderer()
        stages = list(EvolutionStage)
        moods = list(PetMood)
        animations = list(PetAnimation)
        parities = (0, 1)

        sensor_scenarios = [
            None,
            SensorFramePayload(distance_cm=None, ir_detected=False, pot_norm=0.5, valid_ultrasonic=False),
            SensorFramePayload(distance_cm=8.5, ir_detected=True, pot_norm=0.1, valid_ultrasonic=True),
            SensorFramePayload(distance_cm=142.0, ir_detected=False, pot_norm=0.9, valid_ultrasonic=True),
            SensorFramePayload(distance_cm=1250.0, ir_detected=False, pot_norm=1.0, valid_ultrasonic=True),  # > 999cm
        ]

        # Testa combinações representativas
        for stage, mood, anim in itertools.product(stages, moods, animations):
            for parity in parities:
                for sensor in sensor_scenarios:
                    state = PetState(
                        name="TestPet" if parity == 0 else "LongNameForPet",
                        stage=stage,
                        mood=mood,
                        animation=anim,
                        level=1 if stage == EvolutionStage.EGG else (3 if stage == EvolutionStage.CHICK else 99),
                        hunger=10.0 if parity == 0 else 95.0,
                        happiness=80.0 if parity == 0 else 5.0,
                        energy=70.0 if parity == 0 else 10.0,
                        health=90.0 if parity == 0 else 25.0,
                        is_sleeping=(mood == PetMood.SLEEPING),
                        last_action="ACTION_TEST" if parity == 0 else "LONG_ACTION_STRING_EXCEEDS",
                    )

                    frame = renderer.render(state, frame_idx=parity, sensor=sensor)
                    assert len(frame.lines) == 4
                    for line_idx, line in enumerate(frame.lines):
                        assert len(line) == 20, (
                            f"Linha {line_idx} com tamanho incorreto ({len(line)}): {line!r} "
                            f"(stage={stage}, mood={mood}, anim={anim}, parity={parity})"
                        )
                        for ch in line:
                            code = ord(ch)
                            assert 0x20 <= code <= 0x7E, (
                                f"Caractere não-ASCII 0x{code:02X} ({ch!r}) na linha {line_idx}: {line!r}"
                            )

    def test_unicode_and_excessive_length_handling_in_lcd(self) -> None:
        renderer = Lcd20x4Renderer()
        state = PetState(
            name="Pipóca_🐶_Ultra",
            last_action="G:APPROACH_INTERAÇÃO_EXTRA",
        )
        frame = renderer.render(state, frame_idx=0)
        assert len(frame.lines) == 4
        for line in frame.lines:
            assert len(line) == 20
            assert all(0x20 <= ord(c) <= 0x7E for c in line)


# ==============================================================================
# 2. Testes do Terminal ASCII Renderer
# ==============================================================================


class TestTerminalAsciiRenderer:
    """Valida geometria, espelhamento do display LCD 20x4 e seções do painel."""

    def test_progress_bar_formatting(self) -> None:
        bar0 = _progress_bar(0.0, width=10)
        assert bar0 == "[----------]   0.0%"

        bar50 = _progress_bar(50.0, width=10)
        assert bar50 == "[#####-----]  50.0%"

        bar100 = _progress_bar(100.0, width=10)
        assert bar100 == "[##########] 100.0%"

        # Clamping
        bar_neg = _progress_bar(-15.0, width=10)
        assert bar_neg == "[----------]   0.0%"
        bar_over = _progress_bar(150.0, width=10)
        assert bar_over == "[##########] 100.0%"

    @pytest.mark.parametrize("stage", list(EvolutionStage))
    @pytest.mark.parametrize("mode", list(AppModeId))
    def test_panel_width_invariant_and_lcd_mirror(
        self, stage: EvolutionStage, mode: AppModeId
    ) -> None:
        renderer = TerminalAsciiRenderer()
        lcd_renderer = Lcd20x4Renderer()
        state = PetState(name="HeroPet", stage=stage, level=5 if stage == EvolutionStage.CYBER_ROOSTER else 1)
        lcd = lcd_renderer.render(state, frame_idx=0)

        telemetry = HudTelemetry(
            mode=mode,
            sensor=SensorFramePayload(distance_cm=24.5, ir_detected=False, pot_norm=0.6),
            last_gesture=GestureEventPayload(
                gesture=GestureType.APPROACH, confidence=0.92, source=GestureSource.SIM_SENSOR
            ),
            tx_packets=12,
            rx_packets=15,
            save_status="TEST_SAVE_OK",
            mode_banner="[BANNER LINHA 1]\n[BANNER LINHA 2]" if mode != AppModeId.MOTION_PET else "",
        )

        rendered = renderer.render(state, lcd, frame_idx=0, telemetry=telemetry)
        lines = rendered.splitlines()

        # Invariante: todas as linhas devem ter exatamente PANEL_WIDTH (86) caracteres
        for idx, line in enumerate(lines):
            assert len(line) == TerminalAsciiRenderer.PANEL_WIDTH, (
                f"Linha {idx} possui largura {len(line)} != {TerminalAsciiRenderer.PANEL_WIDTH}: {line!r}"
            )

        # Invariante: o espelho do LCD 20x4 físico deve estar presente
        assert "ESPELHO LCD FISICO 20x4 (HD44780):" in rendered
        for lcd_line in lcd.lines:
            assert f"  |{lcd_line}|" in rendered


# ==============================================================================
# 3. Testes do PetLaunchMode e Física Balística
# ==============================================================================


class TestPetLaunchPhysicsAndMode:
    """Valida a simulação de trajetória balística e interações de arremesso."""

    def test_distance_monotonicity_with_power(self) -> None:
        # Com ângulo fixo, maior potência deve resultar em maior distância
        powers = [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
        distances = [simulate_launch_trajectory(p, angle_deg=45.0).distance_m for p in powers]

        for i in range(len(distances) - 1):
            assert distances[i] < distances[i + 1], (
                f"Distância para p={powers[i]} ({distances[i]}) não é menor que p={powers[i+1]} ({distances[i+1]})"
            )

    def test_trajectory_clamps_and_metrics(self) -> None:
        res = simulate_launch_trajectory(power_norm=1.5, angle_deg=95.0)  # deve clampar
        assert res.initial_speed_mps == 30.0  # 5 + 1.0 * 25
        assert res.angle_deg == 80.0  # clampado em 80
        assert res.distance_m > 0
        assert res.max_height_m > 0
        assert res.bounces >= 1
        assert res.score == int(round(res.distance_m * 10.0))
        assert 5 <= res.xp_reward <= 50

    def test_pet_launch_mode_events(self) -> None:
        mode = PetLaunchMode()
        assert mode.mode_id == AppModeId.PET_LAUNCH
        assert mode.charge_norm == 0.0

        # Sensor ajusta ângulo via potenciômetro (20° + pot * 50°)
        mode.on_sensor_frame(SensorFramePayload(distance_cm=20.0, ir_detected=False, pot_norm=0.5))
        assert mode.angle_deg == 45.0

        # Gesto HOLD carrega força em incrementos de 0.25
        status = mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.HOLD, confidence=0.9, source=GestureSource.SIM_KEYBOARD)
        )
        assert mode.charge_norm == 0.25
        assert "25%" in status

        mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.HOLD, confidence=0.9, source=GestureSource.SIM_KEYBOARD)
        )
        assert mode.charge_norm == 0.50

        # Gesto RETREAT cancela a carga
        mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.RETREAT, confidence=0.9, source=GestureSource.SIM_KEYBOARD)
        )
        assert mode.charge_norm == 0.0

        # Gesto APPROACH sem carga usa valor padrão (0.5) e arremessa
        launch_status = mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.APPROACH, confidence=0.9, source=GestureSource.SIM_KEYBOARD)
        )
        assert "LANCADO!" in launch_status
        assert mode.last_result is not None
        assert mode.best_distance_m == mode.last_result.distance_m
        assert mode.charge_norm == 0.0

        banner = mode.status_banner()
        assert "PET LAUNCH" in banner
        assert f"{mode.best_distance_m:.1f}m" in banner


# ==============================================================================
# 4. Testes do AirMusicMode
# ==============================================================================


class TestAirMusicMode:
    """Valida mapeamento contínuo de distância e volume para notas e frequências musicais."""

    def test_air_music_pitch_and_volume_mapping(self) -> None:
        mode = AirMusicMode()
        assert mode.mode_id == AppModeId.AIR_MUSIC

        # 1. Distância próxima (<= 8cm) mapeia para nota C4
        mode.on_sensor_frame(
            SensorFramePayload(distance_cm=5.0, ir_detected=True, pot_norm=0.75, valid_ultrasonic=True)
        )
        assert mode.volume_pct == 75.0
        assert mode.current_note == "C4"
        assert mode.current_freq_hz == pytest.approx(261.63, 0.01)

        # 2. Distância distante (>= 48cm) mapeia para nota E5
        mode.on_sensor_frame(
            SensorFramePayload(distance_cm=55.0, ir_detected=False, pot_norm=0.2, valid_ultrasonic=True)
        )
        assert mode.volume_pct == 20.0
        assert mode.current_note == "E5"
        assert mode.current_freq_hz == pytest.approx(659.25, 0.01)

        # 3. Leitura ultrassônica inválida não altera a nota musical
        mode.on_sensor_frame(
            SensorFramePayload(distance_cm=None, ir_detected=False, pot_norm=0.3, valid_ultrasonic=False)
        )
        assert mode.current_note == "E5"
        assert mode.volume_pct == 30.0

    def test_air_music_gesture_controls(self) -> None:
        mode = AirMusicMode()
        mode.current_note = "A4"
        mode.current_freq_hz = 440.0

        # Gesto HOLD alterna mudo (mute on / mute off)
        status_mute = mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.HOLD, confidence=0.9, source=GestureSource.SIM_SENSOR)
        )
        assert mode.muted is True
        assert status_mute == "MUTE ON"

        mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.HOLD, confidence=0.9, source=GestureSource.SIM_SENSOR)
        )
        assert mode.muted is False

        # APPROACH dispara gatilho sonoro
        trig = mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.APPROACH, confidence=0.9, source=GestureSource.SIM_SENSOR)
        )
        assert "TRIGGER A4" in trig

        # RETREAT libera sustentação
        rel = mode.on_gesture_event(
            GestureEventPayload(gesture=GestureType.RETREAT, confidence=0.9, source=GestureSource.SIM_SENSOR)
        )
        assert rel == "RELEASE SUSTAIN"

        banner = mode.status_banner()
        assert "AIR MUSIC" in banner


# ==============================================================================
# 5. Testes do AirSlidesMode e Proteção Anti-Repetição (Debounce)
# ==============================================================================


class TestAirSlidesMode:
    """Valida controle gestual de slides e proteção de cooldown temporal contra múltiplos disparos."""

    def test_slide_navigation_and_bounds(self) -> None:
        mode = AirSlidesMode(total_slides=3, cooldown_ms=0)
        assert mode.current_slide == 1

        evt_next = GestureEventPayload(
            gesture=GestureType.APPROACH, confidence=0.9, source=GestureSource.SIM_SENSOR
        )
        evt_prev = GestureEventPayload(
            gesture=GestureType.RETREAT, confidence=0.9, source=GestureSource.SIM_SENSOR
        )

        # Avança 1 -> 2
        mode.on_gesture_event(evt_next)
        assert mode.current_slide == 2

        # Avança 2 -> 3
        mode.on_gesture_event(evt_next)
        assert mode.current_slide == 3

        # Limite superior: não ultrapassa 3
        mode.on_gesture_event(evt_next)
        assert mode.current_slide == 3

        # Retorna 3 -> 2
        mode.on_gesture_event(evt_prev)
        assert mode.current_slide == 2

        # Retorna 2 -> 1
        mode.on_gesture_event(evt_prev)
        assert mode.current_slide == 1

        # Limite inferior: não desce abaixo de 1
        mode.on_gesture_event(evt_prev)
        assert mode.current_slide == 1

    def test_debounce_cooldown_blocks_rapid_triggers(self) -> None:
        mode = AirSlidesMode(total_slides=10, cooldown_ms=1000)
        evt = GestureEventPayload(
            gesture=GestureType.APPROACH, confidence=0.9, source=GestureSource.SIM_SENSOR
        )

        # Primeiro disparo em t=1000ms: deve avançar para slide 2
        res1 = mode.on_gesture_event(evt, ts_ms=1000)
        assert mode.current_slide == 2
        assert "SLIDE 2/10" in res1

        # Segundo disparo rápido em t=1500ms (500ms depois < 1000ms): DEVE SER BLOQUEADO
        res2 = mode.on_gesture_event(evt, ts_ms=1500)
        assert mode.current_slide == 2
        assert res2 == "BLOQUEADO POR DEBOUNCE"

        # Terceiro disparo após expirar cooldown em t=2050ms (1050ms depois >= 1000ms): ACEITO
        res3 = mode.on_gesture_event(evt, ts_ms=2050)
        assert mode.current_slide == 3
        assert "SLIDE 3/10" in res3

    def test_unrelated_gestures_ignored(self) -> None:
        mode = AirSlidesMode(total_slides=5)
        evt_hold = GestureEventPayload(
            gesture=GestureType.HOLD, confidence=0.9, source=GestureSource.SIM_SENSOR
        )
        status = mode.on_gesture_event(evt_hold)
        assert mode.current_slide == 1
        assert status == "PRONTO"
