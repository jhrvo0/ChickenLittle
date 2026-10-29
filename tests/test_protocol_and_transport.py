"""Testes abrangentes de protocolo JSON Lines v1 e camada de transporte Serial.

Cobre:
- Serialização e desserialização roundtrip de todos os payloads e envelopes.
- Validação estrita de erros e exceções ProtocolError.
- Transporte Serial Virtual (VirtualSerialEndpoint) e criação de par com wire_log.
- Tratamento de endpoint fechado (TransportClosedError).
"""

from __future__ import annotations

import json
from collections import deque
import pytest

from terminal.communication.protocol import (
    PROTOCOL_VERSION,
    AckPayload,
    AppModeId,
    CommandType,
    ErrorPayload,
    GestureEventPayload,
    GestureSource,
    GestureType,
    LcdFramePayload,
    MessageType,
    PetCommandPayload,
    ProtocolCodec,
    ProtocolEnvelope,
    ProtocolError,
    SensorFramePayload,
    now_ms,
)
from terminal.communication.transport import (
    HardwareNotConnectedError,
    PySerialEndpoint,
    TransportClosedError,
    create_virtual_serial_pair,
)
from terminal.pet.state import PetState


# ==============================================================================
# 1. Testes de Payloads Individuais (to_dict / from_dict / validação)
# ==============================================================================


class TestSensorFramePayload:
    """Validação e serialização de quadros de sensores (HC-SR04, TCRT5000, POT)."""

    def test_valid_payload_roundtrip(self) -> None:
        payload = SensorFramePayload(
            distance_cm=23.456,
            ir_detected=True,
            pot_norm=0.75,
            valid_ultrasonic=True,
        )
        data = payload.to_dict()
        assert data == {
            "distance_cm": 23.46,
            "ir_detected": True,
            "pot_norm": 0.75,
            "valid_ultrasonic": True,
        }
        restored = SensorFramePayload.from_dict(data)
        assert restored.distance_cm == 23.46
        assert restored.ir_detected is True
        assert restored.pot_norm == 0.75
        assert restored.valid_ultrasonic is True

    def test_none_distance_for_ultrasonic_timeout(self) -> None:
        payload = SensorFramePayload(
            distance_cm=None,
            ir_detected=False,
            pot_norm=0.0,
            valid_ultrasonic=False,
        )
        data = payload.to_dict()
        assert data["distance_cm"] is None
        assert data["valid_ultrasonic"] is False
        restored = SensorFramePayload.from_dict(data)
        assert restored.distance_cm is None
        assert restored.valid_ultrasonic is False

    @pytest.mark.parametrize("invalid_pot", [-0.01, 1.01, -10.0, 5.0])
    def test_invalid_pot_norm_raises_protocol_error(self, invalid_pot: float) -> None:
        with pytest.raises(ProtocolError, match="pot_norm fora do intervalo"):
            SensorFramePayload(distance_cm=10.0, ir_detected=False, pot_norm=invalid_pot)

    def test_negative_distance_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="distance_cm negativo inválido"):
            SensorFramePayload(distance_cm=-0.1, ir_detected=False, pot_norm=0.5)

    @pytest.mark.parametrize(
        "bad_dict",
        [
            {},
            {"distance_cm": 10.0},
            {"distance_cm": 10.0, "ir_detected": True},  # missing pot_norm
            {"distance_cm": "invalid", "ir_detected": True, "pot_norm": 0.5},
            {"distance_cm": 10.0, "ir_detected": True, "pot_norm": "not_a_float"},
        ],
    )
    def test_from_dict_malformed_raises_protocol_error(self, bad_dict: dict) -> None:
        with pytest.raises(ProtocolError, match="Payload sensor_frame inválido"):
            SensorFramePayload.from_dict(bad_dict)


