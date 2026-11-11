# Atualização de montagem — 10/11/2026

**Revisão 4 — diagnóstico sem refazer a montagem:** o teste opcional de iluminação preserva F1–F4 e os demais componentes já instalados. Com USB fora, remove F16/F17 antes de alimentar o LCD em 5 V; move somente F14 de P2:+3 para P1:+3 e F15 de P2:−3 para P1:−4, contatos livres na montagem normal. A volta devolve a alimentação à P2/3V3 antes de recolocar SDA/SCL. O guia bloqueia captura e navegação durante esse diagnóstico e mantém o aviso após recarregar até a restauração ser declarada. Esse teste não valida texto nem autoriza SDA/SCL diretos com VCC de 5 V. A netlist, o desenho e as tabelas do diagnóstico são derivados da mesma origem que a montagem normal.

**Revisão 3 — recuperar a evidência antes de repetir o mapeamento:** histórico local de 05/11 confirmou os furos do teste LCD: GND6J, VCC19J (3V3), SDA14A e SCL17A; scanner 0x27 e texto confirmado pelo usuário. O resumo com origem e limites está em [bench_verified_wiring.md](bench_verified_wiring.md). A montagem atual passa a alimentar o GND por 6J, não por 2J. A alternativa 2J não foi validada por esse teste e não deve substituir o ponto conhecido. Isso não comprova a causa da falha de 10/11. Consultar esse registro antes de pedir novamente foto/mapeamento da mesma placa.

**Revisão 2:** prioridade para montagem simples, uso das duas protoboards e teste após cada componente. P1 usa um par lateral +5V/GND e P2 um par +3V3/GND, com uma ponte entre negativos. Usar só o primeiro grupo de cinco furos de cada trilho evita depender de continuidade até outras regiões; conferir esse grupo fisicamente. LCD e TCRT5000 usam apenas jumpers e são testados primeiro. Os três resistores disponíveis ficam exclusivamente no divisor de ECHO na região central da P2. A opção sem resistores externos para o ultrassom exige conversão de nível apropriada; não presumir alimentação de 3V3 para o HC-SR04 padrão. Botões do guia usam `terminal.bench.guide`, serviço local sem simulação exposta e sem gravação automática, com distinção entre serial observada e declarações do operador.

O CAD descrito abaixo é o registro **paralelo histórico**. Para a montagem física atual com backpack PCF8574, siga [o guia final I²C](bench_assembly_guide.md) e [o roteiro visual](../hardware/guia_montagem_final.html). A netlist atual por furos é `hardware/netlist/motionpet_final_i2c.json`; o antigo mapa de pinos foi preservado em `hardware/netlist/archive/pinout_parallel.h`. Os testes individuais foram relatados pelo usuário; a integração está pendente. As observações de ferramentas e medições abaixo se referem à geração original, não aos checks atuais.

---

# Decisoes tecnicas — representacao eletronica (CAD) do MotionPet

Data: 2026-10-29 · Escopo: Estagio B (prioridade) + A, C, D (LCD na P2) e E · Status: `PENDING_PHYSICAL_VALIDATION` (Ciclo 5 permanece aberto; nenhum Ciclo 6 iniciado).

