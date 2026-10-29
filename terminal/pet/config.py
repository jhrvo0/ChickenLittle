"""Configurações parametrizáveis das regras de evolução, necessidades e gestos do Pet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from terminal.communication.protocol import CommandType, GestureType


def _default_gesture_map() -> dict[str, str]:
    return {
        GestureType.APPROACH.value: CommandType.INTERACT.value,
        GestureType.HOLD.value: CommandType.FEED.value,
        GestureType.RETREAT.value: CommandType.REST.value,
        GestureType.IMPULSE.value: CommandType.PLAY.value,
        GestureType.DOUBLE.value: CommandType.HEAL.value,
    }


@dataclass(frozen=True)
class PetConfig:
    """Parâmetros configuráveis da máquina de estados do MotionPet.

    Convenção de escalas [0.0, 100.0]:
    - `hunger`: 0.0 = totalmente saciado, 100.0 = faminto crítico.
    - `happiness`, `energy`, `health`: 100.0 = ótimo, 0.0 = crítico.
    """

    default_name: str = "Pip"

    # Taxas passivas por tick de simulação
    hunger_per_tick: float = 0.8
    sleep_hunger_factor: float = 0.4
    happiness_decay_per_tick: float = 0.5
    energy_decay_per_tick: float = 0.6
    sleep_energy_recovery_per_tick: float = 3.5

    # Limiares de saúde e bem-estar
    critical_hunger_threshold: float = 80.0
    critical_energy_threshold: float = 15.0
    critical_happiness_threshold: float = 20.0
    health_penalty_per_tick: float = 1.2
    health_regen_per_tick: float = 0.4
    sick_health_threshold: float = 35.0

    # Efeitos das interações
    feed_hunger_delta: float = -28.0
    feed_health_bonus: float = 2.0
    feed_xp: int = 12

    play_happiness_delta: float = 22.0
    play_energy_delta: float = -14.0
    play_hunger_delta: float = 8.0
    play_min_energy: float = 12.0
    play_xp: int = 18

    interact_happiness_delta: float = 12.0
    interact_energy_delta: float = -2.0
    interact_xp: int = 10

    heal_health_delta: float = 30.0
    heal_happiness_delta: float = 4.0
    heal_xp: int = 15

    rest_xp: int = 5

    # Minijogo Pet Launch (custo moderado e recompensas de bem-estar)
    launch_energy_cost: float = 8.0
    launch_min_energy: float = 10.0
    launch_hunger_delta: float = 4.0
    launch_happiness_bonus: float = 14.0
    launch_record_happiness_bonus: float = 22.0

    # Evolução e níveis
    xp_per_level: int = 50
    chick_min_level: int = 2
    cyber_rooster_min_level: int = 5
    animation_default_ttl: int = 4

    # Mapeamento configurável Gesto -> Comando
    gesture_to_command: dict[str, str] = field(default_factory=_default_gesture_map)

    def resolve_gesture(self, gesture: GestureType) -> CommandType | None:
        cmd_name = self.gesture_to_command.get(gesture.value)
        if not cmd_name:
            return None
        return CommandType(cmd_name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PetConfig:
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**filtered)
