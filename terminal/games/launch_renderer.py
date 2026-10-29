"""Renderizador ASCII dedicado do Pet Launch (Padrão 86 cols, Modo Compacto e Anti-Flicker).

Atende aos requisitos de UX em terminal:
- Cenário horizontal rolante sincronizado com `HorizontalCamera` (céu, estrelas `*`, trilha `.`,
  marcadores de distância no chão, rampa e pet animado com reação emocional).
- Telas dedicadas para Menu/Loja, Seleção do Pet, Preparação/Barra de Força, Voo e Placar Final.
- Detecção das dimensões do terminal com modo compacto (`60` colunas) para janelas pequenas.
- `DifferentialTerminalWriter` para atualização diferencial linha a linha (sem flicker no Windows).
"""

from __future__ import annotations

import shutil
from typing import TextIO

from terminal.communication.protocol import LcdFramePayload
from terminal.games.pet_launch import (
    LAUNCH_UPGRADES,
    LaunchPhase,
    PetLaunchGame,
    describe_personality_perk,
)
from terminal.games.physics import FlightMotionPhase
from terminal.pet.state import EvolutionStage, PetState
from terminal.renderer.ascii_terminal import HudTelemetry


def _fit_ascii(text: str, width: int) -> str:
    """Garante string ASCII imprimível (0x20..0x7E) com largura exata `width`."""
    cleaned = "".join(ch if 0x20 <= ord(ch) <= 0x7E else "?" for ch in text)
    return cleaned[:width].ljust(width)


def detect_terminal_dimensions(
    fallback_cols: int = 86,
    fallback_rows: int = 34,
) -> tuple[int, int]:
    """Obtém `(colunas, linhas)` atuais do terminal com fallback seguro."""
    size = shutil.get_terminal_size((fallback_cols, fallback_rows))
    return max(40, int(size.columns)), max(15, int(size.lines))


def should_use_compact_layout(
    term_cols: int | None = None,
    term_rows: int | None = None,
    force_compact: bool = False,
) -> bool:
    """Ativa layout compacto quando solicitado ou quando o terminal é menor que 86x26."""
    if force_compact:
        return True
    if term_cols is not None and term_cols < 86:
        return True
    if term_rows is not None and term_rows < 26:
        return True
    return False


class DifferentialTerminalWriter:
    """Atualizador ANSI linha a linha que reescreve apenas linhas alteradas (anti-flicker)."""

    def __init__(self, stream: TextIO, is_tty: bool = True) -> None:
        self.stream = stream
        self.is_tty = is_tty
        self._prev_lines: list[str] = []
        self.frames_rendered: int = 0
        self.last_changed_lines: int = 0
        self.total_line_writes: int = 0

    def reset(self) -> None:
        self._prev_lines = []

    def write_frame(self, frame_text: str) -> int:
        """Escreve apenas o diff em relação ao frame anterior. Retorna nº de linhas reescritas."""
        self.frames_rendered += 1
        if not self.is_tty:
            self.stream.write(frame_text + "\n")
            self.stream.flush()
            lines = frame_text.splitlines()
            self.last_changed_lines = len(lines)
            self.total_line_writes += len(lines)
            self._prev_lines = lines
            return self.last_changed_lines

        new_lines = frame_text.splitlines()
        chunks: list[str] = []
        changed = 0

        for idx, line in enumerate(new_lines):
            if idx >= len(self._prev_lines) or self._prev_lines[idx] != line:
                row_1based = idx + 1
                chunks.append(f"\x1b[{row_1based};1H{line}\x1b[K")
                changed += 1

        # Se o frame anterior tinha mais linhas, limpa o excedente inferior
        if len(self._prev_lines) > len(new_lines):
            for extra_idx in range(len(new_lines), len(self._prev_lines)):
                row_1based = extra_idx + 1
                chunks.append(f"\x1b[{row_1based};1H\x1b[K")
                changed += 1

        # Estaciona o cursor logo abaixo do painel
        end_row = len(new_lines) + 1
        chunks.append(f"\x1b[{end_row};1H")

        if chunks:
            self.stream.write("".join(chunks))
            self.stream.flush()

        self._prev_lines = new_lines
        self.last_changed_lines = changed
        self.total_line_writes += changed
        return changed


