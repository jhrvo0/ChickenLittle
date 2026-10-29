"""Testes automatizados de coleta, validação de sessões e pré-processamento estritamente causal (Ciclo 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.classifiers import (
    EmbeddedGestureClassifier,
    MLGestureClassifier,
    SimulatedGestureClassifier,
    create_gesture_classifier,
)
from ml.collection import (
    generate_synthetic_corpus,
    generate_synthetic_session,
    parse_gesture_schedule,
    record_simulated_session,
    save_session_csv,
    save_session_jsonl,
    validate_session_records,
)
from ml.collection.__main__ import main as collection_cli_main
from ml.preprocessing import (
    CausalSignalFilter,
    extract_window_features,
    load_raw_records_from_path,
    load_windows_csv,
    preprocess_records,
    save_windows_csv,
    segment_session_windows,
)
from ml.preprocessing.__main__ import main as preproc_cli_main
from ml.schemas import (
    DataOrigin,
    FEATURE_NAMES,
    PreprocessingConfig,
    RawSampleRecord,
)
from terminal.communication.protocol import SensorFramePayload


def test_parse_gesture_schedule_valid_and_invalid() -> None:
    sched = parse_gesture_schedule("NEUTRAL:10, approach:8 , HOLD:12")
    assert sched == [("NEUTRAL", 10), ("APPROACH", 8), ("HOLD", 12)]

    with pytest.raises(ValueError):
        parse_gesture_schedule("APPROACH")
    with pytest.raises(ValueError):
        parse_gesture_schedule("APPROACH:0")
    with pytest.raises(ValueError):
        parse_gesture_schedule("   ")


def test_record_simulated_session_and_validator_roundtrip(tmp_path: Path) -> None:
    schedule = [("NEUTRAL", 10), ("APPROACH", 10), ("HOLD", 10), ("RETREAT", 10)]
    records = record_simulated_session(
        participant_id="p_sim",
        session_id="sess_01",
        schedule=schedule,
        seed=123,
        dropout_prob=0.05,
    )
    assert len(records) == 40
    assert all(r.data_origin == DataOrigin.SYNTHETIC_SIMULATOR.value for r in records)

    report = validate_session_records(records)
    assert report.valid is True
    assert report.total_samples == 40
    assert report.labels_distribution == {
        "NEUTRAL": 10,
        "APPROACH": 10,
        "HOLD": 10,
        "RETREAT": 10,
    }

    jsonl_p = save_session_jsonl(records, tmp_path / "sess_01.jsonl")
    csv_p = save_session_csv(records, tmp_path / "sess_01.csv")

    from_jsonl = load_raw_records_from_path(jsonl_p)
    from_csv = load_raw_records_from_path(csv_p)
    assert len(from_jsonl) == 40
    assert len(from_csv) == 40
    # Carregar diretório com .jsonl e .csv de mesmo stem não deve duplicar registros
    from_dir = load_raw_records_from_path(tmp_path)
    assert len(from_dir) == 40


def test_validator_catches_non_monotonic_timestamps_and_bad_labels() -> None:
    bad_records = [
        RawSampleRecord(
            participant_id="p01",
            session_id="s01",
            sample_idx=i,
            ts_ms=(100 if i != 5 else 80),  # Regressão temporal no índice 5
            label=("APPROACH" if i != 3 else "UNKNOWN_WAVE"),
            distance_cm=25.0,
            valid_ultrasonic=True,
            ir_detected=False,
        )
        for i in range(12)
    ]
    rep = validate_session_records(bad_records)
    assert rep.valid is False
    assert any("ordenação temporal" in e for e in rep.errors)
    assert any("Rótulos desconhecidos" in e for e in rep.errors)


def test_causal_filter_strictly_has_zero_future_leakage() -> None:
    """Prova matemática: alterar amostras futuras t+1..N jamais altera a saída filtrada em t."""
    cfg = PreprocessingConfig(max_hold_steps=2, median_kernel=3, ema_alpha=0.65)
    prefix = [(42.0, True), (39.5, True), (None, False), (35.0, True), (31.2, True)]
    future_a = [(28.0, True), (24.0, True), (20.0, True)]
    future_b = [(399.0, True), (None, False), (2.0, True)]

    flt_a = CausalSignalFilter(cfg)
    outs_a = [flt_a.step(d, v) for d, v in (prefix + future_a)]

    flt_b = CausalSignalFilter(cfg)
    outs_b = [flt_b.step(d, v) for d, v in (prefix + future_b)]

    assert outs_a[: len(prefix)] == outs_b[: len(prefix)]


def test_causal_filter_hold_and_saturation_behavior() -> None:
    cfg = PreprocessingConfig(max_hold_steps=2, saturation_cm=100.0, ema_alpha=1.0, median_kernel=1)
    flt = CausalSignalFilter(cfg)

    v0, inv0 = flt.step(20.0, True)
    assert (v0, inv0) == (20.0, False)

    # 2 dropouts consecutivos seguram último valor válido (20.0)
    v1, inv1 = flt.step(None, False)
    v2, inv2 = flt.step(None, False)
    assert (v1, inv1) == (20.0, True)
    assert (v2, inv2) == (20.0, True)

    # 3º dropout excede max_hold_steps -> satura em 100.0 cm
    v3, inv3 = flt.step(None, False)
    assert (v3, inv3) == (100.0, True)


def test_feature_extraction_semantics_for_approach_and_retreat() -> None:
    ts = [i * 70 for i in range(10)]
    dists_approach = [45.0 - i * 3.5 for i in range(10)]
    irs = [d <= 14.0 for d in dists_approach]
    invs = [False] * 10

    f_app = dict(zip(FEATURE_NAMES, extract_window_features(dists_approach, ts, irs, invs)))
    assert f_app["d_delta"] < -25.0
    assert f_app["v_mean"] < -35.0
    assert f_app["trend_slope"] < -35.0
    assert f_app["sign_inversions"] == 0.0
    assert f_app["ir_active_ratio"] > 0.0
    assert f_app["invalid_ratio"] == 0.0

    dists_retreat = list(reversed(dists_approach))
    f_ret = dict(zip(FEATURE_NAMES, extract_window_features(dists_retreat, ts, irs, invs)))
    assert f_ret["d_delta"] > 25.0
    assert f_ret["v_mean"] > 35.0
    assert f_ret["trend_slope"] > 35.0


def test_collection_and_preprocessing_cli_end_to_end(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    out_csv = tmp_path / "processed" / "features.csv"

    rc_gen = collection_cli_main(
        [
            "--generate-synthetic-corpus",
            "--output-dir",
            str(raw_dir),
            "--participants",
            "3",
            "--sessions-per-participant",
            "1",
            "--seed",
            "11",
        ]
    )
    assert rc_gen == 0

    rc_val = collection_cli_main(["--validate", str(raw_dir)])
    assert rc_val == 0

    rc_pre = preproc_cli_main(
        [
            "--input",
            str(raw_dir),
            "--output",
            str(out_csv),
            "--window-size",
            "10",
            "--stride",
            "2",
        ]
    )
    assert rc_pre == 0
    windows = load_windows_csv(out_csv)
    assert len(windows) > 30
    assert {w.participant_id for w in windows} == {"sim_p01", "sim_p02", "sim_p03"}
    assert all(w.data_origin == DataOrigin.SYNTHETIC_SIMULATOR.value for w in windows)


def test_interchangeable_classifiers_work_even_without_trained_model(tmp_path: Path) -> None:
    missing_model = tmp_path / "nonexistent_model.joblib"
    ml_clf = create_gesture_classifier("ml", model_path=missing_model)
    sim_clf = create_gesture_classifier("sim")
    emb_clf = create_gesture_classifier("embedded", model_path=missing_model)

    assert isinstance(ml_clf, MLGestureClassifier)
    assert isinstance(sim_clf, SimulatedGestureClassifier)
    assert isinstance(emb_clf, EmbeddedGestureClassifier)
    assert ml_clf.is_loaded is False

    frame = SensorFramePayload(distance_cm=22.0, ir_detected=False, pot_norm=0.5, valid_ultrasonic=True)
    for i in range(12):
        assert ml_clf.push_frame(frame, ts_ms=(i + 1) * 60) is None
        emb_clf.push_frame(frame, ts_ms=(i + 1) * 60)

    diag = ml_clf.get_diagnostics()
    assert diag.model_loaded is False
    assert diag.last_rejection_reason == "no_model_loaded"
    assert "NO_MODEL" in diag.format_hud_line()
