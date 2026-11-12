"""Catálogo fechado de ações do MotionLab e emissor de teclas do sistema.

Não existe execução de comando arbitrário: cada ação externa é uma tecla de uma tabela fixa
(mídia e apresentação), enviada por `user32.keybd_event` para a janela em foco, exatamente como
um passador de slides USB. Ações internas são entregues à interface do módulo ativo.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys
import threading
import time

CONTEXTS = ("control", "canvas", "music", "slides")
TRIGGERS = ("APPROACH", "RETREAT", "HOLD", "IR_TAP", "IR_HOLD")


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label: str
    kind: str  # "system" (MotionLab), "internal" (UI do módulo) ou "external" (tecla no sistema)
    contexts: tuple[str, ...]
    vk: int | None = None
    extended: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind, "contexts": list(self.contexts)}


_EXT = ("control", "slides")
CATALOG: dict[str, ActionSpec] = {a.id: a for a in (
    ActionSpec("lab.toggle_armed", "Ativar/desativar gestos", "system", CONTEXTS),
    # Mídia (teclas multimídia do Windows)
    ActionSpec("media.play_pause", "Mídia: tocar/pausar", "external", _EXT, 0xB3, True),
    ActionSpec("media.next", "Mídia: próxima faixa", "external", _EXT, 0xB0, True),
    ActionSpec("media.prev", "Mídia: faixa anterior", "external", _EXT, 0xB1, True),
    ActionSpec("media.volume_up", "Volume +", "external", _EXT, 0xAF, True),
    ActionSpec("media.volume_down", "Volume −", "external", _EXT, 0xAE, True),
    ActionSpec("media.mute", "Mudo", "external", _EXT, 0xAD, True),
    # Apresentação (PowerPoint, Google Slides, leitores de PDF aceitam PageDown/PageUp)
    ActionSpec("present.next", "Apresentação: avançar (PageDown)", "external", _EXT, 0x22, True),
    ActionSpec("present.prev", "Apresentação: voltar (PageUp)", "external", _EXT, 0x21, True),
    ActionSpec("present.start", "Apresentação: iniciar (F5)", "external", _EXT, 0x74, False),
    ActionSpec("present.blank", "Apresentação: tela preta (B)", "external", _EXT, 0x42, False),
    ActionSpec("present.end", "Apresentação: sair (Esc)", "external", _EXT, 0x1B, False),
    # Air Slides (deck integrado)
    ActionSpec("slides.next", "Deck: próximo slide", "internal", ("slides",)),
    ActionSpec("slides.prev", "Deck: slide anterior", "internal", ("slides",)),
    ActionSpec("slides.blank", "Deck: tela preta", "internal", ("slides",)),
    # Motion Canvas
    ActionSpec("canvas.next_style", "Canvas: próximo estilo", "internal", ("canvas",)),
    ActionSpec("canvas.next_palette", "Canvas: próxima paleta", "internal", ("canvas",)),
    ActionSpec("canvas.freeze", "Canvas: congelar/retomar", "internal", ("canvas",)),
    ActionSpec("canvas.burst", "Canvas: explosão", "internal", ("canvas",)),
    ActionSpec("canvas.reset", "Canvas: limpar", "internal", ("canvas",)),
    # Air Music
    ActionSpec("music.toggle_record", "Música: gravar/parar loop", "internal", ("music",)),
    ActionSpec("music.toggle_play", "Música: tocar/pausar loops", "internal", ("music",)),
    ActionSpec("music.next_timbre", "Música: próximo timbre", "internal", ("music",)),
    ActionSpec("music.clear_layer", "Música: apagar última camada", "internal", ("music",)),
    ActionSpec("music.toggle_mute", "Música: silenciar instrumento", "internal", ("music",)),
)}


class KeySender:
    """Interface mínima: envia uma tecla (pressiona e solta)."""

    available = False
    reason = "Envio de teclas indisponível neste sistema."

    def send(self, vk: int, extended: bool) -> None:  # pragma: no cover - interface
        raise RuntimeError(self.reason)


class WindowsKeySender(KeySender):
    """`keybd_event` do user32 (sem dependência externa). Só funciona no Windows."""

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._user32 = None
        if sys.platform == "win32":
            try:
                import ctypes

                self._user32 = ctypes.windll.user32
                self.available = True
                self.reason = ""
            except Exception as exc:  # pragma: no cover - ambiente sem user32
                self.reason = f"user32 indisponível: {exc}"

    def send(self, vk: int, extended: bool) -> None:
        if self._user32 is None:
            raise RuntimeError(self.reason)
        flags = self.KEYEVENTF_EXTENDEDKEY if extended else 0
        with self._lock:
            self._user32.keybd_event(vk, 0, flags, 0)
            time.sleep(0.01)
            self._user32.keybd_event(vk, 0, flags | self.KEYEVENTF_KEYUP, 0)


class RecordingKeySender(KeySender):
    """Emissor falso para testes e para a demonstração: registra em vez de enviar."""

    available = True
    reason = ""

    def __init__(self) -> None:
        self.sent: list[tuple[int, bool]] = []

    def send(self, vk: int, extended: bool) -> None:
        self.sent.append((vk, extended))


class ExternalRateLimiter:
    """Limite rígido de teclas no sistema, independente de cooldown configurado."""

    MIN_INTERVAL_S = 0.35
    BURST_WINDOW_S = 10.0
    BURST_MAX = 8

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._sent: list[float] = []

    def allow(self) -> bool:
        now = self._clock()
        self._sent = [t for t in self._sent if now - t < self.BURST_WINDOW_S]
        if self._sent and now - self._sent[-1] < self.MIN_INTERVAL_S:
            return False
        if len(self._sent) >= self.BURST_MAX:
            return False
        self._sent.append(now)
        return True
