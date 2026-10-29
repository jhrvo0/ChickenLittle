"""Adaptador unificado de entradas para o Pet Launch (Teclado, Simulador e TinyML/ESP32).

Garante que toda a lógica de gameplay opere exclusivamente sobre ações semânticas (`LaunchAction`),
independentes da origem do comando, com proteção contra eventos duplicados e suporte completo aos
4 gestos prioritários (`HOLD`, `APPROACH`, `RETREAT`, `NEUTRAL`), sem depender de `IMPULSE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from terminal.communication.protocol import (
    GestureEventPayload,
    GestureType,
    SensorFramePayload,
)


class LaunchAction(str, Enum):
    """Ações semânticas consumidas pela máquina de estados do Pet Launch."""

    CONFIRM_OR_LAUNCH = "CONFIRM_OR_LAUNCH"  # Selecionar pet / iniciar / confirmar lançamento (APPROACH / ENTER)
    CHARGE_POWER = "CHARGE_POWER"            # Carregar barra de força calibrada (HOLD / SPACE)
    DIRECT_IMPULSE_LAUNCH = "DIRECT_IMPULSE" # Lançamento direto experimental (IMPULSE / V)
    CANCEL_OR_BACK = "CANCEL_OR_BACK"        # Cancelar carga ou voltar etapa/menu (RETREAT / B / ESC)
    AIM_UP = "AIM_UP"                        # Elevar ângulo de lançamento (W / ])
    AIM_DOWN = "AIM_DOWN"                    # Reduzir ângulo de lançamento (Z / [)
    BUY_NEXT_UPGRADE = "BUY_NEXT_UPGRADE"    # Comprar próxima melhoria disponível (U)
    BUY_UPGRADE_1 = "BUY_UPGRADE_1"          # Comprar melhoria slot 1 (7)
    BUY_UPGRADE_2 = "BUY_UPGRADE_2"          # Comprar melhoria slot 2 (8)
    BUY_UPGRADE_3 = "BUY_UPGRADE_3"          # Comprar melhoria slot 3 (9)


@dataclass(frozen=True)
class UnifiedLaunchInput:
    """Comando normalizado e auditável entregue ao motor de gameplay."""

    action: LaunchAction
    origin: str  # "keyboard" | "sim_keyboard" | "sim_sensor" | "rule_baseline" | "tinyml"
    confidence: float = 1.0
    event_token: str | None = None


@dataclass(frozen=True)
class CalibratedSensorAim:
    """Parâmetros calibrados extraídos dos sensores disponíveis (potenciômetro e distância 1D)."""

    angle_deg: float
    charge_step_norm: float
    proximity_cm: float | None


class LaunchInputAdapter:
    """Converte entradas de teclado, simulador e TinyML em `UnifiedLaunchInput` sem duplicatas."""

    def __init__(
        self,
        min_gesture_confidence: float = 0.55,
        min_angle_deg: float = 20.0,
        max_angle_deg: float = 70.0,
        base_charge_step: float = 0.25,
    ) -> None:
        self.min_gesture_confidence = min_gesture_confidence
        self.min_angle_deg = min_angle_deg
        self.max_angle_deg = max_angle_deg
        self.base_charge_step = base_charge_step
        self._seen_tokens: set[str] = set()
        self._seen_order: list[str] = []
        self.duplicate_drops: int = 0

    def reset_dedup(self) -> None:
        self._seen_tokens.clear()
        self._seen_order.clear()
        self.duplicate_drops = 0

    def _register_token(self, token: str | None) -> bool:
        """Retorna `False` se o token de evento já foi processado (elimina duplicatas)."""
        if not token:
            return True
        if token in self._seen_tokens:
            self.duplicate_drops += 1
            return False
        self._seen_tokens.add(token)
        self._seen_order.append(token)
        if len(self._seen_order) > 128:
            oldest = self._seen_order.pop(0)
            self._seen_tokens.discard(oldest)
        return True

    def from_key(self, key: str, event_token: str | None = None) -> UnifiedLaunchInput | None:
        """Mapeia teclas locais para ações unificadas do Pet Launch."""
        if not key:
            return None
        if not self._register_token(event_token):
            return None

        if key in ("\r", "\n"):
            return UnifiedLaunchInput(LaunchAction.CONFIRM_OR_LAUNCH, origin="keyboard", event_token=event_token)
        if key == " ":
            return UnifiedLaunchInput(LaunchAction.CHARGE_POWER, origin="keyboard", event_token=event_token)
        if key == "\x1b":
            return UnifiedLaunchInput(LaunchAction.CANCEL_OR_BACK, origin="keyboard", event_token=event_token)

        k = key.lower()
        key_map: dict[str, LaunchAction] = {
            "e": LaunchAction.CONFIRM_OR_LAUNCH,
            "h": LaunchAction.CHARGE_POWER,
            "v": LaunchAction.DIRECT_IMPULSE_LAUNCH,
            "b": LaunchAction.CANCEL_OR_BACK,
            "w": LaunchAction.AIM_UP,
            "]": LaunchAction.AIM_UP,
            "z": LaunchAction.AIM_DOWN,
            "[": LaunchAction.AIM_DOWN,
            "u": LaunchAction.BUY_NEXT_UPGRADE,
            "7": LaunchAction.BUY_UPGRADE_1,
            "8": LaunchAction.BUY_UPGRADE_2,
            "9": LaunchAction.BUY_UPGRADE_3,
        }
        mapped = key_map.get(k)
        if mapped is None:
            return None
        return UnifiedLaunchInput(mapped, origin="keyboard", event_token=event_token)

    def from_gesture(
        self,
        event: GestureEventPayload,
        seq_id: int | None = None,
        ts_ms: int | None = None,
    ) -> UnifiedLaunchInput | None:
        """Mapeia eventos `GestureEventPayload` (Simulador ou TinyML ESP32) sem duplicação."""
        if event.confidence < self.min_gesture_confidence:
            return None

        token: str | None = None
        if seq_id is not None:
            token = f"gseq:{seq_id}"
        elif ts_ms is not None:
            token = f"gts:{event.source.value}:{event.gesture.value}:{ts_ms}"

        if not self._register_token(token):
            return None

        origin = event.source.value
        g = event.gesture

        if g == GestureType.HOLD:
            return UnifiedLaunchInput(LaunchAction.CHARGE_POWER, origin=origin, confidence=event.confidence, event_token=token)
        if g == GestureType.APPROACH:
            # Alternativa prioritária segura: confirma menu/pet e dispara o lançamento após carregar com HOLD!
            return UnifiedLaunchInput(LaunchAction.CONFIRM_OR_LAUNCH, origin=origin, confidence=event.confidence, event_token=token)
        if g == GestureType.RETREAT:
            return UnifiedLaunchInput(LaunchAction.CANCEL_OR_BACK, origin=origin, confidence=event.confidence, event_token=token)
        if g == GestureType.IMPULSE:
            # Suportado quando o classificador experimental emitir IMPULSE, mas nunca obrigatório
            return UnifiedLaunchInput(LaunchAction.DIRECT_IMPULSE_LAUNCH, origin=origin, confidence=event.confidence, event_token=token)

        # NEUTRAL e DOUBLE não disparam ações acidentais no Pet Launch
        return None

    def calibrate_from_sensor(self, frame: SensorFramePayload) -> CalibratedSensorAim:
        """Deriva ângulo (via potenciômetro) e passo calibrado de carga a partir de sensores reais/sim."""
        span = self.max_angle_deg - self.min_angle_deg
        angle = round(self.min_angle_deg + float(frame.pot_norm) * span, 1)

        # Passo de carga calibrável pela zona de proximidade medida no HC-SR04 (sem supor força física do braço)
        step = self.base_charge_step
        prox: float | None = None
        if frame.valid_ultrasonic and frame.distance_cm is not None:
            prox = float(frame.distance_cm)

        return CalibratedSensorAim(
            angle_deg=angle,
            charge_step_norm=round(step, 3),
            proximity_cm=prox,
        )
