"""Guia de montagem em SLIDES (HTML autocontido, sem dependencias externas).

Um slide por passo: a protoboard vai sendo montada na tela (item novo destacado, zoom na regiao), com o painel
"ADICIONE AGORA" (cor do fio, furos, resistor com faixas) e "COMO". Tudo e gerado da netlist.
Teclado: setas / espaco = navegar, A = ver tudo, F = tela cheia, Home/End.
"""
from __future__ import annotations

import html
import json
import re

from . import model, reports
from .model import Layout
from .render_bb import BAND_COLORS, K, WIRE_COLORS, Scene, item_bbox, render_scene

CSS = """
:root{--ink:#16202b;--mut:#5d6b78;--line:#d6dbe1;--acc:#0f5c9e;--pink:#e0007a;--bad:#b3261e;--ok:#157a35}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{display:grid;grid-template-rows:auto 1fr auto;background:#e9edf1;color:var(--ink);font:16px/1.45 "Segoe UI",system-ui,Arial,sans-serif;overflow:hidden}
.top{background:#16202b;color:#fff;padding:8px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;margin-right:6px;white-space:nowrap}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{border:1px solid #3d4b5a;background:#1f2d3b;color:#cfd8e2;border-radius:999px;padding:4px 12px;font-size:14px;cursor:pointer}
.chip.on{background:var(--acc);border-color:#5aa7e6;color:#fff;font-weight:600}.chip.prio{outline:2px solid var(--pink)}
.prog{height:5px;background:#2b3a49;position:relative}.prog i{position:absolute;left:0;top:0;bottom:0;background:var(--pink);transition:width .25s}
.stagewrap{display:grid;grid-template-rows:auto 1fr;min-height:0}
main{display:grid;grid-template-columns:minmax(0,1fr) 410px;gap:14px;padding:14px;min-height:0}
main.textonly{grid-template-columns:minmax(0,1fr)}main.textonly #figbox{display:none}
#figbox{position:relative;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 2px 10px #0001;min-height:0}
#figbox svg{position:absolute;inset:0;width:100%;height:100%}
.figtools{position:absolute;right:10px;top:10px;display:flex;gap:6px;z-index:2}
.figtools button{border:1px solid var(--line);background:#ffffffdd;border-radius:8px;padding:5px 10px;font-size:13px;cursor:pointer}
.panel{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;overflow:auto;box-shadow:0 2px 10px #0001;min-height:0}
main.textonly .panel{max-width:1100px;margin:0 auto;width:100%}
.kicker{font-size:13px;letter-spacing:.06em;color:var(--acc);font-weight:700;text-transform:uppercase}
h1{font-size:26px;line-height:1.2;margin:4px 0 10px}
.hold{display:inline-block;background:var(--pink);color:#fff;border-radius:8px;padding:3px 10px;font-weight:700;font-size:13px;margin:0 0 10px}
.sec{font-size:12.5px;letter-spacing:.08em;color:var(--mut);font-weight:700;margin:14px 0 6px;text-transform:uppercase}
.card{border:1px solid var(--line);border-left:6px solid var(--acc);border-radius:10px;padding:8px 10px;margin:0 0 8px;background:#fbfcfd}
.card .t{font-weight:700}.card .m{color:var(--mut);font-size:14px}
.hole{display:inline-block;background:#fff;border:2px solid #16202b;border-radius:7px;padding:0 7px;font-weight:800;font-family:Consolas,monospace;font-size:15px;margin:0 2px}
.swatch{display:inline-block;width:16px;height:16px;border-radius:50%;border:2px solid #222;vertical-align:-3px;margin-right:6px}
.how{font-size:17px}
.warn{background:#fdecea;border:1px solid #f1b1ab;color:var(--bad);border-radius:10px;padding:8px 10px;margin:10px 0;font-weight:600}
ul.checks{margin:6px 0;padding-left:0;list-style:none}ul.checks li{margin:4px 0;display:flex;gap:8px;align-items:flex-start}
ul.checks li:before{content:"☐";font-size:18px;line-height:1.1}
pre{background:#101820;color:#e6edf3;border-radius:8px;padding:8px 70px 8px 10px;margin:6px 0;white-space:pre-wrap;word-break:break-all;font-size:13.5px;position:relative}
pre button{position:absolute;right:6px;top:6px;border:0;border-radius:6px;background:#2b3a49;color:#fff;font-size:12px;padding:3px 8px;cursor:pointer}
table.p{border-collapse:collapse;width:100%;font-size:14px}table.p td,table.p th{border:1px solid var(--line);padding:3px 6px;text-align:left}
.pill{display:inline-block;border-radius:999px;padding:1px 10px;font-size:12.5px;border:1px solid #e0a800;background:#fff7dd;color:#7a5200}
.big{font-size:19px}.cols2{columns:2;column-gap:28px}.cols2 li{break-inside:avoid}
.nav{background:#16202b;color:#fff;display:flex;align-items:center;gap:10px;padding:8px 14px}
.nav button{border:0;border-radius:10px;background:var(--acc);color:#fff;font-size:17px;font-weight:700;padding:9px 22px;cursor:pointer}
.nav button.sec2{background:#2b3a49}.nav button:disabled{opacity:.35;cursor:default}
.nav .cnt{margin-left:auto;color:#aebbc8}.nav .hint{color:#8fa0b1;font-size:13px}
.now{animation:glow 1.1s ease-in-out infinite alternate}
@keyframes glow{from{filter:drop-shadow(0 0 2px #ff2aa8)}to{filter:drop-shadow(0 0 11px #ff2aa8) drop-shadow(0 0 3px #ff2aa8)}}
.old{opacity:.8}.old .htag,.old .wlabel{display:none}.ghost{opacity:.28!important;filter:grayscale(.4)}
@media(max-width:980px){main{grid-template-columns:1fr;grid-template-rows:55% 45%}}
"""

