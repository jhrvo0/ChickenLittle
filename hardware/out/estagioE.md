# Estagio E — Montagem completa

> **CAD paralelo histórico.** Para a montagem atual com LCD I²C, use [o guia final](../guia_montagem_final.html). D/E antigos não se aplicam ao backpack.

> Revisao final com multimetro e teste ponta a ponta.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `M3.K`, `M3.RW`, `M3.VSS`, `R3.B`, `R4.B`, `U1.GND@J2.14`, `U1.GND@J2.18`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. A serigrafia da placa fotografada mostra 4 pinos GND; sua continuidade interna e uma hipotese a verificar fisicamente.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `M3.VDD`, `R5.A`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 3.1 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.
- **LCD_V0** — dominio `ANALOG_LOW`, tensao nao medida: `M3.V0`, `R4.A`. V0 ligado a GND por R4; tensao e contraste reais dependem do modulo (C07).
- **LCD_A** — dominio `POWER_5V_LED`, nominal 5.0 V (max 5.25 V): `M3.A`, `R5.B`. Anodo do backlight (via R5).
- **LCD_RS** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.RS`, `U1.IO19`. GPIO19 -> RS.
- **LCD_E** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.E`, `U1.IO18`. GPIO18 -> E.
- **LCD_D4** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D4`, `U1.IO21`. GPIO21 -> D4.
- **LCD_D5** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D5`, `U1.IO22`. GPIO22 -> D5.
- **LCD_D6** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D6`, `U1.IO23`. GPIO23 -> D6.
- **LCD_D7** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D7`, `U1.IO27`. GPIO27 -> D7.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 3V3 | 19I | 3V3 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 15I | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO35 (GPIO35) | 14I | IR_DO | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO27 (GPIO27) | 9I | LCD_D7 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 6I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 2I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 1I | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 19B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO23 (GPIO23) | 18B | LCD_D6 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO22 (GPIO22) | 17B | LCD_D5 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO21 (GPIO21) | 14B | LCD_D4 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 13B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO19 (GPIO19) | 12B | LCD_RS | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO18 (GPIO18) | 11B | LCD_E | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO5 (GPIO5) | 10B | TRIG | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | VCC | 24W | 5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | TRIG | 10A | TRIG | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | ECHO | 22E | ECHO_5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | GND | 25X | GND | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | A | 22C | ECHO_5V | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | B | 26C | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> meio) | A | 26D | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> meio) | B | 29D | DIV_MID | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R3 | R3 divisor (meio -> trilho -) | A | 29A | DIV_MID | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R3 | R3 divisor (meio -> trilho -) | B | 30X | GND | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| M2 | TCRT5000 (modulo LM393) | VCC | 19J | 3V3 | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | GND | 6J | GND | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | DO | 14J | IR_DO | PIN_ORDER_UNCONFIRMED |
| M3 | LCD 2004A V1.1 | VSS | P2:12J | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | VDD | P2:13J | 5V | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | V0 | P2:14J | LCD_V0 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RS | P2:15J | LCD_RS | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RW | P2:16J | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | E | P2:17J | LCD_E | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D0 | P2:18J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D1 | P2:19J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D2 | P2:20J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D3 | P2:21J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D4 | P2:22J | LCD_D4 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D5 | P2:23J | LCD_D5 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D6 | P2:24J | LCD_D6 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D7 | P2:25J | LCD_D7 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | A | P2:26J | LCD_A | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | K | P2:27J | GND | PENDING_PHYSICAL_CONFIRMATION |
| R4 | R4 contraste (V0 -> GND) | A | P2:14F | LCD_V0 | ADJUST_ON_BENCH |
| R4 | R4 contraste (V0 -> GND) | B | P2:14E | GND | ADJUST_ON_BENCH |
| R5 | R5 backlight (5V -> A) | A | P2:26E | 5V | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |
| R5 | R5 backlight (5V -> A) | B | P2:26F | LCD_A | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 1J | 3W | 5V | 4,75-5,25 V | 5V da ESP32 (1J, junto da USB) -> trilho + (vermelho) de baixo | So o HC-SR04 e o LCD usam 5 V. NUNCA ligue o TCRT5000 no trilho +. |
| W2 | preto | 13A | 15X | GND | 0 V | GND da ESP32 -> trilho - (azul) de baixo |  |
| W3 | verde | 26E | 15J | ECHO_NODE | 0 / 2,83 V (pior caso 3,10 V) | No do divisor -> GPIO34 | Confira o divisor completo, o GND e a serigrafia IO34 antes de instalar; a tensao real nao foi medida. |
| W4 | vermelho | 30W | P2:3W | 5V | 4,75-5,25 V | Ponte 5 V: trilho + da P1 -> trilho + da P2 |  |
| W5 | preto | 29X | P2:3X | GND | 0 V | Ponte GND: trilho - da P1 -> trilho - da P2 |  |
| W6 | preto | P2:12F | P2:13X | GND | 0 V | VSS (pino 1) -> trilho - |  |
| W7 | vermelho | P2:13F | P2:15W | 5V | 4,75-5,25 V | VDD (pino 2) -> trilho + |  |
| W8 | preto | P2:16F | P2:17X | GND | 0 V | RW (pino 5) -> trilho - | OBRIGATORIO: RW = 0 Ω para GND antes de ligar. |
| W9 | preto | P2:27F | P2:29X | GND | 0 V | K (pino 16) -> trilho - |  |
| W10 | preto | P2:14A | P2:16X | GND | 0 V | Ponta de baixo do R4 -> trilho - |  |
| W11 | vermelho | P2:26A | P2:28W | 5V | 4,75-5,25 V | Ponta de baixo do R5 -> trilho + |  |
| W12 | azul | 12A | P2:15I | LCD_RS | 0 / 3,3 V | GPIO19 -> RS (pino 4) |  |
| W13 | verde | 11A | P2:17I | LCD_E | 0 / 3,3 V | GPIO18 -> E (pino 6) |  |
| W14 | branco | 14A | P2:22I | LCD_D4 | 0 / 3,3 V | GPIO21 -> D4 (pino 11) |  |
| W15 | marrom | 17A | P2:23I | LCD_D5 | 0 / 3,3 V | GPIO22 -> D5 (pino 12) |  |
| W16 | laranja | 18A | P2:24I | LCD_D6 | 0 / 3,3 V | GPIO23 -> D6 (pino 13) |  |
| W17 | roxo | 9J | P2:25G | LCD_D7 | 0 / 3,3 V | GPIO27 -> D7 (pino 14) |  |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 1I | 1 | I | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 1J | 1 | J | fio W1 (vermelho), ponta inicial |  |
| 2I | 2 | I | U1 ESP32 DevKit: pino GND [J2.18] | GND |
| 3W | 3 | W | fio W1 (vermelho), ponta final |  |
| 6I | 6 | I | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 6J | 6 | J | M2 TCRT5000 (modulo LM393): pino GND | GND |
| 9I | 9 | I | U1 ESP32 DevKit: pino IO27 (GPIO27) [J2.11] | LCD_D7 |
| 9J | 9 | J | fio W17 (roxo), ponta inicial |  |
| 10A | 10 | A | M1 HC-SR04: pino TRIG | TRIG |
| 10B | 10 | B | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 11A | 11 | A | fio W13 (verde), ponta inicial |  |
| 11B | 11 | B | U1 ESP32 DevKit: pino IO18 (GPIO18) [J3.9] | LCD_E |
| 12A | 12 | A | fio W12 (azul), ponta inicial |  |
| 12B | 12 | B | U1 ESP32 DevKit: pino IO19 (GPIO19) [J3.8] | LCD_RS |
| 13A | 13 | A | fio W2 (preto), ponta inicial |  |
| 13B | 13 | B | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 14A | 14 | A | fio W14 (branco), ponta inicial |  |
| 14B | 14 | B | U1 ESP32 DevKit: pino IO21 (GPIO21) [J3.6] | LCD_D4 |
| 14I | 14 | I | U1 ESP32 DevKit: pino IO35 (GPIO35) [J2.6] | IR_DO |
| 14J | 14 | J | M2 TCRT5000 (modulo LM393): pino DO | IR_DO |
| 15X | 15 | X | fio W2 (preto), ponta final |  |
| 15I | 15 | I | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 15J | 15 | J | fio W3 (verde), ponta final |  |
| 17A | 17 | A | fio W15 (marrom), ponta inicial |  |
| 17B | 17 | B | U1 ESP32 DevKit: pino IO22 (GPIO22) [J3.3] | LCD_D5 |
| 18A | 18 | A | fio W16 (laranja), ponta inicial |  |
| 18B | 18 | B | U1 ESP32 DevKit: pino IO23 (GPIO23) [J3.2] | LCD_D6 |
| 19B | 19 | B | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 19I | 19 | I | U1 ESP32 DevKit: pino 3V3 [J2.1] | 3V3 |
| 19J | 19 | J | M2 TCRT5000 (modulo LM393): pino VCC | 3V3 |
| 22C | 22 | C | R1 1 kΩ: perna A | ECHO_5V |
| 22E | 22 | E | M1 HC-SR04: pino ECHO | ECHO_5V |
| 24W | 24 | W | M1 HC-SR04: pino VCC | 5V |
| 25X | 25 | X | M1 HC-SR04: pino GND | GND |
| 26C | 26 | C | R1 1 kΩ: perna B | ECHO_NODE |
| 26D | 26 | D | R2 1 kΩ: perna A | ECHO_NODE |
| 26E | 26 | E | fio W3 (verde), ponta inicial |  |
| 29X | 29 | X | fio W5 (preto), ponta inicial |  |
| 29A | 29 | A | R3 300 Ω: perna A | DIV_MID |
| 29D | 29 | D | R2 1 kΩ: perna B | DIV_MID |
| 30W | 30 | W | fio W4 (vermelho), ponta inicial |  |
| 30X | 30 | X | R3 300 Ω: perna B | GND |
| P2:3W | 33 | W | fio W4 (vermelho), ponta final |  |
| P2:3X | 33 | X | fio W5 (preto), ponta final |  |
| P2:12F | 42 | F | fio W6 (preto), ponta inicial |  |
| P2:12J | 42 | J | M3 LCD 2004A V1.1: pino VSS | GND |
| P2:13X | 43 | X | fio W6 (preto), ponta final |  |
| P2:13F | 43 | F | fio W7 (vermelho), ponta inicial |  |
| P2:13J | 43 | J | M3 LCD 2004A V1.1: pino VDD | 5V |
| P2:14A | 44 | A | fio W10 (preto), ponta inicial |  |
| P2:14E | 44 | E | R4 1 kΩ: perna B | GND |
| P2:14F | 44 | F | R4 1 kΩ: perna A | LCD_V0 |
| P2:14J | 44 | J | M3 LCD 2004A V1.1: pino V0 | LCD_V0 |
| P2:15W | 45 | W | fio W7 (vermelho), ponta final |  |
| P2:15I | 45 | I | fio W12 (azul), ponta final |  |
| P2:15J | 45 | J | M3 LCD 2004A V1.1: pino RS | LCD_RS |
| P2:16X | 46 | X | fio W10 (preto), ponta final |  |
| P2:16F | 46 | F | fio W8 (preto), ponta inicial |  |
| P2:16J | 46 | J | M3 LCD 2004A V1.1: pino RW | GND |
| P2:17X | 47 | X | fio W8 (preto), ponta final |  |
| P2:17I | 47 | I | fio W13 (verde), ponta final |  |
| P2:17J | 47 | J | M3 LCD 2004A V1.1: pino E | LCD_E |
| P2:18J | 48 | J | M3 LCD 2004A V1.1: pino D0 |  |
| P2:19J | 49 | J | M3 LCD 2004A V1.1: pino D1 |  |
| P2:20J | 50 | J | M3 LCD 2004A V1.1: pino D2 |  |
| P2:21J | 51 | J | M3 LCD 2004A V1.1: pino D3 |  |
| P2:22I | 52 | I | fio W14 (branco), ponta final |  |
| P2:22J | 52 | J | M3 LCD 2004A V1.1: pino D4 | LCD_D4 |
| P2:23I | 53 | I | fio W15 (marrom), ponta final |  |
| P2:23J | 53 | J | M3 LCD 2004A V1.1: pino D5 | LCD_D5 |
| P2:24I | 54 | I | fio W16 (laranja), ponta final |  |
| P2:24J | 54 | J | M3 LCD 2004A V1.1: pino D6 | LCD_D6 |
| P2:25G | 55 | G | fio W17 (roxo), ponta final |  |
| P2:25J | 55 | J | M3 LCD 2004A V1.1: pino D7 | LCD_D7 |
| P2:26A | 56 | A | fio W11 (vermelho), ponta inicial |  |
| P2:26E | 56 | E | R5 300 Ω: perna A | 5V |
| P2:26F | 56 | F | R5 300 Ω: perna B | LCD_A |
| P2:26J | 56 | J | M3 LCD 2004A V1.1: pino A | LCD_A |
| P2:27F | 57 | F | fio W9 (preto), ponta inicial |  |
| P2:27J | 57 | J | M3 LCD 2004A V1.1: pino K | GND |
| P2:28W | 58 | W | fio W11 (vermelho), ponta final |  |
| P2:29X | 59 | X | fio W9 (preto), ponta final |  |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