class TestGestureEventPayload:
    """Validação e serialização de eventos de gestos classificados."""

    @pytest.mark.parametrize("gesture", list(GestureType))
    @pytest.mark.parametrize("source", list(GestureSource))
    def test_roundtrip_all_gestures_and_sources(
        self, gesture: GestureType, source: GestureSource
    ) -> None:
        payload = GestureEventPayload(
            gesture=gesture,
            confidence=0.875,
            source=source,
            window_ms=480,
        )
        data = payload.to_dict()
        assert data["gesture"] == gesture.value
        assert data["confidence"] == 0.875
        assert data["source"] == source.value
        assert data["window_ms"] == 480

        restored = GestureEventPayload.from_dict(data)
        assert restored == payload

    @pytest.mark.parametrize("bad_conf", [-0.1, 1.01, 2.0, -100.0])
    def test_invalid_confidence_raises_protocol_error(self, bad_conf: float) -> None:
        with pytest.raises(ProtocolError, match="confidence fora do intervalo"):
            GestureEventPayload(
                gesture=GestureType.APPROACH,
                confidence=bad_conf,
                source=GestureSource.SIM_KEYBOARD,
            )

    @pytest.mark.parametrize("bad_win", [0, -1, -500])
    def test_invalid_window_ms_raises_protocol_error(self, bad_win: int) -> None:
        with pytest.raises(ProtocolError, match="window_ms deve ser positivo"):
            GestureEventPayload(
                gesture=GestureType.APPROACH,
                confidence=0.9,
                source=GestureSource.SIM_KEYBOARD,
                window_ms=bad_win,
            )

    def test_from_dict_unknown_gesture_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="Payload gesture_event inválido"):
            GestureEventPayload.from_dict(
                {
                    "gesture": "SUPER_PUNCH",
                    "confidence": 0.8,
                    "source": "sim_keyboard",
                }
            )

    def test_from_dict_unknown_source_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="Payload gesture_event inválido"):
            GestureEventPayload.from_dict(
                {
                    "gesture": "APPROACH",
                    "confidence": 0.8,
                    "source": "alien_mind_control",
                }
            )


class TestPetCommandPayload:
    """Validação e serialização de comandos de interação."""

    @pytest.mark.parametrize("cmd", list(CommandType))
    def test_roundtrip_all_commands(self, cmd: CommandType) -> None:
        payload = PetCommandPayload(command=cmd, payload={"sample_arg": 123})
        data = payload.to_dict()
        assert data["command"] == cmd.value
        assert data["payload"] == {"sample_arg": 123}

        restored = PetCommandPayload.from_dict(data)
        assert restored.command == cmd
        assert restored.payload == {"sample_arg": 123}

    def test_from_dict_invalid_command_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="Payload pet_command inválido"):
            PetCommandPayload.from_dict({"command": "FLY_TO_MARS"})

    def test_from_dict_non_dict_payload_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="Campo 'payload' de pet_command deve ser um objeto JSON"):
            PetCommandPayload.from_dict({"command": "FEED", "payload": "not_a_dict"})


