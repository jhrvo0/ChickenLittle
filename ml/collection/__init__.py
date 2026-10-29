"""Subpacote de coleta, validação de integridade e geração sintética para testes."""

from ml.collection.collector import (
    SAMPLE_CSV_FIELDS,
    SerialSessionRecorder,
    parse_gesture_schedule,
    record_simulated_session,
    save_session_csv,
    save_session_jsonl,
)
from ml.collection.synthetic import generate_synthetic_corpus, generate_synthetic_session
from ml.collection.validator import SessionQualityReport, validate_session_records

__all__ = [
    "SAMPLE_CSV_FIELDS",
    "SerialSessionRecorder",
    "SessionQualityReport",
    "generate_synthetic_corpus",
    "generate_synthetic_session",
    "parse_gesture_schedule",
    "record_simulated_session",
    "save_session_csv",
    "save_session_jsonl",
    "validate_session_records",
]
