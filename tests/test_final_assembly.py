"""Confere contatos reais dos furos, divisor, pinagem ativa e evidencias do LCD I2C."""
import copy
import re
from pathlib import Path

import pytest

from hardware import final_assembly, model
from terminal.bench import assistant, pinout
from tests.test_bench_stage_d_evidence import _mock_physical_session

ROOT = Path(__file__).resolve().parents[1]


def _graph(wiring):
    """Deriva contatos em DUAS placas; só o primeiro grupo de cinco de cada trilho é usado."""
    parent, occupied = {}, {}

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def join(a, b):
        parent[find(a)] = find(b)

    def strip(h):
        board, contact = h.split(":", 1)
        assert board in ("P1", "P2")
        if contact[0] in "+-":
            assert 1 <= int(contact[1:]) <= 5
            return f"{board}:rail:{contact[0]}:first_group"
        col, row = int(contact[:-1]), contact[-1]
        assert 1 <= col <= 30 and row in "ABCDEFGHIJ"
        return f"{board}:{col}:{'AE' if row in 'ABCDE' else 'FJ'}"

    for w in wiring["wires"]:
        nodes = {}
        for end in ("from", "to"):
            h = w[end + "_hole"]
            # Nomes de redes no texto não unem tiras distintas: só contatos físicos fazem isso.
            label = w[end]
            nodes[end] = label if h is None and label.startswith(("HC-SR04.", "TCRT5000.", "LCD.")) else w["id"] + "." + end
            if h:
                assert h not in occupied, (h, occupied.get(h), w["id"])
                occupied[h] = w["id"]
                join(nodes[end], strip(h))
        join(nodes["from"], nodes["to"])
    for r in wiring["resistors"]:
        for end in ("from", "to"):
            h = r[end + "_hole"]
            assert h not in occupied, (h, occupied.get(h), r["id"])
            occupied[h] = r["id"]
            join(r["id"] + "." + end, strip(h))

    join("GND comum", strip("P1:-1"))
    profile = model.load_boards()[wiring["board_profile"]]
    for side, pins in profile["sides"].items():
        for idx, (label, _, _, _) in enumerate(pins, 1):
            col = 20 - idx
            row = "I" if side == "J2" else "B"
            # Ocupacao fisica: só A/J ficam acessiveis ao longo do corpo da ESP32.
            for h in occupied:
                board, contact = h.split(":", 1)
                if board == "P1" and contact[0] not in "+-" and int(contact[:-1]) <= 19:
                    assert contact[-1] in "AJ", h
            name = f"ESP32.{label}@{side}.{idx}" if label == "GND" else f"ESP32.{label}"
            join(name, strip(f"P1:{col}{row}"))
            if label == "GND":
                join(name, "ESP32.GND@J2.14")
    return find


def _assert_topology(wiring):
    net = _graph(wiring)
    assert net("ESP32.5V") == net("HC-SR04.VCC")
    assert net("ESP32.3V3") == net("LCD.VCC") == net("TCRT5000.VCC")
    assert len({net("ESP32.5V"), net("ESP32.3V3"), net("GND comum")}) == 3
    for module in ("HC-SR04", "LCD", "TCRT5000"):
        assert net(f"{module}.GND") == net("GND comum") == net("ESP32.GND@J2.14")
    for signal, gpio in (("HC-SR04.TRIG", 5), ("TCRT5000.DO", 35), ("LCD.SDA", 21), ("LCD.SCL", 22)):
        assert net(signal) == net(f"ESP32.IO{gpio}")
        assert net(signal) not in {net("ESP32.3V3"), net("ESP32.5V"), net("GND comum")}
    assert net("HC-SR04.ECHO") == net("R1.from")
    assert net("R1.to") == net("R2.from") == net("ESP32.IO34")
    assert net("R2.to") == net("R3.from")
    assert net("R3.to") == net("GND comum")
    assert len({net("HC-SR04.ECHO"), net("ESP32.IO34"), net("R2.to"), net("GND comum")}) == 4
    assert {r["id"]: r["ohms"] for r in wiring["resistors"]} == {"R1": 1000, "R2": 1000, "R3": 300}
    assert net("ESP32.IO34") != net("HC-SR04.VCC")
    return net


