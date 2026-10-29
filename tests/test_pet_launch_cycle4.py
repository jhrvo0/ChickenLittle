"""Suíte completa de testes automatizados do Ciclo 4 — Pet Launch e Gameplay.

Cobre integralmente os 12 requisitos de verificação do Ciclo 4:
1. Determinismo da física 2D e independência rigorosa do FPS do terminal (`fixed_dt = 0.02s`).
2. Colisões com o solo, quiques, atrito pós-contato e dissipação monotônica coerente de energia.
3. Término garantido da partida em condições normais e extremas.
4. Cálculo de pontuação, estrelas, sweet-spot e modificadores de personalidade/estágio.
5. Recordes pessoais, moedas, XP e melhorias desbloqueáveis na loja.
6. Persistência atômica (`PetPersistence`) e retrocompatibilidade com saves legados.
7. Integração com `PetEngine` (custo moderado de energia, bloqueios de prontidão, evolução e humor).
8. Integração unificada de entradas (Teclado, Simulador e TinyML; fluxo seguro `HOLD` + `APPROACH`).
9. Ausência de comandos duplicados (deduplicação por token/seq e isolamento de modo no nó ESP32).
10. Limites estritos de renderização: Terminal Padrão (86c), Compacto (60c), Anti-Flicker e LCD 20x4.
11. Múltiplas partidas consecutivas com evolução acumulada no barramento JSON Lines v1.
12. Demonstração automatizada completa sem hardware físico (`run_pet_launch_demo`).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.app import TerminalHostClient, run_pet_launch_demo
from terminal.communication.protocol import (
    AppModeId,
    CommandType,
    GestureEventPayload,
    GestureSource,
    GestureType,
    SensorFramePayload,
)
from terminal.communication.transport import create_virtual_serial_pair
from terminal.games.input_adapter import LaunchAction, LaunchInputAdapter
from terminal.games.launch_renderer import (
    DifferentialTerminalWriter,
    PetLaunchAsciiRenderer,
    should_use_compact_layout,
)
from terminal.games.pet_launch import (
    LAUNCH_UPGRADES,
    LaunchPhase,
    PetLaunchGame,
    PetLaunchMode,
    compute_launch_modifiers,
)
from terminal.games.physics import (
    FlightMotionPhase,
    LaunchModifiers,
    LaunchPhysicsConfig,
    LaunchPhysicsSimulator,
)
from terminal.pet.engine import PetEngine
from terminal.pet.persistence import SAVE_SCHEMA_VERSION, PetPersistence
from terminal.pet.state import (
    EvolutionStage,
    PetMood,
    PetPersonality,
    PetState,
)
from terminal.renderer.lcd20x4 import Lcd20x4Renderer


# ==============================================================================
# 1. Determinismo Físico, Câmera Horizontal e Independência do FPS
# ==============================================================================


class TestPhysicsDeterminismAndTimestep:
    """Garante simulação 2D determinística e desacoplada da taxa de quadros do terminal."""

    def test_bit_identical_determinism_for_same_inputs(self) -> None:
        mods = LaunchModifiers(speed_multiplier=1.12, drag_multiplier=0.85, restitution_bonus=0.05)
        sim_a = LaunchPhysicsSimulator()
        sim_b = LaunchPhysicsSimulator()

        sim_a.start_launch(power_norm=0.88, angle_deg=43.5, modifiers=mods, course_index=1)
        sim_b.start_launch(power_norm=0.88, angle_deg=43.5, modifiers=mods, course_index=1)

        end_a = sim_a.run_until_stopped()
        end_b = sim_b.run_until_stopped()

        assert end_a.x_m == end_b.x_m
        assert end_a.max_height_m == end_b.max_height_m
        assert end_a.bounces == end_b.bounces
        assert end_a.roll_distance_m == end_b.roll_distance_m
        assert end_a.steps == end_b.steps
        assert end_a.collected_stars == end_b.collected_stars
        assert end_a.events == end_b.events

    @pytest.mark.parametrize("frame_dt", [0.02, 0.05, 0.08, 0.16, 0.25])
    def test_physics_decoupled_from_terminal_fps(self, frame_dt: float) -> None:
        ref_sim = LaunchPhysicsSimulator()
        ref_sim.start_launch(power_norm=0.82, angle_deg=46.0)
        ref_end = ref_sim.run_until_stopped()

        fps_sim = LaunchPhysicsSimulator()
        fps_sim.start_launch(power_norm=0.82, angle_deg=46.0)
        while not fps_sim.state.is_stopped:
            fps_sim.advance_time(frame_dt, time_scale=1.0)

        assert fps_sim.state.x_m == pytest.approx(ref_end.x_m, abs=1e-9)
        assert fps_sim.state.max_height_m == pytest.approx(ref_end.max_height_m, abs=1e-9)
        assert fps_sim.state.bounces == ref_end.bounces
        assert fps_sim.state.steps == ref_end.steps

    def test_horizontal_camera_tracks_pet_monotonically(self) -> None:
        sim = LaunchPhysicsSimulator(viewport_width_m=36.0)
        sim.start_launch(power_norm=0.95, angle_deg=44.0)

        prev_cam_x = sim.camera.x_left_m
        while not sim.state.is_stopped:
            sim.step_fixed(1)
            assert sim.camera.x_left_m >= prev_cam_x - 1e-9
            prev_cam_x = sim.camera.x_left_m
            col = sim.camera.world_to_screen_col(sim.state.x_m, screen_cols=80)
            assert col is not None
            assert 0 <= col < 80

        assert sim.state.x_m > 36.0
        assert sim.camera.x_left_m > 10.0
        assert sim.camera.world_to_screen_col(sim.camera.x_left_m - 2.0, 80) is None


# ==============================================================================
# 2. Colisões, Quiques, Atrito e Dissipação Coerente de Energia
# ==============================================================================


class TestCollisionsBouncesAndEnergyDissipation:
    """Valida colisões com o chão, perda de energia nos quiques e atrito até parar."""

    def test_ground_collision_bounces_sliding_and_energy_loss(self) -> None:
        sim = LaunchPhysicsSimulator()
        sim.start_launch(power_norm=0.90, angle_deg=45.0)
        initial_energy = sim.state.specific_mechanical_energy
        assert initial_energy > 200.0

        bounce_energies: list[float] = []
        saw_sliding = False
        prev_bounces = 0

        while not sim.state.is_stopped:
            sim.step_fixed(1)
            s = sim.state
            # Nunca atravessa o solo após tratamento de colisão
            assert s.y_m >= 0.0
            # Nunca ganha energia artificial acima da energia mecânica inicial
            assert s.specific_mechanical_energy <= initial_energy + 1e-6

            if s.bounces > prev_bounces:
                bounce_energies.append(s.specific_mechanical_energy)
                prev_bounces = s.bounces

            if s.motion_phase == FlightMotionPhase.SLIDING:
                saw_sliding = True
                assert s.y_m == 0.0
                assert s.vy_mps == 0.0

        assert len(bounce_energies) >= 2
        # Cada quique dissipa energia de forma estritamente decrescente
        assert bounce_energies[0] < initial_energy
        for e_prev, e_next in zip(bounce_energies, bounce_energies[1:]):
            assert e_next < e_prev

        assert saw_sliding is True
        assert sim.state.roll_distance_m > 0.0
        assert sim.state.specific_mechanical_energy == 0.0


# ==============================================================================
# 3. Término Garantido da Partida
# ==============================================================================


class TestGuaranteedMatchTermination:
    """Verifica parada determinística sob parâmetros extremos e todas as melhorias."""

    @pytest.mark.parametrize("power_norm", [0.05, 0.35, 0.88, 1.0])
    @pytest.mark.parametrize("angle_deg", [15.0, 42.0, 75.0])
    def test_always_terminates_cleanly(self, power_norm: float, angle_deg: float) -> None:
        max_mods = LaunchModifiers(
            speed_multiplier=1.35,
            drag_multiplier=0.65,
            restitution_bonus=0.16,
            extra_max_bounces=2,
        )
        cfg = LaunchPhysicsConfig()
        sim = LaunchPhysicsSimulator(config=cfg)
        sim.start_launch(power_norm=power_norm, angle_deg=angle_deg, modifiers=max_mods)
        final_state = sim.run_until_stopped()

        assert final_state.is_stopped is True
        assert final_state.motion_phase == FlightMotionPhase.STOPPED
        assert final_state.vx_mps == 0.0
        assert final_state.vy_mps == 0.0
        assert final_state.y_m == 0.0
        assert final_state.x_m > 0.0
        assert final_state.steps < cfg.max_simulation_steps


# ==============================================================================
# 4 & 5. Pontuação, Personalidade, Recordes, Moedas e Melhorias Desbloqueáveis
# ==============================================================================


class TestScoringRecordsAndUpgrades:
    """Valida progressão, loja de upgrades e bônus de personalidade/estágio."""

    def test_upgrades_measurably_improve_ballistic_performance(self) -> None:
        base_pet = PetState()
        upgraded_pet = PetState(
            stage=EvolutionStage.CYBER_ROOSTER,
            unlocked_upgrades=["SLINGSHOT_PRO", "AERO_CAPE", "SPRING_BOOTS"],
        )

        sim_base = LaunchPhysicsSimulator()
        sim_base.start_launch(0.85, 44.0, modifiers=compute_launch_modifiers(base_pet))
        end_base = sim_base.run_until_stopped()

        sim_upg = LaunchPhysicsSimulator()
        sim_upg.start_launch(0.85, 44.0, modifiers=compute_launch_modifiers(upgraded_pet))
        end_upg = sim_upg.run_until_stopped()

        assert end_upg.initial_speed_mps > end_base.initial_speed_mps
        assert end_upg.x_m > end_base.x_m + 15.0
        assert end_upg.bounces >= end_base.bounces

    def test_personality_modifiers_and_sweet_spot_bonus(self) -> None:
        playful_mods = compute_launch_modifiers(PetState(personality=PetPersonality.PLAYFUL), sweet_spot=True)
        curious_mods = compute_launch_modifiers(PetState(personality=PetPersonality.CURIOUS), sweet_spot=False)
        foodie_mods = compute_launch_modifiers(PetState(personality=PetPersonality.FOODIE), sweet_spot=False)
        zen_mods = compute_launch_modifiers(PetState(personality=PetPersonality.ZEN), sweet_spot=False)

        assert playful_mods.score_multiplier == pytest.approx(1.10)
        assert playful_mods.speed_multiplier == pytest.approx(1.06)  # sweet spot +6%
        assert curious_mods.coin_bonus_flat == 2
        assert foodie_mods.drag_multiplier == pytest.approx(0.92)
        assert zen_mods.speed_multiplier == pytest.approx(1.05)

    def test_engine_unlock_upgrade_validation(self) -> None:
        engine = PetEngine(state=PetState(coins=20))
        spec_pro = LAUNCH_UPGRADES[0]   # 15 moedas
        spec_cape = LAUNCH_UPGRADES[1]  # 25 moedas

        # Moedas insuficientes para Capa Aerodinâmica
        ok_cape, msg_cape = engine.unlock_launch_upgrade(spec_cape.upgrade_id, spec_cape.cost_coins)
        assert ok_cape is False
        assert "INSUFICIENTES" in msg_cape
        assert engine.state.coins == 20

        # Compra válida do Estilingue Pro
        ok_pro, _ = engine.unlock_launch_upgrade(spec_pro.upgrade_id, spec_pro.cost_coins)
        assert ok_pro is True
        assert engine.state.coins == 5
        assert spec_pro.upgrade_id in engine.state.unlocked_upgrades

        # Tentativa duplicada é bloqueada sem descontar moedas
        ok_dup, msg_dup = engine.unlock_launch_upgrade(spec_pro.upgrade_id, spec_pro.cost_coins)
        assert ok_dup is False
        assert "JA DESBLOQUEADO" in msg_dup
        assert engine.state.coins == 5


# ==============================================================================
# 6 & 7. Persistência Atômica e Integração com PetEngine
# ==============================================================================


class TestPersistenceAndPetEngineIntegration:
    """Valida fonte única de verdade no `PetState`, custo de energia, evolução e save JSON."""

    def test_pet_engine_launch_rewards_energy_cost_and_evolution(self) -> None:
        engine = PetEngine(state=PetState(xp=30, level=1, stage=EvolutionStage.EGG, energy=80.0))

        state, is_rec = engine.apply_launch_match(
            distance_m=64.5,
            score=980,
            coins_earned=18,
            xp_earned=25,
            bounces=3,
        )
        assert is_rec is True
        assert state.best_launch_distance_m == 64.5
        assert state.best_launch_score == 980
        assert state.total_launches == 1
        assert state.coins == 18
        assert state.energy == pytest.approx(72.0)  # custo moderado de 8%
        assert state.xp == 55
        assert state.level == 2
        assert state.stage == EvolutionStage.CHICK  # evoluiu de EGG -> CHICK!

        # Segunda partida com distância menor não marca novo recorde
        state2, is_rec2 = engine.apply_launch_match(
            distance_m=30.0,
            score=400,
            coins_earned=7,
            xp_earned=12,
        )
        assert is_rec2 is False
        assert state2.best_launch_distance_m == 64.5
        assert state2.total_launches == 2
        assert state2.coins == 25

    def test_pet_readiness_blocks_sleeping_sick_or_exhausted_pet(self) -> None:
        sleeping_engine = PetEngine(state=PetState(is_sleeping=True, energy=90.0))
        ok_slp, reason_slp = sleeping_engine.can_start_launch()
        assert ok_slp is False and "DORMINDO" in reason_slp

        tired_engine = PetEngine(state=PetState(energy=6.0))
        ok_trd, reason_trd = tired_engine.can_start_launch()
        assert ok_trd is False and "ENERGIA" in reason_trd

        sick_engine = PetEngine(state=PetState(health=20.0))
        ok_sck, reason_sck = sick_engine.can_start_launch()
        assert ok_sck is False and "DOENTE" in reason_sck

        # PetLaunchGame também bloqueia transição SELECT_PET -> PREP quando dormindo
        game = PetLaunchGame()
        slp_pet = sleeping_engine.state
        game.handle_key("\r", slp_pet)  # MENU -> SELECT_PET
        assert game.phase == LaunchPhase.SELECT_PET
        msg = game.handle_key("\r", slp_pet)  # Tenta ir para PREP
        assert game.phase == LaunchPhase.SELECT_PET
        assert "DORMINDO" in msg

    def test_persistence_roundtrip_and_legacy_save_compatibility(self, tmp_path: Path) -> None:
        save_file = tmp_path / "cycle4_pet.save.json"
        persistence = PetPersistence(save_file)

        rich_state = PetState(
            name="RocketPip",
            xp=120,
            level=3,
            stage=EvolutionStage.CHICK,
            coins=47,
            best_launch_distance_m=83.45,
            best_launch_score=1420,
            total_launches=5,
            unlocked_upgrades=["SLINGSHOT_PRO", "AERO_CAPE"],
        )
        persistence.save(rich_state)
        loaded = persistence.load()

        assert loaded.name == "RocketPip"
        assert loaded.coins == 47
        assert loaded.best_launch_distance_m == 83.45
        assert loaded.best_launch_score == 1420
        assert loaded.total_launches == 5
        assert loaded.unlocked_upgrades == ["SLINGSHOT_PRO", "AERO_CAPE"]

        # Save legado do Ciclo 1 (sem campos de moedas/recordes/upgrades)
        legacy_file = tmp_path / "legacy_cycle1.save.json"
        legacy_payload = {
            "schema_version": SAVE_SCHEMA_VERSION,
            "saved_at_utc": "2026-10-29T00:00:00Z",
            "pet": {
                "name": "OldPip",
                "hunger": 20.0,
                "happiness": 85.0,
                "energy": 90.0,
                "health": 95.0,
                "xp": 10,
                "level": 1,
                "stage": "EGG",
                "mood": "HAPPY",
                "personality": "CURIOUS",
                "animation": "IDLE",
                "animation_ttl_ticks": 0,
                "is_sleeping": False,
                "age_ticks": 12,
                "last_action": "FED",
                "care_counters": {"feed": 1, "play": 0, "rest": 0, "interact": 0, "heal": 0},
            },
        }
        legacy_file.write_text(json.dumps(legacy_payload), encoding="utf-8")
        legacy_loaded = PetPersistence(legacy_file).load()
        assert legacy_loaded.name == "OldPip"
        assert legacy_loaded.coins == 0
        assert legacy_loaded.best_launch_distance_m == 0.0
        assert legacy_loaded.unlocked_upgrades == []


# ==============================================================================
# 8 & 9. Entradas Unificadas (Teclado/Sim/TinyML) e Zero Comandos Duplicados
# ==============================================================================


class TestUnifiedInputAndZeroDuplicateCommands:
    """Valida equivalência entre origens de entrada, fluxo `HOLD+APPROACH` e deduplicação."""

    def test_keyboard_and_tinyml_gestures_produce_identical_gameplay(self) -> None:
        pet = PetState(name="ParityPip")
        game_kbd = PetLaunchGame()
        game_ml = PetLaunchGame()

        # Sequência equivalente até o disparo com 66% de carga (3x HOLD / 3x SPACE)
        game_kbd.handle_key("\r", pet)  # MENU -> SELECT_PET
        game_kbd.handle_key("\r", pet)  # SELECT_PET -> PREP
        for _ in range(3):
            game_kbd.handle_key(" ", pet)
        game_kbd.handle_key("\r", pet)  # Dispara!

        def ml_evt(g: GestureType, seq: int) -> None:
            ev = GestureEventPayload(gesture=g, confidence=0.91, source=GestureSource.TINYML)
            game_ml.handle_gesture(ev, pet, seq_id=seq)

        ml_evt(GestureType.APPROACH, 1)
        ml_evt(GestureType.APPROACH, 2)
        ml_evt(GestureType.HOLD, 3)
        ml_evt(GestureType.HOLD, 4)
        ml_evt(GestureType.HOLD, 5)
        ml_evt(GestureType.APPROACH, 6)

        assert game_kbd.phase == LaunchPhase.LAUNCHING
        assert game_ml.phase == LaunchPhase.LAUNCHING

        while game_kbd.phase != LaunchPhase.RESULT:
            game_kbd.update(0.10, pet)
        while game_ml.phase != LaunchPhase.RESULT:
            game_ml.update(0.10, pet)

        assert game_kbd.last_result == game_ml.last_result

    def test_retreat_cancels_charge_and_optional_impulse_launches(self) -> None:
        pet = PetState()
        game = PetLaunchGame()
        game.on_sensor_frame(SensorFramePayload(distance_cm=22.0, ir_detected=False, pot_norm=0.60))
        assert game.angle_deg == pytest.approx(50.0)

        # Avança até CHARGING e cancela com RETREAT
        game.handle_gesture(GestureEventPayload(GestureType.APPROACH, 0.9, GestureSource.TINYML), pet, seq_id=10)
        game.handle_gesture(GestureEventPayload(GestureType.APPROACH, 0.9, GestureSource.TINYML), pet, seq_id=11)
        game.handle_gesture(GestureEventPayload(GestureType.HOLD, 0.9, GestureSource.TINYML), pet, seq_id=12)
        assert game.phase == LaunchPhase.CHARGING
        assert game.charge_norm > 0.0

        game.handle_gesture(GestureEventPayload(GestureType.RETREAT, 0.9, GestureSource.TINYML), pet, seq_id=13)
        assert game.phase == LaunchPhase.PREP
        assert game.charge_norm == 0.0

        # IMPULSE opcional lança diretamente a partir de PREP
        game.handle_gesture(GestureEventPayload(GestureType.IMPULSE, 0.85, GestureSource.TINYML), pet, seq_id=14)
        assert game.phase == LaunchPhase.LAUNCHING

    def test_input_adapter_deduplicates_repeated_sequence_tokens(self) -> None:
        adapter = LaunchInputAdapter()
        evt = GestureEventPayload(GestureType.HOLD, 0.92, GestureSource.TINYML)

        first = adapter.from_gesture(evt, seq_id=42)
        second = adapter.from_gesture(evt, seq_id=42)
        assert first is not None and first.action == LaunchAction.CHARGE_POWER
        assert second is None
        assert adapter.duplicate_drops == 1

        k1 = adapter.from_key(" ", event_token="kbd:100")
        k2 = adapter.from_key(" ", event_token="kbd:100")
        assert k1 is not None
        assert k2 is None
        assert adapter.duplicate_drops == 2

    def test_end_to_end_mode_isolation_prevents_duplicate_pet_care_commands(self, tmp_path: Path) -> None:
        """Garante que gestos em PET_LAUNCH não alimentem nem coloquem o pet para dormir."""
        host_ep, dev_ep, _ = create_virtual_serial_pair()
        sensor_sim = SensorSimulator(seed=5, dropout_prob=0.0)
        sim_node = SimulatedEsp32Node(
            endpoint=dev_ep,
            sensor_source=sensor_sim,
            initial_state=PetState(name="IsoPip", hunger=40.0),
            save_path=tmp_path / "iso.save.json",
        )
        client = TerminalHostClient(host_ep)
        sim_node.boot(auto_load=False)
        client.poll_serial()

        client.set_mode(AppModeId.PET_LAUNCH)
        sim_node.step()
        client.poll_serial()

        # Navega até CHARGING e envia HOLD e RETREAT pelo barramento serial
        for g in (GestureType.APPROACH, GestureType.APPROACH, GestureType.HOLD):
            client.send_simulated_gesture(g)
            sim_node.step()
            client.poll_serial()

        assert client.pet_launch_mode.phase == LaunchPhase.CHARGING
        assert client.pet_launch_mode.charge_norm == pytest.approx(0.22)
        # HOLD não alimentou o pet!
        assert client.pet_state.care_counters["feed"] == 0
        # Carregou exatamente 1 degrau (sem comando duplicado)
        assert client.pet_state.is_sleeping is False

        client.send_simulated_gesture(GestureType.RETREAT)
        sim_node.step()
        client.poll_serial()

        assert client.pet_launch_mode.phase == LaunchPhase.PREP
        # RETREAT cancelou a carga, mas NÃO colocou o pet para dormir!
        assert client.pet_state.is_sleeping is False
        assert client.pet_state.care_counters["rest"] == 0


# ==============================================================================
# 10. Limites de Renderização: Terminal 86c, Compacto 60c, Anti-Flicker e LCD 20x4
# ==============================================================================


class TestTerminalAndLcdRenderingBoundaries:
    """Valida invariantes geométricos e ASCII imprimível em todas as fases do jogo."""

    @pytest.mark.parametrize(
        "phase",
        [
            LaunchPhase.MENU,
            LaunchPhase.SELECT_PET,
            LaunchPhase.PREP,
            LaunchPhase.CHARGING,
            LaunchPhase.LAUNCHING,
            LaunchPhase.FLIGHT,
            LaunchPhase.RESULT,
            LaunchPhase.RETURN_TO_PET,
        ],
    )
    def test_all_launch_phases_respect_lcd_20x4_and_terminal_widths(self, phase: LaunchPhase) -> None:
        pet = PetState(name="AsciiPip", coins=35, best_launch_distance_m=62.4)
        game = PetLaunchGame()
        game.charge_norm = 0.88
        game.angle_deg = 44.5
        game.physics.start_launch(0.88, 44.5)
        game.physics.step_fixed(15)
        if phase == LaunchPhase.RESULT:
            game.physics.run_until_stopped()
            game._finalize_match(pet)
        game.phase = phase

        lcd_renderer = Lcd20x4Renderer()
        lcd_frame = lcd_renderer.render_launch(
            state=pet,
            phase=phase.value,
            angle_deg=game.angle_deg,
            charge_norm=game.charge_norm,
            phys=game.physics.state,
            last_result=game.last_result,
            best_distance_m=game.best_distance_m,
            sweet_spot=game.is_in_sweet_spot(),
        )

        # Validação estrita do LCD 20x4 (4 linhas x 20 chars ASCII imprimíveis)
        assert len(lcd_frame.lines) == 4
        for line in lcd_frame.lines:
            assert len(line) == 20
            assert all(0x20 <= ord(ch) <= 0x7E for ch in line)

        term_renderer = PetLaunchAsciiRenderer()

        # Layout Padrão: todas as linhas com largura exata 86 + espelho LCD 20x4
        std_frame = term_renderer.render(game, pet, lcd_frame, frame_idx=1, compact=False)
        std_lines = std_frame.splitlines()
        assert len(std_lines) >= 24
        for tline in std_lines:
            assert len(tline) == 86
            assert all(0x20 <= ord(ch) <= 0x7E for ch in tline)
        assert "ESPELHO LCD FISICO 20x4 (HD44780):" in std_frame
        for lline in lcd_frame.lines:
            assert f"  |{lline}|" in std_frame

        # Layout Compacto: todas as linhas com largura exata 60
        cmp_frame = term_renderer.render(game, pet, lcd_frame, frame_idx=1, compact=True)
        cmp_lines = cmp_frame.splitlines()
        assert len(cmp_lines) <= 22
        for cline in cmp_lines:
            assert len(cline) == 60
            assert all(0x20 <= ord(ch) <= 0x7E for ch in cline)

    def test_compact_layout_detection_and_differential_anti_flicker_writer(self) -> None:
        assert should_use_compact_layout(86, 30, force_compact=False) is False
        assert should_use_compact_layout(72, 30, force_compact=False) is True
        assert should_use_compact_layout(90, 20, force_compact=False) is True
        assert should_use_compact_layout(120, 40, force_compact=True) is True

        buf = io.StringIO()
        writer = DifferentialTerminalWriter(buf, is_tty=True)
        frame_1 = "LINHA_A\nLINHA_B\nLINHA_C"
        changed_1 = writer.write_frame(frame_1)
        assert changed_1 == 3

        # Quadro idêntico não reescreve nenhuma linha de conteúdo (zero flicker!)
        buf.truncate(0)
        buf.seek(0)
        changed_2 = writer.write_frame(frame_1)
        assert changed_2 == 0

        # Alteração pontual reescreve apenas a linha 2
        buf.truncate(0)
        buf.seek(0)
        frame_3 = "LINHA_A\nLINHA_B_MOD\nLINHA_C"
        changed_3 = writer.write_frame(frame_3)
        assert changed_3 == 1
        ansi_out = buf.getvalue()
        assert "\x1b[2;1HLINHA_B_MOD\x1b[K" in ansi_out
        assert "LINHA_A" not in ansi_out


# ==============================================================================
# 11 & 12. Partidas Consecutivas e Demonstração Automatizada sem Hardware
# ==============================================================================


class TestConsecutiveMatchesAndAutomatedDemo:
    """Valida múltiplas partidas seguidas no barramento serial e a demo executável."""

    def test_three_consecutive_matches_with_shop_upgrade_and_return_to_pet(self, tmp_path: Path) -> None:
        host_ep, dev_ep, _ = create_virtual_serial_pair()
        sensor_sim = SensorSimulator(seed=11, dropout_prob=0.0)
        sensor_sim.set_potentiometer(0.50)  # 45 graus
        sim_node = SimulatedEsp32Node(
            endpoint=dev_ep,
            sensor_source=sensor_sim,
            initial_state=PetState(name="StreakPip", coins=5, energy=95.0),
            save_path=tmp_path / "streak.save.json",
        )
        client = TerminalHostClient(host_ep)
        sim_node.boot(auto_load=False)
        client.poll_serial()

        def pump() -> None:
            sim_node.step()
            client.poll_serial()

        client.set_mode(AppModeId.PET_LAUNCH)
        pump()

        distances: list[float] = []
        for match_idx in range(3):
            assert client.pet_launch_mode.phase == LaunchPhase.MENU
            # MENU -> SELECT_PET -> PREP
            client.send_simulated_gesture(GestureType.APPROACH)
            pump()
            client.send_simulated_gesture(GestureType.APPROACH)
            pump()
            assert client.pet_launch_mode.phase == LaunchPhase.PREP

            # Carrega força (2x na 1ª partida, 4x nas seguintes)
            holds = 2 if match_idx == 0 else 4
            for _ in range(holds):
                client.send_simulated_gesture(GestureType.HOLD)
                pump()
            assert client.pet_launch_mode.phase == LaunchPhase.CHARGING

            # Dispara!
            client.send_simulated_gesture(GestureType.APPROACH)
            pump()
            assert client.pet_launch_mode.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT)

            while client.pet_launch_mode.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT):
                client.update_game(0.10)
            pump()  # Propaga recompensa ao PetEngine autoritativo

            assert client.pet_launch_mode.phase == LaunchPhase.RESULT
            assert client.pet_launch_mode.last_result is not None
            distances.append(client.pet_launch_mode.last_result.distance_m)

            # Etapa 10: Retorna ao Menu
            client.send_simulated_gesture(GestureType.APPROACH)
            pump()
            assert client.pet_launch_mode.phase == LaunchPhase.MENU

            # Após a 2ª partida, compra melhoria na loja antes da 3ª partida
            if match_idx == 1 and client.pet_state.coins >= 15:
                client.handle_keypress("u")
                pump()
                assert "SLINGSHOT_PRO" in client.pet_state.unlocked_upgrades

        assert client.pet_state.total_launches == 3
        assert client.pet_state.best_launch_distance_m == pytest.approx(max(distances))
        # Com Estilingue Pro na 3ª partida (4x HOLD @ 45d), supera a 2ª partida (4x HOLD @ 45d)!
        assert distances[2] > distances[1] > distances[0]

        # Retorna ao modo MotionPet e valida estado LCD de Retorno ao Pet
        client.set_mode(AppModeId.MOTION_PET)
        assert "RETORNO AO MOTIONPET" in client.lcd_frame.lines[0]
        pump()

    def test_automated_pet_launch_demo_runs_without_hardware(self, tmp_path: Path) -> None:
        save_file = tmp_path / "auto_launch_demo.save.json"
        out = io.StringIO()

        rc = run_pet_launch_demo(save_path=save_file, pet_name="DemoFlyer", out=out)
        assert rc == 0
        assert save_file.is_file()

        text = out.getvalue()
        assert "=== MOTIONPET CICLO 4 -- DEMONSTRACAO AUTOMATIZADA PET LAUNCH ===" in text
        assert "STEP_1_ENTER_MODE" in text
        assert "STEP_2_SELECT_PET" in text
        assert "STEP_3_PREP" in text
        assert "STEP_4_CHARGING" in text
        assert "STEP_5_LAUNCHING" in text
        assert "STEP_6_FLIGHT" in text
        assert "STEP_7_PHYS_STOPPED" in text
        assert "STEP_8_9_RESULT" in text
        assert "STEP_10_RETURN_MENU" in text
        assert "Resumo da Partida:" in text
