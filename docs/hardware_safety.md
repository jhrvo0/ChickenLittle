# Guia de Segurança e Validação de Hardware — MotionPet

> [!CAUTION]
> **AVISO DE SEGURANÇA CRÍTICO — HARDWARE NÃO VALIDADO FISICAMENTE**
>
> As atribuições de pinos, esquemas e níveis de tensão contidos neste documento são **propostas de engenharia** e **NÃO foram testadas fisicamente na bancada**.
> O microcontrolador ESP32 opera internamente em nível lógico de **3,3 V** e **NÃO é tolerante a 5 V**. A injeção direta de 5 V em qualquer GPIO causará a queima irreversível do pino ou de todo o microcontrolador.
> **NÃO energize o circuito** antes de executar o *Checklist de Inspeção e Validação com Multímetro* (Seção 7).

---

## 1. Topologia de Alimentação e Terra Comum (*Common GND*)

O sistema é alimentado pela porta USB (5 V) do ESP32 DevKit. Os trilhos de alimentação na protoboard devem ser organizados de forma estrita:

1. **Trilho 5 V (VBUS/VIN)**:
   - Fornecido pelo pino `5V` (ou `VIN` / `VBUS`) do DevKit (alimentação direta do cabo USB).
   - Alimenta:
     - Sensor ultrassônico HC-SR04 (`VCC` requer 5 V para operação confiável do transdutor piezelétrico).
     - Display LCD 2004A (`VDD` / pino 2 requer 5 V).
2. **Trilho 3,3 V (V33)**:
   - Fornecido pelo pino `3V3` do regulador linear LDO integrado à placa do ESP32.
   - Alimenta:
     - Sensor infravermelho TCRT5000 (se for módulo com comparador LM393).
     - Potenciômetro rotativo (quando usado como entrada analógica do ADC1).
3. **Barramento de Terra Comum (*Common GND*)**:
   - **OBRIGATÓRIO**: Todos os componentes (ESP32, HC-SR04, LCD 2004A, TCRT5000, divisores de tensão e potenciômetro) devem compartilhar exatamente o mesmo barramento de referência de terra (`GND`).
   - A ausência de um terra comum gera tensões flutuantes, ruídos severos de medição ultrassônica e risco de condução de retorno por vias inesperadas.

---

## 2. Sensor Ultrassônico HC-SR04: Proteção do Pino ECHO

O HC-SR04 exige alimentação de 5 V para que seus emissores ultrassônicos atinjam a potência adequada. Consequentemente, o sinal retornado pelo pino **ECHO** é um pulso digital com amplitude de **5 V (nível TTL)**.

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
                         |     Divisor de Tensão
                         |       R1 = 1 kΩ (ou 10 kΩ)
                         +------[=====]-------+-----> GPIO34 (Input-only)
                                              |
                                              |
                                             [ ] R2 = 2 kΩ (ou 20 kΩ)
                                             [ ]
                                              |