class TestLcdFramePayload:
    """Validação estrita do display 20x4 (exatamente 4 linhas de 20 caracteres ASCII 0x20..0x7E)."""

    def test_valid_frame_roundtrip(self) -> None:
        lines = (
            "Pip     EGG L01 HAPY",
            "[o_o]  HG: 25 HP: 80",
            "*IDLE* EN: 85 HL: 95",
            "D:025cm READY       ",
        )
        frame = LcdFramePayload(lines=lines)
        data = frame.to_dict()
        assert data == {"lines": list(lines)}

        restored = LcdFramePayload.from_dict(data)
        assert restored.lines == lines

    def test_invalid_line_count_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="exatamente 4 linhas"):
            LcdFramePayload(lines=("line1" * 4, "line2" * 4, "line3" * 4))  # 3 lines

        with pytest.raises(ProtocolError, match="exatamente 4 linhas"):
            LcdFramePayload(lines=("line1" * 4, "line2" * 4, "line3" * 4, "line4" * 4, "line5" * 4))

    @pytest.mark.parametrize("line_len", [19, 21, 0, 1])
    def test_invalid_line_length_raises_protocol_error(self, line_len: int) -> None:
        bad_line = "A" * line_len
        valid_line = " " * 20
        with pytest.raises(ProtocolError, match="deve ter exatamente 20 caracteres"):
            LcdFramePayload(lines=(bad_line, valid_line, valid_line, valid_line))

    @pytest.mark.parametrize(
        "bad_char",
        [
            "\x19",  # ord < 0x20
            "\x00",
            "\n",
            "\t",
            "\x7F",  # DEL (ord > 0x7E)
            "é",
            "ã",
            "ç",
            "🚀",
        ],
    )
    def test_non_ascii_printable_raises_protocol_error(self, bad_char: str) -> None:
        bad_line = f"Test{bad_char}".ljust(20, " ")[:20]
        valid_line = " " * 20
        with pytest.raises(ProtocolError, match="Caractere não-ASCII imprimível"):
            LcdFramePayload(lines=(bad_line, valid_line, valid_line, valid_line))

    @pytest.mark.parametrize(
        ("bad_payload", "expected_match"),
        [
            ({}, "Payload lcd_frame exige lista"),
            ({"lines": "not_a_list"}, "Payload lcd_frame exige lista"),
            ({"lines": ["1", "2", "3"]}, "Payload lcd_frame exige lista"),
            ({"lines": [" " * 20, " " * 20, " " * 20, 12345]}, "Todas as linhas de lcd_frame devem ser strings"),
        ],
    )
    def test_from_dict_malformed_raises_protocol_error(
        self, bad_payload: dict, expected_match: str
    ) -> None:
        with pytest.raises(ProtocolError, match=expected_match):
            LcdFramePayload.from_dict(bad_payload)


class TestAckAndErrorPayloads:
    """Validação e serialização de ACK e ERROR."""

    def test_ack_roundtrip(self) -> None:
        payload = AckPayload(ack_seq=42, status="ok")
        data = payload.to_dict()
        assert data == {"ack_seq": 42, "status": "ok"}
        restored = AckPayload.from_dict(data)
        assert restored.ack_seq == 42
        assert restored.status == "ok"

    def test_ack_from_dict_malformed(self) -> None:
        with pytest.raises(ProtocolError, match="Payload ack inválido"):
            AckPayload.from_dict({"status": "ok"})

    def test_error_roundtrip(self) -> None:
        payload = ErrorPayload(code="BAD_FRAME", message="Syntax error", ref_seq=10)
        data = payload.to_dict()
        assert data == {
            "code": "BAD_FRAME",
            "message": "Syntax error",
            "ref_seq": 10,
        }
        restored = ErrorPayload.from_dict(data)
        assert restored.code == "BAD_FRAME"
        assert restored.message == "Syntax error"
        assert restored.ref_seq == 10

    def test_error_without_ref_seq(self) -> None:
        payload = ErrorPayload(code="ERR", message="Something bad")
        data = payload.to_dict()
        assert data["ref_seq"] is None
        restored = ErrorPayload.from_dict(data)
        assert restored.ref_seq is None


# ==============================================================================
# 2. Testes de ProtocolEnvelope e ProtocolCodec
# ==============================================================================


