"""Modelo eletrico/fisico canonico do MotionPet.

A netlist JSON (hardware/netlist/motionpet.netlist.json) e a UNICA fonte de verdade.
Este modulo:
  * carrega perfis de placa/modulos e a netlist;
  * modela a conectividade REAL de uma protoboard de 830 pontos (grupos de coluna e trilhos);
  * resolve o furo de cada pino de cada componente;
  * DERIVA as redes eletricas a partir dos furos/fios (nao confia no desenho);
  * valida as redes contra as redes logicas declaradas e contra regras de seguranca.

Sem dependencias externas (apenas biblioteca padrao).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
NETLIST_PATH = PKG_DIR / "netlist" / "motionpet.netlist.json"

# ----------------------------------------------------------------------------
# Geometria da protoboard (medida no SVG do Fritzing "breadboard2", 830 pontos).
# Unidades: passo de 0,1 pol = 1 "passo" (pitch). A = y 0 ... J = y 11, canal entre E e F.
# ----------------------------------------------------------------------------
ROW_Y = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 7, "G": 8, "H": 9, "I": 10, "J": 11,
         "X": -3, "W": -4, "Y": 14, "Z": 15}
LOWER_ROWS = "ABCDE"   # grupo inferior (cada coluna: A-E ligadas)
UPPER_ROWS = "FGHIJ"   # grupo superior (cada coluna: F-J ligadas)
RAIL_ROWS = "WXYZ"


@dataclass(frozen=True)
class BreadboardProfile:
    """Protoboard ATIVA (a netlist declara qual: breadboard.profile)."""
    key: str
    title: str
    n_cols: int
    rail_cols: tuple
    rails_in_this_project: bool
    fz_module_id: str
    fz_path: str
    fz_scale: float
    fz_x0: float
    fz_y_a: float
    fz_pitch: float
    fz_size: tuple
    boards: int = 1                 # quantas placas iguais encaixadas pela ponta
    cols_per_board: int = 0
    board_gap_pitch: float = 0.0    # passos extras entre a ultima coluna de uma placa e a 1a da seguinte
    rail_x_offset: float = 0.0      # furo de trilho "pinN" fica em x = N + offset (em colunas)
    rail_polarity: dict | None = None
    rail_lines_y: dict | None = None


def _load_breadboards() -> dict:
    raw = json.load(open(DATA_DIR / "breadboards.json", encoding="utf-8"))["profiles"]
    return {k: BreadboardProfile(k, v["title"], v["n_cols"], tuple(v["rail_cols"]), v["rails_in_this_project"], v["fz_module_id"],
                                 v["fz_path"], v["fz_scale"], v["fz_x0"], v["fz_y_a"], v["fz_pitch"], tuple(v["fz_size"]),
                                 v.get("boards", 1), v.get("cols_per_board", v["n_cols"]), v.get("board_gap_pitch", 0.0),
                                 v.get("rail_x_offset", 0.0), v.get("rail_polarity"), v.get("rail_lines_y"))
            for k, v in raw.items()}


BREADBOARDS: dict = {}
_ACTIVE: list = []


def breadboard_profiles() -> dict:
    if not BREADBOARDS:
        BREADBOARDS.update(_load_breadboards())
    return BREADBOARDS


def set_active_breadboard(key: str) -> BreadboardProfile:
    prof = breadboard_profiles()[key]
    _ACTIVE[:] = [prof]
    return prof


def active() -> BreadboardProfile:
    if not _ACTIVE:
        set_active_breadboard("bb400")
    return _ACTIVE[0]


def n_cols() -> int:
    return active().n_cols


def rail_cols() -> tuple:
    return active().rail_cols


def board_of(col: int) -> tuple[int, int]:
    """(numero da placa 1.., coluna impressa nessa placa)."""
    cpb = active().cols_per_board
    return (col - 1) // cpb + 1, (col - 1) % cpb + 1


def make_hole(col: int, row: str) -> str:
    """Nome do furo como o iniciante le na placa: '21J' (placa 1) ou 'P2:5E' (placa 2)."""
    b, c = board_of(col)
    return f"{c}{row}" if b == 1 else f"P{b}:{c}{row}"


def col_x(col: float) -> float:
    """Coluna (pode ser fracionaria, ex.: pontos de passagem de fios) -> x em passos, com o vao entre placas."""
    prof = active()
    if prof.boards <= 1:
        return float(col)
    k = int(max(0.0, (col - 1) // prof.cols_per_board)) if col >= prof.cols_per_board + 1 else 0
    k = min(k, prof.boards - 1)
    return float(col) + k * prof.board_gap_pitch

HOLE_RE = re.compile(r"^(?:P(\d):)?(\d{1,2})([A-JW-Z])$")
WIRE_END_RE = re.compile(r"^W\d+\.[ab]$")


class NetlistError(Exception):
    """Erro estrutural na netlist."""


@dataclass(frozen=True)
class Issue:
    level: str          # "ERROR" | "WARN" | "INFO"
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


# ----------------------------------------------------------------------------
# Furos
# ----------------------------------------------------------------------------
def parse_hole(hole: str) -> tuple[int, str]:
    m = HOLE_RE.match(hole)
    if not m:
        raise NetlistError(f"Furo invalido: {hole!r} (esperado ex.: 17A, 30J, 5Z, P2:5E)")
    prof = active()
    board = int(m.group(1) or 1)
    local, row = int(m.group(2)), m.group(3)
    if not 1 <= board <= prof.boards or not 1 <= local <= prof.cols_per_board:
        raise NetlistError(f"Placa inexistente ou coluna fora da placa: {hole!r}")
    if row in RAIL_ROWS and (not prof.rails_in_this_project or local not in prof.rail_cols):
        raise NetlistError(f"Nao existe furo de trilho {local}{row} nesta protoboard: {hole!r}")
    col = (board - 1) * prof.cols_per_board + local
    if not 1 <= col <= n_cols():
        raise NetlistError(f"Coluna fora da protoboard ({n_cols()} colunas): {hole!r}")
    return col, row


def hole_group(hole: str, rail_split: int | None = None) -> tuple:
    """Grupo eletrico (tira) a que o furo pertence na protoboard."""
    col, row = parse_hole(hole)
    if row in LOWER_ROWS:
        return ("col", col, "AE")
    if row in UPPER_ROWS:
        return ("col", col, "FJ")
    board = board_of(col)[0]
    if rail_split and col >= rail_split:
        return ("rail", board, row, "R")
    return ("rail", board, row, "L" if rail_split else "ALL")


def rail_sign(hole: str) -> str | None:
    """'+' ou '-' (cor impressa: vermelho/azul) para furos de trilho; None para o resto."""
    _, row = parse_hole(hole)
    pol = active().rail_polarity or {}
    return pol.get(row) if row in RAIL_ROWS else None


def hole_x(col: int, row: str) -> float:
    """x em passos (com vao entre placas e deslocamento dos furos de trilho)."""
    if row in RAIL_ROWS:
        board, local = board_of(col)
        return col_x(col) + active().rail_x_offset
    return col_x(col)


def hole_label(hole: str) -> str:
    """Nome curto para o iniciante: furos normais como estao; trilhos por cor/lado/placa."""
    col, row = parse_hole(hole)
    if row not in RAIL_ROWS:
        return hole
    board = board_of(col)[0]
    sign = rail_sign(hole)
    side = "baixo" if row in "WX" else "cima"
    return f"P{board} trilho {sign} ({'vermelho' if sign == '+' else 'azul'}, {side})"


def hole_tag(hole: str) -> str:
    """Etiqueta curtissima para o desenho."""
    col, row = parse_hole(hole)
    if row not in RAIL_ROWS:
        return hole
    return f"P{board_of(col)[0]} {rail_sign(hole)}"


def hole_xy(hole: str) -> tuple[float, float]:
    """Posicao do furo em passos (x = coluna, y = fileira; y cresce para CIMA)."""
    col, row = parse_hole(hole)
    return hole_x(col, row), float(ROW_Y[row])


def fz_hole_xy(hole: str) -> tuple[float, float]:
    """Posicao do furo nas coordenadas do SVG do Fritzing (unidades do SVG, y para baixo)."""
    col, row = parse_hole(hole)
    b = active()
    board, local = board_of(col)
    x = (board - 1) * b.fz_size[0] + b.fz_x0 + (local - 1 + (b.rail_x_offset if row in RAIL_ROWS else 0.0)) * b.fz_pitch
    y = b.fz_y_a - ROW_Y[row] * b.fz_pitch
    return round(x, 3), round(y, 3)


# ----------------------------------------------------------------------------
# Carregamento
# ----------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_boards() -> dict:
    return load_json(DATA_DIR / "boards.json")["profiles"]


def load_modules() -> dict:
    return load_json(DATA_DIR / "modules.json")


STAGE_ORDER = ["A", "B", "C", "D", "E"]


def stage_index(stage: str) -> int:
    return STAGE_ORDER.index(stage)


# ----------------------------------------------------------------------------
# Pinos da ESP32
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class BoardPin:
    side: str            # "J2" | "J3"
    index: int           # 1..N (a partir da extremidade da USB)
    label: str
    gpio: int | None
    kind: str
    note: str

    @property
    def pid(self) -> str:
        return f"{self.side}.{self.index}"


class BoardProfile:
    def __init__(self, key: str, data: dict):
        self.key = key
        self.data = data
        self.pins: list[BoardPin] = []
        for side, rows in data["sides"].items():
            for i, (label, gpio, kind, note) in enumerate(rows, start=1):
                self.pins.append(BoardPin(side, i, label, gpio, kind, note))
        self.by_pid = {p.pid: p for p in self.pins}
        self.by_label: dict[str, list[BoardPin]] = {}
        for p in self.pins:
            self.by_label.setdefault(p.label, []).append(p)

    @property
    def n(self) -> int:
        return self.data["pins_per_side"]

    def resolve(self, ref: str) -> BoardPin:
        """'IO34' | 'GND@J3.7' | 'J2.19'."""
        if ref in self.by_pid:
            return self.by_pid[ref]
        if "@" in ref:
            label, pid = ref.split("@", 1)
            pin = self.by_pid.get(pid)
            if pin is None or pin.label != label:
                raise NetlistError(f"Pino de placa inexistente/inconsistente: {ref!r}")
            return pin
        cands = self.by_label.get(ref, [])
        if len(cands) != 1:
            raise NetlistError(
                f"Rotulo de pino ambiguo ou inexistente: {ref!r} ({len(cands)} candidatos); use 'ROTULO@Jx.n'")
        return cands[0]

    def ref_name(self, pin: BoardPin) -> str:
        return pin.label if len(self.by_label[pin.label]) == 1 else f"{pin.label}@{pin.pid}"


# ----------------------------------------------------------------------------
# Netlist / layout
# ----------------------------------------------------------------------------
@dataclass
class Layout:
    raw: dict
    boards: dict
    modules: dict
    components: dict[str, dict] = field(default_factory=dict)
    wires: dict[str, dict] = field(default_factory=dict)
    board: BoardProfile | None = None

    # ---- construcao ----
    @classmethod
    def load(cls, path: Path | str = NETLIST_PATH) -> "Layout":
        return cls.from_raw(load_json(Path(path)))

    @classmethod
    def from_raw(cls, raw: dict) -> "Layout":
        set_active_breadboard(raw.get("breadboard", {}).get("profile", "bb400"))
        lay = cls(raw=raw, boards=load_boards(), modules=load_modules())
        lay.components = {c["ref"]: c for c in raw["components"]}
        lay.wires = {w["id"]: w for w in raw["wires"]}
        if len(lay.components) != len(raw["components"]):
            raise NetlistError("Referencias de componente duplicadas")
        if len(lay.wires) != len(raw["wires"]):
            raise NetlistError("IDs de fio duplicados")
        esp = lay.esp32()
        lay.board = BoardProfile(esp["profile"], lay.boards[esp["profile"]])
        return lay

    # ---- consultas ----
    def esp32(self) -> dict:
        for c in self.components.values():
            if c["type"] == "esp32":
                return c
        raise NetlistError("Nenhuma ESP32 na netlist")

    def present(self, item: dict, stage: str) -> bool:
        return stage_index(item["stage"]) <= stage_index(stage)

    def comps(self, stage: str) -> list[dict]:
        return [c for c in self.raw["components"] if self.present(c, stage)]

    def wires_at(self, stage: str) -> list[dict]:
        return [w for w in self.raw["wires"] if self.present(w, stage)]

    def nets_at(self, stage: str) -> list[dict]:
        return [n for n in self.raw["nets"] if self.present(n, stage)]

    # ---- furos dos pinos ----
    def esp32_pin_hole(self, pin: BoardPin) -> str:
        esp = self.esp32()
        pl = esp["placement"]
        col0 = pl["col0"]
        n = self.board.n
        usb = pl.get("usb", "left")
        if usb != "left":
            raise NetlistError("Somente USB a esquerda foi modelada nesta versao")
        # USB a esquerda: J2 fica na fileira inferior (B), J3 na superior (I); pino 1 junto a USB.
        row = pl["rows"][pin.side]
        col = col0 + (pin.index - 1)
        if not 1 <= col <= n_cols():
            raise NetlistError("ESP32 fora da protoboard")
        assert n >= pin.index
        return make_hole(col, row)

    def pin_hole(self, ref: str, pin: str) -> str:
        """Furo ocupado pelo pino 'pin' do componente 'ref' (ou erro)."""
        comp = self.components[ref]
        t = comp["type"]
        if t == "esp32":
            return self.esp32_pin_hole(self.board.resolve(pin))
        if t == "resistor":
            idx = {"A": 0, "B": 1}[pin]
            return comp["legs"][idx]
        if "pins" in comp:
            if pin not in comp["pins"]:
                raise NetlistError(f"{ref} nao tem o pino {pin!r}")
            return comp["pins"][pin]
        raise NetlistError(f"Componente sem posicionamento: {ref}")

    def component_pins(self, ref: str) -> list[str]:
        comp = self.components[ref]
        t = comp["type"]
        if t == "esp32":
            return [self.board.ref_name(p) for p in self.board.pins]
        if t == "resistor":
            return ["A", "B"]
        return list(comp["pins"].keys())

    def occupied_holes(self, stage: str) -> dict[str, list[str]]:
        """Furo -> lista de 'REF.PINO' / 'W:ID.a|b' que o ocupam."""
        occ: dict[str, list[str]] = {}
        for comp in self.comps(stage):
            if comp["type"] == "breadboard":
                continue
            for pin in self.component_pins(comp["ref"]):
                occ.setdefault(self.pin_hole(comp["ref"], pin), []).append(f"{comp['ref']}.{pin}")
        for w in self.wires_at(stage):
            occ.setdefault(w["from"], []).append(f"{w['id']}.a")
            occ.setdefault(w["to"], []).append(f"{w['id']}.b")
        return occ

    # ---- redes derivadas ----
    def extract_nets(self, stage: str) -> list[frozenset[str]]:
        """Redes fisicas (conjuntos de 'REF.PINO') derivadas da protoboard e dos fios.

        - tiras da protoboard unem os furos de um grupo;
        - cada fio une seus dois furos;
        - os pinos de mesmo rotulo de terra (GND) da ESP32 sao unidos pela placa;
        - resistores NAO unem redes (sao elementos serie).
        """
        parent: dict = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        rail_split = self.raw.get("breadboard", {}).get("rail_split")
        occ = self.occupied_holes(stage)
        for hole in occ:
            union(("hole", hole), hole_group(hole, rail_split))
        for w in self.wires_at(stage):
            union(("hole", w["from"]), ("hole", w["to"]))

        # pinos de terra da placa ligados internamente
        esp = self.esp32()
        gnd_pins = [p for p in self.board.pins if p.kind == "ground"]
        for p in gnd_pins[1:]:
            union(("hole", self.esp32_pin_hole(gnd_pins[0])), ("hole", self.esp32_pin_hole(p)))

        groups: dict = {}
        for hole, users in occ.items():
            root = find(("hole", hole))
            for u in users:
                if WIRE_END_RE.match(u):
                    continue  # pontas de fio nao sao pinos de componente
                groups.setdefault(root, set()).add(u)
        return [frozenset(pins) for pins in groups.values()]

    def pin_net_map(self, stage: str) -> dict[str, frozenset[str]]:
        out: dict[str, frozenset[str]] = {}
        for net in self.extract_nets(stage):
            for pin in net:
                out[pin] = net
        return out

    # ---- nets logicas ----
    def logical_nets(self, stage: str) -> list[tuple[dict, frozenset[str]]]:
        res = []
        for n in self.nets_at(stage):
            pins = frozenset(self.canon_pin(p) for p in n["pins"] if self.pin_present(p, stage))
            res.append((n, pins))
        return res

    def canon_pin(self, ref_pin: str) -> str:
        ref, pin = ref_pin.split(".", 1)
        comp = self.components[ref]
        if comp["type"] == "esp32":
            return f"{ref}.{self.board.ref_name(self.board.resolve(pin))}"
        return ref_pin

    def pin_present(self, ref_pin: str, stage: str) -> bool:
        ref = ref_pin.split(".", 1)[0]
        return self.present(self.components[ref], stage)


# ----------------------------------------------------------------------------
# Calculos eletricos
# ----------------------------------------------------------------------------
def divider_vout(v_in: float, r1: float, r2: float) -> float:
    return v_in * r2 / (r1 + r2)


def divider_extremes(v_in_min: float, v_in_max: float, r1: float, r2: float, tol: float) -> tuple[float, float]:
    """(Vout_min, Vout_max) com tolerancia de resistores e faixa de Vin (pior caso)."""
    vmax = v_in_max * (r2 * (1 + tol)) / (r1 * (1 - tol) + r2 * (1 + tol))
    vmin = v_in_min * (r2 * (1 - tol)) / (r1 * (1 + tol) + r2 * (1 - tol))
    return vmin, vmax


def resistor_bands(ohms: float, tolerance: float, color_code: dict | None = None) -> list[str]:
    """Cores das faixas (4 faixas) de um resistor."""
    cc = color_code or load_modules()["resistor_color_code"]
    exp = 0
    val = float(ohms)
    while val >= 100:
        val /= 10
        exp += 1
    d1, d2 = int(val) // 10, int(val) % 10
    tol_color = {0.05: "gold", 0.1: "silver", 0.01: "brown", 0.02: "red"}[round(tolerance, 2)]
    return [cc[str(d1)], cc[str(d2)], cc[str(exp)], tol_color]


def fmt_ohms(ohms: float) -> str:
    if ohms >= 1000:
        k = ohms / 1000
        return (f"{k:g}".replace(".", ",")) + " kΩ"
    return f"{ohms:g} Ω"


# ----------------------------------------------------------------------------
# Validacao
# ----------------------------------------------------------------------------
V_LIMIT_GPIO = 3.30
SAFE_MODEL_STATUSES = {"PENDING_PHYSICAL_VALIDATION"}


def validate(layout: Layout, stage: str) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda lvl, code, msg: issues.append(Issue(lvl, code, msg))  # noqa: E731

    # 1) furos validos e sem dupla ocupacao
    try:
        occ = layout.occupied_holes(stage)
        for hole in occ:
            parse_hole(hole)
        for w in layout.wires_at(stage):
            parse_hole(w["from"])
            parse_hole(w["to"])
    except NetlistError as exc:
        return [Issue("ERROR", "HOLE_INVALID", str(exc))]
    for hole, users in sorted(occ.items()):
        if len(users) > 1:
            add("ERROR", "HOLE_DOUBLE_OCCUPIED", f"Furo {hole} ocupado por {users}")

    # 2) redes derivadas == redes logicas declaradas
    pin_net = layout.pin_net_map(stage)
    declared: dict[str, tuple[dict, frozenset[str]]] = {}
    for net, pins in layout.logical_nets(stage):
        declared[net["name"]] = (net, pins)
        if not pins:
            continue
        # todos os pinos declarados devem estar na mesma rede fisica
        phys = {pin_net.get(p) for p in pins}
        if len(phys) != 1 or None in phys:
            add("ERROR", "NET_OPEN", f"Rede {net['name']}: pinos {sorted(pins)} NAO estao na mesma rede fisica")
            continue
        extra = next(iter(phys)) - pins
        if extra:
            add("ERROR", "NET_EXTRA_PINS",
                f"Rede {net['name']}: a protoboard liga tambem {sorted(extra)} (curto/ligacao nao declarada)")

    declared_pins = {p for _, pins in declared.values() for p in pins}
    for net in layout.extract_nets(stage):
        # redes fisicas com 2+ pinos de componentes devem estar declaradas
        real = {p for p in net if not layout.components[p.split(".")[0]]["type"] == "breadboard"}
        if len(real) >= 2 and not (real & declared_pins):
            add("ERROR", "NET_UNDECLARED", f"Rede fisica nao declarada: {sorted(real)}")
        if len(real) >= 2 and (real & declared_pins) and not real <= declared_pins:
            add("ERROR", "NET_PARTIAL", f"Rede fisica contem pinos fora das redes declaradas: {sorted(real - declared_pins)}")

    # 3) regras de seguranca eletrica
    esp_ref = layout.esp32()["ref"]
    for net, pins in declared.values():
        dom = net.get("domain")
        v = net.get("v_nominal")
        esp_pins = [p for p in pins if p.startswith(esp_ref + ".")]
        gpio_pins = []
        for p in esp_pins:
            bp = layout.board.resolve(p.split(".", 1)[1])
            if bp.gpio is not None:
                gpio_pins.append(bp)
        if gpio_pins:
            vmax = net_vmax_at_gpio(layout, net, stage)
            if vmax is None or vmax > V_LIMIT_GPIO:
                add("ERROR", "GPIO_OVERVOLTAGE",
                    f"Rede {net['name']} liga GPIO {[g.label for g in gpio_pins]} a {vmax} V (> {V_LIMIT_GPIO} V)")
            if dom == "5V":
                add("ERROR", "GPIO_ON_5V_DOMAIN", f"Rede {net['name']} no dominio 5 V contem GPIO")
        for bp in gpio_pins:
            if bp.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved"):
                add("ERROR", "FORBIDDEN_GPIO_USED", f"GPIO proibido/reservado {bp.label} (GPIO{bp.gpio}) em uso na rede {net['name']}")
            if bp.kind == "strapping_avoid":
                add("WARN", "STRAPPING_PIN_USED", f"{bp.label} (GPIO{bp.gpio}) e pino de strapping")
            if bp.kind == "strapping_caution":
                add("INFO", "STRAPPING_PIN_NOTED", f"{bp.label} (GPIO{bp.gpio}) e pino de strapping (uso como saida e aceitavel)")

    # 4) pinos proibidos da ESP32 nao podem receber NADA
    for p in layout.board.pins:
        if p.kind in ("flash_forbidden", "strapping_forbidden", "uart_reserved"):
            hole = layout.esp32_pin_hole(p)
            own = f"{esp_ref}.{layout.board.ref_name(p)}"
            users = [u for u in occ.get(hole, []) if u != own]
            net = pin_net.get(own, frozenset())
            others = {x for x in net if x != own}
            if users or others:
                add("ERROR", "FORBIDDEN_PIN_TOUCHED",
                    f"{p.label} (GPIO{p.gpio}) recebeu ligacao: {sorted(set(users) | others)}")

    # 5) curtos entre fontes
    for net in layout.extract_nets(stage):
        labels = set()
        for pin in net:
            ref, name = pin.split(".", 1)
            c = layout.components[ref]
            if c["type"] == "esp32":
                bp = layout.board.resolve(name)
                labels.add({"power_5v": "5V", "power_3v3": "3V3", "ground": "GND"}.get(bp.kind, ""))
            elif c["type"] in ("hc_sr04", "tcrt5000_module", "potentiometer", "lcd2004a"):
                role = layout.modules["modules"][c["type"]]["pin_electrical"][name].get("role")
                v = layout.modules["modules"][c["type"]]["pin_electrical"][name].get("v")
                if role == "ground":
                    labels.add("GND")
                elif role == "power_in" and v == 5.0:
                    labels.add("5V")
                elif role == "power_in" and v == 3.3:
                    labels.add("3V3")
        labels.discard("")
        if len(labels) > 1:
            add("ERROR", "SUPPLY_SHORT", f"Rede liga fontes diferentes {sorted(labels)}: {sorted(net)}")

    # 6) alimentacao correta dos modulos
    for comp in layout.comps(stage):
        mod = layout.modules["modules"].get(comp["type"])
        if not mod or "supply_v" not in mod:
            continue
        for pin, spec in mod["pin_electrical"].items():
            if spec.get("role") == "power_in":
                net = pin_net.get(f"{comp['ref']}.{pin}", frozenset())
                want = {5.0: "5V", 3.3: "3V3"}[spec["v"]]
                got = set()
                for x in net:
                    ref, nm = x.split(".", 1)
                    if layout.components[ref]["type"] == "esp32":
                        bp = layout.board.resolve(nm)
                        if bp.kind == "power_5v":
                            got.add("5V")
                        if bp.kind == "power_3v3":
                            got.add("3V3")
                # pino de alimentacao pode chegar via rede interna de modulo (ex.: backlight via resistor)
                if got and got != {want}:
                    add("ERROR", "WRONG_SUPPLY", f"{comp['ref']}.{pin} deveria estar em {want}, esta em {sorted(got)}")

    # 7) divisor de ECHO (ramo de cima e ramo de baixo podem ter varios resistores em serie)
    top = [c for c in layout.components.values() if c.get("role") == "divider_top" and layout.present(c, stage)]
    bot = [c for c in layout.components.values() if str(c.get("role", "")).startswith("divider_bottom") and layout.present(c, stage)]
    if top and bot:
        ra = sum(c["ohms"] for c in top)
        rb = sum(c["ohms"] for c in bot)
        tol = max(c["tolerance"] for c in top + bot)
        lo, hi = divider_extremes(4.75, 5.25, ra, rb, tol)
        nom = divider_vout(5.0, ra, rb)
        if hi > V_LIMIT_GPIO:
            add("ERROR", "DIVIDER_TOO_HIGH", f"Divisor: Vout_max(pior caso)={hi:.3f} V > {V_LIMIT_GPIO} V")
        if lo < 0.75 * 3.3:
            add("ERROR", "DIVIDER_TOO_LOW", f"Divisor: Vout_min(pior caso)={lo:.3f} V < VIH_min={0.75*3.3:.3f} V")
        if hi > V_LIMIT_GPIO - 0.05:
            add("WARN", "DIVIDER_MARGIN_THIN",
                f"Divisor com tolerancia {tol:.0%}: pior caso {hi:.3f} V "
                f"(margem {1000*(V_LIMIT_GPIO-hi):.0f} mV ao teto de {V_LIMIT_GPIO} V); nominal {nom:.2f} V")
        if lo < 0.75 * 3.3 + 0.05 and lo >= 0.75 * 3.3:
            add("WARN", "DIVIDER_LOW_MARGIN_THIN",
                f"Divisor: pior caso minimo {lo:.3f} V, so {1000*(lo-0.75*3.3):.0f} mV acima de VIH={0.75*3.3:.3f} V")
    return issues


def net_vmax_at_gpio(layout: Layout, net: dict, stage: str) -> float | None:
    """Tensao maxima (pior caso) que a rede pode apresentar a um GPIO."""
    rule = net.get("v_max_at_gpio")
    if isinstance(rule, str) and rule.startswith("divider:"):
        _, a, b = rule.split(":")
        # cada lado pode ser "R2" ou uma serie "R2+R3"
        top = [layout.components[x] for x in a.split("+")]
        bot = [layout.components[x] for x in b.split("+")]
        _lo, hi = divider_extremes(4.75, 5.25, sum(c["ohms"] for c in top), sum(c["ohms"] for c in bot),
                                   max(c["tolerance"] for c in top + bot))
        return hi
    if rule is None:
        return net.get("v_max", net.get("v_nominal"))
    return float(rule)


def errors(issues: Iterable[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "ERROR"]
