"""A bancada física só aprova canais que responderam ao estímulo."""
from dataclasses import dataclass

import pytest

from terminal.bench import assistant


@dataclass
class FakeStream:
    problems: tuple = ()
    sensor_frames_count: int = 20
    ir_true_count: int = 0
    ir_false_count: int = 20
    ir_transitions: int = 0
    pot_min: float = 0.5
    pot_max: float = 0.5
    pot_span: float = 0.0

    def to_dict(self):
        return self.__dict__.copy()


class FakeEndpoint:
    def write_line(self, line):
        pass

    def read_all_lines(self):
        return []


@pytest.fixture
def fake_session(monkeypatch):
    stream = FakeStream()
    monkeypatch.setattr(assistant, "_open_bench_session", lambda *args: (FakeEndpoint(), None, "PHYSICAL_ESP32", lambda: None))
    monkeypatch.setattr(assistant, "inspect_telemetry_stream", lambda *args, **kwargs: stream)
    return stream


def test_stage_c_requires_a_real_supply_measurement(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "_open_bench_session", lambda *args: pytest.fail("A porta não deve ser aberta sem medição"))
    result = assistant.run_stage_c(serial_port="COM99", log_path=tmp_path / "log.json")
    assert not result.passed
    assert result.halted_for_electrical_safety
    assert "--vcc-measured-v" in result.summary


def test_stage_c_rejects_constant_ir_but_accepts_both_states(fake_session, tmp_path):
    opts = dict(serial_port="COM99", component="ir", vcc_measured_v=3.3, log_path=tmp_path / "log.json")
    result = assistant.run_stage_c(**opts)
    assert not result.passed
    assert any("transicao" in problem for problem in result.problems)
    fake_session.ir_true_count = 10
    fake_session.ir_false_count = 10
    fake_session.ir_transitions = 1
    assert assistant.run_stage_c(**opts).passed


def test_stage_c_rejects_fixed_pot_value_when_channel_disabled(fake_session, tmp_path):
    opts = dict(serial_port="COM99", component="pot", vcc_measured_v=3.3, log_path=tmp_path / "log.json")
    result = assistant.run_stage_c(**opts)
    assert not result.passed
    assert any("desativado" in problem for problem in result.problems)
    fake_session.pot_min, fake_session.pot_max, fake_session.pot_span = 0.2, 0.8, 0.6
    assert assistant.run_stage_c(**opts).passed


@pytest.mark.parametrize("voltage", [float("nan"), float("inf"), 5.0])
def test_stage_c_rejects_unsafe_or_nonfinite_measurement(voltage, tmp_path):
    result = assistant.run_stage_c(serial_port="COM99", vcc_measured_v=voltage, log_path=tmp_path / "log.json")
    assert not result.passed
    assert result.halted_for_electrical_safety
