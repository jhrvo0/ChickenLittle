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
    highlight_new: bool = True
    notes: list[str] = field(default_factory=list)


class Frame:
    """Conversao passo/fileira -> pixels. y cresce para CIMA nos passos; o SVG cresce para BAIXO."""

    def __init__(self, x0: float, y0: float):
        self.x0, self.y0 = x0, y0

    def px(self, col: float, y: float) -> tuple[float, float]:
        return self.x0 + (col - 1) * K, self.y0 - y * K

    def hole(self, hole: str) -> tuple[float, float]:
        c, r = parse_hole(hole)
        return self.px(c, model.ROW_Y[r])


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
    x_left, y_top = f.px(0.15, 16.2)
    x_right, y_bot = f.px(63.85, -5.2)
    parts.append(f'<g id="breadboard" data-ref="BB1">')
    parts.append(f'<rect x="{x_left:.1f}" y="{y_top:.1f}" width="{x_right - x_left:.1f}" height="{y_bot - y_top:.1f}" rx="6" '
                 f'fill="#e8e6df" stroke="#b9b6aa" stroke-width="1.5"/>')
    # canal central
    cx0, cy0 = f.px(0.15, 5.9)
    cx1, cy1 = f.px(63.85, 5.1)
    parts.append(f'<rect x="{cx0:.1f}" y="{cy0:.1f}" width="{cx1 - cx0:.1f}" height="{cy1 - cy0:.1f}" fill="#cfccc2"/>')
    # listras dos trilhos (vermelho = +, azul = -) como no Fritzing
    for yv, col in ((15.9, "#1d4ed8"), (13.2, "#d11a1a"), (-3.2, "#1d4ed8"), (-4.35, "#d11a1a")):
        a = f.px(1.5, yv)
        b = f.px(62.5, yv)
        parts.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{col}" stroke-width="1.4"/>')
    # furos
    for col in range(1, model.N_COLS + 1):
        for row in "ABCDEFGHIJ":
            x, y = f.px(col, model.ROW_Y[row])
            parts.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" rx="1.2" fill="#3b3b3b"/>')
    for row in "WXYZ":
        for col in model.RAIL_COLS:
            x, y = f.px(col, model.ROW_Y[row])
            parts.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" rx="1.2" fill="#3b3b3b"/>')
    # numeros de coluna (de 1 em 1) e letras de fileira
    for col in range(1, model.N_COLS + 1):
        x, yj = f.px(col, 11.95)
        _, ya = f.px(col, -0.95)
        size = 6.4 if col % 5 else 7.6
        weight = "normal" if col % 5 else "bold"
        parts.append(_text(x, yj, col, size, "#555", weight=weight))
        parts.append(_text(x, ya + 3, col, size, "#555", weight=weight))
    for row in "ABCDEFGHIJ":
        for cx in (0.1, 63.9):
            x, y = f.px(cx, model.ROW_Y[row])
            parts.append(_text(x, y + 3, row, 7.4, "#555", weight="bold"))
    for row, name in (("Z", "Z"), ("Y", "Y"), ("X", "X"), ("W", "W")):
        for cx in (0.1, 63.9):
            x, y = f.px(cx, model.ROW_Y[row])
            parts.append(_text(x, y + 2.6, name, 6.2, "#888"))
    parts.append("</g>")


def draw_esp32(f: Frame, lay: Layout, badges: dict[str, str], parts: list[str], new: bool) -> None:
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
    parts.append(f'<g id="U1" class="part{" new" if new else ""}" data-ref="U1">')
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
        if key in badges:
            colr = WIRE_COLORS[badges[key]]
            tcol = "#111" if badges[key] in ("yellow", "white", "orange") else "#fff"
            w = max(26, 6.4 * len(name) + 8)
            h = 13
            by = ly if inward > 0 else ly - h
            parts.append(f'<g class="badge" data-pin="{esc(key)}"><rect x="{x - w / 2:.1f}" y="{by:.1f}" width="{w:.1f}" height="{h}" rx="3" '
                         f'fill="{colr}" stroke="#fff" stroke-width="1"/>'
                         + _text(x, by + 9.6, name, 8, tcol, weight="bold") + "</g>")
        else:
            col_t = "#8fa5ba" if p.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved") else "#c9d6e2"
            if p.kind in ("flash_forbidden", "strapping_forbidden"):
                col_t = "#ff8d8d"
            parts.append(_text(x, ly + (8 if inward > 0 else -1), name, 7.2, col_t))
    # legenda da placa
    cxl, cyl = f.px(first + 6.2, ymid + 0.0)
    parts.append(_text(cxl, cyl + 3, "ESP32 DevKit 38 pinos", 9, "#8aa0b4", weight="bold"))
    parts.append(_text(cxl, cyl + 15, "(ilustracao; confira a sua placa)", 7, "#6f8497"))
    parts.append("</g>")


