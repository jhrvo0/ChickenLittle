"""Submódulo de avaliação multivariada, métricas de eventos contínuos e relatórios."""

from __future__ import annotations

from ml.evaluation.metrics import (
    estimate_esp32_memory,
    evaluate_classification_metrics,
    evaluate_event_level,
    measure_inference_latency,
)
from ml.evaluation.report import (
    format_evaluation_markdown,
    generate_evaluation_report,
    save_evaluation_json,
    save_evaluation_markdown,
)
from ml.evaluation.stabilizer import EventStabilizer, StabilizerDecision

__all__ = [
    "EventStabilizer",
    "StabilizerDecision",
    "estimate_esp32_memory",
    "evaluate_classification_metrics",
    "evaluate_event_level",
    "format_evaluation_markdown",
    "generate_evaluation_report",
    "measure_inference_latency",
    "save_evaluation_json",
    "save_evaluation_markdown",
]
