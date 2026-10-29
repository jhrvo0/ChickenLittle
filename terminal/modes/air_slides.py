"""Interface modular do modo Air Slides com proteção anti-repetição (Ciclo 6)."""

from __future__ import annotations

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    GestureType,
    SensorFramePayload,
)
from terminal.modes.base import BaseAppMode


class AirSlidesMode(BaseAppMode):
    """Controlador modular de slides com debounce temporal contra disparos repetidos."""

    mode_id = AppModeId.AIR_SLIDES
    title = "Air Slides (Apresentacao Sem Contato)"
    lifecycle_stage = "INTERFACE_MODULAR_CICLO_6"

    def __init__(
        self,
        total_slides: int = 8,
        cooldown_ms: int = 1000,
    ) -> None:
        self.total_slides = max(1, total_slides)
        self.current_slide = 1
        self.cooldown_ms = max(0, cooldown_ms)
        self._last_trigger_ts_ms: int | None = None
        self.last_status = "PRONTO"

    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        # Air Slides responde primariamente a eventos discretos de gestos
        _ = frame

    def on_gesture_event(self, event: GestureEventPayload, ts_ms: int | None = None) -> str:
        if event.gesture not in (GestureType.APPROACH, GestureType.RETREAT):
            return self.last_status

        if (
            ts_ms is not None
            and self._last_trigger_ts_ms is not None
            and (ts_ms - self._last_trigger_ts_ms) < self.cooldown_ms
        ):
            self.last_status = "BLOQUEADO POR DEBOUNCE"
            return self.last_status

        if ts_ms is not None:
            self._last_trigger_ts_ms = ts_ms

        if event.gesture == GestureType.APPROACH:
            self.current_slide = min(self.total_slides, self.current_slide + 1)
            self.last_status = f"AVANCOU -> SLIDE {self.current_slide}/{self.total_slides}"
        elif event.gesture == GestureType.RETREAT:
            self.current_slide = max(1, self.current_slide - 1)
            self.last_status = f"VOLTOU -> SLIDE {self.current_slide}/{self.total_slides}"

        return self.last_status

    def status_banner(self) -> str:
        return (
            f"[AIR SLIDES - {self.lifecycle_stage}] Slide Interno: "
            f"{self.current_slide}/{self.total_slides} | Cooldown: {self.cooldown_ms}ms\n"
            f"Status: {self.last_status} (APPROACH=Proximo, RETREAT=Anterior)"
        )
