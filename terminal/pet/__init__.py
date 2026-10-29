"""Subsistema de domínio do Pet: estado, regras configuráveis e persistência."""

from terminal.pet.config import PetConfig
from terminal.pet.engine import PetEngine
from terminal.pet.persistence import SAVE_SCHEMA_VERSION, PersistenceError, PetPersistence
from terminal.pet.state import (
    EvolutionStage,
    PetAnimation,
    PetMood,
    PetPersonality,
    PetState,
    clamp_stat,
)

__all__ = [
    "EvolutionStage",
    "PersistenceError",
    "PetAnimation",
    "PetConfig",
    "PetEngine",
    "PetMood",
    "PetPersistence",
    "PetPersonality",
    "PetState",
    "SAVE_SCHEMA_VERSION",
    "clamp_stat",
]