JS = r"""
const SL=window.SLIDES,svg=document.querySelector('#figbox svg'),main=document.querySelector('main');
let k=0,showAll=false,vb=null,raf=0;const FULL=window.FULLBOX;
const $=(s)=>document.querySelector(s);
function setVB(t,animate){if(!vb||!animate){vb=t.slice();svg.setAttribute('viewBox',vb.join(' '));return}
 const from=vb.slice(),t0=performance.now(),D=380;cancelAnimationFrame(raf);
 (function step(now){const p=Math.min(1,(now-t0)/D),e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;
  vb=from.map((v,i)=>v+(t[i]-v)*e);svg.setAttribute('viewBox',vb.join(' '));if(p<1)raf=requestAnimationFrame(step)})(t0)}
function apply(animate){const s=SL[k];
 main.classList.toggle('textonly',s.kind!=='step');
 document.querySelectorAll('[data-gstep]').forEach(e=>{const g=+e.dataset.gstep,u=e.dataset.until;
  const gh=(s.ghost||[]).includes(e.dataset.ref||e.dataset.id);
  const vis=(g<=k&&(u===undefined||k<=+u))||gh;e.style.display=vis?'':'none';
  e.classList.toggle('now',vis&&g===k&&!gh);e.classList.toggle('old',vis&&g<k&&!gh);e.classList.toggle('ghost',gh)});
 if(s.kind==='step')setVB(showAll?FULL:s.focus,animate);
 $('#panel').innerHTML=s.html;$('#panel').scrollTop=0;
 document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c.dataset.stage===s.stage));
 $('#bar').style.width=((k)/(SL.length-1)*100)+'%';$('#cnt').textContent=(k+1)+' / '+SL.length;
 $('#prev').disabled=k===0;$('#next').disabled=k===SL.length-1;
 try{localStorage.setItem('mp_slide',k)}catch(e){}history.replaceState(null,'','#'+(k+1))}
function go(i,animate=true){k=Math.max(0,Math.min(SL.length-1,i));apply(animate)}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
 if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(k+1)}
 else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(k-1)}
 else if(e.key==='Home')go(0);else if(e.key==='End')go(SL.length-1);
 else if(e.key==='a'||e.key==='A'){showAll=!showAll;apply(true)}
 else if(e.key==='f'||e.key==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}});
document.addEventListener('click',e=>{const b=e.target.closest('button[data-copy]');if(b){const t=b.dataset.copy;
 (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(()=>{const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(_){}ta.remove()});
 b.textContent='copiado';setTimeout(()=>b.textContent='copiar',1200)}});
let sx=null;document.addEventListener('touchstart',e=>{sx=e.touches[0].clientX},{passive:true});
document.addEventListener('touchend',e=>{if(sx===null)return;const d=e.changedTouches[0].clientX-sx;if(Math.abs(d)>70)go(k+(d<0?1:-1));sx=null});
let start=0;const h=parseInt((location.hash||'').slice(1));if(h>=1&&h<=SL.length)start=h-1;
else{try{start=Math.min(SL.length-1,parseInt(localStorage.getItem('mp_slide')||'0')||0)}catch(e){}}
go(start,false);
"""

