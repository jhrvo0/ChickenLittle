"""Modelos de dados e enumerações do estado do Pet (independentes de interface)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionStage(str, Enum):
    EGG = "EGG"
    CHICK = "CHICK"
    CYBER_ROOSTER = "CYBER_ROOSTER"


class PetMood(str, Enum):
    ECSTATIC = "ECSTATIC"
    HAPPY = "HAPPY"
    CONTENT = "CONTENT"
    HUNGRY = "HUNGRY"
    TIRED = "TIRED"
    SAD = "SAD"
    SICK = "SICK"
    SLEEPING = "SLEEPING"


class PetPersonality(str, Enum):
    CURIOUS = "CURIOUS"
    PLAYFUL = "PLAYFUL"
    FOODIE = "FOODIE"
    ZEN = "ZEN"


class PetAnimation(str, Enum):
    IDLE = "IDLE"
    EATING = "EATING"
    PLAYING = "PLAYING"
    SLEEPING = "SLEEPING"
    PETTING = "PETTING"
    HEALING = "HEALING"
    EVOLVING = "EVOLVING"
    SICK = "SICK"


def clamp_stat(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _default_care_counters() -> dict[str, int]:
    return {
        "feed": 0,
        "play": 0,
        "rest": 0,
        "interact": 0,
        "heal": 0,
    }


LAUNCH_UPGRADE_IDS: tuple[str, ...] = (
    "SLINGSHOT_PRO",
    "AERO_CAPE",
    "SPRING_BOOTS",
)


@dataclass
class PetState:
    """Snapshot serializável e completo do estado do MotionPet."""

    name: str = "Pip"
    hunger: float = 25.0  # 0 = saciado, 100 = faminto
    happiness: float = 80.0
    energy: float = 85.0
    health: float = 95.0
    xp: int = 0
    level: int = 1
    stage: EvolutionStage = EvolutionStage.EGG
    mood: PetMood = PetMood.HAPPY
    personality: PetPersonality = PetPersonality.CURIOUS
    animation: PetAnimation = PetAnimation.IDLE
    animation_ttl_ticks: int = 0
    is_sleeping: bool = False
    age_ticks: int = 0
    last_action: str = "READY"
    care_counters: dict[str, int] = field(default_factory=_default_care_counters)
    coins: int = 0
    best_launch_distance_m: float = 0.0
    best_launch_score: int = 0
    total_launches: int = 0
    unlocked_upgrades: list[str] = field(default_factory=list)

    def clamp_all(self) -> None:
        self.hunger = round(clamp_stat(self.hunger), 2)
        self.happiness = round(clamp_stat(self.happiness), 2)
        self.energy = round(clamp_stat(self.energy), 2)
        self.health = round(clamp_stat(self.health), 2)
        self.xp = max(0, int(self.xp))
        self.level = max(1, int(self.level))
        self.age_ticks = max(0, int(self.age_ticks))
        self.animation_ttl_ticks = max(0, int(self.animation_ttl_ticks))
        self.coins = max(0, int(self.coins))
        self.best_launch_distance_m = round(max(0.0, float(self.best_launch_distance_m)), 2)
        self.best_launch_score = max(0, int(self.best_launch_score))
        self.total_launches = max(0, int(self.total_launches))
        deduped: list[str] = []
        for item in self.unlocked_upgrades:
            uid = str(item).strip().upper()
            if uid and uid not in deduped:
                deduped.append(uid)
        self.unlocked_upgrades = deduped

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hunger": round(self.hunger, 2),
            "happiness": round(self.happiness, 2),
            "energy": round(self.energy, 2),
            "health": round(self.health, 2),
            "xp": self.xp,
            "level": self.level,
            "stage": self.stage.value,
            "mood": self.mood.value,
            "personality": self.personality.value,
            "animation": self.animation.value,
            "animation_ttl_ticks": self.animation_ttl_ticks,
            "is_sleeping": self.is_sleeping,
            "age_ticks": self.age_ticks,
            "last_action": self.last_action,
            "care_counters": dict(self.care_counters),
            "coins": self.coins,
            "best_launch_distance_m": round(self.best_launch_distance_m, 2),
            "best_launch_score": self.best_launch_score,
            "total_launches": self.total_launches,
            "unlocked_upgrades": list(self.unlocked_upgrades),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PetState:
        counters = _default_care_counters()
        raw_counters = data.get("care_counters")
        if isinstance(raw_counters, dict):
            for k in counters:
                if k in raw_counters:
                    counters[k] = max(0, int(raw_counters[k]))

        raw_upgrades = data.get("unlocked_upgrades", [])
        upgrades = [str(u) for u in raw_upgrades] if isinstance(raw_upgrades, list) else []

        state = cls(
            name=str(data.get("name", "Pip"))[:12] or "Pip",
            hunger=float(data.get("hunger", 25.0)),
            happiness=float(data.get("happiness", 80.0)),
            energy=float(data.get("energy", 85.0)),
            health=float(data.get("health", 95.0)),
            xp=int(data.get("xp", 0)),
            level=int(data.get("level", 1)),
            stage=EvolutionStage(data.get("stage", EvolutionStage.EGG.value)),
            mood=PetMood(data.get("mood", PetMood.HAPPY.value)),
            personality=PetPersonality(data.get("personality", PetPersonality.CURIOUS.value)),
            animation=PetAnimation(data.get("animation", PetAnimation.IDLE.value)),
            animation_ttl_ticks=int(data.get("animation_ttl_ticks", 0)),
            is_sleeping=bool(data.get("is_sleeping", False)),
            age_ticks=int(data.get("age_ticks", 0)),
            last_action=str(data.get("last_action", "READY"))[:20],
            care_counters=counters,
            coins=int(data.get("coins", 0)),
            best_launch_distance_m=float(data.get("best_launch_distance_m", 0.0)),
            best_launch_score=int(data.get("best_launch_score", 0)),
            total_launches=int(data.get("total_launches", 0)),
            unlocked_upgrades=upgrades,
        )
        state.clamp_all()
        return state
