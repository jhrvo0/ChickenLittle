r"""Guia da montagem I2C atual, separado do CAD paralelo historico.

Gerar: .venv\Scripts\python.exe -m hardware.final_assembly
Furos e fios vem de netlist/motionpet_final_i2c.json; perfil da ESP32 de data/boards.json.
"""
from __future__ import annotations

import html
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NETLIST = ROOT / "netlist" / "motionpet_final_i2c.json"


def load_wiring() -> dict:
    return json.loads(NETLIST.read_text(encoding="utf-8"))


def lcd_light_diagnostic(wiring: dict) -> dict:
    """Aplica somente as duas mudancas de ponta e remove os dois sinais do LCD."""
    result = deepcopy(wiring)
    plan = wiring["diagnostics"]["lcd_backlight_5v"]
    changes = {w["id"]: w for w in plan["move_ends"]}
    result["wires"] = [dict(w, **{k: v for k, v in changes.get(w["id"], {}).items() if k != "id"})
                       for w in result["wires"] if w["id"] not in plan["disconnect_wires"]]
    return result


def steps() -> list[dict]:
    return [
        {"title": "Use as duas protoboards", "items": [], "text": "Se vai começar do zero, desconecte a USB e retire os fios externos da montagem anterior. Chame a placa da ESP32 de P1 e a outra de P2. Vamos usar os trilhos laterais e deixar os componentes ligados por cabos, com espaço para conferir cada fio. Separe 11 jumpers fêmea–macho, 6 macho–macho e o multímetro.", "note": "Já instalou os trilhos F1–F4 e o LCD? Mantenha esses fios e escolha o passo Teste o LCD antes de continuar. O botão Luz do LCD instável ou apagada abre o diagnóstico com as mudanças exatas. LCD e TCRT5000 usam somente jumpers; os três resistores ficam reservados ao ECHO do HC-SR04."},
        {"title": "Identifique os trilhos + e −", "items": [], "text": "Use um par lateral por placa, do lado da fileira J: + da P1 será 5 V; + da P2 será 3,3 V; os dois − serão GND. O par da outra lateral de cada placa fica livre. No guia, +1…+5 e −1…−5 são os cinco furos do PRIMEIRO grupo de cinco de cada trilho, contando a partir do lado da linha 1.", "note": "São nomes do guia, não números impressos. Use somente esse primeiro grupo de cinco: assim não dependemos da continuidade até o meio ou o outro lado do trilho. Confira continuidade sem USB. Encaixar uma protoboard na outra não interliga seus trilhos. Nunca faça ponte entre os dois +."},
        {"title": "Confira os nomes na ESP32", "items": [], "text": "P1 mostra a placa de 38 pinos com USB para a linha 1, pinos em B/I e A/J livres: 1J=5V, 6J=GND, 19J=3V3, 10A=IO5, 15J=IO34, 14J=IO35, 14A=IO21 e 17A=IO22. O teste LCD de 05/11 usou 6J/19J/14A/17A. Na P2, a região central fica disponível para o divisor.", "note": "GND de referência é 6J, recuperado do teste que funcionou; a indicação anterior de 2J foi retirada. P1:14A e P2:14A são furos de placas diferentes."},
        {"title": "Teste primeiro a ESP32 sozinha", "items": [], "text": "Conecte apenas a ESP32 à USB. Escolha a porta no painel e clique em Testar ESP32. O teste consulta o firmware integrado pela serial. Se a placa ainda tiver o programa isolado do LCD ou do ultrassom, grave o firmware completo com o comando abaixo, trocando COMx pela porta listada; depois repita o teste.", "test_component": "esp32", "command": ".\\.venv\\Scripts\\python.exe -m platformio run -d firmware -t upload --upload-port COMx", "note": "Feche monitores seriais antes dos testes ou do upload. Depois do teste, retire a USB antes de instalar os próximos fios."},
        {"title": "F1: alimente o trilho de 5 V", "items": ["F1"], "text": "Com USB fora, ligue 5V da ESP32 (P1:1J) ao primeiro furo + do grupo escolhido na P1 (P1:+1). Identifique esse trilho como 5 V. Na montagem normal, o HC-SR04 usa essa alimentação; o diagnóstico de iluminação do LCD é temporário e tem instruções próprias."},
        {"title": "F2: leve GND ao trilho − da P1", "items": ["F2"], "text": "Ligue o GND usado no teste anterior (P1:6J) a P1:−1. O fio fica no − do mesmo par lateral em que você acabou de colocar os 5 V no +."},
        {"title": "F3: alimente o trilho de 3,3 V", "items": ["F3"], "text": "Ligue 3V3 da ESP32 (P1:19J) a P2:+1. Identifique o + da segunda placa como 3,3 V. LCD e TCRT5000 receberão alimentação aqui.", "note": "O + da P2 é 3,3 V, embora a linha impressa também seja vermelha. Não o conecte ao + de 5 V da P1."},
        {"title": "F4: interligue somente os GNDs", "items": ["F4"], "text": "Ligue P1:−2 a P2:−1. Agora os dois trilhos − pertencem ao mesmo GND da ESP32. Os trilhos + permanecem separados."},
        {"title": "Meça os trilhos antes dos módulos", "items": [], "text": "Conecte a USB apenas para medir em tensão contínua. Na P1, ponta preta em −4 e vermelha em +3: espere aproximadamente 5 V. Na P2, preta em −5 e vermelha em +4: espere aproximadamente 3,3 V. Se faltar tensão, confira os quatro jumpers de alimentação. Depois desligue a USB.", "note": "O navegador não mede esses trilhos. O teste de serial da ESP32 não substitui esta conferência. Nunca encoste a ponta de prova entre + e − ao mesmo tempo."},
        {"title": "Alimente o LCD, sem resistores", "items": ["F14", "F15"], "text": "Com USB fora, ligue VCC do backpack do LCD a P2:+3 e GND a P2:−3. Confira o jumper de backlight do adaptador. Use os nomes VCC/GND da peça, não a posição desenhada dos conectores."},
        {"title": "Ligue os dois sinais do LCD", "items": ["F16", "F17"], "text": "Ligue SDA do LCD a IO21 (P1:14A) e SCL a IO22 (P1:17A). Só usamos os quatro pinos do backpack; não coloque fios nos 16 contatos do painel. O LCD continua em 3,3 V.", "note": "Se o painel precisar de 5 V para contraste, será necessário um conversor I²C bidirecional. Não mude apenas o VCC para 5 V mantendo SDA/SCL diretos."},
        {"title": "Teste o LCD antes de continuar", "items": [], "text": "Conecte a USB e observe primeiro a iluminação. Se a luz de trás pisca ou a frente fica apagada, desligue a USB e abra Luz do LCD instável ou apagada: ver diagnóstico, abaixo. Esse procedimento muda a alimentação do LCD e retira os sinais antes de usar 5 V. Só execute Testar LCD na montagem normal de 3,3 V, com a iluminação estável. Confira a tensão no adaptador, informe a medição e compare a imagem física com o quadro recebido. Tire a USB antes de instalar o próximo módulo.", "test_component": "lcd", "note": "Luz piscando ou apagada: resolva a alimentação pelo diagnóstico antes de continuar. Com a iluminação estável, o trimpot azul ajusta o contraste dos caracteres. Receber um quadro pela serial não prova que o painel físico está aceso. Os timeouts do HC-SR04 ainda desconectado não reprovam este teste."},
        {"title": "Ligue o TCRT5000, sem resistores", "items": ["F11", "F12", "F13"], "text": "Ligue VCC a P2:+2, GND a P2:−2 e DO a IO35 (P1:14J). AO fica desconectado. Confira a serigrafia do seu módulo; a ordem dos pinos pode variar."},
        {"title": "Teste o TCRT5000", "items": [], "text": "Conecte a USB, informe a alimentação medida no módulo e clique em Testar TCRT5000. Durante a captura de 8 segundos, aproxime e afaste um cartão claro a poucos milímetros do sensor. O teste precisa observar o IR alternando. Ajuste o trimpot do sensor se necessário. Desligue a USB antes de avançar.", "test_component": "ir", "note": "LCD e IR agora estão montados usando somente jumpers. Os três resistores seguintes pertencem exclusivamente ao ultrassom."},
        {"title": "R1: proteção do ultrassom", "items": ["R1"], "text": "Na P2 livre, coloque o resistor de 1 kΩ entre 8C e 12C. Quatro faixas: marrom, preto, vermelho, dourado. Confira o valor fora do circuito. O HC-SR04 e o GPIO34 continuam desconectados.", "note": "Para eliminar esses resistores seria preciso um conversor apropriado de 5 V para 3,3 V. Com as peças registradas, mantenha o divisor; não ligue ECHO direto nem presuma que o HC-SR04 padrão funcione em 3,3 V."},
        {"title": "R2: outro resistor de 1 kΩ", "items": ["R2"], "text": "Na P2, coloque o segundo resistor de 1 kΩ entre 12D e 16D. As pernas de R1 em 12C e de R2 em 12D se unem pela tira 12 A–E."},
        {"title": "R3: resistor de 300 Ω", "items": ["R3"], "text": "Na P2, coloque 300 Ω entre 16E e 20E. Quatro faixas: laranja, preto, marrom, dourado. R2 e R3 ficam em série, somando 1,3 kΩ até o GND. Não deixe pernas de tiras diferentes se tocarem."},
        {"title": "F10: aterre a base do divisor", "items": ["F10"], "text": "Ligue P2:20A a P2:−4. O resistor R3 termina na mesma tira 20 A–E e passa a estar ligado ao GND. Tudo fica na segunda protoboard, com espaço entre os pontos."},
        {"title": "Confira o divisor antes do ECHO", "items": [], "text": "Sem USB, faça um jumper TEMPORÁRIO entre P1:+3 (5 V) e P2:8B. HC-SR04 e GPIO34 ainda ficam desconectados. Ligue USB apenas para medir: ponta preta em P2:−5 e vermelha em P2:12B. Espere cerca de 2,8 V. Anote a tensão. Desligue a USB e RETIRE o jumper temporário.", "note": "Acima de 3,30 V ou fora de aproximadamente 2,5–3,2 V: reveja a montagem antes de conectar o GPIO34. Este ensaio estático não mede o pico do ECHO real. Pode usar temporariamente o jumper reservado ao F9."},
        {"title": "Ligue o HC-SR04", "items": ["F5", "F6", "F7", "F8"], "text": "Com USB fora: VCC do HC-SR04 → P1:+2 (5 V); GND → P1:−3; TRIG → IO5 (P1:10A); ECHO → P2:8A. ECHO entra no resistor R1, não em um GPIO. Leia os nomes impressos no módulo."},
        {"title": "F9: leve o ponto protegido ao GPIO34", "items": ["F9"], "text": "Depois de conferir o divisor e retirar o jumper temporário, ligue P2:12A a IO34 (P1:15J). Esse é o ponto entre R1 e R2. O ECHO do sensor fica separado, na tira 8 A–E.", "note": "Revise: ECHO → R1 → ponto 12 → R2 → R3 → GND. Só o ponto 12 vai ao GPIO34."},
        {"title": "Teste o HC-SR04", "items": [], "text": "Ponha um livro de frente para o sensor, a uma distância medida, por exemplo 25 cm. Conecte USB, informe abaixo a tensão anotada no ensaio do divisor e a distância do alvo. Clique em Testar HC-SR04. A medição estática declarada não deve ser confundida com o pico real de ECHO.", "test_component": "hcsr04"},
        {"title": "Confira os três funcionando juntos", "items": [], "text": "Clique em Testar conjunto e repita os estímulos: alvo na distância de referência, cartão entrando e saindo da frente do TCRT5000 e LCD legível. Informe as medições reais e confirme a imagem na tela. Para qualquer correção de fio, desconecte a USB antes.", "test_component": "all", "note": "O resultado distingue evidências recebidas pela serial de medições e comparação visual declaradas por você. Reconhecimento TinyML e minijogo têm validações próprias."},
    ]


