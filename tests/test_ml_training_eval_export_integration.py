"""Testes de treinamento sem vazamento, avaliação de eventos, exportação C++ nativa e integração MotionPet."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest

from ml.classifiers import (
    EmbeddedGestureClassifier,
    MLGestureClassifier,
    SimulatedGestureClassifier,
    create_gesture_classifier,
)
from ml.collection import generate_synthetic_session
from ml.evaluation import (
    EventStabilizer,
    format_evaluation_markdown,
    generate_evaluation_report,
    save_evaluation_json,
    save_evaluation_markdown,
)
from ml.evaluation.__main__ import main as eval_cli_main
from ml.export import (
    detect_native_cpp_compiler,
    export_model_to_cpp_header,
    run_cpp_parity_verification,
    verify_zero_dynamic_allocation,
)
from ml.export.__main__ import main as export_cli_main
from ml.preprocessing import preprocess_records, save_windows_csv
from ml.schemas import (
    DataOrigin,
    ExperimentalStatus,
    PreprocessingConfig,
    StabilizerConfig,
    WindowSample,
)
from ml.training import (
    DataLeakageError,
    TrainingConfig,
    load_trained_bundle,
    save_trained_bundle,
    select_best_embeddable_bundle,
    split_windows_grouped,
    train_candidate_models,
    windows_to_xy,
)
from ml.training.__main__ import main as train_cli_main
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.app import TerminalHostClient, run_demo
from terminal.communication.protocol import GestureSource, GestureType, SensorFramePayload
from terminal.communication.transport import create_virtual_serial_pair
from terminal.renderer.ascii_terminal import TerminalAsciiRenderer


@pytest.fixture(scope="module")
def synthetic_corpus_and_windows() -> tuple[list, list[WindowSample]]:
    raw_all = []
    for p_idx in range(1, 5):
        pid = f"p{p_idx:02d}"
        for s_idx in range(1, 3):
            sid = f"{pid}_s{s_idx:02d}"
            raw_all.extend(
                generate_synthetic_session(
                    participant_id=pid,
                    session_id=sid,
                    seed=100 * p_idx + s_idx,
                    participant_bias_cm=(p_idx - 2.5) * 1.2,
                )
            )
    windows = preprocess_records(raw_all, config=PreprocessingConfig(window_size=10, stride=2))
    return raw_all, windows


def test_group_splitter_prevents_participant_and_session_leakage(
    synthetic_corpus_and_windows: tuple[list, list[WindowSample]],
) -> None:
    _, windows = synthetic_corpus_and_windows
    split = split_windows_grouped(windows, seed=42)
    assert split.strategy == "by_participant"

    p_train = {w.participant_id for w in split.train}
    p_val = {w.participant_id for w in split.val}
    p_test = {w.participant_id for w in split.test}
    assert p_train and p_val and p_test
    assert p_train.isdisjoint(p_val)
    assert p_train.isdisjoint(p_test)
    assert p_val.isdisjoint(p_test)

    # Caso com apenas 1 participante mas >= 3 sessões independentes -> fallback por sessão com aviso
    single_p_windows = [
        WindowSample(
            participant_id="solo_user",
            session_id=f"solo_s{idx % 4}",
            start_ts_ms=w.start_ts_ms,
            end_ts_ms=w.end_ts_ms,
            label=w.label,
            features=w.features,
            data_origin=w.data_origin,
        )
        for idx, w in enumerate(windows[:80])
    ]
    fb_split = split_windows_grouped(single_p_windows, seed=42)
    assert fb_split.strategy == "by_session_fallback"
    assert len(fb_split.warnings) >= 1
    s_train = {w.session_id for w in fb_split.train}
    s_val = {w.session_id for w in fb_split.val}
    s_test = {w.session_id for w in fb_split.test}
    assert s_train.isdisjoint(s_val)
    assert s_train.isdisjoint(s_test)
    assert s_val.isdisjoint(s_test)

    # Menos de 3 sessões independentes -> proíbe split com vazamento
    two_sessions_only = [w for w in single_p_windows if w.session_id in ("solo_s0", "solo_s1")]
    with pytest.raises(DataLeakageError):
        split_windows_grouped(two_sessions_only, seed=42)


def test_training_reproducibility_and_experimental_status_guard(
    synthetic_corpus_and_windows: tuple[list, list[WindowSample]],
    tmp_path: Path,
) -> None:
    _, windows = synthetic_corpus_and_windows
    t_cfg = TrainingConfig(seed=42, mlp_max_iter=1200)

    bundles_1, split_1 = train_candidate_models(windows, training_config=t_cfg)
    bundles_2, _ = train_candidate_models(windows, training_config=t_cfg)

    assert set(bundles_1.keys()) == {
        "rule_baseline",
        "decision_tree",
        "random_forest",
        "mlp_compact",
    }
    X_test, _ = windows_to_xy(split_1.test)

    for name in bundles_1:
        b1 = bundles_1[name]
        b2 = bundles_2[name]
        assert b1.experimental_status == ExperimentalStatus.AWAITING_REAL_DATA.value
        assert b1.val_f1_macro == pytest.approx(b2.val_f1_macro, abs=1e-9)
        np.testing.assert_allclose(
            b1.estimator.predict_proba(X_test),
            b2.estimator.predict_proba(X_test),
            atol=1e-9,
        )

    best = select_best_embeddable_bundle(bundles_1)
    saved_p = save_trained_bundle(best, tmp_path / "best.joblib")
    reloaded = load_trained_bundle(saved_p)
    assert reloaded.model_name == best.model_name
    assert reloaded.experimental_status == ExperimentalStatus.AWAITING_REAL_DATA.value

    # Se todas as janelas forem marcadas como real_hardware -> EVALUATED_ON_REAL_DATA
    real_tagged = [
        WindowSample(
            participant_id=w.participant_id,
            session_id=w.session_id,
            start_ts_ms=w.start_ts_ms,
            end_ts_ms=w.end_ts_ms,
            label=w.label,
            features=w.features,
            data_origin=DataOrigin.REAL_HARDWARE.value,
        )
        for w in windows
    ]
    real_bundles, _ = train_candidate_models(real_tagged, training_config=t_cfg)
    assert (
        real_bundles["decision_tree"].experimental_status
        == ExperimentalStatus.EVALUATED_ON_REAL_DATA.value
    )


def test_event_stabilizer_rejection_hysteresis_and_cooldown() -> None:
    stab = EventStabilizer(
        StabilizerConfig(
            min_confidence=0.65,
            min_consecutive_windows=2,
            cooldown_ms=700,
            require_neutral_reset=False,
        )
    )

    # 1. Rejeição por baixa confiança
    d1 = stab.update("APPROACH", confidence=0.50, ts_ms=100)
    assert d1.accepted is False
    assert d1.rejection_reason == "low_confidence"

    # 2. Supressão de NEUTRAL
    d2 = stab.update("NEUTRAL", confidence=0.95, ts_ms=200)
    assert d2.accepted is False
    assert d2.rejection_reason == "neutral"

    # 3. Primeira janela de APPROACH -> aguarda estabilização (min_consecutive_windows=2)
    d3 = stab.update("APPROACH", confidence=0.90, ts_ms=300)
    assert d3.accepted is False
    assert d3.rejection_reason == "unstable_state"

    # 4. Segunda janela consecutiva de APPROACH -> EMITIDO!
    d4 = stab.update("APPROACH", confidence=0.92, ts_ms=400)
    assert d4.accepted is True
    assert d4.emitted_label == "APPROACH"

    # 5. Terceira janela dentro do cooldown -> bloqueado contra repetição involuntária
    d5 = stab.update("APPROACH", confidence=0.94, ts_ms=650)
    assert d5.accepted is False
    assert d5.rejection_reason == "cooldown_active"

    # 6. Retorno a NEUTRAL + novo gesto após expirar cooldown -> aceito novamente
    stab.update("NEUTRAL", confidence=0.95, ts_ms=900)
    stab.update("RETREAT", confidence=0.88, ts_ms=1150)
    d6 = stab.update("RETREAT", confidence=0.91, ts_ms=1250)
    assert d6.accepted is True
    assert d6.emitted_label == "RETREAT"


def test_evaluation_report_generation_and_cpp_native_parity(
    synthetic_corpus_and_windows: tuple[list, list[WindowSample]],
    tmp_path: Path,
) -> None:
    raw_records, windows = synthetic_corpus_and_windows
    bundles, split = train_candidate_models(
        windows,
        training_config=TrainingConfig(seed=42, mlp_max_iter=1200),
    )

    report = generate_evaluation_report(bundles=bundles, test_windows=split.test)
    assert report["experimental_status"] == ExperimentalStatus.AWAITING_REAL_DATA.value
    assert set(report["models"].keys()) == {
        "rule_baseline",
        "decision_tree",
        "random_forest",
        "mlp_compact",
    }

    json_p = save_evaluation_json(report, tmp_path / "eval.json")
    md_p = save_evaluation_markdown(report, tmp_path / "eval.md")
    assert json.loads(json_p.read_text(encoding="utf-8"))["experimental_status"] == "AWAITING_REAL_DATA"
    md_text = format_evaluation_markdown(report)
    assert "AWAITING_REAL_DATA" in md_text
    assert md_p.is_file()

    # Verifica exportação C++ estática e paridade nativa compilada para os 3 modelos aprendidos
    X_test, _ = windows_to_xy(split.test)
    X_sub = X_test[:50]

    for model_key in ("decision_tree", "random_forest", "mlp_compact"):
        bundle = bundles[model_key]
        hdr_path = tmp_path / f"tinyml_{model_key}.h"
        meta = export_model_to_cpp_header(
            estimator=bundle.estimator,
            class_names=bundle.class_names,
            output_path=hdr_path,
            preprocessing_config=bundle.preprocessing_config,
            experimental_status=bundle.experimental_status,
            model_name=bundle.model_name,
        )
        assert hdr_path.is_file()
        assert meta.estimated_flash_bytes > 0
        assert verify_zero_dynamic_allocation(hdr_path) is True

        parity = run_cpp_parity_verification(
            estimator=bundle.estimator,
            header_path=hdr_path,
            X_test=X_sub,
            raw_window_records=raw_records[:12],
            preprocessing_config=bundle.preprocessing_config,
        )
        assert parity.passed is True
        assert parity.zero_dynamic_alloc_verified is True
        if detect_native_cpp_compiler() is not None:
            assert parity.compiled_natively is True
        assert parity.class_agreement_rate >= 0.999
        assert parity.max_abs_proba_diff <= 1e-4
        assert parity.max_abs_feature_diff <= 1e-3


def test_cli_pipeline_and_motionpet_ml_integration(
    synthetic_corpus_and_windows: tuple[list, list[WindowSample]],
    tmp_path: Path,
) -> None:
    _, windows = synthetic_corpus_and_windows
    csv_path = save_windows_csv(windows, tmp_path / "features.csv")
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"
    hdr_out = tmp_path / "tinyml_model.h"

    assert train_cli_main(["--input", str(csv_path), "--output-dir", str(models_dir), "--seed", "42"]) == 0
    assert (
        eval_cli_main(
            [
                "--dataset",
                str(csv_path),
                "--models-dir",
                str(models_dir),
                "--output-dir",
                str(reports_dir),
            ]
        )
        == 0
    )
    assert (
        export_cli_main(
            [
                "--model",
                str(models_dir / "best_model.joblib"),
                "--dataset",
                str(csv_path),
                "--output",
                str(hdr_out),
            ]
        )
        == 0
    )

    # Integração com SimulatedEsp32Node + TerminalHostClient + HUD 86 colunas
    ml_clf = MLGestureClassifier(
        model_path=models_dir / "best_model.joblib",
        stabilizer_config=StabilizerConfig(min_confidence=0.55, min_consecutive_windows=2, cooldown_ms=500),
    )
    assert ml_clf.is_loaded is True

    host_ep, dev_ep, _ = create_virtual_serial_pair()
    sensor_sim = SensorSimulator(seed=7, dropout_prob=0.0, noise_std_cm=0.2)
    node = SimulatedEsp32Node(endpoint=dev_ep, sensor_source=sensor_sim, classifier=ml_clf)
    client = TerminalHostClient(host_ep)

    node.boot(auto_load=False)
    sensor_sim.queue_gesture_profile(GestureType.APPROACH)
    for _ in range(14):
        node.step()
    client.poll_serial()
    client.classifier_summary = ml_clf.get_diagnostics().format_hud_line()

    assert client.last_gesture is not None
    assert client.last_gesture.source == GestureSource.TINYML
    assert client.last_gesture.gesture == GestureType.APPROACH

    rendered = client.render_frame()
    assert "CLASSIF. |" in rendered
    for line in rendered.splitlines():
        assert len(line) == TerminalAsciiRenderer.PANEL_WIDTH

    buf = io.StringIO()
    rc = run_demo(
        save_path=tmp_path / "demo_ml.save.json",
        pet_name="MLPip",
        out=buf,
        classifier_kind="ml",
        model_path=models_dir / "best_model.joblib",
    )
    assert rc == 0
    assert "CLASSIF. |" in buf.getvalue()


def test_interchangeable_classifiers_and_unloaded_fallback(tmp_path: Path) -> None:
    sim_clf = create_gesture_classifier("sim")
    ml_unloaded = create_gesture_classifier("ml", model_path=tmp_path / "missing.joblib")
    emb_clf = create_gesture_classifier("embedded")

    assert isinstance(sim_clf, SimulatedGestureClassifier)
    assert isinstance(ml_unloaded, MLGestureClassifier)
    assert isinstance(emb_clf, EmbeddedGestureClassifier)
    assert ml_unloaded.is_loaded is False

    frame = SensorFramePayload(
        distance_cm=18.0,
        valid_ultrasonic=True,
        ir_detected=True,
        pot_norm=0.5,
    )
    assert ml_unloaded.push_frame(frame, ts_ms=100) is None
    diag = ml_unloaded.get_diagnostics()
    assert diag.model_loaded is False
    assert diag.last_rejection_reason == "no_model_loaded"
    assert "NO_MODEL" in diag.format_hud_line()

    # Terminal e simulador continuam operando normalmente com teclado mesmo sem modelo treinado
    buf_unloaded = io.StringIO()
    rc_unloaded = run_demo(
        save_path=tmp_path / "demo_unloaded.save.json",
        pet_name="NoModelPip",
        out=buf_unloaded,
        classifier_kind="ml",
        model_path=tmp_path / "missing.joblib",
    )
    assert rc_unloaded == 0
    assert "NO_MODEL" in buf_unloaded.getvalue()

    buf_emb = io.StringIO()
    rc_emb = run_demo(
        save_path=tmp_path / "demo_emb.save.json",
        pet_name="EmbPip",
        out=buf_emb,
        classifier_kind="embedded",
    )
    assert rc_emb == 0
    assert "CLASSIF. |" in buf_emb.getvalue()
