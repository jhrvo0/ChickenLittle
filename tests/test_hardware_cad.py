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
PINOUT_H = REPO / "hardware" / "netlist" / "archive" / "pinout_parallel.h"


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
    _layout()                                           # ativa o perfil da netlist (bb400x2: duas meias-protoboards)
    g = model.hole_group
    assert model.n_cols() == 60 and model.active().cols_per_board == 30
    assert g("17A") == g("17E") == g("17C")           # A-E ligadas na mesma coluna
    assert g("17F") == g("17J")                        # F-J ligadas na mesma coluna
    assert g("17E") != g("17F")                        # canal central isola os dois lados
    assert g("17A") != g("18A")                        # colunas diferentes sao isoladas
    with pytest.raises(model.NetlistError):
        model.parse_hole("31A")                        # cada meia-protoboard so tem 30 colunas (a 2a e escrita P2:...)
    with pytest.raises(model.NetlistError):
        model.parse_hole("0A")
    with pytest.raises(model.NetlistError):
        model.parse_hole("P3:1A")                      # so ha duas placas
    assert model.parse_hole("P2:5E") == (35, "E")
    assert g("P2:5A") == g("P2:5E") and g("P2:5A") != g("5A") and g("P2:5F") != g("5F")   # placas sao independentes
    assert model.make_hole(35, "E") == "P2:5E" and model.make_hole(30, "J") == "30J"


def test_breadboard_geometry_matches_fritzing_half_breadboard_v2():
    _layout()
    # valores medidos no SVG do Fritzing Half_breadboard56a (Chromium getBoundingClientRect), unidades do SVG
    assert model.fz_hole_xy("1A") == (13.65, 144.0)
    assert model.fz_hole_xy("30A") == (274.65, 144.0)
    assert model.fz_hole_xy("1J") == (13.65, 45.0)
    assert model.fz_hole_xy("10F")[1] - model.fz_hole_xy("10E")[1] == -27.0     # canal: E -> F = 3 passos de 9
    assert model.ROW_Y["F"] - model.ROW_Y["E"] == 3
    # a 2a placa (P2) e a mesma peca deslocada da largura da placa (292,41 unidades): encostadas pela ponta
    assert model.fz_hole_xy("P2:1A") == (292.41 + 13.65, 144.0)
    assert model.fz_hole_xy("P2:30J") == (292.41 + 274.65, 45.0)
    assert len(model.breadboard_profiles()["bb400"].rail_cols) == 25


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
    assert pin_net["R2.B"] == frozenset({"R2.B", "R3.A"})                  # NO -> R2 -> junção -> R3
    assert "R3.B" in pin_net["M1.GND"] and "U1.GND@J3.7" in pin_net["M1.GND"]  # R3 -> GND
    assert pin_net["M1.VCC"] == frozenset({"M1.VCC", "U1.5V"})
    assert pin_net["M1.TRIG"] == frozenset({"M1.TRIG", "U1.IO5"})


def test_divider_math_with_the_users_resistors_1k_and_1k_plus_300():
    """Resistores do usuario: 1 kΩ (dourado-vermelho-preto-marrom) e 300 Ω (dourado-marrom-preto-laranja)."""
    lay = _layout()
    r1, r2, r3 = (lay.components[k] for k in ("R1", "R2", "R3"))
    assert (r1["ohms"], r2["ohms"], r3["ohms"]) == (1000, 1000, 300)
    bottom = r2["ohms"] + r3["ohms"]                                   # R2 e R3 em serie
    assert model.divider_vout(5.0, r1["ohms"], bottom) == pytest.approx(2.826, abs=0.001)
    assert model.divider_vout(5.25, r1["ohms"], bottom) == pytest.approx(2.967, abs=0.001)
    lo, hi = model.divider_extremes(4.75, 5.25, r1["ohms"], bottom, 0.05)
    assert hi == pytest.approx(3.096, abs=0.001) and hi <= 3.30 - 0.15  # >= 150 mV de folga ao teto de 3,30 V
    assert lo > 0.75 * 3.3 + 0.05                                      # acima de VIH min (2,475 V) com folga
    # o par proibido 1k/2k estoura o teto
    assert model.divider_vout(5.25, 1000, 2000) > 3.30
    # coerencia com o validador ja existente do Ciclo 5
    from terminal.bench import pinout as p
    a = p.evaluate_echo_divider(r1["ohms"], bottom)
    assert a.safe is True and a.has_recommended_margin is True and a.vout_nominal_v == pytest.approx(2.826, abs=0.001)
    # tensao no nó entre R2 e R3 (so resistores) e corrente solicitada ao ECHO
    assert 5.0 * r3["ohms"] / (r1["ohms"] + bottom) == pytest.approx(0.652, abs=0.001)
    assert 5.0 / (r1["ohms"] + bottom) < 0.0025                        # < 2,5 mA


