"""Roda a bateria de testes de bancada (somente leitura serial; NAO grava firmware) e imprime tudo.

Uso (Windows): de dois cliques em teste_bancada.bat na raiz do repositorio. A saida vai para teste_bancada_saida.txt.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time


def run(args: list[str], timeout: float = 90) -> int:
    print(f"\n$ python -m terminal.bench {' '.join(args)}", flush=True)
    try:
        p = subprocess.run([sys.executable, "-m", "terminal.bench", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print("  (tempo esgotado)", flush=True)
        return -1
    print(p.stdout, p.stderr, sep="", flush=True)
    print(f"  -> codigo de saida {p.returncode}", flush=True)
    return p.returncode


def raw_capture(port: str) -> None:
    """Le a serial crua (115200) por alguns segundos, incluindo o log de boot apos um reset pelo DTR/RTS."""
    import serial
    print("\n--- SERIAL CRUA (115200), com reset da placa ---", flush=True)
    try:
        with serial.Serial(port, 115200, timeout=0.2) as s:
            s.dtr = False; s.rts = True; time.sleep(0.15); s.rts = False      # pulso no EN (reset), IO0 alto (boot normal)
            t0, lines, buf = time.time(), 0, b""
            while time.time() - t0 < 10 and lines < 150:
                buf += s.read(512)
                while b"\n" in buf and lines < 150:
                    ln, buf = buf.split(b"\n", 1)
                    print("  |", ln.decode("utf-8", "replace").rstrip(), flush=True)
                    lines += 1
            if buf:
                print("  |", buf[:300].decode("utf-8", "replace"), flush=True)
            print(f"--- fim da captura ({lines} linhas) ---", flush=True)
    except Exception as e:
        print("Falha ao abrir a porta:", e, flush=True)


def main() -> int:
    print("=== MotionPet: teste de bancada automatico ===", time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    print("Python:", sys.version.split()[0], flush=True)
    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial NAO instalado (pip install pyserial).", flush=True)
        return 1
    ports = list(list_ports.comports())
    for p in ports:
        print(f"PORTA {p.device}: {p.description} | VID:PID={p.vid}:{p.pid} | {p.hwid}", flush=True)
    keys = ("CP210", "CH340", "CH910", "USB-SERIAL", "USB SERIAL", "SILICON LABS", "UART", "ESP32", "JTAG")
    cand = [p for p in ports if any(k in (p.description or "").upper() or k in (p.manufacturer or "").upper() for k in keys)] or ports
    if not cand:
        print("NENHUMA porta serial encontrada: a ESP32 nao foi reconhecida (cabo de carga? driver CP210x/CH340?).", flush=True)
        return 2
    port = cand[0].device
    print(f"\n>>> Usando {port}", flush=True)
    raw_capture(port)
    run(["check-deps"])
    run(["diag", "--serial-port", port])
    run(["inspect", "--serial-port", port, "--duration", "6"])
    run(["stage", "A", "--serial-port", port])
    run(["stage", "B", "--serial-port", port, "--r1", "1000", "--r2", "1300"])
    run(["stage", "C", "--serial-port", port, "--component", "ir"])   # potenciometro removido
    run(["stage", "D", "--serial-port", port])
    print("\n=== FIM ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
