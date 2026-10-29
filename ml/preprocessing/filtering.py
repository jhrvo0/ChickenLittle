"""Filtragem estritamente causal de leituras ultrassônicas 1D (sem acesso a amostras futuras)."""

from __future__ import annotations

from collections import deque
from typing import Sequence

from ml.schemas import PreprocessingConfig


def _median_of_up_to_3(values: Sequence[float]) -> float:
    n = len(values)
    if n == 1:
        return values[0]
    if n == 2:
        return 0.5 * (values[0] + values[1])
    a, b, c = values[0], values[1], values[2]
    if a > b:
        a, b = b, a
    if b > c:
        b, c = c, b
    if a > b:
        a, b = b, a
    return b


class CausalSignalFilter:
    """Filtro online passo a passo reproduzível em C++ no ESP32 sem olhar para o futuro.

    Pipeline por amostra `t`:
    1. Validação física `[min_valid_cm, max_valid_cm]` e `valid_ultrasonic`.
    2. Retenção causal de ordem zero (`max_hold_steps`) para dropouts curtos; saturação em
       `saturation_cm` para timeouts prolongados ou ausência de alvo.
    3. Mediana móvel causal de até 3 amostras `(x[t-2], x[t-1], x[t])`.
    4. Suavização exponencial causal (EMA `alpha`).
    """

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()
        self._last_valid: float | None = None
        self._hold_count: int = 0
        self._history: deque[float] = deque(maxlen=max(1, min(3, self.config.median_kernel)))
        self._ema: float | None = None

    def reset(self) -> None:
        self._last_valid = None
        self._hold_count = 0
        self._history.clear()
        self._ema = None

    def step(self, distance_cm: float | None, valid_ultrasonic: bool = True) -> tuple[float, bool]:
        """Processa uma única amostra causalmente.

        Retorna `(filtered_distance_cm, was_invalid_raw)`.
        """
        cfg = self.config
        is_valid = (
            bool(valid_ultrasonic)
            and distance_cm is not None
            and (cfg.min_valid_cm <= float(distance_cm) <= cfg.max_valid_cm)
        )

        if is_valid and distance_cm is not None:
            raw_val = float(distance_cm)
            self._last_valid = raw_val
            self._hold_count = 0
            was_invalid = False
        else:
            was_invalid = True
            if self._last_valid is not None and self._hold_count < cfg.max_hold_steps:
                self._hold_count += 1
                raw_val = self._last_valid
            else:
                raw_val = cfg.saturation_cm

        clamped = max(cfg.min_valid_cm, min(cfg.saturation_cm, raw_val))
        self._history.append(clamped)
        med = _median_of_up_to_3(tuple(self._history))

        if self._ema is None:
            self._ema = med
        else:
            alpha = cfg.ema_alpha
            self._ema = alpha * med + (1.0 - alpha) * self._ema

        return self._ema, was_invalid