def test_users_resistors_cannot_be_used_directly_as_r1_r2():
    """1 kΩ em cima/300 Ω embaixo da 1,15 V (leitura falha); 300 Ω em cima/1 kΩ embaixo da 3,85 V (queima o GPIO)."""
    def only_two(top, bottom):
        def mut(r):
            _comp(r, "R1").update({"ohms": top})
            _comp(r, "R2").update({"ohms": bottom})
            _comp(r, "R3").update({"ohms": 0.001})                       # R3 ~ curto (nao existe no cenario)
        return _codes(_mutated(mut), "B")
    assert "DIVIDER_TOO_LOW" in only_two(1000, 300)
    assert "DIVIDER_TOO_HIGH" in only_two(300, 1000)


def test_chosen_divider_is_the_cheapest_safe_combination_of_1k_and_300():
    """Enumera redes EM SERIE de 1 kΩ e 300 Ω (ate 3 resistores no total): so (R1 = 1k | R2 = 1k + 300) passa."""
    def chain(a, b):
        return a * 1000 + b * 300
    safe = []
    for n1a in range(0, 4):
        for n1b in range(0, 4):
            for n2a in range(0, 4):
                for n2b in range(0, 4):
                    if n1a + n1b == 0 or n2a + n2b == 0 or n1a + n1b + n2a + n2b > 3:
                        continue
                    r1, r2 = chain(n1a, n1b), chain(n2a, n2b)
                    lo, hi = model.divider_extremes(4.75, 5.25, r1, r2, 0.05)
                    if hi <= 3.30 and lo >= 0.75 * 3.3:
                        safe.append(((n1a, n1b), (n2a, n2b)))
    assert safe == [((1, 0), (1, 1))]                                  # R1 = 1 kΩ ; R2 = 1 kΩ + 300 Ω em serie


def test_resistor_color_bands_match_docs():
    assert model.resistor_bands(2200, 0.05) == ["red", "red", "red", "gold"]
    assert model.resistor_bands(3300, 0.05) == ["orange", "orange", "red", "gold"]
    # resistores do usuario (lidos a partir da faixa dourada: dourado-vermelho-preto-marrom e dourado-marrom-preto-laranja)
    assert model.resistor_bands(1000, 0.05) == ["brown", "black", "red", "gold"]
    assert model.resistor_bands(300, 0.05) == ["orange", "black", "brown", "gold"]
    assert model.resistor_bands(150, 0.05) == ["brown", "green", "brown", "gold"]


# ----------------------------------------------------------------------------
# Firmware x netlist
# ----------------------------------------------------------------------------
def _header_defines() -> dict[str, int]:
    text = PINOUT_H.read_text(encoding="utf-8")
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"#define\s+(PIN_\w+)\s+(-?\d+)", text)}


def test_historical_netlist_preserves_archived_parallel_pinout():
    lay = _layout()
    defines = _header_defines()
    fw_map = lay.raw["firmware_pin_map"]
    assert set(defines) == set(fw_map), "PIN_* do firmware e da netlist divergem"
    for name, spec in fw_map.items():
        assert defines[name] == spec["gpio"], f"{name}: firmware={defines[name]} netlist={spec['gpio']}"
        pin = lay.board.resolve(spec["pin"].split(".", 1)[1])
        assert pin.gpio == spec["gpio"], f"{name}: pino {spec['pin']} nao e GPIO{spec['gpio']} no perfil de placa"
        if spec["net"] and not spec.get("deferred"):
            declared = {n["name"]: n for n in lay.raw["nets"]}[spec["net"]]
            assert spec["pin"] in declared["pins"], f"{name}: rede {spec['net']} nao contem {spec['pin']}"
        if spec.get("deferred"):                               # LCD: estagio D adiado, mas os GPIOs continuam conferidos acima
            assert name.startswith("PIN_LCD")
            assert spec["net"] in {n["name"] for n in lay.raw["deferred_nets"]}


