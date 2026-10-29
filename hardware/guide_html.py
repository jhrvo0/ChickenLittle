"""Guia HTML navegavel (autocontido, sem dependencias externas) para montagem em protoboard."""
from __future__ import annotations

import html
import json
import re

from . import model, reports
from .model import Layout
from .render_bb import Scene, WIRE_COLORS, render_scene
from .render_schematic import render_schematic

CSS = """
:root{--bg:#f6f4ec;--card:#fff;--ink:#17212b;--mut:#5b6773;--line:#d9d5c7;--ok:#157a35;--warn:#b45309;--bad:#b91c1c;--acc:#0f5c9e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,Arial,sans-serif}
header{padding:18px 22px;background:#17212b;color:#fff}header h1{margin:0;font-size:21px}header p{margin:4px 0 0;color:#c8d2dc}
.banner{background:#fff3cd;border-bottom:2px solid #e0a800;padding:10px 22px;color:#5a4300;font-weight:600}
nav.tabs{position:sticky;top:0;z-index:5;display:flex;gap:6px;padding:8px 14px;background:#e9e5d6;border-bottom:1px solid var(--line);flex-wrap:wrap}
nav.tabs button{border:1px solid #bdb7a0;background:#fff;border-radius:8px;padding:8px 14px;font-size:14px;cursor:pointer}
nav.tabs button.on{background:var(--acc);color:#fff;border-color:var(--acc)}nav.tabs button.prio{outline:2px solid #e0007a}
main{max-width:1500px;margin:0 auto;padding:16px}
section.stage{display:none}section.stage.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 16px}
.card h2,.card h3{margin:0 0 8px}.goal{color:var(--mut);margin:0 0 10px}
.fig{overflow:auto;border:1px solid var(--line);border-radius:10px;background:#f7f5ee;max-height:78vh}
.fig svg{width:var(--zoom,100%);height:auto;display:block}.tool{display:flex;gap:14px;align-items:center;margin:0 0 8px;flex-wrap:wrap;color:var(--mut)}
.cols{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:16px}@media(max-width:1100px){.cols{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{border:1px solid var(--line);padding:5px 7px;text-align:left;vertical-align:top}
th{background:#efece0}tr.sel,tr:hover{background:#ffe3f3;cursor:pointer}
.sw{display:inline-block;width:14px;height:14px;border-radius:50%;border:1px solid #333;vertical-align:-2px;margin-right:6px}
ol.steps{padding-left:0;list-style:none;margin:0}ol.steps li{border:1px solid var(--line);border-radius:10px;margin:0 0 8px;padding:8px 10px;background:#fcfbf6}
ol.steps li.hold{border-color:#e0007a;background:#fff0f8}ol.steps li h4{margin:0 0 3px;font-size:15px}ol.steps label{display:flex;gap:8px;align-items:flex-start}
.hold-tag{background:#e0007a;color:#fff;border-radius:6px;padding:1px 7px;font-size:12px;margin-left:6px}
code{background:#eef1f4;border-radius:4px;padding:1px 5px;font-size:13px}.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;border:1px solid}
.pill.pend{color:#8a5a00;border-color:#e0a800;background:#fff7dd}.safe{color:var(--bad);font-weight:600}
.checks li{margin:3px 0}details{margin:6px 0}details>summary{cursor:pointer;font-weight:600}
.dim{opacity:.16}
"""

JS = """
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
function show(st){$$('section.stage').forEach(e=>e.classList.toggle('on',e.dataset.stage===st));
 $$('nav.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.stage===st));try{localStorage.setItem('mp_stage',st)}catch(e){}
 location.hash=st}
function hl(stage,id){const sec=$('section.stage[data-stage="'+stage+'"]');
 $$('.wire,.part',sec).forEach(e=>{e.classList.remove('hl');e.classList.toggle('dim',!!id&&e.dataset.id!==id&&e.dataset.ref!==id)});
 $$('tr.sel',sec).forEach(e=>e.classList.remove('sel'));
 if(!id)return;$$('[data-id="'+id+'"],[data-ref="'+id+'"]',sec).forEach(e=>{e.classList.add('hl');e.classList.remove('dim')});
 $$('tr[data-hl="'+id+'"]',sec).forEach(e=>e.classList.add('sel'))}
function zoom(stage,v){const sec=$('section.stage[data-stage="'+stage+'"]');$('.fig',sec).style.setProperty('--zoom',v+'%')}
function tags(stage,on){const sec=$('section.stage[data-stage="'+stage+'"]');$$('.htag',sec).forEach(e=>e.style.display=on?'inline':'none')}
document.addEventListener('click',e=>{const tr=e.target.closest('tr[data-hl]');if(tr){hl(tr.closest('section').dataset.stage,tr.dataset.hl)}
 const w=e.target.closest('.wire,.part');if(w&&w.closest('.fig')){hl(w.closest('section').dataset.stage,w.dataset.id||w.dataset.ref)}
 if(e.target.matches('.clr')){hl(e.target.closest('section').dataset.stage,null)}});
$$('input[type=checkbox][data-k]').forEach(c=>{try{c.checked=localStorage.getItem('mp_'+c.dataset.k)==='1'}catch(e){}
 c.addEventListener('change',()=>{try{localStorage.setItem('mp_'+c.dataset.k,c.checked?'1':'0')}catch(e){}})});
let st='B';try{st=localStorage.getItem('mp_stage')||'B'}catch(e){}if(/^#[A-E]$/.test(location.hash))st=location.hash[1];show(st);
"""

