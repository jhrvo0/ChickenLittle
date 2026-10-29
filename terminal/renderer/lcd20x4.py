"""Renderizador estrito para o display físico/simulado LCD 2004A V1.1 (20 colunas x 4 linhas)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from terminal.communication.protocol import LcdFramePayload, SensorFramePayload
from terminal.pet.state import EvolutionStage, PetAnimation, PetMood, PetState

if TYPE_CHECKING:
    from terminal.games.pet_launch import LaunchResult
    from terminal.games.physics import LaunchPhysicsState

_STAGE_SHORT: dict[EvolutionStage, str] = {
    EvolutionStage.EGG: "EGG",
    EvolutionStage.CHICK: "CHK",
    EvolutionStage.CYBER_ROOSTER: "CYB",
}

_MOOD_SHORT: dict[PetMood, str] = {
    PetMood.ECSTATIC: "ECST",
    PetMood.HAPPY: "HAPY",
    PetMood.CONTENT: "OKAY",
    PetMood.HUNGRY: "HNGR",
    PetMood.TIRED: "TIRD",
    PetMood.SAD: "SAD!",
    PetMood.SICK: "SICK",
    PetMood.SLEEPING: "ZZZ.",
}

_ANIM_BADGES: dict[PetAnimation, tuple[str, str]] = {
    PetAnimation.IDLE: ("*IDLE*", ".IDLE."),
    PetAnimation.EATING: ("~EAT!~", "*CHMP*"),
    PetAnimation.PLAYING: (">PLAY<", "^JUMP^"),
    PetAnimation.SLEEPING: ("zZZZZz", ".zZZz."),
    PetAnimation.PETTING: ("<3PET!", "*LUV!*"),
    PetAnimation.HEALING: ("+HEAL+", "*CURE*"),
    PetAnimation.EVOLVING: ("!EVOL!", "*LVL+*"),
    PetAnimation.SICK: ("!SICK!", "!HELP!"),
}


def _sanitize_ascii(text: str, width: int) -> str:
    """Garante string ASCII imprimível (0x20..0x7E) com largura fixa exata."""
    cleaned_chars = [ch if 0x20 <= ord(ch) <= 0x7E else "?" for ch in text]
    cleaned = "".join(cleaned_chars)
    return cleaned[:width].ljust(width)


class Lcd20x4Renderer:
    """Gera quadros 20x4 compatíveis com controlador HD44780 a partir de `PetState`."""

    def render(
        self,
        state: PetState,
        frame_idx: int = 0,
        sensor: SensorFramePayload | None = None,
    ) -> LcdFramePayload:
        parity = frame_idx % 2

        # Linha 0: Nome(7) + Estágio(3) + Nível(3) + Humor(4) = 20 cols
        stage_txt = _STAGE_SHORT.get(state.stage, "PET")
        mood_txt = _MOOD_SHORT.get(state.mood, "OKAY")
        lvl = min(max(state.level, 1), 99)
        raw_l0 = f"{state.name[:7]:<7} {stage_txt:3} L{lvl:02d} {mood_txt:4}"

        # Linha 1: Face ASCII(6) + Fome(6) + Felicidade(6) = 20 cols
        face = self._select_face(state, parity)
        hg = int(round(state.hunger))
        hp = int(round(state.happiness))
        raw_l1 = f"{face:6} HG:{hg:3d} HP:{hp:3d}"

        # Linha 2: Badge animação(6) + Energia(6) + Saúde(6) = 20 cols
        badges = _ANIM_BADGES.get(state.animation, ("*IDLE*", ".IDLE."))
        badge = badges[parity]
        en = int(round(state.energy))
        hl = int(round(state.health))
        raw_l2 = f"{badge:6} EN:{en:3d} HL:{hl:3d}"

        # Linha 3: Distância sensor (8) + Última ação (12) = 20 cols
        if sensor is not None and sensor.valid_ultrasonic and sensor.distance_cm is not None:
            dist_int = min(max(int(round(sensor.distance_cm)), 0), 999)
            dist_txt = f"D:{dist_int:03d}cm "
        else:
            dist_txt = "D:---cm "
        raw_l3 = f"{dist_txt}{state.last_action[:12]:<12}"

        lines = (
            _sanitize_ascii(raw_l0, 20),
            _sanitize_ascii(raw_l1, 20),
            _sanitize_ascii(raw_l2, 20),
            _sanitize_ascii(raw_l3, 20),
        )
        return LcdFramePayload(lines=lines)

    def render_launch(
        self,
        state: PetState,
        phase: str,
        angle_deg: float = 45.0,
        charge_norm: float = 0.0,
        phys: LaunchPhysicsState | None = None,
        last_result: LaunchResult | None = None,
        best_distance_m: float = 0.0,
        sweet_spot: bool = False,
        frame_idx: int = 0,
    ) -> LcdFramePayload:
        """Renderiza os 6 estados dedicados do Pet Launch estritamente em 20x4 ASCII."""
        parity = frame_idx % 2
        face = self._select_face(state, parity)
        stage_txt = _STAGE_SHORT.get(state.stage, "PET")
        en = min(max(int(round(state.energy)), 0), 100)
        rec = max(best_distance_m, state.best_launch_distance_m)
        ph = str(phase).upper()

        if ph in ("MENU", "SELECT_PET", "PREP"):
            # Estado 1: Preparação (Menu / Seleção / Rampa)
            hdr = "MENU" if ph == "MENU" else ("PET OK" if ph == "SELECT_PET" else "PREPARE")
            raw_l0 = f"PET LAUNCH: {hdr:<8}"
            raw_l1 = f"{state.name[:7]:<7} {stage_txt:3} EN:{en:3d}%"
            raw_l2 = f"ANG:{angle_deg:4.1f}d REC:{min(999.0, rec):4.0f}m"
            act_hint = "[APP]JOGAR [U]LOJA  " if ph == "MENU" else "[HOLD]CARR [APP]OK  "
            raw_l3 = act_hint

        elif ph == "CHARGING":
            # Estado 2: Carregamento de força
            clamped = max(0.0, min(1.0, float(charge_norm)))
            filled = int(round(clamped * 8))
            bar8 = ("#" * filled) + ("-" * (8 - filled))
            pct = int(round(clamped * 100.0))
            tag = "*" if sweet_spot else " "
            raw_l0 = "PET LAUNCH: CARGA   "
            raw_l1 = f"PWR:[{bar8}]{tag}{pct:3d}%"
            raw_l2 = f"ANG:{angle_deg:4.1f}d  {face:6}"
            raw_l3 = "APP:LANCA  RET:CANC "

        elif ph == "LAUNCHING":
            # Estado 3: Lançamento / Disparo na rampa
            v0 = phys.initial_speed_mps if phys is not None else 0.0
            raw_l0 = "PET LAUNCH: DISPARO!"
            raw_l1 = ">> LANCAMENTO! >>   "
            raw_l2 = f"V0:{min(99.9, v0):4.1f}m/s A:{angle_deg:4.1f}d"
            raw_l3 = f"{state.name[:7]:<7} DECOLANDO!  "

        elif ph == "FLIGHT":
            # Estado 4: Voo balístico / Quiques / Rolagem
            x_m = min(999.9, phys.x_m) if phys is not None else 0.0
            y_m = min(999.9, phys.y_m) if phys is not None else 0.0
            spd = min(99.9, phys.speed_mps) if phys is not None else 0.0
            bnc = min(9, phys.bounces) if phys is not None else 0
            st_cnt = min(9, len(phys.collected_stars)) if phys is not None else 0
            mphase = phys.motion_phase.value[:8] if phys is not None else "AIRBORNE"
            raw_l0 = "PET LAUNCH: EM VOO  "
            raw_l1 = f"DIST:{x_m:5.1f}m B:{bnc:1d} *{st_cnt:1d}"
            raw_l2 = f"ALT :{y_m:5.1f}m V:{spd:4.1f}"
            raw_l3 = f"FASE:{mphase:<8} {face:6}"

        elif ph == "RESULT":
            # Estado 5: Resultado da partida e recompensas
            dist = min(999.9, last_result.distance_m) if last_result is not None else 0.0
            pts = min(99999, last_result.score) if last_result is not None else 0
            coins = min(99, last_result.coins_reward) if last_result is not None else 0
            xp = min(99, last_result.xp_reward) if last_result is not None else 0
            is_rec = bool(last_result.is_new_record) if last_result is not None else False
            raw_l0 = "RESULTADO *RECORDE!*" if is_rec else "PET LAUNCH: PLACAR  "
            raw_l1 = f"D:{dist:5.1f}m PTS:{pts:5d}"
            raw_l2 = f"MOEDAS:+{coins:2d}  XP:+{xp:2d}"
            raw_l3 = f"{face:6} [APP] MENU   "

        else:
            # Estado 6: Retorno ao pet (RETURN_TO_PET)
            coins_tot = min(9999, state.coins)
            raw_l0 = "RETORNO AO MOTIONPET"
            raw_l1 = f"{state.name[:7]:<7} MOEDAS:{coins_tot:4d}"
            raw_l2 = f"REC:{min(999.9, rec):5.1f}m EN:{en:3d}%"
            raw_l3 = f"{face:6} ATE A PROXIMA"

        lines = (
            _sanitize_ascii(raw_l0, 20),
            _sanitize_ascii(raw_l1, 20),
            _sanitize_ascii(raw_l2, 20),
            _sanitize_ascii(raw_l3, 20),
        )
        return LcdFramePayload(lines=lines)

    @staticmethod
    def _select_face(state: PetState, parity: int) -> str:
        if state.stage == EvolutionStage.EGG:
            if state.is_sleeping:
                return "(-_-)z" if parity == 0 else "(-_-)Z"
            return "[o_o] " if parity == 0 else "[O_o]~"

        if state.is_sleeping:
            return "(-v-)z" if parity == 0 else "(-v-)Z"
        if state.mood == PetMood.SICK:
            return "(x_x)!" if parity == 0 else "(+_+)!"
        if state.animation == PetAnimation.EATING:
            return "(>O<)*" if parity == 0 else "(>v<)."
        if state.animation == PetAnimation.PLAYING:
            return "\\^v^/*" if parity == 0 else "/^v^\\+"
        if state.animation == PetAnimation.PETTING:
            return "(^v^)<" if parity == 0 else "(>v<)3"
        if state.animation == PetAnimation.EVOLVING:
            return "*\\O/*+" if parity == 0 else "+/O\\*+"
        if state.mood == PetMood.HUNGRY:
            return "(oAo)?" if parity == 0 else "(o_o)!"
        if state.mood in (PetMood.SAD, PetMood.TIRED):
            return "(;v;) " if parity == 0 else "(._.) "
        if state.mood == PetMood.ECSTATIC:
            return "(^v^)*" if parity == 0 else "(^o^)*"
        return "(^v^) " if parity == 0 else "(^v^)~"
