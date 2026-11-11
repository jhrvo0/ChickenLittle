r"""Mede o HC-SR04 em faixas de distancia e resume precisao e taxa de falhas.

Uso, na raiz do projeto (PowerShell):
    .\.venv\Scripts\python.exe teste-hcsr04\medir_faixas.py COM3
    .\.venv\Scripts\python.exe teste-hcsr04\medir_faixas.py COM3 --distancias 10 25 50 100 --tentativas 30

Para cada distancia, o script pede que voce posicione o alvo na regua e pressione Enter.
Depois descarta o buffer antigo e le a serial ate juntar --tentativas medicoes
(validas ou SEM ECO) ou esgotar --tempo-max.

Aceita os dois formatos de saida:
  - firmware de teste: "Distancia: 39.3 cm" e "SEM ECO";
  - firmware MotionPet: JSON sensor_frame com distance_cm e valid_ultrasonic.

O resultado vale apenas para a montagem descrita em --config. Nao mede tensao
e nao prova a montagem fisica.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

import serial

RE_DISTANCIA = re.compile(r"Distancia:\s*([\d.]+)\s*cm")
RE_FALHA = re.compile(r"SEM ECO|TIMEOUT")
PASTA = Path(__file__).resolve().parent
CONFIG_PADRAO = "VCC 3V3, ECHO direto ao GPIO34, sem divisor"
COLUNAS = [
    "data", "config", "ref_cm", "tentativas", "validas", "falhas",
    "taxa_validas_pct", "mediana_cm", "media_cm", "desvio_cm",
    "min_cm", "max_cm", "erro_cm", "erro_pct", "encerrou_por_tempo",
]


def interpretar(linha: str) -> tuple[str, float | None] | None:
    """Devolve ('valida', cm), ('falha', None), ou None se a linha nao for medicao."""
    linha = linha.strip()
    if not linha:
        return None
    if linha.startswith("{"):
        try:
            msg = json.loads(linha)
        except ValueError:
            return None
        if not isinstance(msg, dict) or msg.get("type") != "sensor_frame":
            return None
        data = msg.get("data")
        if not isinstance(data, dict):
            return None
        cm = data.get("distance_cm")
        if data.get("valid_ultrasonic") is True and isinstance(cm, (int, float)) and not isinstance(cm, bool):
            return ("valida", float(cm))
        return ("falha", None)
    m = RE_DISTANCIA.search(linha)
    if m:
        return ("valida", float(m.group(1)))
    if RE_FALHA.search(linha):
        return ("falha", None)
    return None


def medir_faixa(ser, ref_cm, tentativas, tempo_max_s, bruto):
    """Le a serial ate juntar 'tentativas' medicoes. Devolve (validas, falhas, encerrou_por_tempo)."""
    ser.reset_input_buffer()
    validas: list[float] = []
    falhas = 0
    fim = time.monotonic() + tempo_max_s
    while len(validas) + falhas < tentativas:
        if time.monotonic() >= fim:
            return validas, falhas, True
        texto = ser.readline().decode("utf-8", "replace")
        if not texto.strip():
            continue
        bruto.write(f"[ref={ref_cm:g}] {texto.rstrip()}\n")
        r = interpretar(texto)
        if r is None:
            continue
        if r[0] == "valida":
            validas.append(r[1])
        else:
            falhas += 1
    return validas, falhas, False


def resumir(ref_cm, validas, falhas, config, por_tempo):
    tentativas = len(validas) + falhas
    linha = {
        "data": datetime.now().isoformat(timespec="seconds"),
        "config": config,
        "ref_cm": ref_cm,
        "tentativas": tentativas,
        "validas": len(validas),
        "falhas": falhas,
        "taxa_validas_pct": round(100.0 * len(validas) / tentativas, 1) if tentativas else "",
        "encerrou_por_tempo": por_tempo,
    }
    if validas:
        mediana = statistics.median(validas)
        linha.update(
            mediana_cm=round(mediana, 2),
            media_cm=round(statistics.fmean(validas), 2),
            desvio_cm=round(statistics.stdev(validas), 2) if len(validas) > 1 else 0.0,
            min_cm=min(validas),
            max_cm=max(validas),
            erro_cm=round(mediana - ref_cm, 2),
            erro_pct=round(100.0 * (mediana - ref_cm) / ref_cm, 1),
        )
    return linha


def imprimir(r):
    ref = r["ref_cm"]
    if "mediana_cm" not in r:
        print(f"  ref {ref:g} cm: nenhuma leitura valida em {r['tentativas']} tentativas")
        return
    print(
        f"  ref {ref:g} cm | validas {r['validas']}/{r['tentativas']} ({r['taxa_validas_pct']:.0f}%)"
        f" | mediana {r['mediana_cm']:.1f} cm | desvio {r['desvio_cm']:.1f} cm"
        f" | erro {r['erro_cm']:+.1f} cm ({r['erro_pct']:+.0f}%)"
        f" | faixa {r['min_cm']:.1f}-{r['max_cm']:.1f} cm"
        + ("  [encerrou por tempo]" if r["encerrou_por_tempo"] else "")
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Mede o HC-SR04 em faixas de distancia.")
    p.add_argument("porta", help="porta serial, por exemplo COM3")
    p.add_argument("--distancias", type=float, nargs="+", default=[10, 25, 50, 100],
                   help="referencias em cm (padrao: 10 25 50 100)")
    p.add_argument("--tentativas", type=int, default=30,
                   help="medicoes por distancia, validas mais falhas (padrao: 30)")
    p.add_argument("--tempo-max", type=float, default=90.0,
                   help="limite de tempo por distancia, em segundos (padrao: 90)")
    p.add_argument("--config", default=CONFIG_PADRAO, help="descricao da montagem, gravada no CSV")
    args = p.parse_args()

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = PASTA / f"resultados_{marca}.csv"
    bruto_path = PASTA / f"resultados_{marca}_brutas.txt"

    ser = serial.Serial()
    ser.port = args.porta
    ser.baudrate = 115200
    ser.timeout = 0.5
    ser.dtr = False  # evita o reset automatico ao abrir a porta
    ser.rts = False
    ser.open()
    print(f"Montagem: {args.config}")
    print(f"Gravando em {csv_path.name} e {bruto_path.name}")

    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f_csv, \
                bruto_path.open("w", encoding="utf-8") as bruto:
            escritor = csv.DictWriter(f_csv, fieldnames=COLUNAS)
            escritor.writeheader()
            for ref in args.distancias:
                input(f"\nPosicione o alvo a {ref:g} cm (regua) e pressione Enter... ")
                validas, falhas, por_tempo = medir_faixa(ser, ref, args.tentativas, args.tempo_max, bruto)
                r = resumir(ref, validas, falhas, args.config, por_tempo)
                escritor.writerow(r)
                f_csv.flush()
                imprimir(r)
    finally:
        ser.close()
    print(f"\nPronto. CSV: {csv_path}")


if __name__ == "__main__":
    main()
