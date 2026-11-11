# hardware/ — representacao eletronica canonica do MotionPet

**Configuração escolhida em 10/11/2026: sem LCD.** Use [o desenho sem LCD](wokwi/montagem_atual/diagram_sem_lcd.json) e [o registro da bancada](wokwi/montagem_atual/README.md). A retirada física dos dois cabos do LCD aguarda confirmação. Os guias I²C abaixo registram a montagem anterior com LCD.

**Guia anterior com LCD: [guia final I²C](guia_montagem_final.html), [roteiro escrito](../docs/bench_assembly_guide.md) e `netlist/motionpet_final_i2c.json`.** Regenere com `.\.venv\Scripts\python.exe -m hardware.final_assembly`. O texto abaixo documenta o **CAD paralelo histórico**; seus estágios D/E, desenhos `.fzz`/SVG e Wokwi não representam o LCD com backpack atual. `python -m hardware.build` continua reproduzindo esse CAD histórico, identificado por avisos. O pinout de referência dele foi preservado em `netlist/archive/pinout_parallel.h`.

A revisão 4 usa as **duas protoboards e seus trilhos**, com GND da ESP32 em **6J**, recuperado do teste LCD de 05/11 ([registro](../docs/bench_verified_wiring.md)), com +5V na P1, +3V3 na P2 e negativos unidos. Somente o primeiro grupo de cinco furos de um par lateral por placa é usado. LCD e IR vêm primeiro, sem resistores externos; o HC-SR04 recebe o divisor na P2. O diagnóstico de iluminação mantém F1–F4, remove SDA/SCL e move apenas as pontas de alimentação do LCD para contatos livres dos trilhos da P1; o guia também mostra a restauração de 3V3 antes de reconectar os sinais. Para testes após cada instalação, rode `.\.venv\Scripts\python.exe -m terminal.bench.guide` e abra [127.0.0.1:8766](http://127.0.0.1:8766/).

> **Status oficial: `PENDING_PHYSICAL_VALIDATION`.** Nada aqui foi medido numa bancada. Tudo e consistencia de SOFTWARE
> (netlist ⇄ firmware ⇄ protoboard ⇄ CAD). Ciclo 5 permanece aberto; nenhum Ciclo 6 foi iniciado.

## Fluxo (circuito antes da imagem)
```
firmware/main/pinout_config.h ─► netlist canonica (JSON) ─► modelo fisico da protoboard ─► diagramas / .fzz / Wokwi / guia ─► validacao cruzada
```
A fonte do **CAD paralelo historico** e `hardware/netlist/motionpet.netlist.json` (componentes, furos, fios, redes, tensoes, cores, estados de validacao,
observacoes de seguranca, confirmacoes pendentes). Nada e desenhado a mao: `python -m hardware.build` gera tudo a partir dele.

## Como ver o Estagio B (prioridade)
1. Abra **`hardware/out/guia_montagem.html`** no navegador: e uma **apresentacao de slides** (um passo por slide, 34 no total).
   A protoboard vai sendo montada na tela, o item novo pisca em rosa, o zoom segue a regiao e o painel "ADICIONE AGORA" mostra cor do fio,
   furos de cada ponta e faixas dos resistores. Teclado: **← →** navegam, **A** mostra a protoboard inteira, **F** tela cheia. O Estagio B (★) esta nos slides 6–16; o LCD (Estagio D) fica na 2ª meia-protoboard (P2).
2. Imagens: `hardware/out/protoboard_estagioB.svg|png`, ensaio do divisor `protoboard_estagioB_passo5_ensaio_divisor.svg|png`,
   esquematico independente `esquematico_estagioB.svg|png`.
3. Tabelas: `hardware/out/fios_estagioB.csv`, `furos_estagioB.csv`, `estagioB.md` (redes, componentes/furos, fio a fio, mapa de furos).
4. Editavel: **`hardware/out/MotionPet_estagioB.fzz`** (Fritzing 1.0.x: *Arquivo → Abrir*). **Nao foi aberto no Fritzing** na geracao — confira a vista de protoboard.

## Arquivos
| Caminho | O que e |
|---|---|
| `netlist/motionpet.netlist.json` | fonte unica de verdade (A–E) |
| `data/boards.json`, `data/modules.json`, `data/breadboards.json` | perfis de placa (38/30 pinos), modulos (pinagem, tensoes, Fritzing/Wokwi) e protoboards (meia 30 colunas = `bb400`, completa 830 = `bb830`) |
| `netlist/archive/` | layout ARQUIVADO dos estagios D/E para protoboard de 830 pontos (nao se aplica a 30 colunas) |
| `model.py` | geometria e conectividade da protoboard (conferida contra os barramentos reais do Fritzing: `Half_breadboard_v2` e `breadboard2`), derivacao de redes, validador |
| `render_bb.py`, `render_schematic.py` | SVG da protoboard e esquematico (puros, deterministas) |
| `export_fz.py`, `fz_parts.py` | `.fz/.fzz` (pecas core do Fritzing + pecas genericas embutidas) e releitura das redes do XML |
| `export_wokwi.py`, `wokwi/` | `diagram.json`, `wokwi.toml`, cenario de teste (nao executados) |
| `reports.py`, `guide_html.py`, `build.py` | tabelas, guia HTML e orquestrador |
| `tools/` | `build_parts_db.py` (indice de pecas), `setup_fritzing_mcp.py`, `svg2png.py` (Chromium), `extract_geom.py` |
| `mcp/README.md` | avaliacao dos MCPs e estado real da configuracao |
| `out/` | artefatos gerados (reproduziveis; `MANIFEST.json` traz SHA-256) |

## Regenerar / editar
```powershell
.\.venv\Scripts\python.exe -m hardware.build            # SVG, .fzz, CSV, MD, HTML, Wokwi
.\.venv\Scripts\python.exe -m hardware.build --png      # + PNG (requer: pip install playwright; python -m playwright install chromium)
.\.venv\Scripts\python.exe -m pytest tests/test_hardware_cad.py
```
Para mudar um furo, cor, resistor ou a ordem de pinos de um modulo: edite **somente** o JSON da netlist, rode o build e os testes.
O validador reprova curtos, fios em GPIO6–11/12/TX/RX, GPIO em dominio de 5 V, modulos de 3,3 V em 5 V, divisor fora do teto de 3,30 V, etc.

## Hipoteses e pendencias
Veja `docs/cad_decisions.md` (decisoes, descobertas, limites) e as confirmacoes **C01–C09** na netlist / aba "Antes de comecar" do guia.
A mais importante: **C01** — a distancia entre as fileiras de pinos da SUA ESP32 (22,86 mm = 9 furos ou 25,4 mm = 10 furos) e a contagem de pinos.
