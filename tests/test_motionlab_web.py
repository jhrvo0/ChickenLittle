"""Rotas HTTP do MotionLab: arquivos servidos, /api/live, /api/lab, experiência legada e segurança."""
import json
import re
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terminal.motionlab.actions import RecordingKeySender
from terminal.motionlab.engine import MotionEngine
from terminal.motionlab.profiles import ProfileStore
from terminal.web.server import MotionPetServer
from tests.test_web_app import WebClient, eventually


@pytest.fixture
def lab_web(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    server = MotionPetServer(0, allow_demo=True)
    sender = RecordingKeySender()
    server.session.engine.key_sender = sender
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = WebClient(server)
        client.sender = sender
        yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def lab(client, **payload):
    return client.request("/api/lab", payload)


def test_new_ui_and_legacy_ui_are_served_with_the_local_key(lab_web):
    page = urlopen(lab_web.origin + "/", timeout=4).read().decode()
    assert "MotionLab" in page and 'name="motionpet-key"' in page
    for path in ("/lab.js", "/lab.css", "/canvas.js", "/music.js", "/intel.js", "/legacy/app.js", "/legacy/app.css"):
        assert urlopen(lab_web.origin + path, timeout=4).status == 200
    legacy = urlopen(lab_web.origin + "/legacy/", timeout=4).read().decode()
    assert "MotionPet" in legacy and re.search(r'name="motionpet-key" content="[^"]+"', legacy)
    with pytest.raises(HTTPError) as err:
        urlopen(lab_web.origin + "/../pyproject.toml", timeout=4)
    assert err.value.code in (403, 404)


def test_live_and_lab_require_the_local_key(lab_web):
    for path in ("/api/live", "/api/lab"):
        with pytest.raises(HTTPError) as err:
            urlopen(Request(lab_web.origin + path), timeout=4)
        assert err.value.code == 403


def test_live_without_device_reports_nothing_invented(lab_web):
    live = lab_web.request("/api/live?f=0&e=0")
    assert live["frames"] == [] and live["signal"]["filtered_cm"] is None and live["age_ms"] is None
    assert live["armed"] is False and live["connection"]["status"] == "disconnected"
    with pytest.raises(HTTPError) as err:
        lab(lab_web, cmd="arm", value=True)
    assert err.value.code == 400  # não arma sem leituras


def test_demo_stream_reaches_live_feed_with_cursor_and_is_labelled(lab_web):
    lab_web.request("/api/connect", {"port": "DEMO"})
    live = eventually(lambda: lab_web.request("/api/live?f=0&e=0"), lambda s: len(s["frames"]) >= 5)
    assert live["origin"] == "DEMO" and live["connection"]["origin"] == "DEMO"
    cursor = live["frame_seq"]
    later = eventually(lambda: lab_web.request(f"/api/live?f={cursor}&e=0"), lambda s: s["frames"])
    assert all(f["seq"] > cursor for f in later["frames"])
    state = lab(lab_web, cmd="module", module="slides")["lab"]
    device = next(r for r in state["recognizers"] if r["source"] == "device")
    assert device["label"] == "Detector do simulador"  # nunca rotulado como TinyML na demonstração


def test_demo_gestures_drive_slides_only_when_armed(lab_web):
    lab_web.request("/api/connect", {"port": "DEMO"})
    eventually(lambda: lab_web.request("/api/live"), lambda s: s["connection"]["live"])
    lab(lab_web, cmd="module", module="slides")
    lab(lab_web, cmd="arm", value=True)
    # o roteiro da demonstração faz aproximação/afastamento: regras disparam e o deck recebe ações
    live = eventually(lambda: lab_web.request("/api/live?f=0&e=0"),
                      lambda s: any(e["status"] == "dispatched" and e["action"].startswith("slides.") for e in s["events"] if e["action"]),
                      timeout=12)
    assert live["armed"] is True
    lab_web.request("/api/disconnect", {})
    after = eventually(lambda: lab_web.request("/api/live"), lambda s: s["connection"]["status"] == "disconnected")
    assert after["armed"] is False


def test_lab_settings_profiles_and_external_switch_over_http(lab_web):
    state = lab(lab_web, cmd="settings", changes={"cooldown_ms": 1500, "driver": "ml"})["lab"]
    assert state["store"]["settings"]["cooldown_ms"] == 1500 and state["store"]["settings"]["driver"] == "ml"
    with pytest.raises(HTTPError):
        lab(lab_web, cmd="settings", changes={"cooldown_ms": 10})
    with pytest.raises(HTTPError):
        lab(lab_web, cmd="profile_save", profile={"id": "x", "name": "X", "context": "control", "bindings": {"HOLD": "powershell"}})
    lab(lab_web, cmd="profile_save", profile={"id": "meu", "name": "Meu", "context": "control", "bindings": {"HOLD": "media.mute"}})
    state = lab(lab_web, cmd="profile_activate", context="control", id="meu")["lab"]
    assert state["store"]["active"]["control"] == "meu"
    with pytest.raises(HTTPError):
        lab(lab_web, cmd="test_action", action="media.mute")  # chave externa desligada
    lab(lab_web, cmd="external", value=True)
    lab(lab_web, cmd="module", module="control")
    lab(lab_web, cmd="test_action", action="media.mute")
    assert lab_web.sender.sent == [(0xAD, True)]
    saved = json.loads(open("data/motionlab/settings.json", encoding="utf-8").read())
    assert saved["active"]["control"] == "meu" and "external_enabled" not in json.dumps(saved)


def test_experience_switch_controls_legacy_sensor_rules(lab_web):
    assert lab_web.state()["experience"] == "lab"
    lab_web.request("/api/experience", {"value": "legacy"})
    assert lab_web.state()["experience"] == "legacy"
    with pytest.raises(HTTPError):
        lab_web.request("/api/experience", {"value": "root"})


def test_evaluate_without_real_sessions_is_pending_and_synthetic_is_flagged(lab_web, tmp_path):
    result = lab(lab_web, cmd="evaluate")["lab"]["evaluation"]
    assert result["real"]["status"] == "pending"
    assert result["synthetic"] is None or result["synthetic"]["is_synthetic"] is True


def test_engine_is_injectable_for_offline_tests(tmp_path):
    engine = MotionEngine(store=ProfileStore(None), key_sender=RecordingKeySender(), recognizers={}, data_root=tmp_path)
    assert engine.snapshot()["store"]["settings"]["driver"] == "rules"
