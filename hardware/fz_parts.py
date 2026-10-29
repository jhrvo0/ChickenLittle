"""Gerador de partes Fritzing genericas (.fzp + SVGs) para o que NAO existe na biblioteca core.

Sao partes GENERICAS (corpo simples + pinos em grade de 0,1 pol com a pinagem correta). Nao sao modelos
fisicos exatos das placas do usuario: dimensoes marcadas ASSUMED nas definicoes de modulo.
Unidades dos SVGs: 1000 unidades = 1 polegada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

U = 1000.0  # unidades por polegada


@dataclass
class PartSpec:
    key: str                         # id curto: "esp32_38", "tcrt5000", "pot", "lcd2004a"
    title: str
    label: str
    body_in: tuple[float, float]     # (largura, altura) do desenho em polegadas
    pins: list[tuple[str, float, float]]   # (nome, x_in, y_in) centro do pino na vista de protoboard
    pin_edge: str = "bottom"         # borda do corpo onde ficam os pinos (so informativo)
    color: str = "#1c2733"
    tags: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def module_id(self) -> str:
        return f"MotionPet_{self.key}_ModuleID"

    @property
    def base(self) -> str:
        return f"MotionPet_{self.key}"


def _svg_open(w_in: float, h_in: float, extra: str = "") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny" '
            f'width="{w_in:.4f}in" height="{h_in:.4f}in" viewBox="0 0 {w_in * U:.1f} {h_in * U:.1f}" {extra}>\n')


def breadboard_svg(s: PartSpec) -> str:
    w, h = s.body_in
    out = [_svg_open(w, h), '<g id="breadboard">']
    out.append(f'<rect x="0" y="0" width="{w * U:.1f}" height="{h * U:.1f}" rx="40" fill="{s.color}" stroke="#000" stroke-width="12"/>')
    out.append(f'<text x="{w * U / 2:.1f}" y="{h * U / 2:.1f}" font-family="DejaVu Sans, Arial" font-size="70" fill="#9fb3c8" text-anchor="middle">{escape(s.label)}</text>')
    for i, (name, x, y) in enumerate(s.pins):
        out.append(f'<rect id="connector{i}pin" x="{x * U - 36:.1f}" y="{y * U - 36:.1f}" width="72" height="72" fill="#d9b24a" stroke="#7a5f12" stroke-width="6"/>')
        out.append(f'<text x="{x * U:.1f}" y="{(y * U - 60) if s.pin_edge == "bottom" else (y * U + 100):.1f}" font-family="DejaVu Sans, Arial" font-size="50" fill="#e6eef6" text-anchor="middle">{escape(name)}</text>')
    out.append("</g></svg>\n")
    return "\n".join(out)


def schematic_svg(s: PartSpec) -> str:
    n = len(s.pins)
    half = (n + 1) // 2 if n > 20 else n          # ESP32 (38): dois lados; demais: um lado
    two_sides = n > 20
    rows = half
    w_in = 1.8 if two_sides else 1.2
    h_in = (rows + 1) * 0.1 + 0.2
    out = [_svg_open(w_in, h_in), '<g id="schematic">']
    out.append(f'<rect x="{0.3 * U:.0f}" y="0" width="{(w_in - 0.6) * U:.0f}" height="{h_in * U:.0f}" fill="#fff" stroke="#000" stroke-width="10"/>')
    out.append(f'<text x="{w_in * U / 2:.0f}" y="{0.12 * U:.0f}" font-family="DejaVu Sans, Arial" font-size="60" text-anchor="middle">{escape(s.label)}</text>')
    for i, (name, _x, _y) in enumerate(s.pins):
        left = (not two_sides) or i < half
        idx = i if left else i - half
        y = 0.2 * U + idx * 0.1 * U
        x_edge = 0.3 * U if left else (w_in - 0.3) * U
        x_end = 0.0 if left else w_in * U
        tx = x_edge + (50 if left else -50)
        out.append(f'<line id="connector{i}pin" x1="{x_end:.0f}" y1="{y:.0f}" x2="{x_edge:.0f}" y2="{y:.0f}" stroke="#000" stroke-width="10"/>')
        out.append(f'<rect id="connector{i}terminal" x="{x_end - (0 if left else 4):.0f}" y="{y - 4:.0f}" width="4" height="8" fill="none" stroke="none"/>')
        out.append(f'<text x="{tx:.0f}" y="{y + 20:.0f}" font-family="DejaVu Sans, Arial" font-size="55" text-anchor="{"start" if left else "end"}">{escape(name)}</text>')
    out.append("</g></svg>\n")
    return "\n".join(out)


def pcb_svg(s: PartSpec) -> str:
    w, h = s.body_in
    out = [_svg_open(w, h), '<g id="silkscreen">']
    out.append(f'<rect x="10" y="10" width="{w * U - 20:.0f}" height="{h * U - 20:.0f}" fill="none" stroke="#000" stroke-width="10"/></g>')
    for layer in ("copper0", "copper1"):
        out.append(f'<g id="{layer}">')
        for i, (_n, x, y) in enumerate(s.pins):
            out.append(f'<circle id="connector{i}pad" cx="{x * U:.1f}" cy="{y * U:.1f}" r="40" fill="#f2b300" stroke="#b78500" stroke-width="8"/>' if layer == "copper0"
                       else f'<circle cx="{x * U:.1f}" cy="{y * U:.1f}" r="40" fill="#f2b300" stroke="#b78500" stroke-width="8"/>')
        out.append("</g>")
    out.append("</svg>\n")
    return "\n".join(out)


def icon_svg(s: PartSpec) -> str:
    return (_svg_open(0.4, 0.4) + f'<g id="icon"><rect x="20" y="60" width="360" height="280" fill="{s.color}" stroke="#000" stroke-width="10"/>'
            f'<text x="200" y="215" font-family="DejaVu Sans, Arial" font-size="80" fill="#fff" text-anchor="middle">{escape(s.label[:6])}</text></g></svg>\n')


def fzp(s: PartSpec, date: str = "2026-10-29") -> str:
    conns = []
    for i, (name, _x, _y) in enumerate(s.pins):
        conns.append(
            f'  <connector id="connector{i}" name="{escape(name)}" type="male">\n'
            f'   <description>{escape(name)}</description>\n   <views>\n'
            f'    <breadboardView><p layer="breadboard" svgId="connector{i}pin"/></breadboardView>\n'
            f'    <schematicView><p layer="schematic" svgId="connector{i}pin" terminalId="connector{i}terminal"/></schematicView>\n'
            f'    <pcbView><p layer="copper0" svgId="connector{i}pad"/><p layer="copper1" svgId="connector{i}pad"/></pcbView>\n'
            f'   </views>\n  </connector>')
    tags = "".join(f"<tag>{escape(t)}</tag>" for t in (s.tags or ["MotionPet", "generico"]))
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<module moduleId="{s.module_id}" fritzingVersion="1.0.0">\n'
            f' <version>1</version>\n <author>MotionPet (gerado)</author>\n <title>{escape(s.title)}</title>\n <label>{escape(s.label)}</label>\n'
            f' <date>{date}</date>\n <tags>{tags}</tags>\n'
            f' <properties><property name="family">MotionPet generic</property><property name="editor">hardware/fz_parts.py</property></properties>\n'
            f' <taxonomy>MotionPet.generic</taxonomy>\n <description>{escape(s.description or s.title)}</description>\n'
            f' <views>\n'
            f'  <iconView><layers image="icon/{s.base}_icon.svg"><layer layerId="icon"/></layers></iconView>\n'
            f'  <breadboardView><layers image="breadboard/{s.base}_breadboard.svg"><layer layerId="breadboard"/></layers></breadboardView>\n'
            f'  <schematicView><layers image="schematic/{s.base}_schematic.svg"><layer layerId="schematic"/></layers></schematicView>\n'
            f'  <pcbView><layers image="pcb/{s.base}_pcb.svg"><layer layerId="copper0"/><layer layerId="copper1"/><layer layerId="silkscreen"/></layers></pcbView>\n'
            f' </views>\n <connectors>\n' + "\n".join(conns) + "\n </connectors>\n</module>\n")


def bundle_files(s: PartSpec) -> dict[str, bytes]:
    """Arquivos como aparecem dentro de um .fzz/.fzpz (prefixo svg.<vista>.<nome>)."""
    return {
        f"{s.base}.fzp": fzp(s).encode(),
        f"svg.breadboard.{s.base}_breadboard.svg": breadboard_svg(s).encode(),
        f"svg.schematic.{s.base}_schematic.svg": schematic_svg(s).encode(),
        f"svg.pcb.{s.base}_pcb.svg": pcb_svg(s).encode(),
        f"svg.icon.{s.base}_icon.svg": icon_svg(s).encode(),
    }


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
