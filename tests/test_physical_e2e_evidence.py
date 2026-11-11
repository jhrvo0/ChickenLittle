"""A sessão física deve separar observações de critérios realmente verificados."""

import json

import pytest

from terminal.bench import e2e
from terminal.communication.protocol import GestureEventPayload, GestureSource, GestureType, LcdFramePayload, MessageType, ProtocolCodec


def test_physical_report_does_not_infer_validation_from_messages_or_game(tmp_path, monkeypatch):
    codec = ProtocolCodec()
    lines = [
        codec.encode(MessageType.GESTURE_EVENT, GestureEventPayload(kind, 0.9, GestureSource.TINYML).to_dict(), ts_ms=1000 + i * 500)
        for i, kind in enumerate((GestureType.HOLD, GestureType.APPROACH, GestureType.RETREAT))
    ]
    lines.append(codec.encode(MessageType.LCD_FRAME, LcdFramePayload((" " * 20,) * 4).to_dict(), ts_ms=3000))

    class Endpoint:
        def __init__(self, **kwargs):
            self.lines = lines

        def write_line(self, line):
            pass

        def read_all_lines(self):
            result, self.lines = self.lines, []
            return result

        def close(self):
            pass

    class FinishedHostGame:
        def __init__(self, **kwargs):
            self.matches_completed = 1
            self.best_distance_m = 10.0

        def update(self, *args):
            pass

        def handle_gesture(self, *args):
            pass

    # Advance the clock so the test needs neither hardware nor a real wait.
    ticks = iter(range(100))
    monkeypatch.setattr(e2e.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(e2e.time, "sleep", lambda _: None)
    monkeypatch.setattr(e2e, "PySerialEndpoint", Endpoint)
    monkeypatch.setattr(e2e, "PetLaunchGame", FinishedHostGame)

    path = tmp_path / "report.json"
    report = e2e.run_pet_launch_e2e_validation(serial_port="COM_TEST", simulate=False, report_path=path)

    assert report.validation_origin == "PHYSICAL_ESP32"
    assert report.matches_completed == 1
    assert report.observations["gestures_received"] == ["APPROACH", "HOLD", "RETREAT"]
    assert report.observations["valid_lcd_frame_received"] is True
    assert not report.all_passed
    assert all(value is None for value in report.checks.values())
    assert report.lcd_terminal_synced is None
    assert report.persistence_verified is None
    assert report.involuntary_noise_rejected is None
    assert report.duplicate_events_blocked is None
    assert report.mean_e2e_latency_ms is None
    assert report.mean_processing_ms is not None
    assert report.coins_after_match is None
    assert report.xp_after_match is None
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["checks"]["progress_persistence"] is None
    assert written["mean_e2e_latency_ms"] is None


def test_physical_request_without_port_does_not_silently_simulate(tmp_path):
    with pytest.raises(ValueError, match="porta serial"):
        e2e.run_pet_launch_e2e_validation(simulate=False, report_path=tmp_path / "report.json")
