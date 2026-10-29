# Decisoes tecnicas — representacao eletronica (CAD) do MotionPet

Data: 2026-10-29 · Escopo: Estagio B (prioridade) + A/C/D/E · Status: `PENDING_PHYSICAL_VALIDATION` (Ciclo 5 permanece aberto; nenhum Ciclo 6 iniciado).

## 1. Decisoes
| ID | Decisao | Motivo |
|---|---|---|
| D1 | A netlist JSON (`hardware/netlist/motionpet.netlist.json`) e a unica fonte; tudo e gerado dela | "circuito antes da imagem"; nenhuma conexao sem pino real e justificativa |
| D2 | Pinagem do firmware **inalterada** (GPIO5, 34, 35, 39, 36, 19, 18, 21, 22, 23, 27); testes comparam `firmware/main/pinout_config.h`, `terminal.bench.pinout.ALL_ASSIGNED_GPIOS` e a netlist | preservar o trabalho do Antigravity |
| D3 | Perfil de placa assumido: **ESP32 DevKit 38 pinos, 0,9 pol entre fileiras** (confirmar em C01) | e o unico leiaute comum que deixa 1 furo acessivel de cada lado numa protoboard unica |
| D4 | Protoboard de 830 pontos com a geometria/barramentos do `breadboard2` do Fritzing (verificada contra os 830 conectores e 130 barramentos) | geometria real e reprodutivel |
| D5 | ESP32 nas fileiras **B** (lado J2) e **I** (lado J3), pino 1 na coluna 4, USB a esquerda → so as fileiras **A** e **J** ficam acessiveis | fisica do encaixe |
| D6 | Estagio B: HC-SR04 em `30J–33J`; R1 `32H–36H`; R2 `36G–33G`; no do divisor = coluna 36 (grupo F–J); fios W1–W4 | W4 (no → GPIO34) e o unico fio do sinal e so entra depois do ensaio estatico (ponto de parada) |
| D7 | `.fzz` gerado por codigo proprio (nao pelo MCP) | o MCP escolhido liga conector a conector e nao modela pecas encaixadas nos furos |
| D8 | MCP escolhido: fedoragobrowse/fritzing-mcp (MIT) — **configurado, nao verificado** (ver `hardware/mcp/README.md`) | roda sem o app Fritzing; codigo revisado; execucao negada no ambiente de geracao |
| D9 | Wokwi: `board-esp32-devkit-c-v4` (38 pinos); TCRT5000 omitido (sem modelo Wokwi) | mesmo conjunto de GPIO |

## 2. Descobertas que merecem sua atencao
1. **Divisor 2,2 kΩ / 3,3 kΩ com resistores de ±5 %**: nominal 3,00 V (ok), mas no **pior caso 3,275 V @ 5,25 V** — so **25 mV** abaixo do teto de 3,30 V (o minimo e 2,73 V, acima de VIH = 2,475 V). Use resistores de 1 % ou **meça os seus** antes (`terminal.bench divider`). O validador emite `DIVIDER_MARGIN_THIN`.
2. **LCD V0 (`hardware_safety.md` §3.3)**: um resistor sozinho de V0 a GND nao gera "0,4–0,8 V": sem fonte, V0 ≈ 0 V (contraste maximo). Para 0,4–0,8 V use divisor 5 V/GND (ex.: 4,7 kΩ + 680 Ω ≈ 0,63 V) ou V0 direto ao GND. **Nao alterei a doc**; a netlist mantem R3 como `DESIGN_ISSUE_FLAGGED` (confirmacao C07).
3. **Placa de 30 pinos / 1,0 pol (25,4 mm)**: numa protoboard unica so um lado fica acessivel; o Estagio B precisa dos dois lados (IO34 e 5V de um lado, IO5 do outro). Nesse caso este leiaute **nao serve** — sera preciso a variante com jumpers femea–macho ou duas protoboards.
4. A doc cita `firmware/pinout_config.h`; o arquivo real e **`firmware/main/pinout_config.h`**.
5. GPIO5 (TRIG) e pino de strapping: uso como saida e aceitavel; o validador registra `STRAPPING_PIN_NOTED` (info).
6. Os 3 pinos GND da placa sao tratados como ligados internamente (hipotese A6; confirmar com multimetro).
7. Corrente: a USB alimenta HC-SR04 + backlight do LCD (C08).

## 3. O que NAO foi feito / limites
- **Nenhuma validacao fisica.** Wokwi nao substitui multimetro e nao valida o divisor.
- **Build do firmware (PlatformIO) nao reexecutado**: o registro do PlatformIO (`api.registry.platformio.org`) esta bloqueado no ambiente de geracao. Nenhum arquivo de firmware foi alterado; os 271 testes originais foram executados (Python 3.13.16, Linux aarch64 — nao no Windows).
- **`wokwi-cli`**: download e execucao negados pelo sistema de permissoes; `lint` e o cenario de teste **nao foram executados**.
- **MCP de Fritzing**: instalacao/execucao negadas; **nenhuma chamada MCP foi testada**.
- **`.fzz` nao aberto no Fritzing** (nao ha Fritzing na maquina de geracao). Verificado: ZIP/XML validos, conexoes reciprocas, redes reextraidas do XML = netlist (A–E), conectores sobre os furos (≤ 0,6 px), `moduleId` reais do Fritzing. A peca da ESP32 e **generica** (nao e o modelo da sua placa).
- Estagios C–E sao **provisorios** (ordem de pinos do TCRT5000 nao confirmada; V0 do LCD em aberto; fios longos).

## 4. Pendencias de confirmacao fisica (C01–C09)
Ver `confirmations` na netlist. Bloqueiam a montagem: **C01** (placa), **C02** (protoboard), **C03** (resistores), **C04** (HC-SR04), **C09** (jumpers).