COMMON_ERRORS = [
    "ESP32 deslocada uma coluna: TODOS os pinos ficam errados. Confira: 3V3 na coluna 4 e 5V na coluna 22 (fileira de baixo).",
    "Letras da protoboard invertidas (A no topo em vez de J): use sempre a coluna pelo NUMERO e confira pelo desenho; se invertida, vire a protoboard.",
    "HC-SR04 com VCC e GND trocados: pode queimar o modulo. Leia a serigrafia (VCC | TRIG | ECHO | GND) antes de encaixar.",
    "ECHO ligado direto ao GPIO34 (sem divisor): proibido; entrega ~5 V a um pino de 3,3 V.",
    "R1 e R2 trocados: o no cai para 2,0 V (abaixo de 2,475 V) e a leitura falha (sem dano, mas sem distancia).",
    "TCRT5000 ou potenciometro ligados em 5 V: eles so podem usar 3V3.",
    "Fio em IO12, IO6..IO11 (SD0..CLK) ou TX0/RX0: proibido (boot loop / falha de flash / serial).",
    "LCD com RW (pino 5) no ar: obrigatorio ligar no GND antes de energizar.",
    "Cabo USB so de carga (sem dados): a porta COM nunca aparece.",
    "Jumper 'quase' encaixado: empurre ate o fim e puxe de leve para testar.",
]
NO_PORT = [
    "Troque o cabo por um cabo USB DE DADOS e teste outra porta USB do notebook.",
    "Deixe SOMENTE a ESP32 na protoboard (Estagio A) — sem sensores ou fios.",
    "Windows: Gerenciador de Dispositivos > Portas (COM e LPT). Sem porta? Instale o driver da ponte USB-serial da sua placa (CP210x ou CH340).",
    "Rode `python -m terminal.bench ports` para listar as portas.",
    "Nao use a ESP32 se 5V/3V3 medirem fora de 4,75-5,25 V / 3,25-3,35 V.",
    "Para gravar o firmware pode ser preciso segurar BOOT ao iniciar o upload.",
]
PRE_POWER = [
    "01 Sem curto 5V/VIN x GND (> 1 kΩ).",
    "02 Sem curto 3V3 x GND (> 500 Ω).",
    "03 R1 entre 2,09 e 2,31 kΩ (2,2 kΩ).",
    "04 R2 entre 3,14 e 3,47 kΩ (3,3 kΩ).",
    "05 LCD pino 5 (RW) com 0 Ω ate o GND (a partir do Estagio D).",
    "06 TCRT5000 VCC somente em 3V3 (Estagio C).",
    "07 Potenciometro: extremos em 3V3 e GND, cursor em IO36/VP (Estagio C).",
    "08 Nada nos pinos IO6..IO11 (SD0..CLK).",
    "09 Nada em IO12, TX0, RX0.",
]


def _clean_svg(svg: str) -> str:
    svg = re.sub(r'<svg xmlns="http://www.w3.org/2000/svg" ', '<svg xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMin meet" ', svg, count=1)
    svg = re.sub(r'\s(width|height)="[\d.]+"', "", svg, count=2)          # escala pelo CSS
    return re.sub(r'\sid="[^"]*"', "", svg)


def _h(s) -> str:
    return html.escape(str(s))


