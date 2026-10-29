"""CLI do Painel de Diagnóstico em Tempo Real (`python -m terminal.diag`)."""

from __future__ import annotations

import argparse

from terminal.diag.panel import run_diagnostic_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m terminal.diag",
        description=(
            "MotionPet Ciclo 5 — Painel ASCII de diagnostico em tempo real "
            "(distancia, serie temporal, classe, confianca, eventos, perdas e status TinyML)."
        ),
    )
    parser.add_argument("--serial-port", default=None, help="Porta USB Serial real do ESP32 (ex: COM3).")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate serial.")
    parser.add_argument("--simulate", action="store_true", help="Executa com dados simulados.")
    parser.add_argument("--replay", default=None, help="Reproduz arquivo .jsonl/.csv gravado.")
    parser.add_argument(
        "--classifier",
        choices=["sim", "ml", "embedded"],
        default="embedded",
        help="Motor de classificacao inspecionado.",
    )
    parser.add_argument(
        "--model-path",
        default="data/models/best_model.joblib",
        help="Bundle .joblib quando '--classifier ml' e utilizado.",
    )
    parser.add_argument("--frames", type=int, default=32, help="Quantidade de quadros a processar.")
    parser.add_argument("--compact", action="store_true", help="Modo compacto de 60 colunas.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Atualizacao diferencial continua in-place no terminal.",
    )
    args = parser.parse_args(argv)

    if not args.serial_port and not args.simulate and not args.replay:
        parser.error("Informe '--serial-port COMx', '--simulate' ou '--replay CAMINHO'.")

    run_diagnostic_session(
        serial_port=args.serial_port,
        simulate=args.simulate,
        replay_path=args.replay,
        baudrate=args.baudrate,
        classifier_kind=args.classifier,
        model_path=args.model_path,
        max_frames=args.frames,
        compact=args.compact,
        interactive_differential=args.live,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
