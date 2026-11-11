"""Minijogo completo Pet Launch (Ciclo 4): loop de 10 etapas, física 2D, loja e integração Pet.

Preserva `simulate_launch_trajectory` e o comportamento instantâneo padrão de `PetLaunchMode()`
para retrocompatibilidade com os testes anteriores, enquanto `PetLaunchMode(animated_flight=True)`
e `PetLaunchGame` executam o loop arcade completo de 10 etapas com física de timestep fixo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    GestureType,
    SensorFramePayload,
)
from terminal.games.input_adapter import (
    LaunchAction,
    LaunchInputAdapter,
    UnifiedLaunchInput,
)
from terminal.games.physics import (
    FlightMotionPhase,
    LaunchModifiers,
    LaunchPhysicsConfig,
    LaunchPhysicsSimulator,
    LaunchPhysicsState,
)
from terminal.modes.base import BaseAppMode
from terminal.pet.state import (
    EvolutionStage,
    PetMood,
    PetPersonality,
    PetState,
)


class LaunchPhase(str, Enum):
    """Fases da máquina de estados do gameplay de 10 etapas do Pet Launch."""

    MENU = "MENU"                  # Etapas 1 e 10: Menu principal, recordes, moedas e loja
    SELECT_PET = "SELECT_PET"      # Etapa 2: Confirmar pet, bônus de perfil e prontidão
    PREP = "PREP"                  # Etapa 3: Pet na rampa e ajuste de ângulo
    CHARGING = "CHARGING"          # Etapa 4: Barra de força calibrada (HOLD / SPACE)
    LAUNCHING = "LAUNCHING"        # Etapa 5: Disparo na rampa
    FLIGHT = "FLIGHT"              # Etapas 6 e 7: Trajetória animada, quiques, atrito e parada
    RESULT = "RESULT"              # Etapas 8 e 9: Pontuação, moedas, XP, recorde e reação do pet
    RETURN_TO_PET = "RETURN_TO_PET"  # Retorno ao modo Tamagotchi


@dataclass(frozen=True)
class LaunchUpgradeSpec:
    """Especificação de uma melhoria permanente comprável com moedas do Pet Launch."""

    upgrade_id: str
    slot_key: str
    name: str
    cost_coins: int
    description: str
    speed_bonus: float = 0.0
    drag_factor: float = 1.0
    restitution_bonus: float = 0.0
    extra_bounces: int = 0


LAUNCH_UPGRADES: tuple[LaunchUpgradeSpec, ...] = (
    LaunchUpgradeSpec(
        upgrade_id="SLINGSHOT_PRO",
        slot_key="7",
        name="Estilingue Pro",
        cost_coins=15,
        description="+12% velocidade inicial",
        speed_bonus=0.12,
    ),
    LaunchUpgradeSpec(
        upgrade_id="AERO_CAPE",
        slot_key="8",
        name="Capa Aerodinamica",
        cost_coins=25,
        description="-25% resistencia do ar",
        drag_factor=0.75,
    ),
    LaunchUpgradeSpec(
        upgrade_id="SPRING_BOOTS",
        slot_key="9",
        name="Botas de Mola",
        cost_coins=35,
        description="+0.12 quique e +1 salto",
        restitution_bonus=0.12,
        extra_bounces=1,
    ),
)

UPGRADE_BY_ID: dict[str, LaunchUpgradeSpec] = {u.upgrade_id: u for u in LAUNCH_UPGRADES}


@dataclass(frozen=True)
class LaunchResult:
    """Resultado consolidado de um arremesso balístico 2D."""

    initial_speed_mps: float
    angle_deg: float
    distance_m: float
    max_height_m: float
    bounces: int
    score: int
    xp_reward: int
    coins_reward: int = 0
    stars_collected: int = 0
    sweet_spot_bonus: bool = False
    is_new_record: bool = False
    roll_distance_m: float = 0.0
    flight_time_s: float = 0.0


def simulate_launch_trajectory(
    power_norm: float,
    angle_deg: float = 42.0,
    gravity: float = 9.81,
    restitution: float = 0.45,
    dt: float = 0.02,
) -> LaunchResult:
    """Simula trajetória balística 2D base (contrato preservado desde o Ciclo 1)."""
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


def compute_launch_modifiers(state: PetState, sweet_spot: bool = False) -> LaunchModifiers:
    """Combina melhorias desbloqueadas, estágio evolutivo, personalidade e sweet-spot."""
    speed_mult = 1.0
    drag_mult = 1.0
    rest_bonus = 0.0
    extra_bounces = 0
    coin_bonus = 0
    score_mult = 1.0

    for uid in state.unlocked_upgrades:
        spec = UPGRADE_BY_ID.get(uid)
        if spec is not None:
            speed_mult += spec.speed_bonus
            drag_mult *= spec.drag_factor
            rest_bonus += spec.restitution_bonus
            extra_bounces += spec.extra_bounces

    # Bônus do estágio evolutivo
    if state.stage == EvolutionStage.CHICK:
        speed_mult += 0.04
    elif state.stage == EvolutionStage.CYBER_ROOSTER:
        speed_mult += 0.08
        rest_bonus += 0.04

    # Bônus da personalidade do pet
    if state.personality == PetPersonality.PLAYFUL:
        score_mult *= 1.10
    elif state.personality == PetPersonality.CURIOUS:
        coin_bonus += 2
    elif state.personality == PetPersonality.FOODIE:
        drag_mult *= 0.92
    elif state.personality == PetPersonality.ZEN:
        speed_mult += 0.05

    if sweet_spot:
        speed_mult += 0.06

    return LaunchModifiers(
        speed_multiplier=round(speed_mult, 4),
        drag_multiplier=round(drag_mult, 4),
        restitution_bonus=round(rest_bonus, 4),
        extra_max_bounces=extra_bounces,
        coin_bonus_flat=coin_bonus,
        score_multiplier=round(score_mult, 4),
    )


def describe_personality_perk(personality: PetPersonality) -> str:
    perks = {
        PetPersonality.PLAYFUL: "PLAYFUL (+10% pontuacao final)",
        PetPersonality.CURIOUS: "CURIOUS (+2 moedas extras/voo)",
        PetPersonality.FOODIE: "FOODIE (-8% arrasto do ar)",
        PetPersonality.ZEN: "ZEN (+5% velocidade de saida)",
    }
    return perks.get(personality, "EQUILIBRADO")


class PetLaunchGame:
    """Máquina de estados completa do Pet Launch (10 etapas, física 2D e progressão)."""

    SWEET_SPOT_MIN = 0.80
    SWEET_SPOT_MAX = 0.95

    def __init__(
        self,
        physics_config: LaunchPhysicsConfig | None = None,
        input_adapter: LaunchInputAdapter | None = None,
        flight_time_scale: float = 1.35,
    ) -> None:
        self.physics = LaunchPhysicsSimulator(config=physics_config)
        self.input_adapter = input_adapter or LaunchInputAdapter(base_charge_step=0.22)
        self.flight_time_scale = max(0.25, float(flight_time_scale))

        self.phase: LaunchPhase = LaunchPhase.MENU
        self.angle_deg: float = 45.0
        self.charge_norm: float = 0.0
        self.charge_step_norm: float = 0.22
        self.sensor_proximity_cm: float | None = None

        self.best_distance_m: float = 0.0
        self.best_score: int = 0
        self.matches_completed: int = 0
        self.last_result: LaunchResult | None = None
        self.status_message: str = "Bem-vindo ao Pet Launch! [APPROACH/ENTER] Selecionar Pet"
        self.pet_reaction: str = "Pronto para voar!"
        self.event_log: list[str] = ["STEP_1_ENTER_MODE"]

        self._launching_timer_s: float = 0.0
        self._active_sweet_spot: bool = False
        self._active_modifiers: LaunchModifiers = LaunchModifiers()
        self._synced_phys_event_idx: int = 0
        self._pending_pet_commands: list[dict[str, Any]] = []
        self._manual_angle_override: bool = False

    def reset_to_menu(self) -> None:
        self.phase = LaunchPhase.MENU
        self.charge_norm = 0.0
        self._launching_timer_s = 0.0
        self.status_message = "Menu Pet Launch: [APPROACH/ENTER] Jogar | [U/7/8/9] Loja"
        self._log_event("STEP_1_ENTER_MODE")

    def mark_return_to_pet(self, pet_state: PetState) -> None:
        self.phase = LaunchPhase.RETURN_TO_PET
        self.charge_norm = 0.0
        self.pet_reaction = f"{pet_state.name}: Foi divertido! Vamos descansar no ninho."
        self.status_message = "Retornando ao modo MotionPet..."
        self._log_event("RETURN_TO_MOTION_PET")

    def pop_pending_pet_commands(self) -> list[dict[str, Any]]:
        """Retorna payloads de `CommandType.PLAY` para sincronizar recompensas/loja no `PetEngine`."""
        cmds = list(self._pending_pet_commands)
        self._pending_pet_commands.clear()
        return cmds

    def is_in_sweet_spot(self, power: float | None = None) -> bool:
        val = self.charge_norm if power is None else power
        return self.SWEET_SPOT_MIN <= val <= self.SWEET_SPOT_MAX

    @staticmethod
    def check_pet_readiness(pet_state: PetState, min_energy: float = 10.0) -> tuple[bool, str]:
        if pet_state.is_sleeping:
            return False, "PET DORMINDO! Acorde-o [R] antes de lancar."
        if pet_state.mood == PetMood.SICK:
            return False, "PET DOENTE! Cure-o [C] antes de lancar."
        if pet_state.energy < min_energy:
            return False, f"ENERGIA BAIXA ({pet_state.energy:.0f}% < {min_energy:.0f}%)! Descanse [R]."
        return True, "APTO PARA VOO"

    def sync_records_from_pet(self, pet_state: PetState) -> None:
        self.best_distance_m = max(self.best_distance_m, pet_state.best_launch_distance_m)
        self.best_score = max(self.best_score, pet_state.best_launch_score)

    def set_records_from_pet(self, pet_state: PetState) -> None:
        """Atribui (não usa max) os recordes do pet autoritativo, sem mexer na partida."""
        self.best_distance_m = float(pet_state.best_launch_distance_m)
        self.best_score = int(pet_state.best_launch_score)
        self.matches_completed = int(pet_state.total_launches)

    def reset_progress(self, pet_state: PetState) -> None:
        """Reinicia partida e recordes a partir do pet autoritativo (LOAD/RESET confirmados).

        `sync_records_from_pet` só sobe recordes (max); aqui o valor é atribuído, para que
        um save com recordes menores (ou um pet novo) realmente reduza os locais.
        """
        self.set_records_from_pet(pet_state)
        self.last_result = None
        self.charge_norm = 0.0
        self._launching_timer_s = 0.0
        self._active_sweet_spot = False
        self._active_modifiers = LaunchModifiers()
        self._pending_pet_commands.clear()
        self.physics.state = LaunchPhysicsState()
        self._synced_phys_event_idx = 0
        self._manual_angle_override = False
        self.phase = LaunchPhase.MENU
        self.pet_reaction = "Pronto para voar!"
        self.status_message = "Menu Pet Launch: [APPROACH/ENTER] Jogar | [U/7/8/9] Loja"
        self._log_event("PET_RELOADED")

    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        aim = self.input_adapter.calibrate_from_sensor(frame)
        self.charge_step_norm = aim.charge_step_norm
        self.sensor_proximity_cm = aim.proximity_cm
        if self.phase in (LaunchPhase.MENU, LaunchPhase.SELECT_PET, LaunchPhase.PREP, LaunchPhase.CHARGING):
            if not self._manual_angle_override:
                self.angle_deg = aim.angle_deg

    def handle_key(
        self,
        key: str,
        pet_state: PetState,
        event_token: str | None = None,
    ) -> str:
        cmd = self.input_adapter.from_key(key, event_token=event_token)
        if cmd is None:
            return self.status_message
        return self.handle_input(cmd, pet_state)

    def handle_gesture(
        self,
        event: GestureEventPayload,
        pet_state: PetState,
        seq_id: int | None = None,
        ts_ms: int | None = None,
    ) -> str:
        cmd = self.input_adapter.from_gesture(event, seq_id=seq_id, ts_ms=ts_ms)
        if cmd is None:
            return self.status_message
        return self.handle_input(cmd, pet_state)

    def handle_input(self, cmd: UnifiedLaunchInput, pet_state: PetState) -> str:
        """Processa `UnifiedLaunchInput` de forma idêntica independente da origem."""
        self.sync_records_from_pet(pet_state)
        act = cmd.action

        if self.phase == LaunchPhase.RETURN_TO_PET:
            self.phase = LaunchPhase.MENU

        # Ajustes finos de ângulo permitidos antes do disparo
        if act == LaunchAction.AIM_UP and self.phase in (
            LaunchPhase.MENU,
            LaunchPhase.SELECT_PET,
            LaunchPhase.PREP,
            LaunchPhase.CHARGING,
        ):
            self._manual_angle_override = True
            self.angle_deg = round(min(70.0, self.angle_deg + 3.0), 1)
            self.status_message = f"Angulo ajustado: {self.angle_deg:.1f} deg"
            return self.status_message

        if act == LaunchAction.AIM_DOWN and self.phase in (
            LaunchPhase.MENU,
            LaunchPhase.SELECT_PET,
            LaunchPhase.PREP,
            LaunchPhase.CHARGING,
        ):
            self._manual_angle_override = True
            self.angle_deg = round(max(20.0, self.angle_deg - 3.0), 1)
            self.status_message = f"Angulo ajustado: {self.angle_deg:.1f} deg"
            return self.status_message

        # Compras na loja (permitidas no MENU e SELECT_PET)
        if act in (
            LaunchAction.BUY_NEXT_UPGRADE,
            LaunchAction.BUY_UPGRADE_1,
            LaunchAction.BUY_UPGRADE_2,
            LaunchAction.BUY_UPGRADE_3,
        ):
            if self.phase in (LaunchPhase.MENU, LaunchPhase.SELECT_PET, LaunchPhase.RESULT):
                return self._request_upgrade_purchase(act, pet_state)
            self.status_message = "Volte ao MENU para visitar a loja."
            return self.status_message

        # --- Máquina de Estados Principal (10 Etapas) ---
        if self.phase == LaunchPhase.MENU:
            if act == LaunchAction.CONFIRM_OR_LAUNCH:
                self.phase = LaunchPhase.SELECT_PET
                ok, reason = self.check_pet_readiness(pet_state)
                self.pet_reaction = (
                    f"{pet_state.name} ({pet_state.stage.value}): "
                    + ("Vamos bater o recorde!" if ok else reason)
                )
                self.status_message = (
                    f"Pet {pet_state.name} selecionado! [APPROACH/ENTER] Confirmar e ir p/ Rampa"
                )
                self._log_event("STEP_2_SELECT_PET")
            elif act == LaunchAction.CHARGE_POWER:
                self.status_message = "No Menu: use [APPROACH/ENTER] para selecionar o pet."
            return self.status_message

        if self.phase == LaunchPhase.SELECT_PET:
            if act == LaunchAction.CANCEL_OR_BACK:
                self.phase = LaunchPhase.MENU
                self.status_message = "Retornou ao Menu Principal."
                return self.status_message
            if act == LaunchAction.CONFIRM_OR_LAUNCH:
                ok, reason = self.check_pet_readiness(pet_state)
                if not ok:
                    self.status_message = reason
                    self.pet_reaction = f"{pet_state.name}: Preciso de cuidados primeiro..."
                    self._log_event("LAUNCH_BLOCKED_READINESS")
                    return self.status_message
                self.phase = LaunchPhase.PREP
                self.charge_norm = 0.0
                self.pet_reaction = f"{pet_state.name}: Na rampa! Segure [HOLD/SPACE] p/ carregar!"
                self.status_message = (
                    f"Preparacao ({self.angle_deg:.1f} deg): [HOLD/SPACE] Carregar Forca"
                )
                self._log_event("STEP_3_PREP")
            return self.status_message

        if self.phase == LaunchPhase.PREP:
            if act == LaunchAction.CANCEL_OR_BACK:
                self.phase = LaunchPhase.SELECT_PET
                self.status_message = "Voltou para selecao do pet."
                return self.status_message
            if act == LaunchAction.CHARGE_POWER:
                self.phase = LaunchPhase.CHARGING
                self._advance_charge()
                self._log_event("STEP_4_CHARGING")
                return self.status_message
            if act == LaunchAction.DIRECT_IMPULSE_LAUNCH:
                # Suporte opcional quando o classificador emitir IMPULSE direto
                self.charge_norm = 0.78
                return self._execute_launch(pet_state, via=cmd.origin)
            if act == LaunchAction.CONFIRM_OR_LAUNCH:
                self.status_message = "Carregue a forca primeiro com [HOLD / SPACE]!"
            return self.status_message

        if self.phase == LaunchPhase.CHARGING:
            if act == LaunchAction.CANCEL_OR_BACK:
                self.charge_norm = 0.0
                self.phase = LaunchPhase.PREP
                self.pet_reaction = f"{pet_state.name}: Ufa, carga cancelada. Respira!"
                self.status_message = "CARGA CANCELADA — de volta a preparacao."
                self._log_event("CHARGE_CANCELLED")
                return self.status_message
            if act == LaunchAction.CHARGE_POWER:
                self._advance_charge()
                return self.status_message
            if act in (LaunchAction.CONFIRM_OR_LAUNCH, LaunchAction.DIRECT_IMPULSE_LAUNCH):
                return self._execute_launch(pet_state, via=cmd.origin)
            return self.status_message

        if self.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT):
            self.status_message = (
                f"Em voo! Dist: {self.physics.state.x_m:.1f}m | Alt: {self.physics.state.y_m:.1f}m"
            )
            return self.status_message

        if self.phase == LaunchPhase.RESULT:
            if act in (LaunchAction.CONFIRM_OR_LAUNCH, LaunchAction.CANCEL_OR_BACK):
                self.phase = LaunchPhase.MENU
                self.charge_norm = 0.0
                self.pet_reaction = (
                    f"{pet_state.name}: Moedas={pet_state.coins} | Recorde={self.best_distance_m:.1f}m. Outra?"
                )
                self.status_message = (
                    f"Progresso atualizado! Partidas: {self.matches_completed} | [APPROACH/ENTER] Nova Partida"
                )
                self._log_event("STEP_10_RETURN_MENU")
            return self.status_message

        return self.status_message

    def update(self, dt_s: float, pet_state: PetState) -> None:
        """Avança timers de decolagem e simulação física 2D de timestep fixo."""
        self.sync_records_from_pet(pet_state)
        dt = max(0.0, float(dt_s))
        if dt <= 0.0:
            return

        if self.phase == LaunchPhase.LAUNCHING:
            self._launching_timer_s -= dt
            if self._launching_timer_s <= 0.0:
                self.phase = LaunchPhase.FLIGHT
                self.pet_reaction = f"{pet_state.name}: Uhuuuu! Olha a altura!"
                self.status_message = "Voo balistico em andamento..."
                self._log_event("STEP_6_FLIGHT")
                # Avança o restante do delta de tempo já na física
                rem = abs(self._launching_timer_s)
                if rem > 0.0:
                    self._step_flight_and_check_stop(rem, pet_state)
            return

        if self.phase == LaunchPhase.FLIGHT:
            self._step_flight_and_check_stop(dt, pet_state)

    def _advance_charge(self) -> None:
        if self.charge_norm >= 1.0 - 1e-6:
            # Oscilação arcade: passar de 100% reinicia em um degrau base para exigir timing no sweet-spot
            self.charge_norm = round(self.charge_step_norm, 2)
        else:
            self.charge_norm = round(min(1.0, self.charge_norm + self.charge_step_norm), 2)

        pct = self.charge_norm * 100.0
        sweet = " [SWEET SPOT!]" if self.is_in_sweet_spot() else ""
        self.pet_reaction = (
            "AGORA! Zona perfeita!" if sweet else f"Concentrando impulso ({pct:.0f}%)..."
        )
        self.status_message = (
            f"CARREGANDO FORCA: {pct:.0f}%{sweet} -> [APPROACH/ENTER] Lancar | [RETREAT/B] Cancelar"
        )

    def _execute_launch(self, pet_state: PetState, via: str) -> str:
        ok, reason = self.check_pet_readiness(pet_state)
        if not ok:
            self.phase = LaunchPhase.SELECT_PET
            self.charge_norm = 0.0
            self.status_message = reason
            return self.status_message

        effective_power = max(0.15, self.charge_norm)
        self._active_sweet_spot = self.is_in_sweet_spot(effective_power)
        self._active_modifiers = compute_launch_modifiers(
            pet_state,
            sweet_spot=self._active_sweet_spot,
        )
        self.physics.start_launch(
            power_norm=effective_power,
            angle_deg=self.angle_deg,
            modifiers=self._active_modifiers,
            course_index=self.matches_completed,
        )
        self._synced_phys_event_idx = len(self.physics.state.events)
        self.phase = LaunchPhase.LAUNCHING
        self._launching_timer_s = 0.12
        self.pet_reaction = (
            f"{pet_state.name}: DISPARO PERFEITO!" if self._active_sweet_spot else f"{pet_state.name}: LAAA VOU EU!"
        )
        self.status_message = (
            f"LANCAMENTO ({effective_power * 100.0:.0f}% @ {self.angle_deg:.1f} deg via {via})!"
        )
        self._log_event(
            f"STEP_5_LAUNCHING(power={effective_power:.2f},angle={self.angle_deg:.1f},sweet={self._active_sweet_spot})"
        )
        return self.status_message

    def _step_flight_and_check_stop(self, dt_s: float, pet_state: PetState) -> None:
        self.physics.advance_time(dt_s, time_scale=self.flight_time_scale)
        pstate = self.physics.state

        # Registra eventos físicos recém-ocorridos (quiques, estrelas, atrito, parada)
        while self._synced_phys_event_idx < len(pstate.events):
            ev = pstate.events[self._synced_phys_event_idx]
            self._synced_phys_event_idx += 1
            self._log_event(f"STEP_7_PHYS_{ev}")
            if ev.startswith("BOUNCE_"):
                self.pet_reaction = f"{pet_state.name}: Boing! Quique #{pstate.bounces}!"
            elif ev.startswith("STAR_"):
                self.pet_reaction = f"{pet_state.name}: Peguei estrela {ev[5:]}! *brilho*"
            elif ev == "TOUCHDOWN_SLIDE":
                self.pet_reaction = f"{pet_state.name}: Derrapando na grama..."

        self.status_message = (
            f"VOO: {pstate.x_m:5.1f}m | Alt: {pstate.y_m:4.1f}m | "
            f"Vel: {pstate.speed_mps:4.1f}m/s | Quiques: {pstate.bounces}"
        )

        if pstate.is_stopped:
            self._finalize_match(pet_state)

    def _finalize_match(self, pet_state: PetState) -> None:
        pstate = self.physics.state
        mods = self._active_modifiers
        dist = round(pstate.x_m, 2)
        prev_best_dist = max(self.best_distance_m, pet_state.best_launch_distance_m)
        prev_best_score = max(self.best_score, pet_state.best_launch_score)

        collected_specs = [s for s in self.physics.stars if s.star_id in pstate.collected_stars]
        star_pts = sum(s.score_value for s in collected_specs)
        star_coins = sum(s.coin_value for s in collected_specs)

        raw_score = (dist * 12.0) + (pstate.bounces * 18.0) + star_pts
        sweet_mult = 1.15 if self._active_sweet_spot else 1.0
        final_score = int(round(raw_score * mods.score_multiplier * sweet_mult))

        is_record = (dist > prev_best_dist) or (final_score > prev_best_score)
        coins = max(
            3,
            int(dist // 8.0)
            + star_coins
            + mods.coin_bonus_flat
            + (3 if is_record else 0)
            + (2 if self._active_sweet_spot else 0),
        )
        xp = max(8, min(60, 8 + (final_score // 35)))

        res = LaunchResult(
            initial_speed_mps=round(pstate.initial_speed_mps, 2),
            angle_deg=round(pstate.launch_angle_deg, 1),
            distance_m=dist,
            max_height_m=round(pstate.max_height_m, 2),
            bounces=pstate.bounces,
            score=final_score,
            xp_reward=xp,
            coins_reward=coins,
            stars_collected=len(collected_specs),
            sweet_spot_bonus=self._active_sweet_spot,
            is_new_record=is_record,
            roll_distance_m=round(pstate.roll_distance_m, 2),
            flight_time_s=round(pstate.elapsed_s, 2),
        )
        self.last_result = res
        self.best_distance_m = max(prev_best_dist, dist)
        self.best_score = max(prev_best_score, final_score)
        self.matches_completed += 1
        self.charge_norm = 0.0
        self.phase = LaunchPhase.RESULT

        # Reação emocional baseada no desempenho e personalidade
        if is_record:
            self.pet_reaction = (
                f"{pet_state.name} (*ECSTATIC*): NOVO RECORDE {dist:.1f}m! Eu sou um foguete!"
            )
        elif dist >= 45.0:
            self.pet_reaction = f"{pet_state.name} (^v^): Que voo incrivel! Ganhei +{coins} moedas!"
        else:
            self.pet_reaction = (
                f"{pet_state.name} (o_o): Pouso suave em {dist:.1f}m. Vamos tentar mais alto!"
            )

        self.status_message = (
            f"LANCADO! {dist:.1f}m ({final_score} pts) | +{coins} moedas | +{xp} XP"
            + (" [NOVO RECORDE!]" if is_record else "")
        )

        # Etapa 9: Enfileira recompensa autoritativa para o PetEngine
        self._pending_pet_commands.append(
            {
                "minigame": "PET_LAUNCH",
                "action": "MATCH_RESULT",
                "distance_m": dist,
                "score": final_score,
                "coins_earned": coins,
                "xp_earned": xp,
                "bounces": pstate.bounces,
            }
        )
        self._log_event(
            f"STEP_8_9_RESULT(dist={dist:.2f}m,score={final_score},coins={coins},xp={xp},record={is_record})"
        )

    def _request_upgrade_purchase(self, act: LaunchAction, pet_state: PetState) -> str:
        target: LaunchUpgradeSpec | None = None
        if act == LaunchAction.BUY_UPGRADE_1:
            target = LAUNCH_UPGRADES[0]
        elif act == LaunchAction.BUY_UPGRADE_2:
            target = LAUNCH_UPGRADES[1]
        elif act == LaunchAction.BUY_UPGRADE_3:
            target = LAUNCH_UPGRADES[2]
        else:
            for spec in LAUNCH_UPGRADES:
                if spec.upgrade_id not in pet_state.unlocked_upgrades:
                    target = spec
                    break

        if target is None:
            self.status_message = "LOJA: Todas as melhorias ja foram desbloqueadas!"
            return self.status_message
        if target.upgrade_id in pet_state.unlocked_upgrades:
            self.status_message = f"LOJA: {target.name} ja esta ativa!"
            return self.status_message
        if pet_state.coins < target.cost_coins:
            self.status_message = (
                f"LOJA: Moedas insuficientes p/ {target.name} ({pet_state.coins}/{target.cost_coins})."
            )
            return self.status_message

        self._pending_pet_commands.append(
            {
                "minigame": "PET_LAUNCH",
                "action": "UNLOCK_UPGRADE",
                "upgrade_id": target.upgrade_id,
                "cost": target.cost_coins,
            }
        )
        self.pet_reaction = f"{pet_state.name}: Oba! Equipamento novo: {target.name}!"
        self.status_message = f"LOJA: Solicitado desbloqueio de {target.name} (-{target.cost_coins} moedas)!"
        self._log_event(f"SHOP_UNLOCK_REQUEST({target.upgrade_id})")
        return self.status_message

    def _log_event(self, entry: str) -> None:
        self.event_log.append(entry)
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]


class PetLaunchMode(BaseAppMode):
    """Modo Pet Launch compatível com `BaseAppMode` e com o motor completo `PetLaunchGame`."""

    mode_id = AppModeId.PET_LAUNCH
    title = "Pet Launch (Arcade Balistico)"
    lifecycle_stage = "JOGAVEL_CICLO_4"

    def __init__(self, animated_flight: bool = False) -> None:
        self.animated_flight = animated_flight
        self.game = PetLaunchGame()
        self._pet_snapshot = PetState()

        # Campos espelhados para compatibilidade direta com chamadas do Ciclo 1
        self.charge_norm: float = 0.0
        self.angle_deg: float = 45.0
        self.best_distance_m: float = 0.0
        self.last_result: LaunchResult | None = None

    def bind_pet_state(self, state: PetState) -> None:
        self._pet_snapshot = state
        self.game.sync_records_from_pet(state)
        self._sync_mirror_fields()

    def reload_from_pet(self, state: PetState) -> None:
        """Descarta recordes e partida locais após LOAD/RESET confirmados pela ESP32."""
        self._pet_snapshot = state
        self.game.reset_progress(state)
        self._sync_mirror_fields()
        self.last_result = None

    def resync_records_from_pet(self, state: PetState) -> None:
        """Reatribui só os recordes (pet_state que chega depois do ACK de LOAD/RESET)."""
        self._pet_snapshot = state
        self.game.set_records_from_pet(state)
        self._sync_mirror_fields()

    def on_enter_mode(self, state: PetState) -> None:
        self._pet_snapshot = state
        self.game.sync_records_from_pet(state)
        self.game.reset_to_menu()
        self._sync_mirror_fields()

    def on_exit_mode(self, state: PetState) -> None:
        self._pet_snapshot = state
        self.game.mark_return_to_pet(state)
        self._sync_mirror_fields()

    def on_sensor_frame(self, frame: SensorFramePayload) -> None:
        if not self.animated_flight:
            self.angle_deg = round(20.0 + frame.pot_norm * 50.0, 1)
            return
        self.game.on_sensor_frame(frame)
        self._sync_mirror_fields()

    def on_gesture_event(
        self,
        event: GestureEventPayload,
        seq_id: int | None = None,
        ts_ms: int | None = None,
    ) -> str:
        if not self.animated_flight:
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

        msg = self.game.handle_gesture(event, self._pet_snapshot, seq_id=seq_id, ts_ms=ts_ms)
        self._sync_mirror_fields()
        return msg

    def on_key_input(self, key: str, event_token: str | None = None) -> str:
        msg = self.game.handle_key(key, self._pet_snapshot, event_token=event_token)
        self._sync_mirror_fields()
        return msg

    def update(self, dt_s: float) -> None:
        if self.animated_flight:
            self.game.update(dt_s, self._pet_snapshot)
            self._sync_mirror_fields()

    def pop_pending_pet_commands(self) -> list[dict[str, Any]]:
        return self.game.pop_pending_pet_commands()

    @property
    def phase(self) -> LaunchPhase:
        return self.game.phase

    @property
    def physics_state(self) -> LaunchPhysicsState:
        return self.game.physics.state

    def _sync_mirror_fields(self) -> None:
        self.charge_norm = self.game.charge_norm
        self.angle_deg = self.game.angle_deg
        self.best_distance_m = self.game.best_distance_m
        self.last_result = self.game.last_result

    def status_banner(self) -> str:
        last_txt = (
            f"Ultimo: {self.last_result.distance_m:.1f}m ({self.last_result.score} pts)"
            if self.last_result
            else "Ultimo: ---"
        )
        phase_txt = self.game.phase.value if self.animated_flight else self.lifecycle_stage
        return (
            f"[PET LAUNCH - {phase_txt}] Carga: {self.charge_norm * 100.0:.0f}% | "
            f"Angulo(POT): {self.angle_deg:.1f} deg | Recorde: {self.best_distance_m:.1f}m\n"
            f"{last_txt} | {self.game.status_message}"
        )
