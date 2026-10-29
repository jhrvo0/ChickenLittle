"""Submódulo de treinamento de modelos de classificação e particionamento anti-vazamento."""

from __future__ import annotations

from ml.training.models import (
    RuleBaselineModel,
    TrainingConfig,
    build_candidate_models,
)
from ml.training.splitter import (
    DataLeakageError,
    DatasetSplit,
    split_windows_grouped,
    windows_to_xy,
)
from ml.training.trainer import (
    TrainedBundle,
    load_trained_bundle,
    save_trained_bundle,
    select_best_embeddable_bundle,
    train_candidate_models,
)

__all__ = [
    "DataLeakageError",
    "DatasetSplit",
    "RuleBaselineModel",
    "TrainedBundle",
    "TrainingConfig",
    "build_candidate_models",
    "load_trained_bundle",
    "save_trained_bundle",
    "select_best_embeddable_bundle",
    "split_windows_grouped",
    "train_candidate_models",
    "windows_to_xy",
]
