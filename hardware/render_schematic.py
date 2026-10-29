"""Esquematico eletrico (independente da vista de protoboard), gerado da netlist.

Duas partes:
  1. Blocos por componente com rotulos de rede (cada rede da netlist aparece com o mesmo nome em todos os pinos).
  2. Painel explicito do divisor resistivo do ECHO: ECHO -> R1 -> NO -> GPIO34 e NO -> R2 -> GND, com tensoes.
"""
from __future__ import annotations

from . import model
from .model import Layout
from .render_bb import FONT, esc, _text

DOMAIN_FILL = {"5V": "#fde2e2", "3V3": "#ffe9d2", "GND": "#e4e4e4", "SIGNAL_3V3": "#dff5e6", "SIGNAL_5V": "#fde2e2",
               "ANALOG_LOW": "#e7e1f7", "POWER_5V_LED": "#fde2e2"}
DOMAIN_STROKE = {"5V": "#d11a1a", "3V3": "#e07b00", "GND": "#555", "SIGNAL_3V3": "#1f9d46", "SIGNAL_5V": "#d11a1a",
                 "ANALOG_LOW": "#6b4fb8", "POWER_5V_LED": "#d11a1a"}


def _gnd_symbol(x, y):
    return (f'<path d="M{x},{y} v6 M{x - 8},{y + 6} h16 M{x - 5},{y + 10} h10 M{x - 2},{y + 14} h4" '
            f'stroke="#333" stroke-width="1.6" fill="none"/>')


def _resistor_h(x, y, w=64, label="", sub="", bands=None):
    from .render_bb import BAND_COLORS
    zig = f"M{x},{y} h8 l4,-8 l8,16 l8,-16 l8,16 l8,-16 l4,8 h8"
    out = [f'<path d="{zig}" fill="none" stroke="#222" stroke-width="2"/>']
    out.append(_text(x + w / 2, y - 16, label, 11, "#111", weight="bold"))
    if sub:
        out.append(_text(x + w / 2, y + 28, sub, 9, "#444"))
    if bands:
        for i, b in enumerate(bands):
            out.append(f'<rect x="{x + 12 + i * 11}" y="{y + 12}" width="7" height="6" fill="{BAND_COLORS[b]}" stroke="#0004" stroke-width="0.5"/>')
    return "\n".join(out)


def _resistor_v(x, y, h=64, label="", sub="", bands=None):
    from .render_bb import BAND_COLORS
    zig = f"M{x},{y} v8 l-8,4 l16,8 l-16,8 l16,8 l-16,8 l8,4 v8"
    out = [f'<path d="{zig}" fill="none" stroke="#222" stroke-width="2"/>']
    out.append(_text(x + 20, y + h / 2 - 2, label, 11, "#111", anchor="start", weight="bold"))
    if sub:
        out.append(_text(x + 20, y + h / 2 + 11, sub, 9, "#444", anchor="start"))
    if bands:
        for i, b in enumerate(bands):
            out.append(f'<rect x="{x + 20 + i * 11}" y="{y + h / 2 + 16}" width="7" height="6" fill="{BAND_COLORS[b]}" stroke="#0004" stroke-width="0.5"/>')
    return "\n".join(out)


def _pt(bands):
    from .reports import BAND_PT
    return "-".join(BAND_PT[b] for b in bands)