GND ------------------------------------------+
```

### 2.1 Equacionamento do Divisor Resistivo

A tensão entregue ao pino de entrada do ESP32 ($V_{out}$) em função da tensão emitida pelo HC-SR04 ($V_{in} \approx 5,0\text{ V}$) é calculada por:

$$V_{out} = V_{in} \cdot \frac{R_2}{R_1 + R_2}$$

Para obter uma tensão segura de aproximadamente $3,3\text{ V}$:

$$\frac{R_2}{R_1 + R_2} \approx \frac{3,3}{5,0} = 0,66$$

### 2.2 Pares Recomendados de Resistores

| Par | $R_1$ (ECHO $\rightarrow$ Nó) | $R_2$ (Nó $\rightarrow$ GND) | Razão ($R_2 / (R_1+R_2)$) | $V_{out}$ Teórico ($V_{in}=5,0\text{ V}$) | $V_{out}$ Máximo ($V_{in}=5,25\text{ V}$) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | $1,0\text{ k}\Omega$ | $2,0\text{ k}\Omega$ (ou $2\times 1\text{k}\Omega$ série) | $0,667$ | **$3,33\text{ V}$** | **$3,50\text{ V}$** |
| **B** | $1,8\text{ k}\Omega$ | $3,3\text{ k}\Omega$ | $0,647$ | **$3,24\text{ V}$** | **$3,40\text{ V}$** |
| **C** | $10\text{ k}\Omega$ | $20\text{ k}\Omega$ (ou $2\times 10\text{k}\Omega$ série) | $0,667$ | **$3,33\text{ V}$** | **$3,50\text{ V}$** |

> [!WARNING]
> Nunca conecte o pino `ECHO` diretamente a um pino do ESP32. Utilize sempre o divisor de tensão.
> Verifique os valores reais das resistências com o multímetro na escala de resistência antes da soldagem/inserção na protoboard.

---

## 3. Display LCD 2004A V1.1 (Modo Paralelo 4-bits)

O display LCD 2004A é baseado no controlador padrão Hitachi HD44780 (ou variantes compatíveis como KS0066U, SPLC780D). Ele é alimentado em 5 V para obter contraste e tempo de resposta aceitáveis.

### 3.1 Aterramento Obrigatório do Pino RW (Pino 5)

- O LCD possui o pino `RW` (Read/Write):
  - Em nível lógico LOW (`0 V`), o display está no modo **Write** (Escrita).
  - Em nível lógico HIGH (`5 V`), o display está no modo **Read** (Leitura de Busy Flag / RAM).
- **REGRA INEGOCIÁVEL**: O pino 5 (`RW`) deve ser conectado **direta e permanentemente ao GND da protoboard**.
- **Motivo de Segurança**: Se o pino `RW` fosse controlado por um GPIO ou deixado flutuando, o LCD poderia entrar em modo de leitura e colocar **5 V** nas linhas de dados (`D4`..`D7`), destruindo os pinos do ESP32 configurados como saída. Com `RW` aterrado, o LCD opera exclusivamente como receptor (somente-escrita), eliminando esse risco elétrico.

### 3.2 Compatibilidade de Níveis Lógicos (ESP32 $\rightarrow$ LCD)

- O ESP32 emite nível alto típico de $V_{OH} \approx 3,0\text{ V}$ a $3,3\text{ V}$.
- No controlador original **Hitachi HD44780**:
  - $V_{IH\text{ min}} = 2,2\text{ V}$ quando alimentado em $5\text{ V}$.
  - Como $3,0\text{ V} \ge 2,2\text{ V}$, o nível lógico alto do ESP32 é reconhecido sem necessidade de level shifters.
- Em certos **clones CMOS de baixo custo**:
  - A especificação pode exigir $V_{IH\text{ min}} = 0,7 \cdot V_{DD} = 3,5\text{ V}$.
  - Caso os caracteres não apareçam ou surjam caracteres corrompidos mesmo com o contraste ajustado, aplique o **Plano de Contingência**:
    1. Inserir um diodo de silício de uso geral (ex: 1N4148 ou 1N4007) em série no pino de alimentação $V_{DD}$ do LCD (ânodo no 5 V, cátodo no pino 2 do LCD). A queda de tensão direta de $\approx 0,7\text{ V}$ reduz a alimentação do display para $\approx 4,3\text{ V}$, abaixando o limiar $V_{IH}$ para $0,7 \times 4,3 = 3,01\text{ V}$, dentro da faixa de saída do ESP32.
    2. Alternativamente, utilizar um buffer CMOS com entradas tolerantes a 3.3V (ex: 74HCT08 ou 74HCT245 alimentado em 5V).

### 3.3 Ajuste de Contraste (Pino V0) e Alocação do Potenciômetro

O projeto possui **apenas 1 potenciômetro rotativo**. Ele pode ser utilizado de duas maneiras:

1. **Estratégia A (Recomendada para Produção / Modos de Jogo)**:
   - O único potenciômetro rotativo é reservado para **entrada analógica do usuário** (modulação de som no *Air Music*, mira/potência no *Pet Launch*), ligado aos trilhos de 3,3 V e GND, com o terminal central em um pino de ADC1 (`GPIO36` / VP).
   - O pino `V0` do LCD é polarizado por um **divisor fixo de resistores** ou por um resistor para o GND:
     - Na maioria dos módulos LCD 2004A, a tensão de contraste ideal $V_0$ fica entre $0,4\text{ V}$ e $0,8\text{ V}$.
     - Um resistor fixo de $1\text{ k}\Omega$ a $2,2\text{ k}\Omega$ entre o pino `V0` e o `GND` costuma fornecer contraste excelente e nítido.
2. **Estratégia B (Calibração Inicial na Bancada)**:
   - Conectar o potenciômetro temporariamente entre 5 V, `V0` e GND para identificar visualmente a posição de contraste ótimo.
   - Medir a tensão resultante com multímetro no pino central.
   - Substituir o potenciômetro por resistores fixos equivalentes e liberar o potenciômetro para o ADC1.

### 3.4 Proteção do Backlight (Pinos 15 e 16)

- Pino 15 (`A` / Ânodo): alimentação dos LEDs de luz de fundo.
- Pino 16 (`K` / Cátodo): terra dos LEDs de luz de fundo (conectar ao GND).
- **Atenção**: Inspecione a parte traseira da placa do LCD. Se não houver resistor limitador SMD soldado na trilha do pino 15 (frequentemente identificado como `R8` de $100\,\Omega$ ou similar), **não conecte o pino 15 diretamente ao 5 V**. Adicione um resistor em série de $100\,\Omega$ a $220\,\Omega$ (1/4 W) para evitar queima do backlight.

---

## 4. Sensor Infravermelho Reflexivo (TCRT5000)

O sensor TCRT5000 pode ser encontrado em duas configurações físicas distintas:

### 4.1 Cenário A: Módulo Breakout com Comparador LM393 (Mais Comum)
- A placa possui 3 ou 4 pinos (`VCC`, `GND`, `DO` - Saída Digital, `AO` - Saída Analógica opcional).
- **REGRA**: Alimente o pino `VCC` do módulo com **3,3 V** (pino 3V3 do ESP32), **NÃO COM 5 V**.
- Ao alimentar com 3,3 V, o sinal da saída digital `DO` variará de $0\text{ V}$ a $3,3\text{ V}$, podendo ser ligado diretamente a um GPIO de entrada do ESP32 (`GPIO35`) sem qualquer risco elétrico.

### 4.2 Cenário B: Componente Discreto (Cápsula de 4 Terminais Solta)
Caso o kit contenha apenas a cápsula óptica de 4 pinos (sem placa de suporte):
- **LED Emissor (Azul/Transparente)**:
  - Ânodo em série com resistor limitador de $180\,\Omega$ ligado ao trilho 3,3 V (corrente $\approx 10\text{ mA}$).
  - Cátodo ligado ao GND.
- **Fototransistor Receptor (Escuro/Preto)**:
  - Coletor ligado a um resistor de *pull-up* de $10\text{ k}\Omega$ conectado ao trilho 3,3 V e ao pino do ESP32 (`GPIO35`).
  - Emissor ligado ao GND.
  - **Aviso**: Nunca conecte o coletor a 5 V se for ligado diretamente ao ESP32.

---

## 5. Restrições Rígidas de GPIOs do ESP-WROOM-32

Para garantir inicialização estável, gravação de firmware sem falhas e integridade de memória, as seguintes regras físicas devem ser observadas:

```
                              ESP32 DevKit 30/38 pinos
                           +----------------------------+
                           | [USB-C]                    |
                  EN (RST) |                            | GPIO23 (VSPI MOSI)
              GPIO36 (VP)  | [ADC1_0]                   | GPIO22 (I2C SCL)
              GPIO39 (VN)  | [ADC1_3]                   | GPIO1 (TX0)
             GPIO34 (GPI)  | [ADC1_6]                   | GPIO3 (RX0)
             GPIO35 (GPI)  | [ADC1_7]                   | GPIO21 (I2C SDA)
                   GPIO32  | [ADC1_4]                   | GPIO19 (VSPI MISO)
                   GPIO33  | [ADC1_5]                   | GPIO18 (VSPI SCK)
                   GPIO25  | [DAC1]                     | GPIO5  (Strapping)
                   GPIO26  | [DAC2]                     | GPIO17
                   GPIO27  |                            | GPIO16
                   GPIO14  |                            | GPIO4
                   GPIO12  | [MTDI - PERIGO STRAP!]     | GPIO0  (Bootloader)
                   GPIO13  |                            | GPIO2  (Boot LED)
                      GND  |                            | GPIO15 (MTDO)
                      VIN  | (5V USB)                   | 3V3    (LDO 3.3V)
                           +----------------------------+
