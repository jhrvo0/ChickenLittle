"""Testes de consistencia da montagem eletronica (netlist canonica, protoboard, firmware, CAD).

Estes testes NAO validam o hardware fisico (status: PENDING_PHYSICAL_VALIDATION). Eles garantem que
a representacao eletronica e coerente com o firmware, com a tabela canonica do Ciclo 5 e com a
conectividade REAL de uma protoboard de 830 pontos.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from hardware import model

REPO = Path(__file__).resolve().parents[1]
PINOUT_H = REPO / "firmware" / "main" / "pinout_config.h"


def _layout() -> model.Layout:
    return model.Layout.load()


def _mutated(mutator) -> model.Layout:
    raw = copy.deepcopy(_layout().raw)
    mutator(raw)
    return model.Layout.from_raw(raw)


def _codes(lay: model.Layout, stage: str = "E") -> set[str]:
    return {i.code for i in model.errors(model.validate(lay, stage))}


def _wire(raw: dict, wid: str) -> dict:
    return next(w for w in raw["wires"] if w["id"] == wid)


def _comp(raw: dict, ref: str) -> dict:
    return next(c for c in raw["components"] if c["ref"] == ref)


# ----------------------------------------------------------------------------
# Protoboard: conectividade e geometria
# ----------------------------------------------------------------------------
def test_breadboard_strips_follow_real_connectivity():
    g = model.hole_group
    assert g("17A") == g("17E") == g("17C")           # A-E ligadas na mesma coluna
    assert g("17F") == g("17J")                        # F-J ligadas na mesma coluna
    assert g("17E") != g("17F")                        # canal central isola os dois lados
    assert g("17A") != g("18A")                        # colunas diferentes sao isoladas
    assert g("5W") == g("61W") != g("5X")              # trilho continuo, trilhos distintos
    with pytest.raises(model.NetlistError):
        model.hole_group("8W")                         # lacuna do trilho (nao existe furo)
    with pytest.raises(model.NetlistError):
        model.parse_hole("64A")


def test_breadboard_geometry_matches_fritzing_svg():
    # valores medidos no SVG do Fritzing breadboard2 (Chromium getBoundingClientRect)
    assert model.fz_hole_xy("1A") == (10.94, 115.19)
    assert model.fz_hole_xy("63J") == (457.34, 36.0) or abs(model.fz_hole_xy("63J")[0] - 457.3) < 0.1
    x, y = model.fz_hole_xy("3W")
    assert abs(x - 25.35) < 0.02 and abs(y - 143.99) < 0.02
    assert abs(model.fz_hole_xy("3Z")[1] - 7.2) < 0.02
    # canal: E -> F = 3 passos (0,3 pol)
    assert model.ROW_Y["F"] - model.ROW_Y["E"] == 3
    assert len(model.RAIL_COLS) == 50


# ----------------------------------------------------------------------------
# Netlist e validacao eletrica
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("stage", model.STAGE_ORDER)
def test_each_stage_validates_without_errors(stage):
    issues = model.validate(_layout(), stage)
    assert not model.errors(issues), [str(i) for i in model.errors(issues)]


def test_derived_nets_match_declared_nets_stage_b():
    lay = _layout()
    pin_net = lay.pin_net_map("B")
    echo = pin_net["M1.ECHO"]
    assert echo == frozenset({"M1.ECHO", "R1.A"})                      # ECHO ve SO o R1
    node = pin_net["R1.B"]
    assert node == frozenset({"R1.B", "R2.A", "U1.IO34"})              # ECHO -> R1 -> NO -> GPIO34
    assert "R2.B" in pin_net["M1.GND"] and "U1.GND@J3.7" in pin_net["M1.GND"]  # NO -> R2 -> GND
    assert pin_net["M1.VCC"] == frozenset({"M1.VCC", "U1.5V"})
    assert pin_net["M1.TRIG"] == frozenset({"M1.TRIG", "U1.IO5"})


def test_divider_math_matches_cycle5_values_and_flags_tolerance_stack():
    lay = _layout()
    r1, r2 = lay.components["R1"], lay.components["R2"]
    assert (r1["ohms"], r2["ohms"]) == (2200, 3300)
    assert model.divider_vout(5.0, 2200, 3300) == pytest.approx(3.00)
    assert model.divider_vout(5.25, 2200, 3300) == pytest.approx(3.15)
    lo, hi = model.divider_extremes(4.75, 5.25, 2200, 3300, 0.05)
    assert hi == pytest.approx(3.275, abs=0.001) and hi <= 3.30   # pior caso com resistores de 5%
    assert lo > 0.75 * 3.3                                           # acima de VIH min (2,475 V)
    # o par proibido 1k/2k estoura o teto
    assert model.divider_vout(5.25, 1000, 2000) > 3.30
    # coerencia com o validador ja existente do Ciclo 5
    from terminal.bench import pinout as p
    a = p.evaluate_echo_divider(2200, 3300)
    assert a.safe is True and a.vout_nominal_v == pytest.approx(3.00)


def test_resistor_color_bands_match_docs():
    assert model.resistor_bands(2200, 0.05) == ["red", "red", "red", "gold"]
    assert model.resistor_bands(3300, 0.05) == ["orange", "orange", "red", "gold"]
    assert model.resistor_bands(150, 0.05) == ["brown", "green", "brown", "gold"]


# ----------------------------------------------------------------------------
# Firmware x netlist
# ----------------------------------------------------------------------------
def _header_defines() -> dict[str, int]:
    text = PINOUT_H.read_text(encoding="utf-8")
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"#define\s+(PIN_\w+)\s+(-?\d+)", text)}


def test_netlist_pins_equal_firmware_pinout_header():
    lay = _layout()
    defines = _header_defines()
    fw_map = lay.raw["firmware_pin_map"]
    assert set(defines) == set(fw_map), "PIN_* do firmware e da netlist divergem"
    for name, spec in fw_map.items():
        assert defines[name] == spec["gpio"], f"{name}: firmware={defines[name]} netlist={spec['gpio']}"
        pin = lay.board.resolve(spec["pin"].split(".", 1)[1])
        assert pin.gpio == spec["gpio"], f"{name}: pino {spec['pin']} nao e GPIO{spec['gpio']} no perfil de placa"
        if spec["net"]:
            declared = {n["name"]: n for n in lay.raw["nets"]}[spec["net"]]
            assert spec["pin"] in declared["pins"], f"{name}: rede {spec['net']} nao contem {spec['pin']}"


def test_netlist_gpios_match_cycle5_canonical_table():
    from terminal.bench import pinout as p
    used = {spec["gpio"] for spec in _layout().raw["firmware_pin_map"].values()}
    assert used == set(p.ALL_ASSIGNED_GPIOS)
    assert not used & set(p.FORBIDDEN_SPI_FLASH_GPIOS)
    assert not used & set(p.RESERVED_UART0_GPIOS)
    assert 12 not in used                                             # MTDI proibido


def test_no_forbidden_esp32_pin_receives_a_connection_in_any_stage():
    lay = _layout()
    for stage in model.STAGE_ORDER:
        occ = lay.occupied_holes(stage)
        for pin in lay.board.pins:
            if pin.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved"):
                hole = lay.esp32_pin_hole(pin)
                assert occ[hole] == [f"U1.{lay.board.ref_name(pin)}"], (stage, pin.label, occ[hole])


def test_usb_side_and_pin_columns_are_consistent_with_assumed_orientation():
    lay = _layout()
    holes = {p.label: lay.esp32_pin_hole(p) for p in lay.board.pins if p.label in ("3V3", "5V", "IO34", "IO5", "IO12")}
    assert holes == {"3V3": "4B", "5V": "22B", "IO34": "8B", "IO5": "13I", "IO12": "16B"}
    # a ESP32 ocupa as fileiras B e I: A e J sao as unicas fileiras acessiveis
    esp_rows = {model.parse_hole(lay.esp32_pin_hole(p))[1] for p in lay.board.pins}
    assert esp_rows == {"B", "I"}


# ----------------------------------------------------------------------------
# Mutacoes: o validador DEVE reprovar montagens perigosas ou erradas
# ----------------------------------------------------------------------------
def test_mutation_echo_wire_to_wrong_pin_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W4").update({"to": "7A"}))       # VN em vez de IO34
    assert "NET_OPEN" in _codes(lay, "B")


def test_mutation_echo_directly_on_gpio34_without_divider_is_rejected():
    def mut(r):
        r["wires"].append({"id": "W99", "stage": "B", "net": "ECHO_5V", "from": "32I", "to": "8A", "color": "red",
                           "via": [], "label": "x", "purpose": "x", "voltage": "x", "safety": "", "validation": "x"})
    codes = _codes(_mutated(mut), "B")
    assert {"NET_EXTRA_PINS", "NET_OPEN"} & codes
    assert "NET_EXTRA_PINS" in codes


def test_mutation_5v_to_flash_pin_column_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W1").update({"to": "20A"}))     # coluna 20 = SD3 (GPIO10, flash)
    assert "FORBIDDEN_PIN_TOUCHED" in _codes(lay, "B")


def test_mutation_gpio12_touched_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W7").update({"from": "16A"}))   # coluna 16 = IO12 (MTDI)
    assert "FORBIDDEN_PIN_TOUCHED" in _codes(lay, "C")


def test_mutation_old_1k_2k_divider_is_rejected():
    def mut(r):
        _comp(r, "R1").update({"ohms": 1000})
        _comp(r, "R2").update({"ohms": 2000})
    assert "DIVIDER_TOO_HIGH" in _codes(_mutated(mut), "B")


def test_mutation_tcrt5000_on_5v_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W5").update({"from": "22A"}))   # 5V no VCC do TCRT5000
    codes = _codes(lay, "C")
    assert "NET_OPEN" in codes or "WRONG_SUPPLY" in codes or "NET_EXTRA_PINS" in codes


def test_mutation_lcd_rw_not_grounded_is_rejected():
    raw_wires = lambda r: r.update(wires=[w for w in r["wires"] if w["id"] != "W14"])  # noqa: E731
    assert "NET_OPEN" in _codes(_mutated(raw_wires), "D")


def test_mutation_double_occupied_hole_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W4").update({"from": "36G"}))   # 36G ja e perna de R2
    assert "HOLE_DOUBLE_OCCUPIED" in _codes(lay, "B")


def test_mutation_invalid_hole_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W3").update({"to": "64A"}))
    assert "HOLE_INVALID" in _codes(lay, "B")


def test_mutation_supply_short_is_rejected():
    def mut(r):
        r["wires"].append({"id": "W98", "stage": "B", "net": "5V", "from": "30F", "to": "33F", "color": "red",
                           "via": [], "label": "x", "purpose": "x", "voltage": "x", "safety": "", "validation": "x"})
    assert "SUPPLY_SHORT" in _codes(_mutated(mut), "B")


def test_mutation_resistor_leg_moved_breaks_divider_node():
    lay = _mutated(lambda r: _comp(r, "R2").update({"legs": ["37G", "33G"]}))   # no fica aberto
    codes = _codes(lay, "B")
    assert "NET_OPEN" in codes


# ----------------------------------------------------------------------------
# Exportadores: Fritzing (.fzz), Wokwi, relatorios, determinismo
# ----------------------------------------------------------------------------
import json
import xml.etree.ElementTree as ET
import zipfile

from hardware import export_fz, export_wokwi, reports
from hardware.render_bb import Scene, render_scene
from hardware.render_schematic import render_schematic


@pytest.mark.parametrize("stage", model.STAGE_ORDER)
def test_fzz_nets_rederived_from_xml_equal_netlist(tmp_path, stage):
    lay = _layout()
    path = tmp_path / f"s{stage}.fzz"
    export_fz.write_fzz(lay, stage, str(path))
    from_fz = {n for n in export_fz.nets_from_fzz(str(path), lay, stage) if len(n) >= 2}
    from_model = {n for n in lay.extract_nets(stage) if len(n) >= 2}
    assert from_fz == from_model


def test_fzz_is_real_zip_with_wellformed_parts_and_reciprocal_connections(tmp_path):
    lay = _layout()
    path = tmp_path / "b.fzz"
    export_fz.write_fzz(lay, "B", str(path))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert any(n.endswith(".fz") for n in names)
        for n in names:
            if n.endswith((".fz", ".fzp", ".svg")):
                ET.fromstring(z.read(n))                       # XML bem formado
        fz = ET.fromstring(z.read([n for n in names if n.endswith(".fz")][0]))
    inst = {i.get("modelIndex"): i for i in fz.find("instances")}
    conn = set()
    for idx, i in inst.items():
        for c in i.findall("views/breadboardView/connectors/connector"):
            for cc in c.findall("connects/connect"):
                conn.add((idx, c.get("connectorId"), cc.get("modelIndex"), cc.get("connectorId")))
    for (a, ca, b, cb) in conn:                                # toda conexao tem a reciproca
        assert (b, cb, a, ca) in conn, (a, ca, b, cb)


def test_fz_part_connectors_land_on_their_holes_within_tolerance():
    lay = _layout()
    xml, extra, _ = export_fz.build_fz(lay, "B")
    fz = ET.fromstring(xml)
    insts = {i.get("modelIndex"): i for i in fz.find("instances")}
    bb = next(i for i in insts.values() if i.get("moduleIdRef") == export_fz.BB_MODULE_ID)
    gen = export_fz.generic_parts(lay)
    pin_off = {export_fz.HCSR04_MODULE_ID: {f"connector{i}": (u[0] * export_fz.HCSR04_PX_PER_UNIT, u[1] * export_fz.HCSR04_PX_PER_UNIT)
                                            for i, u in enumerate(export_fz.HCSR04_PIN_UNITS.values())}}
    spec = gen["esp32"]
    pin_off[spec.module_id] = {f"connector{i}": (p[1] * 90, p[2] * 90) for i, p in enumerate(spec.pins)}
    checked = 0
    for idx, i in insts.items():
        mid = i.get("moduleIdRef")
        if mid not in pin_off:
            continue
        g = i.find("views/breadboardView/geometry")
        x0, y0 = float(g.get("x")), float(g.get("y"))
        for c in i.findall("views/breadboardView/connectors/connector"):
            hole = c.find("connects/connect").get("connectorId")[3:]
            hx, hy = export_fz.bb_hole_px(hole)
            px, py = pin_off[mid][c.get("connectorId")]
            assert abs(x0 + px - hx) < 0.6 and abs(y0 + py - hy) < 0.6, (mid, c.get("connectorId"), hole)
            checked += 1
    assert checked == 38 + 4


def test_fzz_references_only_real_fritzing_core_module_ids():
    xml, extra, _ = export_fz.build_fz(_layout(), "B")
    ids = {i.get("moduleIdRef") for i in ET.fromstring(xml).find("instances")}
    core = {export_fz.BB_MODULE_ID, export_fz.HCSR04_MODULE_ID, export_fz.RESISTOR_MODULE_ID, export_fz.WIRE_MODULE_ID}
    generic = {"MotionPet_esp32_38pin_ModuleID"}
    assert ids <= core | generic
    assert any(n == "MotionPet_esp32_38pin.fzp" for n in extra)       # a parte generica vem embutida


def test_wokwi_diagram_nets_equal_logical_nets_except_unmodeled_tcrt5000():
    lay = _layout()
    d = export_wokwi.build_diagram(lay, "E")
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, *_ in d["connections"]:
        if a.startswith("$") or b.startswith("$"):
            continue
        parent[find(a)] = find(b)
    groups: dict = {}
    for k in list(parent):
        groups.setdefault(find(k), set()).add(k)
    wokwi_nets = {frozenset(g) for g in groups.values()}
    expected = set()
    for net, pins in lay.logical_nets("E"):
        terms = {export_wokwi.wokwi_terminal(lay, p) for p in pins} - {None}
        terms = {t for t in terms if not (t.startswith("esp:GND") and t != "esp:GND.1")}
        if len(terms) >= 2:
            expected.add(frozenset(terms))
    assert wokwi_nets == expected
    types = {p["type"] for p in d["parts"]}
    assert types == {"board-esp32-devkit-c-v4", "wokwi-hc-sr04", "wokwi-resistor", "wokwi-potentiometer", "wokwi-lcd2004"}
    # RW do LCD no GND e ECHO nunca no mesmo no que o GPIO34
    gnd = next(n for n in wokwi_nets if "lcd:RW" in n)
    assert "esp:GND.1" in gnd
    echo = next(n for n in wokwi_nets if "ultra:ECHO" in n)
    assert not any(t.startswith("esp:") for t in echo)


def test_wokwi_gpio_numbers_match_firmware_header():
    lay = _layout()
    d = export_wokwi.build_diagram(lay, "E")
    esp_pins = {t for c in d["connections"] for t in c[:2] if t.startswith("esp:")}
    for name, spec in lay.raw["firmware_pin_map"].items():
        if spec["net"] is None:
            continue
        if name == "PIN_TCRT5000_DO":                       # sem modelo Wokwi: omitido de proposito (documentado)
            assert "esp:35" not in esp_pins
            assert "TCRT5000" in export_wokwi.README and "omitido" in export_wokwi.README.lower() or "nao ha modelo" in export_wokwi.README.lower()
            continue
        want = f"esp:{spec['gpio']}" if spec["gpio"] not in (36, 39) else f"esp:{'VP' if spec['gpio'] == 36 else 'VN'}"
        assert want in esp_pins, (name, want)


def test_stage_svgs_are_wellformed_and_contain_every_wire_and_part():
    lay = _layout()
    for st in model.STAGE_ORDER:
        svg, _ = render_scene(lay, Scene(stage=st, title="t"))
        root = ET.fromstring(svg)
        ids = {e.get("data-id") for e in root.iter() if e.get("data-id")} | {e.get("data-ref") for e in root.iter() if e.get("data-ref")}
        for w in lay.wires_at(st):
            assert w["id"] in ids
        for c in lay.comps(st):
            assert c["ref"] in ids
        ET.fromstring(render_schematic(lay, st))


def test_outputs_are_deterministic_and_wire_table_matches_netlist():
    lay = _layout()
    a = render_scene(lay, Scene(stage="B", title="x"))[0]
    b = render_scene(lay, Scene(stage="B", title="x"))[0]
    assert a == b
    rows = reports.wire_rows(lay, "B")
    assert [r["id"] for r in rows] == ["W1", "W2", "W3", "W4"]
    assert {(r["de_furo"], r["ate_furo"]) for r in rows} == {("22A", "30H"), ("10J", "33I"), ("13J", "31I"), ("36F", "8A")}
    hm = {r["furo"] for r in reports.hole_map_rows(lay, "B")}
    assert {"36F", "36G", "36H", "8A", "8B", "22A", "22B", "30J", "32J"} <= hm


def test_stage_b_wires_do_not_reach_forbidden_pins_nor_5v_gpio():
    lay = _layout()
    occ = lay.occupied_holes("B")
    forbidden_groups = {model.hole_group(lay.esp32_pin_hole(p)) for p in lay.board.pins
                        if p.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved")}
    wire_groups = {model.hole_group(h) for w in lay.wires_at("B") for h in (w["from"], w["to"])}
    assert not (wire_groups & forbidden_groups), wire_groups & forbidden_groups   # compara GRUPOS eletricos, nao so numeros de coluna
    assert occ


# ----------------------------------------------------------------------------
# Indice de pecas (parts.db equivalente) e partes genericas
# ----------------------------------------------------------------------------
def test_parts_db_builder_matches_fzkit_partsdb_schema(tmp_path):
    import sqlite3
    from hardware.tools import build_parts_db
    parts = tmp_path / "parts" / "core"
    parts.mkdir(parents=True)
    (parts / "r.fzp").write_text(
        '<module moduleId="ResistorModuleID"><title>220 Resistor</title><label>R</label>'
        '<tags><tag>Resistor</tag></tags><properties><property name="family">Resistor</property></properties>'
        '<connectors><connector id="connector0" name="Pin 0" type="male"/><connector id="connector1" name="Pin 1" type="male"/></connectors></module>',
        encoding="utf-8")
    lay = _layout()
    for spec in export_fz.generic_parts(lay).values():
        (tmp_path / f"{spec.base}.fzp").write_bytes(fz_parts.fzp(spec).encode())
    db = tmp_path / "root" / "parts" / "parts.db"
    n = build_parts_db.build(tmp_path / "parts", db, sorted(tmp_path.glob("MotionPet_*.fzp")))
    assert n == 1 + 4
    con = sqlite3.connect(db)
    # mesmas consultas SQL que fzkit/partsdb.py usa (copiadas como dado, nao importadas)
    row = con.execute("SELECT path FROM parts WHERE moduleID = ?", ("ResistorModuleID",)).fetchone()
    assert row == ("core/r.fzp",)
    rows = con.execute("""SELECT c.connectorid, c.name, c.type FROM connectors c JOIN parts p ON c.part_id = p.id
                          WHERE p.moduleID = ? ORDER BY c.connectorid""", ("MotionPet_esp32_38pin_ModuleID",)).fetchall()
    assert len(rows) == 38 and rows[0][2] == 0
    hits = con.execute("SELECT moduleID FROM parts WHERE lower(title) LIKE ?", ("%resistor%",)).fetchall()
    assert ("ResistorModuleID",) in hits


from hardware import fz_parts  # noqa: E402


def test_generic_esp32_part_pins_follow_board_profile_and_grid():
    lay = _layout()
    spec = export_fz.generic_parts(lay)["esp32"]
    assert len(spec.pins) == 38
    xs = sorted({round(p[1], 4) for p in spec.pins})
    assert all(abs((b - a) - 0.1) < 1e-6 for a, b in zip(xs, xs[1:]))          # grade de 0,1 pol
    ys = sorted({round(p[2], 4) for p in spec.pins})
    assert len(ys) == 2 and abs((ys[1] - ys[0]) - 0.9) < 1e-6                  # 0,9 pol entre fileiras
    names = [p[0] for p in spec.pins]
    assert "IO34" in names and "5V" in names and names.count("IO5") == 1
    ET.fromstring(fz_parts.breadboard_svg(spec))
    ET.fromstring(fz_parts.schematic_svg(spec))
    ET.fromstring(fz_parts.pcb_svg(spec))


import os  # noqa: E402


@pytest.mark.skipif(not os.environ.get("FRITZING_PARTS_DIR"), reason="defina FRITZING_PARTS_DIR=<checkout do fritzing-parts> para comparar com o Fritzing")
def test_breadboard_model_equals_fritzing_breadboard2_buses():
    """Confere TODAS as 830 posicoes e os 130 barramentos do 'breadboard2' do Fritzing contra o modelo."""
    fzp = Path(os.environ["FRITZING_PARTS_DIR"]) / "core" / "breadboard2.fzp"
    root = ET.parse(fzp).getroot()
    connectors = {c.get("id") for c in root.find("connectors")}
    assert len(connectors) == 830
    fritz_groups = []
    for bus in root.iter("bus"):
        fritz_groups.append(frozenset(m.get("connectorId")[3:] for m in bus.findall("nodeMember")))
    assert len(fritz_groups) == 130
    mine: dict = {}
    for c in connectors:
        mine.setdefault(model.hole_group(c[3:]), set()).add(c[3:])
    assert {frozenset(v) for v in mine.values()} == set(fritz_groups)


# ----------------------------------------------------------------------------
# Guia em slides
# ----------------------------------------------------------------------------
def test_every_component_and_wire_is_added_in_exactly_one_slide_of_its_own_stage():
    lay = _layout()
    seen: dict[str, str] = {}
    for stage, steps in lay.raw["build_steps"].items():
        assert [s["n"] for s in steps] == list(range(1, len(steps) + 1)), stage
        for s in steps:
            for ident in s.get("adds", []):
                assert ident not in seen, f"{ident} adicionado duas vezes"
                seen[ident] = stage
    expected = {c["ref"]: c["stage"] for c in lay.raw["components"] if c["ref"] != "BB1"} | {w["id"]: w["stage"] for w in lay.raw["wires"]}
    assert seen == expected                                    # nada esquecido, nada fora do seu estagio


def test_slides_html_structure_and_focus_boxes():
    from hardware import guide_html
    lay = _layout()
    page = guide_html.build_guide(lay)
    m = re.search(r"window\.SLIDES=(\[.*?\]);window\.FULLBOX=(\[.*?\]);", page, re.S)
    slides, full = json.loads(m.group(1)), json.loads(m.group(2))
    n_steps = sum(len(v) for v in lay.raw["build_steps"].values())
    assert len(slides) == 2 + n_steps + 2                      # intro + materiais + passos + 2 slides de ajuda
    steps = [s for s in slides if s["kind"] == "step"]
    assert len(steps) == n_steps
    for s in steps:
        x, y, w, h = s["focus"]
        assert x >= -1 and y >= -1 and x + w <= full[2] + 1 and y + h <= full[3] + 1, s["title"]
        assert w >= 700 and abs(w / h - 1.6) < 0.05
    assert "ADICIONE AGORA" in page.upper() and "PONTO DE PARADA" in page
    # no master SVG, cada item adicionado carrega o slide em que aparece
    for ident in ("W1", "W4", "M1", "R1", "T1", "MK5", "U1"):
        assert re.search(rf'data-(?:id|ref)="{ident}"[^>]*data-gstep="\d+"|class="marker" data-gstep="\d+"', page) or ident == "MK5"
    # os passos da etapa B aparecem na ordem do guia de bancada: W4 (no -> GPIO34) vem DEPOIS do ensaio do divisor
    titles = [s["title"] if s.get("title") else "" for s in steps]
    assert titles  # titulos vivem no html
    b = lay.raw["build_steps"]["B"]
    assert [i for i, s in enumerate(b) if s.get("hold")] == [4]
    assert "W4" in b[9]["adds"] and "T1" in b[4]["temp"]
    assert all(s["adds"] == [] for s in b[:2])
