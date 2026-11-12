"""MotionLab: sensores → reconhecimento (regras, ML no host, TinyML na ESP32) → ações dos módulos.

Ver `docs/motionlab_arquitetura.md`.
"""
from terminal.motionlab.engine import MotionEngine

__all__ = ["MotionEngine"]
