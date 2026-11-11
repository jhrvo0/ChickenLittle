"""Camada de transporte Serial (Virtual Loopback para simulação e PySerial para hardware real)."""

from __future__ import annotations

from collections import deque
from typing import Any, Protocol


class TransportClosedError(RuntimeError):
    """Operação tentada em um transporte serial fechado."""


class HardwareNotConnectedError(RuntimeError):
    """Porta serial física indisponível ou pyserial não instalado."""


class SerialEndpoint(Protocol):
    """Interface comum para comunicação linha a linha (JSON Lines) com o dispositivo."""

    @property
    def is_open(self) -> bool: ...

    def write_line(self, line: str) -> None: ...

    def read_line(self) -> str | None: ...

    def read_all_lines(self) -> list[str]: ...

    def close(self) -> None: ...


class VirtualSerialEndpoint:
    """Extremidade de um cabo serial virtual bidirecional em memória."""

    def __init__(
        self,
        name: str,
        rx_queue: deque[str],
        tx_queue: deque[str],
        wire_log: deque[tuple[str, str]],
    ) -> None:
        self.name = name
        self._rx = rx_queue
        self._tx = tx_queue
        self._wire_log = wire_log
        self._open = True
        self.tx_count = 0
        self.rx_count = 0

    @property
    def is_open(self) -> bool:
        return self._open

    def write_line(self, line: str) -> None:
        if not self._open:
            raise TransportClosedError(f"Endpoint virtual '{self.name}' está fechado")
        normalized = line if line.endswith("\n") else line + "\n"
        self._tx.append(normalized)
        self._wire_log.append((self.name, normalized))
        self.tx_count += 1

    def read_line(self) -> str | None:
        if not self._open:
            raise TransportClosedError(f"Endpoint virtual '{self.name}' está fechado")
        if not self._rx:
            return None
        self.rx_count += 1
        return self._rx.popleft()

    def read_all_lines(self) -> list[str]:
        if not self._open:
            raise TransportClosedError(f"Endpoint virtual '{self.name}' está fechado")
        lines: list[str] = []
        while self._rx:
            lines.append(self._rx.popleft())
            self.rx_count += 1
        return lines

    def close(self) -> None:
        self._open = False


def create_virtual_serial_pair(
    max_wire_log: int = 500,
) -> tuple[VirtualSerialEndpoint, VirtualSerialEndpoint, deque[tuple[str, str]]]:
    """Cria um par conectado `(host_endpoint, device_endpoint, wire_log)`.

    Tudo que `host_endpoint.write_line()` envia chega em `device_endpoint.read_line()`,
    e vice-versa, reproduzindo um link UART/USB Serial completo sem placa física.
    """
    host_to_device: deque[str] = deque()
    device_to_host: deque[str] = deque()
    wire_log: deque[tuple[str, str]] = deque(maxlen=max_wire_log)

    host = VirtualSerialEndpoint("host", rx_queue=device_to_host, tx_queue=host_to_device, wire_log=wire_log)
    device = VirtualSerialEndpoint("device", rx_queue=host_to_device, tx_queue=device_to_host, wire_log=wire_log)
    return host, device, wire_log


class PySerialEndpoint:
    """Adaptador para porta USB Serial real (Ciclo 5 — Integração física com ESP32)."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.01) -> None:
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:
            raise HardwareNotConnectedError(
                "Pacote 'pyserial' não instalado. Instale com '.venv/Scripts/pip install pyserial' "
                "quando conectar o ESP32 físico."
            ) from exc

        try:
            self._ser: Any = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            self._rx_buffer = bytearray()
        except Exception as exc:
            raise HardwareNotConnectedError(
                f"Não foi possível abrir a porta serial '{port}' ({baudrate} bps): {exc}"
            ) from exc

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def write_line(self, line: str) -> None:
        if not self.is_open:
            raise TransportClosedError("Porta serial física está fechada")
        normalized = line if line.endswith("\n") else line + "\n"
        self._ser.write(normalized.encode("utf-8"))

    def read_line(self) -> str | None:
        if not self.is_open:
            raise TransportClosedError("Porta serial física está fechada")
        # USB/UART entrega blocos de bytes, nao mensagens. readline() com timeout
        # pode retornar metade de um JSON; guarde o fragmento ate receber '\n'.
        if b"\n" not in self._rx_buffer:
            available = self._ser.in_waiting
            if available > 0:
                self._rx_buffer.extend(self._ser.read(min(available, 4096)))
        end = self._rx_buffer.find(b"\n")
        if end < 0:
            if len(self._rx_buffer) > 65536:
                self._rx_buffer.clear()
                raise RuntimeError("Entrada serial excedeu 64 KiB sem fim de linha; confira baudrate e firmware.")
            return None
        raw = bytes(self._rx_buffer[:end + 1])
        del self._rx_buffer[:end + 1]
        return raw.decode("utf-8", errors="replace")

    def read_all_lines(self) -> list[str]:
        lines: list[str] = []
        while True:
            line = self.read_line()
            if line is None:
                break
            lines.append(line)
        return lines

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._rx_buffer.clear()
