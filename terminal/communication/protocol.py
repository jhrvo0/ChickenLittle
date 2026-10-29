"""Protocolo JSON Lines v1 para comunicação entre ESP32 (ou Simulador) e Terminal."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """Erro de validação, versão ou formatação no protocolo JSON Lines."""


class MessageType(str, Enum):
    SENSOR_FRAME = "sensor_frame"
    GESTURE_EVENT = "gesture_event"
    PET_COMMAND = "pet_command"
    PET_STATE = "pet_state"
    LCD_FRAME = "lcd_frame"
    ACK = "ack"
    ERROR = "error"


class GestureType(str, Enum):
    APPROACH = "APPROACH"
    RETREAT = "RETREAT"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"
    # Gestos candidatos para investigação experimental posterior
    IMPULSE = "IMPULSE"
    DOUBLE = "DOUBLE"


class GestureSource(str, Enum):
    SIM_KEYBOARD = "sim_keyboard"
    SIM_SENSOR = "sim_sensor"
    RULE_BASELINE = "rule_baseline"
    TINYML = "tinyml"


class CommandType(str, Enum):
    FEED = "FEED"
    PLAY = "PLAY"
    REST = "REST"
    HEAL = "HEAL"
    INTERACT = "INTERACT"
    SAVE = "SAVE"
    LOAD = "LOAD"
    RESET = "RESET"
    SWITCH_MODE = "SWITCH_MODE"
    TICK = "TICK"


class AppModeId(str, Enum):
    MOTION_PET = "MOTION_PET"
    PET_LAUNCH = "PET_LAUNCH"
    AIR_MUSIC = "AIR_MUSIC"
    AIR_SLIDES = "AIR_SLIDES"


def now_ms() -> int:
    """Retorna timestamp monotônico em milissegundos."""
    return int(time.monotonic() * 1000)


@dataclass(frozen=True)
class SensorFramePayload:
    distance_cm: float | None
    ir_detected: bool
    pot_norm: float
    valid_ultrasonic: bool = True

    def __post_init__(self) -> None:
        if not (0.0 <= self.pot_norm <= 1.0):
            raise ProtocolError(f"pot_norm fora do intervalo [0.0, 1.0]: {self.pot_norm}")
        if self.distance_cm is not None and self.distance_cm < 0.0:
            raise ProtocolError(f"distance_cm negativo inválido: {self.distance_cm}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "distance_cm": round(self.distance_cm, 2) if self.distance_cm is not None else None,
            "ir_detected": bool(self.ir_detected),
            "pot_norm": round(float(self.pot_norm), 4),
            "valid_ultrasonic": bool(self.valid_ultrasonic),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SensorFramePayload:
        try:
            dist = data.get("distance_cm")
            return cls(
                distance_cm=float(dist) if dist is not None else None,
                ir_detected=bool(data["ir_detected"]),
                pot_norm=float(data["pot_norm"]),
                valid_ultrasonic=bool(data.get("valid_ultrasonic", dist is not None)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Payload sensor_frame inválido: {exc}") from exc


@dataclass(frozen=True)
class GestureEventPayload:
    gesture: GestureType
    confidence: float
    source: GestureSource
    window_ms: int = 600

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ProtocolError(f"confidence fora do intervalo [0.0, 1.0]: {self.confidence}")
        if self.window_ms <= 0:
            raise ProtocolError(f"window_ms deve ser positivo: {self.window_ms}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gesture": self.gesture.value,
            "confidence": round(float(self.confidence), 4),
            "source": self.source.value,
            "window_ms": int(self.window_ms),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GestureEventPayload:
        try:
            return cls(
                gesture=GestureType(data["gesture"]),
                confidence=float(data["confidence"]),
                source=GestureSource(data["source"]),
                window_ms=int(data.get("window_ms", 600)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Payload gesture_event inválido: {exc}") from exc


@dataclass(frozen=True)
class PetCommandPayload:
    command: CommandType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command.value,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PetCommandPayload:
        try:
            raw_payload = data.get("payload", {})
            if not isinstance(raw_payload, dict):
                raise ProtocolError("Campo 'payload' de pet_command deve ser um objeto JSON")
            return cls(
                command=CommandType(data["command"]),
                payload=dict(raw_payload),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Payload pet_command inválido: {exc}") from exc


@dataclass(frozen=True)
class LcdFramePayload:
    lines: tuple[str, str, str, str]

    def __post_init__(self) -> None:
        if len(self.lines) != 4:
            raise ProtocolError(f"LCD 20x4 exige exatamente 4 linhas, recebeu {len(self.lines)}")
        for idx, line in enumerate(self.lines):
            if len(line) != 20:
                raise ProtocolError(
                    f"Linha {idx} do LCD deve ter exatamente 20 caracteres, recebeu {len(line)}: {line!r}"
                )
            for ch in line:
                code = ord(ch)
                if not (0x20 <= code <= 0x7E):
                    raise ProtocolError(
                        f"Caractere não-ASCII imprimível (0x{code:02X}) na linha {idx} do LCD: {line!r}"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {"lines": list(self.lines)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LcdFramePayload:
        raw_lines = data.get("lines")
        if not isinstance(raw_lines, list) or len(raw_lines) != 4:
            raise ProtocolError("Payload lcd_frame exige lista 'lines' com 4 strings")
        if not all(isinstance(item, str) for item in raw_lines):
            raise ProtocolError("Todas as linhas de lcd_frame devem ser strings")
        return cls(lines=(raw_lines[0], raw_lines[1], raw_lines[2], raw_lines[3]))


@dataclass(frozen=True)
class AckPayload:
    ack_seq: int
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"ack_seq": int(self.ack_seq), "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AckPayload:
        try:
            return cls(ack_seq=int(data["ack_seq"]), status=str(data.get("status", "ok")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Payload ack inválido: {exc}") from exc


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    ref_seq: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "ref_seq": self.ref_seq,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorPayload:
        try:
            ref = data.get("ref_seq")
            return cls(
                code=str(data["code"]),
                message=str(data["message"]),
                ref_seq=int(ref) if ref is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Payload error inválido: {exc}") from exc


@dataclass(frozen=True)
class ProtocolEnvelope:
    v: int
    seq: int
    type: MessageType
    ts_ms: int
    data: dict[str, Any]

    def to_json_line(self) -> str:
        """Serializa o envelope em uma linha JSON compacta terminada por '\\n'."""
        obj = {
            "v": self.v,
            "seq": self.seq,
            "type": self.type.value,
            "ts_ms": self.ts_ms,
            "data": self.data,
        }
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=True) + "\n"


class ProtocolCodec:
    """Codificador/decodificador com contador sequencial para links JSON Lines v1."""

    def __init__(self, initial_seq: int = 1) -> None:
        self._next_seq = initial_seq

    @property
    def next_seq(self) -> int:
        return self._next_seq

    def build_envelope(
        self,
        msg_type: MessageType,
        data: dict[str, Any],
        ts_ms: int | None = None,
    ) -> ProtocolEnvelope:
        seq = self._next_seq
        self._next_seq += 1
        return ProtocolEnvelope(
            v=PROTOCOL_VERSION,
            seq=seq,
            type=msg_type,
            ts_ms=now_ms() if ts_ms is None else int(ts_ms),
            data=data,
        )

    def encode(
        self,
        msg_type: MessageType,
        data: dict[str, Any],
        ts_ms: int | None = None,
    ) -> str:
        return self.build_envelope(msg_type, data, ts_ms=ts_ms).to_json_line()

    @staticmethod
    def decode(line: str) -> ProtocolEnvelope:
        stripped = line.strip()
        if not stripped:
            raise ProtocolError("Linha JSON vazia recebida")
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"JSON malformado: {exc}") from exc

        if not isinstance(raw, dict):
            raise ProtocolError("Mensagem JSON Lines deve ser um objeto na raiz")

        for req in ("v", "seq", "type", "ts_ms", "data"):
            if req not in raw:
                raise ProtocolError(f"Campo obrigatório ausente no envelope: '{req}'")

        if raw["v"] != PROTOCOL_VERSION:
            raise ProtocolError(
                f"Versão de protocolo não suportada: {raw['v']} (esperado {PROTOCOL_VERSION})"
            )

        if not isinstance(raw["seq"], int) or isinstance(raw["seq"], bool) or raw["seq"] < 0:
            raise ProtocolError(f"Campo 'seq' inválido: {raw['seq']!r}")

        if not isinstance(raw["ts_ms"], int) or isinstance(raw["ts_ms"], bool) or raw["ts_ms"] < 0:
            raise ProtocolError(f"Campo 'ts_ms' inválido: {raw['ts_ms']!r}")

        if not isinstance(raw["data"], dict):
            raise ProtocolError("Campo 'data' deve ser um objeto JSON")

        try:
            msg_type = MessageType(raw["type"])
        except ValueError as exc:
            raise ProtocolError(f"Tipo de mensagem desconhecido: {raw['type']!r}") from exc

        return ProtocolEnvelope(
            v=raw["v"],
            seq=raw["seq"],
            type=msg_type,
            ts_ms=raw["ts_ms"],
            data=raw["data"],
        )
