"""MotionLab: canais contínuo/discreto, portão de segurança, perfis, ações externas, coleta e avaliação."""
import json

import pytest

from terminal.communication.protocol import GestureEventPayload, GestureSource, GestureType, SensorFramePayload
from terminal.motionlab.actions import CATALOG, ExternalRateLimiter, RecordingKeySender
from terminal.motionlab.dataset import GuidedRecorder, evaluate_real_sessions
from terminal.motionlab.engine import MotionEngine
from terminal.motionlab.profiles import ProfileStore
from terminal.motionlab.recognizers import HostRecognizer, build_host_recognizers, rule_bundle
from terminal.motionlab.signals import IrTracker, SignalTracker


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def frame(d=20.0, ir=False, valid=True):
    return SensorFramePayload(d if valid else None, ir, 0.5, valid)


def make_engine(tmp_path, **kw):
    clock = Clock()
    sender = RecordingKeySender()
    store = ProfileStore(tmp_path / "settings.json")
    recognizers = kw.pop("recognizers", {"rules": HostRecognizer("rules", rule_bundle(), label="Regras", kind="rules", origin="deterministic")})
    engine = MotionEngine(store=store, key_sender=sender, recognizers=recognizers, data_root=tmp_path / "raw", clock=clock, **kw)
    engine.reset("ESP32_HW")
    return engine, clock, sender


def feed(engine, clock, values, ts0=0, ir=False):
    ts = ts0
    for d in values:
        ts += 70
        clock.t += 0.07
        engine.on_frame(frame(d, ir=ir), ts)
    return ts


def device_event(gesture, conf=0.95):
    return GestureEventPayload(GestureType(gesture), conf, GestureSource.TINYML)


# ---------------------------------------------------------------- canais
def test_signal_tracker_normalizes_and_holds_last_valid_briefly():
    s = SignalTracker(near_cm=5, far_cm=45)
    snap = s.push(25.0, True, 0)
    assert snap.position == pytest.approx(0.5) and snap.present
    assert s.push(None, False, 100).filtered_cm == pytest.approx(25.0)  # mantém por até 300 ms
    gone = s.push(None, False, 500)
    assert gone.filtered_cm is None and gone.position is None and not gone.present
    assert s.push(80.0, True, 600).present is False  # longe demais: fora da zona ativa


def test_ir_tracker_tap_hold_and_initial_state_is_not_a_tap():
    ir = IrTracker(tap_max_ms=600, hold_ms=900)
    assert ir.push(True, 0) == []          # cartão já presente ao conectar
    assert ir.push(False, 70) == ["IR_OFF"]  # não vira toque
    assert ir.push(True, 140) == ["IR_ON"]
    assert ir.push(False, 280) == ["IR_OFF", "IR_TAP"]
    ir.push(True, 300)
    assert ir.push(True, 1250) == ["IR_HOLD"]
    assert ir.push(True, 1400) == []       # dispara uma vez por toque
    assert ir.push(False, 1500) == ["IR_OFF"]


# ---------------------------------------------------------------- portão
def test_gestures_do_nothing_while_disarmed_and_disconnect_disarms(tmp_path):
    engine, clock, sender = make_engine(tmp_path)
    engine.set_module("canvas")
    feed(engine, clock, [20.0] * 3)
    engine.on_frame(frame(20, ir=True), 400); clock.t += .07
    engine.on_frame(frame(20, ir=False), 470)
    tap = [e for e in engine.events if e["gesture"] == "IR_TAP"][-1]
    assert tap["status"] == "rejected" and tap["reason"] == "disarmed"
    engine.set_armed(True)
    engine.reset("NONE")
    assert engine.armed is False and engine.external_enabled is False


