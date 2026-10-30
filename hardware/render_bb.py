"""Renderizador SVG da protoboard (vista de cima) a partir da netlist canonica.

Nada aqui e desenhado "a mao": posicoes de furos, pernas de resistores e fios saem de Layout.
O desenho e uma ilustracao tecnica estilizada (NAO e uma foto nem um render do Fritzing).
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from . import model
from .model import Layout, parse_hole

K = 20.0                  # pixels por passo de 0,1 pol (2,54 mm)
MM = K / 2.54             # pixels por mm
FONT = "DejaVu Sans, Verdana, Arial, sans-serif"

WIRE_COLORS = {
    "red": "#e0312f", "black": "#2b2b2b", "orange": "#f08a1c", "yellow": "#f2c30f", "green": "#2fa84f",
    "blue": "#2f6fe0", "purple": "#8a47c9", "white": "#f4f4f4", "brown": "#8a5a2b", "grey": "#9a9a9a",
}
BAND_COLORS = {
    "black": "#111", "brown": "#7a4a21", "red": "#d62d20", "orange": "#f08a1c", "yellow": "#f2c30f", "green": "#2fa84f",
    "blue": "#2f6fe0", "violet": "#8a47c9", "grey": "#9a9a9a", "white": "#f4f4f4", "gold": "#d4af37", "silver": "#c0c0c0",
}
NET_BADGE = {"5V": "red", "GND": "black", "3V3": "orange", "TRIG": "yellow", "ECHO_NODE": "green", "IR_DO": "blue",
             "POT_WIPER": "purple", "LCD_RS": "blue", "LCD_E": "green", "LCD_D4": "white", "LCD_D5": "brown",
             "LCD_D6": "orange", "LCD_D7": "purple"}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


@dataclass
class Scene:
    stage: str
    title: str = ""
    subtitle: str = ""
    include_refs: set[str] | None = None        # None = todos do estagio
    exclude_refs: set[str] = field(default_factory=set)
    exclude_wires: set[str] = field(default_factory=set)
    temp_wires: list[dict] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)      # [{"hole": "36F", "text": "..."}]
    show_tags: bool = True                       # etiquetas de furo (ex.: 22A) nas pontas
    bare: bool = False                           # sem titulo/rodape (slides)
    step_of: dict | None = None                  # id -> indice do slide em que o item aparece (modo slides)
    until_of: dict | None = None                 # id -> ultimo slide em que o item ainda aparece
    tag_scale: float = 1.0                       # aumenta etiquetas/rotulos de fio (slides)
    highlight_new: bool = True
    notes: list[str] = field(default_factory=list)


class Frame:
    """Conversao passo/fileira -> pixels. y cresce para CIMA nos passos; o SVG cresce para BAIXO."""

    def __init__(self, x0: float, y0: float):
        self.x0, self.y0 = x0, y0

    def px(self, col: float, y: float) -> tuple[float, float]:
        return self.x0 + (model.col_x(col) - 1) * K, self.y0 - y * K

    def hole(self, hole: str) -> tuple[float, float]:
        c, r = parse_hole(hole)
        return self.x0 + (model.hole_x(c, r) - 1) * K, self.y0 - model.ROW_Y[r] * K


def _y_from_spec(v) -> float:
    return float(model.ROW_Y[v]) if isinstance(v, str) else float(v)


# ----------------------------------------------------------------------------
# Elementos
# ----------------------------------------------------------------------------
def _text(x, y, s, size=8, fill="#222", anchor="middle", weight="normal", rotate=None, extra=""):
    t = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}"{t} {extra}>{esc(s)}</text>')


def draw_breadboard(f: Frame, parts: list[str]) -> None:
    prof = model.active()
    n = prof.n_cols
    cpb = prof.cols_per_board
    rails = prof.rails_in_this_project
    y_hi, y_lo = (16.2, -5.2) if rails else (12.6, -1.7)
    parts.append(f'<g id="breadboard" data-ref="BB1">')
    for b in range(prof.boards):
        c0, c1 = b * cpb + 1, (b + 1) * cpb
        half_gap = prof.board_gap_pitch / 2 + 0.5 if prof.boards > 1 else 0.85
        lpad = 0.85 if b == 0 else half_gap
        rpad = 0.85 if b == prof.boards - 1 else half_gap
        x_left = f.px(c0, 0)[0] - lpad * K
        x_right = f.px(c1, 0)[0] + rpad * K
        y_top = f.px(c0, y_hi)[1]
        y_bot = f.px(c0, y_lo)[1]
        parts.append(f'<rect x="{x_left:.1f}" y="{y_top:.1f}" width="{x_right - x_left:.1f}" height="{y_bot - y_top:.1f}" rx="6" '
                     f'fill="#e8e6df" stroke="#b9b6aa" stroke-width="1.5"/>')
        # canal central
        cy0 = f.px(c0, 5.9)[1]
        cy1 = f.px(c0, 5.1)[1]
        parts.append(f'<rect x="{x_left + 4:.1f}" y="{cy0:.1f}" width="{x_right - x_left - 8:.1f}" height="{cy1 - cy0:.1f}" fill="#cfccc2"/>')
        if prof.boards > 1:
            parts.append(_text(x_left + 3, y_top - 4, f"P{b + 1}", 12, "#5a4a00", anchor="start", weight="bold"))
            if b > 0:
                parts.append(_text((x_left + x_right) / 2, (cy0 + cy1) / 2 + 3, f"PROTOBOARD P{b + 1}  ·  furos escritos P{b + 1}:coluna+fileira (ex.: P{b + 1}:12E)",
                                   7.6, "#6a6658", weight="bold"))
        if rails:
            ly = prof.rail_lines_y or {"red_top": 13.3, "blue_top": 15.6, "blue_bottom": -2.4, "red_bottom": -4.7}
            for key, col in (("red_top", "#d11a1a"), ("blue_top", "#1d4ed8"), ("blue_bottom", "#1d4ed8"), ("red_bottom", "#d11a1a")):
                a = f.px(c0 - 0.6, ly[key])
                bb = f.px(c1 + 0.6, ly[key])
                parts.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{bb[0]:.1f}" y2="{bb[1]:.1f}" stroke="{col}" stroke-width="1.6"/>')
                sgn = "+" if key.startswith("red") else "−"
                for xx in (c0 - 1.05, c1 + 1.05):
                    tx = f.px(c0, 0)[0] + (xx - c0) * K
                    parts.append(_text(tx, a[1] + 4, sgn, 11, col, weight="bold"))
        for row in "ABCDEFGHIJ":
            for cx in (c0 - 0.9, c1 + 0.9):
                x, y = f.px(c0, model.ROW_Y[row])
                x = f.px(c0, 0)[0] + (cx - c0) * K
                parts.append(_text(x, y + 3, row, 7.4, "#555", weight="bold"))
    # furos
    for col in range(1, n + 1):
        for row in "ABCDEFGHIJ":
            x, y = f.px(col, model.ROW_Y[row])
            parts.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" rx="1.2" fill="#3b3b3b"/>')
    if rails:
        for b in range(prof.boards):
            for row in "WXYZ":
                for rc in prof.rail_cols:
                    x, y = f.hole(model.make_hole(b * cpb + rc, row))
                    parts.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" rx="1.2" fill="#3b3b3b"/>')
    # numeros de coluna impressos em cada placa (de 1 em 1)
    for col in range(1, n + 1):
        _, local = model.board_of(col)
        x, yj = f.px(col, 11.95)
        _, ya = f.px(col, -0.95)
        size = 6.8 if local % 5 else 8.2
        weight = "normal" if local % 5 else "bold"
        parts.append(_text(x, yj, local, size, "#555", weight=weight))
        parts.append(_text(x, ya + 3, local, size, "#555", weight=weight))
    parts.append("</g>")


def draw_esp32(f: Frame, lay: Layout, badges: dict[str, str], parts: list[str], new: bool, extra: str = "", badge_steps: dict | None = None) -> None:
    esp = lay.esp32()
    pl = esp["placement"]
    col0 = pl["col0"]
    n = lay.board.n
    prof = lay.board.data
    length_p = prof["pcb_mm"][0] / 2.54
    width_p = prof["pcb_mm"][1] / 2.54
    first = col0 - (length_p - (n - 1)) / 2.0
    # a USB fica a esquerda: PCB deslocada 0,25 passo para a esquerda (conector sai ~1 mm)
    x_left, _ = f.px(first, 0)
    x_right, _ = f.px(first + length_p, 0)
    ymid = (model.ROW_Y["B"] + model.ROW_Y["I"]) / 2.0
    _, y_top = f.px(0, ymid + width_p / 2)
    _, y_bot = f.px(0, ymid - width_p / 2)
    parts.append(f'<g id="U1" class="part{" new" if new else ""}" data-ref="U1"{extra}>')
    parts.append(f'<rect x="{x_left:.1f}" y="{y_top:.1f}" width="{x_right - x_left:.1f}" height="{y_bot - y_top:.1f}" rx="4" '
                 f'fill="#1c2733" stroke="#0d141b" stroke-width="2"/>')
    # modulo ESP-WROOM-32 (lata prateada) + antena
    mod_len = 25.5 / 2.54
    mod_w = 18.0 / 2.54
    mx0, _ = f.px(first + length_p - mod_len - 0.15, 0)
    mx1, _ = f.px(first + length_p - 0.15, 0)
    _, my0 = f.px(0, ymid + mod_w / 2)
    _, my1 = f.px(0, ymid - mod_w / 2)
    ant = 6.0 / 2.54
    ax0, _ = f.px(first + length_p - 0.15 - ant, 0)
    parts.append(f'<rect x="{mx0:.1f}" y="{my0:.1f}" width="{ax0 - mx0:.1f}" height="{my1 - my0:.1f}" rx="2" fill="#b8bdc4" stroke="#7d848c"/>')
    parts.append(f'<rect x="{ax0:.1f}" y="{my0:.1f}" width="{mx1 - ax0:.1f}" height="{my1 - my0:.1f}" fill="#e9e4d2" stroke="#7d848c"/>')
    for i in range(5):
        xx = ax0 + 4 + i * ((mx1 - ax0 - 8) / 4)
        parts.append(f'<path d="M{xx:.1f},{my0 + 4:.1f} v{(my1 - my0 - 8) * 0.55:.1f} h4 v-{(my1 - my0 - 8) * 0.55:.1f}" fill="none" stroke="#a89f7a" stroke-width="1.2"/>')
    parts.append(_text((mx0 + ax0) / 2, (my0 + my1) / 2 - 2, "ESP-WROOM-32", 8.5, "#2a2f35", weight="bold"))
    parts.append(_text((mx0 + ax0) / 2, (my0 + my1) / 2 + 9, "ESP32", 7.5, "#2a2f35"))
    # conector USB-C (esquerda)
    uy0 = (y_top + y_bot) / 2 - 1.8 * K / 2.0
    parts.append(f'<rect x="{x_left - 3:.1f}" y="{uy0 - 4:.1f}" width="{2.6 * K / 2.2:.1f}" height="{3.6 * K / 2.0 + 8:.1f}" rx="3" fill="#c9ccd1" stroke="#7d848c" stroke-width="1.2"/>')
    parts.append(_text(x_left + 12, (y_top + y_bot) / 2 + 3, "USB-C", 7.5, "#2a2f35", weight="bold", rotate=-90))
    # botoes EN/BOOT e LEDs
    for off, name in ((2.2, "EN"), (4.2, "BOOT")):
        bx, by = f.px(first + off, ymid)
        parts.append(f'<rect x="{bx - 5:.1f}" y="{by - 10:.1f}" width="10" height="20" rx="2" fill="#555" stroke="#222"/>')
    # pinos e rotulos
    for p in lay.board.pins:
        hole = lay.esp32_pin_hole(p)
        x, y = f.hole(hole)
        col, row = parse_hole(hole)
        parts.append(f'<rect x="{x - 4.5:.1f}" y="{y - 4.5:.1f}" width="9" height="9" fill="#d9b24a" stroke="#8a6d1b" stroke-width="0.8"/>')
        inward = 1 if row == "I" else -1       # em pixels SVG: fileira I (topo) -> rotulo para baixo; B -> para cima
        ly = y + inward * 9
        name = lay.board.ref_name(p).split("@")[0]
        key = f"U1.{lay.board.ref_name(p)}"
        # rotulo de serigrafia SEMPRE desenhado (o selo colorido, quando existe, cobre-o por cima)
        col_t = "#8fa5ba" if p.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved") else "#c9d6e2"
        if p.kind in ("flash_forbidden", "strapping_forbidden"):
            col_t = "#ff8d8d"
        parts.append(_text(x, ly + (8 if inward > 0 else -1), name, 7.2, col_t))
        if key in badges:
            colr = WIRE_COLORS[badges[key]]
            tcol = "#111" if badges[key] in ("yellow", "white", "orange") else "#fff"
            w = max(26, 6.4 * len(name) + 8)
            h = 13
            by = ly if inward > 0 else ly - h
            bst = f' data-gstep="{badge_steps[key]}"' if badge_steps and key in badge_steps else ""
            parts.append(f'<g class="badge" data-pin="{esc(key)}"{bst}><rect x="{x - w / 2:.1f}" y="{by:.1f}" width="{w:.1f}" height="{h}" rx="3" '
                         f'fill="{colr}" stroke="#fff" stroke-width="1"/>'
                         + _text(x, by + 9.6, name, 8, tcol, weight="bold") + "</g>")
    # legenda da placa
    cxl, cyl = f.px(first + 6.2, ymid + 0.0)
    parts.append(_text(cxl, cyl + 3, "ESP32 DevKit 38 pinos", 9, "#8aa0b4", weight="bold"))
    parts.append(_text(cxl, cyl + 15, "(ilustracao; confira a sua placa)", 7, "#6f8497"))
    parts.append("</g>")


def _hole_pin_marker(parts, x, y, colr="#d9b24a"):
    parts.append(f'<rect x="{x - 3.6:.1f}" y="{y - 3.6:.1f}" width="7.2" height="7.2" fill="{colr}" stroke="#7a5f12" stroke-width="0.8"/>')


def offboard_geometry(f: Frame, lay: Layout, comp: dict) -> dict:
    """Corpo e pinos (px) de um modulo FORA da protoboard, ligado por jumpers femea-macho."""
    mod = lay.modules["modules"][comp["type"]]
    ob = comp["offboard"]
    cx, cy = f.px(ob["anchor"][0], ob["anchor"][1])
    w, h = mod["body_mm"][0] * MM, mod["body_mm"][1] * MM
    if comp["type"] == "tcrt5000_module":
        w, h = max(w, 4 * K + 10), h
    names = mod["pin_order"]
    top = cy - h / 2
    above = ob["anchor"][1] > 6                     # modulo desenhado ACIMA da placa: conector na borda de baixo
    py = (top + h) if above else (top - 10)
    pins = {nm: (cx + (i - (len(names) - 1) / 2) * K, py) for i, nm in enumerate(names)}
    return {"cx": cx, "cy": cy, "w": w, "h": h, "top": top, "pins": pins, "names": names, "above": above}


def lead_points(f: Frame, lay: Layout, comp: dict, geo: dict | None = None) -> dict[str, list[tuple[float, float]]]:
    """Caminho de cada jumper femea-macho: pino do modulo -> nivel abaixo da placa -> furo."""
    geo = geo or offboard_geometry(f, lay, comp)
    out = {}
    pins = [p for p in geo["names"] if p in comp["pins"]]
    order = sorted(pins, key=lambda p: abs(f.hole(comp["pins"][p])[0] - geo["pins"][p][0]))
    above = geo.get("above")
    base = f.px(0, 16.9 if above else -5.9)[1]
    for k, p in enumerate(order):
        x0, y0 = geo["pins"][p]
        y0 = y0 + (10 if above else 0)
        hx, hy = f.hole(comp["pins"][p])
        lvl = base + (-1 if above else 1) * k * 0.45 * K
        out[p] = [(x0, y0), (x0, lvl), (hx, lvl), (hx, hy)]
    return out


def draw_offboard_module(f: Frame, lay: Layout, comp: dict, parts: list[str], new: bool, extra: str = "") -> None:
    t, ref = comp["type"], comp["ref"]
    geo = offboard_geometry(f, lay, comp)
    cx, w, h, top = geo["cx"], geo["w"], geo["h"], geo["top"]
    parts.append(f'<g id="{ref}" class="part{" new" if new else ""}" data-ref="{ref}"{extra}>')
    if t == "hc_sr04":
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="#1e6fb5" fill-opacity="0.95" stroke="#0e3f6b" stroke-width="1.5"/>')
        for kk in (0.25, 0.75):
            tx, ty, r = cx - w / 2 + w * kk, top + h * 0.55, 8.0 * MM
            parts.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r:.1f}" fill="#c4c9cf" stroke="#6b737b" stroke-width="2"/>'
                         f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r * 0.72:.1f}" fill="#8a9097" stroke="#555"/>'
                         f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r * 0.28:.1f}" fill="#3d4247"/>')
        parts.append(_text(cx, top + h * 0.55 + 3, "HC-SR04", 9, "#eaf4ff", weight="bold"))
    else:
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="#243a8a" fill-opacity="0.95" stroke="#101c4a" stroke-width="1.5"/>')
        parts.append(f'<rect x="{cx - w * 0.38:.1f}" y="{top + h * 0.62:.1f}" width="{w * 0.30:.1f}" height="{h * 0.3:.1f}" fill="#101010" stroke="#555"/>')
        parts.append(f'<rect x="{cx + w * 0.08:.1f}" y="{top + h * 0.62:.1f}" width="{w * 0.24:.1f}" height="{h * 0.3:.1f}" fill="#2b66d9" stroke="#0a2a7a"/>')
        parts.append(_text(cx, top + h * 0.45, "TCRT5000", 8, "#cfe0ff", weight="bold"))
    above = geo.get("above")
    parts.append(_text(cx, (top - 6) if above else (top + h + 12), "fora da protoboard · jumpers fêmea–macho", 7.5, "#555"))
    # conector (pinos) na borda voltada para a placa, com o nome
    for nm in geo["names"]:
        x, y = geo["pins"][nm]
        parts.append(f'<rect x="{x - 4:.1f}" y="{y:.1f}" width="8" height="10" fill="#222" stroke="#000" stroke-width="0.6"/>')
        parts.append(_text(x, (top + h - 3) if above else (top + 9), nm, 6.6, "#fff", weight="bold"))
    # jumpers
    colors = comp["offboard"].get("leads", {})
    for nm, pts in lead_points(f, lay, comp, geo).items():
        colr = WIRE_COLORS.get(colors.get(nm, "grey"), "#999")
        d = _rounded_polyline(pts)
        parts.append(f'<g class="wire lead" data-id="{ref}.{nm}">')
        parts.append(f'<path d="{d}" fill="none" stroke="#000" stroke-opacity="0.55" stroke-width="7.4" stroke-linecap="round" stroke-linejoin="round"/>')
        parts.append(f'<path class="core" d="{d}" fill="none" stroke="{colr}" stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round"/>')
        hx, hy = pts[-1]
        parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="4.4" fill="{colr}" stroke="#000" stroke-width="1.2"/>')
        tag = model.hole_tag(comp["pins"][nm])
        tx, ty = _place_tag(hx, hy, tag, TAKEN_TAGS, 1.0)
        tw_ = 7.2 * len(tag) + 6
        parts.append(f'<g class="htag"><line x1="{hx:.1f}" y1="{hy:.1f}" x2="{tx + tw_ / 2:.1f}" y2="{ty + 6:.1f}" stroke="#555" stroke-width="0.7"/>'
                     f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw_:.1f}" height="12" rx="3" fill="#fff" fill-opacity="0.96" stroke="#555" stroke-width="0.8"/>'
                     + _text(tx + tw_ / 2, ty + 9, tag, 8.2, "#111", weight="bold") + "</g>")
        parts.append("</g>")
    parts.append("</g>")


def draw_module(f: Frame, lay: Layout, comp: dict, parts: list[str], new: bool, extra: str = "") -> None:
    if comp.get("offboard"):
        return draw_offboard_module(f, lay, comp, parts, new, extra)
    t = comp["type"]
    mod = lay.modules["modules"][t]
    ref = comp["ref"]
    holes = [f.hole(h) for h in comp["pins"].values()]
    xs = [h[0] for h in holes]
    ys = [h[1] for h in holes]
    cx = (min(xs) + max(xs)) / 2
    row = parse_hole(next(iter(comp["pins"].values())))[1]
    up = row in model.UPPER_ROWS      # modulo pendurado para CIMA (fileira J) ou para BAIXO (fileira A)
    wmm, hmm = mod["body_mm"]
    if t == "lcd2004a":
        hmm = min(hmm, 25.4)                          # altura recortada (fora de escala)
    w, h = wmm * MM, hmm * MM
    ybase = ys[0] + (-1 if up else 1) * lift_for(comp) * K   # borda do corpo (modulo "em pe" sobre os pinos)
    top = ybase - h if up else ybase
    if t == "lcd2004a" and mod.get("pin1_from_left_mm") is not None:
        cx = min(xs) - mod["pin1_from_left_mm"] * MM + w / 2       # conector fica a esquerda no modulo real
    parts.append(f'<g id="{ref}" class="part{" new" if new else ""}" data-ref="{ref}"{extra}>')
    if t == "hc_sr04":
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="#1e6fb5" fill-opacity="0.93" stroke="#0e3f6b" stroke-width="1.5"/>')
        for k in (0.25, 0.75):
            tx = cx - w / 2 + w * k
            ty = top + h * 0.47
            r = 8.0 * MM
            parts.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r:.1f}" fill="#c4c9cf" stroke="#6b737b" stroke-width="2"/>'
                         f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r * 0.72:.1f}" fill="#8a9097" stroke="#555"/>'
                         f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r * 0.28:.1f}" fill="#3d4247"/>')
        parts.append(_text(cx, top + h * 0.47 + 3, "HC-SR04", 9, "#eaf4ff", weight="bold"))
    elif t == "tcrt5000_module":
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="#243a8a" fill-opacity="0.93" stroke="#101c4a" stroke-width="1.5"/>')
        parts.append(f'<rect x="{cx - w / 2 + 6:.1f}" y="{top + h * 0.25:.1f}" width="{w * 0.30:.1f}" height="{h * 0.55:.1f}" fill="#101010" stroke="#555"/>')
        parts.append(f'<rect x="{cx + w * 0.12:.1f}" y="{top + h * 0.25:.1f}" width="{w * 0.22:.1f}" height="{h * 0.5:.1f}" fill="#2b66d9" stroke="#0a2a7a"/>')
        parts.append(_text(cx - w * 0.2, top + h * 0.18, "TCRT5000", 7.4, "#cfe0ff", weight="bold"))
    elif t == "potentiometer":
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="#2a63b8" fill-opacity="0.95" stroke="#123a75" stroke-width="1.5"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{top + h / 2:.1f}" r="{min(w, h) * 0.34:.1f}" fill="#d7dbe0" stroke="#6b737b" stroke-width="2"/>'
                     f'<line x1="{cx:.1f}" y1="{top + h / 2:.1f}" x2="{cx + min(w, h) * 0.24:.1f}" y2="{top + h / 2 - min(w, h) * 0.24:.1f}" stroke="#444" stroke-width="3"/>')
        parts.append(_text(cx, top + h * 0.12, "POT", 7.5, "#dfeaff", weight="bold"))
    elif t == "lcd2004a":
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="#0f7a4d" fill-opacity="0.88" stroke="#07452c" stroke-width="2"/>')
        wx, wy = cx - 38 * MM, top + 3 * MM
        wh = max(h - 14 * MM, 8 * MM)
        parts.append(f'<rect x="{wx:.1f}" y="{wy:.1f}" width="{76 * MM:.1f}" height="{wh:.1f}" fill="#1c3b34" fill-opacity="0.95" stroke="#0b2018" stroke-width="2"/>')
        for r in range(4):
            parts.append(f'<rect x="{wx + 5:.1f}" y="{wy + 3 + r * (wh - 6) / 4:.1f}" width="{76 * MM - 10:.1f}" height="{(wh - 6) / 4 - 3:.1f}" fill="#2c5e52" fill-opacity="0.7"/>')
        parts.append(_text(cx, (top + 16) if up else (top + h - 7), "LCD 2004A V1.1 (20x4) - altura recortada", 9, "#d9fbe9", weight="bold"))
    # pinos dourados descendo ate os furos + rotulos
    names = list(comp["pins"].keys())
    for name, (px_, py_) in zip(names, holes):
        parts.append(f'<line x1="{px_:.1f}" y1="{ybase:.1f}" x2="{px_:.1f}" y2="{py_:.1f}" stroke="#d9b24a" stroke-width="4" stroke-opacity="0.95"/>')
        _hole_pin_marker(parts, px_, py_)
    fs = 7.0
    for name, (px_, py_) in zip(names, holes):
        # nome do pino escrito na borda do corpo, na vertical (cabe no passo de 2,54 mm)
        tx = px_ + 2.6
        ty = ybase + (-4 if up else 4)
        anchor = "start" if up else "end"
        parts.append(_text(tx, ty, name, fs, "#fff", anchor=anchor, weight="bold", rotate=-90))
    parts.append("</g>")


def lift_for(comp: dict) -> float:
    """Distancia (em passos) entre a fileira de furos e a borda do corpo do modulo."""
    return {"lcd2004a": 9.0, "hc_sr04": 4.6 if model.active().boards > 1 else 3.4, "tcrt5000_module": 3.8, "potentiometer": 3.8}.get(comp["type"], 3.0)


def _band_rects(bands, x0, x1, y, h):
    out = []
    n = len(bands)
    span = x1 - x0
    for i, b in enumerate(bands):
        pos = x0 + span * (0.18 + 0.15 * i) if i < 3 else x0 + span * 0.82
        out.append(f'<rect x="{pos - 1.6:.1f}" y="{y:.1f}" width="3.2" height="{h:.1f}" fill="{BAND_COLORS[b]}" stroke="#00000033" stroke-width="0.4"/>')
    _ = n
    return out


def draw_resistor(f: Frame, lay: Layout, comp: dict, parts: list[str], new: bool, extra: str = "") -> None:
    (xa, ya), (xb, yb) = f.hole(comp["legs"][0]), f.hole(comp["legs"][1])
    bands = model.resistor_bands(comp["ohms"], comp["tolerance"], lay.modules["resistor_color_code"])
    dx, dy = xb - xa, yb - ya
    dist = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / dist, dy / dist
    body = min(2.5 * K, dist - 0.8 * K)
    mx, my = (xa + xb) / 2, (ya + yb) / 2
    bx0, by0 = mx - ux * body / 2, my - uy * body / 2
    bx1, by1 = mx + ux * body / 2, my + uy * body / 2
    ang = 0
    import math
    ang = math.degrees(math.atan2(dy, dx))
    ref = comp["ref"]
    parts.append(f'<g id="{ref}" class="part res{" new" if new else ""}" data-ref="{ref}"{extra}>')
    parts.append(f'<path d="M{xa:.1f},{ya:.1f} L{bx0:.1f},{by0:.1f} M{bx1:.1f},{by1:.1f} L{xb:.1f},{yb:.1f}" stroke="#9aa0a6" stroke-width="3.2" stroke-linecap="round" fill="none"/>')
    parts.append(f'<g transform="translate({mx:.1f} {my:.1f}) rotate({ang:.2f})">')
    parts.append(f'<rect x="{-body / 2:.1f}" y="-6.2" width="{body:.1f}" height="12.4" rx="6" fill="#d9c28e" stroke="#8a7440" stroke-width="1.2"/>')
    parts.extend(_band_rects(bands, -body / 2, body / 2, -6.2, 12.4))
    parts.append("</g>")
    for hx, hy in ((xa, ya), (xb, yb)):
        parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="3.4" fill="#cfd3d8" stroke="#555" stroke-width="0.8"/>')
    label = f'{ref} {model.fmt_ohms(comp["ohms"])}'
    pos = comp.get("label_pos")
    if pos == "right":                       # a direita da perna mais a direita (fora do corpo, longe de outros resistores)
        ex, ey = (xa, ya) if xa >= xb else (xb, yb)
        lx0, ly0 = ex + 9.0, ey - 6.5
    else:
        lx0, ly0 = mx - 30, (my - 22 if pos == "above" else my + 8)
    TAKEN_TAGS.append((lx0, ly0, lx0 + 60, ly0 + 13))
    parts.append(f'<g class="reslabel"><rect x="{lx0:.1f}" y="{ly0:.1f}" width="60" height="13" rx="3" fill="#fffbe6" stroke="#8a7440" stroke-width="0.8"/>'
                 + _text(lx0 + 30, ly0 + 9.6, label, 8.4, "#3a2f10", weight="bold") + "</g>")
    parts.append("</g>")


def _rounded_polyline(pts: list[tuple[float, float]], r: float = 7.0) -> str:
    if len(pts) == 2:
        return f"M{pts[0][0]:.1f},{pts[0][1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f}"
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    import math
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1) or 1, math.hypot(*v2) or 1
        rr = min(r, l1 / 2, l2 / 2)
        a = (p1[0] + v1[0] / l1 * rr, p1[1] + v1[1] / l1 * rr)
        b = (p1[0] + v2[0] / l2 * rr, p1[1] + v2[1] / l2 * rr)
        d.append(f"L{a[0]:.1f},{a[1]:.1f} Q{p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}")
    d.append(f"L{pts[-1][0]:.1f},{pts[-1][1]:.1f}")
    return " ".join(d)


def wire_points(f: Frame, w: dict) -> list[tuple[float, float]]:
    pts = [f.hole(w["from"])]
    for v in w.get("via", []):
        pts.append(f.px(float(v[0]), _y_from_spec(v[1])))
    pts.append(f.hole(w["to"]))
    return pts


def _place_tag(x: float, y: float, text: str, taken: list[tuple[float, float, float, float]], sc: float = 1.0) -> tuple[float, float]:
    """Escolhe o canto (4 candidatos x 2 distancias) que nao colide com etiquetas ja posicionadas."""
    wtag, htag = (7.2 * len(text) + 6) * sc, 12.0 * sc
    cands = []
    for dist in (9.0 * sc, 17.0 * sc, 26.0 * sc):
        for dx, dy in ((1, -1), (-1, -1), (1, 1), (-1, 1)):
            cx = x + dx * dist - (wtag if dx < 0 else 0)
            cy = y + dy * dist - (htag if dy < 0 else 0)
            cands.append((cx, cy))
    for cx, cy in cands:
        rect = (cx, cy, cx + wtag, cy + htag)
        if all(rect[2] < t[0] or rect[0] > t[2] or rect[3] < t[1] or rect[1] > t[3] for t in taken):
            taken.append(rect)
            return cx, cy
    cx, cy = cands[0]
    taken.append((cx, cy, cx + wtag, cy + htag))
    return cx, cy


TAKEN_TAGS: list[tuple[float, float, float, float]] = []


def draw_wire(f: Frame, w: dict, parts: list[str], new: bool, show_tags: bool, temp: bool = False, extra: str = "", sc: float = 1.0) -> None:
    pts = wire_points(f, w)
    colr = WIRE_COLORS.get(w.get("color", "grey"), "#999")
    d = _rounded_polyline(pts)
    cls = "wire" + (" new" if new else "") + (" temp" if temp else "")
    dash = ' stroke-dasharray="7 5"' if temp else ""
    parts.append(f'<g id="{w["id"]}" class="{cls}" data-id="{w["id"]}" data-net="{esc(w.get("net", ""))}"{extra}>')
    parts.append(f'<path d="{d}" fill="none" stroke="#000" stroke-opacity="0.55" stroke-width="7.4" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
    parts.append(f'<path class="core" d="{d}" fill="none" stroke="{colr}" stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
    for (x, y) in (pts[0], pts[-1]):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="{colr}" stroke="#000" stroke-width="1.2"/>')
    # etiqueta do fio no meio do maior segmento
    best = max(range(len(pts) - 1), key=lambda i: (pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2)
    lx = (pts[best][0] + pts[best + 1][0]) / 2
    ly = (pts[best][1] + pts[best + 1][1]) / 2
    label = w["id"]
    parts.append(f'<g class="wlabel"><rect x="{lx - 11 * sc:.1f}" y="{ly - 7 * sc:.1f}" width="{22 * sc:.1f}" height="{14 * sc:.1f}" rx="4" fill="#fff" stroke="{colr if colr != "#f4f4f4" else "#888"}" stroke-width="1.6"/>'
                 + _text(lx, ly + 3.6 * sc, label, 8.6 * sc, "#111", weight="bold") + "</g>")
    if show_tags:
        for (x, y), hole in ((pts[0], w["from"]), (pts[-1], w["to"])):
            hole = model.hole_tag(hole)
            tx, ty = _place_tag(x, y, hole, TAKEN_TAGS, sc)
            tw_ = (7.2 * len(hole) + 6) * sc
            parts.append(f'<g class="htag"><line x1="{x:.1f}" y1="{y:.1f}" x2="{tx + tw_ / 2:.1f}" y2="{ty + 6 * sc:.1f}" stroke="#555" stroke-width="0.7"/>'
                         f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw_:.1f}" height="{12 * sc:.1f}" rx="3" fill="#fff" fill-opacity="0.96" stroke="#555" stroke-width="0.8"/>'
                         + _text(tx + tw_ / 2, ty + 9 * sc, hole, 8.2 * sc, "#111", weight="bold") + "</g>")
    parts.append("</g>")


def _bounds_pitch(lay: Layout, scene: Scene) -> tuple[float, float, float, float]:
    prof = model.active()
    xs, ys = [0.0, prof.n_cols + 1.0], ([-5.6, 16.6] if prof.rails_in_this_project else [-2.9 if prof.boards > 1 else -2.2, 13.2])
    for comp in lay.comps(scene.stage):
        t = comp["type"]
        if t in ("breadboard", "esp32", "resistor"):
            continue
        if comp["ref"] in scene.exclude_refs or (scene.include_refs is not None and comp["ref"] not in scene.include_refs):
            continue
        mod = lay.modules["modules"][t]
        if comp.get("offboard"):
            ax, ay = comp["offboard"]["anchor"]
            xs += [ax - mod["body_mm"][0] / 2.54 / 2 - 0.5, ax + mod["body_mm"][0] / 2.54 / 2 + 0.5]
            ys += [ay - mod["body_mm"][1] / 2.54 / 2 - 1.2, ay + mod["body_mm"][1] / 2.54 / 2 + 1.2]
            continue
        cols = [parse_hole(h)[0] for h in comp["pins"].values()]
        row = parse_hole(next(iter(comp["pins"].values())))[1]
        wp = mod["body_mm"][0] / 2.54
        hp = (min(mod["body_mm"][1], 25.4) if t == "lcd2004a" else mod["body_mm"][1]) / 2.54
        c = (min(cols) + max(cols)) / 2
        if t == "lcd2004a" and mod.get("pin1_from_left_mm") is not None:
            c = min(cols) - mod["pin1_from_left_mm"] / 2.54 + wp / 2
        xs += [c - wp / 2, c + wp / 2]
        if row in model.UPPER_ROWS:
            ys.append(11 + lift_for(comp) + hp)
        else:
            ys.append(-lift_for(comp) - hp)
    for mk in scene.markers:
        col = parse_hole(mk["hole"])[0]
        xs.append(col + (50 + 6.6 * len(mk["text"])) / K)
        ys.append(model.ROW_Y[parse_hole(mk["hole"])[1]] + (170 / K if mk.get("dir") == "up" else -4.5))
    for w in lay.wires_at(scene.stage):
        if w["id"] in scene.exclude_wires or (scene.include_refs is not None and w["id"] not in scene.include_refs):
            continue
        for v in w.get("via", []):
            xs.append(float(v[0]))
            ys.append(_y_from_spec(v[1]))
    xs = [model.col_x(x) for x in xs]
    return min(xs) - 2.5, max(xs) + 2.5, min(ys) - 2.5, max(ys) + 3.5


CSS = """
.part.new > rect:first-of-type, .part.new > circle:first-of-type {}
.wire .wlabel, .wire .htag { pointer-events: none; }
.dim { opacity: 0.18; }
.hl .core { stroke-width: 6.4; }
.hl path:first-child { stroke: #ff00aa; stroke-opacity: 0.95; stroke-width: 11; }
.part.hl rect:first-of-type { stroke: #ff00aa; stroke-width: 3; }
.htag { display: var(--tags, inline); }
"""


def render_scene(lay: Layout, scene: Scene) -> tuple[str, dict]:
    """Retorna (svg, meta). meta traz largura/altura e o mapa ref->furos para o guia HTML."""
    TAKEN_TAGS.clear()
    xmin, xmax, ymin, ymax = _bounds_pitch(lay, scene)
    f = Frame(x0=(1 - xmin) * K, y0=(ymax) * K)
    width = (xmax - xmin) * K
    height = (ymax - ymin) * K
    comps = [c for c in lay.comps(scene.stage)]
    if scene.include_refs is not None:
        comps = [c for c in comps if c["ref"] in scene.include_refs]
    comps = [c for c in comps if c["ref"] not in scene.exclude_refs]
    wires = [w for w in lay.wires_at(scene.stage) if w["id"] not in scene.exclude_wires]
    if scene.include_refs is not None:
        wires = [w for w in wires if w["id"] in scene.include_refs]
    # selo de "novo neste estagio"
    new = (lambda it: scene.highlight_new and it["stage"] == scene.stage and scene.stage not in ("A",))

    # etiquetas dos pinos da ESP32 em uso: o pino aparece se um fio chega na coluna dele
    badges: dict[str, str] = {}
    occ_cols: dict[tuple[int, str], str] = {}
    for w in wires:
        for h in (w["from"], w["to"]):
            c, r = parse_hole(h)
            grp = model.hole_group(h)
            occ_cols[grp] = w["color"]
    for p in lay.board.pins:
        grp = model.hole_group(lay.esp32_pin_hole(p))
        if grp in occ_cols:
            badges[f"U1.{lay.board.ref_name(p)}"] = occ_cols[grp]

    def gx(ident: str) -> str:
        """atributos data-gstep/data-until (modo slides)."""
        if not scene.step_of or ident not in scene.step_of:
            return ""
        a = f' data-gstep="{scene.step_of[ident]}"'
        if scene.until_of and ident in scene.until_of:
            a += f' data-until="{scene.until_of[ident]}"'
        return a

    # selos dos badges da ESP32: aparecem quando o primeiro fio chega na coluna do pino
    badge_steps: dict[str, int] = {}
    if scene.step_of:
        for w in wires:
            for h in (w["from"], w["to"]):
                grp = model.hole_group(h)
                for p in lay.board.pins:
                    if model.hole_group(lay.esp32_pin_hole(p)) == grp:
                        key = f"U1.{lay.board.ref_name(p)}"
                        st_ = scene.step_of.get(w["id"])
                        if st_ is not None:
                            badge_steps[key] = min(badge_steps.get(key, st_), st_)

    y_off = 0 if scene.bare else 56
    extra_h = 0 if scene.bare else 66
    out: list[str] = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height + extra_h:.0f}" width="{width:.0f}" height="{height + extra_h:.0f}" '
               f'data-stage="{scene.stage}" font-family="{FONT}" role="img" aria-label="{esc(scene.title)}">')
    out.append(f"<style>{CSS}</style>")
    out.append(f'<rect x="-3000" y="-3000" width="{width + 6000:.0f}" height="{height + extra_h + 6000:.0f}" fill="#f7f5ee"/>')
    if not scene.bare:
        out.append(_text(14, 22, scene.title or f"MotionPet - Estagio {scene.stage}", 17, "#17212b", anchor="start", weight="bold"))
        if scene.subtitle:
            out.append(_text(14, 40, scene.subtitle, 10.5, "#4a5560", anchor="start"))
    out.append(f'<g transform="translate(0 {y_off})">')
    body: list[str] = []
    draw_breadboard(f, body)
    # zonas de dominio de tensao (Estagio B+): ECHO 5 V x no <= 3,3 V
    if "R1" in {c["ref"] for c in comps}:
        body.append(f'<g class="zone"{gx("R1")}>')
        ze = []
        r1 = lay.components["R1"]

        def zone(hole: str, fill: str, stroke: str) -> tuple[float, float]:
            col, row = parse_hole(hole)
            rows = ("F", "J") if row in model.UPPER_ROWS else ("A", "E")
            xa, ya = f.hole(model.make_hole(col, rows[0]))
            xb, yb = f.hole(model.make_hole(col, rows[1]))
            y0, y1 = min(ya, yb), max(ya, yb)
            body.append(f'<rect x="{xa - 12:.1f}" y="{y0 - 12:.1f}" width="24" height="{y1 - y0 + 24:.1f}" rx="6" fill="{fill}" fill-opacity="0.16" stroke="{stroke}" stroke-width="1.2" stroke-dasharray="4 3"/>')
            return xa, y0
        zx, _ = zone(r1["legs"][0], "#ff5a5a", "#e03b3b")
        nx, _ = zone(r1["legs"][1], "#3ecf6b", "#1f9d46")
        cy_ch = f.px(0, 5.5)[1]
        top = [c for c in comps if c.get("role") == "divider_top"]
        bot = [c for c in comps if str(c.get("role", "")).startswith("divider_bottom")]
        vnode = model.divider_vout(5.0, sum(c["ohms"] for c in top), sum(c["ohms"] for c in bot)) if top and bot else 3.0
        body.append(_text(zx, cy_ch - 2, "ECHO", 8.6, "#b02020", weight="bold"))
        body.append(_text(zx, cy_ch + 8, "5 V", 8.6, "#b02020", weight="bold"))
        body.append(_text(nx, cy_ch - 2, "NÓ", 8.6, "#157a35", weight="bold"))
        body.append(_text(nx, cy_ch + 8, f"≈{vnode:.1f} V".replace(".", ","), 8.6, "#157a35", weight="bold"))
        # junção entre resistores do ramo de baixo (tira compartilhada por pernas de dois resistores; trilhos nao contam)
        legs_grp: dict = {}
        for c in bot:
            for h_ in c["legs"]:
                if parse_hole(h_)[1] not in model.RAIL_ROWS:
                    legs_grp.setdefault(model.hole_group(h_), []).append((c["ref"], h_))
        for grp, items in sorted(legs_grp.items(), key=lambda kv: str(kv[0])):
            if len(items) == 2:
                mx0, _ = zone(items[0][1], "#e8c34a", "#b08a10")
                body.append(_text(mx0, cy_ch - 2, "MEIO", 8.6, "#7a5a00", weight="bold"))
                body.append(_text(mx0, cy_ch + 8, "/".join(r for r, _ in items), 8.0, "#7a5a00", weight="bold"))
        body.append("</g>")
        _ = ze
    for comp in comps:
        t = comp["type"]
        if t == "esp32":
            draw_esp32(f, lay, badges, body, new(comp), gx(comp["ref"]), badge_steps)
        elif t in ("hc_sr04", "tcrt5000_module", "potentiometer", "lcd2004a"):
            draw_module(f, lay, comp, body, new(comp), gx(comp["ref"]))
    for comp in comps:
        if comp["type"] == "resistor":
            draw_resistor(f, lay, comp, body, new(comp), gx(comp["ref"]))
    for w in wires:
        draw_wire(f, w, body, new(w), scene.show_tags, extra=gx(w["id"]), sc=scene.tag_scale)
    for tw in scene.temp_wires:
        tw = dict(tw)
        tw.setdefault("via", [])
        tw.setdefault("color", "grey")
        draw_wire(f, tw, body, True, scene.show_tags, temp=True, extra=gx(tw["id"]), sc=scene.tag_scale)
    for mk in scene.markers:
        mx_, my_ = f.hole(mk["hole"])
        tw_ = 6.6 * len(mk["text"]) + 14
        up = mk.get("dir") == "up"                      # chamada para cima (livra os resistores quando o furo esta na fileira J)
        dy_line, dy_box, dy_txt = (-11, -164, -150) if up else (11, 44, 58)
        body.append(f'<g class="marker"{gx(mk.get("id", ""))}><circle cx="{mx_:.1f}" cy="{my_:.1f}" r="11" fill="none" stroke="#e0007a" stroke-width="3"/>'
                    f'<line x1="{mx_:.1f}" y1="{my_ + dy_line:.1f}" x2="{mx_ + 24:.1f}" y2="{my_ + (-144 if up else 44):.1f}" stroke="#e0007a" stroke-width="2"/>'
                    f'<rect x="{mx_ + 24:.1f}" y="{my_ + dy_box:.1f}" width="{tw_:.1f}" height="20" rx="5" fill="#fff0f8" stroke="#e0007a" stroke-width="1.6"/>'
                    + _text(mx_ + 24 + tw_ / 2, my_ + dy_txt, mk["text"], 10.5, "#8a004c", weight="bold") + "</g>")
    out.extend(body)
    out.append("</g>")
    # rodape
    foot_y = height + 56 + 4
    foot = ["Fonte: hardware/netlist/motionpet.netlist.json  |  Status: PENDING_PHYSICAL_VALIDATION  |  "
            "Ilustracao tecnica gerada da netlist (nao e foto; confira SEMPRE a serigrafia da sua placa)."]
    if not scene.bare:
        out.append(_text(14, foot_y + 6, foot[0], 8.6, "#6b7682", anchor="start"))
    out.append("</svg>")
    meta = {
        "width": width, "height": height + extra_h, "y_off": y_off,
        "frame_x0": f.x0, "frame_y0": f.y0,
        "holes": {w["id"]: {"from": w["from"], "to": w["to"]} for w in wires},
    }
    return "\n".join(out), meta


# ----------------------------------------------------------------------------
# Caixas delimitadoras (px do SVG) para dar zoom em cada slide
# ----------------------------------------------------------------------------
def item_bbox(lay: Layout, meta: dict, ident: str, scene: Scene) -> tuple[float, float, float, float] | None:
    f = Frame(meta["frame_x0"], meta["frame_y0"])
    yo = meta.get("y_off", 0)
    pts: list[tuple[float, float]] = []
    pad = 14.0
    if ident == "BB1":
        prof = model.active()
        a = f.px(0.15, 16.2 if prof.rails_in_this_project else 12.6)
        b = f.px(prof.n_cols + 0.85, -5.2 if prof.rails_in_this_project else -1.7)
        pts = [a, b]
        pad = 0
    elif ident in lay.wires:
        pts = wire_points(f, lay.wires[ident])
        pad = 55.0
    elif any(t["id"] == ident for t in scene.temp_wires):
        tw = next(t for t in scene.temp_wires if t["id"] == ident)
        pts = wire_points(f, {**tw, "via": tw.get("via", [])})
        pad = 30.0
    elif any(m.get("id") == ident for m in scene.markers):
        m = next(m for m in scene.markers if m.get("id") == ident)
        x, y = f.hole(m["hole"])
        pts = [(x - 12, y - 170), (x + 40 + 6.6 * len(m["text"]), y + 12)] if m.get("dir") == "up" else [(x - 12, y - 12), (x + 40 + 6.6 * len(m["text"]), y + 70)]
        pad = 0
    elif ident in lay.components:
        comp = lay.components[ident]
        t = comp["type"]
        if t == "esp32":
            prof = lay.board.data
            n = lay.board.n
            length_p = prof["pcb_mm"][0] / 2.54
            width_p = prof["pcb_mm"][1] / 2.54
            first = comp["placement"]["col0"] - (length_p - (n - 1)) / 2.0
            ymid = (model.ROW_Y["B"] + model.ROW_Y["I"]) / 2.0
            pts = [f.px(first - 0.4, ymid + width_p / 2 + 0.6), f.px(first + length_p, ymid - width_p / 2 - 0.6)]
            pad = 6
        elif t == "resistor":
            pts = [f.hole(h) for h in comp["legs"]]
            pad = 34.0
        elif comp.get("offboard"):
            geo = offboard_geometry(f, lay, comp)
            pts = [f.hole(h) for h in comp["pins"].values()] + [(geo["cx"] - geo["w"] / 2, geo["top"] - 16), (geo["cx"] + geo["w"] / 2, geo["top"] + geo["h"] + 16)]
            pad = 20
        else:
            mod = lay.modules["modules"][t]
            holes = [f.hole(h) for h in comp["pins"].values()]
            row = parse_hole(next(iter(comp["pins"].values())))[1]
            up = row in model.UPPER_ROWS
            hmm = min(mod["body_mm"][1], 25.4) if t == "lcd2004a" else mod["body_mm"][1]
            w, h = mod["body_mm"][0] * MM, hmm * MM
            cx = (min(x for x, _ in holes) + max(x for x, _ in holes)) / 2
            ybase = holes[0][1] + (-1 if up else 1) * lift_for(comp) * K
            y2 = ybase - h if up else ybase + h
            pts = holes + [(cx - w / 2, ybase), (cx + w / 2, y2)]
            pad = 14
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] + yo for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