def divider_panel(lay: Layout, ox: float, oy: float) -> tuple[str, float, float]:
    r1 = lay.components["R1"]
    lower = [x for x in lay.components.values() if str(x.get("role", "")).startswith("divider_bottom")]
    a = r1["ohms"]
    b = sum(x["ohms"] for x in lower)                       # ramo de baixo = resistores em serie
    tol = max([r1["tolerance"]] + [x["tolerance"] for x in lower])
    vnom = model.divider_vout(5.0, a, b)
    vnom_max = model.divider_vout(5.25, a, b)
    lo, hi = model.divider_extremes(4.75, 5.25, a, b, tol)
    c = lay.modules["resistor_color_code"]
    b1 = model.resistor_bands(a, r1["tolerance"], c)
    extra = 78 * (len(lower) - 1)                            # cada resistor extra no ramo de baixo
    w, h = 640, 372 + extra
    o = [f'<g transform="translate({ox} {oy})">']
    o.append(f'<rect x="0" y="0" width="{w}" height="{h}" rx="10" fill="#fffdf6" stroke="#b9b6aa" stroke-width="1.5"/>')
    o.append(_text(16, 26, "Divisor resistivo do ECHO (a parte que protege o ESP32)", 14, "#17212b", anchor="start", weight="bold"))
    # dominios
    o.append(f'<rect x="14" y="44" width="250" height="{262 + extra}" rx="8" fill="#fde2e2" fill-opacity="0.65" stroke="#d11a1a" stroke-dasharray="5 4"/>')
    o.append(_text(24, 62, "DOMINIO 5 V (HC-SR04)", 10, "#a01818", anchor="start", weight="bold"))
    o.append(f'<rect x="270" y="44" width="356" height="{262 + extra}" rx="8" fill="#dff5e6" fill-opacity="0.8" stroke="#1f9d46" stroke-dasharray="5 4"/>')
    o.append(_text(280, 62, "DOMINIO 3,3 V (ESP32)", 10, "#157a35", anchor="start", weight="bold"))
    # ECHO -> R1
    y0 = 130
    o.append(f'<rect x="30" y="{y0 - 22}" width="86" height="44" rx="5" fill="#1e6fb5" stroke="#0e3f6b"/>')
    o.append(_text(73, y0 - 4, "HC-SR04", 11, "#fff", weight="bold"))
    o.append(_text(73, y0 + 12, "pino ECHO", 10, "#dcecff"))
    o.append(f'<path d="M116,{y0} h30" stroke="#222" stroke-width="2"/>')
    o.append(_resistor_h(146, y0, 64, f"R1 = {model.fmt_ohms(a)}", _pt(b1), b1))
    o.append(f'<path d="M210,{y0} h64 " stroke="#222" stroke-width="2"/>')
    o.append(f'<path d="M274,{y0} h110" stroke="#222" stroke-width="2"/>')
    o.append(f'<circle cx="320" cy="{y0}" r="4.5" fill="#111"/>')
    o.append(_text(332, y0 - 14, "NO do divisor", 11, "#157a35", anchor="start", weight="bold"))
    o.append(_text(332, y0 - 28, f"V = {vnom:.2f} V (nominal)", 10, "#157a35", anchor="start"))
    # no -> GPIO34
    o.append(f'<path d="M320,{y0} h120" stroke="#222" stroke-width="2"/>')
    o.append(f'<rect x="440" y="{y0 - 22}" width="168" height="44" rx="5" fill="#1c2733" stroke="#0d141b"/>')
    o.append(_text(524, y0 - 4, "ESP32  GPIO34 (IO34)", 11, "#fff", weight="bold"))
    o.append(_text(524, y0 + 12, "entrada somente-leitura (GPI)", 9.5, "#c9d6e2"))
    # ramo de baixo (R2, R3...) em serie ate o GND
    o.append(f'<path d="M320,{y0} v30" stroke="#222" stroke-width="2"/>')
    yy = y0 + 30
    for i, rr in enumerate(lower):
        bb = model.resistor_bands(rr["ohms"], rr["tolerance"], c)
        o.append(_resistor_v(320, yy, 64, f"{rr['ref']} = {model.fmt_ohms(rr['ohms'])}", _pt(bb), bb))
        yy += 64
        if i < len(lower) - 1:
            vmid = 5.0 * sum(x["ohms"] for x in lower[i + 1:]) / (a + b)
            o.append(f'<path d="M320,{yy} v14" stroke="#222" stroke-width="2"/>')
            o.append(f'<circle cx="320" cy="{yy + 14}" r="4" fill="#111"/>')
            o.append(_text(332, yy + 18, f"junção {rr['ref']}/{lower[i + 1]['ref']}: {vmid:.2f} V (só resistores)", 9.5, "#333", anchor="start"))
            o.append(f'<path d="M320,{yy + 14} v14" stroke="#222" stroke-width="2"/>')
            yy += 28
    o.append(f'<path d="M320,{yy} v22" stroke="#222" stroke-width="2"/>')
    o.append(_gnd_symbol(320, yy + 22))
    o.append(_text(348, yy + 36, "GND comum", 10, "#333", anchor="start"))
    # contas
    ty = 330 + extra
    low_name = "+".join(x["ref"] for x in lower)
    o.append(_text(16, ty, f"Vout = Vecho x ({low_name})/(R1+{low_name}) = Vecho x {b / (a + b):.3f}", 11, "#17212b", anchor="start", weight="bold"))
    o.append(_text(16, ty + 16, f"5,00 V -> {vnom:.2f} V   |   5,25 V -> {vnom_max:.2f} V   |   pior caso com tolerancia {tol:.0%}: "
                   f"{lo:.2f} V .. {hi:.3f} V (teto seguro 3,30 V; VIH minimo 2,475 V)", 9.8, "#333", anchor="start"))
    o.append("</g>")
    return "\n".join(o), w, h


