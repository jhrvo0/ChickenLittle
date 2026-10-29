"""Renderizador estrito para o display físico/simulado LCD 2004A V1.1 (20 colunas x 4 linhas)."""

from __future__ import annotations

from terminal.communication.protocol import LcdFramePayload, SensorFramePayload
from terminal.pet.state import EvolutionStage, PetAnimation, PetMood, PetState

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