class TestProtocolCodec:
    """Codificador/decodificador JSON Lines v1 e validação estrita de envelope."""

    def test_codec_sequential_seq_increment(self) -> None:
        codec = ProtocolCodec(initial_seq=100)
        assert codec.next_seq == 100
        env1 = codec.build_envelope(MessageType.ACK, {"ack_seq": 1})
        assert env1.seq == 100
        assert codec.next_seq == 101
        env2 = codec.build_envelope(MessageType.ACK, {"ack_seq": 2})
        assert env2.seq == 101

    @pytest.mark.parametrize("msg_type", list(MessageType))
    def test_roundtrip_all_message_types(self, msg_type: MessageType) -> None:
        codec = ProtocolCodec(initial_seq=1)
        sample_data = {"test_key": f"value_{msg_type.value}"}
        encoded = codec.encode(msg_type, sample_data, ts_ms=123456)
        assert encoded.endswith("\n")

        decoded = ProtocolCodec.decode(encoded)
        assert decoded.v == PROTOCOL_VERSION
        assert decoded.seq == 1
        assert decoded.type == msg_type
        assert decoded.ts_ms == 123456
        assert decoded.data == sample_data

    def test_roundtrip_pet_state_envelope(self) -> None:
        codec = ProtocolCodec(initial_seq=5)
        state = PetState(name="TestPip", hunger=30.0, happiness=90.0, xp=45)
        encoded = codec.encode(MessageType.PET_STATE, state.to_dict(), ts_ms=5000)

        envelope = ProtocolCodec.decode(encoded)
        assert envelope.type == MessageType.PET_STATE
        restored_state = PetState.from_dict(envelope.data)
        assert restored_state.name == "TestPip"
        assert restored_state.hunger == 30.0
        assert restored_state.happiness == 90.0
        assert restored_state.xp == 45

    def test_decode_empty_or_whitespace_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="Linha JSON vazia recebida"):
            ProtocolCodec.decode("")
        with pytest.raises(ProtocolError, match="Linha JSON vazia recebida"):
            ProtocolCodec.decode("   \n\t  ")

    def test_decode_malformed_json_syntax_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="JSON malformado"):
            ProtocolCodec.decode("{bad:json,")

    def test_decode_root_not_dict_raises_protocol_error(self) -> None:
        with pytest.raises(ProtocolError, match="deve ser um objeto na raiz"):
            ProtocolCodec.decode("[1, 2, 3]\n")
        with pytest.raises(ProtocolError, match="deve ser um objeto na raiz"):
            ProtocolCodec.decode('"just a string"\n')

    @pytest.mark.parametrize("missing_field", ["v", "seq", "type", "ts_ms", "data"])
    def test_missing_mandatory_field_raises_protocol_error(self, missing_field: str) -> None:
        base = {
            "v": PROTOCOL_VERSION,
            "seq": 1,
            "type": "ack",
            "ts_ms": 1000,
            "data": {},
        }
        del base[missing_field]
        with pytest.raises(ProtocolError, match="Campo obrigatório ausente no envelope"):
            ProtocolCodec.decode(json.dumps(base))

    @pytest.mark.parametrize("unsupported_version", [0, 2, 99, -1])
    def test_unsupported_protocol_version_raises_protocol_error(
        self, unsupported_version: int
    ) -> None:
        raw = {
            "v": unsupported_version,
            "seq": 1,
            "type": "ack",
            "ts_ms": 1000,
            "data": {},
        }
        with pytest.raises(ProtocolError, match="Versão de protocolo não suportada"):
            ProtocolCodec.decode(json.dumps(raw))

    @pytest.mark.parametrize("invalid_seq", [-1, "1", 3.14, True, None])
    def test_invalid_seq_raises_protocol_error(self, invalid_seq: object) -> None:
        raw = {
            "v": PROTOCOL_VERSION,
            "seq": invalid_seq,
            "type": "ack",
            "ts_ms": 1000,
            "data": {},
        }
        with pytest.raises(ProtocolError, match="Campo 'seq' inválido"):
            ProtocolCodec.decode(json.dumps(raw))

    @pytest.mark.parametrize("invalid_ts", [-5, "1000", 2.5, False, None])
    def test_invalid_ts_ms_raises_protocol_error(self, invalid_ts: object) -> None:
        raw = {
            "v": PROTOCOL_VERSION,
            "seq": 1,
            "type": "ack",
            "ts_ms": invalid_ts,
            "data": {},
        }
        with pytest.raises(ProtocolError, match="Campo 'ts_ms' inválido"):
            ProtocolCodec.decode(json.dumps(raw))

    def test_invalid_data_type_raises_protocol_error(self) -> None:
        raw = {
            "v": PROTOCOL_VERSION,
            "seq": 1,
            "type": "ack",
            "ts_ms": 1000,
            "data": "not a dict",
        }
        with pytest.raises(ProtocolError, match="Campo 'data' deve ser um objeto JSON"):
            ProtocolCodec.decode(json.dumps(raw))

    def test_unknown_message_type_raises_protocol_error(self) -> None:
        raw = {
            "v": PROTOCOL_VERSION,
            "seq": 1,
            "type": "unknown_broadcast",
            "ts_ms": 1000,
            "data": {},
        }
        with pytest.raises(ProtocolError, match="Tipo de mensagem desconhecido"):
            ProtocolCodec.decode(json.dumps(raw))