def _used_nets(lay: Layout, stage: str) -> list[tuple[dict, frozenset[str]]]:
    return [(n, p) for n, p in lay.logical_nets(stage) if len(p) >= 2]


def render_schematic(lay: Layout, stage: str, title: str = "") -> str:
    nets = _used_nets(lay, stage)
    pin_to_net: dict[str, dict] = {}
    for n, pins in nets:
        for p in pins:
            pin_to_net[p] = n
    esp_pins = []
    for p in lay.board.pins:
        key = f"U1.{lay.board.ref_name(p)}"
        if key in pin_to_net:
            esp_pins.append((p, pin_to_net[key]))
    order = {"5V": 0, "3V3": 1, "GND": 2}
    esp_pins.sort(key=lambda t: (order.get(t[1]["name"], 9), t[0].gpio if t[0].gpio is not None else -1))
    seen_gnd = False
    collapsed = []
    for p_, n_ in esp_pins:
        if p_.kind == "ground":
            if seen_gnd:
                continue
            seen_gnd = True
        collapsed.append((p_, n_))
    esp_pins = collapsed
    ROW = 30
    mods = [c for c in lay.comps(stage) if c["type"] in ("hc_sr04", "tcrt5000_module", "potentiometer", "lcd2004a")]
    ress = [c for c in lay.comps(stage) if c["type"] == "resistor" and not str(c.get("role", "")).startswith("divider")]
    height = 90 + max(len(esp_pins) * ROW + 40, 200)
    # coluna da direita: modulos empilhados
    y_cursor = 80
    blocks = []
    for m in mods:
        names = list(m["pins"].keys())
        h = len(names) * 24 + 34
        blocks.append((m, y_cursor, h))
        y_cursor += h + 22
    rblocks = []
    for r in ress:
        rblocks.append((r, y_cursor, 74))
        y_cursor += 74 + 16
    height = max(height, y_cursor + 20)
    div = ""
    dh = 0
    if "R1" in {c["ref"] for c in lay.comps(stage)}:
        div, dw, dh = divider_panel(lay, 700, 70)
    height = max(height, 70 + dh + 30)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1360 {height + 40}" width="1360" height="{height + 40}" font-family="{FONT}">',
           '<rect width="100%" height="100%" fill="#f7f5ee"/>',
           _text(14, 24, title or f"MotionPet - Esquematico eletrico - Estagio {stage}", 17, "#17212b", anchor="start", weight="bold"),
           _text(14, 42, "Cada rede tem o MESMO nome em todos os pinos ligados a ela (rotulos de rede). Status: PENDING_PHYSICAL_VALIDATION.",
                 10, "#4a5560", anchor="start")]
    # --- ESP32 ---
    bx, by = 40, 70
    bh = len(esp_pins) * ROW + 34
    out.append(f'<rect x="{bx}" y="{by}" width="150" height="{bh}" rx="8" fill="#1c2733" stroke="#0d141b" stroke-width="2"/>')
    out.append(_text(bx + 75, by + 22, "U1  ESP32", 12, "#fff", weight="bold"))
    for i, (p, net) in enumerate(esp_pins):
        y = by + 44 + i * ROW
        dom = net["domain"]
        out.append(f'<path d="M{bx + 150},{y} h24" stroke="#222" stroke-width="2"/>')
        out.append(_text(bx + 142, y + 4, (f"{lay.board.ref_name(p).split('@')[0]}" + (f" (GPIO{p.gpio})" if p.gpio is not None else "")) + (" x3" if p.kind == "ground" else ""), 10, "#e6eef6", anchor="end"))
        fill, stroke = DOMAIN_FILL.get(dom, "#fff"), DOMAIN_STROKE.get(dom, "#555")
        out.append(f'<g><rect x="{bx + 178}" y="{y - 10}" width="{8 * len(net["name"]) + 14}" height="20" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
                   + _text(bx + 178 + (8 * len(net["name"]) + 14) / 2, y + 4, net["name"], 10.5, "#111", weight="bold") + "</g>")
    # --- modulos (a direita) ---
    mx = 560 if div else 560
    right_x = 470
    for m, y, h in blocks:
        out.append(f'<rect x="{right_x}" y="{y}" width="190" height="{h}" rx="8" fill="#eef3f8" stroke="#33506b" stroke-width="2"/>')
        out.append(_text(right_x + 95, y + 20, f"{m['ref']}  {m['label']}", 10.5, "#17212b", weight="bold"))
        for i, name in enumerate(m["pins"].keys()):
            yy = y + 38 + i * 24
            key = f"{m['ref']}.{name}"
            out.append(f'<path d="M{right_x},{yy} h-24" stroke="#222" stroke-width="2"/>')
            out.append(_text(right_x + 8, yy + 4, name, 9.5, "#17212b", anchor="start"))
            net = pin_to_net.get(key)
            if net:
                dom = net["domain"]
                fill, stroke = DOMAIN_FILL.get(dom, "#fff"), DOMAIN_STROKE.get(dom, "#555")
                wlab = 8 * len(net["name"]) + 14
                out.append(f'<g><rect x="{right_x - 24 - wlab}" y="{yy - 10}" width="{wlab}" height="20" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
                           + _text(right_x - 24 - wlab / 2, yy + 4, net["name"], 10.5, "#111", weight="bold") + "</g>")
            else:
                out.append(_text(right_x - 32, yy + 4, "NC ✕", 9.5, "#999", anchor="end"))
    for r, y, h in rblocks:
        a, b = f"{r['ref']}.A", f"{r['ref']}.B"
        out.append(f'<rect x="{right_x}" y="{y}" width="190" height="{h}" rx="8" fill="#fffbe6" stroke="#8a7440" stroke-width="2"/>')
        out.append(_text(right_x + 95, y + 20, f"{r['ref']}  {model.fmt_ohms(r['ohms'])}", 11, "#3a2f10", weight="bold"))
        out.append(_text(right_x + 95, y + 36, r["label"], 8.6, "#6a5a2a"))
        for i, pin in enumerate((a, b)):
            yy = y + 48 + i * 18
            net = pin_to_net.get(pin)
            out.append(f'<path d="M{right_x},{yy} h-24" stroke="#222" stroke-width="2"/>')
            if net:
                dom = net["domain"]
                fill, stroke = DOMAIN_FILL.get(dom, "#fff"), DOMAIN_STROKE.get(dom, "#555")
                wlab = 8 * len(net["name"]) + 14
                out.append(f'<g><rect x="{right_x - 24 - wlab}" y="{yy - 9}" width="{wlab}" height="18" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
                           + _text(right_x - 24 - wlab / 2, yy + 4, net["name"], 10, "#111", weight="bold") + "</g>")
            out.append(_text(right_x + 8, yy + 4, "terminal " + pin.split(".")[1], 9, "#3a2f10", anchor="start"))
    out.append(div)
    out.append(_text(14, height + 28, "Gerado por hardware/render_schematic.py a partir de hardware/netlist/motionpet.netlist.json", 8.6, "#6b7682", anchor="start"))
    out.append("</svg>")
    return "\n".join(out)