def hole_xy(hole: str) -> tuple[int, int]:
    board, contact = hole.split(":", 1)
    offset = 0 if board == "P1" else 520
    if contact[0] in "+-":
        return 90 + int(contact[1:]) * 20, offset + (110 if contact[0] == "+" else 140)
    col, row = int(contact[:-1]), contact[-1]
    return 50 + col * 20, offset + {"J": 200, "I": 220, "H": 240, "G": 260, "F": 280,
                                   "E": 330, "D": 350, "C": 370, "B": 390, "A": 410}[row]


def wiring_svg(wiring: dict) -> str:
    esc = html.escape
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1260 1060" role="img" aria-label="Duas protoboards: ESP32 e 5 V na P1, divisor e 3,3 V na P2">',
             '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#25344a}.small{font-size:13px}.pin{font-size:14px;font-weight:600}.wire{fill:none;stroke-width:3;stroke-linecap:round}.item text{font-size:14px;font-weight:700}.wire-label{display:none}.now .wire-label{display:inline}.now{filter:drop-shadow(0 0 4px #ed6487)}</style>',
             '<rect width="1260" height="1060" rx="20" fill="#f3f5fa"/>',
             '<text x="30" y="29" font-size="22" font-weight="700">MotionPet · duas protoboards com trilhos</text>',
             '<text x="30" y="51" class="small">Contatos +1…+5 / −1…−5: primeiro grupo de cinco do trilho, a partir do lado da linha 1.</text>']
    for board, offset, voltage in (("P1", 0, "5 V"), ("P2", 520, "3,3 V")):
        parts.append(f'<text x="48" y="{offset+78}" font-size="21" font-weight="700">{board} · trilho + = {voltage} · trilho − = GND</text>')
        parts.append(f'<rect x="42" y="{offset+90}" width="643" height="425" rx="12" fill="white" stroke="#c9d3e3"/>')
        for yy, color, sign in ((110, "#d33449", "+"), (140, "#3975c6", "−"), (470, "#b3bbc8", "+"), (500, "#b3bbc8", "−")):
            y = offset + yy
            parts.append(f'<text x="51" y="{y+5}" font-size="19" style="fill:{color}">{sign}</text>')
            for group in range(5):
                x0 = 110 + group * 120
                stroke = color if group == 0 and yy < 200 else "#e3e7ef"
                parts.append(f'<path d="M{x0-8},{y} H{x0+88}" stroke="{stroke}" stroke-width="2"/>')
                for contact in range(1, 6):
                    x = x0 + (contact-1) * 20
                    parts.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{color if yy < 200 and group == 0 else "#cbd2df"}"/>')
                    if group == 0 and yy < 200:
                        parts.append(f'<text x="{x}" y="{y + (-11 if yy == 110 else 17)}" text-anchor="middle" style="font-size:11px;fill:{color}">{sign}{contact}</text>')
        parts.append(f'<text x="350" y="{offset+489}" class="small" style="fill:#8793a6">par da outra lateral: sem fios</text>')
        parts.append(f'<rect x="49" y="{offset+300}" width="628" height="12" rx="6" fill="#e7ebf3"/>')
        for col in range(1, 31):
            x, _ = hole_xy(f"{board}:{col}J")
            parts.append(f'<text x="{x}" y="{offset+187}" text-anchor="middle" style="font-size:11px">{col}</text>')
            for row in "ABCDEFGHIJ":
                x, y = hole_xy(f"{board}:{col}{row}")
                parts.append(f'<circle cx="{x}" cy="{y}" r="3.4" fill="#c5cedd"/>')
        for row in "ABCDEFGHIJ":
            _, y = hole_xy(f"{board}:1{row}")
            parts.append(f'<text x="25" y="{y+4}" class="small">{row}</text>')
    parts.extend(['<rect x="60" y="210" width="380" height="190" rx="10" fill="#233345"/>',
                  '<rect x="173" y="238" width="150" height="128" rx="7" fill="#cbd4de"/>',
                  '<text x="247" y="296" text-anchor="middle" font-size="24">ESP32</text>',
                  '<text x="247" y="320" text-anchor="middle" font-size="13">ESP-WROOM-32</text>',
                  '<rect x="37" y="278" width="44" height="54" rx="7" fill="#a9b5c5"/>',
                  '<text x="49" y="437" class="pin">USB</text>'])
    boards = json.loads((ROOT / "data" / "boards.json").read_text(encoding="utf-8"))
    for side, y in (("J2", 236), ("J3", 385)):
        for idx, (name, _, _, _) in enumerate(boards["profiles"][wiring["board_profile"]]["sides"][side]):
            x = 50 + (19-idx) * 20
            parts.append(f'<text transform="translate({x},{y}) rotate(-65)" style="fill:white;font-size:9px">{esc(name)}</text>')
    positions = {}
    for name, y0, pins in (("HC-SR04", 150, ["VCC", "TRIG", "ECHO", "GND"]), ("TCRT5000", 610, ["VCC", "GND", "DO", "AO"]), ("LCD", 850, ["VCC", "GND", "SDA", "SCL"])):
        parts.append(f'<rect x="875" y="{y0}" width="345" height="180" rx="12" fill="white" stroke="#a8b6ca"/>')
        parts.append(f'<text x="901" y="{y0+31}" font-size="22" font-weight="700">{name if name != "LCD" else "LCD 2004 I²C"}</text>')
        for i, pin in enumerate(pins):
            y = y0 + 60 + i * 30
            positions[f"{name}.{pin}"] = (875, y)
            parts.append(f'<circle cx="875" cy="{y}" r="4" fill="#8292a9"/><text x="890" y="{y+5}" class="pin">{pin}</text>')
    parts.extend(['<text x="887" y="387" class="small">Módulos fora da protoboard.</text>', '<text x="887" y="410" class="small">Ordem dos conectores ilustrativa:</text>', '<text x="887" y="433" class="small">leia os nomes nas peças.</text>', '<text x="887" y="483" class="pin">LCD + IR: só jumpers.</text>', '<text x="887" y="509" class="small">Resistores: só no ECHO.</text>'])
    colors = {"GND": "#536275", "3V3": "#9252c7", "5V": "#d33449", "TRIG": "#c08a12", "ECHO_5V": "#d36f22", "ECHO_3V3": "#1875c2", "IR": "#228447", "SDA": "#078991", "SCL": "#3b64cc"}
    for w in wiring["wires"]:
        x1, y1 = hole_xy(w["from_hole"]) if w["from_hole"] else positions[w["from"]]
        x2, y2 = hole_xy(w["to_hole"])
        if w["id"] == "F1":
            path = f'M{x1},{y1} V{y2} H{x2}'
        elif w["id"] == "F2":
            path = f'M{x1},{y1} V169 H{x2} V{y2}'
        elif w["id"] == "F3":
            path = f'M{x1},{y1} V170 H705 V560 H{x2} V{y2}'
        elif w["id"] == "F4":
            path = f'M{x1},{y1} H15 V554 H{x2} V{y2}'
        elif w["id"] == "F9":
            path = f'M{x1},{y1} V950 H729 V174 H{x2} V{y2}'
        elif w["id"] == "F10":
            path = f'M{x1},{y1} V956 H756 V685 H{x2} V{y2}'
        elif w["id"] in ("F8", "F13", "F16", "F17"):
            lane = {"F8": 786, "F13": 807, "F16": 827, "F17": 847}[w["id"]]
            turn = y2 + (27 if w["id"] != "F13" else -28)
            path = f'M{x1},{y1} H{lane} V{turn} H{x2} V{y2}'
        else:
            path = f'M{x1},{y1} C785,{y1} {x2},{y1} {x2},{y2}'
        color = colors[w["net"]]
        parts.append(f'<g class="item" data-item="{w["id"]}"><title>{esc(w["from"])} → {esc(w["to"])} ({w["to_hole"]})</title><path d="{path}" class="wire" stroke="{color}"/><circle cx="{x2}" cy="{y2}" r="5" fill="{color}"/><text class="wire-label" x="{x2+7}" y="{y2-7}" style="fill:{color}">{w["id"]}</text></g>')
    for r in wiring["resistors"]:
        x1, y1 = hole_xy(r["from_hole"])
        x2, y2 = hole_xy(r["to_hole"])
        mx, my = (x1+x2)/2, (y1+y2)/2
        label = "1 kΩ" if r["ohms"] == 1000 else "300 Ω"
        parts.append(f'<g class="item" data-item="{r["id"]}"><path d="M{x1},{y1} L{x2},{y2}" stroke="#a75f27" stroke-width="5"/><rect x="{mx-23}" y="{my-9}" width="46" height="18" rx="6" fill="#edc98d" stroke="#8b6233"/><text x="{mx}" y="{my-16}" text-anchor="middle">{r["id"]} {label}</text></g>')
    parts.append('</svg>')
    return "".join(parts)


