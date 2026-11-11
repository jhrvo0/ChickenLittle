"""Verifica leituras sucessivas no log serial produzido pelo cenário Wokwi.

O cenário e a simulação precisam ter terminado com sucesso antes desta análise.
Esta verificação não avalia tensões nem prova o funcionamento do circuito físico.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def verify_distances(lines: list[str]) -> tuple[float, float]:
    """Exige amostras válidas próximas de 25 cm e depois de 300 cm."""
    first: float | None = None
    for line in lines:
        try:
            message = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(message, dict) or message.get("type") != "sensor_frame":
            continue
        data = message.get("data")
        if not isinstance(data, dict) or data.get("valid_ultrasonic") is not True:
            continue
        value = data.get("distance_cm")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        if first is None and 22 <= value <= 28:
            first = float(value)
        elif first is not None and 290 <= value <= 310:
            return first, float(value)
    raise ValueError("Não encontrou leitura válida de 22–28 cm seguida de leitura válida de 290–310 cm")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial_log", type=Path, help="Arquivo de --serial-log-file")
    args = parser.parse_args()
    try:
        near, far = verify_distances(args.serial_log.read_text(encoding="utf-8").splitlines())
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Falha ao verificar log: {exc}\n")
    print(f"Leituras virtuais encontradas em ordem: {near:.2f} cm e {far:.2f} cm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
