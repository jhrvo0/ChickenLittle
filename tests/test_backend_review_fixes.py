"""Correções do backend apontadas na revisão: payload ruim, rajadas de sensor, erros da ESP32,
recordes do Pet Launch após LOAD/RESET e fila de ações com prazo."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from terminal import app as app_module
from terminal.app import TerminalHostClient
from terminal.communication.protocol import CommandType, MessageType, ProtocolCodec
from terminal.communication.transport import create_virtual_serial_pair
from terminal.pet.state import PetState
from terminal.web import session as module


def eventually(read, predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = read()
        if predicate(value):
            return value
        time.sleep(.02)
    raise AssertionError(f"Condição não atingida: {value}")


def sensor_line(codec, ir=False, distance=30, **extra):
    data = {"distance_cm": distance, "valid_ultrasonic": True, "ir_detected": ir, "pot_norm": 0, **extra}
    return codec.encode(MessageType.SENSOR_FRAME, data)


def sent_commands(device):
    return [json.loads(line) for line in device.read_all_lines() if line.startswith("{")]


def seq_of(device, command):
    return [c["seq"] for c in sent_commands(device) if c["type"] == "pet_command" and c["data"]["command"] == command][-1]


# ---------------------------------------------------------------- cliente (sem sessão web)

@pytest.fixture
def pair():
    host, device, _ = create_virtual_serial_pair()
    return TerminalHostClient(host), device, ProtocolCodec()


BAD_PAYLOADS = [
    (MessageType.SENSOR_FRAME, {"distance_cm": 10, "ir_detected": False, "pot_norm": 5}),
    (MessageType.SENSOR_FRAME, {"distance_cm": float("nan"), "ir_detected": False, "pot_norm": 0}),
    (MessageType.SENSOR_FRAME, {"ir_detected": False}),
    (MessageType.PET_STATE, {"stage": "NAO_EXISTE"}),
    (MessageType.PET_STATE, {"hunger": "abc"}),
    (MessageType.GESTURE_EVENT, {"gesture": "FLY", "confidence": 1, "source": "tinyml"}),
    (MessageType.LCD_FRAME, {"lines": ["curta"] * 4}),
]


@pytest.mark.parametrize("mtype,data", BAD_PAYLOADS)
def test_invalid_payload_inside_valid_envelope_is_discarded_and_polling_continues(pair, mtype, data):
    client, device, codec = pair
    device.write_line(codec.encode(mtype, data))
    device.write_line(sensor_line(codec, distance=42))
    assert client.poll_serial() == 2  # não levanta: só descarta a mensagem ruim
    assert client.discarded_messages == 1
    assert client.last_discard and client.last_error == client.last_discard
    assert client.last_sensor is not None and client.last_sensor.distance_cm == 42


def test_burst_notifies_every_sensor_frame_in_order(pair):
    client, device, codec = pair
    seen = []
    client.sensor_listener = lambda frame: seen.append(frame.ir_detected)
    for ir in (False, True, False):
        device.write_line(sensor_line(codec, ir=ir))
    client.poll_serial()
    assert seen == [False, True, False]


def test_device_error_is_correlated_with_the_command_and_exposed(pair):
    client, device, codec = pair
    client.send_command(CommandType.SAVE)
    seq = seq_of(device, "SAVE")
    assert client.command_log[seq].status == "sent"
    device.write_line(codec.encode(MessageType.ERROR, {"code": "NVS_SAVE_FAIL", "message": "Failed to save", "ref_seq": seq}))
    client.poll_serial()
    err = client.device_errors[-1]
    assert (err.code, err.ref_seq, err.command) == ("NVS_SAVE_FAIL", seq, "SAVE")
    assert client.command_log[seq].status == "failed"
    assert client.last_error == "NVS_SAVE_FAIL: Failed to save"


def test_ack_confirms_and_unanswered_command_times_out(pair, monkeypatch):
    client, device, codec = pair
    client.send_command(CommandType.FEED)
    client.send_command(CommandType.HEAL)
    sent = sent_commands(device)
    feed, heal = sent[0]["seq"], sent[1]["seq"]
    device.write_line(codec.encode(MessageType.ACK, {"ack_seq": feed, "status": "applied"}))
    client.poll_serial()
    assert client.command_log[feed].status == "confirmed"
    assert client.command_log[heal].status == "sent"
    monkeypatch.setattr(app_module, "COMMAND_ACK_TIMEOUT_S", 0.0)
    time.sleep(.01)
    client.poll_serial()
    assert client.command_log[heal].status == "timeout"
    assert client.command_log[feed].status == "confirmed"


def launch_records(client, distance, score, launches):
    return PetState(best_launch_distance_m=distance, best_launch_score=score, total_launches=launches).to_dict()


@pytest.mark.parametrize("command,ack_status,ack_first", [
    (CommandType.LOAD, "loaded_nvs", True),
    (CommandType.LOAD, "loaded_nvs", False),
    (CommandType.RESET, "applied", True),
    (CommandType.RESET, "applied", False),
])
def test_confirmed_load_or_reset_lowers_local_launch_records(pair, command, ack_status, ack_first):
    client, device, codec = pair
    game = client.pet_launch_mode.game
    device.write_line(codec.encode(MessageType.PET_STATE, launch_records(client, 80.0, 900, 3)))
    client.poll_serial()
    assert (game.best_distance_m, game.best_score) == (80.0, 900)

    client.send_command(command)
    seq = seq_of(device, command.value)
    new = launch_records(client, 20.0, 100, 1) if command == CommandType.LOAD else PetState().to_dict()
    lines = [codec.encode(MessageType.ACK, {"ack_seq": seq, "status": ack_status}),
             codec.encode(MessageType.PET_STATE, new)]
    for line in (lines if ack_first else lines[::-1]):
        device.write_line(line)
    client.poll_serial()
    expected = (20.0, 100) if command == CommandType.LOAD else (0.0, 0)
    assert (game.best_distance_m, game.best_score) == expected
    assert client.pet_launch_mode.best_distance_m == expected[0]


def test_load_without_save_keeps_local_records(pair):
    client, device, codec = pair
    game = client.pet_launch_mode.game
    device.write_line(codec.encode(MessageType.PET_STATE, launch_records(client, 80.0, 900, 3)))
    client.poll_serial()
    client.send_command(CommandType.LOAD)
    seq = seq_of(device, "LOAD")
    device.write_line(codec.encode(MessageType.ACK, {"ack_seq": seq, "status": "no_save_found"}))
    device.write_line(codec.encode(MessageType.PET_STATE, launch_records(client, 80.0, 900, 3)))
    client.poll_serial()
    assert (game.best_distance_m, game.best_score) == (80.0, 900)


# ---------------------------------------------------------------- sessão web

@pytest.fixture
def env(monkeypatch):
    host, device, _ = create_virtual_serial_pair()
    monkeypatch.setattr(module, "list_serial_ports", lambda: [SimpleNamespace(device="TEST", description="Teste isolado")])
    monkeypatch.setattr(module, "PySerialEndpoint", lambda *a, **k: host)
    monkeypatch.setattr(module, "query_device_diag", lambda *a, **k: SimpleNamespace(is_physical_hardware=True))
    s = module.MotionPetSession()
    codec = ProtocolCodec()

    def sample(ir=False, distance=30):
        before = s.state()["connection"]["frames"]
        device.write_line(sensor_line(codec, ir=ir, distance=distance))
        return eventually(s.state, lambda state: state["connection"]["frames"] > before)

    try:
        s.connect("TEST")
        eventually(s.state, lambda state: state["connection"]["status"] == "connected")
        device.write_line(codec.encode(MessageType.PET_STATE, PetState().to_dict()))
        sample(False)
        eventually(s.state, lambda state: state["pet"] is not None)
        # START / IR ON são linhas simples; o SWITCH_MODE inicial é confirmado como faria a ESP32.
        device.write_line(codec.encode(MessageType.ACK, {"ack_seq": seq_of(device, "SWITCH_MODE"), "status": "mode_switched"}))
        eventually(s.state, lambda state: state.get("commands", {}).get("pending", 0) == 0)
        yield SimpleNamespace(s=s, device=device, codec=codec, sample=sample)
    finally:
        s.close()


def test_session_keeps_serial_open_after_invalid_payload(env):
    env.device.write_line(env.codec.encode(MessageType.PET_STATE, {"stage": "NAO_EXISTE"}))
    env.device.write_line(env.codec.encode(MessageType.SENSOR_FRAME, {"distance_cm": 5, "ir_detected": False, "pot_norm": 9}))
    state = env.sample(False)
    assert state["connection"]["status"] == "connected"
    assert state["discarded"]["count"] == 2
    assert state["discarded"]["last"] and state["discarded"]["age_ms"] is not None
    env.s.action({"action": "feed"})  # a serial continua aceitando comandos
    assert seq_of(env.device, "FEED")


def test_session_still_disconnects_on_transport_failure(env):
    env.s._client.endpoint.close()
    state = eventually(env.s.state, lambda st: st["connection"]["status"] == "error")
    assert "interrompida" in state["connection"]["message"]


def test_ir_toggle_inside_one_burst_still_feeds_the_pet(env):
    """false→true→false drenado de uma vez (worker ocupado) é um toque; antes só o último frame valia."""
    before = env.s.state()["connection"]["frames"]
    with env.s._lock:  # impede o worker de drenar até as três linhas estarem na fila
        for ir in (True, False):
            env.device.write_line(sensor_line(env.codec, ir=ir))
    eventually(env.s.state, lambda st: st["connection"]["frames"] >= before + 2)
    feeds = [c for c in sent_commands(env.device) if c["data"].get("command") == "FEED"]
    assert len(feeds) == 1


def test_device_error_and_ack_reach_api_state_and_events(env):
    initial = env.s.state()
    assert initial["device_error"] is None and initial["commands"]["pending"] == 0

    env.s.action({"action": "save"})
    seq = seq_of(env.device, "SAVE")
    state = env.s.state()
    assert state["commands"]["last"]["status"] == "sent" and state["commands"]["pending"] == 1

    env.device.write_line(env.codec.encode(MessageType.ERROR, {"code": "NVS_SAVE_FAIL", "message": "Failed to save state to NVS", "ref_seq": seq}))
    state = eventually(env.s.state, lambda st: st["device_error"] is not None)
    assert state["device_error"]["code"] == "NVS_SAVE_FAIL"
    assert state["device_error"]["command"] == "SAVE" and state["device_error"]["ref_seq"] == seq
    assert isinstance(state["device_error"]["age_ms"], int)
    assert state["device_errors"][0] == state["device_error"]
    assert state["commands"]["last"]["status"] == "failed"
    assert any(e["type"] == "error" and "recusou" in e["text"] for e in state["events"])

    env.s.action({"action": "feed"})
    seq = seq_of(env.device, "FEED")
    env.device.write_line(env.codec.encode(MessageType.ACK, {"ack_seq": seq, "status": "applied"}))
    state = eventually(env.s.state, lambda st: st["commands"]["last"]["status"] == "confirmed")
    assert state["commands"]["last"]["command"] == "FEED" and state["commands"]["pending"] == 0


def test_launch_state_exposes_stable_phase_and_records(env):
    env.s.action({"action": "mode", "mode": "PET_LAUNCH"})
    launch = env.s.state()["launch"]
    assert launch["phase"] == "MENU" and launch["phase"] in launch["phases"]
    assert {"SELECT_PET", "PREP", "CHARGING", "LAUNCHING", "FLIGHT", "RESULT"} <= set(launch["phases"])
    for key in ("angle_deg", "charge_norm", "best_distance_m", "best_score", "matches_completed"):
        assert isinstance(launch[key], (int, float))


# ---------------------------------------------------------------- fila de ações

def test_ticket_expired_in_queue_never_runs():
    ticket = module._ActionTicket({"action": "feed"}, timeout_s=0)
    time.sleep(.01)
    assert ticket.claim() is False
    assert ticket.done.is_set() and ticket.error


def test_action_that_timed_out_is_discarded_not_executed_later(env, monkeypatch):
    monkeypatch.setattr(module, "ACTION_TIMEOUT_S", .3, raising=False)
    gate = threading.Event()
    monkeypatch.setattr(env.s, "_open", lambda port: gate.wait(5))
    env.s._jobs.put(("connect", "TEST", None))  # trava o worker sem segurar o lock
    time.sleep(.1)
    try:
        with pytest.raises(ValueError, match="ocupada"):
            env.s.action({"action": "feed"})
    finally:
        gate.set()
    time.sleep(.4)  # o worker volta e encontra a ação já cancelada
    assert not [c for c in sent_commands(env.device) if c["data"].get("command") == "FEED"]
    assert env.s.state()["commands"]["pending"] == 0


def test_job_queue_is_bounded(env, monkeypatch):
    monkeypatch.setattr(module, "ACTION_TIMEOUT_S", .02, raising=False)
    gate = threading.Event()
    monkeypatch.setattr(env.s, "_open", lambda port: gate.wait(5))
    env.s._jobs.put(("connect", "TEST", None))
    time.sleep(.1)
    try:
        for _ in range(module.MAX_QUEUED_JOBS + 3):
            with pytest.raises(ValueError, match="ocupada"):
                env.s.action({"action": "feed"})
        assert env.s._jobs.qsize() <= module.MAX_QUEUED_JOBS
    finally:
        gate.set()
    time.sleep(.3)
    assert not [c for c in sent_commands(env.device) if c["data"].get("command") == "FEED"]


# ---------------------------------------------------------------- ajustes da revisão do diff

def test_pet_state_before_ack_does_not_restart_a_new_match_twice(pair):
    from terminal.games.pet_launch import LaunchPhase

    client, device, codec = pair
    game = client.pet_launch_mode.game
    device.write_line(codec.encode(MessageType.PET_STATE, launch_records(client, 80.0, 900, 3)))
    client.poll_serial()
    client.send_command(CommandType.LOAD)
    seq = seq_of(device, "LOAD")
    loaded = launch_records(client, 20.0, 100, 1)
    device.write_line(codec.encode(MessageType.PET_STATE, loaded))   # estado antes do ACK
    device.write_line(codec.encode(MessageType.ACK, {"ack_seq": seq, "status": "loaded"}))
    client.poll_serial()
    assert (game.best_distance_m, game.best_score) == (20.0, 100)

    game.phase = LaunchPhase.PREP  # o usuário começa uma partida nova
    device.write_line(codec.encode(MessageType.PET_STATE, loaded))   # pet_state periódico
    client.poll_serial()
    assert game.phase == LaunchPhase.PREP
    assert (game.best_distance_m, game.best_score) == (20.0, 100)


def test_full_command_log_never_drops_a_pending_command_silently(pair):
    client, device, codec = pair
    seen = []
    client.command_listener = seen.append
    for _ in range(app_module._MAX_TRACKED_COMMANDS + 1):
        client.send_command(CommandType.FEED)
    seqs = [c["seq"] for c in sent_commands(device)]
    first = seen[0]
    assert first.seq == seqs[0] and first.status == "timeout" and "cheia" in first.detail
    device.write_line(codec.encode(MessageType.ACK, {"ack_seq": seqs[1], "status": "ok"}))
    client.poll_serial()
    assert client.command_log[seqs[1]].status == "confirmed"
    client.send_command(CommandType.FEED)   # agora há um resolvido: ele sai antes dos pendentes
    assert seqs[2] in client.command_log and seqs[1] not in client.command_log


def test_ticket_is_not_claimed_while_the_session_lock_is_busy(env, monkeypatch):
    monkeypatch.setattr(module, "ACTION_TIMEOUT_S", .3, raising=False)
    sent_commands(env.device)  # descarta o que já foi enviado
    with env.s._lock:  # simula o worker esperando o lock (ex.: escrita serial lenta)
        with pytest.raises(ValueError, match="cancelado"):
            env.s.action({"action": "feed"})
    time.sleep(.3)
    assert not [c for c in sent_commands(env.device) if c["data"].get("command") == "FEED"]