def build_guide(wiring: dict) -> str:
    esc = html.escape
    rows = []
    for r in wiring["resistors"]:
        rows.append(f'<tr><td>{r["id"]}</td><td>{r["ohms"]} Ω · só no ECHO</td><td>{r["from_hole"]}</td><td>{r["to_hole"]}</td></tr>')
    for w in wiring["wires"]:
        rows.append(f'<tr><td>{w["id"]}</td><td>{esc(w["from"])} → {esc(w["to"])}</td><td>{w["from_hole"] or "pino do módulo"}</td><td>{w["to_hole"]}</td></tr>')
    normal = {w["id"]: w for w in wiring["wires"]}
    plan = wiring["diagnostics"]["lcd_backlight_5v"]
    keep_rows = "".join(f'<tr><td>{wid}</td><td>{normal[wid]["from_hole"]}</td><td>{normal[wid]["to_hole"]}</td><td>Fica no lugar</td></tr>'
                        for wid in plan["keep_power_wires"])
    change_rows = "".join(f'<tr><td>{change["id"]} · {esc(normal[change["id"]]["from"])}</td><td>{normal[change["id"]]["to_hole"]}</td><td><b>{change["to_hole"]}</b></td></tr>'
                          for change in plan["move_ends"])
    return_rows = "".join(f'<tr><td>{change["id"]}</td><td>{change["to_hole"]}</td><td><b>{normal[change["id"]]["to_hole"]}</b></td></tr>'
                          for change in plan["move_ends"])
    diagnostic = lcd_light_diagnostic(wiring)
    diagnostic["wires"] = [w for w in diagnostic["wires"] if w["id"] in plan["diagram_wires"]]
    diagnostic["resistors"] = []
    diagnostic_svg = wiring_svg(diagnostic).replace('data-item=', 'data-diagnostic-item=')
    diagnostic_svg = diagnostic_svg.replace('MotionPet · duas protoboards com trilhos', 'DIAGNÓSTICO · LCD em 5 V, sem SDA/SCL')
    diagnostic_svg = diagnostic_svg.replace('LCD + IR: só jumpers.', 'Somente iluminação do LCD.').replace('Resistores: só no ECHO.', 'Sem teste I²C neste modo.')
    payload = json.dumps(steps(), ensure_ascii=False).replace("</", "<\\/")
    page = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MotionPet · duas protoboards e testes</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf1f7;color:#213149;font-family:Segoe UI,Arial,sans-serif}header{padding:15px 25px;background:#17273a;color:white;display:flex;align-items:center;justify-content:space-between;gap:20px}header strong{font-size:22px}header span{font-size:14px;color:#d0d9e8}main{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(390px,1fr);gap:18px;padding:20px;max-width:1700px;margin:auto}.visual svg{width:100%;height:auto}.visual svg:fullscreen{width:100vw;height:100vh;background:#f3f5fa}.panel,.table{padding:24px;background:white;border-radius:17px;box-shadow:0 5px 24px #2036550b}.eyebrow{font-size:13px;color:#526785;font-weight:700}h1{font-size:28px;line-height:1.2;margin:12px 0 16px}p{font-size:17px;line-height:1.55}.note{padding:12px;border-left:4px solid #d08019;background:#fff6e5;font-size:14px;line-height:1.55}.nav{display:flex;gap:10px;align-items:center;justify-content:space-between;margin-top:23px}button,select,input[type=number]{font:inherit;padding:9px 12px;border-radius:8px;border:1px solid #bac7d9;background:white;color:#253953}button,select{cursor:pointer}button.primary{background:#2863c7;color:white;border-color:#2863c7}button:disabled{opacity:.45;cursor:default}select{max-width:100%}#jump{width:100%;margin-bottom:12px}pre{font:13px/1.5 Consolas,monospace;background:#162537;color:#edf4ff;padding:14px;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere}.table{grid-column:1/-1;overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:9px;border-bottom:1px solid #dfe5ef}label{font-size:14px;display:block;margin:12px 0;line-height:1.5}label input[type=checkbox]{margin-right:6px}a{color:#2863c7}.progress{height:5px;background:#dbe3f0}.progress div{height:100%;background:#3f83e6;transition:width .2s}#items{font-size:16px;font-weight:600;color:#28589a}.visual{align-self:start}.tip{font-size:13px;color:#596b83;margin:12px 0}h2{font-size:20px}.toolbar{display:flex;gap:13px;align-items:center;flex-wrap:wrap}.testbox{margin-top:20px;border:1px solid #bdcfe8;border-radius:12px;padding:16px;background:#f6f9fe}.testbox h2{margin:0 0 8px}.portrow{display:flex;gap:8px;align-items:center;margin:12px 0;flex-wrap:wrap}.field input{width:115px;margin-top:5px}.result{border-radius:9px;padding:12px;font-size:14px;line-height:1.55;white-space:pre-wrap;margin-top:12px;background:#e9eef7}.result.passed{background:#e6f5ec;border-left:4px solid #23804a}.result.pending{background:#fff4d6;border-left:4px solid #c48915}.result.failed{background:#ffe9e6;border-left:4px solid #c7473a}#received-frame{letter-spacing:.5px}.startbox{padding:12px;border-radius:10px;background:#e6eefb;font-size:14px;line-height:1.5}details{margin-top:12px}summary{cursor:pointer;font-size:14px}.testhint{font-size:14px;line-height:1.5}#run-test{width:100%;font-weight:700}.rail-key{padding:12px;border:1px solid #d0d9e7;border-radius:10px;background:#fff;line-height:1.5;font-size:14px}code{font-family:Consolas,monospace}@media(max-width:950px){main{grid-template-columns:1fr}.panel{order:-1}h1{font-size:25px}}@media print{header{color:#17273a;background:white}main{display:block}.panel,.toolbar,.progress{display:none}.table{box-shadow:none}svg .item{opacity:1!important;display:inline!important}}
