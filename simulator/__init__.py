"""Ambiente de simulação do MotionPet (sensores, detector de janela e nó ESP32 virtual)."""

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.gesture_detector_sim import SimulatedWindowGestureDetector
from simulator.sensors import DatasetReplaySource, SensorSimulator, SensorSource

__all__ = [
    "DatasetReplaySource",
    "SensorSimulator",
    "SensorSource",
    "SimulatedEsp32Node",
    "SimulatedWindowGestureDetector",
]