## 1. Decisoes
| ID | Decisao | Motivo |
|---|---|---|
| D1 | A netlist JSON (`hardware/netlist/motionpet.netlist.json`) e a unica fonte; tudo e gerado dela | "circuito antes da imagem"; nenhuma conexao sem pino real e justificativa |
| D2 | Pinagem do firmware **inalterada** (GPIO5, 34, 35, 39, 36, 19, 18, 21, 22, 23, 27); testes comparam `firmware/main/pinout_config.h`, `terminal.bench.pinout.ALL_ASSIGNED_GPIOS` e a netlist | preservar o trabalho do Antigravity |
| D3 | Perfil de placa assumido: **ESP32 DevKit 38 pinos, 0,9 pol entre fileiras** (confirmar em C01) | e o unico leiaute comum que deixa 1 furo acessivel de cada lado numa protoboard unica |
| D4 | **Meia-protoboard de 30 colunas (A–J × 1–30)** para os estagios A–C (P1); a P2 so recebe o LCD (D10), geometria/barramentos do `Half_breadboard_v2` do Fritzing; o modelo e parametrizado por perfil (`data/breadboards.json`: `bb400` ativo, `bb830` mantido) | informado pelo usuario; geometria real e conferida por teste |
| D5 | **(corrigido em 2026-10-29)** ESP32 com a USB-C na ponta da coluna 1; como na DevKitC, **5V e CLK ficam junto da USB** (coluna 1) e o 3V3/GND do pino 1 na coluna 19. Lado J2 na fileira **I**, lado J3 na **B**. (Antes o modelo punha o pino 1 junto da USB, o que estava errado.) → so as fileiras **A** e **J** ficam acessiveis; sobram as colunas **21–30** | fisica do encaixe; 19 das 30 colunas |
| D6 | Estagio B: HC-SR04 em `21J–24J`; R1 `23H–27H` (1 kΩ); R2 `27F–30F` (1 kΩ); R3 `30G–24G` (300 Ω); no do divisor = coluna 27, junção R2/R3 = coluna 30 (grupo F–J); fios W1 `19A→21H`, W2 `7J→24I`, W3 `10J→22I`, W4 `27I→5A` | W4 (no → GPIO34) e o unico fio do sinal e so entra depois do ensaio estatico (ponto de parada) |
| D10 | **Estagio D (LCD) na 2ª meia-protoboard (P2)**, encaixada na ponta da coluna 30 da P1. Perfil `bb400x2` (60 colunas internas; furos da P2 escritos `P2:12E`). LCD com o conector na fileira A da P2 (VSS em `P2:12A` … K em `P2:27A`), display para fora da placa. RW, VSS e K no GND por jumpers curtos (W12–W14); R4 = 1 kΩ (contraste, V0→GND, ajustavel: C07); R5 = 300 Ω (backlight); 3 fios de alimentacao (W11 GND, W15/W16 5 V) e 6 de sinal (W17–W22). Estagios A–C nao mudaram | o usuario juntou duas meias-protoboards e pediu montagem simples |
| D11 | **Divisor 1 kΩ / (1 kΩ + 300 Ω)**: unica combinacao **em serie** com ≤ 3 resistores de 1 kΩ e 300 Ω que respeita o teto de 3,30 V e VIH no pior caso (teste `test_chosen_divider_is_the_cheapest_safe_combination_of_1k_and_300`). Havia uma variante em paralelo (R1 = 1 kΩ‖300 Ω, R2 = 300 Ω) com a mesma tensao, mas ela puxaria ≈ 9,4 mA do pino ECHO do HC-SR04 (contra ≈ 2,2 mA): descartada. Leitura das faixas a partir da dourada: 1 kΩ = dourado-vermelho-preto-marrom; 300 Ω = dourado-marrom-preto-laranja. Precisa de 2 resistores de 1 kΩ e 1 de 300 Ω | resistores informados pelo usuario |
| D12 | **Montagem simplificada (bancada real):** trilhos de BAIXO usados como barramento (vermelho + = 5 V vindo do 19A; azul − = GND vindo do 14A; P2 recebe por 2 fios-ponte). HC-SR04 e TCRT5000 ficam FORA da placa, com jumpers fêmea–macho (VCC/GND no trilho ou no 1A, sinais direto nos furos da ESP32/divisor). Divisor na metade de baixo da P1 (R1 `22C–26C`, R2 `26D–29D`, R3 `29A`→trilho −; nó = coluna 26; fio W3 `26E→5A`). LCD na fileira J da P2 (VSS `P2:12J`), cada pino de alimentação com um jumper curto até o trilho; R4/R5 atravessam o canal. **Potenciômetro removido** (firmware `DEFAULT_POT_ENABLED=false`). Geometria dos trilhos medida no SVG do Fritzing (pinN em x = 17 + 9(N−3)) | pedido do usuário: "o mais simples possível e que facilite a montagem na vida real"; trilhos e módulos soltos eliminam os conflitos de módulos pendurados |
| D7 | `.fzz` gerado por codigo proprio (nao pelo MCP) | o MCP escolhido liga conector a conector e nao modela pecas encaixadas nos furos |
| D8 | MCP escolhido: fedoragobrowse/fritzing-mcp (MIT) — **configurado, nao verificado** (ver `hardware/mcp/README.md`) | roda sem o app Fritzing; codigo revisado; execucao negada no ambiente de geracao |
| D9 | Wokwi: `board-esp32-devkit-c-v4` (38 pinos); TCRT5000 omitido (sem modelo Wokwi) | mesmo conjunto de GPIO |