NAMES = {"U1": "ESP32", "M1": "HC-SR04", "M2": "TCRT5000", "P1": "potenciômetro", "M3": "LCD"}
STAGE_CHIP = {"A": "A · ESP32", "B": "B · HC-SR04 ★", "C": "C · TCRT5000", "D": "D · LCD", "E": "E · final"}


def _h(s) -> str:
    return html.escape(str(s))


def _md(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", _h(s))


def hole_ctx(lay: Layout, hole: str, placed: set[str]) -> str:
    """O que esta (ou ficara) na mesma tira da protoboard, para o iniciante achar o furo."""
    if model.rail_sign(hole):
        net = "5 V" if model.rail_sign(hole) == "+" else "GND"
        return f"{net} · use o mesmo segmento do trilho; confira se não há divisão no meio"
    grp = model.hole_group(hole)
    occ = lay.occupied_holes(model.STAGE_ORDER[-1])
    now, later = [], []
    for h, users in occ.items():
        if h == hole or model.hole_group(h) != grp:
            continue
        for u in users:
            if re.match(r"^W\d+\.[ab]$", u):
                continue
            ref, pin = u.split(".", 1)
            c = lay.components[ref]
            if c["type"] == "esp32":
                phrase = f"do pino {lay.board.resolve(pin).label} da ESP32"
            elif c["type"] == "resistor":
                phrase = f"da perna de {ref}"
            else:
                phrase = f"do pino {pin} do {NAMES.get(ref, ref)}"
            (now if ref in placed else later).append(phrase)
    if now:
        b, _ = model.board_of(model.parse_hole(hole)[0])
        num, row = model.parse_hole(hole)
        _, local = model.board_of(num)
        side = "A–E" if row in "ABCDE" else "F–J"
        board = "" if b == 1 else f" da P{b}"
        return f"mesma linha {local}{board}, lado {side}: " + " e ".join(dict.fromkeys(now))
    col = model.parse_hole(hole)[0]
    b, local = model.board_of(col)
    col = local if b == 1 else f"{local} da P{b}"
    if later:
        return f"linha {col}: onde ficará o pino {later[0].split('pino ')[-1] if 'pino' in later[0] else later[0]} (entra depois)"
    return f"linha {col} (livre)"


def _res_svg(bands: list[str]) -> str:
    out = ['<svg width="132" height="30" viewBox="0 0 132 30" xmlns="http://www.w3.org/2000/svg">',
           '<path d="M2,15 H26 M106,15 H130" stroke="#9aa0a6" stroke-width="3" stroke-linecap="round"/>',
           '<rect x="24" y="4" width="84" height="22" rx="11" fill="#d9c28e" stroke="#8a7440"/>']
    xs = [44, 58, 72, 92]
    for x, b in zip(xs, bands):
        out.append(f'<rect x="{x}" y="4" width="7" height="22" fill="{BAND_COLORS[b]}" stroke="#0003" stroke-width=".6"/>')
    out.append("</svg>")
    return "".join(out)


BAND_PT = reports.BAND_PT


def _card_resistor(lay: Layout, ref: str, measure: bool) -> str:
    c = lay.components[ref]
    bands = model.resistor_bands(c["ohms"], c["tolerance"], lay.modules["resistor_color_code"])
    lo, hi = c["ohms"] * (1 - c["tolerance"]), c["ohms"] * (1 + c["tolerance"])
    legs = " e ".join(f'<span class="hole">{_h(model.hole_label(h))}</span>' for h in c["legs"])
    names = "–".join(BAND_PT[b] for b in bands)
    names_rev = "–".join(BAND_PT[b] for b in reversed(bands))      # lendo a partir da faixa dourada
    extra = (f'<div class="m">Meça: <b>{model.fmt_ohms(lo)} a {model.fmt_ohms(hi)}</b></div>' if measure
             else f'<div class="m">Pernas nos furos {legs}</div>')
    note = f'<div class="m">{_h(c["note"])}</div>' if c.get("note") and not measure else ""
    return (f'<div class="card" style="border-left-color:#8a7440"><div class="t">{ref} · {model.fmt_ohms(c["ohms"])} <span class="m">({_h(c["label"])})</span></div>'
            f'{_res_svg(bands)}<div class="m">{names}</div>'
            f'<div class="m">a partir do dourado: <b>{names_rev}</b></div>{extra}{note}</div>')


def _card_wire(lay: Layout, w: dict, placed: set[str], temp: bool = False) -> str:
    colr = WIRE_COLORS.get(w.get("color", "grey"), "#999")
    cname = reports.COLOR_PT.get(w.get("color", "grey"), w.get("color", ""))
    a, b = w["from"], w["to"]
    saf = f'<div class="m" style="color:var(--bad)">⚠ {_h(w["safety"])}</div>' if w.get("safety") else ""
    label = _h(w.get("label", ""))
    return (f'<div class="card" style="border-left-color:{colr}"><div class="t"><span class="swatch" style="background:{colr}"></span>'
            f'{"jumper TEMPORÁRIO" if temp else "Fio " + w["id"]} · {cname} no desenho</div><div class="m">{label}</div>'
            '<div class="m">A cor do seu fio pode ser outra; identifique pelas pontas.</div>'
            f'<div>Ponta 1: <span class="hole">{_h(model.hole_label(a))}</span> <span class="m">{_h(hole_ctx(lay, a, placed))}</span></div>'
            f'<div>Ponta 2: <span class="hole">{_h(model.hole_label(b))}</span> <span class="m">{_h(hole_ctx(lay, b, placed))}</span></div>{saf}</div>')


def _card_comp(lay: Layout, c: dict) -> str:
    if c["type"] == "esp32":
        return ('<div class="card"><div class="t">ESP32 DevKit · perfil assumido</div><div class="m">Atravessando o canal central, das colunas '
                f'<b>{c["placement"]["col0"]}</b> a 19; USB para a <b>esquerda</b>, para fora da placa. Fileira I (de cima): <b>5V na coluna 1 e 3V3 na 19</b>; fileira B (de baixo): <b>CLK na coluna 1 e GND na 19</b>. '
                'Só as fileiras <b>A</b> e <b>J</b> ficam livres.</div></div>')
    note = f'<div class="m">{_h(c["note"])}</div>' if c.get("note") else ""
    if c.get("offboard"):
        leads = c["offboard"].get("leads", {})
        rows = "".join(
            f'<tr><td><b>{n}</b></td><td><span class="swatch" style="background:{WIRE_COLORS.get(leads.get(n, "grey"), "#999")}"></span>'
            f'{_h(reports.COLOR_PT.get(leads.get(n, "grey"), ""))}</td><td><span class="hole">{_h(model.hole_label(h))}</span></td></tr>'
            for n, h in c["pins"].items())
        unused = [p for p in lay.modules["modules"][c["type"]]["pin_order"] if p not in c["pins"]]
        nc = f'<div class="m">Sem fio: {", ".join(unused)}.</div>' if unused else ""
        return (f'<div class="card"><div class="t">{c["ref"]} · {_h(c["label"])}</div>'
                '<div class="m">Fora da protoboard: um jumper <b>fêmea–macho</b> por pino (fêmea no pino do módulo, macho no furo). '
                'No trilho, use o mesmo segmento ligado à alimentação: o trilho pode ser dividido.</div>'
                f'<table class="p"><tr><th>Pino</th><th>Fio</th><th>Vai em</th></tr>{rows}</table>{nc}{note}</div>')
    rows = "".join(f'<tr><td><b>{n}</b></td><td><span class="hole">{_h(model.hole_label(h))}</span></td></tr>' for n, h in c["pins"].items()
                   if not (c["type"] == "lcd2004a" and n in ("D0", "D1", "D2", "D3")))
    nc = '<div class="m">D0–D3: encaixam mas ficam sem fio.</div>' if c["type"] == "lcd2004a" else ""
    return (f'<div class="card"><div class="t">{c["ref"]} · {_h(c["label"])}</div><div class="m">Encaixe os pinos nestes furos:</div>'
            f'<table class="p"><tr><th>Pino</th><th>Furo</th></tr>{rows}</table>{nc}{note}</div>')


def build_slides(lay: Layout):
    """Retorna (slides, step_of, until_of, scene)."""
    steps = lay.raw["build_steps"]
    temp = {t["id"]: t for t in lay.raw.get("temporary_wires", [])}
    markers = {m["id"]: m for m in lay.raw.get("markers", [])}
    slides: list[dict] = []
    # --- intro e materiais ---
    slides.append({"kind": "intro", "stage": "", "title": "MotionPet · montagem em protoboard"})
    slides.append({"kind": "materials", "stage": "", "title": "O que você vai precisar"})
    index = {}
    for st in model.STAGE_ORDER:
        for s in steps[st]:
            index[(st, s["n"])] = len(slides)
            slides.append({"kind": "step", "stage": st, "step": s})
    slides.append({"kind": "errors", "stage": "", "title": "Se algo der errado"})
    slides.append({"kind": "noport", "stage": "", "title": "A ESP32 não aparece como porta COM"})

    step_of: dict[str, int] = {}
    until_of: dict[str, int] = {}
    for (st, n), idx in index.items():
        s = next(x for x in steps[st] if x["n"] == n)
        for ident in s.get("adds", []):
            assert ident not in step_of, f"{ident} aparece em dois passos"
            step_of[ident] = idx
        for ident in s.get("temp", []):
            step_of[ident] = idx
            until_of[ident] = idx
        if s.get("marker"):
            step_of[s["marker"]] = idx
            until_of[s["marker"]] = idx
    scene = Scene(stage=model.STAGE_ORDER[-1], bare=True, show_tags=True, tag_scale=1.4, highlight_new=False, step_of=step_of, until_of=until_of,
                  temp_wires=[dict(t) for t in temp.values() if t["id"] in step_of],
                  markers=[dict(m) for m in markers.values() if m["id"] in step_of])
    return slides, index, step_of, until_of, scene, temp, markers


def _focus_rect(boxes: list[tuple[float, float, float, float]], full: tuple[float, float, float, float], aspect: float = 1.6):
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    w, h = x1 - x0, y1 - y0
    w, h = max(w, 780.0), max(h, 780.0 / aspect)
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fx, fy, fw, fh = full
    w, h = min(w, fw), min(h, fh)
    x = min(max(cx - w / 2, fx), fx + fw - w)
    y = min(max(cy - h / 2, fy), fy + fh - h)
    return [round(x, 1), round(y, 1), round(w, 1), round(h, 1)]


MATERIALS = [
    ("ESP32 DevKit (ESP-WROOM-32, USB-C)", "1", "Conte os pinos e meça a distância entre as fileiras (confirmação C01)."),
    ("Meia-protoboard 30 linhas (A–J × 1–30) com trilhos + e −", "1 + 1", "Para o HC-SR04, use P1; P2 só é necessária para o LCD. Trilho +: 5 V. Trilho −: GND. Confira se cada trilho é contínuo."),
    ("Cabo USB de DADOS", "1", "Cabo só de carga não cria a porta COM."),
    ("HC-SR04", "1", "Estágio B, fora da placa."),
    ("Módulo TCRT5000 (LM393, 4 pinos)", "1", "Estágio C, fora da placa."),
    ("LCD 2004A (20×4, 16 pinos)", "1", "Estágio D, encaixado na P2."),
    ("Resistor 1 kΩ (dourado, vermelho, preto, marrom — lendo da faixa dourada)", "3", "R1 e R2 do divisor; R4 do contraste do LCD."),
    ("Resistor 300 Ω (dourado, marrom, preto, laranja — lendo da faixa dourada)", "2", "R3 do divisor; R5 do backlight do LCD."),
    ("Jumpers macho–macho", "~17", "Os 6 sinais do LCD (W12–W17) e o W3 são os longos (15–20 cm); o resto é curto."),
    ("Jumpers fêmea–macho", "7", "4 para o HC-SR04 e 3 para o TCRT5000."),
    ("Multímetro e instrumento para pulsos", "se disponíveis", "Permitem verificar ligações e tensão; sem medições, a segurança elétrica permanece pendente."),
]


def build_guide(lay: Layout, figs=None) -> str:
    slides, index, step_of, until_of, scene, temp, markers = build_slides(lay)
    svg, meta = render_scene(lay, scene)
    full = (0.0, 0.0, meta["width"], meta["height"])
    proj = lay.raw["project"]
    placed_by_slide: dict[int, set[str]] = {}
    out_slides = []
    last_focus = list(full)
    n_by_stage = {st: len(lay.raw["build_steps"][st]) for st in model.STAGE_ORDER}
    first_of_stage = {st: index[(st, 1)] for st in model.STAGE_ORDER}
    for i, s in enumerate(slides):
        kind = s["kind"]
        d = {"kind": "step" if kind == "step" else "text", "stage": s.get("stage", "")}
        if kind == "intro":
            conf = "".join(f"<li><b>{c['id']}</b> — {_h(c['text'])}</li>" for c in lay.raw["confirmations"] if c["blocks"] in ("B",))
            d["html"] = (f'<div class="kicker">{_h(proj["name"])} · Ciclo {proj["cycle"]} · firmware {_h(proj["firmware_version"])}</div>'
                         '<h1 style="font-size:40px">Montagem em protoboard, passo a passo</h1>'
                         '<p class="big">Para continuar sua montagem, clique em <b>B · HC-SR04 ★</b> no topo. Cada passo mostra o que conferir e onde conectar.</p>'
                         '<div class="card"><div class="t">No seu sensor: siga as letras, não só as cores</div>'
                         '<div class="m">ECHO = azul · GND = branco · TRIG e VCC = dois fios vermelhos. Confira cada inscrição no sensor.</div></div>'
                         f'<div class="sec">O que já foi verificado</div><p class="m">{_h(proj.get("bench_observation", ""))}</p>'
                         '<div class="warn">Status: PENDING_PHYSICAL_VALIDATION — a montagem e os periféricos ainda não foram validados. '
                         'Desconecte a USB para montar. Confira a serigrafia e as medidas antes de seguir o desenho; meça o pico real do ECHO antes de conectar o GPIO34.</div>'
                         '<div class="sec">Confirme antes (bloqueiam o Estágio B)</div><ul class="checks">' + conf + '</ul>'
                         f'<p class="m">Dica: tecla <b>A</b> mostra a protoboard inteira; <b>F</b> tela cheia. Estágio B (★) é a prioridade.</p>')
        elif kind == "materials":
            rows = "".join(f"<tr><td>{_h(a)}</td><td>{_h(b)}</td><td>{_h(c)}</td></tr>" for a, b, c in MATERIALS)
            d["html"] = (f'<div class="kicker">Antes de começar</div><h1>{_h(s["title"])}</h1>'
                         f'<table class="p"><tr><th>Item</th><th>Qtd.</th><th>Observação</th></tr>{rows}</table>')
        elif kind == "errors":
            from .guide_extra import COMMON_ERRORS
            d["html"] = f'<div class="kicker">Ajuda</div><h1>{_h(s["title"])}</h1><ul class="cols2">' + "".join(f"<li>{_h(e)}</li>" for e in COMMON_ERRORS) + "</ul>"
        elif kind == "noport":
            from .guide_extra import NO_PORT
            d["html"] = f'<div class="kicker">Ajuda</div><h1>{_h(s["title"])}</h1><ol class="how">' + "".join(f"<li>{_md(e)}</li>" for e in NO_PORT) + "</ol>"
        else:
            st = s["stage"]
            step = s["step"]
            n, total = step["n"], n_by_stage[st]
            placed = {c["ref"] for c in lay.components.values() if step_of.get(c["ref"], -1) <= i and c["ref"] in step_of}
            placed |= {"BB1"}
            parts = [f'<div class="kicker">Estágio {st} · {_h(lay.raw["stages"][st]["title"])} · passo {n} de {total}</div>',
                     f'<h1>{_h(step["title"])}</h1>']
            if step.get("hold"):
                parts.append('<div class="hold">PONTO DE PARADA — não avance sem conferir</div>')
            cards = []
            for ident in step.get("measure", []):
                cards.append(_card_resistor(lay, ident, True))
            for ident in step.get("adds", []):
                if ident in lay.components:
                    c = lay.components[ident]
                    cards.append(_card_resistor(lay, ident, False) if c["type"] == "resistor" else _card_comp(lay, c))
                else:
                    cards.append(_card_wire(lay, lay.wires[ident], placed))
            for ident in step.get("temp", []):
                cards.append(_card_wire(lay, temp[ident], placed, temp=True))
            if cards:
                parts.append('<div class="sec">' + ("Meça agora" if step.get("measure") and not step.get("adds") else "Adicione agora") + '</div>' + "".join(cards))
            parts.append(f'<div class="sec">Como</div><div class="how">{_md(step["text"])}</div>')
            if step.get("checks"):
                parts.append('<ul class="checks">' + "".join(f"<li>{_h(c)}</li>" for c in step["checks"]) + "</ul>")
            if step.get("warn"):
                parts.append(f'<div class="warn">⚠ {_h(step["warn"])}</div>')
            for cmd in step.get("commands", []):
                parts.append(f'<pre>{_h(cmd)}<button data-copy="{_h(cmd)}">copiar</button></pre>')
            # zoom
            ids = list(step.get("focus", [])) or (list(step.get("adds", [])) + list(step.get("temp", [])) + ([step["marker"]] if step.get("marker") else []))
            boxes = [b for b in (item_bbox(lay, meta, x, scene) for x in ids) if b]
            if boxes:
                last_focus = _focus_rect(boxes, full)
            d["focus"] = last_focus
            d["ghost"] = [x for x in step.get("focus", []) if x in lay.components and step_of.get(x, -1) > i]
            d["html"] = "".join(parts)
            d["stage"] = st
        d["title"] = s.get("title", "")
        out_slides.append(d)
    chips = "".join(f'<button class="chip{" prio" if st == "B" else ""}" data-stage="{st}" onclick="go({first_of_stage[st]})">{_h(STAGE_CHIP[st])}</button>' for st in model.STAGE_ORDER)
    svg = re.sub(r'\s(width|height)="[\d.]+"', "", svg, count=2)
    svg = svg.replace('<svg ', '<svg preserveAspectRatio="xMidYMid meet" ', 1)
    payload = json.dumps(out_slides, ensure_ascii=False).replace("</", "<\\/")
    return ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>MotionPet — montagem em slides</title><style>{CSS}</style></head><body>"
            f'<div class="stagewrap"><div style="padding:10px;background:#fff0cc;color:#643d00;font-weight:700">CAD paralelo histórico — D/E não correspondem ao LCD I²C atual. <a href="../guia_montagem_final.html">Abrir montagem final I²C</a></div><div class="top"><span class="brand">MotionPet · histórico</span><div class="chips">{chips}</div></div><div class="prog"><i id="bar"></i></div></div>'
            f'<main><div id="figbox"><div class="figtools"><button onclick="showAll=!showAll;apply(true)">ver tudo (A)</button></div>{svg}</div>'
            '<div class="panel" id="panel"></div></main>'
            '<div class="nav"><button class="sec2" id="prev" onclick="go(k-1)">◀ Voltar</button><button id="next" onclick="go(k+1)">Avançar ▶</button>'
            '<span class="hint">← → navegam · A ver tudo · F tela cheia</span><span class="cnt" id="cnt"></span></div>'
            f"<script>window.SLIDES={payload};window.FULLBOX={json.dumps([0, 0, round(meta['width'], 1), round(meta['height'], 1)])};{JS}</script></body></html>")
