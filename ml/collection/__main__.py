"""CLI de coleta de séries temporais (serial física ou simulador) e validação (`python -m ml.collection`)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from ml.collection.collector import (
    SerialSessionRecorder,
    parse_gesture_schedule,
    record_simulated_session,
    save_session_csv,
    save_session_jsonl,
)
from ml.collection.synthetic import generate_synthetic_corpus
from ml.collection.validator import validate_session_records
from ml.preprocessing.windowing import load_raw_records_from_path
from ml.schemas import DataOrigin
from terminal.communication.transport import PySerialEndpoint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.collection",
        description="MotionPet ML — Captura de sessoes temporais (USB Serial ou Simulador) e validacao",
    )
    parser.add_argument(
        "--validate",
        default=None,
        help="Valida integridade e ordenacao temporal de um arquivo .jsonl/.csv ou diretorio.",
    )
    parser.add_argument(
        "--generate-synthetic-corpus",
        action="store_true",
        help="Gera corpus sintetico multi-participante (exclusivo para testar codigo do pipeline).",
    )
    parser.add_argument("--participants", type=int, default=5, help="Participantes sinteticos.")
    parser.add_argument(
        "--sessions-per-participant",
        type=int,
        default=2,
        help="Sessoes por participante sintetico.",
    )
    parser.add_argument("--simulate", action="store_true", help="Captura uma sessao via simulador.")
    parser.add_argument("--serial-port", default=None, help="Porta USB Serial real (ex: COM3).")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    parser.add_argument("--participant", default="p01", help="Identificador do participante.")
    parser.add_argument("--session-id", default=None, help="Identificador unico da sessao.")
    parser.add_argument("--gesture", default="APPROACH", help="Classe alvo para captura simples.")
    parser.add_argument("--samples", type=int, default=40, help="Numero de amostras na captura simples.")
    parser.add_argument(
        "--schedule",
        default=None,
        help="Cronograma continuo com transicoes, ex: 'NEUTRAL:15,APPROACH:12,NEUTRAL:15'.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Diretorio de saida das sessoes gravadas.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed para reprodutibilidade.")
    args = parser.parse_args(argv)

    if args.validate:
        records = load_raw_records_from_path(args.validate)
        by_session: dict[str, list] = defaultdict(list)
        for rec in records:
            by_session[rec.session_id].append(rec)

        all_ok = True
        for sid in sorted(by_session.keys()):
            rep = validate_session_records(by_session[sid])
            status = "VALIDA" if rep.valid else "INVALIDA"
            print(
                f"[{status}] {sid}: {rep.total_samples} amostras | "
                f"invalid_ratio={rep.invalid_ratio:.1%} | mean_dt={rep.mean_dt_ms}ms | "
                f"classes={rep.labels_distribution} | origem={rep.data_origins}"
            )
            for err in rep.errors:
                print(f"   ERRO: {err}")
            for warn in rep.warnings:
                print(f"   AVISO: {warn}")
            all_ok = all_ok and rep.valid

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

    schedule = (
        parse_gesture_schedule(args.schedule)
        if args.schedule
        else [(args.gesture.strip().upper(), args.samples)]
    )
    ts_slug = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = args.session_id or f"session_{ts_slug}_{args.participant}"

    if args.serial_port:
        ep = PySerialEndpoint(port=args.serial_port, baudrate=args.baudrate)
        try:
            recorder = SerialSessionRecorder(ep, data_origin=DataOrigin.REAL_HARDWARE)
            records = recorder.record_schedule(
                participant_id=args.participant,
                session_id=session_id,
                schedule=schedule,
                on_segment_start=lambda lbl, cnt: print(
                    f">>> Execute agora: {lbl} ({cnt} amostras)..."
                ),
            )
        finally:
            ep.close()
    elif args.simulate:
        records = record_simulated_session(
            participant_id=args.participant,
            session_id=session_id,
            schedule=schedule,
            seed=args.seed,
        )
    else:
        parser.error(
            "Especifique --serial-port COMx, --simulate, --generate-synthetic-corpus ou --validate."
        )
        return 2

    out_dir = Path(args.output_dir)
    jsonl_p = save_session_jsonl(records, out_dir / f"{session_id}.jsonl")
    csv_p = save_session_csv(records, out_dir / f"{session_id}.csv")
    report = validate_session_records(records)
    meta_p = out_dir / f"{session_id}.meta.json"
    meta_p.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(
        f"[OK] Sessao '{session_id}' gravada em '{jsonl_p}' e '{csv_p}' "
        f"({report.total_samples} amostras, valida={report.valid})"
    )
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
