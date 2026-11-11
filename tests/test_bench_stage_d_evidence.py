"""A etapa de LCD distingue quadros recebidos e confirmações do operador."""

from types import SimpleNamespace

import pytest

from terminal.bench import assistant


def _mock_physical_session(monkeypatch, lines):
    diag = SimpleNamespace(sample_period_ms=70, lcd_frames=20, to_dict=lambda: {"lcd_frames": 20})
    stream = SimpleNamespace(
        problems=(), lcd_frames_count=1 if lines else 0, last_lcd_lines=tuple(lines),
        to_dict=lambda: {"lcd_frames_count": 1 if lines else 0},
    )
    monkeypatch.setattr(assistant, "_open_bench_session", lambda *args: (object(), None, "PHYSICAL_ESP32", lambda: None))
    monkeypatch.setattr(assistant, "query_device_diag", lambda *args, **kwargs: diag)
    monkeypatch.setattr(assistant, "inspect_telemetry_stream", lambda *args, **kwargs: stream)


def test_physical_display_requires_received_frame_even_with_operator_confirmations(monkeypatch, tmp_path):
    _mock_physical_session(monkeypatch, [])
    result = assistant.run_stage_d(serial_port="COM1", lcd_interface="parallel", rw_confirmed=True, visual_confirmed=True,
                                   lcd_vdd_v=5.0, log_path=tmp_path / "log.json")
    assert not result.passed
    assert result.details["device_lcd_20x4"] == []
    assert any("Nenhum quadro LCD" in p for p in result.problems)


@pytest.mark.parametrize("rw_confirmed,lcd_vdd_v,visual_confirmed", [
    (False, 5.0, True), (True, None, True), (True, 5.0, False),
])
def test_physical_display_requires_each_operator_confirmation(monkeypatch, tmp_path, rw_confirmed, lcd_vdd_v, visual_confirmed):
    _mock_physical_session(monkeypatch, ["line".ljust(20)] * 4)
    result = assistant.run_stage_d(serial_port="COM1", lcd_interface="parallel", rw_confirmed=rw_confirmed, visual_confirmed=visual_confirmed,
                                   lcd_vdd_v=lcd_vdd_v, log_path=tmp_path / "log.json")
    assert not result.passed
    assert "RW=GND confirmado" not in result.summary


def test_physical_display_passes_with_received_frame_and_explicit_evidence(monkeypatch, tmp_path):
    _mock_physical_session(monkeypatch, ["line".ljust(20)] * 4)
    result = assistant.run_stage_d(serial_port="COM1", lcd_interface="parallel", rw_confirmed=True, visual_confirmed=True,
                                   lcd_vdd_v=5.0, log_path=tmp_path / "log.json")
    assert result.passed
    assert result.details["rw_confirmed_by_operator"]
    assert result.details["visual_confirmed_by_operator"]
    assert result.details["lcd_vdd_v_reported"] == 5.0


@pytest.mark.parametrize("voltage", [float("nan"), float("inf"), 4.74, 5.26])
def test_invalid_or_out_of_range_voltage_cannot_pass_stage_d(tmp_path, voltage):
    result = assistant.run_stage_d(serial_port="COM1", lcd_interface="parallel", lcd_vdd_v=voltage, log_path=tmp_path / "log.json")
    assert not result.passed
    assert result.halted_for_electrical_safety
