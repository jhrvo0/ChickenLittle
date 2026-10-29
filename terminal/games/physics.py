"""Motor determinístico de física 2D com timestep fixo para o minijogo Pet Launch.

Separa rigorosamente a simulação física da taxa de quadros do terminal:
- Posição `(x_m, y_m)` e velocidade `(vx_mps, vy_mps)` em 2D.
- Gravidade, força de lançamento calibrada e resistência do ar quadrática simplificada.
- Colisão com o solo (`y = 0`), quiques com perda controlada de energia e atrito de rolagem.
- Detecção determinística de parada e câmera horizontal com avanço suave (`HorizontalCamera`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class FlightMotionPhase(str, Enum):
    """Subfases físicas do movimento do pet após o lançamento."""

    IDLE = "IDLE"
    AIRBORNE = "AIRBORNE"
    SLIDING = "SLIDING"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class LaunchPhysicsConfig:
    """Parâmetros físicos calibráveis do motor 2D de timestep fixo."""

    fixed_dt: float = 0.02  # 50 Hz fixo e independente do FPS do terminal
    gravity_mps2: float = 9.81
    min_launch_speed_mps: float = 7.0
    max_launch_speed_mps: float = 30.0
    min_angle_deg: float = 15.0
    max_angle_deg: float = 75.0
    air_drag_coeff: float = 0.010  # desaceleração por arrasto: -c_d * |v| * v
    restitution: float = 0.48  # retenção vertical no quique (0 < e < 1)
    bounce_horizontal_retention: float = 0.80  # retenção horizontal em cada impacto
    min_bounce_vy_mps: float = 1.05  # abaixo disso transita para rolagem/atrito no solo
    max_bounces: int = 5
    ground_friction_mu: float = 0.55  # desaceleração no solo: mu * g
    stop_speed_eps_mps: float = 0.10
    max_simulation_steps: int = 4000


@dataclass(frozen=True)
class LaunchModifiers:
    """Modificadores provenientes de melhorias desbloqueadas e personalidade do pet."""

    speed_multiplier: float = 1.0
    drag_multiplier: float = 1.0
    restitution_bonus: float = 0.0
    extra_max_bounces: int = 0
    coin_bonus_flat: int = 0
    score_multiplier: float = 1.0


@dataclass(frozen=True)
class CourseStar:
    """Estrela colecionável posicionada no cenário horizontal (bônus de pontos/moedas)."""

    star_id: str
    x_m: float
    y_m: float
    radius_m: float = 3.2
    coin_value: int = 2
    score_value: int = 35


@dataclass
class LaunchPhysicsState:
    """Snapshot completo e determinístico do corpo 2D durante o lançamento."""

    x_m: float = 0.0
    y_m: float = 0.0
    vx_mps: float = 0.0
    vy_mps: float = 0.0
    initial_speed_mps: float = 0.0
    launch_angle_deg: float = 45.0
    power_norm: float = 0.0
    elapsed_s: float = 0.0
    steps: int = 0
    max_height_m: float = 0.0
    bounces: int = 0
    roll_distance_m: float = 0.0
    motion_phase: FlightMotionPhase = FlightMotionPhase.IDLE
    collected_stars: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @property
    def speed_mps(self) -> float:
        return math.hypot(self.vx_mps, self.vy_mps)

    @property
    def specific_mechanical_energy(self) -> float:
        """Energia mecânica específica `E/m = 0.5 * v^2 + g * y` (J/kg) para auditoria física."""
        return 0.5 * (self.vx_mps * self.vx_mps + self.vy_mps * self.vy_mps) + 9.81 * max(0.0, self.y_m)

    @property
    def is_stopped(self) -> bool:
        return self.motion_phase == FlightMotionPhase.STOPPED


@dataclass
class HorizontalCamera:
    """Câmera horizontal 1D que acompanha o pet mantendo visão antecipada da pista."""

    viewport_width_m: float = 36.0
    lead_ratio: float = 0.28  # pet fica a ~28% da borda esquerda da janela
    x_left_m: float = 0.0

    def reset(self) -> None:
        self.x_left_m = 0.0

    def update(self, target_x_m: float) -> float:
        desired_left = max(0.0, target_x_m - self.viewport_width_m * self.lead_ratio)
        # Câmera avança suavemente e nunca recua bruscamente durante o voo para frente
        if desired_left >= self.x_left_m:
            self.x_left_m = desired_left
        else:
            self.x_left_m = max(0.0, 0.7 * self.x_left_m + 0.3 * desired_left)
        return self.x_left_m

    @property
    def x_right_m(self) -> float:
        return self.x_left_m + self.viewport_width_m

    def world_to_screen_col(self, world_x_m: float, screen_cols: int) -> int | None:
        if screen_cols <= 0:
            return None
        if world_x_m < self.x_left_m or world_x_m > self.x_right_m:
            return None
        norm = (world_x_m - self.x_left_m) / max(1e-6, self.viewport_width_m)
        col = int(round(norm * (screen_cols - 1)))
        return max(0, min(screen_cols - 1, col))


def build_default_course_stars(course_index: int = 0) -> tuple[CourseStar, ...]:
    """Gera constelação determinística de estrelas ao longo do percurso horizontal."""
    phase_shift = (course_index % 3) * 1.5
    specs = (
        ("S1", 11.0 + phase_shift, 4.2, 2, 30),
        ("S2", 23.0 + phase_shift, 7.0, 2, 40),
        ("S3", 37.0 + phase_shift, 5.5, 3, 50),
        ("S4", 52.0 + phase_shift, 3.4, 3, 60),
        ("S5", 68.0 + phase_shift, 2.2, 4, 75),
        ("S6", 86.0 + phase_shift, 1.8, 5, 90),
    )
    return tuple(
        CourseStar(
            star_id=sid,
            x_m=round(xm, 2),
            y_m=round(ym, 2),
            coin_value=coins,
            score_value=pts,
        )
        for sid, xm, ym, coins, pts in specs
    )


class LaunchPhysicsSimulator:
    """Simulador balístico 2D com acumulador de timestep fixo e zero dependência de UI."""

    def __init__(
        self,
        config: LaunchPhysicsConfig | None = None,
        viewport_width_m: float = 36.0,
    ) -> None:
        self.config = config or LaunchPhysicsConfig()
        self.state = LaunchPhysicsState()
        self.camera = HorizontalCamera(viewport_width_m=viewport_width_m)
        self.modifiers = LaunchModifiers()
        self.stars: tuple[CourseStar, ...] = build_default_course_stars(0)
        self.trail: list[tuple[float, float]] = []
        self._accumulator_s: float = 0.0

    def start_launch(
        self,
        power_norm: float,
        angle_deg: float,
        modifiers: LaunchModifiers | None = None,
        course_index: int = 0,
    ) -> LaunchPhysicsState:
        """Inicializa um novo arremesso calibrado a partir de `power_norm` e `angle_deg`."""
        cfg = self.config
        mods = modifiers or LaunchModifiers()
        self.modifiers = mods
        self.stars = build_default_course_stars(course_index)

        p = max(0.05, min(1.0, float(power_norm)))
        ang = max(cfg.min_angle_deg, min(cfg.max_angle_deg, float(angle_deg)))
        base_speed = cfg.min_launch_speed_mps + p * (cfg.max_launch_speed_mps - cfg.min_launch_speed_mps)
        v0 = base_speed * max(0.5, mods.speed_multiplier)
        rad = math.radians(ang)

        self.state = LaunchPhysicsState(
            x_m=0.0,
            y_m=0.0,
            vx_mps=v0 * math.cos(rad),
            vy_mps=v0 * math.sin(rad),
            initial_speed_mps=round(v0, 4),
            launch_angle_deg=round(ang, 2),
            power_norm=round(p, 4),
            elapsed_s=0.0,
            steps=0,
            max_height_m=0.0,
            bounces=0,
            roll_distance_m=0.0,
            motion_phase=FlightMotionPhase.AIRBORNE,
            collected_stars=[],
            events=["LAUNCHED"],
        )
        self._accumulator_s = 0.0
        self.camera.reset()
        self.trail = [(0.0, 0.0)]
        return self.state

    def advance_time(self, real_elapsed_s: float, time_scale: float = 1.0) -> int:
        """Consome tempo real em múltiplos exatos de `fixed_dt`. Retorna passos executados."""
        if self.state.motion_phase in (FlightMotionPhase.IDLE, FlightMotionPhase.STOPPED):
            return 0
        clamped_elapsed = max(0.0, min(0.5, float(real_elapsed_s))) * max(0.1, float(time_scale))
        self._accumulator_s += clamped_elapsed
        dt = self.config.fixed_dt
        executed = 0
        while self._accumulator_s + 1e-12 >= dt and not self.state.is_stopped:
            self._accumulator_s -= dt
            self.step_fixed(1)
            executed += 1
        return executed

    def step_fixed(self, steps: int = 1) -> LaunchPhysicsState:
        """Avança exatamente `steps` intervalos discretos de `config.fixed_dt`."""
        for _ in range(max(1, int(steps))):
            if self.state.motion_phase in (FlightMotionPhase.IDLE, FlightMotionPhase.STOPPED):
                break
            self._single_fixed_step()
        return self.state

    def run_until_stopped(self) -> LaunchPhysicsState:
        """Executa toda a trajetória até a parada completa (útil para testes e modo rápido)."""
        while not self.state.is_stopped and self.state.motion_phase != FlightMotionPhase.IDLE:
            self._single_fixed_step()
        return self.state

    def _single_fixed_step(self) -> None:
        s = self.state
        cfg = self.config
        mods = self.modifiers
        dt = cfg.fixed_dt

        s.steps += 1
        s.elapsed_s = round(s.steps * dt, 4)

        if s.motion_phase == FlightMotionPhase.AIRBORNE:
            # 1. Resistência do ar quadrática simplificada + gravidade (semi-implicit Euler)
            drag_c = max(0.0, cfg.air_drag_coeff * max(0.1, mods.drag_multiplier))
            speed = math.hypot(s.vx_mps, s.vy_mps)
            ax = -drag_c * speed * s.vx_mps
            ay = -cfg.gravity_mps2 - drag_c * speed * s.vy_mps

            s.vx_mps += ax * dt
            s.vy_mps += ay * dt
            if s.vx_mps < 0.0:
                s.vx_mps = 0.0

            prev_x, prev_y = s.x_m, s.y_m
            s.x_m += s.vx_mps * dt
            s.y_m += s.vy_mps * dt

            if s.y_m > s.max_height_m:
                s.max_height_m = s.y_m

            # 2. Colisão com o chão (y <= 0)
            if s.y_m <= 0.0 and s.vy_mps <= 0.0:
                # Interpola ponto horizontal aproximado do toque no solo quando veio de y > 0
                if prev_y > 0.0 and prev_y != s.y_m:
                    frac = prev_y / (prev_y - s.y_m)
                    s.x_m = prev_x + (s.x_m - prev_x) * max(0.0, min(1.0, frac))
                s.y_m = 0.0

                eff_restitution = max(0.0, min(0.88, cfg.restitution + mods.restitution_bonus))
                eff_max_bounces = max(1, cfg.max_bounces + mods.extra_max_bounces)
                rebound_vy = -s.vy_mps * eff_restitution

                if rebound_vy >= cfg.min_bounce_vy_mps and s.bounces < eff_max_bounces:
                    s.vy_mps = rebound_vy
                    s.vx_mps *= cfg.bounce_horizontal_retention
                    s.bounces += 1
                    s.events.append(f"BOUNCE_{s.bounces}")
                else:
                    s.vy_mps = 0.0
                    s.vx_mps *= cfg.bounce_horizontal_retention
                    s.motion_phase = FlightMotionPhase.SLIDING
                    s.events.append("TOUCHDOWN_SLIDE")

        elif s.motion_phase == FlightMotionPhase.SLIDING:
            # 3. Atrito dinâmico com o solo após fim dos quiques
            s.y_m = 0.0
            s.vy_mps = 0.0
            decel = (cfg.ground_friction_mu * cfg.gravity_mps2) + (cfg.air_drag_coeff * s.vx_mps * s.vx_mps)
            next_vx = max(0.0, s.vx_mps - decel * dt)
            avg_vx = 0.5 * (s.vx_mps + next_vx)
            dx = avg_vx * dt
            s.x_m += dx
            s.roll_distance_m += dx
            s.vx_mps = next_vx

            if s.vx_mps <= cfg.stop_speed_eps_mps:
                s.vx_mps = 0.0
                s.vy_mps = 0.0
                s.motion_phase = FlightMotionPhase.STOPPED
                s.events.append("STOPPED")

        # 4. Coleta determinística de estrelas no percurso
        for star in self.stars:
            if star.star_id in s.collected_stars:
                continue
            if math.hypot(s.x_m - star.x_m, s.y_m - star.y_m) <= star.radius_m:
                s.collected_stars.append(star.star_id)
                s.events.append(f"STAR_{star.star_id}")

        # 5. Guarda de término determinístico caso exceda limite máximo de passos
        if s.steps >= cfg.max_simulation_steps and not s.is_stopped:
            s.vx_mps = 0.0
            s.vy_mps = 0.0
            s.y_m = max(0.0, s.y_m)
            s.motion_phase = FlightMotionPhase.STOPPED
            s.events.append("STOPPED_MAX_STEPS")

        # 6. Atualiza trilha esparsa e câmera horizontal
        if s.steps % 3 == 0 or s.is_stopped:
            self.trail.append((round(s.x_m, 2), round(s.y_m, 2)))
            if len(self.trail) > 48:
                self.trail = self.trail[-48:]
        self.camera.update(s.x_m)
