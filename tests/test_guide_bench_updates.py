"""O guia não confunde telemetria observada com validação elétrica da montagem."""

import json
import re

from hardware import guide_html, model


def test_guide_reports_observed_serial_and_keeps_electrical_checks_pending():
    page = guide_html.build_guide(model.Layout.load())
    match = re.search(r"window\.SLIDES=(\[.*?\]);window\.FULLBOX=", page, re.S)
    assert match is not None
    slides = json.loads(match.group(1))
    intro = slides[0]["html"]
    assert "COM3" in intro and "serial" in intro
    assert "PENDING_PHYSICAL_VALIDATION" in intro
    assert "ainda nao foram validados fisicamente" in intro


def test_echo_check_precedes_gpio_and_commands_match_bench_requirements():
    steps = model.Layout.load().raw["build_steps"]
    echo_test = steps["B"][7]
    gpio_connection = steps["B"][8]
    assert "USB desligada" in echo_test["text"]
    assert "linha 22" in echo_test["text"]
    assert "W3" in gpio_connection["adds"]
    assert "Não conecte" in gpio_connection["warn"]
    assert "inspect" in steps["B"][-1]["commands"][0]
    assert "measured" not in steps["B"][-1]["commands"][0]
    assert "--vcc-measured-v" in steps["C"][-1]["commands"][0]
    assert "--lcd-vdd-v" in steps["D"][-1]["commands"][0]
    assert "--rw-confirmed" in steps["D"][-1]["commands"][-1]
    assert "--visual-confirmed" in steps["D"][-1]["commands"][-1]
