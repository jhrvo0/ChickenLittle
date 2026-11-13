"""Regressões das correções de revisão do firmware (docs/revisao_firmware_testes_2026-11-12.md).

Conferem o código-fonte; não substituem o build PlatformIO nem o ensaio com a placa.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "firmware/main/main.cpp").read_text(encoding="utf-8")
PINOUT = (ROOT / "firmware/main/pinout_config.h").read_text(encoding="utf-8")
IOT = (ROOT / "firmware/communication/iot_transport.cpp").read_text(encoding="utf-8")


def _setup_body() -> str:
    start = MAIN.index("void setup(void)")
    return MAIN[start:MAIN.index("void loop(void)", start)]


def test_lcd_hardware_is_disabled_by_default_and_overridable():
    assert re.search(r"#ifndef MOTIONLAB_LCD_HW_ENABLED\s+#define MOTIONLAB_LCD_HW_ENABLED 0\s+#endif", PINOUT)


def test_lcd_init_and_boot_animation_only_run_when_hardware_enabled():
    setup = _setup_body()
    guard = setup.index("#if MOTIONLAB_LCD_HW_ENABLED")
    end = setup.index("#endif", guard)
    for call in ("lcd_ctx_init(", "lcd_ctx_load_default_glyphs(", "lcd_play_boot_animation("):
        assert guard < setup.index(call) < end, call
    # O quadro virtual continua sendo montado para o notebook, mesmo sem LCD físico.
    assert "lcd_format_pet_frame(&g_shared_pet_state" in setup[end:]
    assert "TaskLcdDisplay," in setup


def test_setup_checks_rtos_primitives_before_creating_tasks():
    setup = _setup_body()
    check = setup.index("if (!g_state_mutex || !g_q_sensor_infer")
    assert check < setup.index("xTaskCreatePinnedToCore(")
    for handle in ("g_q_sensor_tx", "g_q_gesture_pet", "g_q_gesture_tx", "g_q_cmd_pet", "g_q_pet_reply_tx"):
        assert f"!{handle}" in setup[check:setup.index("return;", check)]


def test_iot_network_task_runs_on_the_wifi_core():
    call = IOT[IOT.index("xTaskCreateStaticPinnedToCore(network_task"):]
    call = call[:call.index(")) {")]
    assert "PRO_CPU_NUM" in call and "APP_CPU_NUM" not in call
    # Sensores e inferência continuam no APP_CPU.
    assert MAIN.count("APP_CPU_NUM") >= 5
