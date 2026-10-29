"""Testes automatizados completos do Ciclo 5:
- Reconciliação canônica de pinagem (`GPIO34`) e segurança elétrica (`<= 3,30 V`, rejeição de `3,5 V`).
- Assistente de bancada CLI (`terminal.bench`) e comandos `DIAG`/`START`/`STOP`/`PERIOD`/`IR`.
- Validação incremental (Etapas A, B, C e D) com barreiras de bloqueio elétrico.
- Coleta guiada enriquecida (`conditions`, `firmware_version`), plano `>= 5` participantes e guarda anti-sintético.
- Seleção multicritério embarcada e pipeline completo `ml.real_pipeline` + paridade Python/C++.
- Teste ponta a ponta do `Pet Launch` e Painel de Diagnóstico em tempo real (`terminal.diag`).
"""

from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from ml.collection.__main__ import main as collection_cli_main
from ml.collection.collector import (
    build_real_collection_campaign_plan,
    save_session_jsonl,
)
from ml.collection.synthetic import generate_synthetic_corpus
from ml.preprocessing.windowing import load_raw_records_from_path
from ml.real_pipeline import execute_real_data_pipeline
from ml.schemas import (
    CORE_GESTURE_CLASSES,
    FEATURE_NAMES,
    DataOrigin,
    ExperimentalStatus,
    PreprocessingConfig,
)
from ml.training.models import TrainingConfig
from ml.training.trainer import (
    SyntheticDataContaminationError,
    TrainedBundle,
    assert_strictly_real_data,
    compute_embedded_selection_score,
    select_best_embeddable_bundle,
)
from simulator.esp32_sim_node import SimulatedEsp32Node
from simulator.sensors import SensorSimulator
from terminal.bench.__main__ import main as bench_cli_main
from terminal.bench.assistant import (
    check_dependencies,
    inspect_telemetry_stream,
    parse_diag_status,
    query_device_diag,
    run_stage_a,
    run_stage_b,
    run_stage_c,
    run_stage_d,
)
from terminal.bench.e2e import run_pet_launch_e2e_validation
from terminal.bench.pinout import (
    CANONICAL_PINOUT_TABLE,
    ESP32_GPIO_MAX_SAFE_V,
    evaluate_echo_divider,
    verify_canonical_pinout_conflicts,
)
from terminal.communication.protocol import AckPayload, MessageType, ProtocolCodec
from terminal.communication.transport import create_virtual_serial_pair
from terminal.diag.panel import DiagnosticPanelRenderer, run_diagnostic_session

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_canonical_pinout_reconciliation_and_docs_consistency() -> None:
    """Garante reconciliação única em GPIO34 para HC-SR04 ECHO e ausência de conflitos."""
    ok, issues = verify_canonical_pinout_conflicts()
    assert ok is True, f"Conflitos na tabela canonica: {issues}"

    by_signal = {(r.peripheral, r.signal): r for r in CANONICAL_PINOUT_TABLE}
    assert by_signal[("HC-SR04", "ECHO")].gpio_number == 34
    assert by_signal[("HC-SR04", "TRIG")].gpio_number == 5
    assert by_signal[("TCRT5000", "DO")].gpio_number == 35
    assert by_signal[("Potenciometro", "WIPER (cursor)")].gpio_number == 36
    assert by_signal[("LCD 2004A V1.1", "RW (pino 5)")].gpio_number is None
    assert "GND" in by_signal[("LCD 2004A V1.1", "RW (pino 5)")].esp32_pin

    pinout_h = (REPO_ROOT / "firmware" / "main" / "pinout_config.h").read_text(encoding="utf-8")
    assert "#define PIN_HCSR04_ECHO       34" in pinout_h
    assert 'MOTIONPET_PINOUT_STATUS "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"' in pinout_h
    assert 'MOTIONPET_FW_VERSION    "0.5.0-cycle5"' in pinout_h

    for doc_rel in (
        "docs/hardware_safety.md",
        "docs/bench_assembly_guide.md",
        "docs/real_data_collection_guide.md",
        "docs/cycle5_bench_checklist.md",
    ):
        doc_path = REPO_ROOT / doc_rel
        assert doc_path.is_file(), f"Documento obrigatorio ausente: {doc_rel}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content) > 400


