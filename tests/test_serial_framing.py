"""Regressoes da bancada real: fragmentacao USB e comandos perdidos durante boot."""
import sys
from types import SimpleNamespace

import pytest

from terminal.bench import assistant
from terminal.communication.protocol import MessageType, ProtocolCodec
from terminal.communication.transport import PySerialEndpoint, TransportClosedError


@pytest.fixture
def serial_endpoint(monkeypatch):
    class Port:
        is_open = True

        def __init__(self):
            self.buffer = bytearray()
            self.max_read = 4096

        @property
        def in_waiting(self):
            return len(self.buffer)

        def read(self, size):
            size = min(size, self.max_read)
            result = bytes(self.buffer[:size])
            del self.buffer[:size]
            return result

        def close(self):
            self.is_open = False

    port = Port()
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=lambda **kwargs: port))
    endpoint = PySerialEndpoint("COM_TEST")
    yield endpoint, port
    endpoint.close()


def test_timeout_fragment_is_retained_until_newline(serial_endpoint):
    endpoint, port = serial_endpoint
    line = ProtocolCodec().encode(MessageType.ACK, {"ack_seq": 0, "status": "ok"})
    data = line.encode()
    for byte in data[:-1]:
        port.buffer.append(byte)
        assert endpoint.read_all_lines() == []
    port.buffer.append(data[-1])
    assert endpoint.read_all_lines() == [line]
    assert endpoint.read_all_lines() == []


def test_multiple_messages_and_trailing_fragment_are_preserved(serial_endpoint):
    endpoint, port = serial_endpoint
    codec = ProtocolCodec()
    lines = [codec.encode(MessageType.ACK, {"ack_seq": i}) for i in range(3)]
    port.buffer.extend((lines[0] + lines[1] + lines[2][:12]).encode())
    assert endpoint.read_all_lines() == lines[:2]
    port.buffer.extend(lines[2][12:].encode())
    assert endpoint.read_all_lines() == lines[2:]


def test_utf8_and_crlf_are_decoded_only_after_complete_line(serial_endpoint):
    endpoint, port = serial_endpoint
    data = "mensagem: ação\r\n".encode()
    cut = data.index("ç".encode()) + 1
    port.buffer.extend(data[:cut])
    assert endpoint.read_line() is None
    port.buffer.extend(data[cut:])
    assert endpoint.read_line() == "mensagem: ação\r\n"


def test_short_reads_do_not_split_or_duplicate_messages(serial_endpoint):
    endpoint, port = serial_endpoint
    port.max_read = 3
    port.buffer.extend(b'primeira\nsegunda\n')
    received = []
    for _ in range(10):
        received.extend(endpoint.read_all_lines())
    assert received == ["primeira\n", "segunda\n"]


def test_oversized_unterminated_line_is_bounded_and_next_message_can_recover(serial_endpoint):
    endpoint, port = serial_endpoint
    port.buffer.extend(b'x' * 70000)
    with pytest.raises(RuntimeError, match="64 KiB"):
        for _ in range(20):
            endpoint.read_all_lines()
    port.buffer.clear()
    port.buffer.extend(b'ok\n')
    assert endpoint.read_line() == 'ok\n'


def test_closed_endpoint_does_not_return_buffered_data(serial_endpoint):
    endpoint, port = serial_endpoint
    port.buffer.extend(b'primeira\nsegunda\n')
    assert endpoint.read_line() == 'primeira\n'
    endpoint.close()
    with pytest.raises(TransportClosedError):
        endpoint.read_line()


def test_diag_retries_when_first_commands_are_lost_during_boot(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(assistant.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(assistant.time, "sleep", lambda dt: setattr(clock, "now", clock.now + dt))
    commands = []
    response = ProtocolCodec().encode(MessageType.ACK, {"ack_seq": 0,
        "status": "diag:fw=0.5.0-cycle5,origin=ESP32_HW,per_ms=70,heap=100000"})
    endpoint = SimpleNamespace(
        write_line=commands.append,
        read_all_lines=lambda: [response] if len(commands) >= 3 else [],
    )
    diag = assistant.query_device_diag(endpoint, timeout_sec=2.0)
    assert diag.is_physical_hardware
    assert commands == ["DIAG", "DIAG", "DIAG"]
    assert 1.0 <= clock.now < 2.0


def test_diag_retry_still_expires_without_hardware_response(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(assistant.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(assistant.time, "sleep", lambda dt: setattr(clock, "now", clock.now + dt))
    commands = []
    endpoint = SimpleNamespace(write_line=commands.append, read_all_lines=lambda: [])
    with pytest.raises(TimeoutError):
        assistant.query_device_diag(endpoint, timeout_sec=1.2)
    assert commands == ["DIAG", "DIAG", "DIAG"]
    assert 1.2 <= clock.now < 1.3
