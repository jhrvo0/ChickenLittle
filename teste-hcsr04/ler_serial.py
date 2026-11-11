"""Le a serial da ESP32 por N segundos e imprime/grava as linhas (sem reiniciar a placa).

Uso: .venv\\Scripts\\python.exe teste-hcsr04\\ler_serial.py [porta] [segundos] [arquivo_log]
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
log = sys.argv[3] if len(sys.argv) > 3 else None

# dtr/rts em False evita o reset automatico ao abrir a porta
ser = serial.Serial()
ser.port, ser.baudrate, ser.timeout = port, 115200, 0.5
ser.dtr = False
ser.rts = False
ser.open()
out = open(log, "w", encoding="utf-8") if log else None
end = time.time() + secs
while time.time() < end:
    line = ser.readline().decode("utf-8", "replace").rstrip()
    if line:
        print(line, flush=True)
        if out:
            out.write(line + "\n")
ser.close()
if out:
    out.close()