def _hole_pin_marker(parts, x, y, colr="#d9b24a"):
    parts.append(f'<rect x="{x - 3.6:.1f}" y="{y - 3.6:.1f}" width="7.2" height="7.2" fill="{colr}" stroke="#7a5f12" stroke-width="0.8"/>')


def draw_module(f: Frame, lay: Layout, comp: dict, parts: list[str], new: bool) -> None:
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
    parts.append(f'<g id="{ref}" class="part{" new" if new else ""}" data-ref="{ref}">')
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
        parts.append(_text(cx, top + h - 7, "LCD 2004A V1.1 (20x4) - altura recortada", 9, "#d9fbe9", weight="bold"))
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
    return {"lcd2004a": 9.0, "hc_sr04": 3.4, "tcrt5000_module": 3.8, "potentiometer": 3.8}.get(comp["type"], 3.0)


def _band_rects(bands, x0, x1, y, h):
    out = []
    n = len(bands)
    span = x1 - x0
    for i, b in enumerate(bands):
        pos = x0 + span * (0.18 + 0.15 * i) if i < 3 else x0 + span * 0.82
        out.append(f'<rect x="{pos - 1.6:.1f}" y="{y:.1f}" width="3.2" height="{h:.1f}" fill="{BAND_COLORS[b]}" stroke="#00000033" stroke-width="0.4"/>')
    _ = n
    return out


def draw_resistor(f: Frame, lay: Layout, comp: dict, parts: list[str], new: bool) -> None:
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
    parts.append(f'<g id="{ref}" class="part res{" new" if new else ""}" data-ref="{ref}">')
    parts.append(f'<path d="M{xa:.1f},{ya:.1f} L{bx0:.1f},{by0:.1f} M{bx1:.1f},{by1:.1f} L{xb:.1f},{yb:.1f}" stroke="#9aa0a6" stroke-width="3.2" stroke-linecap="round" fill="none"/>')
    parts.append(f'<g transform="translate({mx:.1f} {my:.1f}) rotate({ang:.2f})">')
    parts.append(f'<rect x="{-body / 2:.1f}" y="-6.2" width="{body:.1f}" height="12.4" rx="6" fill="#d9c28e" stroke="#8a7440" stroke-width="1.2"/>')
    parts.extend(_band_rects(bands, -body / 2, body / 2, -6.2, 12.4))
    parts.append("</g>")
    for hx, hy in ((xa, ya), (xb, yb)):
        parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="3.4" fill="#cfd3d8" stroke="#555" stroke-width="0.8"/>')
    label = f'{ref} {model.fmt_ohms(comp["ohms"])}'
    ly0 = my - 22 if comp.get("label_pos") == "above" else my + 8
    parts.append(f'<g class="reslabel"><rect x="{mx - 30:.1f}" y="{ly0:.1f}" width="60" height="13" rx="3" fill="#fffbe6" stroke="#8a7440" stroke-width="0.8"/>'
                 + _text(mx, ly0 + 9.6, label, 8.4, "#3a2f10", weight="bold") + "</g>")
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


def _place_tag(x: float, y: float, text: str, taken: list[tuple[float, float, float, float]]) -> tuple[float, float]:
    """Escolhe o canto (4 candidatos x 2 distancias) que nao colide com etiquetas ja posicionadas."""
    wtag, htag = 7.2 * len(text) + 6, 12.0
    cands = []
    for dist in (9.0, 17.0, 26.0):
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