def test_echo_voltage_divider_rejects_3v5_and_approves_2k2_3k3() -> None:
    """Regra crítica da Seção 1: 3,5 V NÃO é aceito; 2,2 kOhm + 3,3 kOhm fornece margem <= 3,30 V."""
    assert ESP32_GPIO_MAX_SAFE_V == pytest.approx(3.30)

    # Divisor preferencial Ciclo 5: R1=2.2k, R2=3.3k -> 3.00 V @ 5.0 V, 3.15 V @ 5.25 V
    pref = evaluate_echo_divider(r1_ohm=2200.0, r2_ohm=3300.0, measured_peak_v=3.02)
    assert pref.safe is True
    assert pref.has_recommended_margin is True
    assert pref.vout_nominal_v == pytest.approx(3.00, abs=1e-3)
    assert pref.vout_max_v == pytest.approx(3.15, abs=1e-3)

    # Divisor antigo 1k/2k gera 3.33 V @ 5.0 V e 3.50 V @ 5.25 V -> DEVE SER REPROVADO!
    old_1k_2k = evaluate_echo_divider(r1_ohm=1000.0, r2_ohm=2000.0)
    assert old_1k_2k.safe is False
    assert any("TENSAO PERIGOSA" in r for r in old_1k_2k.reasons)

    # Medição de 3,50 V no multímetro DEVE SER REPROVADA mesmo que os resistores declarados sejam 2.2k/3.3k
    bad_meas_3v5 = evaluate_echo_divider(r1_ohm=2200.0, r2_ohm=3300.0, measured_peak_v=3.50)
    assert bad_meas_3v5.safe is False
    assert any("3.5 V NAO e seguro" in r for r in bad_meas_3v5.reasons)


def test_simulated_node_bench_commands_and_origin_separation() -> None:
    """Verifica comandos DIAG/STOP/START/PERIOD/IR e distinção estrita SIMULATOR vs ESP32_HW."""
    host_ep, dev_ep, _ = create_virtual_serial_pair()
    node = SimulatedEsp32Node(endpoint=dev_ep, sensor_source=SensorSimulator(seed=7, sample_period_ms=70))
    node.boot(auto_load=False)
    host_ep.read_all_lines()

    snap = query_device_diag(host_ep, step_callback=node.step)
    assert snap.origin == "SIMULATOR"
    assert snap.is_physical_hardware is False
    assert snap.acquisition_active is True
    assert snap.sample_period_ms == 70

    # Pausa aquisição com STOP e confirma que nenhum sensor_frame é emitido enquanto pausado
    codec = ProtocolCodec()
    host_ep.write_line("STOP")
    node.step()
    lines_after_stop = host_ep.read_all_lines()
    acks = [
        AckPayload.from_dict(codec.decode(ln).data).status
        for ln in lines_after_stop
        if codec.decode(ln).type == MessageType.ACK
    ]
    assert "collection_stopped" in acks

    node.step()
    assert all(codec.decode(ln).type != MessageType.SENSOR_FRAME for ln in host_ep.read_all_lines())

    # Altera período via PERIOD 80, reativa com START e verifica DIAG atualizado
    host_ep.write_line("PERIOD 80")
    host_ep.write_line("START")
    node.step()
    host_ep.read_all_lines()

    snap2 = query_device_diag(host_ep, step_callback=node.step)
    assert snap2.acquisition_active is True
    assert snap2.sample_period_ms == 80

    # Verifica parsing de string real do firmware C++ (ESP32_HW)
    hw_snap = parse_diag_status(
        "diag:fw=0.5.0-cycle5,origin=ESP32_HW,pins=CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION,"
        "acq=on,per_ms=70,acq_us=1820,samp=120,to_us=2,drop_inf=0,drop_tx=0,"
        "mdl=mlp_compact,exp=EVALUATED_ON_REAL_DATA,inf_us=145,evt=8,rej=14,"
        "mode=MOTION_PET,nvs_w=1,lcd_f=42,heap=258400"
    )
    assert hw_snap.is_physical_hardware is True
    assert hw_snap.fw_version == "0.5.0-cycle5"
    assert hw_snap.windows_rejected == 14
    assert hw_snap.free_heap_bytes == 258400

    host_ep.close()
    dev_ep.close()


