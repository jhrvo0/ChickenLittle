"""Detector heurístico de janela deslizante exclusivo para o ambiente de simulação (Ciclo 1).

IMPORTANTE: Este módulo NÃO é o modelo de Machine Learning. Ele existe apenas para fechar
o loop de simulação de séries temporais no Ciclo 1 (`source=GestureSource.SIM_SENSOR`) antes
da coleta física e treinamento dos modelos reais no Ciclo 2/5.
"""

from __future__ import annotations

import statistics
from collections import deque

from terminal.communication.protocol import (
    GestureEventPayload,
    GestureSource,
    GestureType,
    SensorFramePayload,
)


class SimulatedWindowGestureDetector:
    """Analisa janelas temporais 1D sintéticas para emitir `GestureEventPayload` em simulação."""

    def __init__(
        self,
        window_size: int = 8,
        sample_period_ms: int = 60,
        cooldown_frames: int = 8,
    ) -> None:
        self.window_size = max(4, window_size)
        self.sample_period_ms = sample_period_ms
        self.cooldown_frames = max(1, cooldown_frames)
        self._buffer: deque[float] = deque(maxlen=self.window_size)
        self._cooldown = 0

    def reset(self) -> None:
        self._buffer.clear()
        self._cooldown = 0

    def push(self, frame: SensorFramePayload) -> GestureEventPayload | None:
        if self._cooldown > 0:
            self._cooldown -= 1

        if not frame.valid_ultrasonic or frame.distance_cm is None:
            return None

        self._buffer.append(frame.distance_cm)
        if len(self._buffer) < self.window_size or self._cooldown > 0:
            return None

        samples = list(self._buffer)
        first_half = statistics.fmean(samples[: self.window_size // 2])
        second_half = statistics.fmean(samples[self.window_size // 2 :])
        delta = second_half - first_half
        spread = max(samples) - min(samples)
        mean_dist = statistics.fmean(samples)
        win_ms = self.window_size * self.sample_period_ms

        # Zona ativa de interação: abaixo de 50 cm
        if mean_dist > 55.0:
            return None

        # Aproximação clara: distância cai significativamente
        if delta <= -10.0:
            self._cooldown = self.cooldown_frames
            conf = min(0.95, 0.65 + abs(delta) / 60.0)
            return GestureEventPayload(
                gesture=GestureType.APPROACH,
                confidence=round(conf, 2),
                source=GestureSource.SIM_SENSOR,
                window_ms=win_ms,
            )

        # Afastamento claro: distância sobe significativamente
        if delta >= 10.0:
            self._cooldown = self.cooldown_frames
            conf = min(0.95, 0.65 + abs(delta) / 60.0)
            return GestureEventPayload(
                gesture=GestureType.RETREAT,
                confidence=round(conf, 2),
                source=GestureSource.SIM_SENSOR,
                window_ms=win_ms,
            )

        # Mão estacionária próxima (HOLD): baixa variância entre 8 cm e 28 cm
        if 8.0 <= mean_dist <= 28.0 and spread <= 4.0:
            self._cooldown = self.cooldown_frames
            return GestureEventPayload(
                gesture=GestureType.HOLD,
                confidence=0.88,
                source=GestureSource.SIM_SENSOR,
                window_ms=win_ms,
            )

        return None