def test_final_holes_form_safe_expected_topology_and_protected_echo():
    _assert_topology(final_assembly.load_wiring())


def test_ground_uses_recovered_lcd_reference_instead_of_unverified_alternative():
    wiring = final_assembly.load_wiring()
    ground = next(w for w in wiring["wires"] if w["id"] == "F2")
    assert ground["from_hole"] == "P1:6J"
    assert ground["from"] == "ESP32.GND@J2.14"
    for wire in wiring["wires"]:
        assert wire["from_hole"] not in wiring["avoid_unverified_holes"]
        assert wire["to_hole"] not in wiring["avoid_unverified_holes"]


def test_lcd_light_diagnostic_preserves_existing_feeds_and_changes_only_lcd_ends():
    base = final_assembly.load_wiring()
    original = {w["id"]: w for w in base["wires"]}
    diagnostic = final_assembly.lcd_light_diagnostic(base)
    changed = {w["id"]: w for w in diagnostic["wires"]}
    assert set(changed) == set(original) - {"F16", "F17"}
    for wid in set(changed) - {"F14", "F15"}:
        assert changed[wid] == original[wid]
    assert changed["F14"]["to_hole"] == "P1:+3"
    assert changed["F15"]["to_hole"] == "P1:-4"
    assert base == final_assembly.load_wiring(), "O diagnostico nao pode alterar a montagem normal"
    # Contatos livres dos trilhos, sem tentar inserir outro cabo em 1J/6J/19J.
    used = {w[end] for w in base["wires"] for end in ("from_hole", "to_hole") if w[end]}
    assert not {"P1:+3", "P1:-4"} & used


def test_lcd_light_diagnostic_has_five_volt_power_without_signal_path_to_gpio():
    diagnostic = final_assembly.lcd_light_diagnostic(final_assembly.load_wiring())
    net = _graph(diagnostic)
    assert net("LCD.VCC") == net("ESP32.5V") != net("ESP32.3V3")
    assert net("LCD.GND") == net("ESP32.GND@J2.14")
    assert net("TCRT5000.VCC") == net("ESP32.3V3")
    assert net("HC-SR04.VCC") == net("ESP32.5V")
    assert net("R1.to") == net("R2.from") == net("ESP32.IO34")
    for pin in (5, 34, 35, 21, 22):
        assert net("LCD.VCC") != net(f"ESP32.IO{pin}")
    assert net("LCD.SDA") != net("ESP32.IO21")
    assert net("LCD.SCL") != net("ESP32.IO22")


@pytest.mark.parametrize("wire,hole", [("F14", "P1:+5"), ("F9", "P2:8B"), ("F16", "P1:13J"), ("F3", "P2:1A"), ("F4", "P2:+5"), ("F10", "P2:20J")])
def test_topology_checks_catch_wrong_supply_unprotected_echo_and_wrong_halves(wire, hole):
    wiring = copy.deepcopy(final_assembly.load_wiring())
    w = next(w for w in wiring["wires"] if w["id"] == wire)
    w["to_hole"] = hole
    with pytest.raises(AssertionError):
        _assert_topology(wiring)


def test_two_boards_have_independent_positive_rails_and_explicit_common_ground():
    wiring = final_assembly.load_wiring()
    assert [(b["id"], b["positive_rail_v"]) for b in wiring["breadboards"]] == [("P1", 5.0), ("P2", 3.3)]
    wiring["wires"] = [w for w in wiring["wires"] if w["id"] != "F4"]
    with pytest.raises(AssertionError):
        _assert_topology(wiring)


