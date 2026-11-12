"""Reconhecedores de gesto que rodam lado a lado no host, com a mesma janela, filtro e estabilizador.

- `rules`: `RuleBaselineModel` (limiares físicos explícitos, sem treino).
- `ml`: bundle treinado (`data/models/best_model.joblib`, hoje o `mlp_compact`).
- `device`: não roda aqui; são os `gesture_event` que o TinyML da ESP32 envia (ver `engine.py`).

Usar o mesmo `MLGestureClassifier` para regras e ML torna a comparação justa: o que muda é só
o estimador.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import statistics

from ml.classifiers import MLGestureClassifier
from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, PreprocessingConfig, StabilizerConfig
from terminal.communication.protocol import GestureEventPayload, SensorFramePayload

DEFAULT_MODEL_PATH = Path("data/models/best_model.joblib")


def rule_bundle():
    """Bundle em memória do baseline por regras (não depende de arquivo ignorado pelo git)."""
    from ml.training.models import RuleBaselineModel, TrainingConfig
    from ml.training.trainer import TrainedBundle

    return TrainedBundle(
        model_name="rule_baseline", estimator=RuleBaselineModel(class_names=CORE_GESTURE_CLASSES),
        class_names=tuple(CORE_GESTURE_CLASSES), feature_names=tuple(FEATURE_NAMES),
        preprocessing_config=PreprocessingConfig(), training_config=TrainingConfig(),
        split_strategy="none", split_warnings=(), data_origins=(), experimental_status="RULES_NO_TRAINING",
    )


def load_model_bundle(path: Path):
    """Carrega o bundle de ML; devolve `(bundle, erro)` sem levantar exceção."""
    if not path.is_file():
        return None, f"Modelo não encontrado em {path.as_posix()}."
    try:
        from ml.training.trainer import load_trained_bundle

        return load_trained_bundle(path), None
    except Exception as exc:  # arquivo corrompido ou versão incompatível do scikit-learn
        return None, f"Não foi possível carregar o modelo: {exc}"


@dataclass
class RecognizerStats:
    windows: int = 0
    events: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=400))

    def latency_summary(self) -> dict:
        if not self.latencies_ms:
            return {"mean_ms": None, "p95_ms": None}
        values = sorted(self.latencies_ms)
        p95 = values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]
        return {"mean_ms": round(statistics.fmean(values), 3), "p95_ms": round(p95, 3)}


class HostRecognizer:
    """Envolve um `MLGestureClassifier` e guarda a predição crua de cada janela para o painel."""

    def __init__(self, source: str, bundle, *, label: str, kind: str, origin: str, error: str | None = None,
                 stabilizer: StabilizerConfig | None = None) -> None:
        self.source = source
        self.label = label
        self.kind = kind  # "rules" ou "ml": define se a confiança é interpretável
        self.origin = origin
        self.error = error
        self.bundle = bundle
        self.classifier = MLGestureClassifier(bundle=bundle, stabilizer_config=stabilizer) if bundle is not None else None
        self.stats = RecognizerStats()
        self.last_raw: dict | None = None

    @property
    def available(self) -> bool:
        return self.classifier is not None

    @property
    def model_name(self) -> str | None:
        return self.bundle.model_name if self.bundle is not None else None

    def reset(self) -> None:
        if self.classifier is not None:
            self.classifier.reset()
        self.stats = RecognizerStats()
        self.last_raw = None

    def push(self, frame: SensorFramePayload, ts_ms: int) -> GestureEventPayload | None:
        if self.classifier is None:
            return None
        before = self.classifier.get_diagnostics()
        event = self.classifier.push_frame(frame, ts_ms=ts_ms)
        diag = self.classifier.get_diagnostics()
        window_full = diag.samples_used >= self.bundle.preprocessing_config.window_size
        if window_full:
            self.stats.windows += 1
            self.stats.latencies_ms.append(diag.last_latency_ms)
            self.last_raw = {"label": diag.last_class, "confidence": round(diag.last_confidence, 4), "ts_ms": ts_ms}
            if diag.rejected_events > before.rejected_events and diag.last_rejection_reason:
                reason = diag.last_rejection_reason
                self.stats.rejected[reason] = self.stats.rejected.get(reason, 0) + 1
        if event is not None:
            self.stats.events += 1
        return event

    def describe(self) -> dict:
        meta = None
        if self.bundle is not None:
            meta = {
                "model_name": self.bundle.model_name,
                "experimental_status": self.bundle.experimental_status,
                "data_origins": list(self.bundle.data_origins),
                "window_size": self.bundle.preprocessing_config.window_size,
            }
        return {
            "source": self.source, "label": self.label, "kind": self.kind, "available": self.available,
            "origin": self.origin, "error": self.error, "model": meta,
            "confidence_meaning": "n/a (regra fixa 0,85)" if self.kind == "rules" else "softmax não calibrado",
            "windows": self.stats.windows, "events": self.stats.events, "rejected": dict(self.stats.rejected),
            "latency": self.stats.latency_summary(), "last_raw": self.last_raw,
        }


def build_host_recognizers(model_path: Path = DEFAULT_MODEL_PATH) -> dict[str, HostRecognizer]:
    bundle, error = load_model_bundle(model_path)
    origins = list(bundle.data_origins) if bundle is not None else []
    synthetic = any(o != "real_hardware" for o in origins) or not origins
    return {
        "rules": HostRecognizer("rules", rule_bundle(), label="Regras", kind="rules", origin="deterministic"),
        "ml": HostRecognizer("ml", bundle, label="ML no host", kind="ml",
                             origin="synthetic" if synthetic else "real", error=error),
    }
