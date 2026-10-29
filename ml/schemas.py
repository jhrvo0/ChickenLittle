"""Contratos de dados, constantes canônicas e configurações versionadas do pipeline de ML (Ciclo 2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

ML_SCHEMA_VERSION = 1

# Ordem canônica alinhada 1:1 com `GestureType` em `firmware/gestures/gesture_classifier.h`
CORE_GESTURE_CLASSES: tuple[str, ...] = (
    "NEUTRAL",
    "APPROACH",
    "RETREAT",
    "HOLD",
)

EXPERIMENTAL_GESTURE_CLASSES: tuple[str, ...] = (
    "IMPULSE",
    "DOUBLE",
)

ALL_GESTURE_CLASSES: tuple[str, ...] = CORE_GESTURE_CLASSES + EXPERIMENTAL_GESTURE_CLASSES

# 11 características causais O(W) extraíveis em tempo real no ESP32 sem alocação dinâmica
FEATURE_NAMES: tuple[str, ...] = (
    "d_min",
    "d_max",
    "d_mean",
    "d_std",
    "d_delta",
    "v_mean",
    "v_peak",
    "trend_slope",
    "sign_inversions",
    "ir_active_ratio",
    "invalid_ratio",
)


class DataOrigin(str, Enum):
    REAL_HARDWARE = "real_hardware"
    SYNTHETIC_SIMULATOR = "synthetic_simulator"


class ExperimentalStatus(str, Enum):
    AWAITING_REAL_DATA = "AWAITING_REAL_DATA"
    EVALUATED_ON_REAL_DATA = "EVALUATED_ON_REAL_DATA"


@dataclass(frozen=True)
class RawSampleRecord:
    """Uma amostra temporal capturada do HC-SR04 + TCRT5000 + potenciômetro com metadados."""

    participant_id: str
    session_id: str
    sample_idx: int
    ts_ms: int
    label: str
    distance_cm: float | None
    valid_ultrasonic: bool
    ir_detected: bool
    pot_norm: float = 0.5
    data_origin: str = DataOrigin.REAL_HARDWARE.value
    captured_at_iso: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "sample_idx": int(self.sample_idx),
            "ts_ms": int(self.ts_ms),
            "label": self.label,
            "distance_cm": round(float(self.distance_cm), 3) if self.distance_cm is not None else None,
            "valid_ultrasonic": bool(self.valid_ultrasonic),
            "ir_detected": bool(self.ir_detected),
            "pot_norm": round(float(self.pot_norm), 4),
            "data_origin": self.data_origin,
            "captured_at_iso": self.captured_at_iso,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSampleRecord:
        raw_dist = data.get("distance_cm")
        dist: float | None
        if raw_dist in (None, "", "None", "null", "NaN"):
            dist = None
        else:
            dist = float(raw_dist)

        raw_valid = data.get("valid_ultrasonic")
        if isinstance(raw_valid, bool):
            valid = raw_valid
        elif raw_valid in (None, ""):
            valid = dist is not None
        else:
            valid = str(raw_valid).strip().lower() in ("1", "true", "yes")

        raw_ir = data.get("ir_detected", False)
        if isinstance(raw_ir, bool):
            ir = raw_ir
        else:
            ir = str(raw_ir).strip().lower() in ("1", "true", "yes")

        return cls(
            participant_id=str(data["participant_id"]).strip(),
            session_id=str(data["session_id"]).strip(),
            sample_idx=int(data["sample_idx"]),
            ts_ms=int(data["ts_ms"]),
            label=str(data["label"]).strip().upper(),
            distance_cm=dist,
            valid_ultrasonic=valid,
            ir_detected=ir,
            pot_norm=float(data.get("pot_norm", 0.5)),
            data_origin=str(data.get("data_origin", DataOrigin.REAL_HARDWARE.value)).strip(),
            captured_at_iso=str(data.get("captured_at_iso", "")).strip(),
        )


@dataclass(frozen=True)
class PreprocessingConfig:
    """Configuração estritamente causal de filtragem e janelamento temporal."""

    schema_version: int = ML_SCHEMA_VERSION
    window_size: int = 10
    stride: int = 2
    min_valid_cm: float = 2.0
    max_valid_cm: float = 400.0
    saturation_cm: float = 100.0
    max_hold_steps: int = 2
    median_kernel: int = 3
    ema_alpha: float = 0.65
    inversion_deadband_cm: float = 0.8
    min_label_purity: float = 0.60

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreprocessingConfig:
        valid_keys = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_keys)


@dataclass(frozen=True)
class StabilizerConfig:
    """Configuração de rejeição de incerteza, histerese/estabilização e cooldown anti-repetição."""

    min_confidence: float = 0.60
    min_consecutive_windows: int = 2
    cooldown_ms: int = 700
    require_neutral_reset: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StabilizerConfig:
        valid_keys = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_keys)


@dataclass(frozen=True)
class WindowSample:
    """Janela temporal processada com vetor de características e metadados de agrupamento."""

    participant_id: str
    session_id: str
    start_ts_ms: int
    end_ts_ms: int
    label: str
    features: tuple[float, ...]
    data_origin: str = DataOrigin.REAL_HARDWARE.value

    @property
    def duration_ms(self) -> int:
        return max(1, self.end_ts_ms - self.start_ts_ms)

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "start_ts_ms": self.start_ts_ms,
            "end_ts_ms": self.end_ts_ms,
            "label": self.label,
            "data_origin": self.data_origin,
        }
        for fname, fval in zip(FEATURE_NAMES, self.features):
            row[fname] = round(float(fval), 6)
        return row

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WindowSample:
        feats = tuple(float(data[fname]) for fname in FEATURE_NAMES)
        return cls(
            participant_id=str(data["participant_id"]),
            session_id=str(data["session_id"]),
            start_ts_ms=int(data["start_ts_ms"]),
            end_ts_ms=int(data["end_ts_ms"]),
            label=str(data["label"]).strip().upper(),
            features=feats,
            data_origin=str(data.get("data_origin", DataOrigin.REAL_HARDWARE.value)),
        )