def test_component_test_stops_follow_each_installation_and_lcd_ir_precede_resistors():
    steps = final_assembly.steps()
    assert [s["test_component"] for s in steps if "test_component" in s] == ["esp32", "lcd", "ir", "hcsr04", "all"]
    def placed_before(component):
        placed = set()
        for s in steps:
            if s.get("test_component") == component:
                return placed
            placed.update(s["items"])
        raise AssertionError(component)
    assert not placed_before("esp32")
    assert {"F14", "F15", "F16", "F17"} <= placed_before("lcd")
    assert {"F11", "F12", "F13"} <= placed_before("ir")
    assert not {"R1", "R2", "R3"} & placed_before("ir")
    assert {"R1", "R2", "R3", "F5", "F6", "F7", "F8", "F9", "F10"} <= placed_before("hcsr04")


def test_active_firmware_and_bench_pinouts_match_final_wiring():
    header = (ROOT / "firmware/main/pinout_config.h").read_text(encoding="utf-8")
    defines = {k: int(v) for k, v in re.findall(r"#define\s+(PIN_\w+)\s+(-?\d+)", header)}
    for name, gpio in final_assembly.load_wiring()["firmware_pins"].items():
        assert defines[name] == gpio
    assert set(defines.values()) == set(pinout.ALL_ASSIGNED_GPIOS)
    assert not any(k.startswith("PIN_LCD_") and k not in ("PIN_LCD_SDA", "PIN_LCD_SCL") for k in defines)
    assert pinout.verify_canonical_pinout_conflicts() == (True, [])
    used = {s.gpio_number for s in pinout.CANONICAL_PINOUT_TABLE if s.gpio_number is not None}
    assert used == set(pinout.ALL_ASSIGNED_GPIOS)


def test_visual_guide_contains_every_item_once_in_sequence_and_stays_reproducible():
    wiring = final_assembly.load_wiring()
    expected = {x["id"] for k in ("wires", "resistors") for x in wiring[k]}
    actual = [x for s in final_assembly.steps() for x in s["items"]]
    assert set(actual) == expected and len(actual) == len(expected)
    page = final_assembly.build_guide(wiring)
    assert page == (ROOT / "hardware/guia_montagem_final.html").read_text(encoding="utf-8")
    assert re.findall(r'data-item="([^"]+)"', page) == [w["id"] for w in wiring["wires"]] + [r["id"] for r in wiring["resistors"]]


def test_stage_d_i2c_accepts_3v3_and_four_wire_evidence_without_rw_jumper(monkeypatch, tmp_path):
    _mock_physical_session(monkeypatch, ["line".ljust(20)] * 4)
    result = assistant.run_stage_d(serial_port="COM1", lcd_vdd_v=3.30, i2c_wiring_confirmed=True,
                                   visual_confirmed=True, log_path=tmp_path / "log.json")
    assert result.passed
    assert result.details["lcd_interface"] == "i2c"
    assert result.details["i2c_wiring_confirmed_by_operator"]
    assert result.details["rw_confirmed_by_operator"] is None


@pytest.mark.parametrize("voltage", [float("nan"), float("inf"), 2.99, 3.36, 5.0])
def test_stage_d_i2c_rejects_5v_and_invalid_measurements_before_opening_port(tmp_path, voltage):
    result = assistant.run_stage_d(serial_port="COM1", lcd_vdd_v=voltage, log_path=tmp_path / "log.json")
    assert not result.passed and result.halted_for_electrical_safety


@pytest.mark.parametrize("voltage,wiring,visual,has_frame", [(None, True, True, True), (3.3, False, True, True), (3.3, True, False, True), (3.3, True, True, False)])
def test_stage_d_i2c_requires_measurement_wiring_visual_and_received_frame(monkeypatch, tmp_path, voltage, wiring, visual, has_frame):
    _mock_physical_session(monkeypatch, ["line".ljust(20)] * 4 if has_frame else [])
    result = assistant.run_stage_d(serial_port="COM1", lcd_vdd_v=voltage, i2c_wiring_confirmed=wiring,
                                   visual_confirmed=visual, log_path=tmp_path / "log.json")
    assert not result.passed
