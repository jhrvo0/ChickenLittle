"""CLI de coleta de séries temporais (serial física ou simulador) e validação (`python -m ml.collection`)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import defaultdict
from pathlib import Path

from ml.collection.collector import (
    DEFAULT_GUIDED_REAL_SCHEDULE,
    SerialSessionRecorder,
    build_real_collection_campaign_plan,
    build_session_metadata,
    parse_gesture_schedule,
    probe_firmware_version_from_endpoint,
    record_simulated_session,
    save_session_csv,
    save_session_jsonl,
)
from ml.collection.synthetic import generate_synthetic_corpus
from ml.collection.validator import validate_session_records
from ml.preprocessing.windowing import load_raw_records_from_path
from ml.schemas import EXPERIMENTAL_GESTURE_CLASSES, DataOrigin
from simulator.esp32_sim_node import SIMULATED_FW_VERSION
from terminal.communication.transport import PySerialEndpoint

_GESTURE_INSTRUCTIONS: dict[str, str] = {
    "NEUTRAL": "REPOUSO (NEUTRAL): Mantenha a area frontal livre ou mao fora da zona (<55 cm vazio).",
    "APPROACH": "APROXIMAR (APPROACH): Traga a mao aberta de ~45 cm ate ~12 cm na frente do HC-SR04.",
    "RETREAT": "AFASTAR (RETREAT): Recue a mao aberta de ~12 cm ate ~45 cm de forma continua.",
    "HOLD": "SUSTENTAR (HOLD): Mantenha a palma parada estavel entre 15 cm e 25 cm do sensor.",
    "IMPULSE": "[EXPERIMENTAL] IMPULSE: Toque rapido de ida e volta na zona frontal.",
    "DOUBLE": "[EXPERIMENTAL] DOUBLE: Dois pulsos rapidos consecutivos.",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.collection",
        description="MotionPet ML — Captura guiada de sessoes temporais (USB Serial ou Simulador) e validacao",
    )
    parser.add_argument(
        "--plan-campaign",
        action="store_true",
        help="Exibe plano estruturado de coleta real multi-participante (>= 5 participantes, sem dados sinteticos).",
    )
    parser.add_argument(
        "--validate",
        default=None,
        help="Valida integridade e ordenacao temporal de um arquivo .jsonl/.csv ou diretorio.",
    )
    parser.add_argument(
        "--require-real-origin",
        action="store_true",
        help="Ao usar --validate, falha caso encontre qualquer amostra 'synthetic_simulator'.",
    )
    parser.add_argument(
        "--generate-synthetic-corpus",
        action="store_true",
        help="Gera corpus sintetico multi-participante (exclusivo para testar codigo do pipeline).",
    )
    parser.add_argument("--participants", type=int, default=5, help="Numero de participantes.")
    parser.add_argument(
        "--sessions-per-participant",
        type=int,
        default=2,
        help="Sessoes por participante sintetico.",
    )
    parser.add_argument("--simulate", action="store_true", help="Captura uma sessao via simulador.")
    parser.add_argument("--serial-port", default=None, help="Porta USB Serial real (ex: COM3).")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    parser.add_argument("--participant", default="p01", help="Identificador anonimizado do participante (ex: p01).")
    parser.add_argument("--session-id", default=None, help="Identificador unico da sessao.")
    parser.add_argument("--gesture", default="APPROACH", help="Classe alvo para captura simples.")
    parser.add_argument("--samples", type=int, default=40, help="Numero de amostras na captura simples.")
    parser.add_argument(
        "--schedule",
        default=None,
        help=f"Cronograma continuo, ex: '{DEFAULT_GUIDED_REAL_SCHEDULE}'.",
    )
    parser.add_argument(
        "--guided",
        action="store_true",
        help="Ativa instrucoes passo a passo na tela e protocolo padrao de 4 classes principais.",
    )
    parser.add_argument(
        "--countdown-sec",
        type=float,
        default=0.0,
        help="Contagem regressiva em segundos antes de cada segmento no modo real.",
    )
    parser.add_argument(
        "--conditions",
        default="bancada_padrao_iluminacao_interna_vel_normal",
        help="Condicoes fisicas da coleta (ambiente, posicao, distancia, velocidade, iluminacao).",
    )
    parser.add_argument(
        "--firmware-version",
        default=None,
        help="Versao do firmware (consultada automaticamente via DIAG na serial se omitida).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Diretorio de saida das sessoes gravadas.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed para reprodutibilidade.")
    args = parser.parse_args(argv)

    if args.plan_campaign:
        plan = build_real_collection_campaign_plan(num_participants=args.participants)
        print("=== PLANO DE CAMPANHA DE COLETA REAL — MOTIONPET CICLO 5 ===")
        print(f"Classes principais:   {', '.join(plan['core_classes'])}")
        print(f"Classes experimentais:{', '.join(plan['experimental_classes'])} (nao prioritarias)")
        print(f"Regra anti-vazamento: {plan['strict_anti_synthetic_rule']}")
        print(f"Participantes (>=5):  {plan['recommended_participants_count']}\n")
        for p in plan["participants"]:
            print(f"  * {p['participant_id']} -> {p['assigned_split_role']}")
            for s in p["sessions"]:
                print(f"      - {s['session_id']} [{s['conditions']}]: {s['guidance']}")
        return 0

    if args.validate:
        records = load_raw_records_from_path(args.validate)
        by_session: dict[str, list] = defaultdict(list)
        for rec in records:
            by_session[rec.session_id].append(rec)

        all_ok = True
        for sid in sorted(by_session.keys()):
            rep = validate_session_records(by_session[sid])
            has_synth = any(o != DataOrigin.REAL_HARDWARE.value for o in rep.data_origins)
            origin_ok = not (args.require_real_origin and has_synth)
            status = "VALIDA" if (rep.valid and origin_ok) else "INVALIDA"
            print(
                f"[{status}] {sid}: {rep.total_samples} amostras | "
                f"invalid_ratio={rep.invalid_ratio:.1%} | mean_dt={rep.mean_dt_ms}ms | "
                f"classes={rep.labels_distribution} | origem={rep.data_origins}"
            )
            for err in rep.errors:
                print(f"   ERRO: {err}")
            if not origin_ok:
                print(
                    "   ERRO: Detectada origem nao-fisica ('synthetic_simulator') com "
                    "--require-real-origin ativo! Proibido misturar dados sinteticos."
                )
            for warn in rep.warnings:
                print(f"   AVISO: {warn}")
            all_ok = all_ok and rep.valid and origin_ok

        return 0 if all_ok else 1

    if args.generate_synthetic_corpus:
        files = generate_synthetic_corpus(
            output_dir=args.output_dir,
            n_participants=args.participants,
            sessions_per_participant=args.sessions_per_participant,
            seed=args.seed,
        )
        print(
            f"[OK] Corpus sintetico gerado ({len(files)} sessoes .jsonl + .csv) em '{args.output_dir}' "
            "[STATUS: synthetic_simulator — APENAS VALIDACAO DE PIPELINE]"
        )
        return 0

    if args.schedule:
        schedule = parse_gesture_schedule(args.schedule)
    elif args.guided:
        schedule = parse_gesture_schedule(DEFAULT_GUIDED_REAL_SCHEDULE)
    else:
        schedule = [(args.gesture.strip().upper(), args.samples)]

    ts_slug = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = args.session_id or f"session_{ts_slug}_{args.participant}"

    parse_errors = 0
    seq_drops = 0

    def _guided_prompt(lbl: str, cnt: int) -> None:
        hint = _GESTURE_INSTRUCTIONS.get(lbl, f"Execute o gesto {lbl}")
        exp_tag = " [CLASSE EXPERIMENTAL]" if lbl in EXPERIMENTAL_GESTURE_CLASSES else ""
        print(f"\n>>> SEGMENTO {lbl}{exp_tag} ({cnt} amostras): {hint}")
        if args.countdown_sec > 0 and not args.simulate:
            time.sleep(max(0.0, float(args.countdown_sec)))

    if args.serial_port:
        ep = PySerialEndpoint(port=args.serial_port, baudrate=args.baudrate)
        try:
            fw_ver = args.firmware_version or probe_firmware_version_from_endpoint(ep)
            ep.write_line("START")
            recorder = SerialSessionRecorder(ep, data_origin=DataOrigin.REAL_HARDWARE)
            records = recorder.record_schedule(
                participant_id=args.participant,
                session_id=session_id,
                schedule=schedule,
                on_segment_start=_guided_prompt,
            )
            parse_errors = recorder.parse_errors
            seq_drops = recorder.seq_drops
        finally:
            ep.close()
    elif args.simulate:
        fw_ver = args.firmware_version or SIMULATED_FW_VERSION
        if args.guided:
            for lbl, cnt in schedule:
                _guided_prompt(lbl, cnt)
        records = record_simulated_session(
            participant_id=args.participant,
            session_id=session_id,
            schedule=schedule,
            seed=args.seed,
        )
    else:
        parser.error(
            "Especifique --serial-port COMx, --simulate, --plan-campaign, "
            "--generate-synthetic-corpus ou --validate."
        )
        return 2

    out_dir = Path(args.output_dir)
    jsonl_p = save_session_jsonl(records, out_dir / f"{session_id}.jsonl")
    csv_p = save_session_csv(records, out_dir / f"{session_id}.csv")
    report = validate_session_records(records)
    meta_dict = build_session_metadata(
        records=records,
        validation_report=report,
        schedule=schedule,
        conditions=args.conditions,
        firmware_version=fw_ver,
        serial_port=args.serial_port,
        parse_errors=parse_errors,
        seq_drops=seq_drops,
    )
    meta_p = out_dir / f"{session_id}.meta.json"
    meta_p.write_text(json.dumps(meta_dict, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(
        f"[OK] Sessao '{session_id}' gravada em '{jsonl_p}' e '{csv_p}' "
        f"({report.total_samples} amostras, fw={fw_ver}, condicoes='{args.conditions}', valida={report.valid})"
    )
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