def test_bench_assistant_dependencies_telemetry_and_incremental_stages(tmp_path: Path) -> None:
    """Testa check-deps, inspeção de fluxo e barreiras elétricas nas Etapas A, B, C e D."""
    deps = check_dependencies(REPO_ROOT)
    assert deps.python_ok is True
    assert deps.packages["pyserial"] is True
    assert deps.packages["scikit-learn"] is True
    assert deps.pinout_conflict_free is True
    assert deps.ready_for_bench is True

    log_file = tmp_path / "bench_log.json"

    # Etapa A sem porta física não grava firmware nem finge sucesso físico
    res_a_no_hw = run_stage_a(serial_port=None, simulate=False, log_path=log_file)
    assert res_a_no_hw.passed is False
    assert res_a_no_hw.validation_origin == "PHYSICAL_ESP32"

    # Etapa A em simulação passa mas carimba SIMULATION
    res_a_sim = run_stage_a(simulate=True, log_path=log_file)
    assert res_a_sim.passed is True
    assert res_a_sim.validation_origin == "SIMULATION"

    # Etapa B bloqueia imediatamente se tensão medida for 3,50 V (> 3,30 V)
    res_b_unsafe = run_stage_b(
        simulate=True,
        r1_ohm=2200.0,
        r2_ohm=3300.0,
        measured_echo_v=3.50,
        log_path=log_file,
    )
    assert res_b_unsafe.passed is False
    assert res_b_unsafe.halted_for_electrical_safety is True

    # Etapa B física exige medição prévia no multímetro antes de conectar ao GPIO34
    res_b_missing_multimeter = run_stage_b(
        serial_port="COM99",
        simulate=False,
        measured_echo_v=None,
        log_path=log_file,
    )
    assert res_b_missing_multimeter.passed is False
    assert res_b_missing_multimeter.halted_for_electrical_safety is True

    # Etapa B simulada com divisor 2,2k/3,3k e referência de 30 cm passa
    res_b_ok = run_stage_b(
        simulate=True,
        r1_ohm=2200.0,
        r2_ohm=3300.0,
        measured_echo_v=3.00,
        reference_cm=30.0,
        log_path=log_file,
    )
    assert res_b_ok.passed is True
    assert res_b_ok.details["telemetry"]["reference_within_tolerance"] is True

    # Etapa C bloqueia alimentação de 5,0 V nos periféricos de 3,3 V
    res_c_unsafe = run_stage_c(simulate=True, component="both", vcc_measured_v=5.00, log_path=log_file)
    assert res_c_unsafe.passed is False
    assert res_c_unsafe.halted_for_electrical_safety is True

    res_c_pot = run_stage_c(simulate=True, component="pot", vcc_measured_v=3.30, log_path=log_file)
    assert res_c_pot.passed is True

    # Etapa D bloqueia se RW não estiver aterrado em GND
    res_d_unsafe = run_stage_d(simulate=True, rw_grounded=False, log_path=log_file)
    assert res_d_unsafe.passed is False
    assert res_d_unsafe.halted_for_electrical_safety is True

    res_d_ok = run_stage_d(simulate=True, rw_grounded=True, lcd_vdd_v=5.00, log_path=log_file)
    assert res_d_ok.passed is True
    assert len(res_d_ok.details["device_lcd_20x4"]) == 4

    # Verifica CLI entrypoints e persistência do histórico JSON
    assert bench_cli_main(["divider", "--r1", "2200", "--r2", "3300", "--measured-v", "3.00"]) == 0
    assert bench_cli_main(["divider", "--r1", "1000", "--r2", "2000"]) == 1
    assert bench_cli_main(["checklist"]) == 0
    saved_entries = json.loads(log_file.read_text(encoding="utf-8"))
    assert len(saved_entries) >= 8


