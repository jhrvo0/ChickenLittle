"""Renderizador ASCII rico para o terminal do notebook, sincronizado com o estado e o LCD 20x4."""

from __future__ import annotations

from dataclasses import dataclass

from terminal.communication.protocol import (
    AppModeId,
    GestureEventPayload,
    LcdFramePayload,
    SensorFramePayload,
)
from terminal.pet.state import EvolutionStage, PetAnimation, PetMood, PetState


@dataclass(frozen=True)
class HudTelemetry:
    """Dados de telemetria exibidos no HUD do terminal."""

    mode: AppModeId = AppModeId.MOTION_PET
    sensor: SensorFramePayload | None = None
    last_gesture: GestureEventPayload | None = None
    tx_packets: int = 0
    rx_packets: int = 0
    save_status: str = "NAO SALVO"
    transport_label: str = "VIRTUAL_SERIAL_JSONL_V1"
    mode_banner: str = ""


def _progress_bar(value: float, width: int = 12) -> str:
    clamped = max(0.0, min(100.0, value))
    filled = int(round((clamped / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {clamped:5.1f}%"


class TerminalAsciiRenderer:
    """Renderiza o painel completo do MotionPet em ASCII puro."""

    PANEL_WIDTH = 86

    def render(
        self,
        state: PetState,
        lcd_frame: LcdFramePayload,
        frame_idx: int = 0,
        telemetry: HudTelemetry | None = None,
    ) -> str:
        tel = telemetry or HudTelemetry()
        w = self.PANEL_WIDTH
        border = "+" + ("=" * (w - 2)) + "+"
        sep = "+" + ("-" * (w - 2)) + "+"

        out: list[str] = [border]
        title = (
            f" MOTIONPET v0.1 | MODO: {tel.mode.value:<12} | "
            f"LINK: {tel.transport_label:<23} | T:{state.age_ticks:04d} "
        )
        out.append("|" + title[: w - 2].ljust(w - 2) + "|")
        out.append(sep)

        if tel.mode != AppModeId.MOTION_PET and tel.mode_banner:
            for bline in tel.mode_banner.splitlines():
                out.append("| " + bline[: w - 4].ljust(w - 4) + " |")
            out.append(sep)

        # Coluna esquerda (36 chars): cena ASCII animada
        # Coluna direita (45 chars): atributos + espelho LCD 20x4
        scene_lines = self._build_scene(state, frame_idx)
        right_lines = self._build_right_panel(state, lcd_frame)

        max_rows = max(len(scene_lines), len(right_lines))
        while len(scene_lines) < max_rows:
            scene_lines.append("")
        while len(right_lines) < max_rows:
            right_lines.append("")

        for left, right in zip(scene_lines, right_lines):
            row_txt = f"| {left[:35]:<35} | {right[:44]:<44} |"
            out.append(row_txt)

        out.append(sep)

        # Telemetria de sensores e gestos
        for tline in self._build_telemetry_lines(tel):
            out.append("| " + tline[: w - 4].ljust(w - 4) + " |")

        out.append(sep)

        # Controles de teclado
        controls = [
            "CONTROLES: [F] Alimentar  [P] Brincar  [R] Dormir/Acordar  [C] Curar  [I] Carinho",
            "GESTOS SIM: [1] APPROACH  [2] RETREAT  [3] HOLD  [4] NEUTRAL   |  [T] Avancar Tick",
            "SISTEMA:    [S] Salvar    [L] Carregar [M] Modo  [N] Reset     |  [Q] Sair",
        ]
        for cline in controls:
            out.append("| " + cline[: w - 4].ljust(w - 4) + " |")

        out.append(border)
        return "\n".join(out)

    def _build_right_panel(self, state: PetState, lcd_frame: LcdFramePayload) -> list[str]:
        xp_in_lvl = state.xp % 50
        lines = [
            f"PET: {state.name:<10} NV:{state.level:02d} (XP:{xp_in_lvl:02d}/50)",
            f"ESTAGIO: {state.stage.value:<13} HUMOR: {state.mood.value:<8}",
            f"PERFIL:  {state.personality.value:<13} ANIM:  {state.animation.value:<8}",
            "",
            f"Fome (0=ok): {_progress_bar(state.hunger, 12)}",
            f"Felicidade : {_progress_bar(state.happiness, 12)}",
            f"Energia    : {_progress_bar(state.energy, 12)}",
            f"Saude      : {_progress_bar(state.health, 12)}",
            "",
            "ESPELHO LCD FISICO 20x4 (HD44780):",
            "  +--------------------+",
            f"  |{lcd_frame.lines[0]}|",
            f"  |{lcd_frame.lines[1]}|",
            f"  |{lcd_frame.lines[2]}|",
            f"  |{lcd_frame.lines[3]}|",
            "  +--------------------+",
        ]
        return lines

    def _build_scene(self, state: PetState, frame_idx: int) -> list[str]:
        parity = frame_idx % 2
        sky = "   .   *       .        *     .   " if parity == 0 else "     *     .        *       .     "
        if not state.is_sleeping:
            sky = "    \\ | /                     .   " if parity == 0 else "     -O-         ~        ~       "

        fx = self._animation_overlay(state, parity)
        sprite = self._select_sprite(state, parity)
        ground = "==================================="
        status = f"ACAO: {state.last_action}"

        scene = [
            "CENARIO DO PET (TERMINAL):",
            sky,
            fx,
            *sprite,
            ground,
            status,
        ]
        return scene

    @staticmethod
    def _animation_overlay(state: PetState, parity: int) -> str:
        if state.is_sleeping:
            return "                 z   Z   z         " if parity == 0 else "               Z   z   Z           "
        if state.animation == PetAnimation.EATING:
            return "         * nhac *   * croc *       " if parity == 0 else "           * croc *   * nhac *     "
        if state.animation == PetAnimation.PLAYING:
            return "        *  \\o/  *   +   *          " if parity == 0 else "          +   *   \\o/   +          "
        if state.animation == PetAnimation.PETTING:
            return "            <3     <3              " if parity == 0 else "              <3       <3          "
        if state.animation == PetAnimation.HEALING:
            return "           [+]   [+]   [+]         " if parity == 0 else "             [+]   [+]             "
        if state.animation == PetAnimation.EVOLVING:
            return "       *** EVOLUCAO TINY-PET ***   "
        if state.mood == PetMood.SICK:
            return "            ! ALERTA SAUDE !       "
        if state.mood == PetMood.HUNGRY:
            return "            ( precisando comer )   "
        return "                                   "

    @staticmethod
    def _select_sprite(state: PetState, parity: int) -> list[str]:
        eye = "-" if state.is_sleeping else ("x" if state.mood == PetMood.SICK else "^")
        if state.mood in (PetMood.SAD, PetMood.TIRED) and not state.is_sleeping:
            eye = ";"

        if state.stage == EvolutionStage.EGG:
            wobble = " " if parity == 0 else "  "
            return [
                "                                   ",
                f"{wobble}           .-\"\"\"-.               ",
                f"{wobble}          /  . .  \\              ",
                f"{wobble}         |  ({eye}_{eye})  |             ",
                f"{wobble}         |   ~~~   |             ",
                f"{wobble}          \\_______/              ",
                "             (ovo vivo)            ",
                "                                   ",
                "                                   ",
                "                                   ",
            ]

        if state.stage == EvolutionStage.CHICK:
            beak = "O" if state.animation == PetAnimation.EATING and parity == 0 else "v"
            wing_l = "\\" if (state.animation == PetAnimation.PLAYING and parity == 0) else "("
            wing_r = "/" if (state.animation == PetAnimation.PLAYING and parity == 0) else ")"
            hop_top = "" if (state.animation == PetAnimation.PLAYING and parity == 0) else "                                   "
            hop_bot = "                                   " if not hop_top else ""
            rows = []
            if hop_top:
                rows.append(hop_top)
            rows.extend(
                [
                    "              ,\\//,                ",
                    "             .-\"\"\"-.               ",
                    f"            / ({eye} {beak} {eye}) \\            ",
                    f"           {wing_l}    _    {wing_r}           ",
                    "             '-----'               ",
                    "              _| |_                ",
                    "                                   ",
                    "                                   ",
                    "                                   ",
                ]
            )
            if hop_bot:
                rows.append(hop_bot)
            return rows[:10]

        # EvolutionStage.CYBER_ROOSTER
        visor = "==" if state.is_sleeping else ("!!" if state.mood == PetMood.SICK else "<>")
        crest = "/\\/\\" if parity == 0 else "\\/\\/"
        return [
            f"             {crest}  [ANT]          ",
            "            .-\"\"\"\"\"-.  |           ",
            f"           / [{eye}:{visor}:{eye}] \\-+          ",
            "          |    \\^/    |            ",
            "         /|   [===]   |\\           ",
            "        /_|  /     \\  |_\\          ",
            "            '-------'              ",
            "             _/   \\_               ",
            "          (cyber-rooster)          ",
            "                                   ",
        ]

    @staticmethod
    def _build_telemetry_lines(tel: HudTelemetry) -> list[str]:
        if tel.sensor is not None:
            if tel.sensor.valid_ultrasonic and tel.sensor.distance_cm is not None:
                dist_str = f"{tel.sensor.distance_cm:6.1f} cm"
            else:
                dist_str = "TIMEOUT/INV"
            ir_str = "ATIVO " if tel.sensor.ir_detected else "LIVRE "
            pot_str = f"{tel.sensor.pot_norm * 100.0:5.1f}%"
        else:
            dist_str = "   --- cm"
            ir_str = "  --- "
            pot_str = "  ---%"

        if tel.last_gesture is not None:
            g = tel.last_gesture
            gest_str = f"{g.gesture.value:<8} ({g.confidence * 100.0:4.0f}% via {g.source.value})"
        else:
            gest_str = "NENHUM"

        line1 = f"SENSORES | HC-SR04: {dist_str:<11} | IR TCRT5000: {ir_str} | POT: {pot_str}"
        line2 = (
            f"EVENTOS  | Ultimo Gesto: {gest_str:<33} | "
            f"PKT TX/RX: {tel.tx_packets}/{tel.rx_packets}"
        )
        line3 = f"PERSIST. | Save: {tel.save_status}"
        return [line1, line2, line3]