def test_historical_netlist_gpios_remain_free_of_forbidden_pins():
    from terminal.bench import pinout as p
    used = {spec["gpio"] for spec in _layout().raw["firmware_pin_map"].values()}
    assert used == set(_header_defines().values())
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
    assert holes == {"3V3": "19I", "5V": "1I", "IO34": "15I", "IO5": "10B", "IO12": "7I"}   # DevKitC: 5V junto da USB (coluna 1)
    # a ESP32 ocupa as fileiras B e I: A e J sao as unicas fileiras acessiveis
    esp_rows = {model.parse_hole(lay.esp32_pin_hole(p))[1] for p in lay.board.pins}
    assert esp_rows == {"B", "I"}


# ----------------------------------------------------------------------------
# Mutacoes: o validador DEVE reprovar montagens perigosas ou erradas
# ----------------------------------------------------------------------------
def test_mutation_echo_wire_to_wrong_pin_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W3").update({"to": "13J"}))      # IO32 em vez de IO34
    assert "NET_OPEN" in _codes(lay, "B")


def test_mutation_echo_directly_on_gpio34_without_divider_is_rejected():
    def mut(r):
        r["wires"].append({"id": "W99", "stage": "B", "net": "ECHO_5V", "from": "22D", "to": "15J", "color": "red",
                           "via": [], "label": "x", "purpose": "x", "voltage": "x", "safety": "", "validation": "x"})
    codes = _codes(_mutated(mut), "B")
    assert {"NET_EXTRA_PINS", "NET_OPEN"} & codes
    assert "NET_EXTRA_PINS" in codes


def test_mutation_5v_to_flash_pin_column_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W1").update({"to": "3J"}))      # coluna 3 de cima = SD3 (GPIO10, flash)
    assert "FORBIDDEN_PIN_TOUCHED" in _codes(lay, "B")


def test_mutation_gpio12_touched_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W2").update({"from": "7J"}))    # 7J = IO12 (MTDI)
    assert "FORBIDDEN_PIN_TOUCHED" in _codes(lay, "B")


def test_mutation_old_1k_2k_divider_is_rejected():
    def mut(r):
        _comp(r, "R1").update({"ohms": 1000})
        _comp(r, "R2").update({"ohms": 1700})                               # 1700 + 300 (R3) = 2000
    assert "DIVIDER_TOO_HIGH" in _codes(_mutated(mut), "B")


def test_mutation_tcrt5000_on_5v_is_rejected():
    lay = _mutated(lambda r: _comp(r, "M2")["pins"].update({"VCC": "22W"}))   # VCC do TCRT5000 no trilho + (5 V)
    codes = _codes(lay, "C")
    assert "NET_OPEN" in codes or "WRONG_SUPPLY" in codes or "NET_EXTRA_PINS" in codes


def test_mutation_double_occupied_hole_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W3").update({"from": "26C"}))   # 26C ja e perna de R1
    assert "HOLE_DOUBLE_OCCUPIED" in _codes(lay, "B")


def test_mutation_invalid_hole_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W3").update({"to": "31A"}))
    assert "HOLE_INVALID" in _codes(lay, "B")


def test_mutation_supply_short_is_rejected():
    def mut(r):
        r["wires"].append({"id": "W98", "stage": "B", "net": "5V", "from": "22W", "to": "22X", "color": "red",
                           "via": [], "label": "x", "purpose": "x", "voltage": "x", "safety": "", "validation": "x"})
    assert "SUPPLY_SHORT" in _codes(_mutated(mut), "B")