def test_guided_collection_metadata_campaign_and_anti_synthetic_guard(tmp_path: Path) -> None:
    """Verifica plano >= 5 participantes, metadados (conditions, fw) e bloqueio de mistura sintética."""
    plan = build_real_collection_campaign_plan(num_participants=5)
    assert plan["recommended_participants_count"] == 5
    assert plan["core_classes"] == ["NEUTRAL", "APPROACH", "RETREAT", "HOLD"]
    assert set(plan["experimental_classes"]) == {"IMPULSE", "DOUBLE"}
    roles = [p["assigned_split_role"] for p in plan["participants"]]
    assert any("TEST_HELD_OUT_FINAL" in r for r in roles)
    assert any("VALIDATION_GROUP" in r for r in roles)

    out_sim = tmp_path / "sim_capture"
    rc = collection_cli_main(
        [
            "--simulate",
            "--guided",
            "--participant",
            "p01",
            "--session-id",
            "sess_p01_guided",
            "--conditions",
            "frontal_25cm_iluminacao_led_vel_media",
            "--firmware-version",
            "0.5.0-sim",
            "--output-dir",
            str(out_sim),
        ]
    )
    assert rc == 0
    meta = json.loads((out_sim / "sess_p01_guided.meta.json").read_text(encoding="utf-8"))
    assert meta["participant_id"] == "p01"
    assert meta["firmware_version"] == "0.5.0-sim"
    assert meta["collection_conditions"] == "frontal_25cm_iluminacao_led_vel_media"
    assert "ultrasonic_timeouts_count" in meta["failures_and_timeouts"]
    assert "ir_detected_ratio" in meta["ir_sensor_summary"]

    # Validação padrão passa, mas `--require-real-origin` DEVE bloquear origem synthetic_simulator!
    assert collection_cli_main(["--validate", str(out_sim)]) == 0
    assert collection_cli_main(["--validate", str(out_sim), "--require-real-origin"]) == 1

    raw_records = load_raw_records_from_path(out_sim)
    with pytest.raises(SyntheticDataContaminationError):
        assert_strictly_real_data(raw_records)


def test_multicriteria_selection_and_full_real_pipeline_execution(tmp_path: Path) -> None:
    """Garante que a seleção não usa apenas acurácia de janela e valida `execute_real_data_pipeline`."""
    # Modelo A: acurácia/F1 de janela levemente maior (0.91), mas FAR Neutro péssimo (0.40),
    # baixo F1 de evento contínuo (0.50) e Flash alta (24 KiB).
    score_bloated_noisy = compute_embedded_selection_score(
        val_f1_macro=0.91,
        val_event_f1=0.50,
        val_neutral_far=0.40,
        estimated_flash_bytes=24576,
        estimated_sram_bytes=512,
    )
    # Modelo B: F1 de janela 0.89, mas F1 de evento contínuo 0.90, FAR Neutro 0.02 e Flash 1.5 KiB.
    score_balanced_compact = compute_embedded_selection_score(
        val_f1_macro=0.89,
        val_event_f1=0.90,
        val_neutral_far=0.02,
        estimated_flash_bytes=1544,
        estimated_sram_bytes=224,
    )
    assert score_balanced_compact > score_bloated_noisy

    p_cfg = PreprocessingConfig()
    t_cfg = TrainingConfig()
    b_rf = TrainedBundle(
        model_name="random_forest",
        estimator=None,
        class_names=CORE_GESTURE_CLASSES,
        feature_names=FEATURE_NAMES,
        preprocessing_config=p_cfg,
        training_config=t_cfg,
        split_strategy="participant_grouped",
        split_warnings=(),
        data_origins=("real_hardware",),
        experimental_status=ExperimentalStatus.EVALUATED_ON_REAL_DATA.value,
        val_f1_macro=0.91,
        val_accuracy=0.92,
        val_event_f1=0.50,
        val_neutral_far=0.40,
        estimated_flash_bytes=24576,
        estimated_sram_bytes=512,
        selection_score=score_bloated_noisy,
    )
    b_mlp = TrainedBundle(
        model_name="mlp_compact",
        estimator=None,
        class_names=CORE_GESTURE_CLASSES,
        feature_names=FEATURE_NAMES,
        preprocessing_config=p_cfg,
        training_config=t_cfg,
        split_strategy="participant_grouped",
        split_warnings=(),
        data_origins=("real_hardware",),
        experimental_status=ExperimentalStatus.EVALUATED_ON_REAL_DATA.value,
        val_f1_macro=0.89,
        val_accuracy=0.89,
        val_event_f1=0.90,
        val_neutral_far=0.02,
        estimated_flash_bytes=1544,
        estimated_sram_bytes=224,
        selection_score=score_balanced_compact,
    )
    chosen = select_best_embeddable_bundle({"random_forest": b_rf, "mlp_compact": b_mlp})
    assert chosen.model_name == "mlp_compact"

    # Testa bloqueio de contaminação sintética no `execute_real_data_pipeline`
    synth_dir = tmp_path / "synth_raw"
    generate_synthetic_corpus(synth_dir, n_participants=5, sessions_per_participant=2, seed=21)
    with pytest.raises(SyntheticDataContaminationError):
        execute_real_data_pipeline(
            raw_dir=synth_dir,
            models_dir=tmp_path / "m_fail",
            reports_dir=tmp_path / "r_fail",
            export_header_path=tmp_path / "fail_model.h",
            allow_synthetic_for_dry_run=False,
        )

    # Converte fixture isolada em `tmp_path` para `real_hardware` apenas para testar o fluxo de código
    # (NUNCA sobrescreve `firmware/gestures/tinyml_model.h` do repositório!)
    real_fixture_dir = tmp_path / "real_hw_fixture"
    for jf in sorted(synth_dir.glob("*.jsonl")):
        recs = load_raw_records_from_path(jf)
        real_recs = [replace(r, data_origin=DataOrigin.REAL_HARDWARE.value) for r in recs]
        save_session_jsonl(real_recs, real_fixture_dir / jf.name)

    # Injetar 1 única amostra sintética no meio de 5 participantes reais AINDA deve bloquear!
    contaminated_dir = tmp_path / "contaminated_raw"
    for idx_f, jf in enumerate(sorted(real_fixture_dir.glob("*.jsonl"))):
        recs = load_raw_records_from_path(jf)
        if idx_f == 0:
            recs[0] = replace(recs[0], data_origin=DataOrigin.SYNTHETIC_SIMULATOR.value)
        save_session_jsonl(recs, contaminated_dir / jf.name)

    with pytest.raises(SyntheticDataContaminationError):
        execute_real_data_pipeline(
            raw_dir=contaminated_dir,
            models_dir=tmp_path / "m_contam",
            reports_dir=tmp_path / "r_contam",
            export_header_path=tmp_path / "contam_model.h",
            allow_synthetic_for_dry_run=False,
        )

    # Execução completa sobre fixture 100% `real_hardware` em diretório temporário
    tmp_hdr = tmp_path / "exported" / "tinyml_model.h"
    summary = execute_real_data_pipeline(
        raw_dir=real_fixture_dir,
        models_dir=tmp_path / "models_real",
        reports_dir=tmp_path / "reports_real",
        export_header_path=tmp_hdr,
        allow_synthetic_for_dry_run=False,
        verify_firmware_build=False,
        seed=42,
    )
    assert summary.experimental_status == ExperimentalStatus.EVALUATED_ON_REAL_DATA.value
    assert len(summary.participants) == 5
    assert summary.cpp_parity_passed is True
    assert summary.cpp_parity_agreement >= 0.999
    assert tmp_hdr.is_file()
    assert '#define TINYML_EXPERIMENTAL_STATUS            "EVALUATED_ON_REAL_DATA"' in tmp_hdr.read_text(encoding="utf-8")

    # Confirma que o header oficial do repositório permaneceu honesto (`AWAITING_REAL_DATA`)
    repo_hdr = (REPO_ROOT / "firmware" / "gestures" / "tinyml_model.h").read_text(encoding="utf-8")
    assert '#define TINYML_EXPERIMENTAL_STATUS            "AWAITING_REAL_DATA"' in repo_hdr


