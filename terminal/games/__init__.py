"""Minijogos do MotionPet."""

from terminal.games.input_adapter import (
    CalibratedSensorAim,
    LaunchAction,
    LaunchInputAdapter,
    UnifiedLaunchInput,
)
from terminal.games.pet_launch import (
    LAUNCH_UPGRADES,
    LaunchPhase,
    LaunchResult,
    LaunchUpgradeSpec,
    PetLaunchGame,
    PetLaunchMode,
    compute_launch_modifiers,
    simulate_launch_trajectory,
)
from terminal.games.physics import (
    CourseStar,
    FlightMotionPhase,
    HorizontalCamera,
    LaunchModifiers,
    LaunchPhysicsConfig,
    LaunchPhysicsSimulator,
    LaunchPhysicsState,
)

__all__ = [
    "CalibratedSensorAim",
    "CourseStar",
    "FlightMotionPhase",
    "HorizontalCamera",
    "LAUNCH_UPGRADES",
    "LaunchAction",
    "LaunchInputAdapter",
    "LaunchModifiers",
    "LaunchPhase",
    "LaunchPhysicsConfig",
    "LaunchPhysicsSimulator",
    "LaunchPhysicsState",
    "LaunchResult",
    "LaunchUpgradeSpec",
    "PetLaunchGame",
    "PetLaunchMode",
    "UnifiedLaunchInput",
    "compute_launch_modifiers",
    "simulate_launch_trajectory",
]