# ==============================================================================
# 3. Testes de Camada de Transporte (VirtualSerialEndpoint e PySerialEndpoint)
# ==============================================================================


class TestVirtualSerialTransport:
    """Comunicação bidirecional in-memory entre host e device."""

    def test_virtual_serial_pair_bidirectional_exchange(self) -> None:
        host, device, wire_log = create_virtual_serial_pair(max_wire_log=10)

        assert host.is_open and device.is_open
        assert host.name == "host"
        assert device.name == "device"
        assert host.tx_count == 0 and host.rx_count == 0

        # Host envia comando para device
        host.write_line('{"cmd":"feed"}')
        assert host.tx_count == 1
        assert len(wire_log) == 1
        assert wire_log[0] == ("host", '{"cmd":"feed"}\n')

        # Device lê
        received_at_dev = device.read_line()
        assert received_at_dev == '{"cmd":"feed"}\n'
        assert device.rx_count == 1

        # Device responde com ACK
        device.write_line('{"ack":"ok"}')
        assert device.tx_count == 1
        assert len(wire_log) == 2
        assert wire_log[1] == ("device", '{"ack":"ok"}\n')

        # Host lê resposta
        received_at_host = host.read_line()
        assert received_at_host == '{"ack":"ok"}\n'
        assert host.rx_count == 1

    def test_read_all_lines(self) -> None:
        host, device, _ = create_virtual_serial_pair()

        host.write_line("line1\n")
        host.write_line("line2")
        host.write_line("line3\n")

        lines = device.read_all_lines()
        assert lines == ["line1\n", "line2\n", "line3\n"]
        assert device.rx_count == 3
        # Nova leitura retorna lista vazia
        assert device.read_all_lines() == []
        assert device.read_line() is None

    def test_wire_log_max_capacity(self) -> None:
        host, device, wire_log = create_virtual_serial_pair(max_wire_log=3)
        for i in range(5):
            host.write_line(f"msg_{i}")

        assert len(wire_log) == 3
        assert wire_log[0] == ("host", "msg_2\n")
        assert wire_log[1] == ("host", "msg_3\n")
        assert wire_log[2] == ("host", "msg_4\n")

    def test_operations_on_closed_endpoint_raise_transport_closed_error(self) -> None:
        host, device, _ = create_virtual_serial_pair()

        host.close()
        assert not host.is_open
        assert device.is_open

        with pytest.raises(TransportClosedError, match="está fechado"):
            host.write_line("test")

        with pytest.raises(TransportClosedError, match="está fechado"):
            host.read_line()

        with pytest.raises(TransportClosedError, match="está fechado"):
            host.read_all_lines()

        device.close()
        assert not device.is_open
        with pytest.raises(TransportClosedError, match="está fechado"):
            device.read_line()


class TestPySerialEndpointBehavior:
    """Verifica proteção de porta inválida ou pyserial ausente."""

    def test_pyserial_nonexistent_port_raises_hardware_not_connected_error(self) -> None:
        # Tentar abrir porta física fictícia deve lançar HardwareNotConnectedError
        with pytest.raises(HardwareNotConnectedError):
            PySerialEndpoint(port="COM999_NON_EXISTENT", baudrate=115200, timeout=0.01)