def test_mutation_resistor_leg_moved_breaks_divider_node():
    lay = _mutated(lambda r: _comp(r, "R3").update({"legs": ["29G", "24G"]}))   # a junção R2/R3 fica aberta
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
    bb = next(i for i in insts.values() if i.get("moduleIdRef") == export_fz.bb_module_id())
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
            tgt = c.find("connects/connect").get("connectorId")
            if not tgt.startswith("pin"):                     # modulo fora da placa: o conector liga num fio
                continue
            hole = tgt[3:]
            hx, hy = export_fz.bb_hole_px(hole)
            px, py = pin_off[mid][c.get("connectorId")]
            assert abs(x0 + px - hx) < 0.6 and abs(y0 + py - hy) < 0.6, (mid, c.get("connectorId"), hole)
            checked += 1
    assert checked == 38                                     # HC-SR04 fica fora da placa (ligado por fios)


def test_fzz_references_only_real_fritzing_core_module_ids():
    xml, extra, _ = export_fz.build_fz(_layout(), "B")
    ids = {i.get("moduleIdRef") for i in ET.fromstring(xml).find("instances")}
    core = {export_fz.bb_module_id(), export_fz.HCSR04_MODULE_ID, export_fz.RESISTOR_MODULE_ID, export_fz.WIRE_MODULE_ID}
    generic = {"MotionPet_esp32_38pin_ModuleID"}
    assert ids <= core | generic
    assert any(n == "MotionPet_esp32_38pin.fzp" for n in extra)       # a parte generica vem embutida


def test_wokwi_diagram_nets_equal_logical_nets_except_unmodeled_tcrt5000():
    lay = _layout()
    d = export_wokwi.build_diagram(lay, "C")
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
    for net, pins in lay.logical_nets("C"):
        terms = {export_wokwi.wokwi_terminal(lay, p) for p in pins} - {None}
        terms = {t for t in terms if not (t.startswith("esp:GND") and t != "esp:GND.1")}
        if len(terms) >= 2:
            expected.add(frozenset(terms))
    assert wokwi_nets == expected
    types = {p["type"] for p in d["parts"]}
    assert types == {"board-esp32-devkit-c-v4", "wokwi-hc-sr04", "wokwi-resistor"}           # sem potenciometro
    # ECHO bruto (5 V) nunca no mesmo no que um pino da ESP32
    echo = next(n for n in wokwi_nets if "ultra:ECHO" in n)
    assert not any(t.startswith("esp:") for t in echo)