def test_ir_tap_dispatches_internal_action_of_active_module(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.set_module("canvas")
    engine.set_armed(True)
    ts = feed(engine, clock, [20.0] * 3)
    engine.on_frame(frame(20, ir=True), ts + 70); clock.t += .07
    engine.on_frame(frame(20, ir=False), ts + 140)
    tap = [e for e in engine.events if e["gesture"] == "IR_TAP"][-1]
    assert tap["status"] == "dispatched" and tap["action"] == "canvas.next_style" and tap["context"] == "canvas"
    live = engine.live(0, 0)
    assert any(e["action"] == "canvas.next_style" for e in live["events"])
    assert live["frames"][-1]["ir"] is False and live["signal"]["present"] is True


def test_driver_selects_which_recognizer_controls_the_modules(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.set_module("slides")
    engine.set_armed(True)
    feed(engine, clock, [20.0] * 2)
    engine.on_device_gesture(device_event("APPROACH"), 300)
    assert engine.events[-1]["status"] == "observed"  # driver = regras: TinyML só é observado
    engine.update_settings({"driver": "device"})
    clock.t += 2
    feed(engine, clock, [20.0])
    engine.on_device_gesture(device_event("APPROACH"), 400)
    e = engine.events[-1]
    assert e["source"] == "device" and e["status"] == "dispatched" and e["action"] == "slides.next"


def test_confidence_cooldown_repeat_lock_and_zone(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.set_module("slides")
    engine.set_armed(True)
    engine.update_settings({"driver": "device", "min_confidence": 0.8, "cooldown_ms": 900})
    feed(engine, clock, [20.0] * 2)
    engine.on_device_gesture(device_event("APPROACH", 0.7), 1)
    assert engine.events[-1]["reason"] == "low_confidence"
    engine.on_device_gesture(device_event("APPROACH", 0.9), 2)
    assert engine.events[-1]["status"] == "dispatched"
    engine.on_device_gesture(device_event("RETREAT", 0.9), 3)
    assert engine.events[-1]["reason"] == "cooldown"
    clock.t += 1.0
    feed(engine, clock, [20.0])
    engine.on_device_gesture(device_event("APPROACH", 0.9), 4)
    assert engine.events[-1]["reason"] == "repeat_lock"
    engine.on_device_gesture(device_event("RETREAT", 0.9), 5)
    assert engine.events[-1]["status"] == "dispatched"
    # mão fora da zona ativa por mais de 1,2 s
    clock.t += 1.0
    feed(engine, clock, [90.0] * 25)
    engine.on_device_gesture(device_event("APPROACH", 0.95), 6)
    assert engine.events[-1]["reason"] == "out_of_zone"


def test_stale_signal_blocks_actions(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.set_module("slides")
    engine.set_armed(True)
    engine.update_settings({"driver": "device"})
    feed(engine, clock, [20.0])
    clock.t += 1.5
    engine.on_device_gesture(device_event("APPROACH"), 9)
    assert engine.events[-1]["reason"] == "stale_signal"


def test_external_actions_need_switch_allowlist_and_rate_limit(tmp_path):
    engine, clock, sender = make_engine(tmp_path)
    engine.set_module("control")
    engine.store.activate("control", "presenter")
    engine.set_armed(True)
    engine.update_settings({"driver": "device", "cooldown_ms": 200})
    feed(engine, clock, [20.0])
    engine.on_device_gesture(device_event("APPROACH"), 1)
    assert engine.events[-1]["reason"] == "external_disabled" and sender.sent == []
    engine.set_external(True)
    engine.on_device_gesture(device_event("APPROACH"), 2)
    assert engine.events[-1]["status"] == "executed"
    assert sender.sent == [(CATALOG["present.next"].vk, True)]
    with pytest.raises(ValueError):
        engine.test_action("cmd.exe /c calc")
    limiter = ExternalRateLimiter(clock)
    assert limiter.allow() and not limiter.allow()  # intervalo mínimo de 350 ms
    for _ in range(10):
        clock.t += 0.4
        limiter.allow()
    clock.t += 0.4
    assert limiter.allow() is False  # no máximo 8 em 10 s


def test_ir_hold_can_arm_and_disarm_hands_free(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.set_module("control")
    ts = feed(engine, clock, [20.0])
    for i in range(16):
        clock.t += .07
        engine.on_frame(frame(20, ir=True), ts + 70 * (i + 1))
    assert engine.armed is True
    entry = [e for e in engine.events if e["gesture"] == "IR_HOLD"][-1]
    assert entry["action"] == "lab.toggle_armed" and entry["detail"] == "armed"


# ---------------------------------------------------------------- perfis
def test_profiles_validate_actions_and_contexts_and_survive_corruption(tmp_path):
    path = tmp_path / "settings.json"
    store = ProfileStore(path)
    with pytest.raises(ValueError):
        store.upsert_profile({"id": "x", "name": "X", "context": "canvas", "bindings": {"APPROACH": "media.next"}})
    with pytest.raises(ValueError):
        store.upsert_profile({"id": "x", "name": "X", "context": "control", "bindings": {"APPROACH": "shell.run"}})
    store.upsert_profile({"id": "meu", "name": "Meu", "context": "control", "bindings": {"HOLD": "media.mute"}})
    store.activate("control", "meu")
    store.update_settings({"cooldown_ms": 1200})
    again = ProfileStore(path)
    assert again.active["control"] == "meu" and again.settings["cooldown_ms"] == 1200
    with pytest.raises(ValueError):
        again.delete_profile("media")
    path.write_text("{corrompido", encoding="utf-8")
    broken = ProfileStore(path)
    assert broken.load_error and broken.settings["driver"] == "rules"
    with pytest.raises(ValueError):
        broken.update_settings({"near_cm": 30, "far_cm": 20})


# ---------------------------------------------------------------- reconhecedores
def test_rules_and_ml_run_side_by_side_on_the_same_frames(tmp_path):
    recognizers = build_host_recognizers()
    engine, clock, _ = make_engine(tmp_path, recognizers=recognizers)
    # aproximação clara: 50 → 8 cm, depois parado
    feed(engine, clock, [60.0] * 12 + [50 - 4 * i for i in range(11)] + [8.0] * 10)
    sources = {e["source"] for e in engine.events if e["gesture"] in ("APPROACH", "RETREAT", "HOLD")}
    assert "rules" in sources
    rules = next(r for r in engine.snapshot()["recognizers"] if r["source"] == "rules")
    assert rules["windows"] > 0 and rules["latency"]["mean_ms"] is not None
    assert rules["confidence_meaning"].startswith("n/a")
    ml = next(r for r in engine.snapshot()["recognizers"] if r["source"] == "ml")
    if ml["available"]:
        assert ml["origin"] == "synthetic" and ml["windows"] > 0
    else:
        assert ml["error"]


# ---------------------------------------------------------------- coleta e avaliação
def test_guided_recording_writes_real_only_for_hardware_and_evaluates(tmp_path):
    rec = GuidedRecorder(tmp_path)
    with pytest.raises(ValueError):
        rec.start("../x", "ESP32_HW")
    with pytest.raises(ValueError):
        rec.start("p01", "NONE")
    rec.start("p01", "DEMO", repeats=1)
    ts = 0
    while rec.active:
        ts += 70
        rec.on_frame(frame(30.0), ts)
    assert rec.last_result["origin"] == "demo" and "real" not in rec.last_result["path"]
    assert evaluate_real_sessions({"rules": HostRecognizer("rules", rule_bundle(), label="R", kind="rules", origin="d")}, tmp_path)["status"] == "pending"

    rec.start("p01", "ESP32_HW", repeats=1)
    profile = {"NEUTRAL": lambda i: 70.0, "APPROACH": lambda i: 45 - 2.5 * i, "RETREAT": lambda i: 8 + 2.5 * i, "HOLD": lambda i: 15.0}
    counters = {}
    while rec.active:
        ts += 70
        label = rec.status()["label"]
        counters[label] = counters.get(label, 0) + 1
        rec.on_frame(frame(profile[label](counters[label] % 16)), ts)
        if rec.status().get("label") != label:
            counters[label] = 0
    result = rec.last_result
    assert result["ok"] and result["origin"] == "real"
    lines = [json.loads(x) for x in open(result["path"], encoding="utf-8")]
    assert lines[0]["data_origin"] == "real_hardware" and {x["label"] for x in lines} == {"NEUTRAL", "APPROACH", "RETREAT", "HOLD"}
    evaluation = evaluate_real_sessions({"rules": HostRecognizer("rules", rule_bundle(), label="R", kind="rules", origin="d")}, tmp_path)
    assert evaluation["status"] == "evaluated_on_real_data" and evaluation["caveat"]
    rules = evaluation["results"]["rules"]
    assert rules["windows"] > 0 and 0 <= rules["f1_macro"] <= 1 and len(rules["confusion_matrix"]) == 4


def test_recording_is_aborted_when_connection_changes(tmp_path):
    engine, clock, _ = make_engine(tmp_path)
    engine.recorder.start("p02", "ESP32_HW", repeats=1)
    feed(engine, clock, [30.0] * 5)
    engine.reset("NONE")
    assert engine.recorder.active is False and engine.recorder.last_result["ok"] is False