## 2. Descobertas que merecem sua atencao
1. **Divisor com os resistores que o usuario tem (1 kΩ e 300 Ω, ±5 %)**: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. Nominal 2,83 V @ 5,00 V; pior caso **3,096 V** (folga de 204 mV ao teto de 3,30 V) e minimo **2,567 V** (92 mV acima de VIH = 2,475 V); corrente pedida ao ECHO ≈ 2,2 mA. O par 2,2 kΩ / 3,3 kΩ original (3,00 V; pior caso 3,275 V) continua aceito pelo validador, mas **nao** e o que ha na bancada. Os resistores nao servem diretamente como R1/R2: 1 kΩ/300 Ω da 1,15 V (leitura falha) e 300 Ω/1 kΩ da 3,85 V (queima o GPIO34) — ha testes para isso.
2. **LCD V0**: um resistor sozinho de V0 a GND nao gera "0,4–0,8 V". O desenho usa R4 de 1 kΩ para GND; se necessario, ajustar com potenciometro entre VDD e GND, com cursor em V0. O contraste e a compatibilidade do modulo real continuam pendentes (C07). Veja `hardware_safety.md`.
3. **Placa de 30 pinos / 1,0 pol (25,4 mm)**: numa protoboard unica so um lado fica acessivel; o Estagio B precisa dos dois lados (IO34 e 5V de um lado, IO5 do outro). Nesse caso este leiaute **nao serve** — sera preciso a variante com jumpers femea–macho ou duas protoboards.
4. A doc cita `firmware/pinout_config.h`; o arquivo real e **`firmware/main/pinout_config.h`**.
5. GPIO5 (TRIG) e pino de strapping: uso como saida e aceitavel; o validador registra `STRAPPING_PIN_NOTED` (info).
6. As fotos da NODEMCU ESP-32S V1.1 mostram **quatro** pinos GND; o segundo a partir da USB no lado do 5V e GND, nao CMD. O modelo trata os quatro como ligados internamente (hipotese A6, sem medicao fisica).
7. Corrente: a USB alimenta HC-SR04 + backlight do LCD (C08).

## 3. O que NAO foi feito / limites
- **Nenhuma validacao fisica.** Wokwi nao substitui multimetro e nao valida o divisor.
- **Build do firmware (PlatformIO) nao reexecutado**: o registro do PlatformIO (`api.registry.platformio.org`) esta bloqueado no ambiente de geracao. Nenhum arquivo de firmware foi alterado; os 271 testes originais foram executados (Python 3.13.16, Linux aarch64 — nao no Windows).
- **`wokwi-cli`**: lint executado com sucesso na versao 0.29.1 em 2026-10-29; houve aviso informativo de que `board-esp32-devkit-c-v4` nao e documentado. O cenario de teste **nao foi executado**, pois nao havia token configurado.
- **MCP de Fritzing**: instalacao/execucao negadas; **nenhuma chamada MCP foi testada**.
- **`.fzz` nao aberto no Fritzing** (nao ha Fritzing na maquina de geracao). Verificado: ZIP/XML validos, conexoes reciprocas, redes reextraidas do XML = netlist (A–C), conectores sobre os furos (≤ 0,6 px), `moduleId` reais do Fritzing. A peca da ESP32 e **generica** (nao e o modelo da sua placa).
- Estagio C e **provisorio** (ordem de pinos do TCRT5000 nao confirmada; 6 fios, 4 deles longos). Estagio D: contraste (R4) e backlight (R5) a ajustar na bancada; fios de sinal do LCD com 15–20 cm.
- Trilhos: so os de BAIXO sao usados (D12). Se a linha vermelha/azul tiver uma falha no meio, o trilho e cortado: ligue as duas metades com um jumper.

## 4. Pendencias de confirmacao fisica
Ver `confirmations` na netlist. Bloqueiam a montagem: **C01** (placa), **C02** (protoboard: 30 colunas e sentido das letras), **C03** (resistores), **C04** (HC-SR04), **C09** (jumpers). **C10**: decidir como ligar o LCD.
