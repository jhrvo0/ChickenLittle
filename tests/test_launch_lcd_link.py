"""Contrato de envio do LCD do jogo pelo cabo serial virtual."""

from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.app import TerminalHostClient
from terminal.communication.protocol import AppModeId, CommandType, LcdFramePayload, MessageType, ProtocolCodec
from terminal.communication.transport import create_virtual_serial_pair


def test_launch_frame_reaches_device_and_expires(tmp_path):
    host, device, _ = create_virtual_serial_pair()
    node = SimulatedEsp32Node(device, sensor_source=SensorSimulator(seed=42), save_path=tmp_path / "pet.json")
    client = TerminalHostClient(host)
    node.boot(auto_load=False)
    client.poll_serial()

    client.set_mode(AppModeId.PET_LAUNCH)
    expected = client.lcd_frame
    node.step()
    assert node.last_lcd == expected

    # Sem quadros novos, a tela local do pet volta após 2 segundos simulados.
    for _ in range(50):
        node.step()
    assert node.last_lcd != expected


def test_launch_frames_are_rate_limited_and_only_sent_in_launch(monkeypatch):
    host, device, _ = create_virtual_serial_pair()
    client = TerminalHostClient(host)
    now = [10.0]
    monkeypatch.setattr("terminal.app.time.monotonic", lambda: now[0])
    client.set_mode(AppModeId.PET_LAUNCH)
    codec = ProtocolCodec()
    first = [codec.decode(line) for line in device.read_all_lines()]
    assert [env.type for env in first] == [MessageType.PET_COMMAND, MessageType.LCD_FRAME]
    assert LcdFramePayload.from_dict(first[1].data) == client.lcd_frame

    client.update_game(0.02)
    assert device.read_all_lines() == []
    now[0] += 0.21
    client.update_game(0.02)
    assert [codec.decode(line).type for line in device.read_all_lines()] == [MessageType.LCD_FRAME]
    client.set_mode(AppModeId.MOTION_PET)
    device.read_all_lines()
    now[0] += 1.0
    client.update_game(0.02)
    assert device.read_all_lines() == []


def test_simulator_rejects_unknown_upgrade_and_wrong_price(tmp_path):
    host, device, _ = create_virtual_serial_pair()
    node = SimulatedEsp32Node(device, sensor_source=SensorSimulator(seed=42), save_path=tmp_path / "pet.json")
    node.engine.state.coins = 100
    client = TerminalHostClient(host)
    for upgrade_id, cost in (("SLINGSHOT_PRO", 0), ("UNKNOWN", 15)):
        client.send_command(CommandType.PLAY, {"minigame": "PET_LAUNCH", "action": "UNLOCK_UPGRADE", "upgrade_id": upgrade_id, "cost": cost})
        node.step()
        client.poll_serial()
        assert client.last_error is not None
        assert node.engine.state.coins == 100
        assert node.engine.state.unlocked_upgrades == []
