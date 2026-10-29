"""Infraestrutura de Machine Learning e TinyML para reconhecimento de gestos do MotionPet."""

from ml.classifiers import (
    BaseGestureClassifier,
    ClassifierDiagnostics,
    EmbeddedGestureClassifier,
    MLGestureClassifier,
    SimulatedGestureClassifier,
    create_gesture_classifier,
)
from ml.schemas import (
    ALL_GESTURE_CLASSES,
    CORE_GESTURE_CLASSES,
    EXPERIMENTAL_GESTURE_CLASSES,
    FEATURE_NAMES,
    ML_SCHEMA_VERSION,
    DataOrigin,
    ExperimentalStatus,
    PreprocessingConfig,
    RawSampleRecord,
    StabilizerConfig,
    WindowSample,
)

__all__ = [
    "ALL_GESTURE_CLASSES",
    "BaseGestureClassifier",
    "CORE_GESTURE_CLASSES",
    "ClassifierDiagnostics",
    "DataOrigin",
    "EXPERIMENTAL_GESTURE_CLASSES",
    "EmbeddedGestureClassifier",
    "ExperimentalStatus",
    "FEATURE_NAMES",
    "MLGestureClassifier",
    "ML_SCHEMA_VERSION",
    "PreprocessingConfig",
    "RawSampleRecord",
    "SimulatedGestureClassifier",
    "StabilizerConfig",
    "WindowSample",
    "create_gesture_classifier",
]