def stage_section(lay: Layout, stage: str, extra_figs: list[tuple[str, str]]) -> str:
    st = lay.raw["stages"][stage]
    svg, _ = render_scene(lay, Scene(stage=stage, title=f"Estagio {stage} - {st['title']}", subtitle=st["goal"]))
    sch = render_schematic(lay, stage)
    steps = lay.raw["build_steps"].get(stage, [])
    wrows = reports.wire_rows(lay, stage)
    crows = reports.component_rows(lay, stage)
    issues = model.validate(lay, stage)
    out = [f'<section class="stage" data-stage="{stage}" id="s{stage}">',
           f'<div class="card"><h2>Estagio {stage} — {_h(st["title"])}</h2><p class="goal">{_h(st["goal"])}</p>',
           '<span class="pill pend">PENDING_PHYSICAL_VALIDATION</span> '
           f'<span class="pill pend">{sum(1 for i in issues if i.level == "ERROR")} erros de consistencia (software)</span></div>']
    out.append('<div class="cols"><div>')
    out.append('<div class="card"><h3>Montagem na protoboard</h3><div class="tool">'
               f'<label>Zoom <input type="range" min="60" max="400" value="100" oninput="zoom(\'{stage}\',this.value)"></label>'
               f'<label><input type="checkbox" checked onchange="tags(\'{stage}\',this.checked)"> etiquetas de furo</label>'
               '<button class="clr">limpar destaque</button><span>Clique num fio, componente ou linha da tabela para destacar.</span></div>')
    out.append(f'<div class="fig">{_clean_svg(svg)}</div></div>')
    for title, fig in extra_figs:
        out.append(f'<div class="card"><h3>{_h(title)}</h3><div class="fig">{_clean_svg(fig)}</div></div>')
    out.append(f'<div class="card"><h3>Esquematico eletrico</h3><div class="fig">{_clean_svg(sch)}</div></div>')
    out.append("</div><div>")
    out.append('<div class="card"><h3>Passo a passo</h3><ol class="steps">')
    for s_ in steps:
        key = f"{stage}_{s_['n']}"
        hold = " hold" if s_.get("hold") else ""
        tag = '<span class="hold-tag">PONTO DE PARADA</span>' if s_.get("hold") else ""
        refs = "".join(f' <a href="#" onclick="hl(\'{stage}\',\'{r}\');return false">{r}</a>' for r in s_.get("refs", []))
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", _h(s_["text"]))
        out.append(f'<li class="{hold.strip()}"><label><input type="checkbox" data-k="{key}"><span><h4>{s_["n"]}. {_h(s_["title"])}{tag}</h4>{text}{refs}</span></label></li>')
    out.append("</ol></div>")
    out.append('<div class="card"><h3>Fio a fio</h3><table><tr><th>Fio</th><th>Cor</th><th>De</th><th>Ate</th><th>Rede</th><th>V</th></tr>')
    for r in wrows:
        colr = WIRE_COLORS.get(next((k for k, v in reports.COLOR_PT.items() if v == r["cor"]), "grey"), "#999")
        out.append(f'<tr data-hl="{r["id"]}"><td><b>{r["id"]}</b></td><td><span class="sw" style="background:{colr}"></span>{_h(r["cor"])}</td>'
                   f'<td><b>{r["de_furo"]}</b></td><td><b>{r["ate_furo"]}</b></td><td>{_h(r["rede"])}</td><td>{_h(r["tensao_esperada"])}</td></tr>')
        if r["seguranca"]:
            out.append(f'<tr data-hl="{r["id"]}"><td colspan="6" class="safe">⚠ {_h(r["seguranca"])}</td></tr>')
    out.append("</table></div>")
    out.append('<div class="card"><h3>Pinos e furos dos componentes</h3><table><tr><th>Comp.</th><th>Pino</th><th>Furo</th><th>Rede</th></tr>')
    for r in crows:
        out.append(f'<tr data-hl="{r["componente"]}"><td>{r["componente"]}</td><td>{_h(r["pino"])}</td><td><b>{r["furo"]}</b></td><td>{_h(r["rede"])}</td></tr>')
    out.append("</table></div>")
    if "R1" in {c["ref"] for c in lay.comps(stage)}:
        r1, r2 = lay.components["R1"], lay.components["R2"]
        lo, hi = model.divider_extremes(4.75, 5.25, r1["ohms"], r2["ohms"], r1["tolerance"])
        out.append('<div class="card"><h3>Como o divisor protege o GPIO34</h3>'
                   f'<p>O HC-SR04 responde no pino ECHO com pulsos de <b>~5 V</b>; o ESP32 so aguenta <b>3,3 V</b>. '
                   f'Dois resistores em serie dividem a tensao: <code>Vout = Vecho × R2/(R1+R2)</code> = Vecho × {r2["ohms"]/(r1["ohms"]+r2["ohms"]):.3f}.</p>'
                   f'<ul><li>5,00 V → <b>{model.divider_vout(5.0, r1["ohms"], r2["ohms"]):.2f} V</b></li>'
                   f'<li>5,25 V → {model.divider_vout(5.25, r1["ohms"], r2["ohms"]):.2f} V</li>'
                   f'<li>Pior caso com resistores de ±5%: {lo:.2f} V a <b>{hi:.3f} V</b> (teto seguro 3,30 V; <span class="safe">margem de so {1000*(3.30-hi):.0f} mV</span> — prefira resistores de 1% ou meça os seus).</li></ul>'
                   '<p>Caminho: <b>ECHO → R1 → NÓ → GPIO34</b> e <b>NÓ → R2 → GND</b>. O fio verde W4 sai do NÓ (furo 36F), nunca do ECHO.</p></div>')
    if any(i.level == "WARN" for i in issues):
        out.append('<div class="card"><h3>Avisos da validacao (software)</h3><ul>' + "".join(f"<li>{_h(i)}</li>" for i in issues if i.level == "WARN") + "</ul></div>")
    out.append("</div></div></section>")
    return "\n".join(out)


