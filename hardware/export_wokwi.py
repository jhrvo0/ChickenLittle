"""Exportador Wokwi (diagram.json, wokwi.toml, cenario de teste) a partir da netlist canonica.

Limites HONESTOS (documentados tambem em hardware/wokwi/README.md):
  * o Wokwi simula logica digital; NAO valida o divisor resistivo nem a compatibilidade eletrica real;
  * nao existe modelo Wokwi do modulo TCRT5000: ele e omitido (a rede IR_DO fica sem simulacao);
  * lint verifica o diagrama, mas nao confirma o funcionamento do firmware nem da montagem fisica.
"""
from __future__ import annotations

import json

from . import model
from .model import Layout

ESP_ID = "esp"
PART_IDS = {"M1": "ultra", "P1": "pot", "R1": "r1", "R2": "r2", "R3": "r3", "R4": "r4", "R5": "r5", "M3": "lcd"}
# O quarto GND da placa fotografada e representado pelo mesmo GND virtual;
# a equivalencia de pinos fisicos do modelo Wokwi permanece hipotese.
GND_MAP = {"J2.14": "GND.1", "J2.18": "GND.1", "J3.1": "GND.2", "J3.7": "GND.3"}


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
        # Na Wokwi os GND da placa ja sao um so: manter apenas um terminal de placa por rede.
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
#   wokwi-cli hardware/wokwi --scenario scenarios/hcsr04.test.yaml
# Verifica apenas que existem quadros validos apos cada ajuste; NAO confere o valor de distancia.
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

**Referencia do CAD paralelo historico.** A montagem fisica atual usa [o guia final I2C](../guia_montagem_final.html).
O diagrama padrao abaixo so representa o estagio C (sem LCD); os antigos D/E exportados usam LCD paralelo.
O cenario do HC-SR04 simula distancias, nao valida o circuito real.

Arquivos gerados por `python -m hardware.build` a partir de `hardware/netlist/motionpet.netlist.json`:

- `diagram.json` — estagio C: ESP32-DevKitC V4, HC-SR04 e resistores R1-R3 do divisor. O LCD (estagio D) nao esta no diagrama padrao; o potenciometro foi removido da montagem.
- `wokwi.toml` — aponta para o firmware compilado pelo PlatformIO (`pio run -d firmware`).
- `scenarios/hcsr04.test.yaml` — cenario proposto com distancias 25 cm e 300 cm. Espera quadros validos, mas nao confirma os valores lidos ou a mudanca de distancia. Suporte ao controle `distance` tambem precisa ser verificado na versao usada.

## O que o Wokwi NAO prova
- Nao e medicao com multimetro e **nao valida o divisor resistivo** (a simulacao e digital). Nao comprova compatibilidade eletrica.
- Nao ha modelo do TCRT5000: a rede `IR_DO` nao e simulada.
- Os nomes de pino seguem exemplos publicos do Wokwi (`esp:5`, `esp:34`, `esp:5V`, `esp:GND.1`...). Qual `GND.n` e qual pino fisico e **assumido**.

## Estado de verificacao (honesto)
Em 2026-10-29, `wokwi-cli` 0.29.1 verificou o diagrama sem erros; informou que o tipo `board-esp32-devkit-c-v4` nao esta documentado e pode mudar. O cenario **nao foi executado**: requer token e compilacao do firmware. Para verificar na sua maquina:

```powershell
iwr https://wokwi.com/ci/install.ps1 -useb | iex          # instalador oficial (inspecione antes de rodar)
$env:WOKWI_CLI_TOKEN = "<token do painel Wokwi CI>"        # NAO grave no Git
wokwi-cli lint hardware/wokwi
pio run -d firmware
wokwi-cli hardware/wokwi --scenario scenarios/hcsr04.test.yaml --serial-log-file wokwi-serial.log
if ($LASTEXITCODE -eq 0) { python hardware/wokwi/verify_distances.py wokwi-serial.log }
```
O analisador exige uma leitura valida entre 22 e 28 cm seguida de outra entre 290 e 310 cm. Ele deve ser usado somente depois da execucao bem-sucedida do cenario; nao prova tensoes ou comportamento fisico. O controle de distancia e o proprio cenario ainda precisam ser confirmados no Wokwi. A CLI interpreta o caminho do cenario relativamente a `hardware/wokwi`.
"""


def write_all(lay: Layout, out_dir) -> list[str]:
    from pathlib import Path
    out = Path(out_dir)
    (out / "scenarios").mkdir(parents=True, exist_ok=True)
    (out / "diagram.json").write_text(json.dumps(build_diagram(lay), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "wokwi.toml").write_text(WOKWI_TOML, encoding="utf-8", newline="\n")
    (out / "scenarios" / "hcsr04.test.yaml").write_text(SCENARIO, encoding="utf-8", newline="\n")
    (out / "README.md").write_text(README, encoding="utf-8", newline="\n")
    return ["diagram.json", "wokwi.toml", "scenarios/hcsr04.test.yaml", "README.md"]