def test_wokwi_gpio_numbers_match_firmware_header():
    lay = _layout()
    d = export_wokwi.build_diagram(lay, "D")
    esp_pins = {t for c in d["connections"] for t in c[:2] if t.startswith("esp:")}
    for name, spec in lay.raw["firmware_pin_map"].items():
        if spec["net"] is None or spec.get("deferred"):
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
    assert [r["id"] for r in rows] == ["W1", "W2", "W3"]
    assert {(r["de_furo"], r["ate_furo"]) for r in rows} == {("1J", "3W"), ("13A", "15X"), ("26E", "15J")}
    hm = {r["furo"] for r in reports.hole_map_rows(lay, "B")}
    assert {"22C", "26C", "26D", "29D", "29A", "30X", "26E", "15J", "22E", "10A", "24W", "25X", "1J", "13A"} <= hm


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
@pytest.mark.parametrize("profile,fzp_name,n_connectors", [("bb400", "Half_breadboard_v2.fzp", 400), ("bb830", "breadboard2.fzp", 830)])
def test_breadboard_model_equals_fritzing_buses(profile, fzp_name, n_connectors):
    """Confere as tiras A-J (colunas) do modelo contra os barramentos reais do Fritzing, para cada perfil."""
    root = ET.parse(Path(os.environ["FRITZING_PARTS_DIR"]) / "core" / fzp_name).getroot()
    connectors = {c.get("id") for c in root.find("connectors")}
    assert len(connectors) == n_connectors
    fritz = {frozenset(m.get("connectorId")[3:] for m in b.findall("nodeMember")) for b in root.iter("bus")}
    model.set_active_breadboard(profile)
    try:
        mine: dict = {}
        for c in connectors:
            hole = c[3:]
            if hole[-1] in "ABCDEFGHIJ" and model.parse_hole(hole):
                mine.setdefault(model.hole_group(hole), set()).add(hole)
        main_fritz = {g for g in fritz if all(h[-1] in "ABCDEFGHIJ" for h in g)}
        assert {frozenset(v) for v in mine.values()} == main_fritz
        assert len(main_fritz) == 2 * model.n_cols()
    finally:
        model.set_active_breadboard("bb400")


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
    assert len(slides) == 2 + n_steps + 2                      # intro + materiais + passos + 2 de ajuda
    steps = [s for s in slides if s["kind"] == "step"]
    assert len(steps) == n_steps
    for s in steps:
        x, y, w, h = s["focus"]
        assert x >= -1 and y >= -1 and x + w <= full[2] + 1 and y + h <= full[3] + 1, s["title"]
        clamped = w >= full[2] - 1 or h >= full[3] - 1               # o zoom nunca passa do tamanho do desenho
        assert (w >= 700 or clamped) and (abs(w / h - 1.6) < 0.05 or clamped)
    assert "ADICIONE AGORA" in page.upper() and "PONTO DE PARADA" in page
    # no master SVG, cada item adicionado carrega o slide em que aparece
    for ident in ("W1", "W3", "M1", "R1", "U1"):
        assert re.search(rf'data-(?:id|ref)="{ident}"[^>]*data-gstep="\d+"|class="marker" data-gstep="\d+"', page) or ident == "MK5"
    # os passos da etapa B aparecem na ordem do guia de bancada: W4 (no -> GPIO34) vem DEPOIS do ensaio do divisor
    titles = [s["title"] if s.get("title") else "" for s in steps]
    assert titles  # titulos vivem no html
    b = lay.raw["build_steps"]["B"]
    assert [i for i, s in enumerate(b) if s.get("hold")] == [4]
    assert "W3" in b[8]["adds"] and not b[4].get("temp")
    assert 'data-id="T1"' not in page and 'data-id="MK5"' not in page
    assert b[0]["adds"] == [] and set(b[1]["adds"]) == {"W1", "W2"}       # primeiro so os trilhos (5 V e GND)


# ----------------------------------------------------------------------------
# Estagio D: LCD 2004A na 2a meia-protoboard (P2)
# ----------------------------------------------------------------------------
def test_lcd_on_second_board_has_rw_grounded_and_signals_on_firmware_gpios():
    lay = _layout()
    pin_net = lay.pin_net_map("D")
    gnd = pin_net["M3.VSS"]
    assert {"M3.RW", "M3.K", "R4.B", "U1.GND@J3.7"} <= gnd           # RW no GND: o LCD nunca devolve 5 V
    assert pin_net["M3.VDD"] >= {"U1.5V", "R5.A"}
    assert pin_net["M3.V0"] == frozenset({"M3.V0", "R4.A"})
    assert pin_net["M3.A"] == frozenset({"M3.A", "R5.B"})
    for gpio, pin in ((19, "RS"), (18, "E"), (21, "D4"), (22, "D5"), (23, "D6"), (27, "D7")):
        assert pin_net[f"M3.{pin}"] == frozenset({f"M3.{pin}", f"U1.IO{gpio}"}), pin
    for d in ("D0", "D1", "D2", "D3"):                                 # modo 4 bits: D0-D3 sem fio
        assert pin_net.get(f"M3.{d}", frozenset({f"M3.{d}"})) == frozenset({f"M3.{d}"})
    assert all(h.startswith("P2:") for h in lay.components["M3"]["pins"].values())


def test_mutation_lcd_rw_not_grounded_is_rejected():
    lay = _mutated(lambda r: r.update({"wires": [w for w in r["wires"] if w["id"] != "W8"]}))   # tira o fio do RW
    codes = _codes(lay, "D")
    assert "NET_OPEN" in codes or "NET_PARTIAL" in codes or "NET_UNDECLARED" in codes


def test_mutation_lcd_vdd_on_gpio_is_rejected():
    lay = _mutated(lambda r: _wire(r, "W7").update({"to": "12A"}))    # VDD do LCD ligado ao GPIO19 em vez do trilho +
    assert model.errors(model.validate(lay, "D"))