def _power_bar_ascii(charge_norm: float, width: int = 20, sweet_min: float = 0.80, sweet_max: float = 0.95) -> str:
    """Barra de força com marcação visual da zona de Sweet-Spot (`*`)."""
    p = max(0.0, min(1.0, float(charge_norm)))
    filled = int(round(p * width))
    s_lo = int(round(sweet_min * width))
    s_hi = max(s_lo, int(round(sweet_max * width)))
    chars: list[str] = []
    for i in range(width):
        in_sweet = s_lo <= i < s_hi
        if i < filled:
            chars.append("*" if in_sweet else "#")
        else:
            chars.append(":" if in_sweet else "-")
    return "[" + "".join(chars) + "]"


class PetLaunchAsciiRenderer:
    """Renderiza a arena e as telas interativas do Pet Launch em padrão (86c) ou compacto (60c)."""

    STANDARD_WIDTH = 86
    COMPACT_WIDTH = 60

    def render(
        self,
        game: PetLaunchGame,
        state: PetState,
        lcd_frame: LcdFramePayload,
        frame_idx: int = 0,
        telemetry: HudTelemetry | None = None,
        compact: bool = False,
    ) -> str:
        tel = telemetry or HudTelemetry()
        if compact:
            return self._render_compact(game, state, lcd_frame, frame_idx, tel)
        return self._render_standard(game, state, lcd_frame, frame_idx, tel)

    def _render_standard(
        self,
        game: PetLaunchGame,
        state: PetState,
        lcd_frame: LcdFramePayload,
        frame_idx: int,
        tel: HudTelemetry,
    ) -> str:
        w = self.STANDARD_WIDTH
        inner = w - 4  # 82 chars úteis entre "| " e " |"
        border = "+" + ("=" * (w - 2)) + "+"
        sep = "+" + ("-" * (w - 2)) + "+"

        out: list[str] = [border]
        rec_dist = max(game.best_distance_m, state.best_launch_distance_m)
        title = (
            f" MOTIONPET | PET LAUNCH [{game.phase.value:<10}] | "
            f"MOEDAS: {state.coins:03d} | RECORDE: {rec_dist:5.1f}m | T:{state.age_ticks:04d} "
        )
        out.append("|" + _fit_ascii(title, w - 2) + "|")
        out.append(sep)

        # 1. Arena horizontal rolante (82 colunas x 8 linhas de céu/solo + régua de distância)
        arena_lines = self._build_scrolling_arena(
            game=game,
            state=state,
            cols=inner,
            sky_rows=7,
            frame_idx=frame_idx,
        )
        for aline in arena_lines:
            out.append("| " + _fit_ascii(aline, inner) + " |")

        out.append(sep)

        # 2. Painel dividido inferior: Esquerda (45c: Menu/Barra/Placar) | Direita (34c: Pet + Espelho LCD 20x4)
        # Verificação de largura: 2 ("| ") + 45 + 3 (" | ") + 34 + 2 (" |") = 86 colunas exatas!
        left_w = 45
        right_w = 34
        left_lines = self._build_phase_panel(game, state, width=left_w)
        right_lines = self._build_pet_and_lcd_panel(state, lcd_frame, width=right_w)

        rows = max(len(left_lines), len(right_lines))
        while len(left_lines) < rows:
            left_lines.append("")
        while len(right_lines) < rows:
            right_lines.append("")

        for ltxt, rtxt in zip(left_lines, right_lines):
            out.append(f"| {_fit_ascii(ltxt, left_w)} | {_fit_ascii(rtxt, right_w)} |")

        out.append(sep)

        # 3. Reação do pet + telemetria enxuta de gestos/sensores
        out.append("| " + _fit_ascii(f"REACAO PET | {game.pet_reaction}", inner) + " |")
        out.append("| " + _fit_ascii(self._format_sensor_gesture_line(tel, game), inner) + " |")
        out.append(sep)

        # 4. Controles claros do modo Pet Launch (Teclado + Gestos Prioritários)
        ctrl_1 = "JOGO: [ENTER/1:APPROACH] OK/Lancar | [SPACE/3:HOLD] Forca | [B/2:RETREAT] Voltar"
        ctrl_2 = "MIRA: [W/Z ou +/- POT] Angulo | LOJA: [U/7/8/9] | [M] Modo [S] Salvar [Q] Sair"
        out.append("| " + _fit_ascii(ctrl_1, inner) + " |")
        out.append("| " + _fit_ascii(ctrl_2, inner) + " |")
        out.append(border)
        return "\n".join(out)

    def _render_compact(
        self,
        game: PetLaunchGame,
        state: PetState,
        lcd_frame: LcdFramePayload,
        frame_idx: int,
        tel: HudTelemetry,
    ) -> str:
        w = self.COMPACT_WIDTH
        inner = w - 4  # 56 chars úteis
        border = "+" + ("=" * (w - 2)) + "+"
        sep = "+" + ("-" * (w - 2)) + "+"
        rec_dist = max(game.best_distance_m, state.best_launch_distance_m)

        out: list[str] = [border]
        hdr = f" PET LAUNCH [{game.phase.value[:8]:<8}] ${state.coins:03d} REC:{rec_dist:5.1f}m EN:{state.energy:3.0f}% "
        out.append("|" + _fit_ascii(hdr, w - 2) + "|")
        out.append(sep)

        arena_lines = self._build_scrolling_arena(
            game=game,
            state=state,
            cols=inner,
            sky_rows=4,
            frame_idx=frame_idx,
        )
        for aline in arena_lines:
            out.append("| " + _fit_ascii(aline, inner) + " |")
        out.append(sep)

        # Resumo compacto da fase atual (4 linhas) + LCD linha principal
        phase_lines = self._build_phase_panel(game, state, width=inner)[:4]
        for pline in phase_lines:
            out.append("| " + _fit_ascii(pline, inner) + " |")

        out.append("| " + _fit_ascii(f"PET: {game.pet_reaction}", inner) + " |")
        out.append("| " + _fit_ascii(f"LCD0:[{lcd_frame.lines[0]}] LCD1:[{lcd_frame.lines[1]}]", inner) + " |")
        out.append(sep)
        _ = tel
        out.append("| " + _fit_ascii("[ENT/1]OK/Lanca [SPC/3]Forca [B/2]Volta [U]Loja [M/Q]", inner) + " |")
        out.append(border)
        return "\n".join(out)

    def _build_scrolling_arena(
        self,
        game: PetLaunchGame,
        state: PetState,
        cols: int,
        sky_rows: int,
        frame_idx: int,
    ) -> list[str]:
        """Desenha viewport 2D horizontal com câmera seguindo o pet, trilha, estrelas e régua."""
        pstate = game.physics.state
        cam = game.physics.camera
        in_flight = game.phase in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT, LaunchPhase.RESULT)
        if not in_flight:
            cam_left = 0.0
            view_w_m = cam.viewport_width_m
        else:
            cam_left = cam.x_left_m
            view_w_m = cam.viewport_width_m

        max_alt_view_m = 16.0
        canvas: list[list[str]] = [[" " for _ in range(cols)] for _ in range(sky_rows)]

        def world_to_cell(wx: float, wy: float) -> tuple[int, int] | None:
            if wx < cam_left or wx > cam_left + view_w_m:
                return None
            c = int(round(((wx - cam_left) / max(1e-6, view_w_m)) * (cols - 1)))
            c = max(0, min(cols - 1, c))
            norm_y = max(0.0, min(1.0, wy / max_alt_view_m))
            r = (sky_rows - 1) - int(round(norm_y * (sky_rows - 1)))
            r = max(0, min(sky_rows - 1, r))
            return r, c

        def stamp(row: int, col: int, sprite: str) -> None:
            if row < 0 or row >= sky_rows:
                return
            for i, ch in enumerate(sprite):
                cc = col + i
                if 0 <= cc < cols:
                    canvas[row][cc] = ch

        # 1. Nuvens em paralaxe suave no topo do céu
        cloud_shift = int(cam_left * 0.7 + (frame_idx % 4 == 0))
        for c in range(2, cols - 4, 19):
            pos = (c - (cloud_shift % 19)) % max(1, cols - 4)
            stamp(0, pos, "~ ~~")
            if sky_rows >= 5:
                stamp(1, (pos + 9) % max(1, cols - 3), "~~")

        # 2. Bandeira de recorde pessoal na pista (quando visível na janela)
        rec_m = max(game.best_distance_m, state.best_launch_distance_m)
        if rec_m > 1.0:
            rc = world_to_cell(rec_m, 0.2)
            if rc is not None:
                stamp(sky_rows - 1, max(0, rc[1] - 1), "|R!")

        # 3. Estrelas colecionáveis ao longo do percurso
        for star in game.physics.stars:
            if in_flight and star.star_id in pstate.collected_stars:
                continue
            cell = world_to_cell(star.x_m, star.y_m)
            if cell is not None:
                stamp(cell[0], cell[1], "*")

        # 4. Rampa de lançamento em x = 0m quando visível
        pad_cell = world_to_cell(0.0, 0.0)
        if pad_cell is not None:
            stamp(sky_rows - 1, pad_cell[1], "_/|")

        # 5. Trilha parabólica (`.`) e sprite animado do Pet
        if in_flight:
            for tx, ty in game.physics.trail[:-1]:
                tcell = world_to_cell(tx, ty)
                if tcell is not None and canvas[tcell[0]][tcell[1]] == " ":
                    canvas[tcell[0]][tcell[1]] = "."

            pet_cell = world_to_cell(pstate.x_m, pstate.y_m)
            if pet_cell is not None:
                sprite = self._select_flying_pet_token(state, pstate.vy_mps, pstate.motion_phase, frame_idx)
                start_c = max(0, min(cols - len(sprite), pet_cell[1] - len(sprite) // 2))
                stamp(pet_cell[0], start_c, sprite)
        else:
            # Pet posicionado na rampa aguardando disparo
            idle_tok = self._select_ramp_pet_token(state, game.phase, frame_idx)
            stamp(max(0, sky_rows - 2), 1, idle_tok)
            # Vetor visual do ângulo de mira
            aim_glyph = "^" if game.angle_deg >= 55.0 else ("/" if game.angle_deg >= 32.0 else ">")
            stamp(max(0, sky_rows - 2), 1 + len(idle_tok) + 1, f"--{aim_glyph} {game.angle_deg:4.1f}d")

        # 6. HUD flutuante no canto superior direito da arena
        hud_tag = (
            f"DIST:{pstate.x_m:5.1f}m ALT:{pstate.y_m:4.1f}m V:{pstate.speed_mps:4.1f}m/s"
            if in_flight
            else f"MIRA:{game.angle_deg:4.1f}d FORCA:{game.charge_norm * 100.0:3.0f}%"
        )
        if cols > len(hud_tag) + 2:
            stamp(0, cols - len(hud_tag) - 1, hud_tag)

        # 7. Linha do chão + régua horizontal de distância sincronizada com a câmera
        ground_chars = ["=" for _ in range(cols)]
        ruler_chars = [" " for _ in range(cols)]
        first_tick_m = int(cam_left // 10.0) * 10
        tick_m = max(0, first_tick_m)
        while tick_m <= int(cam_left + view_w_m) + 10:
            tc = world_to_cell(float(tick_m), 0.0)
            if tc is not None:
                c = tc[1]
                ground_chars[c] = "+"
                label = f"{tick_m:03d}m"
                for i, ch in enumerate(label):
                    if c + i < cols:
                        ruler_chars[c + i] = ch
            tick_m += 10

        lines = ["".join(row) for row in canvas]
        lines.append("".join(ground_chars))
        lines.append("".join(ruler_chars))
        return lines

    @staticmethod
    def _select_flying_pet_token(
        state: PetState,
        vy_mps: float,
        mphase: FlightMotionPhase,
        frame_idx: int,
    ) -> str:
        parity = frame_idx % 2
        if mphase == FlightMotionPhase.STOPPED:
            return "\\(^v^)/" if state.stage != EvolutionStage.EGG else "[o_o]!"
        if mphase == FlightMotionPhase.SLIDING:
            return "~(>o<)" if parity == 0 else ".(>v<)"

        if state.stage == EvolutionStage.EGG:
            return "(o_o)>" if vy_mps >= 0 else "(O_O)v"
        if state.stage == EvolutionStage.CYBER_ROOSTER:
            return "=[<>]>" if parity == 0 else "~[<>]>"

        if vy_mps > 2.5:
            return "/^v^\\" if parity == 0 else "\\^o^/"
        if vy_mps < -2.5:
            return "\\>o</" if parity == 0 else "(>O<)v"
        return ">(^v^)>" if parity == 0 else "~(^v^)>"

    @staticmethod
    def _select_ramp_pet_token(state: PetState, phase: LaunchPhase, frame_idx: int) -> str:
        if state.stage == EvolutionStage.EGG:
            return "[o_o]" if frame_idx % 2 == 0 else "[O_o]"
        if state.stage == EvolutionStage.CYBER_ROOSTER:
            return "[<>]"
        if phase == LaunchPhase.CHARGING:
            return "(>v<)!" if frame_idx % 2 == 0 else "(>o<)*"
        return "(^v^)"

    def _build_phase_panel(self, game: PetLaunchGame, state: PetState, width: int) -> list[str]:
        ph = game.phase
        pstate = game.physics.state

        if ph == LaunchPhase.MENU:
            lines = [
                "MENU PRINCIPAL & LOJA DE MELHORIAS:",
                f"Partidas: {state.total_launches:02d} | Melhor Score: {max(game.best_score, state.best_launch_score):04d} pts",
                f"Perfil: {describe_personality_perk(state.personality)}",
                "LOJA ([U] Prox disponivel ou tecla [7/8/9]):",
            ]
            for spec in LAUNCH_UPGRADES:
                owned = spec.upgrade_id in state.unlocked_upgrades
                tag = "[OK]" if owned else f"{spec.cost_coins:2d}$ "
                lines.append(f" [{spec.slot_key}] {spec.name:<18} {tag} {spec.description}")
            lines.append("")
            lines.append(">> [ENTER / Gesto APPROACH] Iniciar Partida!")
            lines.append(f"STATUS: {game.status_message}")
            return [line[:width] for line in lines]

        if ph == LaunchPhase.SELECT_PET:
            ok, reason = game.check_pet_readiness(state)
            upgs = ", ".join(state.unlocked_upgrades) if state.unlocked_upgrades else "Nenhuma"
            lines = [
                "ETAPA 2 - CONFIRMACAO DO PET:",
                f"Competidor : {state.name} ({state.stage.value} Nv.{state.level:02d})",
                f"Energia    : {state.energy:5.1f}% (custo por voo: -8%)",
                f"Bonus Perf.: {describe_personality_perk(state.personality)}",
                f"Equipado   : {upgs}",
                f"Prontidao  : {'PRONTO PARA DECOLAR!' if ok else reason}",
                "",
                ">> [ENTER / APPROACH] Ir p/ Rampa | [B / RETREAT] Menu",
                f"STATUS: {game.status_message}",
            ]
            return [line[:width] for line in lines]

        if ph in (LaunchPhase.PREP, LaunchPhase.CHARGING):
            bar = _power_bar_ascii(game.charge_norm, width=18)
            pct = game.charge_norm * 100.0
            sweet_txt = "ZONA SWEET-SPOT! (+BONUS)" if game.is_in_sweet_spot() else "Zona ideal: 80% a 95% (*)"
            step_lbl = "ETAPA 3 - PREPARACAO NA RAMPA:" if ph == LaunchPhase.PREP else "ETAPA 4 - CARREGANDO FORCA:"
            lines = [
                step_lbl,
                f"FORCA : {bar} {pct:5.1f}%",
                f"BONUS : {sweet_txt}",
                f"ANGULO: {game.angle_deg:4.1f} deg (ajuste via POT ou [W]/[Z])",
                f"PERFIL: {describe_personality_perk(state.personality)}",
                "",
                ">> [SPACE / HOLD] Carregar Forca",
                ">> [ENTER / APPROACH] Lancar! | [B / RETREAT] Cancelar",
                f"STATUS: {game.status_message}",
            ]
            return [line[:width] for line in lines]

        if ph in (LaunchPhase.LAUNCHING, LaunchPhase.FLIGHT):
            hdr = "ETAPA 5 - DISPARO NA RAMPA!" if ph == LaunchPhase.LAUNCHING else "ETAPAS 6 & 7 - TRAJETORIA BALISTICA:"
            lines = [
                hdr,
                f"Dist: {pstate.x_m:6.2f}m | AltMax: {pstate.max_height_m:5.2f}m",
                f"Alt : {pstate.y_m:6.2f}m | Veloc.: {pstate.speed_mps:5.2f}m/s",
                f"Vx/Vy: {pstate.vx_mps:5.1f} / {pstate.vy_mps:5.1f} m/s",
                f"Quiques: {pstate.bounces:2d}   | Rolo  : {pstate.roll_distance_m:5.2f}m",
                f"Estrelas: *{len(pstate.collected_stars):<2d} | Fase  : {pstate.motion_phase.value}",
                f"Energia: {pstate.specific_mechanical_energy:5.1f} J/kg | T: {pstate.elapsed_s:4.2f}s",
                "",
                f"STATUS: {game.status_message}",
            ]
            return [line[:width] for line in lines]

        if ph == LaunchPhase.RESULT and game.last_result is not None:
            r = game.last_result
            rec_badge = " ** NOVO RECORDE! **" if r.is_new_record else ""
            sweet_tag = "SIM(+15%)" if r.sweet_spot_bonus else "NAO"
            lines = [
                f"ETAPAS 8&9 - PLACAR:{rec_badge}",
                f"Distancia : {r.distance_m:6.2f}m (AltMax: {r.max_height_m:5.2f}m)",
                f"Contato   : {r.bounces:2d} quiques | {r.roll_distance_m:5.2f}m solo",
                f"Extras    : *{r.stars_collected} estrelas | Sweet: {sweet_tag}",
                f"PONTUACAO : {r.score:5d} pts",
                f"PREMIOS   : +{r.coins_reward:2d} Moedas | +{r.xp_reward:2d} XP ({state.name})",
                f"SALDO PET : {state.coins:3d} Moedas | Nv.{state.level:02d} ({state.stage.value})",
                ">> [ENTER/APPROACH] Voltar Menu (Etapa 10)",
                f"STATUS: {game.status_message}",
            ]
            return [line[:width] for line in lines]

        return [
            "RETORNANDO AO MODO MOTIONPET...",
            f"Pet: {state.name} | Moedas: {state.coins} | Recorde: {state.best_launch_distance_m:.1f}m",
            f"STATUS: {game.status_message}",
        ]

    @staticmethod
    def _build_pet_and_lcd_panel(
        state: PetState,
        lcd_frame: LcdFramePayload,
        width: int,
    ) -> list[str]:
        xp_mod = state.xp % 50
        lines = [
            f"PET: {state.name:<8} Nv.{state.level:02d} ({xp_mod:02d}/50XP)",
            f"EST: {state.stage.value:<13} {state.mood.value[:8]:<8}",
            f"EN:{state.energy:3.0f}% HP:{state.happiness:3.0f}% HG:{state.hunger:3.0f}%",
            "ESPELHO LCD FISICO 20x4 (HD44780):",
            "  +--------------------+",
            f"  |{lcd_frame.lines[0]}|",
            f"  |{lcd_frame.lines[1]}|",
            f"  |{lcd_frame.lines[2]}|",
            f"  |{lcd_frame.lines[3]}|",
            "  +--------------------+",
        ]
        return [line[:width] for line in lines]

    @staticmethod
    def _format_sensor_gesture_line(tel: HudTelemetry, game: PetLaunchGame) -> str:
        if tel.sensor is not None:
            d_txt = (
                f"{tel.sensor.distance_cm:5.1f}cm"
                if (tel.sensor.valid_ultrasonic and tel.sensor.distance_cm is not None)
                else "TIMEOUT"
            )
            pot_txt = f"{tel.sensor.pot_norm * 100.0:4.0f}%"
        else:
            d_txt = "  ---cm"
            pot_txt = " ---%"

        if tel.last_gesture is not None:
            g = tel.last_gesture
            g_txt = f"{g.gesture.value}({g.confidence * 100.0:.0f}%/{g.source.value})"
        else:
            g_txt = "NENHUM"

        return (
            f"TELEMETRIA | HC-SR04:{d_txt} POT:{pot_txt} | "
            f"Gesto:{g_txt} | Dedup:{game.input_adapter.duplicate_drops}"
        )
