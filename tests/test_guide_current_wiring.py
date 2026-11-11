"""Regressões do guia para os fios e a topologia descritos na bancada."""

import json
import re

from hardware import guide_html, model


def test_sensor_labels_colors_and_voltage_divider_match_guide():
    layout = model.Layout.load()
    leads = layout.components["M1"]["offboard"]["leads"]
    assert leads == {"VCC": "red", "TRIG": "red", "ECHO": "blue", "GND": "white"}
    nets = layout.pin_net_map("B")
    assert {"M1.ECHO", "R1.A"} <= nets["M1.ECHO"]
    assert {"R1.B", "R2.A", "U1.IO34"} <= nets["R1.B"]
    assert {"R2.B", "R3.A"} <= nets["R2.B"]
    assert {"R3.B", "M1.GND"} <= nets["R3.B"]
    assert {"M1.TRIG", "U1.IO5"} <= nets["M1.TRIG"]

    page = guide_html.build_guide(layout)
    match = re.search(r"window\.SLIDES=(\[.*?\]);window\.FULLBOX=", page, re.S)
    assert match is not None
    slides = json.loads(match.group(1))
    sensor_step = next(s for s in slides if "M1 ·" in s["html"])
    assert "ECHO" in sensor_step["html"] and "azul" in sensor_step["html"]
    assert "GND" in sensor_step["html"] and "branco" in sensor_step["html"]
    assert "TRIG" in sensor_step["html"] and "VCC" in sensor_step["html"]
