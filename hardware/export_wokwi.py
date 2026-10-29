"""Exportador Wokwi (diagram.json, wokwi.toml, cenario de teste) a partir da netlist canonica.

Limites HONESTOS (documentados tambem em hardware/wokwi/README.md):
  * o Wokwi simula logica digital; NAO valida o divisor resistivo nem a compatibilidade eletrica real;
  * nao existe modelo Wokwi do modulo TCRT5000: ele e omitido (a rede IR_DO fica sem simulacao);
  * `wokwi-cli` nao pode ser executado no ambiente de build (download/rede bloqueados); o diagram.json foi
    gerado a partir do catalogo publico de pecas e NAO foi passado por `wokwi-cli lint`.
"""
from __future__ import annotations

import json

from . import model
from .model import Layout

ESP_ID = "esp"
PART_IDS = {"M1": "ultra", "P1": "pot", "R1": "r1", "R2": "r2", "R3": "r3", "R4": "r4", "R5": "r5", "M3": "lcd"}
GND_MAP = {"J2.14": "GND.1", "J3.1": "GND.2", "J3.7": "GND.3"}   # ASSUMIDO (tudo e GND; irrelevante eletricamente)


def esp_pin(lay: Layout, pin: str) -> str:
    bp = lay.board.resolve(pin)
    if bp.kind == "ground":
        return GND_MAP[bp.pid]
    if bp.label in ("3V3", "5V", "VP", "VN", "EN"):
        return bp.label
    if bp.gpio is not None:
        return str(bp.gpio)
    raise ValueError(pin)


def wokwi_terminal(lay: Layout, ref_pin: str) -> str | None:
    ref, pin = ref_pin.split(".", 1)
    t = lay.components[ref]["type"]
    if t == "esp32":
        return f"{ESP_ID}:{esp_pin(lay, pin)}"
    if t == "hc_sr04":
        return f"{PART_IDS[ref]}:{pin}"
    if t == "resistor":
        return f"{PART_IDS[ref]}:{'1' if pin == 'A' else '2'}"
    if t == "potentiometer":
        return f"{PART_IDS[ref]}:{ {'END_A': 'VCC', 'WIPER': 'SIG', 'END_B': 'GND'}[pin] }"
    if t == "lcd2004a":
        return f"{PART_IDS[ref]}:{pin}"
    return None                                  # TCRT5000: sem modelo Wokwi


NET_COLOR = {"LCD_RS": "blue", "LCD_E": "green", "LCD_D4": "white", "LCD_D5": "brown", "LCD_D6": "orange", "LCD_D7": "purple", "5V": "red", "3V3": "orange", "GND": "black", "TRIG": "gold", "ECHO_5V": "red", "ECHO_NODE": "green",
             "POT_WIPER": "purple"}


def build_diagram(lay: Layout, stage: str = "C", distance_cm: int = 25) -> dict:
    parts = [{"type": "board-esp32-devkit-c-v4", "id": ESP_ID, "top": 0, "left": 0, "attrs": {}}]
    present = {c["ref"] for c in lay.comps(stage)}
    y = -120.0
    def ohms(ref):
        return {"value": str(lay.components[ref]["ohms"])} if ref in lay.components else {}
    spec = {
        "M1": ("wokwi-hc-sr04", {"distance": str(distance_cm)}, -160, 240),
        "R1": ("wokwi-resistor", ohms("R1"), -40, 260),
        "R2": ("wokwi-resistor", ohms("R2"), 30, 260),
        "R3": ("wokwi-resistor", ohms("R3"), 100, 260),
        "P1": ("wokwi-potentiometer", {}, 150, 260),
        "R4": ("wokwi-resistor", ohms("R4"), 170, 420),
        "R5": ("wokwi-resistor", ohms("R5"), 230, 420),
        "M3": ("wokwi-lcd2004", {"pins": "full"}, -60, 420),
    }
    for ref, (ptype, attrs, top, left) in spec.items():
        if ref in present:
            parts.append({"type": ptype, "id": PART_IDS[ref], "top": top, "left": left, "attrs": attrs})
    conns = [["esp:TX", "$serialMonitor:RX", "", []], ["esp:RX", "$serialMonitor:TX", "", []]]
    for net, pins in lay.logical_nets(stage):
        terms = []
        for p in sorted(pins):
            t = wokwi_terminal(lay, p)
            if t and t not in terms:
                terms.append(t)
        # na Wokwi os 3 GND da placa ja sao um so: manter apenas um terminal de placa por rede
        esp_terms = [t for t in terms if t.startswith(ESP_ID + ":GND")]
        if len(esp_terms) > 1:
            terms = [t for t in terms if t not in esp_terms[1:]]
        if len(terms) < 2:
            continue
        terms.sort(key=lambda t: (not t.startswith(ESP_ID + ":"), t))   # a placa e o "hub" da rede
        root = terms[0]
        col = NET_COLOR.get(net["name"], "blue")
        for t in terms[1:]:
            conns.append([root, t, col, []])
    return {"version": 1, "author": "MotionPet (gerado de hardware/netlist)", "editor": "wokwi",
            "parts": parts, "connections": conns, "dependencies": {},
            "_comment": ("GERADO por python -m hardware.build. TCRT5000 nao possui modelo Wokwi e foi omitido. "
                         "O divisor 1k / (1k+300) existe no diagrama mas o Wokwi NAO o valida analogicamente.")}


