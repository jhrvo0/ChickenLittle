"""Estabilizador temporal de predições, histerese e supressão de falsos disparos."""

from __future__ import annotations

from dataclasses import dataclass

from ml.schemas import StabilizerConfig


@dataclass(frozen=True)
class StabilizerDecision:
    """Decisão causal tomada sobre uma predição crua de janela pelo estabilizador."""

    emitted_label: str | None
    raw_label: str
    confidence: float
    accepted: bool
    rejection_reason: str | None


class EventStabilizer:
    """Filtro causal de eventos em nível de aplicação com rejeição, histerese e cooldown.

    Garante que oscilações temporais de janelas isoladas não disparem comandos no MotionPet,
    implementando:
    1. Rejeição de incerteza por limiar mínimo de probabilidade.
    2. Supressão silenciosa de estado neutro (NEUTRAL).
    3. Histerese temporal (mínimo de janelas consecutivas congruentes).
    4. Cooldown anti-repetição e trava de mesmo gesto sustentado.
    """

    def __init__(self, config: StabilizerConfig | None = None) -> None:
        self.config = config or StabilizerConfig()
        self.reset()

    def reset(self) -> None:
        """Reinicializa todo o histórico temporal do estabilizador."""
        self._last_emit_ts_ms: int = -10_000_000
        self._last_emitted_label: str | None = None
        self._consecutive_label: str | None = None
        self._consecutive_count: int = 0
        self._latched_label: str | None = None

    def step(self, raw_label: str, confidence: float, ts_ms: int) -> StabilizerDecision:
        """Processa causalmente uma nova janela e retorna se o evento deve ser emitido."""
        cfg = self.config
        norm_label = raw_label.strip().upper()

        # 1. Rejeição de incerteza
        if confidence < cfg.min_confidence:
            self._consecutive_count = 0
            self._consecutive_label = None
            reason = "neutral" if norm_label == "NEUTRAL" else "low_confidence"
            return StabilizerDecision(
                emitted_label=None,
                raw_label=norm_label,
                confidence=confidence,
                accepted=False,
                rejection_reason=reason,
            )

        # 2. Supressão de NEUTRAL
        if norm_label == "NEUTRAL":
            self._consecutive_count = 0
            self._consecutive_label = None
            self._latched_label = None
            return StabilizerDecision(
                emitted_label=None,
                raw_label="NEUTRAL",
                confidence=confidence,
                accepted=False,
                rejection_reason="neutral",
            )

        # 3. Estabilização temporal
        if norm_label == self._consecutive_label:
            self._consecutive_count += 1
        else:
            self._consecutive_label = norm_label
            self._consecutive_count = 1

        if self._consecutive_count < cfg.min_consecutive_windows:
            return StabilizerDecision(
                emitted_label=None,
                raw_label=norm_label,
                confidence=confidence,
                accepted=False,
                rejection_reason="unstable_state",
            )

        # 4. Anti-repetição (cooldown + trava de mesmo gesto contínuo)
        dt = ts_ms - self._last_emit_ts_ms
        if dt < cfg.cooldown_ms:
            return StabilizerDecision(
                emitted_label=None,
                raw_label=norm_label,
                confidence=confidence,
                accepted=False,
                rejection_reason="cooldown_active",
            )

        if self._latched_label == norm_label:
            if cfg.require_neutral_reset or (dt < 2 * cfg.cooldown_ms):
                return StabilizerDecision(
                    emitted_label=None,
                    raw_label=norm_label,
                    confidence=confidence,
                    accepted=False,
                    rejection_reason="cooldown_active",
                )

        # 5. Aprovação
        self._last_emit_ts_ms = ts_ms
        self._last_emitted_label = norm_label
        self._latched_label = norm_label
        return StabilizerDecision(
            emitted_label=norm_label,
            raw_label=norm_label,
            confidence=confidence,
            accepted=True,
            rejection_reason=None,
        )

    def update(self, raw_label: str, confidence: float, ts_ms: int) -> StabilizerDecision:
        """Alias compatível com `MLGestureClassifier` para `step()`."""
        return self.step(raw_label=raw_label, confidence=confidence, ts_ms=ts_ms)
