"""Interface modular do modo Air Music (implementação completa prevista para o Ciclo 6)."""

from __future__ import annotations

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    GestureType,
    SensorFramePayload,
)
from terminal.modes.base import BaseAppMode

_PENTATONIC_NOTES: tuple[tuple[str, float], ...] = (
    ("C4", 261.63),
    ("D4", 293.66),
    ("E4", 329.63),
    ("G4", 392.00),
    ("A4", 440.00),
    ("C5", 523.25),
    ("D5", 587.33),
    ("E5", 659.25),
)


class AirMusicMode(BaseAppMode):
    """Mapeia distância 1D e gestos para parâmetros musicais (stub modular — Ciclo 6)."""

    mode_id = AppModeId.AIR_MUSIC
    title = "Air Music (Instrumento Sem Contato)"
    lifecycle_stage = "INTERFACE_MODULAR_CICLO_6"

    def __init__(self) -> None:
        self.current_note: str = "---"
        self.current_freq_hz: float = 0.0
        self.volume_pct: float = 50.0
        self.muted: bool = False
        self.last_trigger: str = "AGUARDANDO GESTO"

    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        self.volume_pct = round(frame.pot_norm * 100.0, 1)
        if not frame.valid_ultrasonic or frame.distance_cm is None:
            return
        # Faixa útil musical: 8 cm a 48 cm
        clamped = max(8.0, min(48.0, frame.distance_cm))
        ratio = (clamped - 8.0) / 40.0
        idx = min(len(_PENTATONIC_NOTES) - 1, int(ratio * len(_PENTATONIC_NOTES)))
        self.current_note, self.current_freq_hz = _PENTATONIC_NOTES[idx]

    def on_gesture_event(self, event: GestureEventPayload) -> str:
        if event.gesture == GestureType.HOLD:
            self.muted = not self.muted
            self.last_trigger = "MUTE ON" if self.muted else "MUTE OFF"
        elif event.gesture in (GestureType.APPROACH, GestureType.IMPULSE):
            self.last_trigger = f"TRIGGER {self.current_note} ({self.current_freq_hz:.1f}Hz)"
        elif event.gesture == GestureType.RETREAT:
            self.last_trigger = "RELEASE SUSTAIN"
        return self.last_trigger

    def status_banner(self) -> str:
        audio_state = "MUTADO" if self.muted else "ATIVO (Audio real no Ciclo 6)"
        return (
            f"[AIR MUSIC - {self.lifecycle_stage}] Nota: {self.current_note} "
            f"({self.current_freq_hz:.1f} Hz) | Vol: {self.volume_pct:.0f}% | {audio_state}\n"
            f"Evento musical: {self.last_trigger}"
        )