WOKWI_TOML = """[wokwi]
version = 1
# Compile antes:  pio run -d firmware   (gera firmware/.pio/build/esp32dev/*, que esta no .gitignore)
firmware = '../../firmware/.pio/build/esp32dev/firmware.bin'
elf = '../../firmware/.pio/build/esp32dev/firmware.elf'
"""

SCENARIO = """name: 'MotionPet - ESP32 + HC-SR04 emitindo sensor_frame (JSON Lines v1)'
version: 1
author: 'MotionPet'
# ESTE CENARIO NAO FOI EXECUTADO no ambiente de build (wokwi-cli indisponivel). Executar com:
#   WOKWI_CLI_TOKEN=<seu token> wokwi-cli hardware/wokwi --scenario hardware/wokwi/scenarios/hcsr04.test.yaml
steps:
  - wait-serial: 'sensor_frame'
  - set-control:
      part-id: ultra
      name: distance
      value: 25
  - delay: 800ms
  - wait-serial: '"valid_ultrasonic":true'
  - set-control:
      part-id: ultra
      name: distance
      value: 300
  - delay: 800ms
  - wait-serial: '"valid_ultrasonic":true'
"""

README = """# Simulacao Wokwi do MotionPet (gerada)

Arquivos gerados por `python -m hardware.build` a partir de `hardware/netlist/motionpet.netlist.json`:

- `diagram.json` — ESP32-DevKitC V4 (`board-esp32-devkit-c-v4`, 38 pinos), HC-SR04, R1-R5, potenciometro e LCD 2004A em modo paralelo de 4 bits (estagios A-D).
- `wokwi.toml` — aponta para o firmware compilado pelo PlatformIO (`pio run -d firmware`).
- `scenarios/hcsr04.test.yaml` — cenario de teste (sensor_frame, distancias 25 cm e 300 cm).

## O que o Wokwi NAO prova
- Nao e medicao com multimetro e **nao valida o divisor resistivo** (a simulacao e digital). Nao comprova compatibilidade eletrica.
- Nao ha modelo do TCRT5000: a rede `IR_DO` nao e simulada.
- Os nomes de pino seguem exemplos publicos do Wokwi (`esp:5`, `esp:34`, `esp:5V`, `esp:GND.1`...). Qual `GND.n` e qual pino fisico e **assumido**.

## Estado de verificacao (honesto)
`wokwi-cli` nao pode ser instalado/executado no ambiente de geracao (download do binario negado e `wokwi.com` bloqueado),
portanto **`wokwi-cli lint` e os cenarios NAO foram executados**. Para verificar na sua maquina:

```powershell
iwr https://wokwi.com/ci/install.ps1 -useb | iex          # instalador oficial (inspecione antes de rodar)
$env:WOKWI_CLI_TOKEN = "<token do painel Wokwi CI>"        # NAO grave no Git
wokwi-cli lint hardware/wokwi
pio run -d firmware
wokwi-cli hardware/wokwi --scenario hardware/wokwi/scenarios/hcsr04.test.yaml
```
"""


def write_all(lay: Layout, out_dir) -> list[str]:
    from pathlib import Path
    out = Path(out_dir)
    (out / "scenarios").mkdir(parents=True, exist_ok=True)
    (out / "diagram.json").write_text(json.dumps(build_diagram(lay), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "wokwi.toml").write_text(WOKWI_TOML, encoding="utf-8")
    (out / "scenarios" / "hcsr04.test.yaml").write_text(SCENARIO, encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    return ["diagram.json", "wokwi.toml", "scenarios/hcsr04.test.yaml", "README.md"]
