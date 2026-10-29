"""Testes exaustivos da máquina de estados do Pet, regras de evolução e persistência atômica.

Cobre:
- Regras de decaimento temporal (tick), regeneração/penalidade de saúde e sono.
- Auto-despertar ao atingir 100% de energia e carinho suave sem acordar.
- Ações FEED, PLAY (com validação de energia mínima), REST, INTERACT, HEAL, RESET.
- Clamping de status entre 0 e 100.
- Evolução de estágios: EGG (nível 1) -> CHICK (nível 2) -> CYBER_ROOSTER (nível 5).
- Emergência de personalidades: PLAYFUL, FOODIE, ZEN e CURIOUS.
- Hierarquia estrita de transições de humor: SLEEPING, SICK, HUNGRY, TIRED, SAD, ECSTATIC, HAPPY, CONTENT.
- Mapeamento de gestos e filtro de confiança mínima.
- PetPersistence atômica: save, load, load_or_create e tratamento de erros (PersistenceError).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from terminal.communication.protocol import (
    CommandType,
    GestureEventPayload,
    GestureSource,
    GestureType,
)
from terminal.pet.config import PetConfig
from terminal.pet.engine import PetEngine
from terminal.pet.persistence import (
    SAVE_SCHEMA_VERSION,
    PersistenceError,
    PetPersistence,
)
from terminal.pet.state import (
    EvolutionStage,
    PetAnimation,
    PetMood,
    PetPersonality,
    PetState,
)


# ==============================================================================
# 1. Testes de Decaimento Temporal, Sono e Saúde (tick)
# ==============================================================================


class TestPetEngineTicksAndNeeds:
    """Valida o avanço temporal determinístico e as necessidades biológicas do Pet."""

    def test_awake_tick_decays_stats_and_increments_age(self) -> None:
        engine = PetEngine()
        initial_hunger = engine.state.hunger
        initial_happiness = engine.state.happiness
        initial_energy = engine.state.energy
        initial_age = engine.state.age_ticks

        engine.tick(1)

        cfg = engine.config
        assert engine.state.age_ticks == initial_age + 1
        assert engine.state.hunger == pytest.approx(initial_hunger + cfg.hunger_per_tick, 0.01)
        assert engine.state.happiness == pytest.approx(
            initial_happiness - cfg.happiness_decay_per_tick, 0.01
        )
        assert engine.state.energy == pytest.approx(initial_energy - cfg.energy_decay_per_tick, 0.01)

    def test_sleeping_tick_recovers_energy_and_slows_hunger(self) -> None:
        state = PetState(is_sleeping=True, energy=50.0, hunger=20.0, happiness=70.0)
        engine = PetEngine(state=state)
        cfg = engine.config

        engine.tick(1)

        # Durante o sono, felicidade não decai
        assert engine.state.happiness == 70.0
        # Fome aumenta em ritmo reduzido
        assert engine.state.hunger == pytest.approx(20.0 + cfg.hunger_per_tick * cfg.sleep_hunger_factor, 0.01)
        # Energia se recupera
        assert engine.state.energy == pytest.approx(50.0 + cfg.sleep_energy_recovery_per_tick, 0.01)

    def test_sleeping_auto_wakes_up_when_energy_reaches_100(self) -> None:
        state = PetState(is_sleeping=True, energy=98.0)
        engine = PetEngine(state=state)

        # cfg.sleep_energy_recovery_per_tick é 3.5 -> 98 + 3.5 = 101.5 >= 100
        engine.tick(1)

        assert engine.state.energy == 100.0
        assert engine.state.is_sleeping is False
        assert engine.state.last_action == "WOKE UP"

    def test_health_penalty_when_in_distress(self) -> None:
        cfg = PetConfig()
        # Caso 1: Fome crítica (>= 80)
        state_hungry = PetState(hunger=85.0, health=90.0, happiness=80.0, energy=80.0)
        eng1 = PetEngine(state=state_hungry, config=cfg)
        eng1.tick(1)
        assert eng1.state.health == pytest.approx(90.0 - cfg.health_penalty_per_tick, 0.01)

        # Caso 2: Energia crítica (<= 15)
        state_tired = PetState(hunger=30.0, health=90.0, happiness=80.0, energy=10.0)
        eng2 = PetEngine(state=state_tired, config=cfg)
        eng2.tick(1)
        assert eng2.state.health == pytest.approx(90.0 - cfg.health_penalty_per_tick, 0.01)

        # Caso 3: Felicidade crítica (<= 20)
        state_sad = PetState(hunger=30.0, health=90.0, happiness=15.0, energy=80.0)
        eng3 = PetEngine(state=state_sad, config=cfg)
        eng3.tick(1)
        assert eng3.state.health == pytest.approx(90.0 - cfg.health_penalty_per_tick, 0.01)

    def test_health_regeneration_when_thriving(self) -> None:
        cfg = PetConfig()
        # Thriving condition: hunger < 40 and energy > 50 and happiness > 60
        thriving_state = PetState(hunger=20.0, energy=80.0, happiness=90.0, health=75.0)
        engine = PetEngine(state=thriving_state, config=cfg)
        engine.tick(1)
        assert engine.state.health == pytest.approx(75.0 + cfg.health_regen_per_tick, 0.01)

    def test_animation_ttl_decrements_to_zero(self) -> None:
        state = PetState(animation=PetAnimation.EATING, animation_ttl_ticks=2)
        engine = PetEngine(state=state)

        engine.tick(1)
        assert engine.state.animation == PetAnimation.EATING
        assert engine.state.animation_ttl_ticks == 1

        engine.tick(1)
        assert engine.state.animation_ttl_ticks == 0
        # Ao zerar TTL, volta para IDLE (se humor não for SICK)
        assert engine.state.animation == PetAnimation.IDLE

    def test_stat_clamping_limits(self) -> None:
        # Nenhum status pode extrapolar [0.0, 100.0]
        state = PetState(hunger=99.5, happiness=0.2, energy=0.1, health=1.0)
        engine = PetEngine(state=state)
        engine.tick(5)
        assert engine.state.hunger <= 100.0
        assert engine.state.happiness >= 0.0
        assert engine.state.energy >= 0.0
        assert engine.state.health >= 0.0


# ==============================================================================
# 2. Testes de Comandos de Interação
# ==============================================================================


class TestPetEngineCommands:
    """Valida efeitos de cada comando no estado, contadores e XP."""

    def test_feed_command(self) -> None:
        state = PetState(hunger=50.0, health=70.0, is_sleeping=True)
        engine = PetEngine(state=state)
        cfg = engine.config

        engine.apply_command(CommandType.FEED)

        # Alimentar acorda pet adormecido
        assert engine.state.is_sleeping is False
        assert engine.state.hunger == pytest.approx(50.0 + cfg.feed_hunger_delta, 0.01)
        assert engine.state.health == pytest.approx(70.0 + cfg.feed_health_bonus, 0.01)
        assert engine.state.care_counters["feed"] == 1
        assert engine.state.xp == cfg.feed_xp
        assert engine.state.animation == PetAnimation.EATING
        assert "FED" in engine.state.last_action

    def test_play_command_when_energetic(self) -> None:
        state = PetState(happiness=50.0, energy=60.0, hunger=20.0)
        engine = PetEngine(state=state)
        cfg = engine.config

        engine.apply_command(CommandType.PLAY)

        assert engine.state.happiness == pytest.approx(50.0 + cfg.play_happiness_delta, 0.01)
        assert engine.state.energy == pytest.approx(60.0 + cfg.play_energy_delta, 0.01)
        assert engine.state.hunger == pytest.approx(20.0 + cfg.play_hunger_delta, 0.01)
        assert engine.state.care_counters["play"] == 1
        assert engine.state.xp == cfg.play_xp
        assert engine.state.animation == PetAnimation.PLAYING
        assert "PLAYED" in engine.state.last_action

    def test_play_command_rejected_when_too_tired(self) -> None:
        cfg = PetConfig()
        state = PetState(energy=cfg.play_min_energy - 1.0, happiness=50.0, xp=0)
        engine = PetEngine(state=state, config=cfg)

        engine.apply_command(CommandType.PLAY)

        # Não deve gastar energia, nem dar felicidade, nem computar XP
        assert engine.state.energy == cfg.play_min_energy - 1.0
        assert engine.state.happiness == 50.0
        assert engine.state.xp == 0
        assert engine.state.care_counters["play"] == 0
        assert "TOO TIRED" in engine.state.last_action

    def test_rest_command_toggles_sleep(self) -> None:
        engine = PetEngine()
        assert not engine.state.is_sleeping

        # Dormir
        engine.apply_command(CommandType.REST)
        assert engine.state.is_sleeping is True
        assert engine.state.animation == PetAnimation.SLEEPING
        assert engine.state.care_counters["rest"] == 1
        assert "SLEEPING" in engine.state.last_action

        # Acordar
        engine.apply_command(CommandType.REST)
        assert engine.state.is_sleeping is False
        assert engine.state.animation == PetAnimation.IDLE
        assert "AWAKE" in engine.state.last_action

    def test_interact_command_awake_vs_sleeping(self) -> None:
        cfg = PetConfig()
        # 1. Acordado: carinho completo
        eng_awake = PetEngine(config=cfg)
        eng_awake.apply_command(CommandType.INTERACT)
        assert eng_awake.state.animation == PetAnimation.PETTING
        assert "PETTED" in eng_awake.state.last_action

        # 2. Dormindo: carinho suave não acorda o pet
        eng_sleep = PetEngine(state=PetState(is_sleeping=True, happiness=50.0), config=cfg)
        eng_sleep.apply_command(CommandType.INTERACT)
        assert eng_sleep.state.is_sleeping is True
        assert eng_sleep.state.happiness == pytest.approx(
            50.0 + cfg.interact_happiness_delta * 0.5, 0.01
        )
        assert "GENTLE PET" in eng_sleep.state.last_action

    def test_heal_command(self) -> None:
        state = PetState(health=20.0, happiness=40.0)
        engine = PetEngine(state=state)
        cfg = engine.config

        engine.apply_command(CommandType.HEAL)

        assert engine.state.health == pytest.approx(20.0 + cfg.heal_health_delta, 0.01)
        assert engine.state.happiness == pytest.approx(40.0 + cfg.heal_happiness_delta, 0.01)
        assert engine.state.care_counters["heal"] == 1
        assert engine.state.xp == cfg.heal_xp
        assert engine.state.animation == PetAnimation.HEALING
        assert "HEALED" in engine.state.last_action

    def test_reset_command_restores_defaults(self) -> None:
        state = PetState(name="MyPet", level=4, xp=150, hunger=90.0, stage=EvolutionStage.CHICK)
        engine = PetEngine(state=state)

        engine.apply_command(CommandType.RESET)

        assert engine.state.name == "MyPet"
        assert engine.state.level == 1
        assert engine.state.xp == 0
        assert engine.state.stage == EvolutionStage.EGG
        assert engine.state.last_action == "RESET"


# ==============================================================================
# 3. Testes de Evolução, Personalidade e Humor
# ==============================================================================


class TestEvolutionAndPersonality:
    """Valida transição de estágios (EGG -> CHICK -> CYBER_ROOSTER) e personalidades."""

    def test_stage_evolution_at_level_2_and_level_5(self) -> None:
        engine = PetEngine()
        assert engine.state.stage == EvolutionStage.EGG
        assert engine.state.level == 1

        # Acumula XP para nível 2 (xp_per_level = 50)
        # Usamos HEAL (15 xp) * 4 = 60 xp -> nível 2
        for _ in range(4):
            engine.apply_command(CommandType.HEAL)

        assert engine.state.level == 2
        assert engine.state.stage == EvolutionStage.CHICK
        assert engine.state.animation == PetAnimation.EVOLVING
        assert "EVOLVED" in engine.state.last_action

        # Acumula XP para nível 5 (>= 200 xp)
        # Nível 5 exige xp // 50 >= 4 -> xp >= 200
        while engine.state.level < 5:
            engine.apply_command(CommandType.HEAL)

        assert engine.state.level >= 5
        assert engine.state.stage == EvolutionStage.CYBER_ROOSTER

    @pytest.mark.parametrize(
        ("dominant_action", "expected_personality"),
        [
            (CommandType.PLAY, PetPersonality.PLAYFUL),
            (CommandType.FEED, PetPersonality.FOODIE),
            (CommandType.REST, PetPersonality.ZEN),
            (CommandType.INTERACT, PetPersonality.CURIOUS),
        ],
    )
    def test_personality_emergence_after_threshold(
        self, dominant_action: CommandType, expected_personality: PetPersonality
    ) -> None:
        engine = PetEngine()
        # Exige total_actions >= 3. Como REST alterna entre dormir e acordar
        # (incrementando o contador de rest apenas ao adormecer), executamos até
        # que o total de ações de cuidado atinja 3.
        while sum(engine.state.care_counters.values()) < 3:
            engine.state.energy = 90.0
            engine.apply_command(dominant_action)

        assert engine.state.personality == expected_personality

    def test_mood_priority_hierarchy(self) -> None:
        cfg = PetConfig()

        # 1. Sono domina qualquer outro estado
        s1 = PetState(is_sleeping=True, health=10.0, hunger=99.0)
        e1 = PetEngine(state=s1, config=cfg)
        assert e1.state.mood == PetMood.SLEEPING

        # 2. SICK quando saúde <= sick_health_threshold (35.0)
        s2 = PetState(is_sleeping=False, health=30.0, hunger=90.0)
        e2 = PetEngine(state=s2, config=cfg)
        assert e2.state.mood == PetMood.SICK

        # 3. HUNGRY quando fome >= critical_hunger_threshold (80.0)
        s3 = PetState(is_sleeping=False, health=80.0, hunger=85.0, energy=10.0)
        e3 = PetEngine(state=s3, config=cfg)
        assert e3.state.mood == PetMood.HUNGRY

        # 4. TIRED quando energia <= critical_energy_threshold (15.0)
        s4 = PetState(is_sleeping=False, health=80.0, hunger=50.0, energy=12.0, happiness=10.0)
        e4 = PetEngine(state=s4, config=cfg)
        assert e4.state.mood == PetMood.TIRED

        # 5. SAD quando felicidade <= critical_happiness_threshold (20.0)
        s5 = PetState(is_sleeping=False, health=80.0, hunger=50.0, energy=60.0, happiness=18.0)
        e5 = PetEngine(state=s5, config=cfg)
        assert e5.state.mood == PetMood.SAD

        # 6. ECSTATIC quando bem-estar geral é excepcional
        s6 = PetState(is_sleeping=False, health=95.0, hunger=20.0, energy=85.0, happiness=90.0)
        e6 = PetEngine(state=s6, config=cfg)
        assert e6.state.mood == PetMood.ECSTATIC

        # 7. HAPPY quando parâmetros são bons
        s7 = PetState(is_sleeping=False, health=70.0, hunger=45.0, energy=50.0, happiness=65.0)
        e7 = PetEngine(state=s7, config=cfg)
        assert e7.state.mood == PetMood.HAPPY

        # 8. CONTENT quando intermediário
        s8 = PetState(is_sleeping=False, health=70.0, hunger=58.0, energy=50.0, happiness=55.0)
        e8 = PetEngine(state=s8, config=cfg)
        assert e8.state.mood == PetMood.CONTENT


# ==============================================================================
# 4. Testes de Mapeamento de Gestos
# ==============================================================================


class TestGestureMapping:
    """Valida a tradução de eventos de gestos em comandos e filtro de confiança."""

    @pytest.mark.parametrize(
        ("gesture", "expected_cmd"),
        [
            (GestureType.APPROACH, CommandType.INTERACT),
            (GestureType.HOLD, CommandType.FEED),
            (GestureType.RETREAT, CommandType.REST),
            (GestureType.IMPULSE, CommandType.PLAY),
            (GestureType.DOUBLE, CommandType.HEAL),
        ],
    )
    def test_default_gestures_resolve_to_commands(
        self, gesture: GestureType, expected_cmd: CommandType
    ) -> None:
        engine = PetEngine()
        event = GestureEventPayload(
            gesture=gesture,
            confidence=0.85,
            source=GestureSource.SIM_SENSOR,
        )
        resolved = engine.apply_gesture(event, min_confidence=0.55)
        assert resolved == expected_cmd

    def test_gesture_rejected_below_min_confidence(self) -> None:
        engine = PetEngine()
        event = GestureEventPayload(
            gesture=GestureType.HOLD,
            confidence=0.50,  # abaixo de 0.55
            source=GestureSource.SIM_SENSOR,
        )
        resolved = engine.apply_gesture(event, min_confidence=0.55)
        assert resolved is None
        assert engine.state.care_counters["feed"] == 0

    def test_neutral_gesture_has_no_command_mapping(self) -> None:
        engine = PetEngine()
        event = GestureEventPayload(
            gesture=GestureType.NEUTRAL,
            confidence=0.99,
            source=GestureSource.SIM_SENSOR,
        )
        resolved = engine.apply_gesture(event)
        assert resolved is None


# ==============================================================================
# 5. Testes de Persistência Atômica (PetPersistence)
# ==============================================================================


class TestPetPersistence:
    """Valida salvamento, carregamento, isolamento atômico e tratamento de erros."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        save_file = tmp_path / "subdir" / "my_pet.save.json"
        persistence = PetPersistence(save_file)
        assert not persistence.exists()

        original_state = PetState(
            name="AlphaChick",
            hunger=42.0,
            happiness=77.0,
            energy=65.0,
            health=88.0,
            xp=64,
            level=2,
            stage=EvolutionStage.CHICK,
            mood=PetMood.HAPPY,
            personality=PetPersonality.PLAYFUL,
            care_counters={"feed": 3, "play": 8, "rest": 1, "interact": 2, "heal": 0},
        )

        saved_path = persistence.save(original_state)
        assert saved_path == save_file
        assert persistence.exists()
        # Nenhum arquivo temporário deve sobrar
        assert not save_file.with_suffix(save_file.suffix + ".tmp").exists()

        loaded_state = persistence.load()
        assert loaded_state.name == "AlphaChick"
        assert loaded_state.hunger == 42.0
        assert loaded_state.happiness == 77.0
        assert loaded_state.energy == 65.0
        assert loaded_state.health == 88.0
        assert loaded_state.xp == 64
        assert loaded_state.level == 2
        assert loaded_state.stage == EvolutionStage.CHICK
        assert loaded_state.personality == PetPersonality.PLAYFUL
        assert loaded_state.care_counters["play"] == 8

    def test_load_or_create(self, tmp_path: Path) -> None:
        save_file = tmp_path / "auto.save.json"
        persistence = PetPersistence(save_file)

        # 1. Arquivo inexistente -> cria PetState novo com loaded=False
        state, loaded = persistence.load_or_create(default_name="Newborn")
        assert not loaded
        assert state.name == "Newborn"
        assert state.level == 1

        # 2. Salva e chama load_or_create novamente -> loaded=True
        state.xp = 100
        persistence.save(state)
        loaded_state, loaded = persistence.load_or_create()
        assert loaded is True
        assert loaded_state.name == "Newborn"
        assert loaded_state.xp == 100

    def test_load_nonexistent_file_raises_persistence_error(self, tmp_path: Path) -> None:
        persistence = PetPersistence(tmp_path / "does_not_exist.json")
        with pytest.raises(PersistenceError, match="Arquivo de save não encontrado"):
            persistence.load()

    def test_load_corrupted_json_raises_persistence_error(self, tmp_path: Path) -> None:
        corrupted_file = tmp_path / "corrupt.json"
        corrupted_file.write_text("{invalid_json: 123", encoding="utf-8")
        persistence = PetPersistence(corrupted_file)

        with pytest.raises(PersistenceError, match="inválido ou corrompido"):
            persistence.load()

    def test_load_root_not_dict_raises_persistence_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad_root.json"
        bad_file.write_text("[1, 2, 3]", encoding="utf-8")
        persistence = PetPersistence(bad_file)

        with pytest.raises(PersistenceError, match="deve ser um objeto JSON"):
            persistence.load()

    def test_load_incompatible_schema_version_raises_persistence_error(
        self, tmp_path: Path
    ) -> None:
        bad_version_file = tmp_path / "version2.json"
        payload = {
            "schema_version": 99,
            "pet": PetState().to_dict(),
        }
        bad_version_file.write_text(json.dumps(payload), encoding="utf-8")
        persistence = PetPersistence(bad_version_file)

        with pytest.raises(PersistenceError, match="Versão de save incompatível"):
            persistence.load()

    def test_load_missing_or_bad_pet_data_raises_persistence_error(
        self, tmp_path: Path
    ) -> None:
        missing_pet_file = tmp_path / "no_pet.json"
        missing_pet_file.write_text(
            json.dumps({"schema_version": SAVE_SCHEMA_VERSION, "pet": "string_not_dict"}),
            encoding="utf-8",
        )
        persistence = PetPersistence(missing_pet_file)

        with pytest.raises(PersistenceError, match="Campo 'pet' ausente ou inválido"):
            persistence.load()
