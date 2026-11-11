"""Tabelas e relatorios derivados da netlist: fio a fio, mapa de furos, resumo de redes (CSV / Markdown)."""
from __future__ import annotations

import csv
import io

from . import model
from .model import Layout, parse_hole

COLOR_PT = {"red": "vermelho", "black": "preto", "orange": "laranja", "yellow": "amarelo", "green": "verde", "blue": "azul",
            "purple": "roxo", "white": "branco", "brown": "marrom", "grey": "cinza"}
BAND_PT = {"black": "preto", "brown": "marrom", "red": "vermelho", "orange": "laranja", "yellow": "amarelo", "green": "verde",
           "blue": "azul", "violet": "violeta", "grey": "cinza", "white": "branco", "gold": "dourado", "silver": "prata"}


def occupant_label(lay: Layout, occ: str) -> str:
    if occ.startswith("W") and occ[1:].split(".")[0].isdigit():
        wid, end = occ.split(".")
        w = lay.wires[wid]
        return f"fio {wid} ({COLOR_PT.get(w['color'], w['color'])}), ponta {'inicial' if end == 'a' else 'final'}"
    ref, pin = occ.split(".", 1)
    c = lay.components[ref]
    if c["type"] == "esp32":
        bp = lay.board.resolve(pin)
        g = f" (GPIO{bp.gpio})" if bp.gpio is not None else ""
        return f"{ref} {c['label'].split(' (')[0]}: pino {bp.label}{g} [{bp.pid}]"
    if c["type"] == "resistor":
        return f"{ref} {model.fmt_ohms(c['ohms'])}: perna {pin}"
    return f"{ref} {c['label']}: pino {pin}"


def pin_net_names(lay: Layout, stage: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for net, pins in lay.logical_nets(stage):
        for p in pins:
            out[p] = net["name"]
    return out


def wire_rows(lay: Layout, stage: str) -> list[dict]:
    rows = []
    nets = {n["name"]: n for n in lay.raw["nets"]}
    for w in lay.wires_at(stage):
        n = nets.get(w["net"], {})
        rows.append({
            "id": w["id"], "estagio_de_introducao": w["stage"], "cor": COLOR_PT.get(w["color"], w["color"]),
            "de_furo": w["from"], "ate_furo": w["to"], "rede": w["net"], "tensao_esperada": w["voltage"],
            "funcao": w["label"], "justificativa": w["purpose"], "seguranca": w["safety"], "validacao": w["validation"],
        })
        _ = n
    return rows


def component_rows(lay: Layout, stage: str) -> list[dict]:
    pn = pin_net_names(lay, stage)
    rows = []
    for c in lay.comps(stage):
        if c["type"] == "breadboard":
            continue
        for pin in lay.component_pins(c["ref"]):
            hole = lay.pin_hole(c["ref"], pin)
            key = f"{c['ref']}.{pin}"
            if c["type"] == "esp32":
                bp = lay.board.resolve(pin)
                if key not in pn:       # pinos da ESP32 sem uso nao entram na tabela
                    continue
                label = f"{bp.label}" + (f" (GPIO{bp.gpio})" if bp.gpio is not None else "")
            else:
                label = pin
            rows.append({"componente": c["ref"], "descricao": c["label"], "pino": label, "furo": hole,
                         "rede": pn.get(key, "(sem conexao: NC)"), "estado": c.get("status", "")})
    return rows


def hole_map_rows(lay: Layout, stage: str) -> list[dict]:
    occ = lay.occupied_holes(stage)
    pin_net = lay.pin_net_map(stage)
    pn = pin_net_names(lay, stage)

    def key(h):
        c, r = parse_hole(h)
        return (c, model.ROW_Y[r])
    rows = []
    for hole in sorted(occ, key=key):
        users = occ[hole]
        if all(u.startswith("U1.") for u in users) and not any(
                f"{u}" in pn for u in users):
            # pino da ESP32 sem uso: so lista se houver fio na mesma coluna
            grp = model.hole_group(hole)
            if not any(model.hole_group(h2) == grp and h2 != hole for h2 in occ):
                continue
        nets = sorted({pn[u] for u in users if u in pn})
        rows.append({"furo": hole, "coluna": parse_hole(hole)[0], "fileira": parse_hole(hole)[1],
                     "ocupante": " | ".join(occupant_label(lay, u) for u in users), "rede": ",".join(nets)})
    return rows


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    wr.writeheader()
    wr.writerows(rows)
    return buf.getvalue()


def md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "_(vazio)_\n"
    cols = cols or list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |")
    return "\n".join(out) + "\n"


def nets_md(lay: Layout, stage: str) -> str:
    out = []
    for net, pins in lay.logical_nets(stage):
        if len(pins) < 2:
            continue
        voltage = ("tensao nao medida" if net["v_nominal"] is None or net["v_max"] is None
                   else f"nominal {net['v_nominal']} V (max {net['v_max']} V)")
        out.append(f"- **{net['name']}** — dominio `{net['domain']}`, {voltage}: "
                   + ", ".join(f"`{p}`" for p in sorted(pins)) + (f". {net['note']}" if net.get("note") else ""))
    return "\n".join(out) + "\n"


def stage_markdown(lay: Layout, stage: str) -> str:
    st = lay.raw["stages"][stage]
    issues = model.validate(lay, stage)
    md = [f"# Estagio {stage} — {st['title']}", "", "> **CAD paralelo histórico.** Para a montagem atual com LCD I²C, use [o guia final](../guia_montagem_final.html). D/E antigos não se aplicam ao backpack.", "", f"> {st['goal']}", "",
          "> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.", "",
          "## Redes eletricas", "", nets_md(lay, stage), "## Componentes e furos", "",
          md_table(component_rows(lay, stage)), "## Fios (fio a fio)", "", md_table(wire_rows(lay, stage),
                   ["id", "cor", "de_furo", "ate_furo", "rede", "tensao_esperada", "funcao", "seguranca"]),
          "## Mapa de furos ocupados", "", md_table(hole_map_rows(lay, stage)), "## Validacao automatica (software)", ""]
    for i in issues:
        md.append(f"- {i}")
    if not issues:
        md.append("- sem observacoes")
    md.append("")
    md.append("_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._")
    return "\n".join(md) + "\n"
