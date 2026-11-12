"""Canais contínuo (distância) e discreto (infravermelho) do MotionLab.

Leitura direta, sem classificação: a distância controla parâmetros contínuos (nota, intensidade
de partículas) e o IR gera eventos discretos de toque. Gestos classificados ficam em
`recognizers.py`; misturar os dois canais foi um dos problemas da interface anterior.
"""
from __future__ import annotations

from dataclasses import dataclass

# Faixa útil do HC-SR04 nesta bancada: abaixo de ~3 cm o eco é instável; acima de ~80 cm a mão
# já não é o alvo mais próximo. Leituras fora de [MIN_VALID_CM, MAX_VALID_CM] contam como inválidas.
MIN_VALID_CM = 2.0
MAX_VALID_CM = 200.0
# Por quanto tempo a última distância válida continua valendo depois de leituras inválidas.
HOLD_LAST_VALID_MS = 300


@dataclass
class SignalSnapshot:
    raw_cm: float | None
    filtered_cm: float | None
    position: float | None  # 0 = perto (near_cm), 1 = longe (far_cm); None sem mão
    velocity_cm_s: float
    valid: bool
    present: bool  # há mão dentro da zona ativa
    ts_ms: int | None

    def to_dict(self) -> dict:
        r = lambda v, n=2: None if v is None else round(v, n)
        return {
            "raw_cm": r(self.raw_cm), "filtered_cm": r(self.filtered_cm), "position": r(self.position, 4),
            "velocity_cm_s": round(self.velocity_cm_s, 1), "valid": self.valid, "present": self.present,
        }


class SignalTracker:
    """Distância filtrada (EMA), posição normalizada na zona ativa e velocidade."""

    def __init__(self, near_cm: float = 5.0, far_cm: float = 45.0, alpha: float = 0.45) -> None:
        self.near_cm = near_cm
        self.far_cm = far_cm
        self.alpha = alpha
        self.reset()

    def reset(self) -> None:
        self._filtered: float | None = None
        self._last_valid_ts: int | None = None
        self._last_ts: int | None = None
        self._velocity = 0.0
        self.snapshot = SignalSnapshot(None, None, None, 0.0, False, False, None)

    def configure(self, near_cm: float, far_cm: float) -> None:
        if not 0 < near_cm < far_cm:
            raise ValueError("A zona ativa precisa de perto < longe.")
        self.near_cm, self.far_cm = float(near_cm), float(far_cm)

    def push(self, distance_cm: float | None, valid: bool, ts_ms: int) -> SignalSnapshot:
        ok = bool(valid) and distance_cm is not None and MIN_VALID_CM <= distance_cm <= MAX_VALID_CM
        if ok:
            previous = self._filtered
            self._filtered = distance_cm if previous is None else previous + self.alpha * (distance_cm - previous)
            if previous is not None and self._last_valid_ts is not None and ts_ms > self._last_valid_ts:
                inst = (self._filtered - previous) * 1000.0 / (ts_ms - self._last_valid_ts)
                self._velocity += 0.5 * (inst - self._velocity)
            self._last_valid_ts = ts_ms
        elif self._last_valid_ts is None or ts_ms - self._last_valid_ts > HOLD_LAST_VALID_MS:
            self._filtered = None
            self._velocity = 0.0
        self._last_ts = ts_ms
        position = None
        present = False
        if self._filtered is not None:
            span = self.far_cm - self.near_cm
            position = min(1.0, max(0.0, (self._filtered - self.near_cm) / span))
            present = self._filtered <= self.far_cm
        self.snapshot = SignalSnapshot(distance_cm if ok else None, self._filtered, position if present else None,
                                       self._velocity, ok, present, ts_ms)
        return self.snapshot


class IrTracker:
    """Bordas do TCRT5000 viram eventos discretos: toque curto (`IR_TAP`) e toque longo (`IR_HOLD`)."""

    def __init__(self, tap_max_ms: int = 600, hold_ms: int = 900) -> None:
        self.tap_max_ms = tap_max_ms
        self.hold_ms = hold_ms
        self.reset()

    def reset(self) -> None:
        self.active = False
        self._since: int | None = None
        self._hold_fired = False
        self._known = False

    def push(self, detected: bool, ts_ms: int) -> list[str]:
        """Retorna os eventos produzidos por este frame (em ordem)."""
        events: list[str] = []
        detected = bool(detected)
        if not self._known:
            # O primeiro frame só estabelece o estado: um cartão já presente ao conectar não é toque.
            self._known = True
            self.active = detected
            self._since = ts_ms
            self._hold_fired = detected
            return events
        if detected and not self.active:
            self.active, self._since, self._hold_fired = True, ts_ms, False
            events.append("IR_ON")
        elif detected and self.active and not self._hold_fired and self._since is not None and ts_ms - self._since >= self.hold_ms:
            self._hold_fired = True
            events.append("IR_HOLD")
        elif not detected and self.active:
            held = ts_ms - self._since if self._since is not None else 0
            self.active = False
            events.append("IR_OFF")
            if not self._hold_fired and held <= self.tap_max_ms:
                events.append("IR_TAP")
        return events

    def held_ms(self, ts_ms: int) -> int:
        return ts_ms - self._since if self.active and self._since is not None else 0
