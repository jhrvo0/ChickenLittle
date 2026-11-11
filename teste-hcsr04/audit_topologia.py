"""Auditoria de topologia da protoboard (HC-SR04 + ESP32 NodeMCU-32S 38 pinos).

Modela os furos como a protoboard fisica: em cada coluna, A-E e F-J sao dois
grupos separados (canal central). Le a montagem DECLARADA pelo usuario e
calcula quais pinos ficam no mesmo no eletrico e a tensao teorica do divisor.

Nao e medicao: so verifica se a montagem declarada e coerente consigo mesma e
com o perfil de pinagem do repositorio (hardware/data/boards.json, que ainda
esta marcado ASSUMED_PENDING_PHYSICAL_CONFIRMATION).

Uso: python teste-hcsr04/audit_topologia.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOARD = json.loads((ROOT / "hardware/data/boards.json").read_text(encoding="utf-8"))
PROFILE = BOARD["profiles"]["esp32_devkit_38pin"]["sides"]

# ESP32 ocupa as colunas 1..19 com a USB voltada para a coluna 1 (como no guia).
# J2 (esquerda do desenho) -> linha I (metade F-J); J3 -> linha B (metade A-E).
# Pino n (1..19 a partir da antena) fica na coluna 20-n.
ESP_ROW = {"J2": "I", "J3": "B"}


def half(row: str) -> str:
    return "AE" if row in "ABCDE" else "FJ"


def hole(text: str):
    text = text.strip().upper()
    return int(text[:-1]), text[-1]


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


uf = UF()
used = {}  # furo -> descricao (detecta dois itens no mesmo furo)


def strip(col, row):
    return ("strip", col, half(row))


def put(desc, furo):
    col, row = hole(furo)
    if (col, row) in used:
        print(f"  [CONFLITO] furo {furo} usado por '{used[(col, row)]}' e por '{desc}'")
    used[(col, row)] = desc
    return strip(col, row)


# --- pinos da ESP32 ---------------------------------------------------------
esp_pin_node = {}
for side, pins in PROFILE.items():
    for idx, (name, gpio, kind, _note) in enumerate(pins, start=1):
        col = 20 - idx
        row = ESP_ROW[side]
        node = put(f"ESP32 {side}.{idx} {name}", f"{col}{row}")
        esp_pin_node[(side, idx, name)] = node
        uf.union(("esp", name, side, idx), node)

# nomes logicos nos
GND_ESP = [("esp", n, s, i) for (s, i, n) in esp_pin_node if n == "GND"]
for g in GND_ESP[1:]:
    uf.union(GND_ESP[0], g)  # todos os GND da placa sao o mesmo no

# --- montagem declarada pelo usuario ----------------------------------------
# (descricao, furo_a, furo_b) para fios e resistores.
declared = [
    ("sensor VCC  -> 1J", "sensor.VCC", "1J"),
    ("sensor TRIG -> 10A", "sensor.TRIG", "10A"),
    ("sensor ECHO -> 22D", "sensor.ECHO", "22D"),
    ("sensor GND  -> 30A", "sensor.GND", "30A"),
    ("fio GND 13A -> 30D", "13A", "30D"),
    ("R1 1k  22C-26C", "22C", "26C"),
    ("R2 1k  26B-29B", "26B", "29B"),
    ("R3 300 29A-30E", "29A", "30E"),
    ("fio divisor 26A -> 15J", "26A", "15J"),
]
RES = {"R1 1k  22C-26C": 1000.0, "R2 1k  26B-29B": 1000.0, "R3 300 29A-30E": 300.0}

print("== Furos")
res_edges = []
for desc, a, b in declared:
    na = ("sensor", a) if a.startswith("sensor.") else put(desc, a)
    nb = ("sensor", b) if b.startswith("sensor.") else put(desc, b)
    if desc in RES:
        res_edges.append((desc, na, nb, RES[desc]))
    else:
        uf.union(na, nb)

# --- nos eletricos (so fios; resistores separam os nos) ---------------------
def net(x):
    return uf.find(x)


def find_pin(name, side=None, nth=1):
    hits = [k for k in esp_pin_node if k[2] == name and (side is None or k[0] == side)]
    hits.sort(key=lambda k: (k[0], k[1]))
    return hits[nth - 1]


pin5v = find_pin("5V")
pin34 = find_pin("IO34")
pin5 = find_pin("IO5")
n_gnd = net(("esp", "GND", "J3", 1))

checks = []


def chk(ok, text):
    checks.append(ok)
    print(("  [OK]   " if ok else "  [FALHA]") + " " + text)


print("== Nos (somente fios)")
chk(net(("sensor", "sensor.VCC")) == net(("esp", "5V", pin5v[0], pin5v[1])),
    f"VCC do sensor no mesmo no do pino 5V (coluna {20 - pin5v[1]}, {pin5v[0]})")
chk(net(("sensor", "sensor.GND")) == n_gnd, "GND do sensor no mesmo no dos pinos GND da ESP32")
chk(net(("sensor", "sensor.TRIG")) == net(("esp", "IO5", pin5[0], pin5[1])),
    f"TRIG do sensor no mesmo no do GPIO5 (coluna {20 - pin5[1]})")
n_mid = net(("esp", "IO34", pin34[0], pin34[1]))
chk(net(("sensor", "sensor.ECHO")) != n_mid, "ECHO do sensor NAO esta ligado direto ao GPIO34 (obrigatorio)")
chk(net(("sensor", "sensor.ECHO")) != net(("esp", "5V", pin5v[0], pin5v[1])), "ECHO nao esta em curto com 5V")
chk(net(("sensor", "sensor.TRIG")) != n_gnd, "TRIG nao esta em curto com GND")

print("== Divisor")
by = {d: (net(a), net(b), r) for d, a, b, r in res_edges}
r1, r2, r3 = by["R1 1k  22C-26C"], by["R2 1k  26B-29B"], by["R3 300 29A-30E"]
n_echo = net(("sensor", "sensor.ECHO"))
chk(r1[0] == n_echo or r1[1] == n_echo, "R1 tem uma perna no no do ECHO")
other = r1[1] if r1[0] == n_echo else r1[0]
chk(other == n_mid, "outra perna de R1 vai ao no do GPIO34 (ponto medio)")
chk(n_mid in (r2[0], r2[1]), "R2 sai do ponto medio")
n_low = r2[1] if r2[0] == n_mid else r2[0]
chk(n_low in (r3[0], r3[1]), "R2 encadeia em R3")
n_end = r3[1] if r3[0] == n_low else r3[0]
chk(n_end == n_gnd, "R3 termina em GND")

rtop = r1[2]
rbot = r2[2] + r3[2]
print(f"  Vout teorico (ECHO=5,0 V): {5.0 * rbot / (rtop + rbot):.3f} V  (R_top={rtop:.0f}, R_bot={rbot:.0f})")
print(f"  Vout teorico (ECHO=4,5 V): {4.5 * rbot / (rtop + rbot):.3f} V")
print(f"  Corrente no GND em ECHO=5 V: {5.0 / (rtop + rbot) * 1000:.2f} mA")

print("== Pinagem usada (perfil do repositorio; NAO confirmado fisicamente)")
for key in (pin5v, pin5, pin34, find_pin("GND", "J3", 2)):
    print(f"  coluna {20 - key[1]:>2} lado {key[0]} pino#{key[1]:>2} = {key[2]}")

print("== Pontos a confirmar na placa real")
print("  1. Furos A e J ficam livres (pinos da ESP32 nas linhas B e I)? A tabela do usuario cita 10A/13A")
print("     como TRIG/GND e tambem como pinos da ESP32; so e possivel se os pinos estao em B/I.")
print("  2. Coluna 13 (lado J3) e GND, coluna 10 e IO5, coluna 15 (lado J2) e IO34, coluna 1 e 5V.")
print("     Isso vem de um perfil marcado ASSUMED_PENDING_PHYSICAL_CONFIRMATION.")
print("  3. Guia isolado manda o GND do sensor em 2J; o usuario relatou 30A. Eletricamente equivalente")
print("     se coluna 30 estiver no GND (verificado acima), mas a documentacao divergiu da montagem.")

sys.exit(0 if all(checks) else 1)
