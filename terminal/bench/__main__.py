"""CLI amigável do Assistente de Bancada do MotionPet (`python -m terminal.bench`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from terminal.bench.assistant import (
    DEFAULT_BENCH_LOG_PATH,
    _open_bench_session,
    check_dependencies,
    format_safety_and_wiring_checklist,
    inspect_telemetry_stream,
    list_serial_ports,
    query_device_diag,
    record_bench_log_entry,
    run_stage_a,
    run_stage_b,
    run_stage_c,
    run_stage_d,
)
from terminal.bench.e2e import DEFAULT_E2E_REPORT_PATH, run_pet_launch_e2e_validation
from terminal.bench.pinout import (
    PREFERRED_ECHO_R1_OHM,
    PREFERRED_ECHO_R2_OHM,
    evaluate_echo_divider,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m terminal.bench",
        description=(
            "MotionPet Ciclo 5 — Assistente de Bancada, Reconciliacao Eletrica e "
            "Validacao Incremental (NUNCA energiza nem grava firmware sem autorizacao manual)."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # 1. check-deps
    p_deps = sub.add_parser("check-deps", help="Verifica dependencias Python, PlatformIO, firmware e TinyML.")
    p_deps.add_argument("--json", action="store_true", help="Saida em JSON estruturado.")

    # 2. ports
    p_ports = sub.add_parser("ports", help="Lista portas COM seriais e identifica pontes USB-UART ESP32.")
    p_ports.add_argument("--json", action="store_true", help="Saida em JSON estruturado.")

    # 3. checklist
    sub.add_parser("checklist", help="Exibe tabela canonica unica de pinos e checklist de seguranca.")

    # 4. divider
    p_div = sub.add_parser("divider", help="Calcula e valida o divisor resistivo do ECHO (limite <= 3,30 V).")
    p_div.add_argument("--r1", type=float, default=PREFERRED_ECHO_R1_OHM, help="R1 em Ohms (ECHO -> No).")
    p_div.add_argument("--r2", type=float, default=PREFERRED_ECHO_R2_OHM, help="R2 em Ohms (No -> GND).")
    p_div.add_argument("--vin", type=float, default=5.00, help="Tensao nominal ECHO em Volts.")
    p_div.add_argument("--vin-max", type=float, default=5.25, help="Tensao maxima USB/ECHO em Volts.")
    p_div.add_argument("--measured-v", type=float, default=None, help="Tensao real medida no multimetro (V).")

    # 5. diag
    p_diag = sub.add_parser("diag", help="Envia comando DIAG e consulta versao, memoria e estado.")
    p_diag.add_argument("--serial-port", default=None, help="Porta COM fisica (ex: COM3).")
    p_diag.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    p_diag.add_argument("--simulate", action="store_true", help="Executa contra o simulador virtual.")
    p_diag.add_argument("--log-path", default=str(DEFAULT_BENCH_LOG_PATH), help="Arquivo de log JSON.")

    # 6. inspect
    p_insp = sub.add_parser("inspect", help="Inspeciona telemetria JSONL, frequencia Hz, timeouts e perdas.")
    p_insp.add_argument("--serial-port", default=None, help="Porta COM fisica (ex: COM3).")
    p_insp.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    p_insp.add_argument("--simulate", action="store_true", help="Executa contra o simulador virtual.")
    p_insp.add_argument("--duration", type=float, default=3.0, help="Duracao da captura em segundos.")
    p_insp.add_argument("--expected-period-ms", type=int, default=70, help="Periodo nominal esperado (ms).")
    p_insp.add_argument("--reference-cm", type=float, default=None, help="Distancia fisica de referencia (cm).")
    p_insp.add_argument("--log-path", default=str(DEFAULT_BENCH_LOG_PATH), help="Arquivo de log JSON.")

    # 7. stage A|B|C|D
    p_stg = sub.add_parser("stage", help="Executa validacao incremental guiada (Etapas A, B, C ou D).")
    p_stg.add_argument("stage_id", choices=["A", "B", "C", "D", "a", "b", "c", "d"], help="Etapa alvo.")
    p_stg.add_argument("--serial-port", default=None, help="Porta COM fisica (ex: COM3).")
    p_stg.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    p_stg.add_argument("--simulate", action="store_true", help="Simula a etapa (nao substitui validacao fisica).")
    p_stg.add_argument("--r1", type=float, default=PREFERRED_ECHO_R1_OHM, help="[Etapa B] R1 em Ohms.")
    p_stg.add_argument("--r2", type=float, default=PREFERRED_ECHO_R2_OHM, help="[Etapa B] R2 em Ohms.")
    p_stg.add_argument("--measured-echo-v", type=float, default=None, help="[Etapa B] Tensao medida no divisor (V).")
    p_stg.add_argument("--reference-cm", type=float, default=None, help="[Etapa B] Distancia medida na regua (cm).")
    p_stg.add_argument("--component", choices=["ir", "pot", "both"], default="both", help="[Etapa C] Periferico.")
    p_stg.add_argument("--vcc-measured-v", type=float, default=None, help="[Etapa C] Tensao medida no pino 3V3 (V).")
    p_stg.add_argument(
        "--rw-not-grounded",
        action="store_true",
        help="[Etapa D] Indica que RW ainda NAO foi aterrado (aciona bloqueio de seguranca).",
    )
    p_stg.add_argument("--lcd-vdd-v", type=float, default=None, help="[Etapa D] Tensao medida no VDD do LCD (V).")
    p_stg.add_argument("--log-path", default=str(DEFAULT_BENCH_LOG_PATH), help="Arquivo de log JSON.")

    # 8. e2e
    p_e2e = sub.add_parser("e2e", help="Executa teste ponta a ponta (Gestos -> Serial -> Pet Launch -> Save).")
    p_e2e.add_argument("--serial-port", default=None, help="Porta COM fisica (ex: COM3).")
    p_e2e.add_argument("--simulate", action="store_true", help="Executa bateria ponta a ponta em simulacao.")
    p_e2e.add_argument("--classifier", choices=["sim", "ml", "embedded"], default="sim", help="Classificador.")
    p_e2e.add_argument("--model-path", default="data/models/best_model.joblib", help="Caminho do modelo ML.")
    p_e2e.add_argument("--listen-sec", type=float, default=15.0, help="Duracao de escuta no hardware fisico.")
    p_e2e.add_argument("--report-path", default=str(DEFAULT_E2E_REPORT_PATH), help="Relatorio JSON E2E.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "check-deps":
        rep = check_dependencies()
        if args.json:
            print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("=== MOTIONPET BENCH - VERIFICACAO DE DEPENDENCIAS ===")
            print(f"Python:             {rep.python_version} ({'OK' if rep.python_ok else 'INCOMPATIVEL'})")
            for k, ok in rep.packages.items():
                print(f"Pacote {k:<13}: {'INSTALADO' if ok else 'AUSENTE'}")
            print(f"PlatformIO CLI:     {rep.platformio_cli_path or 'NAO ENCONTRADO'}")
            print(f"Firmware compilado: {'SIM' if rep.firmware_binary_exists else 'NAO'} ({rep.firmware_binary_path})")
            print(f"Header TinyML C++:  {rep.tinyml_model_name} [STATUS: {rep.tinyml_experimental_status}]")
            print(f"Tabela de pinagem:  {'SEM CONFLITOS (GPIO34 CANONICO)' if rep.pinout_conflict_free else 'COM CONFLITOS'}")
            for note in rep.notes:
                print(f"  * NOTA: {note}")
        return 0 if rep.ready_for_bench else 1

    if args.subcommand == "ports":
        ports = list_serial_ports()
        if args.json:
            print(json.dumps([p.to_dict() for p in ports], indent=2, ensure_ascii=False))
            return 0
        print("=== PORTAS SERIAIS DETECTADAS NO SISTEMA ===")
        if not ports:
            print("NENHUMA porta COM detectada no momento.")
            print("Orientacao para iniciantes:")
            print("  1. Use um cabo USB-C de DADOS (cabos apenas de carga nao criam porta COM).")
            print("  2. Conecte APENAS o ESP32 desenergizado de sensores ainda nao revisados.")
            print("  3. Verifique no Gerenciador de Dispositivos se o driver CP210x ou CH340 esta ativo.")
            print("  4. Status atual do Ciclo 5 permanece: PENDING_PHYSICAL_VALIDATION.")
            return 0
        for p in ports:
            tag = "[PROVAVEL ESP32]" if p.likely_esp32 else "[PORTA SERIAL]"
            print(f"  {p.device:<8} {tag:<17} {p.description} ({p.hwid})")
        return 0

    if args.subcommand == "checklist":
        print(format_safety_and_wiring_checklist())
        return 0

    if args.subcommand == "divider":
        res = evaluate_echo_divider(
            r1_ohm=args.r1,
            r2_ohm=args.r2,
            vin_nominal_v=args.vin,
            vin_max_v=args.vin_max,
            measured_peak_v=args.measured_v,
        )
        verdict = "APROVADO E SEGURO (<= 3,30 V)" if res.safe else "REPROVADO - RISCO DE DANO AO ESP32!"
        print(f"=== AVALIACAO DO DIVISOR DO ECHO (HC-SR04 -> GPIO34): {verdict} ===")
        print(f"R1 (ECHO -> No):   {res.r1_ohm:.1f} Ohm | R2 (No -> GND): {res.r2_ohm:.1f} Ohm | Fator={res.ratio:.4f}")
        print(f"Vout @ {res.vin_nominal_v:.2f} V:     {res.vout_nominal_v:.3f} V")
        print(f"Vout @ {res.vin_max_v:.2f} V max: {res.vout_max_v:.3f} V (Teto maximo permitido: 3.300 V)")
        if res.measured_peak_v is not None:
            print(f"Medido multimetro: {res.measured_peak_v:.3f} V")
        for r in res.reasons:
            print(f"  [!] {r}")
        return 0 if res.safe else 1

    if args.subcommand == "diag":
        if not args.serial_port and not args.simulate:
            parser.error("Informe '--serial-port COMx' para hardware real ou '--simulate' para simulador.")
        ep, step_cb, origin_tag, cleanup = _open_bench_session(
            args.serial_port,
            args.simulate,
            args.baudrate,
        )
        try:
            snap = query_device_diag(ep, step_callback=step_cb)
        finally:
            cleanup()
        record_bench_log_entry("DIAG", origin_tag, True, snap.to_dict(), (), args.log_path)
        print(f"=== DIAGNOSTICO DO DISPOSITIVO [ORIGEM: {origin_tag}] ===")
        print(f"Firmware:    {snap.fw_version} | Origem reportada: {snap.origin}")
        print(f"Pinout:      {snap.pinout_status}")
        print(f"Aquisicao:   {'ATIVA' if snap.acquisition_active else 'PAUSADA'} @ {snap.sample_period_ms} ms")
        print(f"Amostras:    {snap.total_samples} (timeouts US: {snap.ultrasonic_timeouts})")
        print(f"TinyML:      {snap.model_name} [STATUS: {snap.experimental_status}] (inf={snap.last_infer_us} us)")
        print(f"Eventos:     emitidos={snap.events_emitted} | janelas rejeitadas={snap.windows_rejected}")
        print(f"Modo/LCD:    modo={snap.active_mode} | quadros LCD={snap.lcd_frames} | NVS writes={snap.nvs_writes}")
        print(f"Heap Livre:  {snap.free_heap_bytes} bytes | RTT={snap.roundtrip_ms:.2f} ms")
        return 0

    if args.subcommand == "inspect":
        if not args.serial_port and not args.simulate:
            parser.error("Informe '--serial-port COMx' para hardware real ou '--simulate' para simulador.")
        ep, step_cb, origin_tag, cleanup = _open_bench_session(
            args.serial_port,
            args.simulate,
            args.baudrate,
            sim_distance_cm=args.reference_cm,
        )
        sim_steps = max(10, int(round((args.duration * 1000.0) / max(1, args.expected_period_ms))))
        try:
            rep_t = inspect_telemetry_stream(
                ep,
                duration_sec=args.duration,
                expected_period_ms=args.expected_period_ms,
                reference_cm=args.reference_cm,
                validation_origin=origin_tag,
                step_callback=step_cb,
                simulated_steps=sim_steps if step_cb is not None else None,
            )
        finally:
            cleanup()
        record_bench_log_entry("INSPECT", origin_tag, rep_t.passed, rep_t.to_dict(), rep_t.problems, args.log_path)
        print(f"=== INSPECAO DE TELEMETRIA [ORIGEM: {rep_t.validation_origin}] ===")
        print(
            f"Quadros sensor_frame: {rep_t.sensor_frames_count} | "
            f"Freq efetiva: {rep_t.effective_hz:.2f} Hz (dt={rep_t.mean_dt_ms:.1f} +/- {rep_t.jitter_std_ms:.1f} ms)"
        )
        print(
            f"Timeouts US:          {rep_t.ultrasonic_timeouts_count} ({rep_t.timeout_ratio:.1%}) | "
            f"Perdas seq: {rep_t.seq_gaps_detected} | Erros JSON: {rep_t.parse_errors}"
        )
        print(
            f"Distancia (cm):       min={rep_t.distance_min_cm} | media={rep_t.distance_mean_cm} | "
            f"max={rep_t.distance_max_cm} (std={rep_t.distance_std_cm})"
        )
        if rep_t.reference_cm is not None:
            print(
                f"Comparacao ref:       alvo={rep_t.reference_cm} cm | erro={rep_t.reference_abs_error_cm} cm "
                f"({'OK' if rep_t.reference_within_tolerance else 'FORA DA TOLERANCIA'})"
            )
        print(
            f"IR / Potenciometro:   ir_true={rep_t.ir_true_count}, transicoes={rep_t.ir_transitions} | "
            f"pot=[{rep_t.pot_min}..{rep_t.pot_max}]"
        )
        print(f"Status final:         {'APROVADO' if rep_t.passed else 'COM PROBLEMAS'}")
        for prob in rep_t.problems:
            print(f"  [!] {prob}")
        return 0 if rep_t.passed else 1

    if args.subcommand == "stage":
        sid = args.stage_id.upper()
        if sid == "A":
            res_s = run_stage_a(
                serial_port=args.serial_port,
                simulate=args.simulate,
                baudrate=args.baudrate,
                log_path=args.log_path,
            )
        elif sid == "B":
            res_s = run_stage_b(
                serial_port=args.serial_port,
                simulate=args.simulate,
                baudrate=args.baudrate,
                r1_ohm=args.r1,
                r2_ohm=args.r2,
                measured_echo_v=args.measured_echo_v,
                reference_cm=args.reference_cm,
                log_path=args.log_path,
            )
        elif sid == "C":
            res_s = run_stage_c(
                serial_port=args.serial_port,
                simulate=args.simulate,
                baudrate=args.baudrate,
                component=args.component,
                vcc_measured_v=args.vcc_measured_v,
                log_path=args.log_path,
            )
        else:
            res_s = run_stage_d(
                serial_port=args.serial_port,
                simulate=args.simulate,
                baudrate=args.baudrate,
                rw_grounded=(not args.rw_not_grounded),
                lcd_vdd_v=args.lcd_vdd_v,
                log_path=args.log_path,
            )

        print(f"=== VALIDACAO INCREMENTAL - ETAPA {res_s.stage} [{res_s.validation_origin}] ===")
        print(res_s.summary)
        if sid == "D" and "reference_lcd_20x4" in res_s.details:
            print("\nComparacao Quadro LCD 20x4 (Esquerda = Referencia Simulador | Direita = Dispositivo):")
            print("  +--------------------+    +--------------------+")
            for ref_ln, dev_ln in zip(
                res_s.details["reference_lcd_20x4"],
                res_s.details["device_lcd_20x4"],
            ):
                print(f"  |{ref_ln:<20}|    |{dev_ln:<20}|")
            print("  +--------------------+    +--------------------+")
        for prob in res_s.problems:
            print(f"  [!] {prob}")
        if res_s.next_manual_action:
            print(f"Proxima acao manual: {res_s.next_manual_action}")
        return 0 if res_s.passed else 1

    if args.subcommand == "e2e":
        if not args.serial_port and not args.simulate:
            parser.error("Informe '--serial-port COMx' para E2E fisico ou '--simulate' para E2E simulado.")
        rep_e2e = run_pet_launch_e2e_validation(
            serial_port=args.serial_port,
            simulate=bool(args.simulate or not args.serial_port),
            classifier_kind=args.classifier,
            model_path=args.model_path,
            physical_listen_sec=args.listen_sec,
            report_path=args.report_path,
        )
        print(f"=== TESTE PONTA A PONTA PET LAUNCH [{rep_e2e.validation_origin}] ===")
        print(f"Classificador: {rep_e2e.classifier_kind} | Status geral: {'APROVADO' if rep_e2e.all_passed else 'PENDENTE/FALHOU'}")
        for k, ok in rep_e2e.checks.items():
            print(f"  [{'OK' if ok else 'FALHA'}] {k}")
        print(
            f"Partidas: {rep_e2e.matches_completed} | Melhor dist: {rep_e2e.best_distance_m:.2f} m | "
            f"Moedas: {rep_e2e.coins_after_match} | XP: {rep_e2e.xp_after_match}"
        )
        print(
            f"Latencia E2E: media={rep_e2e.mean_e2e_latency_ms:.3f} ms | "
            f"p95={rep_e2e.p95_e2e_latency_ms:.3f} ms | Relatorio: {Path(args.report_path)}"
        )
        return 0 if rep_e2e.all_passed else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
