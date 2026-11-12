"""Integração HTTP e protocolo; a demonstração é explicitamente identificada."""
import json
import re
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terminal.web.server import MotionPetServer


def eventually(read, predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = read()
        if predicate(value):
            return value
        time.sleep(.025)
    raise AssertionError(f"Condição não atingida: {value}")


class WebClient:
    def __init__(self, server):
        self.server = server
        self.origin = server.origin
        page = urlopen(self.origin + "/", timeout=4).read().decode()
        self.key = re.search(r'name="motionpet-key" content="([^"]+)"', page).group(1)

    def request(self, path, payload=None, headers=None):
        all_headers = {"X-MotionPet-Key": self.key}
        if payload is not None:
            all_headers["Content-Type"] = "application/json"
        all_headers.update(headers or {})
        req = Request(self.origin + path, headers=all_headers, data=json.dumps(payload).encode() if payload is not None else None)
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    def state(self):
        return self.request("/api/state")

    def action(self, **kwargs):
        return self.request("/api/action", kwargs)

    def demo(self):
        self.request("/api/connect", {"port": "DEMO"})
        return eventually(self.state, lambda s: s["connection"]["frames"] >= 3 and s["pet"] is not None)


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    server = MotionPetServer(0, allow_demo=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield WebClient(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_offline_does_not_fabricate_pet_or_sensor_data(web):
    state = web.state()
    assert state["connection"]["status"] == "disconnected"
    assert state["connection"]["origin"] == "NONE"
    assert state["sensors"] is None
    assert state["pet"] is None
    with pytest.raises(HTTPError) as exc:
        web.action(action="feed")
    assert exc.value.code == 400


@pytest.mark.parametrize("headers", [{"X-MotionPet-Key": "wrong"}, {"Origin": "https://external.example"}, {"Host": "external.example"}])
def test_api_rejects_other_origins_and_missing_key(web, headers):
    with pytest.raises(HTTPError) as exc:
        web.request("/api/state", headers=headers)
    assert exc.value.code == 403


def test_demo_requires_explicit_opt_in_and_is_never_labelled_hardware(web):
    assert any(p["device"] == "DEMO" for p in web.request("/api/ports")["ports"])
    state = web.demo()
    assert state["connection"]["origin"] == "DEMO"
    assert state["connection"]["age_ms"] < 2000
    assert state["sensors"] is not None
    assert state["pet"]["stage"] == "EGG"


def test_feed_roundtrip_updates_authoritative_pet_and_save_reload(web):
    initial = web.demo()
    before = initial["pet"]["care_counters"]["feed"]
    web.action(action="feed")
    state = eventually(web.state, lambda s: s["pet"]["care_counters"]["feed"] > before)
    assert state["pet"]["hunger"] < initial["pet"]["hunger"]
    web.action(action="save")
    web.action(action="feed")
    eventually(web.state, lambda s: s["pet"]["care_counters"]["feed"] > state["pet"]["care_counters"]["feed"])
    web.action(action="load")
    loaded = eventually(web.state, lambda s: s["pet"]["care_counters"]["feed"] == state["pet"]["care_counters"]["feed"])
    assert loaded["pet"]["name"] == initial["pet"]["name"]


@pytest.mark.parametrize("command", [{"action": "arbitrary"}, {"action": "mode", "mode": "OTHER"}, {"action": "launch_key", "key": "1"}, {"action": "volume", "value": -1}, {"action": "volume", "value": True}])
def test_invalid_actions_are_not_sent_to_device(web, command):
    with pytest.raises(HTTPError) as exc:
        web.request("/api/action", command)
    assert exc.value.code == 400


def test_launch_reuses_physics_and_sends_reward_commands(web):
    web.demo()
    web.action(action="mode", mode="PET_LAUNCH")
    web.action(action="launch_key", key="enter")
    web.action(action="launch_key", key="enter")
    assert web.state()["launch"]["phase"] == "PREP"
    web.action(action="launch_key", key="space")
    assert web.state()["launch"]["charge_norm"] > 0
    web.action(action="launch_key", key="enter")
    result = eventually(web.state, lambda s: s["launch"]["result"] is not None, timeout=12)
    assert result["launch"]["result"]["distance_m"] > 0
    assert result["launch"]["result"]["score"] > 0
    updated = eventually(web.state, lambda s: s["pet"]["total_launches"] >= 1)
    assert updated["pet"]["coins"] > 0


def test_music_volume_does_not_depend_on_missing_potentiometer_and_slides_start_at_one(web):
    web.demo()
    web.action(action="mode", mode="AIR_MUSIC")
    web.action(action="volume", value=.6)
    assert web.state()["music"]["volume"] == .6
    web.action(action="mode", mode="AIR_SLIDES")
    assert web.state()["slides"]["current"] == 1
    web.action(action="slides_next")
    assert web.state()["slides"]["current"] == 2
    web.action(action="slides_prev")
    assert web.state()["slides"]["current"] == 1
    web.request("/api/disconnect", {})
    off = eventually(web.state, lambda s: s["connection"]["status"] == "disconnected")
    assert off["sensors"] is None


def test_no_demo_port_in_normal_server():
    server = MotionPetServer(0)
    try:
        assert not any(p["device"] == "DEMO" for p in server.session.ports())
        with pytest.raises(ValueError):
            server.session.connect("DEMO")
    finally:
        server.server_close()


def test_sensor_ir_and_distance_control_launch_over_serial(monkeypatch):
    """Endpoint virtual controlado: verifica entradas reais do protocolo, não dados do navegador."""
    from types import SimpleNamespace
    from terminal.web import session as module
    from terminal.communication.protocol import MessageType, ProtocolCodec
    from terminal.communication.transport import create_virtual_serial_pair
    from terminal.pet.state import PetState

    host, device, _ = create_virtual_serial_pair()
    monkeypatch.setattr(module, "list_serial_ports", lambda: [SimpleNamespace(device="TEST", description="Teste isolado")])
    monkeypatch.setattr(module, "PySerialEndpoint", lambda *a, **k: host)
    monkeypatch.setattr(module, "query_device_diag", lambda *a, **k: SimpleNamespace(is_physical_hardware=True))
    s = module.MotionPetSession()
    s.set_experience("legacy")  # regras automáticas sensor→pet só valem na experiência legada
    codec = ProtocolCodec()

    def sample(ir, distance=8):
        before = s.state()["connection"]["frames"]
        device.write_line(codec.encode(MessageType.SENSOR_FRAME, {"distance_cm": distance, "valid_ultrasonic": True, "ir_detected": ir, "pot_norm": 0}))
        return eventually(s.state, lambda state: state["connection"]["frames"] > before)

    try:
        s.connect("TEST")
        eventually(s.state, lambda state: state["connection"]["status"] == "connected")
        device.write_line(codec.encode(MessageType.PET_STATE, PetState().to_dict()))
        sample(False)
        assert s.state()["pet"]["name"] == "Piu-piu"
        sample(True)
        commands = [json.loads(line) for line in device.read_all_lines() if line.startswith("{")]
        assert any(c["type"] == "pet_command" and c["data"]["command"] == "FEED" for c in commands)
        s.action({"action": "mode", "mode": "PET_LAUNCH"})
        sample(False)
        assert sample(True)["launch"]["phase"] == "SELECT_PET"
        sample(False)
        assert sample(True)["launch"]["phase"] == "PREP"
        time.sleep(.27)
        charged = sample(True)
        assert charged["launch"]["phase"] == "CHARGING"
        assert charged["launch"]["angle_deg"] == 70
        launched = sample(False)
        assert launched["launch"]["phase"] in {"LAUNCHING", "FLIGHT"}
        time.sleep(2.05)
        with pytest.raises(ValueError, match="leituras"):
            s.action({"action": "feed"})
    finally:
        s.close()