def test_pet_launch_e2e_harness_and_diagnostic_panel_invariants(tmp_path: Path) -> None:
    """Valida bateria E2E do Pet Launch (Seção 7) e painel ASCII `terminal.diag` (Seção 8)."""
    e2e_json = tmp_path / "e2e_report.json"
    rep = run_pet_launch_e2e_validation(simulate=True, classifier_kind="sim", report_path=e2e_json)
    assert rep.validation_origin == "SIMULATION"
    assert rep.all_passed is True
    assert all(rep.checks.values())
    assert rep.matches_completed == 1
    assert rep.best_distance_m > 0.0
    assert rep.coins_after_match > 0
    assert rep.xp_after_match > 0
    assert e2e_json.is_file()

    # Painel de diagnóstico 86 colunas e 60 colunas (compact)
    buf_std = io.StringIO()
    state_std, rendered_std = run_diagnostic_session(
        simulate=True,
        max_frames=28,
        compact=False,
        output_stream=buf_std,
    )
    assert "SIMULADOR VIRTUAL" in rendered_std
    assert state_std.total_samples == 28
    assert state_std.accepted_events_count >= 2
    for line in rendered_std.splitlines():
        assert "\t" not in line
        assert len(line) == DiagnosticPanelRenderer.PANEL_WIDTH

    buf_cmp = io.StringIO()
    _, rendered_cmp = run_diagnostic_session(
        simulate=True,
        max_frames=16,
        compact=True,
        output_stream=buf_cmp,
    )
    for line in rendered_cmp.splitlines():
        assert "\t" not in line
        assert len(line) == DiagnosticPanelRenderer.COMPACT_WIDTH
