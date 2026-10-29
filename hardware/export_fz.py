"""Exportador Fritzing (.fz / .fzz) a partir da netlist canonica.

* Protoboard, HC-SR04 e resistor usam as pecas CORE do Fritzing (moduleId reais, geometria medida nos SVGs).
* ESP32 de 38 pinos, TCRT5000, potenciometro e LCD usam pecas GENERICAS geradas aqui e embutidas no .fzz.
* Todas as conexoes sao escritas de forma reciproca (parte <-> furo da protoboard <-> fio).

LIMITE: nao ha Fritzing nesta maquina de build; o arquivo foi validado estruturalmente e por reextracao
de redes (tests/test_hardware_cad.py), mas NAO foi aberto no aplicativo. Status: UNVERIFIED_IN_FRITZING_GUI.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from . import fz_parts, model
from .model import Layout, parse_hole

SCENE_DPI = 90.0


def bb_module_id() -> str:
    return model.active().fz_module_id


def bb_scale() -> float:
    return model.active().fz_scale


HCSR04_MODULE_ID = "hc-sr0489a24442a28f4051a3a8757dd4825d87"
RESISTOR_MODULE_ID = "ResistorModuleID"
WIRE_MODULE_ID = "WireModuleID"

# geometria medida (Chromium) nos SVGs do fritzing-parts (unidades -> pixels de cena a 90 dpi)
HCSR04_PIN_UNITS = {"VCC": (724.312, 908.016), "TRIG": (824.306, 908.016), "ECHO": (924.31, 907.985), "GND": (1024.298, 907.974)}
HCSR04_PX_PER_UNIT = 90.0 / 1000.0
HCSR04_SIZE_PX = (45.097 / 25.4 * 90.0, 23.605 / 25.4 * 90.0)
RESISTOR_PX_PER_UNIT = 0.9
RESISTOR_PINS_400MIL = ((1.009, 4.087), (41.897, 4.087))
RESISTOR_SIZE_PX = (42.917 * 0.9, 9.71 * 0.9)

WIRE_HEX = {"red": "#cc1414", "black": "#404040", "orange": "#ff7033", "yellow": "#ffe24d", "green": "#47cc79",
            "blue": "#418dd9", "purple": "#ab58d9", "white": "#ffffff", "brown": "#8c3b00", "grey": "#999999"}


def generic_parts(lay: Layout) -> dict[str, fz_parts.PartSpec]:
    """Especificacoes das partes genericas usadas neste layout."""
    specs: dict[str, fz_parts.PartSpec] = {}
    prof = lay.board.data
    n = lay.board.n
    L = prof["pcb_mm"][0] / 25.4
    Wd = prof["pcb_mm"][1] / 25.4
    off = (L - (n - 1) * 0.1) / 2
    gap = prof["row_spacing_in"]
    y_top = (Wd - gap) / 2
    pins = []
    # USB a esquerda: fileira superior = J3, inferior = J2 (ver Layout.esp32_pin_hole)
    order = [(p, "J3") for p in lay.board.pins if p.side == "J3"] + [(p, "J2") for p in lay.board.pins if p.side == "J2"]
    for p, side in order:
        y = y_top if side == "J3" else y_top + gap
        pins.append((lay.board.ref_name(p).split("@")[0] + (f"#{p.pid}" if "@" in lay.board.ref_name(p) else ""),
                     off + (p.index - 1) * 0.1, y))
    specs["esp32"] = fz_parts.PartSpec("esp32_38pin", "ESP32 DevKit 38 pinos (generico MotionPet)", "ESP32", (L, Wd), pins,
                                       pin_edge="bottom", color="#1c2733",
                                       tags=["ESP32", "DevKit", "MotionPet"],
                                       description="Parte generica: pinagem tipo DevKitC V4, 0,9 pol entre fileiras. NAO e o modelo exato da sua placa.")
    for t, key in (("tcrt5000_module", "tcrt5000"), ("potentiometer", "pot"), ("lcd2004a", "lcd2004a")):
        mod = lay.modules["modules"][t]
        names = mod["pin_order"]
        bw, bh = mod["body_mm"][0] / 25.4, mod["body_mm"][1] / 25.4
        if t == "lcd2004a":
            bh = min(bh, 1.2)
        w = max(bw, (len(names) - 1) * 0.1 + 0.4)
        h = bh + 0.35
        x0 = (w - (len(names) - 1) * 0.1) / 2
        edge = "bottom" if t == "lcd2004a" else "top"
        py = h - 0.12 if edge == "bottom" else 0.12
        specs[t] = fz_parts.PartSpec(key, mod["title"], key.upper()[:6] if key != "lcd2004a" else "LCD2004",
                                     (w, h), [(nm, x0 + i * 0.1, py) for i, nm in enumerate(names)], pin_edge=edge,
                                     color={"tcrt5000": "#243a8a", "pot": "#2a63b8", "lcd2004a": "#0f7a4d"}[key],
                                     tags=[key, "MotionPet"], description=f"Parte generica: {mod['title']}. Ordem dos pinos: {names}.")
    return specs


@dataclass
class _Inst:
    ref: str
    module_id: str
    model_index: int
    layer: str
    x: float
    y: float
    pin_xy: dict[str, tuple[float, float]]     # nome do conector (connectorN) -> (x, y) em px de cena
    props: dict[str, str]
    connects: dict[str, list[tuple[int, str, str]]]   # conector -> [(modelIndex, connectorId, layer)]


def bb_hole_px(hole: str) -> tuple[float, float]:
    x, y = model.fz_hole_xy(hole)
    return round(x * bb_scale(), 3), round(y * bb_scale(), 3)


def build_fz(lay: Layout, stage: str) -> tuple[bytes, dict[str, bytes], dict]:
    """Retorna (xml .fz, arquivos extras do bundle, meta)."""
    gen = generic_parts(lay)
    mi = 3000
    insts: list[_Inst] = []
    bb = _Inst("BB1", bb_module_id(), mi, "breadboardbreadboard", 0.0, 0.0, {}, {}, {})
    insts.append(bb)
    mi += 1
    by_ref: dict[str, _Inst] = {"BB1": bb}

    def connect_hole(inst: _Inst, conn: str, hole: str, layer: str) -> None:
        inst.connects.setdefault(conn, []).append((bb.model_index, f"pin{hole}", "breadboardbreadboard"))
        bb.connects.setdefault(f"pin{hole}", []).append((inst.model_index, conn, layer))

    extra_files: dict[str, bytes] = {}
    for comp in lay.comps(stage):
        t, ref = comp["type"], comp["ref"]
        if t == "breadboard":
            continue
        if t == "esp32":
            spec = gen["esp32"]
            holes = {i: lay.esp32_pin_hole(p) for i, p in enumerate(
                [p for p in lay.board.pins if p.side == "J3"] + [p for p in lay.board.pins if p.side == "J2"])}
            px = {f"connector{i}": (spec.pins[i][1] * SCENE_DPI, spec.pins[i][2] * SCENE_DPI) for i in range(len(spec.pins))}
            hx, hy = bb_hole_px(holes[0])
            ox, oy = hx - px["connector0"][0], hy - px["connector0"][1]
            inst = _Inst(ref, spec.module_id, mi, "breadboard", ox, oy, px, {}, {})
            insts.append(inst); by_ref[ref] = inst; mi += 1
            for i, hole in holes.items():
                connect_hole(inst, f"connector{i}", hole, "breadboard")
            extra_files.update(fz_parts.bundle_files(spec))
        elif t == "hc_sr04":
            order = lay.modules["modules"]["hc_sr04"]["fritzing_connectors"]
            px = {order[n]: (u[0] * HCSR04_PX_PER_UNIT, u[1] * HCSR04_PX_PER_UNIT) for n, u in HCSR04_PIN_UNITS.items()}
            h0 = comp["pins"]["VCC"]
            hx, hy = bb_hole_px(h0)
            ox, oy = hx - px["connector0"][0], hy - px["connector0"][1]
            inst = _Inst(ref, HCSR04_MODULE_ID, mi, "breadboard", ox, oy, px, {}, {})
            insts.append(inst); by_ref[ref] = inst; mi += 1
            for n, hole in comp["pins"].items():
                connect_hole(inst, order[n], hole, "breadboard")
        elif t in ("tcrt5000_module", "potentiometer", "lcd2004a"):
            spec = gen[t]
            names = [p[0] for p in spec.pins]
            px = {f"connector{i}": (spec.pins[i][1] * SCENE_DPI, spec.pins[i][2] * SCENE_DPI) for i in range(len(names))}
            h0 = comp["pins"][names[0]]
            hx, hy = bb_hole_px(h0)
            ox, oy = hx - px["connector0"][0], hy - px["connector0"][1]
            inst = _Inst(ref, spec.module_id, mi, "breadboard", ox, oy, px, {}, {})
            insts.append(inst); by_ref[ref] = inst; mi += 1
            for i, n in enumerate(names):
                connect_hole(inst, f"connector{i}", comp["pins"][n], "breadboard")
            extra_files.update(fz_parts.bundle_files(spec))
        elif t == "resistor":
            ha, hb = comp["legs"]
            xa, ya = bb_hole_px(ha)
            xb, yb = bb_hole_px(hb)
            left, right = (ha, hb) if xa <= xb else (hb, ha)       # connector0 = esquerda
            lx, ly = bb_hole_px(left)
            p0 = (RESISTOR_PINS_400MIL[0][0] * RESISTOR_PX_PER_UNIT, RESISTOR_PINS_400MIL[0][1] * RESISTOR_PX_PER_UNIT)
            span_in = abs(parse_hole(hb)[0] - parse_hole(ha)[0]) * 0.1
            p1 = (p0[0] + span_in * SCENE_DPI, p0[1])
            props = {"resistance": f"{comp['ohms']:g}", "pin spacing": f"{int(round(span_in * 1000))} mil"}
            inst = _Inst(ref, RESISTOR_MODULE_ID, mi, "breadboard", lx - p0[0], ly - p0[1], {"connector0": p0, "connector1": p1}, props, {})
            insts.append(inst); by_ref[ref] = inst; mi += 1
            connect_hole(inst, "connector0", left, "breadboard")
            connect_hole(inst, "connector1", right, "breadboard")
    wires = []
    for w in lay.wires_at(stage):
        x1, y1 = bb_hole_px(w["from"])
        x2, y2 = bb_hole_px(w["to"])
        winst = _Inst(w["id"], WIRE_MODULE_ID, mi, "breadboardWire", x1, y1, {"connector0": (0, 0), "connector1": (x2 - x1, y2 - y1)},
                      {"__color": WIRE_HEX.get(w["color"], "#999999")}, {})
        mi += 1
        for conn, hole in (("connector0", w["from"]), ("connector1", w["to"])):
            winst.connects.setdefault(conn, []).append((bb.model_index, f"pin{hole}", "breadboardbreadboard"))
            bb.connects.setdefault(f"pin{hole}", []).append((winst.model_index, conn, "breadboardWire"))
        wires.append(winst)

    # ---------- XML ----------
    root = ET.Element("module", {"fritzingVersion": "1.0.5", "icon": ".png"})
    pp = ET.SubElement(root, "project_properties")
    for k, v in (("simulator_animation_time_s", "5s"), ("simulator_number_of_steps", "400"), ("simulator_spice_options", ""),
                 ("simulator_time_step_mode", "false"), ("simulator_time_step_s", "1us")):
        ET.SubElement(pp, k, {"value": v})
    views = ET.SubElement(root, "views")
    ET.SubElement(views, "view", {"name": "breadboardView", "backgroundColor": "#ffffff", "gridSize": "0.1in", "showGrid": "1", "alignToGrid": "1", "viewFromBelow": "0", "colorWiresByLength": "0"})
    ET.SubElement(views, "view", {"name": "schematicView", "backgroundColor": "#ffffff", "gridSize": "0.1in", "showGrid": "1", "alignToGrid": "1", "viewFromBelow": "0"})
    ET.SubElement(views, "view", {"name": "pcbView", "backgroundColor": "#333333", "gridSize": "0.05in", "showGrid": "1", "alignToGrid": "1", "viewFromBelow": "0"})
    instances = ET.SubElement(root, "instances")

    def emit_connectors(parent: ET.Element, inst: _Inst, layer: str) -> None:
        if not inst.connects:
            return
        cs = ET.SubElement(parent, "connectors")
        for cid in sorted(inst.connects, key=lambda s: (len(s), s)):
            c = ET.SubElement(cs, "connector", {"connectorId": cid, "layer": layer})
            ET.SubElement(c, "geometry", {"x": "0", "y": "0"})
            cc = ET.SubElement(c, "connects")
            for (midx, ocid, olayer) in inst.connects[cid]:
                ET.SubElement(cc, "connect", {"connectorId": ocid, "modelIndex": str(midx), "layer": olayer})

    for inst in insts:
        attrs = {"moduleIdRef": inst.module_id, "modelIndex": str(inst.model_index)}
        if inst.module_id == bb_module_id():
            attrs["path"] = model.active().fz_path
        elif inst.module_id == RESISTOR_MODULE_ID:
            attrs["path"] = ":/resources/parts/core/resistor.fzp"
        e = ET.SubElement(instances, "instance", attrs)
        for k, v in inst.props.items():
            ET.SubElement(e, "property", {"name": k, "value": v})
        ET.SubElement(e, "title").text = inst.ref
        vs = ET.SubElement(e, "views")
        bbv = ET.SubElement(vs, "breadboardView", {"layer": inst.layer})
        ET.SubElement(bbv, "geometry", {"z": "1.5" if inst is bb else "2.5", "x": f"{inst.x:.3f}", "y": f"{inst.y:.3f}"})
        emit_connectors(bbv, inst, inst.layer)
        if inst is not bb:
            for vn, layer, dx in (("schematicView", "schematic", 700), ("pcbView", "copper0", 1400)):
                v = ET.SubElement(vs, vn, {"layer": layer})
                ET.SubElement(v, "geometry", {"z": "2.5", "x": f"{dx + (inst.model_index - 3000) * 14}", "y": "100"})
    for w in wires:
        e = ET.SubElement(instances, "instance", {"moduleIdRef": WIRE_MODULE_ID, "modelIndex": str(w.model_index), "path": ":/resources/parts/core/wire.fzp"})
        ET.SubElement(e, "title").text = f"Wire{w.ref}"
        vs = ET.SubElement(e, "views")
        v = ET.SubElement(vs, "breadboardView", {"layer": "breadboardWire"})
        x2, y2 = w.pin_xy["connector1"]
        ET.SubElement(v, "geometry", {"z": "3.5", "x": f"{w.x:.3f}", "y": f"{w.y:.3f}", "x1": "0", "y1": "0", "x2": f"{x2:.3f}", "y2": f"{y2:.3f}", "wireFlags": "64"})
        ET.SubElement(v, "wireExtras", {"mils": "22.2222", "color": w.props["__color"], "opacity": "1", "banded": "0"})
        emit_connectors(v, w, "breadboardWire")
    ET.indent(root, space="    ")
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    meta = {"instances": len(insts) + len(wires), "generic_parts": sorted({k for k in extra_files if k.endswith(".fzp")})}
    return xml, extra_files, meta


def write_fzz(lay: Layout, stage: str, path: str) -> dict:
    xml, extra, meta = build_fz(lay, stage)
    base = path.rsplit("/", 1)[-1][:-1]            # nome.fzz -> nome.fz
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(base, date_time=(2026, 10, 29, 0, 0, 0))   # reprodutivel
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, xml)
        for name in sorted(extra):
            i2 = zipfile.ZipInfo(name, date_time=(2026, 10, 29, 0, 0, 0))
            i2.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(i2, extra[name])
    return meta


# ----------------------------------------------------------------------------
# Releitura: redes eletricas a partir do .fz (verificacao cruzada independente)
# ----------------------------------------------------------------------------
def nets_from_fzz(path_or_bytes, lay: Layout, stage: str) -> list[frozenset[str]]:
    """Reextrai as redes do .fz usando SOMENTE <connect> + grupos da protoboard + ligacoes internas de GND."""
    data = path_or_bytes
    if isinstance(path_or_bytes, (str, bytes)) and not isinstance(path_or_bytes, bytes):
        with zipfile.ZipFile(path_or_bytes) as z:
            fz = [n for n in z.namelist() if n.endswith(".fz")][0]
            data = z.read(fz)
    root = ET.fromstring(data)
    gen = generic_parts(lay)
    idx_to_inst: dict[str, ET.Element] = {i.get("modelIndex"): i for i in root.find("instances")}
    title = {k: (v.findtext("title") or "") for k, v in idx_to_inst.items()}
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def node(midx: str, cid: str):
        inst = idx_to_inst[midx]
        mid = inst.get("moduleIdRef")
        if mid == bb_module_id():
            return ("hole", cid[3:])
        return ("pin", title[midx], cid)

    holes = set()
    for midx, inst in idx_to_inst.items():
        bbv = inst.find("views/breadboardView")
        if bbv is None:
            continue
        for c in bbv.findall("connectors/connector"):
            a = node(midx, c.get("connectorId"))
            if a[0] == "hole":
                holes.add(a[1])
            for cc in c.findall("connects/connect"):
                b = node(cc.get("modelIndex"), cc.get("connectorId"))
                if b[0] == "hole":
                    holes.add(b[1])
                union(a, b)
    for h in holes:
        union(("hole", h), model.hole_group(h))
    # fios: as duas pontas do fio sao o mesmo condutor
    for midx, inst in idx_to_inst.items():
        if inst.get("moduleIdRef") == WIRE_MODULE_ID:
            union(("pin", title[midx], "connector0"), ("pin", title[midx], "connector1"))
    # ESP32: GND interligados
    gnd = [p for p in lay.board.pins if p.kind == "ground"]
    esp_spec = gen["esp32"]
    ordered = [p for p in lay.board.pins if p.side == "J3"] + [p for p in lay.board.pins if p.side == "J2"]
    for p in gnd[1:]:
        union(("pin", "U1", f"connector{ordered.index(gnd[0])}"), ("pin", "U1", f"connector{ordered.index(p)}"))
    # converte (pin, ref, connectorN) -> nome de pino logico
    def logical(ref: str, cid: str) -> str | None:
        comp = lay.components.get(ref)
        if comp is None:
            return None
        t = comp["type"]
        n = int(cid.replace("connector", ""))
        if t == "esp32":
            return f"{ref}.{lay.board.ref_name(ordered[n])}"
        if t == "hc_sr04":
            inv = {v: k for k, v in lay.modules["modules"]["hc_sr04"]["fritzing_connectors"].items()}
            return f"{ref}.{inv[cid]}"
        if t == "resistor":
            ha, hb = comp["legs"]
            left_is_a = bb_hole_px(ha)[0] <= bb_hole_px(hb)[0]
            return f"{ref}." + (("A" if left_is_a else "B") if n == 0 else ("B" if left_is_a else "A"))
        names = lay.modules["modules"][t]["pin_order"]
        return f"{ref}.{names[n]}"

    groups: dict = {}
    for key in list(parent):
        if key[0] != "pin":
            continue
        name = logical(key[1], key[2])
        if name:
            groups.setdefault(find(key), set()).add(name)
    return [frozenset(g) for g in groups.values()]
