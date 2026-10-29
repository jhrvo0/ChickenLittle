"""Contrato base modular para os modos de aplicação do MotionPet."""

from __future__ import annotations

from abc import ABC, abstractmethod

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    SensorFramePayload,
)


class BaseAppMode(ABC):
    """Interface comum para modos desacoplados alimentados por sensores e gestos."""

    mode_id: AppModeId
    title: str
    lifecycle_stage: str

    @abstractmethod
    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        """Recebe telemetria contínua (HC-SR04, IR, potenciômetro)."""

    @abstractmethod
    def on_gesture_event(self, event: GestureEventPayload) -> str:
        """Processa um evento de gesto classificado (simulado ou TinyML)."""

    @abstractmethod
    def status_banner(self) -> str:
        """Retorna resumo textual de 1 a 3 linhas para o HUD do terminal."""
