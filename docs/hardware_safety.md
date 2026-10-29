# Guia de Segurança Elétrica e Validação de Hardware — MotionPet (Ciclo 5)

> [!CAUTION]
> **AVISO DE SEGURANÇA CRÍTICO — STATUS `PENDING_PHYSICAL_VALIDATION`**
>
> - **Status de Pinagem:** `MOTIONPET_PINOUT_STATUS = "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"`
> - **Versão de Firmware Alvo:** `MOTIONPET_FW_VERSION = "0.5.0-cycle5"` ([pinout_config.h](file:///c:/Users/joaoh/Downloads/ChickenLittle/firmware/main/pinout_config.h))
>
> As atribuições de pinos, esquemas de condicionamento e níveis de tensão contidos neste documento estão reconciliados canonicamente com o firmware, mas **permanecem pendentes de validação física em bancada real** (nenhuma medição física foi inventada).
>
> O microcontrolador **ESP32 opera internamente em nível lógico de 3,3 V e NÃO é tolerante a 5 V**.
> **REGRA INEGOCIÁVEL DO CICLO 5:** **`3,5 V` NÃO é aceito como tensão segura para nenhum GPIO de 3,3 V do ESP32!** O teto máximo admissível medido no nó do divisor é estritamente **`<= 3,30 V`** (faixa recomendada de operação segura para nível lógico ALTO: **`2,50 V` a `3,20 V`**).
> **NÃO energize o circuito** antes de executar o *Checklist de Inspeção e Validação com Multímetro* (Seção 7) ou [cycle5_bench_checklist.md](file:///c:/Users/joaoh/Downloads/ChickenLittle/docs/cycle5_bench_checklist.md).

---

## 1. Topologia de Alimentação, Terra Comum e Reconciliação Canônica de Pinagem

### 1.1 Barramentos de Alimentação e Terra Comum (*Common GND*)

O sistema é alimentado pela porta USB (`5 V` nominal) do ESP32 DevKit. Os trilhos de alimentação na protoboard devem ser segregados de forma estrita:

1. **Trilho 5 V (`VBUS` / `VIN` / `5V`)**:
   - Fornecido pelo pino `5V` (ou `VIN` / `VBUS`) do DevKit (alimentação direta do barramento USB, tipicamente entre `4,75 V` e `5,25 V`).
   - Alimenta **exclusivamente**:
     - Sensor ultrassônico **HC-SR04** (`VCC = 5 V`, indispensável para excitação confiável dos transdutores piezelétricos de `40 kHz`).
     - Display **LCD 2004A V1.1** (`VDD` / pino 2 em `5 V`, e backlight `A` / pino 15 via resistor limitador quando aplicável).
2. **Trilho 3,3 V (`3V3`)**:
   - Fornecido pelo pino `3V3` do regulador linear LDO integrado à placa do ESP32 (`3,25 V` a `3,35 V`).
   - Alimenta **estritamente**:
     - Sensor infravermelho reflexivo **TCRT5000** (`VCC = 3,3 V` — **NUNCA alimentar em `5 V`**).
     - **Potenciômetro rotativo** (`Terminal 1 = 3,3 V`, `Terminal 2 = GND` — **NUNCA alimentar em `5 V`**).
3. **Barramento de Terra Comum (*Common GND*)**:
   - **OBRIGATÓRIO**: Todos os componentes (ESP32, HC-SR04, LCD 2004A incluindo pino 5 `RW` e pino 16 `K`, TCRT5000, potenciômetro e ramo inferior `R2` do divisor de tensão) devem compartilhar exatamente o mesmo barramento físico de referência de terra (`GND`).
   - A ausência de um terra comum gera potenciais flutuantes, ruídos severos de medição ultrassônica e risco crítico de condução reversa de `5 V` para os pinos do microcontrolador.

### 1.2 Nota de Reconciliação Canônica de Pinagem (`GPIO34` vs `GPIO32`)

> [!IMPORTANT]
> **RECONCILIAÇÃO OFICIAL DO CICLO 5 (`HC-SR04 ECHO = GPIO34`):**
> - No Ciclo 3 ([pinout_config.h](file:///c:/Users/joaoh/Downloads/ChickenLittle/firmware/main/pinout_config.h), linha 35), `PIN_HCSR04_ECHO` foi configurado em **`GPIO34`**. No resumo textual do Ciclo 4 houve uma menção divergente a `GPIO32`.
> - Após auditoria completa de periféricos no Ciclo 5, **`GPIO34` fica estabelecido como o único pino canônico para `HC-SR04 ECHO`** (`MOTIONPET_PINOUT_STATUS = "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"`), pelos seguintes motivos de engenharia e segurança:
>   1. É um pino **GPI *input-only*** de alta impedância (não possui driver de saída CMOS, tornando **fisicamente impossível** configurá-lo por erro de software como saída `3,3 V` disputando corrente contra o divisor resistivo do sensor).
>   2. Não possui qualquer função de *boot strapping*.
>   3. Não apresenta sobreposição com nenhum outro periférico do sistema: `TRIG` (`GPIO5`), `TCRT5000 DO` (`GPIO35`), `TCRT5000 AO` (`GPIO39`, opcional), `Potenciômetro` (`GPIO36` / `ADC1_CH0`), `LCD 2004A` (`RS=GPIO19`, `RW=GND fixo`, `E=GPIO18`, `D4=GPIO21`, `D5=GPIO22`, `D6=GPIO23`, `D7=GPIO27`) ou `UART0` (`GPIO1`/`GPIO3`).
> - **Impacto no Firmware:** Nenhuma migração de código C++ foi necessária no firmware, pois a implementação real já utilizava `GPIO34` desde o Ciclo 3.

---

## 2. Sensor Ultrassônico HC-SR04: Proteção Estrita do Pino `ECHO` (`<= 3,30 V`)

O HC-SR04 opera com `VCC = 5 V`:
- **Entrada `TRIG` (`GPIO5` $\rightarrow$ HC-SR04)**: Recebe diretamente o pulso de `3,3 V` do `GPIO5` do ESP32, valor plenamente compatível com o limiar lógico TTL do HC-SR04 ($V_{IH\text{ min}} = 2,0\text{ V}$).
- **Saída `ECHO` (HC-SR04 $\rightarrow$ Divisor $\rightarrow$ `GPIO34`)**: Emite um pulso digital com amplitude de **`5,0 V` TTL** (podendo chegar a **`5,25 V`** no limite superior da tolerância USB). **NUNCA conecte `ECHO` diretamente ao ESP32.**

```
+5V (USB) -------+-----------------+
                 |                 |
             HC-SR04              ESP32 DevKit
             +-------+            +----------+
             | VCC   |<--- 5V ----| VIN / 5V |
             | TRIG  |<--- 3.3V --| GPIO5    |
             | ECHO  |---+        |          |
             | GND   |   |        |          |
             +-------+   |        |          |
                 |       |        |          |
GND -------------+       |        | GND      |
                         |        +----------+
                         |
                         |   Divisor Canônico (Ciclo 5)
                         |       R1 = 2,2 kΩ
                         +------[=====]-------+-----> GPIO34 (GPI Input-only)
                                              |       V_out = 3,00 V @ 5,00 V
                                              |       V_max = 3,15 V @ 5,25 V
                                             [ ]      (ESTRITAMENTE <= 3,30 V!)
                                             [ ] R2 = 3,3 kΩ
                                              |
GND ------------------------------------------+
```

### 2.1 Limites Elétricos Inegociáveis e Equacionamento do Divisor Canônico

Para alimentação nominal $V_{DD} = 3,30\text{ V}$ no ESP32 (datasheet Espressif ESP-WROOM-32):
- Limiar mínimo garantido para reconhecimento de nível lógico ALTO:
  $$V_{IH\text{ min}} = 0,75 \cdot V_{DD} = 0,75 \cdot 3,30\text{ V} = 2,475\text{ V}$$
- **Teto máximo admissível no projeto MotionPet:** **$V_{out} \le 3,30\text{ V}$** sob qualquer condição de barramento USB (`4,75 V` a `5,25 V`).
- **Faixa operacional segura recomendada para nível ALTO no nó do divisor:** **`2,50 V` a `3,20 V`** (nunca excedendo `3,30 V`).
- **PROIBIÇÃO DE `3,50 V`:** Tensões como `3,33 V` ou `3,50 V` **NÃO são seguras**. Ultrapassar $V_{DD}$ (`3,30 V`) força condução direta pelos diodos internos de proteção ESD (*snapback / clamping*) para o trilho `3V3`, degradando o pad de entrada e arriscando *latch-up* destrutivo do silício.

A tensão entregue ao nó do `GPIO34` ($V_{out}$) em função da amplitude do pulso `ECHO` ($V_{ECHO}$) é dada por:

$$V_{out} = V_{ECHO} \cdot \frac{R_2}{R_1 + R_2}$$

Com o **par canônico preferencial do Ciclo 5** (**$R_1 = 2,2\text{ k}\Omega$** entre `ECHO` e o nó do `GPIO34`; **$R_2 = 3,3\text{ k}\Omega$** entre o nó do `GPIO34` e `GND`):

$$\text{Fator de Divisão} = \frac{3,3\text{ k}\Omega}{2,2\text{ k}\Omega + 3,3\text{ k}\Omega} = \frac{3,3}{5,5} = 0,600$$

- Em tensão nominal USB ($V_{ECHO} = 5,00\text{ V}$):
  $$V_{out} = 5,00\text{ V} \cdot 0,600 = 3,00\text{ V}$$
  *(Margem de segurança de `0,30 V` abaixo do teto de `3,30 V` e `0,525 V` acima de $V_{IH\text{ min}} = 2,475\text{ V}$).*
- Mesmo em sobretensão máxima da especificação USB ($V_{USB} = 5,25\text{ V}$):
  $$V_{out\text{ max}} = 5,25\text{ V} \cdot 0,600 = 3,15\text{ V}$$
  *(Permanece `0,15 V` abaixo do teto estrito de `3,30 V`!).*
- Mesmo em subtensão USB ($V_{USB} = 4,75\text{ V}$):
  $$V_{out\text{ min}} = 4,75\text{ V} \cdot 0,600 = 2,85\text{ V} > 2,475\text{ V}$$

### 2.2 Pares de Resistores Aprovados no Ciclo 5 vs Pares Descontinuados

| Classificação | $R_1$ (`ECHO` $\rightarrow$ Nó) | $R_2$ (Nó $\rightarrow$ `GND`) | Fator $R_2/(R_1+R_2)$ | $V_{out}$ @ $5,00\text{ V}$ | $V_{out\text{ max}}$ @ $5,25\text{ V}$ | Status no Ciclo 5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Canônico Preferencial** | **$2,2\text{ k}\Omega$** | **$3,3\text{ k}\Omega$** | **$0,600$** | **$3,00\text{ V}$** | **$3,15\text{ V}$** | **APROVADO (Padrão Oficial)** |
| **Alternativa Segura 1** | $4,7\text{ k}\Omega$ | $6,8\text{ k}\Omega$ | $0,591$ | **$2,96\text{ V}$** | **$3,10\text{ V}$** | **APROVADO** |
| **Alternativa Segura 2** | $2\times 1,0\text{ k}\Omega$ série ($2,0\text{ k}\Omega$) | $3\times 1,0\text{ k}\Omega$ série ($3,0\text{ k}\Omega$) | $0,600$ | **$3,00\text{ V}$** | **$3,15\text{ V}$** | **APROVADO (Kit só com `1 kΩ`)** |
| ~~Antigo Par 1:2~~ | ~~$1,0\text{ k}\Omega$ (ou $10\text{ k}\Omega$)~~ | ~~$2,0\text{ k}\Omega$ (ou $20\text{ k}\Omega$)~~ | ~~$0,667$~~ | ~~$3,33\text{ V}$~~ | ~~$3,50\text{ V}$~~ | **DESCONTINUADO / PROIBIDO (`> 3,30 V`)** |
| ~~Antigo Par 1,8k/3,3k~~ | ~~$1,8\text{ k}\Omega$~~ | ~~$3,3\text{ k}\Omega$~~ | ~~$0,647$~~ | ~~$3,24\text{ V}$~~ | ~~$3,40\text{ V}$~~ | **DESCONTINUADO / PROIBIDO (`> 3,30 V` @ `5,25 V`)** |

> [!WARNING]
> **POR QUE `1 kΩ / 2 kΩ` FOI DESCONTINUADO:**
> O divisor `R1 = 1 kΩ, R2 = 2 kΩ` citado em revisões iniciais possui fator `0,667`, produzindo **`3,33 V` já em `5,00 V` nominais** e atingindo **`3,50 V` quando a porta USB entrega `5,25 V`**, violando o teto máximo admissível de `3,30 V`. Caso sua bancada tenha apenas resistores avulsos de `1 kΩ`, monte obrigatoriamente a **Alternativa Segura 2**: **`2×1 kΩ` em série para `R1` (`2,0 kΩ`) e `3×1 kΩ` em série para `R2` (`3,0 kΩ`)**, que restaura o fator exato de `0,600` (`3,00 V` @ `5,00 V`).
>
> **Validação obrigatória antes de conectar ao `GPIO34`:** Meça os resistores fora do circuito, energize o divisor **sem o jumper do `GPIO34`** e valide a medição com a ferramenta CLI do Ciclo 5:
> ```powershell
> .\.venv\Scripts\python.exe -m terminal.bench divider --r1 2200 --r2 3300 --measured-v 3.00
> ```

---

## 3. Display LCD 2004A V1.1 (Modo Paralelo 4-bits)

O display LCD 2004A V1.1 utiliza o controlador padrão Hitachi HD44780 (ou equivalentes compatíveis KS0066U / SPLC780D). Ele opera com `VDD = 5 V` e `VSS = GND` para garantir contraste e velocidade de resposta óptica nas 4 linhas x 20 colunas.

### 3.1 Aterramento Permanente Obrigatório do Pino `RW` (Pino 5)

- O pino 5 (`RW` — *Read/Write*) define a direção do barramento de dados do LCD:
  - `LOW` (`0 V`): modo **Write** (recebe comandos/dados do ESP32).
  - `HIGH` (`5 V`): modo **Read** (o LCD injeta **5 V** nos pinos `D4..D7` para reportar *Busy Flag* / RAM).
- **REGRA INEGOCIÁVEL**: O pino 5 (`RW`) deve ser conectado **direta e permanentemente ao barramento `GND` (`0,0 Ω`)**.
- **Motivo de Segurança**: Com `RW` permanentemente em `GND`, os buffers de saída de `5 V` do LCD permanecem fisicamente desabilitados em alta impedância, eliminando qualquer risco de retorno de `5 V` para os GPIOs `GPIO21`, `GPIO22`, `GPIO23` e `GPIO27` do ESP32.

### 3.2 Compatibilidade de Níveis Lógicos (`ESP32 3,3 V` $\rightarrow$ `LCD 5 V`) e Contingência

- O ESP32 entrega nível lógico alto típico $V_{OH} \approx 3,1\text{ V}$ a $3,3\text{ V}$ nas linhas `RS` (`GPIO19`), `E` (`GPIO18`) e `D4..D7` (`GPIO21`, `GPIO22`, `GPIO23`, `GPIO27`).
- No controlador **Hitachi HD44780 genuíno**: $V_{IH\text{ min}} = 2,2\text{ V}$ para $V_{DD} = 5,0\text{ V}$, aceitando diretamente os sinais de `3,3 V` do ESP32.
- Em certos **clones CMOS de baixo custo**: a especificação exige $V_{IH\text{ min}} = 0,7 \cdot V_{DD} = 3,5\text{ V}$.
- **Plano de Contingência para Clones CMOS**:
  1. Caso os caracteres não inicializem ou surjam símbolos corrompidos mesmo com contraste `V0` e `RW=GND` corretos, insira um diodo retificador de silício (**`1N4148`** ou **`1N4007`**) em série na alimentação `VDD` (pino 2 do LCD): **ânodo no trilho `5 V`, cátodo no pino 2 (`VDD`) do LCD**.
  2. A queda direta de $\approx 0,7\text{ V}$ reduz o $V_{DD}$ efetivo do LCD para $\approx 4,3\text{ V}$, rebaixando o limiar $V_{IH\text{ min}}$ para $0,7 \times 4,3\text{ V} = 3,01\text{ V}$ e garantindo leitura estável dos sinais de `3,3 V` do ESP32.
  3. Alternativamente, pode-se empregar um buffer `74HCT245` / `74HCT08` alimentado em `5 V` ($V_{IH\text{ min}} = 2,0\text{ V}$).

### 3.3 Ajuste de Contraste (Pino `V0`) e Estratégia para o Potenciômetro Único

Como o kit possui **apenas 1 potenciômetro rotativo**, adota-se a alocação em duas etapas:

1. **Operação Normal / Produção (Padrão)**:
   - O potenciômetro único fica dedicado exclusivamente à **entrada analógica do usuário** (`GPIO36` / `ADC1_CH0`), alimentado estritamente entre **`3,3 V` (`3V3`) e `GND`**.
   - O pino 3 (`V0`) do LCD é polarizado por um **resistor fixo de `1,0 kΩ` a `2,2 kΩ` conectado entre `V0` e `GND`**, gerando a tensão típica de contraste ótimo ($0,4\text{ V}$ a $0,8\text{ V}$).
2. **Calibração Preliminar Opcional na Bancada**:
   - Caso necessário ajustar o contraste fino de um lote específico de LCD, utilize o potenciômetro provisoriamente em `V0`, meça o valor equivalente com o multímetro, substitua pelo resistor fixo correspondente (`1 kΩ..2,2 kΩ` para `GND`) e **reconecte o potenciômetro estritamente ao trilho de `3,3 V`** antes de ligá-lo ao `GPIO36`.

### 3.4 Proteção do Backlight LED (Pinos 15 e 16)

- Pino 15 (`A` / Ânodo): alimentação do LED de luz de fundo em `5 V`.
- Pino 16 (`K` / Cátodo): retorno ao barramento comum `GND`.
- **Inspeção Obrigatória**: Verifique na face traseira do PCB do LCD se existe resistor limitador SMD soldado em série com o pino 15 (usualmente serigrafado como `R8` ou `R9`, código `101` = $100\,\Omega$). Se a posição estiver vazia ou fechada com jumper `0 Ω`, **adicione obrigatoriamente um resistor externo de `100 Ω` a `220 Ω` (`1/4 W`) em série entre `5 V` e o pino 15 (`A`)**.

---

## 4. Sensor Infravermelho Reflexivo (`TCRT5000`) e Potenciômetro (`ADC1`)

### 4.1 Sensor `TCRT5000` — Alimentação Estrita em `3,3 V`

- **Cenário A — Módulo Breakout com Comparador LM393 (3 ou 4 pinos)**:
  - **REGRA INEGOCIÁVEL**: Alimente o pino `VCC` do módulo estritamente no barramento **`3,3 V` (`3V3`)** do ESP32, **NUNCA em `5 V`**.
  - `GND` conectado ao barramento comum `GND`.
  - `DO` (saída digital limitada a `0 V..3,3 V`) conectado diretamente ao **`GPIO35`** (GPI *input-only*). Em módulos LM393 padrão, reflexão próxima aciona nível baixo (`DEFAULT_IR_ACTIVE_LOW = true`).
  - `AO` (saída analógica opcional, `0 V..3,3 V`) pode ser conectada ao **`GPIO39`** (`VN` / `ADC1_CH3`), mantida desativada por padrão (`DEFAULT_IR_ANALOG_EN = false`).
- **Cenário B — Cápsula Óptica Discreta de 4 Terminais (sem PCB)**:
  - **LED Emissor IR (azul/transparente)**: Ânodo via resistor limitador de `180 Ω` ao trilho **`3,3 V`** ($I_F \approx 11\text{ mA}$); cátodo ao `GND`.
  - **Fototransistor Receptor (preto)**: Coletor com resistor de *pull-up* de `10 kΩ` para **`3,3 V`** e ligado ao **`GPIO35`**; emissor ao `GND`. **Nunca ligue o *pull-up* em `5 V`.**

### 4.2 Potenciômetro Rotativo — Alimentação Estrita em `3,3 V`

- **Terminal extremo 1**: conectado estritamente ao pino **`3V3` (`3,3 V`)** (**NUNCA em `5 V`!**).
- **Terminal extremo 2**: conectado ao barramento comum **`GND`**.
- **Cursor central**: conectado ao **`GPIO36`** (`VP` / `ADC1_CH0`), excursionando de forma segura entre `0,00 V` e `3,30 V` (`pot_norm` de `0.0` a `1.0`).

---

## 5. Restrições Rígidas de GPIOs do `ESP-WROOM-32`

```
                              ESP32 DevKit 30/38 pinos
                           +----------------------------+
                           | [USB]                      |
                  EN (RST) |                            | GPIO23 (LCD D6)
       (POT)  GPIO36 (VP)  | [ADC1_CH0 - GPI]           | GPIO22 (LCD D5)
    (IR AO*)  GPIO39 (VN)  | [ADC1_CH3 - GPI]           | GPIO1  (UART0 TX0)
   (ECHO<=3V3) GPIO34(GPI) | [Input-Only Canônico]      | GPIO3  (UART0 RX0)
     (IR DO)  GPIO35 (GPI) | [Input-Only]               | GPIO21 (LCD D4)
                   GPIO32  | [Livre]                    | GPIO19 (LCD RS)
                   GPIO33  | [Livre]                    | GPIO18 (LCD E)
                   GPIO25  | [Livre]                    | GPIO5  (HC-SR04 TRIG)
                   GPIO26  | [Livre]                    | GPIO17 [Livre]
   (LCD D7)        GPIO27  |                            | GPIO16 [Livre]
                   GPIO14  | [Livre]                    | GPIO4  [Livre]
                   GPIO12  | [MTDI - MANTER LIVRE!]     | GPIO0  (Boot - Livre)
                   GPIO13  | [Livre]                    | GPIO2  (Boot LED - Livre)
                      GND  | [Terra Comum]              | GPIO15 (MTDO - Livre)
                      VIN  | (5V USB: HC-SR04 + LCD)    | 3V3    (TCRT5000 + POT)
                           +----------------------------+
```

1. **Pinos Proibidos — Barramento SPI Flash Interno (`GPIO6` a `GPIO11`)**:
   - **TERMINANTEMENTE PROIBIDOS**. Conectados internamente à memória Flash SPI do módulo `ESP-WROOM-32`; qualquer conexão externa provoca *Guru Meditation Error / Cache disabled*.
2. **Pinos Somente-Entrada (*Input-Only* / GPIs: `GPIO34`, `GPIO35`, `GPIO36`, `GPIO39`)**:
   - Não possuem estágio de saída nem *pull-up*/*pull-down* internos. Ideais para entradas protegidas e canais analógicos: `GPIO34` (`ECHO` pós-divisor), `GPIO35` (`TCRT5000 DO`), `GPIO36` (`Potenciômetro ADC1_CH0`) e `GPIO39` (`TCRT5000 AO` opcional).
3. **Pinos de *Boot Strapping* (`GPIO12`, `GPIO0`, `GPIO2`, `GPIO15`)**:
   - **`GPIO12` (`MTDI` — RISCO CRÍTICO)**: Se puxado para nível ALTO (`3,3 V`) durante o boot, seleciona `1,8 V` para o regulador interno da Flash `VDD_SDIO`, causando *boot loop* (`flash read err, 1000`). **Mantenha `GPIO12` 100% desconectado.**
   - `GPIO0`, `GPIO2` e `GPIO15`: mantidos livres de cargas externas para não interferir na gravação serial ou inicialização da ROM.
4. **Isolamento da `UART0` (`GPIO1` e `GPIO3`)**:
   - Dedicados exclusivamente ao conversor USB-Serial da placa para o protocolo estruturado **JSON Lines v1** a `115200 baud`.
5. **Uso Exclusivo do Bloco `ADC1`**:
   - O `ADC2` sofre bloqueio de hardware quando o rádio Wi-Fi é ativado. Todos os canais analógicos do MotionPet residem exclusivamente no **`ADC1`** (`GPIO36` e `GPIO39`).

---

## 6. Tabela Canônica Única de Pinagem (Ciclo 5 — `CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION`)

Em total conformidade com [pinout_config.h](file:///c:/Users/joaoh/Downloads/ChickenLittle/firmware/main/pinout_config.h):

| Módulo Periférico | Pino do Periférico | Pino no ESP32 | Direção / Função | Nível Elétrico Seguro | Regra Crítica de Segurança |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **HC-SR04** | `VCC` | `VIN` / `5V` | Alimentação | `5,0 V` | Trilho `5 V` USB. |
| **HC-SR04** | `GND` | `GND` | Referência | `0,0 V` | Barramento comum de terra. |
| **HC-SR04** | `TRIG` | `GPIO5` | Saída ESP32 | `3,3 V` | Compatível com entrada TTL (`>= 2,0 V`). |
| **HC-SR04** | `ECHO` | **`GPIO34`** *(Canônico)* | Entrada GPI | **`<= 3,30 V`** (`3,00 V` nom.) | **OBRIGATÓRIO: Divisor `R1 = 2,2 kΩ` / `R2 = 3,3 kΩ`. `3,5 V` é PROIBIDO!** |
| **TCRT5000** | `VCC` | `3V3` | Alimentação | `3,3 V` | **Alimentar estritamente em `3,3 V` (NUNCA em `5 V`)**. |
| **TCRT5000** | `GND` | `GND` | Referência | `0,0 V` | Barramento comum de terra. |
| **TCRT5000** | `DO` | `GPIO35` | Entrada GPI | `0 V` / `3,3 V` | Entrada digital direta (`active-low` padrão LM393). |
| **TCRT5000** | `AO` *(Opcional)* | `GPIO39` (`VN`) | Entrada `ADC1_CH3` | `0 V` a `3,3 V` | Opcional (`DEFAULT_IR_ANALOG_EN = false`). |
| **Potenciômetro** | Terminal 1 | `3V3` | Alimentação | `3,3 V` | **Alimentar estritamente em `3,3 V` (NUNCA em `5 V`)**. |
| **Potenciômetro** | Terminal 2 | `GND` | Referência | `0,0 V` | Barramento comum de terra. |
| **Potenciômetro** | Cursor Central | `GPIO36` (`VP`) | Entrada `ADC1_CH0` | `0 V` a `3,3 V` | Leitura analógica normalizada (`pot_norm` `0.0..1.0`). |
| **LCD 2004A** | 1 (`VSS`) | `GND` | Referência | `0,0 V` | Barramento comum de terra. |
| **LCD 2004A** | 2 (`VDD`) | `VIN` / `5V` | Alimentação | `5,0 V` | Contingência clone CMOS: diodo `1N4148`/`1N4007` em série. |
| **LCD 2004A** | 3 (`V0`) | Resistor p/ `GND` | Contraste | `0,4 V` a `0,8 V` | Resistor fixo `1,0 kΩ` a `2,2 kΩ` para `GND` após calibração. |
| **LCD 2004A** | 4 (`RS`) | `GPIO19` | Saída ESP32 | `3,3 V` | Seleção de registrador (Comando/Dado). |
| **LCD 2004A** | 5 (`RW`) | **`GND`** | Controle Fixo | **`0,0 V` (`0,0 Ω`)** | **ATERRAMENTO PERMANENTE OBRIGATÓRIO (bloqueia retorno de `5 V`)**. |
| **LCD 2004A** | 6 (`E`) | `GPIO18` | Saída ESP32 | `3,3 V` | Pulso de habilitação (*Enable*). |
| **LCD 2004A** | 7..10 (`D0..D3`) | `NC` (Aberto) | Não usado | Flutuante | Desconectados no modo paralelo de 4 bits. |
| **LCD 2004A** | 11 (`D4`) | `GPIO21` | Saída ESP32 | `3,3 V` | Barramento de dados nibble superior (bit 4). |
| **LCD 2004A** | 12 (`D5`) | `GPIO22` | Saída ESP32 | `3,3 V` | Barramento de dados nibble superior (bit 5). |
| **LCD 2004A** | 13 (`D6`) | `GPIO23` | Saída ESP32 | `3,3 V` | Barramento de dados nibble superior (bit 6). |
| **LCD 2004A** | 14 (`D7`) | `GPIO27` | Saída ESP32 | `3,3 V` | Barramento de dados nibble superior (bit 7). |
| **LCD 2004A** | 15 (`A`) | `VIN` / `5V` | Backlight Ânodo | `5,0 V` | Via resistor `100–220 Ω` se a placa não possuir SMD `R8`/`R9`. |
| **LCD 2004A** | 16 (`K`) | `GND` | Backlight Cátodo | `0,0 V` | Barramento comum de terra. |
| **USB-Serial** | `TX0` / `RX0` | `GPIO1` / `GPIO3` | `UART0` | `3,3 V` interno | Exclusivo para telemetria JSON Lines v1 (`115200 baud`). |

---

## 7. Checklist Passo a Passo de Validação Elétrica com Multímetro

Execute rigorosamente antes e durante a energização incremental (use também `.\.venv\Scripts\python.exe -m terminal.bench checklist` e o guia rápido [cycle5_bench_checklist.md](file:///c:/Users/joaoh/Downloads/ChickenLittle/docs/cycle5_bench_checklist.md)):

- [ ] **Etapa 1: Inspeção Visual e Resistências (Circuito Totalmente Desenergizado — USB Desconectado)**
  1. Meça com o multímetro na escala de resistência os componentes do divisor do pino `ECHO`: confirme **`R1 ≈ 2,2 kΩ`** (entre `ECHO` e o nó central) e **`R2 ≈ 3,3 kΩ`** (entre o nó central e `GND`), ou um dos pares alternativos aprovados na Seção 2.2 (**rejeite `1 kΩ / 2 kΩ`**).
  2. Verifique continuidade direta (**`0,0 Ω`**) entre o pino 5 (`RW`) do LCD 2004A e o barramento comum `GND`.
  3. Confirme ausência total de curto-circuito entre `5V/VIN` e `GND` e entre `3V3` e `GND`.
  4. Confirme que `TCRT5000 VCC` e o terminal positivo do `Potenciômetro` vão **exclusivamente ao trilho `3V3`** (nunca ao `5V`).
  5. Inspecione visualmente que `GPIO6..GPIO11`, `GPIO12` e `GPIO1/GPIO3` estão 100% livres de fios na protoboard.

- [ ] **Etapa 2: Energização Inicial Isolada (Etapa A — ESP32 sem Sensores)**
  1. Conecte o cabo USB apenas ao ESP32 e meça as tensões DC em relação ao `GND`:
     - `5V / VIN`: entre `4,75 V` e `5,25 V`.
     - `3V3`: entre `3,25 V` e `3,35 V`.
  2. Valide a comunicação serial inicial com `.\.venv\Scripts\python.exe -m terminal.bench stage A --serial-port COMx`.

- [ ] **Etapa 3: Validação Prévia do Divisor do `HC-SR04` (Etapa B — ANTES de conectar ao `GPIO34`!)**
  1. Desconecte o USB. Instale o HC-SR04 e o divisor `2,2 kΩ / 3,3 kΩ`, **mantendo o jumper para o `GPIO34` desconectado**.
  2. Conecte o USB e meça a tensão de nível alto / pico no nó entre `R1` e `R2` (ou valide tensão estática/osciloscópio + cálculo assistido):
     ```powershell
     .\.venv\Scripts\python.exe -m terminal.bench divider --r1 2200 --r2 3300 --measured-v 3.00
     ```
  3. **CRITÉRIO DE PARADA IMEDIATA:** A tensão máxima no nó **DEVE ser `<= 3,30 V`** (faixa nominal esperada: **`2,85 V` a `3,15 V`**; alvo `3,00 V` @ `5,00 V`). Se qualquer medição indicar `> 3,30 V` (como `3,33 V`, `3,50 V` ou `5,0 V`), **PARE IMEDIATAMENTE, desconecte o USB e corrija o divisor antes de encostar no `GPIO34`!**
  4. Somente após aprovação (`<= 3,30 V`), desconecte o USB, ligue o nó ao `GPIO34`, reconecte o USB e execute `terminal.bench stage B` e `terminal.bench inspect`.

- [ ] **Etapa 4: Validação de `3,3 V` nos Periféricos Analógicos/Ópticos (Etapa C) e LCD 2004A (Etapa D)**
  1. Com TCRT5000 e potenciômetro instalados em `3V3` (desenergizar para montar!), confirme com o multímetro que o cursor central (`GPIO36`) excursiona suavemente de `0,00 V` a `3,30 V` e que `DO` (`GPIO35`) jamais excede `3,30 V`. Valide com `terminal.bench stage C`.
  2. Após instalar o LCD 2004A (desenergizar para montar, confirmando novamente `RW = 0,0 Ω` para `GND` e resistor de backlight `100–220 Ω` se necessário), energize, verifique o contraste em `V0` (`0,4 V..0,8 V`) e valide com `terminal.bench stage D`.
