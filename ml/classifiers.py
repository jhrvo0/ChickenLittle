"""Interface intercambiável de classificadores de gestos para integração com o MotionPet.

Implementações intercambiáveis:
- `SimulatedGestureClassifier`: heurística de janela deslizante para simulação sem modelo treinado.
- `MLGestureClassifier`: classificador causal em tempo real com filtragem, extração das 11 features,
  modelo scikit-learn treinado e estabilização/rejeição/cooldown (`EventStabilizer`). Degrada
  graciosamente caso nenhum arquivo de modelo esteja disponível ainda.
- `EmbeddedGestureClassifier`: adaptador/contrato para inferência TinyML embarcada no ESP32 (Ciclo 3/5),
  opcionalmente capaz de emular o modelo exportado no host ou delegar 100% ao firmware serial.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ml.preprocessing.features import extract_window_features
from ml.preprocessing.filtering import CausalSignalFilter
from ml.schemas import PreprocessingConfig, StabilizerConfig
from terminal.communication.protocol import (
    GestureEventPayload,
    GestureSource,
    GestureType,
    SensorFramePayload,
)


@dataclass(frozen=True)
class ClassifierDiagnostics:
    """Telemetria de observabilidade em tempo real do classificador ativo."""

    classifier_kind: str
    model_name: str
    model_loaded: bool
    last_class: str
    last_confidence: float
    samples_used: int
    last_latency_ms: float
    rejected_events: int
    last_rejection_reason: str | None
    experimental_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_hud_line(self) -> str:
        status_tag = self.model_name if self.model_loaded else f"{self.model_name}(NO_MODEL)"
        rej_detail = (
            f"{self.rejected_events}({self.last_rejection_reason})"
            if self.last_rejection_reason
            else str(self.rejected_events)
        )
        return (
            f"{status_tag} | Cls:{self.last_class} ({self.last_confidence * 100.0:.0f}%) | "
            f"Win:{self.samples_used} | Lat:{self.last_latency_ms:.2f}ms | Rej:{rej_detail}"
        )


class BaseGestureClassifier(ABC):
    """Contrato único de classificação consumido pelo nó de aquisição/simulação."""

    kind: str

    @abstractmethod
    def reset(self) -> None:
        """Limpa buffers temporais, filtros causais e estado de cooldown."""

    @abstractmethod
    def push_frame(
        self,
        frame: SensorFramePayload,
        ts_ms: int | None = None,
    ) -> GestureEventPayload | None:
        """Alimenta uma nova leitura de sensor e retorna evento aceito ou `None`."""

    def push(self, frame: SensorFramePayload) -> GestureEventPayload | None:
        """Alias compatível 1:1 com `SimulatedWindowGestureDetector.push` (Ciclo 1)."""
        return self.push_frame(frame, ts_ms=None)

    @abstractmethod
    def get_diagnostics(self) -> ClassifierDiagnostics:
        """Retorna métricas instantâneas para exibição no terminal e inspeção em testes."""


class SimulatedGestureClassifier(BaseGestureClassifier):
    """Classificador heurístico de simulação (preserva o comportamento do Ciclo 1)."""

    kind = "sim"

    def __init__(
        self,
        window_size: int = 8,
        sample_period_ms: int = 60,
        cooldown_frames: int = 8,
    ) -> None:
        from simulator.gesture_detector_sim import SimulatedWindowGestureDetector

        self._detector = SimulatedWindowGestureDetector(
            window_size=window_size,
            sample_period_ms=sample_period_ms,
            cooldown_frames=cooldown_frames,
        )
        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._last_latency_ms = 0.0
        self._rejected_events = 0
        self._last_rejection_reason: str | None = None
        self._valid_seen = 0

    def reset(self) -> None:
        self._detector.reset()
        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._last_latency_ms = 0.0
        self._rejected_events = 0
        self._last_rejection_reason = None
        self._valid_seen = 0

    def push_frame(
        self,
        frame: SensorFramePayload,
        ts_ms: int | None = None,
    ) -> GestureEventPayload | None:
        _ = ts_ms
        t0 = time.perf_counter()
        was_cooling = self._detector._cooldown > 0
        evt = self._detector.push(frame)
        self._last_latency_ms = (time.perf_counter() - t0) * 1000.0

        if frame.valid_ultrasonic and frame.distance_cm is not None:
            self._valid_seen = min(self._detector.window_size, self._valid_seen + 1)
        else:
            self._rejected_events += 1
            self._last_rejection_reason = "invalid_reading"

        if evt is not None:
            self._last_class = evt.gesture.value
            self._last_conf = evt.confidence
            self._last_rejection_reason = None
            return evt

        if was_cooling and frame.valid_ultrasonic and frame.distance_cm is not None and frame.distance_cm < 45.0:
            self._rejected_events += 1
            self._last_rejection_reason = "cooldown_active"

        return None

    def get_diagnostics(self) -> ClassifierDiagnostics:
        return ClassifierDiagnostics(
            classifier_kind=self.kind,
            model_name="sim_window_heuristic",
            model_loaded=True,
            last_class=self._last_class,
            last_confidence=self._last_conf,
            samples_used=len(self._detector._buffer),
            last_latency_ms=round(self._last_latency_ms, 4),
            rejected_events=self._rejected_events,
            last_rejection_reason=self._last_rejection_reason,
            experimental_status="SIMULATION_ONLY",
        )


class MLGestureClassifier(BaseGestureClassifier):
    """Classificador de Machine Learning em streaming causal com estabilizador de eventos."""

    kind = "ml"

    def __init__(
        self,
        model_path: str | Path | None = None,
        bundle: Any | None = None,
        stabilizer_config: StabilizerConfig | None = None,
        sample_period_fallback_ms: int = 60,
    ) -> None:
        self._bundle = bundle
        if self._bundle is None and model_path is not None:
            p = Path(model_path)
            if p.is_file():
                from ml.training.trainer import load_trained_bundle

                self._bundle = load_trained_bundle(p)

        self._pre_cfg: PreprocessingConfig = (
            self._bundle.preprocessing_config
            if self._bundle is not None
            else PreprocessingConfig()
        )
        self._stab_cfg = stabilizer_config or StabilizerConfig()
        self._sample_period_fallback_ms = sample_period_fallback_ms

        from ml.evaluation.stabilizer import EventStabilizer

        self._filter = CausalSignalFilter(self._pre_cfg)
        self._stabilizer = EventStabilizer(self._stab_cfg)

        w = self._pre_cfg.window_size
        self._dists: deque[float] = deque(maxlen=w)
        self._ts: deque[int] = deque(maxlen=w)
        self._irs: deque[bool] = deque(maxlen=w)
        self._invs: deque[bool] = deque(maxlen=w)
        self._synthetic_clock_ms = 0

        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._last_latency_ms = 0.0
        self._rejected_events = 0
        self._last_rejection_reason: str | None = (
            None if self._bundle is not None else "no_model_loaded"
        )

    @property
    def is_loaded(self) -> bool:
        return self._bundle is not None

    def reset(self) -> None:
        self._filter.reset()
        self._stabilizer.reset()
        self._dists.clear()
        self._ts.clear()
        self._irs.clear()
        self._invs.clear()
        self._synthetic_clock_ms = 0
        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._last_latency_ms = 0.0
        self._rejected_events = 0
        self._last_rejection_reason = None if self._bundle is not None else "no_model_loaded"

    def push_frame(
        self,
        frame: SensorFramePayload,
        ts_ms: int | None = None,
    ) -> GestureEventPayload | None:
        if ts_ms is None:
            self._synthetic_clock_ms += self._sample_period_fallback_ms
            cur_ts = self._synthetic_clock_ms
        else:
            cur_ts = int(ts_ms)
            if self._ts and cur_ts <= self._ts[-1]:
                cur_ts = self._ts[-1] + 1
            self._synthetic_clock_ms = cur_ts

        t0 = time.perf_counter()
        f_dist, was_inv = self._filter.step(frame.distance_cm, frame.valid_ultrasonic)
        self._dists.append(f_dist)
        self._ts.append(cur_ts)
        self._irs.append(frame.ir_detected)
        self._invs.append(was_inv)

        if self._bundle is None:
            self._last_latency_ms = (time.perf_counter() - t0) * 1000.0
            self._last_rejection_reason = "no_model_loaded"
            return None

        if len(self._dists) < self._pre_cfg.window_size:
            self._last_latency_ms = (time.perf_counter() - t0) * 1000.0
            return None

        feats = extract_window_features(
            distances_cm=tuple(self._dists),
            timestamps_ms=tuple(self._ts),
            ir_flags=tuple(self._irs),
            invalid_flags=tuple(self._invs),
            inversion_deadband_cm=self._pre_cfg.inversion_deadband_cm,
        )
        X = np.asarray([feats], dtype=np.float64)
        probs = np.asarray(self._bundle.estimator.predict_proba(X)[0], dtype=np.float64)
        best_idx = int(np.argmax(probs))
        raw_cls = str(self._bundle.class_names[best_idx])
        conf = float(probs[best_idx])

        decision = self._stabilizer.update(raw_label=raw_cls, confidence=conf, ts_ms=cur_ts)
        self._last_latency_ms = (time.perf_counter() - t0) * 1000.0
        self._last_class = raw_cls
        self._last_conf = conf

        if not decision.accepted:
            if decision.rejection_reason not in (None, "neutral"):
                self._rejected_events += 1
                self._last_rejection_reason = decision.rejection_reason
            return None

        self._last_rejection_reason = None
        source = (
            GestureSource.RULE_BASELINE
            if self._bundle.model_name == "rule_baseline"
            else GestureSource.TINYML
        )
        win_ms = max(1, int(self._ts[-1] - self._ts[0]))
        return GestureEventPayload(
            gesture=GestureType(decision.emitted_label or raw_cls),
            confidence=round(min(1.0, max(0.0, conf)), 4),
            source=source,
            window_ms=win_ms,
        )

    def get_diagnostics(self) -> ClassifierDiagnostics:
        model_name = self._bundle.model_name if self._bundle is not None else "ml_unloaded"
        exp_status = (
            self._bundle.experimental_status
            if self._bundle is not None
            else "AWAITING_REAL_DATA"
        )
        return ClassifierDiagnostics(
            classifier_kind=self.kind,
            model_name=model_name,
            model_loaded=(self._bundle is not None),
            last_class=self._last_class,
            last_confidence=round(self._last_conf, 4),
            samples_used=len(self._dists),
            last_latency_ms=round(self._last_latency_ms, 4),
            rejected_events=self._rejected_events,
            last_rejection_reason=self._last_rejection_reason,
            experimental_status=exp_status,
        )


class EmbeddedGestureClassifier(BaseGestureClassifier):
    """Representa o classificador TinyML executado diretamente no firmware C++ do ESP32 (Ciclo 3/5).

    Quando conectado ao ESP32 físico via USB Serial, o microcontrolador envia os quadros
    `gesture_event` (`source="tinyml"`) já classificados, não exigindo inferência no notebook.
    Em simulação sem placa física, registra claramente o estado `DELEGATED_TO_ESP32_FIRMWARE`.
    """

    kind = "embedded"

    def __init__(self, header_path: str | Path = "firmware/gestures/tinyml_model.h") -> None:
        self.header_path = Path(header_path)
        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._samples_seen = 0

    def reset(self) -> None:
        self._last_class = "NEUTRAL"
        self._last_conf = 0.0
        self._samples_seen = 0

    def record_wire_event(self, event: GestureEventPayload) -> None:
        """Atualiza diagnósticos quando o ESP32 real publica um `gesture_event` na serial."""
        self._last_class = event.gesture.value
        self._last_conf = event.confidence

    def push_frame(
        self,
        frame: SensorFramePayload,
        ts_ms: int | None = None,
    ) -> GestureEventPayload | None:
        _ = (frame, ts_ms)
        self._samples_seen = min(16, self._samples_seen + 1)
        return None

    def get_diagnostics(self) -> ClassifierDiagnostics:
        has_hdr = self.header_path.is_file()
        return ClassifierDiagnostics(
            classifier_kind=self.kind,
            model_name="esp32_tinyml_header" if has_hdr else "esp32_pending_export",
            model_loaded=has_hdr,
            last_class=self._last_class,
            last_confidence=self._last_conf,
            samples_used=self._samples_seen,
            last_latency_ms=0.0,
            rejected_events=0,
            last_rejection_reason="awaiting_esp32_firmware",
            experimental_status="NOT_VALIDATED_ON_ESP32_HARDWARE",
        )


def create_gesture_classifier(
    kind: str = "sim",
    model_path: str | Path | None = "data/models/best_model.joblib",
    stabilizer_config: StabilizerConfig | None = None,
) -> BaseGestureClassifier:
    """Fábrica unificada para seleção intercambiável via CLI (`sim` | `ml` | `embedded`)."""
    norm = kind.strip().lower()
    if norm == "sim":
        return SimulatedGestureClassifier()
    if norm == "ml":
        return MLGestureClassifier(
            model_path=model_path,
            stabilizer_config=stabilizer_config,
        )
    if norm == "embedded":
        return EmbeddedGestureClassifier()
    raise ValueError(f"Tipo de classificador desconhecido '{kind}' (use 'sim', 'ml' ou 'embedded').")