# ----------------------------------------------------------------------------
# Trilhos (+/-) e modulos fora da placa
# ----------------------------------------------------------------------------
def test_rails_are_per_board_and_follow_fritzing_geometry_and_colors():
    _layout()
    g = model.hole_group
    assert g("3W") == g("30W") and g("3X") == g("30X") and g("3W") != g("3X")      # trilho continuo, + e - separados
    assert g("3W") != g("P2:3W")                                                   # P1 e P2 so se ligam por fio
    assert model.rail_sign("21W") == "+" and model.rail_sign("15X") == "-"         # base: externo vermelho (+), interno azul (-)
    assert model.fz_hole_xy("3W") == (17.0, 180.0) and model.fz_hole_xy("3X") == (17.0, 171.0)
    assert model.fz_hole_xy("P2:3W") == (292.41 + 17.0, 180.0)
    with pytest.raises(model.NetlistError):
        model.parse_hole("8W")                                                     # vao entre grupos de 5 furos
    assert "trilho +" in model.hole_label("21W") and "vermelho" in model.hole_label("21W")


@pytest.mark.skipif(not os.environ.get("FRITZING_PARTS_DIR"), reason="defina FRITZING_PARTS_DIR=<checkout do fritzing-parts> para comparar com o Fritzing")
def test_rail_buses_equal_fritzing_half_breadboard():
    root = ET.parse(Path(os.environ["FRITZING_PARTS_DIR"]) / "core" / "Half_breadboard_v2.fzp").getroot()
    _layout()
    for b in root.iter("bus"):
        if not b.get("id").startswith("bus-"):
            continue
        holes = {m.get("connectorId")[3:] for m in b.findall("nodeMember")} - {f"31{b.get('id')[-1]}"}   # pino 31 nao e usado
        assert len({model.hole_group(h) for h in holes}) == 1
        assert {h for h in holes} == {f"{c}{b.get('id')[-1]}" for c in model.active().rail_cols}


def test_offboard_modules_use_female_male_leads_and_keep_signals_safe():
    lay = _layout()
    for ref in ("M1", "M2"):
        c = lay.components[ref]
        assert c["offboard"]["leads"].keys() == c["pins"].keys()
    assert lay.components["M2"]["pins"]["VCC"] == "19J"                            # TCRT5000 so no 3V3 (pino 3V3 = 19J)
    assert model.rail_sign(lay.components["M1"]["pins"]["VCC"]) == "+"
    pin_net = lay.pin_net_map("B")
    assert pin_net["M1.ECHO"] == frozenset({"M1.ECHO", "R1.A"})                    # ECHO so ve o divisor
    nets = export_fz.nets_from_fzz(export_fz.build_fz(lay, "C")[0], lay, "C")
    assert frozenset({"M2.DO", "U1.IO35"}) in {frozenset(n) for n in nets}         # os fios dos modulos aparecem no .fzz


def test_esp32_pinout_follows_devkitc_5v_and_clk_next_to_usb():
    """Correcao 2026-10-29: na DevKitC o 5V e o CLK ficam junto da USB; o 3V3 (pino 1) na outra ponta."""
    lay = _layout()
    hole = {p.label: lay.esp32_pin_hole(p) for p in lay.board.pins if p.kind != "ground"}
    assert lay.esp32()["placement"]["usb"] == "left"
    assert hole["5V"] == "1I" and hole["CLK"] == "1B"                 # coluna 1 = ponta da USB
    assert hole["3V3"] == "19I" and hole["IO34"] == "15I" and hole["IO5"] == "10B"


def test_photographed_nodemcu_has_ground_next_to_5v():
    """O verso fotografado diz GND, nao CMD, no segundo pino a partir da USB."""
    lay = _layout()
    pin = lay.board.resolve("GND@J2.18")
    assert pin.kind == "ground" and pin.gpio is None
    assert lay.esp32_pin_hole(pin) == "2I"
    assert lay.esp32_pin_hole(lay.board.resolve("5V")) == "1I"
    assert "U1.GND@J2.18" in lay.pin_net_map("B")["M1.GND"]
    assert export_wokwi.wokwi_terminal(lay, "U1.GND@J2.18") == "esp:GND.1"
