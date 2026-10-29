"""Motor de domínio do MotionPet: transições determinísticas de estado, humor e evolução."""

from __future__ import annotations

from terminal.communication.protocol import CommandType, GestureEventPayload
from terminal.pet.config import PetConfig
from terminal.pet.state import (
    EvolutionStage,
    PetAnimation,
    PetMood,
    PetPersonality,
    PetState,
)


class PetEngine:
    """Motor de regras de negócio independente de UI (compartilhável por simulação e host)."""

    def __init__(
        self,
        state: PetState | None = None,
        config: PetConfig | None = None,
    ) -> None:
        self.config = config or PetConfig()
        self.state = state or PetState(name=self.config.default_name)
        self._refresh_derived_fields(evolved=False)

    def reset(self, name: str | None = None) -> PetState:
        pet_name = (name or self.state.name or self.config.default_name)[:12]
        self.state = PetState(name=pet_name)
        self.state.last_action = "RESET"
        self._refresh_derived_fields(evolved=False)
        return self.state

    def replace_state(self, new_state: PetState) -> PetState:
        self.state = new_state
        self.state.clamp_all()
        self._refresh_derived_fields(evolved=False)
        return self.state

    def tick(self, steps: int = 1) -> PetState:
        """Avança o tempo biológico do pet em `steps` ticks discretos."""
        for _ in range(max(1, steps)):
            self._single_tick()
        return self.state

    def _single_tick(self) -> None:
        s = self.state
        cfg = self.config
        s.age_ticks += 1

        if s.is_sleeping:
            s.hunger += cfg.hunger_per_tick * cfg.sleep_hunger_factor
            s.energy += cfg.sleep_energy_recovery_per_tick
            # Acorda automaticamente quando energia chega a 100%
            if s.energy >= 100.0:
                s.energy = 100.0
                s.is_sleeping = False
                s.last_action = "WOKE UP"
        else:
            s.hunger += cfg.hunger_per_tick
            s.happiness -= cfg.happiness_decay_per_tick
            s.energy -= cfg.energy_decay_per_tick

        # Impacto na saúde conforme condições fisiológicas
        in_distress = (
            s.hunger >= cfg.critical_hunger_threshold
            or s.energy <= cfg.critical_energy_threshold
            or s.happiness <= cfg.critical_happiness_threshold
        )
        if in_distress:
            s.health -= cfg.health_penalty_per_tick
        elif s.hunger < 40.0 and s.energy > 50.0 and s.happiness > 60.0:
            s.health += cfg.health_regen_per_tick

        # Contagem regressiva de animação temporária
        if s.animation_ttl_ticks > 0:
            s.animation_ttl_ticks -= 1

        s.clamp_all()
        self._refresh_derived_fields(evolved=False)

    def apply_gesture(self, event: GestureEventPayload, min_confidence: float = 0.55) -> CommandType | None:
        """Traduz um evento de gesto em comando do pet se atingir confiança mínima."""
        if event.confidence < min_confidence:
            return None
        command = self.config.resolve_gesture(event.gesture)
        if command is None:
            return None
        self.apply_command(command, source_tag=f"G:{event.gesture.value[:6]}")
        return command

    def apply_command(self, command: CommandType, source_tag: str | None = None) -> PetState:
        """Executa um comando de interação sobre o estado do pet."""
        s = self.state
        cfg = self.config
        evolved = False
        prefix = f"{source_tag} " if source_tag else ""

        if command == CommandType.TICK:
            return self.tick(1)

        if command == CommandType.RESET:
            return self.reset()

        if command == CommandType.FEED:
            if s.is_sleeping:
                s.is_sleeping = False
            s.hunger += cfg.feed_hunger_delta
            s.health += cfg.feed_health_bonus
            s.care_counters["feed"] = s.care_counters.get("feed", 0) + 1
            evolved = self._grant_xp(cfg.feed_xp)
            self._trigger_animation(PetAnimation.EATING)
            s.last_action = f"{prefix}FED"[:20]

        elif command == CommandType.PLAY:
            if s.is_sleeping:
                s.is_sleeping = False
            if s.energy < cfg.play_min_energy:
                s.last_action = f"{prefix}TOO TIRED"[:20]
            else:
                s.happiness += cfg.play_happiness_delta
                s.energy += cfg.play_energy_delta
                s.hunger += cfg.play_hunger_delta
                s.care_counters["play"] = s.care_counters.get("play", 0) + 1
                evolved = self._grant_xp(cfg.play_xp)
                self._trigger_animation(PetAnimation.PLAYING)
                s.last_action = f"{prefix}PLAYED"[:20]

        elif command == CommandType.REST:
            s.is_sleeping = not s.is_sleeping
            if s.is_sleeping:
                s.care_counters["rest"] = s.care_counters.get("rest", 0) + 1
                evolved = self._grant_xp(cfg.rest_xp)
                s.animation = PetAnimation.SLEEPING
                s.animation_ttl_ticks = 0
                s.last_action = f"{prefix}SLEEPING"[:20]
            else:
                s.animation = PetAnimation.IDLE
                s.animation_ttl_ticks = 0
                s.last_action = f"{prefix}AWAKE"[:20]

        elif command == CommandType.INTERACT:
            if s.is_sleeping:
                # Carinho suave não acorda bruscamente, mas conforta
                s.happiness += cfg.interact_happiness_delta * 0.5
                s.last_action = f"{prefix}GENTLE PET"[:20]
            else:
                s.happiness += cfg.interact_happiness_delta
                s.energy += cfg.interact_energy_delta
                self._trigger_animation(PetAnimation.PETTING)
                s.last_action = f"{prefix}PETTED"[:20]
            s.care_counters["interact"] = s.care_counters.get("interact", 0) + 1
            evolved = self._grant_xp(cfg.interact_xp)

        elif command == CommandType.HEAL:
            s.health += cfg.heal_health_delta
            s.happiness += cfg.heal_happiness_delta
            s.care_counters["heal"] = s.care_counters.get("heal", 0) + 1
            evolved = self._grant_xp(cfg.heal_xp)
            self._trigger_animation(PetAnimation.HEALING)
            s.last_action = f"{prefix}HEALED"[:20]

        s.clamp_all()
        self._refresh_derived_fields(evolved=evolved)
        return self.state

    def can_start_launch(self) -> tuple[bool, str]:
        """Verifica se o pet está apto a iniciar uma partida de Pet Launch."""
        s = self.state
        if s.is_sleeping:
            return False, "PET DORMINDO"
        if s.mood == PetMood.SICK:
            return False, "PET DOENTE"
        if s.energy < self.config.launch_min_energy:
            return False, "ENERGIA BAIXA"
        return True, "PRONTO"

    def apply_launch_match(
        self,
        distance_m: float,
        score: int,
        coins_earned: int,
        xp_earned: int,
        bounces: int = 0,
    ) -> tuple[PetState, bool]:
        """Integra o resultado de uma partida do Pet Launch na fonte única do `PetState`."""
        s = self.state
        cfg = self.config
        ok, reason = self.can_start_launch()
        if not ok:
            s.last_action = reason[:20]
            return s, False

        dist = round(max(0.0, float(distance_m)), 2)
        pts = max(0, int(score))
        coins = max(0, int(coins_earned))
        xp = max(0, int(xp_earned))
        _ = bounces

        is_new_record = dist > s.best_launch_distance_m or pts > s.best_launch_score
        s.best_launch_distance_m = max(s.best_launch_distance_m, dist)
        s.best_launch_score = max(s.best_launch_score, pts)
        s.total_launches += 1
        s.coins += coins

        # Custo moderado de energia e estímulo positivo ao humor/vínculo
        s.energy -= cfg.launch_energy_cost
        s.hunger += cfg.launch_hunger_delta
        s.happiness += (
            cfg.launch_record_happiness_bonus if is_new_record else cfg.launch_happiness_bonus
        )
        s.care_counters["play"] = s.care_counters.get("play", 0) + 1

        evolved = self._grant_xp(xp)
        self._trigger_animation(PetAnimation.PLAYING)
        prefix = "REC!" if is_new_record else "LAUNCH"
        s.last_action = f"{prefix} {dist:.1f}m"[:20]

        s.clamp_all()
        self._refresh_derived_fields(evolved=evolved)
        return self.state, is_new_record

    def unlock_launch_upgrade(self, upgrade_id: str, cost: int) -> tuple[bool, str]:
        """Desbloqueia melhoria permanente do Pet Launch usando moedas acumuladas."""
        s = self.state
        uid = str(upgrade_id).strip().upper()
        price = max(0, int(cost))
        if not uid:
            return False, "UPGRADE INVALIDO"
        if uid in s.unlocked_upgrades:
            return False, "JA DESBLOQUEADO"
        if s.coins < price:
            return False, "MOEDAS INSUFICIENTES"

        s.coins -= price
        s.unlocked_upgrades.append(uid)
        s.happiness += 6.0
        self._trigger_animation(PetAnimation.PLAYING)
        s.last_action = f"UPG:{uid[:15]}"[:20]
        s.clamp_all()
        self._refresh_derived_fields(evolved=False)
        return True, f"DESBLOQUEADO: {uid}"

    def _grant_xp(self, amount: int) -> bool:
        if amount <= 0:
            return False
        s = self.state
        cfg = self.config
        prev_stage = s.stage
        s.xp += amount
        new_level = 1 + (s.xp // max(1, cfg.xp_per_level))
        if new_level > s.level:
            s.level = new_level

        if s.level >= cfg.cyber_rooster_min_level:
            s.stage = EvolutionStage.CYBER_ROOSTER
        elif s.level >= cfg.chick_min_level:
            s.stage = EvolutionStage.CHICK
        else:
            s.stage = EvolutionStage.EGG

        return s.stage != prev_stage

    def _trigger_animation(self, anim: PetAnimation) -> None:
        self.state.animation = anim
        self.state.animation_ttl_ticks = self.config.animation_default_ttl

    def _refresh_derived_fields(self, evolved: bool) -> None:
        s = self.state
        cfg = self.config

        # 1. Atualizar estágio coerente com nível
        if s.level >= cfg.cyber_rooster_min_level:
            s.stage = EvolutionStage.CYBER_ROOSTER
        elif s.level >= cfg.chick_min_level:
            s.stage = EvolutionStage.CHICK
        else:
            s.stage = EvolutionStage.EGG

        # 2. Atualizar personalidade emergente conforme histórico de cuidado
        total_actions = sum(s.care_counters.values())
        if total_actions >= 3:
            dominant = max(s.care_counters.items(), key=lambda kv: kv[1])[0]
            if dominant == "play":
                s.personality = PetPersonality.PLAYFUL
            elif dominant == "feed":
                s.personality = PetPersonality.FOODIE
            elif dominant == "rest":
                s.personality = PetPersonality.ZEN
            else:
                s.personality = PetPersonality.CURIOUS

        # 3. Atualizar humor prioritário
        if s.is_sleeping:
            s.mood = PetMood.SLEEPING
        elif s.health <= cfg.sick_health_threshold:
            s.mood = PetMood.SICK
        elif s.hunger >= cfg.critical_hunger_threshold:
            s.mood = PetMood.HUNGRY
        elif s.energy <= cfg.critical_energy_threshold:
            s.mood = PetMood.TIRED
        elif s.happiness <= cfg.critical_happiness_threshold:
            s.mood = PetMood.SAD
        elif s.happiness >= 85.0 and s.hunger <= 30.0 and s.energy >= 60.0 and s.health >= 80.0:
            s.mood = PetMood.ECSTATIC
        elif s.happiness >= 60.0 and s.hunger <= 55.0:
            s.mood = PetMood.HAPPY
        else:
            s.mood = PetMood.CONTENT

        # 4. Atualizar animação ativa
        if evolved:
            s.animation = PetAnimation.EVOLVING
            s.animation_ttl_ticks = cfg.animation_default_ttl + 2
            s.last_action = f"EVOLVED->{s.stage.value[:9]}"[:20]
        elif s.is_sleeping:
            s.animation = PetAnimation.SLEEPING
            s.animation_ttl_ticks = 0
        elif s.animation_ttl_ticks == 0:
            if s.mood == PetMood.SICK:
                s.animation = PetAnimation.SICK
            else:
                s.animation = PetAnimation.IDLE