</style></head><body><header><strong>MotionPet · montagem com testes</strong><span>Revisão 4 · GND em 6J · diagnóstico sem desmontar os trilhos</span></header><div class="progress"><div id="progress"></div></div><main><div class="visual"><div id="normal-diagram">__SVG__</div><div id="diagnostic-diagram" hidden>__DIAGNOSTIC_SVG__</div><div class="toolbar"><label><input type="checkbox" id="all"> Mostrar todos os fios</label><button id="zoom">Ampliar desenho</button></div><div class="rail-key"><b>P1: + = 5 V · P2: + = 3,3 V · ambos − = GND.</b><br>Use o primeiro grupo de cinco furos do par junto à fileira J. O outro par lateral fica livre. Os números +1/−1 etc. identificam contatos desse grupo no guia.</div><p class="tip">← e → navegam. O fio do passo atual fica destacado. A posição dos conectores dos módulos é ilustrativa; confira os nomes impressos.</p></div><section class="panel"><select id="jump" aria-label="Escolher passo"></select><div class="eyebrow" id="count"></div><h1 id="title"></h1><div id="items"></div><p id="text"></p><div class="note" id="note"></div><pre id="command"></pre>
<div id="startup" class="startbox" hidden><b>Ative os botões de teste</b><br>Na pasta do projeto, rode:<pre>.\.venv\Scripts\python.exe -m terminal.bench.guide</pre>Depois abra <a href="http://127.0.0.1:8766/">o guia com testes locais</a>. A versão aberta como arquivo continua mostrando todos os passos.</div>
<section class="testbox" id="testbox" hidden><h2 id="test-title"></h2><p class="testhint" id="test-hint"></p><div class="portrow"><label for="port">Porta USB:</label><select id="port" aria-label="Porta USB da ESP32"></select><button id="refresh-ports">Atualizar portas</button></div><p class="tip" id="port-status"></p>
<label class="field" id="supply-row">Tensão medida no 3V3 / VCC do módulo (V)<br><input id="supply" type="number" step="0.01" placeholder="valor medido"></label>
<label class="field" id="echo-row">Tensão anotada no ensaio estático do divisor (V)<br><input id="echo" type="number" step="0.01" placeholder="valor medido"><br><span class="tip">Medição com jumper de 5 V, sem HC-SR04 e sem GPIO34; não é o pico de ECHO.</span></label>
<label class="field" id="reference-row">Distância medida entre o alvo e o HC-SR04 (cm)<br><input id="reference" type="number" step="0.1" placeholder="valor medido"></label>
<label id="wiring-row"><input id="confirm-wiring" type="checkbox"> Conferi a fiação deste componente com a USB desligada.</label><label id="visual-row"><input id="confirm-visual" type="checkbox"> Comparei o LCD físico com o quadro recebido e a imagem está correta.</label>
<button class="primary" id="run-test">Executar teste</button><div id="test-result" class="result" role="status" aria-live="polite" hidden></div><pre id="received-frame" hidden></pre><details id="test-details" hidden><summary>Ver dados recebidos pela serial</summary><pre id="details-body"></pre></details><p class="tip">Instale cada componente com USB fora. Conecte para testar; se alterar fios depois, repita o teste. Sem medições ou confirmação visual, o resultado pode ficar pendente.</p></section>
<button id="diagnostic-open" hidden>Luz do LCD instável ou apagada: ver diagnóstico</button>
<section id="diagnostic-panel" class="testbox" hidden><h2>Diagnóstico temporário de iluminação</h2><div class="note"><b>USB fora para mudar os fios.</b> Este teste usa 5 V somente no LCD, com os cabos SDA/SCL removidos. Não é a montagem final. Não execute o teste I²C neste modo.</div><p>Conserve a alimentação já montada. Não coloque outra ponta nos furos 1J, 6J ou 19J: eles já alimentam os trilhos.</p><table><thead><tr><th>Fio</th><th>Origem</th><th>Destino</th><th>Ação</th></tr></thead><tbody>__KEEP_ROWS__</tbody></table><p>Retire os cabos <b>F16 (SDA)</b> e <b>F17 (SCL)</b> por inteiro, antes de usar 5 V. Depois mova somente as pontas macho destes dois cabos, mantendo as pontas do LCD nos mesmos pinos:</p><table><thead><tr><th>Cabo do LCD</th><th>Sai de</th><th>Vai para</th></tr></thead><tbody>__CHANGE_ROWS__</tbody></table><p class="tip">P1:+3 e P1:−4 são contatos livres do mesmo grupo usado por F1/F2. Não pode haver jumper temporário de ensaio nesses contatos. Os demais fios e resistores já posicionados ficam como estão; não adicione novos componentes durante este diagnóstico.</p><p>Conecte USB apenas para observar: a luz POWER fica estável? A iluminação frontal acende? A página não verifica essas luzes automaticamente. Sem SDA/SCL, não estamos esperando texto.</p><h2>Voltar à montagem normal de 3,3 V</h2><p>Desligue USB e devolva primeiro a alimentação:</p><table><thead><tr><th>Fio</th><th>Sai de</th><th>Volta para</th></tr></thead><tbody>__RETURN_ROWS__</tbody></table><p>Só depois recoloque F16 (SDA → P1:14A) e F17 (SCL → P1:17A). Se o painel só funcionar em 5 V, a comunicação exige conversor I²C; não reconecte os sinais diretos mantendo 5 V.</p><label><input id="diagnostic-restored" type="checkbox"> Com USB fora, devolvi F14 a P2:+3 e F15 a P2:−3 antes de recolocar SDA/SCL.</label><button id="diagnostic-close" class="primary" disabled>Voltar ao teste LCD em 3,3 V</button></section>
<div class="nav"><button id="prev">← Voltar</button><button class="primary" id="next">Próximo →</button></div><p class="tip"><a href="../docs/bench_assembly_guide.md">Guia escrito e alternativas</a> · <a href="../docs/hardware_safety.md">Referências elétricas</a></p></section><section class="table"><h2>Lista completa da montagem normal · LCD em 3,3 V</h2><p class="tip">P1 e P2 são placas diferentes. No diagnóstico de iluminação, siga as mudanças temporárias e a restauração mostradas no painel acima. Furos da ESP32 válidos para o perfil de 38 pinos na posição mostrada. O +1 de cada placa é o primeiro furo do grupo de cinco escolhido no trilho +; −1 idem no trilho −. Nenhum furo recebe duas pontas.</p><table><thead><tr><th>Item</th><th>Ligação</th><th>Origem</th><th>Destino</th></tr></thead><tbody>__ROWS__</tbody></table></section></main><script>
const slides=__SLIDES__;
const el=id=>document.getElementById(id);let index=0,busy=false,currentTest=null,diagnosticActive=false;
const diagnosticStorageKey='motionpet_lcd_light_only_5v';
const testNames={esp32:'Testar ESP32',lcd:'Testar LCD',ir:'Testar TCRT5000',hcsr04:'Testar HC-SR04',all:'Testar conjunto'};
let currentResult=null;const localKey=document.querySelector('meta[name="motionpet-key"]')?.content||'';
const connected=location.protocol==='http:'&&!!localKey;
el('startup').hidden=connected;
slides.forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+s.title;el('jump').appendChild(o)});
function displayResult(result){el('test-result').hidden=!result;el('received-frame').hidden=true;el('test-details').hidden=true;if(!result)return;el('test-result').className='result '+result.status;el('test-result').textContent=(result.details?.port?'Porta testada: '+result.details.port+'\n':'')+result.summary+(result.problems?.length?'\n\n'+result.problems.join('\n'):'')+(result.next_action?'\n\n'+result.next_action:'');const lines=result.details?.device_lcd_20x4;if(Array.isArray(lines)&&lines.length){el('received-frame').textContent='Quadro recebido — compare com o LCD:\n'+lines.join('\n');el('received-frame').hidden=false}if(result.details){el('details-body').textContent=JSON.stringify(result.details,null,2);el('test-details').hidden=false}}
function setupTest(component){if(component!==currentTest){el('confirm-wiring').checked=false;el('confirm-visual').checked=false;el('supply').value='';currentResult=null}currentTest=component;el('diagnostic-open').hidden=!['lcd','all'].includes(component);el('testbox').hidden=!component;if(!component)return;el('test-title').textContent=testNames[component];el('test-hint').textContent=component==='ir'||component==='all'?'Conecte USB. Durante os 8 segundos de captura, aproxime e afaste um cartão do TCRT5000. Mantenha o alvo do ultrassom na referência, se já instalado.':'Conecte USB para capturar os dados. Aguarde o resultado antes de retirar a alimentação.';el('supply-row').hidden=!['lcd','ir','all'].includes(component);el('echo-row').hidden=!['hcsr04','all'].includes(component);el('reference-row').hidden=!['hcsr04','all'].includes(component);el('wiring-row').hidden=component==='esp32';el('visual-row').hidden=!['lcd','all'].includes(component);el('run-test').textContent=testNames[component];el('run-test').disabled=diagnosticActive||!connected||busy||!el('port').value;displayResult(currentResult)}
function show(n){if(busy||diagnosticActive)return;index=Math.max(0,Math.min(slides.length-1,n));const s=slides[index];el('jump').value=index;el('count').textContent='PASSO '+(index+1)+' DE '+slides.length;el('title').textContent=s.title;el('text').textContent=s.text;el('text').hidden=false;el('items').textContent=s.items.length?'Conecte agora: '+s.items.join(', '):'';el('note').textContent=s.note||'';el('note').hidden=!s.note;el('command').textContent=s.command||'';el('command').hidden=!s.command;el('prev').disabled=index===0;el('next').disabled=index===slides.length-1;el('progress').style.width=(index+1)/slides.length*100+'%';const placed=new Set(slides.slice(0,index+1).flatMap(x=>x.items));document.querySelectorAll('[data-item]').forEach(g=>{const id=g.dataset.item;g.style.display=el('all').checked||placed.has(id)?'':'none';g.style.opacity=el('all').checked||s.items.includes(id)||!s.items.length?1:.2;g.classList.toggle('now',s.items.includes(id))});setupTest(s.test_component||null);history.replaceState(null,'','#'+(index+1))}
async function refreshPorts(){if(!connected){el('port-status').textContent='Abra o guia pelo serviço local para acessar a USB.';return}el('refresh-ports').disabled=true;try{const response=await fetch('/api/ports',{headers:{'X-MotionPet-Key':localKey}});const data=await response.json();if(!response.ok)throw Error(data.summary||data.error||'Falha ao consultar portas.');const previous=el('port').value;el('port').replaceChildren();for(const port of data.ports||[]){const o=document.createElement('option');o.value=port.device;o.textContent=port.device+' · '+(port.description||'ESP32');el('port').appendChild(o)}if([...el('port').options].some(o=>o.value===previous))el('port').value=previous;if(el('port').value!==previous){invalidateResult();el('confirm-wiring').checked=false;el('confirm-visual').checked=false;el('supply').value=''}el('port-status').textContent=el('port').options.length?'Feche outros programas que estejam usando esta porta.':'Nenhuma porta encontrada. Conecte a ESP32 com cabo USB de dados e atualize.'}catch(error){el('port-status').textContent=error.message}finally{el('refresh-ports').disabled=false;if(currentTest)el('run-test').disabled=diagnosticActive||!connected||!el('port').value}}
function measured(id){const value=el(id).value.trim();if(!value)return null;const number=Number(value.replace(',','.'));if(!Number.isFinite(number))throw Error('Informe uma medição numérica válida.');return number}
async function runTest(){if(busy||diagnosticActive||!currentTest)return;const component=currentTest;let payload;try{payload={component,port:el('port').value,measurements:{supply_3v3:measured('supply'),echo_v:measured('echo'),reference_cm:measured('reference')},confirmations:{wiring:el('confirm-wiring').checked,lcd_visual:el('confirm-visual').checked}}}catch(error){displayResult({status:'pending',summary:error.message});return}busy=true;for(const id of ['run-test','refresh-ports','prev','next','jump','port'])el(id).disabled=true;displayResult({status:'pending',summary:'Capturando dados da ESP32… mantenha a USB conectada. Isso pode levar até 20 segundos.'});try{const response=await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json','X-MotionPet-Key':localKey},body:JSON.stringify(payload)});const result=await response.json();if(!response.ok)throw Error(result.summary||result.error||'Falha no serviço de testes.');currentResult=result;displayResult(result)}catch(error){displayResult({status:'failed',summary:error.message,next_action:'Confira a porta, feche monitores seriais e verifique se o serviço local está aberto.'})}finally{busy=false;for(const id of ['refresh-ports','jump','port'])el(id).disabled=false;el('prev').disabled=index===0;el('next').disabled=index===slides.length-1;el('run-test').disabled=diagnosticActive||!connected||!el('port').value}}
function enterDiagnostic(){if(busy)return;diagnosticActive=true;invalidateResult();el('diagnostic-restored').checked=false;el('diagnostic-close').disabled=true;el('normal-diagram').hidden=true;el('diagnostic-diagram').hidden=false;el('diagnostic-panel').hidden=false;el('testbox').hidden=true;el('diagnostic-open').hidden=true;el('title').textContent='Diagnóstico: iluminação do LCD em 5 V';el('text').hidden=true;el('note').hidden=true;el('command').hidden=true;el('items').textContent='F1 a F4 ficam. Retire F16/F17 e mova apenas F14/F15.';el('run-test').disabled=true;for(const id of ['prev','next','jump','all'])el(id).disabled=true;try{localStorage.setItem(diagnosticStorageKey,'1')}catch{}}
function leaveDiagnostic(){if(!diagnosticActive||!el('diagnostic-restored').checked)return;diagnosticActive=false;try{localStorage.removeItem(diagnosticStorageKey)}catch{}el('normal-diagram').hidden=false;el('diagnostic-diagram').hidden=true;el('diagnostic-panel').hidden=true;for(const id of ['jump','all'])el(id).disabled=false;currentTest=null;show(slides.findIndex(s=>s.test_component==='lcd'))}
el('diagnostic-panel').hidden=true;el('diagnostic-diagram').hidden=true;el('diagnostic-open').onclick=enterDiagnostic;el('diagnostic-close').onclick=leaveDiagnostic;el('diagnostic-restored').onchange=()=>{el('diagnostic-close').disabled=!el('diagnostic-restored').checked};
el('prev').onclick=()=>show(index-1);el('next').onclick=()=>show(index+1);el('jump').onchange=e=>show(+e.target.value);el('all').onchange=()=>show(index);el('zoom').onclick=()=>document.querySelector(diagnosticActive?'#diagnostic-diagram svg':'#normal-diagram svg').requestFullscreen?.();el('refresh-ports').onclick=refreshPorts;el('run-test').onclick=runTest;function invalidateResult(){currentResult=null;displayResult(null)}for(const id of ['supply','echo','reference'])el(id).oninput=invalidateResult;for(const id of ['confirm-wiring','confirm-visual'])el(id).onchange=invalidateResult;el('port').onchange=()=>{invalidateResult();el('confirm-wiring').checked=false;el('confirm-visual').checked=false;el('supply').value='';if(currentTest)el('run-test').disabled=diagnosticActive||!connected||busy||!el('port').value};document.addEventListener('keydown',e=>{if(['SELECT','INPUT','BUTTON'].includes(e.target.tagName))return;if(e.key==='ArrowRight'){e.preventDefault();show(index+1)}if(e.key==='ArrowLeft'){e.preventDefault();show(index-1)}});
const powerDiagnosticRequested=location.hash==='#lcd-power';const first=Number(location.hash.slice(1));
show(powerDiagnosticRequested?slides.findIndex(s=>s.test_component==='lcd'):Number.isInteger(first)&&first>=1&&first<=slides.length?first-1:0);
let restoreDiagnostic=false;try{restoreDiagnostic=localStorage.getItem(diagnosticStorageKey)==='1'}catch{}
if(powerDiagnosticRequested||restoreDiagnostic){show(slides.findIndex(s=>s.test_component==='lcd'));enterDiagnostic()}if(connected)refreshPorts();
</script></body></html>"""
    return (page.replace("__SVG__", wiring_svg(wiring)).replace("__DIAGNOSTIC_SVG__", diagnostic_svg)
            .replace("__KEEP_ROWS__", keep_rows).replace("__CHANGE_ROWS__", change_rows).replace("__RETURN_ROWS__", return_rows)
            .replace("__ROWS__", "".join(rows)).replace("__SLIDES__", payload))


def main() -> None:
    wiring = load_wiring()
    guide = ROOT / "guia_montagem_final.html"
    diagram = ROOT / "out" / "montagem_final_i2c.svg"
    diagram.parent.mkdir(exist_ok=True)
    guide.write_text(build_guide(wiring), encoding="utf-8", newline="\n")
    diagram.write_text(wiring_svg(wiring), encoding="utf-8", newline="\n")
    print(f"Gerados: {guide.name}, out/{diagram.name} ({len(steps())} passos)")


if __name__ == "__main__":
    main()