```

### 5.1 Pinos Proibidos — Barramento Flash SPI (`GPIO6` a `GPIO11`)
- Pinos: `GPIO6`, `GPIO7`, `GPIO8`, `GPIO9`, `GPIO10`, `GPIO11`.
- **Status**: **TERMINANTEMENTE PROIBIDOS**.
- Estão conectados internamente ao chip de memória flash SPI integrado ao módulo ESP-WROOM-32. Qualquer uso externo causará falha imediata na execução do código (*Guru Meditation Error / Cache disabled*).

### 5.2 Pinos Somente-Entrada (*Input Only* / GPIs)
- Pinos: `GPIO34`, `GPIO35`, `GPIO36` (VP), `GPIO39` (VN).
- Características:
  - Não possuem transistores de saída (não podem operar como `OUTPUT`).
  - Não possuem resistores internos configuráveis de *pull-up* ou *pull-down*.
- **Uso Ideal**: Excelentes para sensores digitais com saída ativa e leituras analógicas (ADC1):
  - `GPIO34`: Entrada do sinal `ECHO` protegido do HC-SR04.
  - `GPIO35`: Entrada digital do sensor infravermelho TCRT5000.
  - `GPIO36` (VP): Entrada analógica do potenciômetro (ADC1 Canal 0).

### 5.3 Pinos de Boot e Strapping (*Cuidado Especial com GPIO12*)
- `GPIO0`: Se estiver em nível LOW durante a reinicialização, o chip entra em modo de gravação via ROM bootloader. Deve permanecer aberto ou em nível HIGH em operação normal.
- `GPIO2`: Deve estar em nível LOW ou desconectado durante a inicialização para permitir boot da flash.
- `GPIO12` (**MTDI — RISCO CRÍTICO**):
  - Este pino atua como seletor da tensão de alimentação da memória flash interna no instante de boot.
  - Se for puxado para nível HIGH (3,3 V) durante o boot por um pull-up externo ou componente periférico, o ESP32 configurará o regulador interno da flash para **1,8 V** em vez de **3,3 V**.
  - **Consequência**: A flash não conseguirá ser lida e o ESP32 entrará em loop contínuo de reset (*boot loop*).
  - **Diretriz**: Não utilizar `GPIO12` para periféricos que possam forçar nível alto na energização.
- `GPIO15` (MTDO): Controla as mensagens de depuração da ROM no boot; deve ser mantido estável.

### 5.4 Prioridade de ADC: Utilização Exclusiva do ADC1
- O ESP32 possui dois blocos de conversores analógico-digitais: ADC1 (`GPIO32` a `GPIO39`) e ADC2 (`GPIO0`, `2`, `4`, `12`..`15`, `25`..`27`).
- **Problema Conhecido**: O periférico ADC2 compartilha recursos com o driver de rádio Wi-Fi. Caso o Wi-Fi seja iniciado no futuro (ex: telemetria sem fio), qualquer leitura no ADC2 falhará ou retornará leituras espúrias.
- **Diretriz**: Todos os sinais analógicos do projeto (potenciômetro) devem ser mapeados exclusivamente nos pinos do **ADC1**.

---

## 6. Proposta de Pinout Candidato (Ciclo 1 / Hardware Provisório)

A tabela abaixo consolida a alocação recomendada de GPIOs, respeitando rigorosamente todas as restrições elétricas e de strapping descritas:

| Módulo Periférico | Pino do Periférico | Pino no ESP32 | Direção / Função | Observação Elétrica de Segurança |
| :--- | :--- | :--- | :---: | :--- |
| **HC-SR04** | `VCC` | Pino `VIN` / `5V` | Alimentação | Trilho de 5 V (USB). |
| **HC-SR04** | `GND` | Pino `GND` | Referência | Barramento comum de terra. |
| **HC-SR04** | `TRIG` | `GPIO5` | Saída ESP32 | Saída digital 3,3 V (compatível com entrada TTL do HC-SR04). |
| **HC-SR04** | `ECHO` | `GPIO34` | Entrada ESP32 | **OBRIGATÓRIO: Passar por divisor $1\text{ k}\Omega / 2\text{ k}\Omega$**. |
| **TCRT5000** | `VCC` | Pino `3V3` | Alimentação | Alimentar em 3,3 V para manter `DO` em 3,3 V seguro. |
| **TCRT5000** | `GND` | Pino `GND` | Referência | Barramento comum de terra. |
| **TCRT5000** | `DO` | `GPIO35` | Entrada ESP32 | Sinal digital de presença (0 V ou 3,3 V). |
| **Potenciômetro** | Terminal 1 | Pino `3V3` | Alimentação | Conectar em 3,3 V (NUNCA em 5 V!). |
| **Potenciômetro** | Terminal 2 | Pino `GND` | Referência | Barramento comum de terra. |
| **Potenciômetro** | Cursor Central | `GPIO36` (VP) | Entrada ADC1 | Faixa analógica de 0 a 3,3 V lida via `ADC1_CHANNEL_0`. |
| **LCD 2004A** | 1 (`VSS`) | Pino `GND` | Referência | Barramento comum de terra. |
| **LCD 2004A** | 2 (`VDD`) | Pino `VIN` / `5V` | Alimentação | Trilho de 5 V (USB). |
| **LCD 2004A** | 3 (`V0`) | Divisor / GND | Contraste | Resistor fixo $\sim 1\text{ k}\Omega$ para GND (ou potenciômetro de bancada). |
| **LCD 2004A** | 4 (`RS`) | `GPIO19` | Saída ESP32 | Saída digital 3,3 V (nível alto aceito pelo HD44780). |
| **LCD 2004A** | 5 (`RW`) | Pino `GND` | Controle | **CONECTAR DIRETAMENTE AO GND (Modo somente-escrita)**. |
| **LCD 2004A** | 6 (`E`) | `GPIO18` | Saída ESP32 | Saída digital de clock/habilitação. |
| **LCD 2004A** | 11 (`D4`) | `GPIO21` | Saída ESP32 | Linha de dados de 4 bits. |
| **LCD 2004A** | 12 (`D5`) | `GPIO22` | Saída ESP32 | Linha de dados de 4 bits. |
| **LCD 2004A** | 13 (`D6`) | `GPIO23` | Saída ESP32 | Linha de dados de 4 bits. |
| **LCD 2004A** | 14 (`D7`) | `GPIO27` | Saída ESP32 | Linha de dados de 4 bits. |
| **LCD 2004A** | 15 (`A`) | Pino `VIN` / `5V` | Backlight Anode | Em série com resistor de $100\,\Omega$ se não houver resistor SMD. |
| **LCD 2004A** | 16 (`K`) | Pino `GND` | Backlight Cathode| Barramento comum de terra. |

---

## 7. Checklist Passo-a-Passo de Validação Física de Bancada

Antes de conectar o cabo USB do computador ao ESP32, execute rigorosamente a seguinte rotina de testes:

- [ ] **Etapa 1: Inspeção Visual e Resistências (Circuito Desligado)**
  1. Meça com o multímetro (escala de resistência) o divisor de tensão do pino `ECHO`: confirme que a resistência do ponto `ECHO` para a junção central é $\approx 1\text{ k}\Omega$ e da junção para o `GND` é $\approx 2\text{ k}\Omega$.
  2. Verifique se o pino 5 (`RW`) do LCD está com continuidade sonora ($0\,\Omega$) para o barramento `GND`.
  3. Verifique se os pinos de alimentação 5 V e 3,3 V **não estão em curto-circuito com o GND** (resistência acima de centenas de ohms ou teste de continuidade sem bip).
  4. Inspecione se os pinos `GPIO6` a `GPIO11` estão completamente livres e sem nenhum jumper conectado.
  5. Verifique se o pino `GPIO12` está livre e sem resistores puxando para nível alto.

- [ ] **Etapa 2: Energização Inicial Isolada (Sem os Sensores Conectados)**
  1. Conecte o cabo USB ao ESP32 com o circuito na protoboard, mas mantendo o HC-SR04 desconectado de seu soquete.
  2. Meça a tensão com o multímetro nos pinos de alimentação:
     - Entre pino `5V/VIN` e `GND`: deve indicar entre $4,75\text{ V}$ e $5,25\text{ V}$.
     - Entre pino `3V3` e `GND`: deve indicar entre $3,25\text{ V}$ e $3,35\text{ V}$.
  3. Meça a tensão nos terminais do potenciômetro: confirme que os extremos estão em 3,3 V e 0 V, e que o cursor central varia suavemente entre 0 V e 3,3 V.

- [ ] **Etapa 3: Validação do Divisor de Tensão do HC-SR04**
  1. Desconecte o USB. Encaixe o HC-SR04 na protoboard.
  2. Desconecte temporariamente o jumper que vai da saída do divisor para o `GPIO34` do ESP32.
  3. Conecte o USB e acione um trigger no sensor.
  4. Meça com o multímetro ou osciloscópio a tensão de pico no nó entre $R_1$ e $R_2$: **confirme que o valor nunca ultrapassa 3,5 V**.
  5. Após validar que a tensão é estritamente segura para 3,3 V, reconecte o pino ao `GPIO34`.

- [ ] **Etapa 4: Validação do Display LCD**
  1. Ao energizar, a primeira e terceira linhas do LCD podem exibir blocos pretos (estado pré-inicialização do HD44780).
  2. Ajuste o resistor ou potenciômetro de teste em `V0` até que os blocos fiquem levemente visíveis sem saturação total.
  3. Após carregar o firmware de teste, os caracteres devem ser desenhados de forma limpa.