def build_guide(lay: Layout, figs: dict[str, list[tuple[str, str]]] | None = None) -> str:
    figs = figs or {}
    proj = lay.raw["project"]
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             f"<title>MotionPet — Guia de montagem em protoboard</title><style>{CSS}</style></head><body>",
             f'<header><h1>MotionPet — Guia de montagem em protoboard</h1><p>Firmware {_h(proj["firmware_version"])} • pinagem {_h(proj["pinout_status"])} • gerado de hardware/netlist/motionpet.netlist.json</p></header>',
             '<div class="banner">STATUS OFICIAL: PENDING_PHYSICAL_VALIDATION — nada aqui foi medido numa bancada real. Com a USB DESCONECTADA monte, meça com o multimetro e so depois energize. A serigrafia da sua placa SEMPRE prevalece sobre o desenho.</div>',
             '<nav class="tabs">'
             + "".join(f'<button data-stage="{s}" onclick="show(\'{s}\')" class="{"prio" if s == "B" else ""}">{s} — {_h(lay.raw["stages"][s]["title"])}{" ★" if s == "B" else ""}</button>' for s in model.STAGE_ORDER)
             + '<button data-stage="X" onclick="show(\'X\')">Antes de comecar / erros / ajuda</button></nav><main>']
    for s in model.STAGE_ORDER:
        parts.append(stage_section(lay, s, figs.get(s, [])))
    parts.append('<section class="stage" data-stage="X"><div class="cols"><div>')
    parts.append('<div class="card"><h2>Confirmacoes fisicas pendentes</h2><p>Marque conforme for conferindo na SUA bancada.</p><ul class="checks">'
                 + "".join(f'<li><label><input type="checkbox" data-k="{c["id"]}"> <b>{c["id"]}</b> (bloqueia estagio {c["blocks"]}) — {_h(c["text"])}</label></li>' for c in lay.raw["confirmations"])
                 + "</ul></div>")
    parts.append('<div class="card"><h2>Hipoteses usadas nos desenhos</h2><ul>' + "".join(f'<li><b>{a["id"]}</b> {_h(a["text"])}</li>' for a in lay.raw["assumptions"]) + "</ul></div>")
    parts.append("</div><div>")
    parts.append('<div class="card"><h2>Checklist antes de ligar (USB desconectada)</h2><ul class="checks">'
                 + "".join(f'<li><label><input type="checkbox" data-k="pp{i}"> {_h(t)}</label></li>' for i, t in enumerate(PRE_POWER))
                 + "</ul><p>Detalhes e criterios em <code>docs/bench_assembly_guide.md</code> e <code>docs/hardware_safety.md</code>.</p></div>")
    parts.append('<div class="card"><h2>Erros comuns</h2><ul>' + "".join(f"<li>{_h(e)}</li>" for e in COMMON_ERRORS) + "</ul></div>")
    parts.append('<div class="card"><h2>A ESP32 nao e reconhecida</h2><ol>' + "".join(f"<li>{re.sub(r'`([^`]+)`', r'<code>\\1</code>', _h(e))}</li>" for e in NO_PORT) + "</ol></div>")
    parts.append("</div></div></section></main>")
    parts.append(f"<script>{JS}</script></body></html>")
    return "\n".join(parts)
