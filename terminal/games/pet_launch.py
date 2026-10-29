"""Núcleo modular e física base do minijogo Pet Launch (loop completo previsto para o Ciclo 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    GestureType,
    SensorFramePayload,
)
from terminal.modes.base import BaseAppMode


@dataclass(frozen=True)
class LaunchResult:
    """Resultado de um arremesso balístico 2D com quique simples."""

    initial_speed_mps: float
    angle_deg: float
    distance_m: float
    max_height_m: float
    bounces: int
    score: int
    xp_reward: int


def simulate_launch_trajectory(
    power_norm: float,
    angle_deg: float = 42.0,
    gravity: float = 9.81,
    restitution: float = 0.45,
    dt: float = 0.02,
) -> LaunchResult:
    """Simula trajetória balística 2D com gravidade e colisões elásticas simples no solo."""
    clamped_power = max(0.05, min(1.0, float(power_norm)))
    clamped_angle = max(10.0, min(80.0, float(angle_deg)))
    v0 = 5.0 + clamped_power * 25.0  # 5 m/s a 30 m/s
    rad = math.radians(clamped_angle)

    vx = v0 * math.cos(rad)
    vy = v0 * math.sin(rad)
    x = 0.0
    y = 0.0
    max_y = 0.0
    bounces = 0

    for _ in range(5000):
        x += vx * dt
        y += vy * dt
        vy -= gravity * dt
        if y > max_y:
            max_y = y
        if y <= 0.0 and vy < 0.0:
            y = 0.0
            vy = -vy * restitution
            vx *= 0.78
            bounces += 1
            if abs(vy) < 0.6 or bounces >= 4:
                break

    dist = round(x, 2)
    score = int(round(dist * 10.0))
    xp_reward = max(5, min(50, score // 20))
    return LaunchResult(
        initial_speed_mps=round(v0, 2),
        angle_deg=round(clamped_angle, 1),
        distance_m=dist,
        max_height_m=round(max_y, 2),
        bounces=bounces,
        score=score,
        xp_reward=xp_reward,
    )


class PetLaunchMode(BaseAppMode):
    """Adaptador de eventos do Pet Launch (preparado para o loop interativo completo do Ciclo 4)."""

    mode_id = AppModeId.PET_LAUNCH
    title = "Pet Launch (Minijogo Balistico)"
    lifecycle_stage = "NUCLEO_FISICO_PRONTO_CICLO_4"

    def __init__(self) -> None:
        self.charge_norm: float = 0.0
        self.angle_deg: float = 45.0
        self.best_distance_m: float = 0.0
        self.last_result: LaunchResult | None = None

    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        # Potenciômetro ajusta o ângulo entre 20° e 70°
        self.angle_deg = round(20.0 + frame.pot_norm * 50.0, 1)

    def on_gesture_event(self, event: GestureEventPayload) -> str:
        if event.gesture == GestureType.HOLD:
            self.charge_norm = min(1.0, round(self.charge_norm + 0.25, 2))
            return f"CARREGANDO FORCA: {self.charge_norm * 100.0:.0f}%"
        if event.gesture in (GestureType.APPROACH, GestureType.IMPULSE):
            effective = self.charge_norm if self.charge_norm > 0.0 else 0.5
            res = simulate_launch_trajectory(effective, self.angle_deg)
            self.last_result = res
            self.best_distance_m = max(self.best_distance_m, res.distance_m)
            self.charge_norm = 0.0
            return f"LANCADO! {res.distance_m:.1f}m ({res.score} pts)"
        if event.gesture == GestureType.RETREAT:
            self.charge_norm = 0.0
            return "CARGA CANCELADA"
        return "AGUARDANDO"

    def status_banner(self) -> str:
        last_txt = (
            f"Ultimo: {self.last_result.distance_m:.1f}m ({self.last_result.score} pts)"
            if self.last_result
            else "Ultimo: ---"
        )
        return (
            f"[PET LAUNCH - {self.lifecycle_stage}] Carga: {self.charge_norm * 100.0:.0f}% | "
            f"Angulo(POT): {self.angle_deg:.1f} deg | Recorde: {self.best_distance_m:.1f}m\n"
            f"{last_txt} (HOLD=Carregar, APPROACH=Arremessar — UI dedicada no Ciclo 4)"
        )