def draw_wire(f: Frame, w: dict, parts: list[str], new: bool, show_tags: bool, temp: bool = False) -> None:
    pts = wire_points(f, w)
    colr = WIRE_COLORS.get(w.get("color", "grey"), "#999")
    d = _rounded_polyline(pts)
    cls = "wire" + (" new" if new else "") + (" temp" if temp else "")
    dash = ' stroke-dasharray="7 5"' if temp else ""
    parts.append(f'<g id="{w["id"]}" class="{cls}" data-id="{w["id"]}" data-net="{esc(w.get("net", ""))}">')
    parts.append(f'<path d="{d}" fill="none" stroke="#000" stroke-opacity="0.55" stroke-width="7.4" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
    parts.append(f'<path class="core" d="{d}" fill="none" stroke="{colr}" stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
    for (x, y) in (pts[0], pts[-1]):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="{colr}" stroke="#000" stroke-width="1.2"/>')
    # etiqueta do fio no meio do maior segmento
    best = max(range(len(pts) - 1), key=lambda i: (pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2)
    lx = (pts[best][0] + pts[best + 1][0]) / 2
    ly = (pts[best][1] + pts[best + 1][1]) / 2
    label = w["id"]
    parts.append(f'<g class="wlabel"><rect x="{lx - 11:.1f}" y="{ly - 7:.1f}" width="22" height="14" rx="4" fill="#fff" stroke="{colr if colr != "#f4f4f4" else "#888"}" stroke-width="1.6"/>'
                 + _text(lx, ly + 3.6, label, 8.6, "#111", weight="bold") + "</g>")
    if show_tags:
        for (x, y), hole in ((pts[0], w["from"]), (pts[-1], w["to"])):
            tx, ty = _place_tag(x, y, hole, TAKEN_TAGS)
            tw_ = 7.2 * len(hole) + 6
            parts.append(f'<g class="htag"><line x1="{x:.1f}" y1="{y:.1f}" x2="{tx + tw_ / 2:.1f}" y2="{ty + 6:.1f}" stroke="#555" stroke-width="0.7"/>'
                         f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw_:.1f}" height="12" rx="3" fill="#fff" fill-opacity="0.96" stroke="#555" stroke-width="0.8"/>'
                         + _text(tx + tw_ / 2, ty + 9, hole, 8.2, "#111", weight="bold") + "</g>")
    parts.append("</g>")


def _bounds_pitch(lay: Layout, scene: Scene) -> tuple[float, float, float, float]:
    xs, ys = [0.0, 64.0], [-5.6, 16.6]
    for comp in lay.comps(scene.stage):
        t = comp["type"]
        if t in ("breadboard", "esp32", "resistor"):
            continue
        if comp["ref"] in scene.exclude_refs or (scene.include_refs is not None and comp["ref"] not in scene.include_refs):
            continue
        mod = lay.modules["modules"][t]
        cols = [parse_hole(h)[0] for h in comp["pins"].values()]
        row = parse_hole(next(iter(comp["pins"].values())))[1]
        wp = mod["body_mm"][0] / 2.54
        hp = (min(mod["body_mm"][1], 25.4) if t == "lcd2004a" else mod["body_mm"][1]) / 2.54
        c = (min(cols) + max(cols)) / 2
        xs += [c - wp / 2, c + wp / 2]
        if row in model.UPPER_ROWS:
            ys.append(11 + lift_for(comp) + hp)
        else:
            ys.append(-lift_for(comp) - hp)
    for w in lay.wires_at(scene.stage):
        if w["id"] in scene.exclude_wires or (scene.include_refs is not None and w["id"] not in scene.include_refs):
            continue
        for v in w.get("via", []):
            xs.append(float(v[0]))
            ys.append(_y_from_spec(v[1]))
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

    out: list[str] = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height + 66:.0f}" width="{width:.0f}" height="{height + 66:.0f}" '
               f'data-stage="{scene.stage}" font-family="{FONT}" role="img" aria-label="{esc(scene.title)}">')
    out.append(f"<style>{CSS}</style>")
    out.append(f'<rect width="100%" height="100%" fill="#f7f5ee"/>')
    # titulo
    out.append(_text(14, 22, scene.title or f"MotionPet - Estagio {scene.stage}", 17, "#17212b", anchor="start", weight="bold"))
    if scene.subtitle:
        out.append(_text(14, 40, scene.subtitle, 10.5, "#4a5560", anchor="start"))
    out.append(f'<g transform="translate(0 56)">')
    body: list[str] = []
    draw_breadboard(f, body)
    # zonas de dominio de tensao (Estagio B+): ECHO 5 V x no <= 3,3 V
    if "R1" in {c["ref"] for c in comps}:
        ze = [lay.pin_hole("M1", "ECHO")]
        zx, zy = f.hole("32F")
        zx2, zy2 = f.hole("32J")
        body.append(f'<rect x="{zx - 12:.1f}" y="{zy2 - 12:.1f}" width="24" height="{zy - zy2 + 24:.1f}" rx="6" fill="#ff5a5a" fill-opacity="0.16" stroke="#e03b3b" stroke-width="1.2" stroke-dasharray="4 3"/>')
        nx, ny = f.hole("36F")
        nx2, ny2 = f.hole("36J")
        body.append(f'<rect x="{nx - 12:.1f}" y="{ny2 - 12:.1f}" width="24" height="{ny - ny2 + 24:.1f}" rx="6" fill="#3ecf6b" fill-opacity="0.16" stroke="#1f9d46" stroke-width="1.2" stroke-dasharray="4 3"/>')
        cy_ch = f.px(0, 5.5)[1]
        body.append(_text(zx, cy_ch - 2, "ECHO", 8.6, "#b02020", weight="bold"))
        body.append(_text(zx, cy_ch + 8, "5 V", 8.6, "#b02020", weight="bold"))
        body.append(_text(nx, cy_ch - 2, "NÓ", 8.6, "#157a35", weight="bold"))
        body.append(_text(nx, cy_ch + 8, "≤3,3 V", 8.6, "#157a35", weight="bold"))
        _ = ze
    for comp in comps:
        t = comp["type"]
        if t == "esp32":
            draw_esp32(f, lay, badges, body, new(comp))
        elif t in ("hc_sr04", "tcrt5000_module", "potentiometer", "lcd2004a"):
            draw_module(f, lay, comp, body, new(comp))
    for comp in comps:
        if comp["type"] == "resistor":
            draw_resistor(f, lay, comp, body, new(comp))
    for w in wires:
        draw_wire(f, w, body, new(w), scene.show_tags)
    for tw in scene.temp_wires:
        tw = dict(tw)
        tw.setdefault("via", [])
        tw.setdefault("color", "grey")
        draw_wire(f, tw, body, True, scene.show_tags, temp=True)
    for mk in scene.markers:
        mx_, my_ = f.hole(mk["hole"])
        tw_ = 6.6 * len(mk["text"]) + 14
        body.append(f'<g class="marker"><circle cx="{mx_:.1f}" cy="{my_:.1f}" r="11" fill="none" stroke="#e0007a" stroke-width="3"/>'
                    f'<line x1="{mx_:.1f}" y1="{my_ + 11:.1f}" x2="{mx_ + 24:.1f}" y2="{my_ + 44:.1f}" stroke="#e0007a" stroke-width="2"/>'
                    f'<rect x="{mx_ + 24:.1f}" y="{my_ + 44:.1f}" width="{tw_:.1f}" height="20" rx="5" fill="#fff0f8" stroke="#e0007a" stroke-width="1.6"/>'
                    + _text(mx_ + 24 + tw_ / 2, my_ + 58, mk["text"], 10.5, "#8a004c", weight="bold") + "</g>")
    out.extend(body)
    out.append("</g>")
    # rodape
    foot_y = height + 56 + 4
    foot = ["Fonte: hardware/netlist/motionpet.netlist.json  |  Status: PENDING_PHYSICAL_VALIDATION  |  "
            "Ilustracao tecnica gerada da netlist (nao e foto; confira SEMPRE a serigrafia da sua placa)."]
    out.append(_text(14, foot_y + 6, foot[0], 8.6, "#6b7682", anchor="start"))
    out.append("</svg>")
    meta = {
        "width": width, "height": height + 66,
        "frame_x0": f.x0, "frame_y0": f.y0,
        "holes": {w["id"]: {"from": w["from"], "to": w["to"]} for w in wires},
    }
    return "\n".join(out), meta
