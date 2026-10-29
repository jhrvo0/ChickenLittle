# Estagio D — LCD 2004A

> Display 20x4 na 2a protoboard (P2), modo 4 bits, RW no GND, sinais de 3,3 V.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `M3.K`, `M3.RW`, `M3.VSS`, `P1.END_B`, `R3.B`, `R4.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `M3.VDD`, `R5.A`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `P1.END_A`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.
- **POT_WIPER** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `P1.WIPER`, `U1.VP`. Cursor do potenciometro.
- **LCD_V0** — dominio `ANALOG_LOW`, nominal 0.4 V (max 0.8 V): `M3.V0`, `R4.A`. Contraste do LCD (ajuste na bancada: C07).
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
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 3V3 | 1B | 3V3 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | VP (GPIO36) | 3B | POT_WIPER | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 5B | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO35 (GPIO35) | 6B | IR_DO | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO27 (GPIO27) | 11B | LCD_D7 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 14B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 19B | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 1I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO23 (GPIO23) | 2I | LCD_D6 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO22 (GPIO22) | 3I | LCD_D5 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO21 (GPIO21) | 6I | LCD_D4 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 7I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO19 (GPIO19) | 8I | LCD_RS | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO18 (GPIO18) | 9I | LCD_E | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO5 (GPIO5) | 10I | TRIG | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | VCC | 21J | 5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | TRIG | 22J | TRIG | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | ECHO | 23J | ECHO_5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | GND | 24J | GND | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | A | 23H | ECHO_5V | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | B | 27H | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> meio) | A | 27F | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> meio) | B | 30F | DIV_MID | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R3 | R3 divisor (meio -> GND) | A | 30G | DIV_MID | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R3 | R3 divisor (meio -> GND) | B | 24G | GND | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| M2 | TCRT5000 (modulo LM393) | VCC | 21A | 3V3 | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | GND | 22A | GND | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | DO | 23A | IR_DO | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | AO | 24A | (sem conexao: NC) | PIN_ORDER_UNCONFIRMED |
| P1 | Potenciometro rotativo | END_A | 28A | 3V3 | PENDING_PHYSICAL_CONFIRMATION |
| P1 | Potenciometro rotativo | WIPER | 29A | POT_WIPER | PENDING_PHYSICAL_CONFIRMATION |
| P1 | Potenciometro rotativo | END_B | 30A | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | VSS | P2:12A | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | VDD | P2:13A | 5V | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | V0 | P2:14A | LCD_V0 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RS | P2:15A | LCD_RS | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RW | P2:16A | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | E | P2:17A | LCD_E | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D0 | P2:18A | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D1 | P2:19A | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D2 | P2:20A | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D3 | P2:21A | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D4 | P2:22A | LCD_D4 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D5 | P2:23A | LCD_D5 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D6 | P2:24A | LCD_D6 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D7 | P2:25A | LCD_D7 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | A | P2:26A | LCD_A | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | K | P2:27A | GND | PENDING_PHYSICAL_CONFIRMATION |
| R4 | R4 contraste (V0 -> GND) | A | P2:14B | LCD_V0 | ADJUST_ON_BENCH |
| R4 | R4 contraste (V0 -> GND) | B | P2:10B | GND | ADJUST_ON_BENCH |
| R5 | R5 backlight (5V -> A) | A | P2:29B | 5V | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |
| R5 | R5 backlight (5V -> A) | B | P2:26B | LCD_A | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 19A | 21H | 5V | 4,75-5,25 V | 5V -> VCC do HC-SR04 | Somente HC-SR04 e LCD usam 5 V. NUNCA levar este fio ao TCRT5000 ou ao potenciometro. |
| W2 | preto | 7J | 24I | GND | 0 V | GND -> GND do HC-SR04 | Sem terra comum o ECHO flutua e pode injetar 5 V no GPIO. |
| W3 | amarelo | 10J | 22I | TRIG | 0 / 3,3 V | GPIO5 -> TRIG | GPIO5 e pino de strapping; usa-lo como saida e aceitavel. |
| W4 | verde | 27I | 5A | ECHO_NODE | 0 / 2,83 V (2,97 V max. nominal; pior caso 3,10 V) | No do divisor -> GPIO34 | NAO instalar antes de medir o no <= 3,30 V (ponto de parada da etapa B). |
| W5 | laranja | 1A | 21D | 3V3 | 3,25-3,35 V | 3V3 -> VCC do TCRT5000 | NUNCA ligar o TCRT5000 em 5 V. |
| W6 | laranja | 21E | 28E | 3V3 | 3,25-3,35 V | 3V3 -> extremo do potenciometro | NUNCA ligar o potenciometro em 5 V. |
| W7 | preto | 22C | 24F | GND | 0 V | GND do TCRT5000 -> GND do sensor |  |
| W8 | preto | 30D | 24H | GND | 0 V | GND do potenciometro -> GND do sensor |  |
| W9 | azul | 23B | 6A | IR_DO | 0 / 3,3 V | DO -> GPIO35 |  |
| W10 | roxo | 29B | 3A | POT_WIPER | 0-3,3 V | Cursor -> GPIO36 (VP) |  |
| W11 | preto | 30E | P2:12E | GND | 0 V | GND -> VSS do LCD |  |
| W12 | preto | P2:12C | P2:16C | GND | 0 V | VSS -> RW (pino 5) | OBRIGATORIO: RW = 0 Ω para GND antes de ligar. |
| W13 | preto | P2:16D | P2:27D | GND | 0 V | RW -> K (pino 16) |  |
| W14 | preto | P2:12D | P2:10D | GND | 0 V | VSS -> coluna 10 (ponta de R4) |  |
| W15 | vermelho | 21F | P2:13E | 5V | 4,75-5,25 V | 5V -> VDD (pino 2) |  |
| W16 | vermelho | 21I | P2:29E | 5V | 4,75-5,25 V | 5V -> R5 (backlight) |  |
| W17 | azul | 8J | P2:15E | LCD_RS | 0 / 3,3 V | GPIO19 -> RS (pino 4) |  |
| W18 | verde | 9J | P2:17E | LCD_E | 0 / 3,3 V | GPIO18 -> E (pino 6) |  |
| W19 | branco | 6J | P2:22E | LCD_D4 | 0 / 3,3 V | GPIO21 -> D4 (pino 11) |  |
| W20 | marrom | 3J | P2:23E | LCD_D5 | 0 / 3,3 V | GPIO22 -> D5 (pino 12) |  |
| W21 | laranja | 2J | P2:24E | LCD_D6 | 0 / 3,3 V | GPIO23 -> D6 (pino 13) |  |
| W22 | roxo | 11A | P2:25E | LCD_D7 | 0 / 3,3 V | GPIO27 -> D7 (pino 14) |  |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 1A | 1 | A | fio W5 (laranja), ponta inicial |  |
| 1B | 1 | B | U1 ESP32 DevKit: pino 3V3 [J2.1] | 3V3 |
| 1I | 1 | I | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 2I | 2 | I | U1 ESP32 DevKit: pino IO23 (GPIO23) [J3.2] | LCD_D6 |
| 2J | 2 | J | fio W21 (laranja), ponta inicial |  |
| 3A | 3 | A | fio W10 (roxo), ponta final |  |
| 3B | 3 | B | U1 ESP32 DevKit: pino VP (GPIO36) [J2.3] | POT_WIPER |
| 3I | 3 | I | U1 ESP32 DevKit: pino IO22 (GPIO22) [J3.3] | LCD_D5 |
| 3J | 3 | J | fio W20 (marrom), ponta inicial |  |
| 5A | 5 | A | fio W4 (verde), ponta final |  |
| 5B | 5 | B | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 6A | 6 | A | fio W9 (azul), ponta final |  |
| 6B | 6 | B | U1 ESP32 DevKit: pino IO35 (GPIO35) [J2.6] | IR_DO |
| 6I | 6 | I | U1 ESP32 DevKit: pino IO21 (GPIO21) [J3.6] | LCD_D4 |
| 6J | 6 | J | fio W19 (branco), ponta inicial |  |
| 7I | 7 | I | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 7J | 7 | J | fio W2 (preto), ponta inicial |  |
| 8I | 8 | I | U1 ESP32 DevKit: pino IO19 (GPIO19) [J3.8] | LCD_RS |
| 8J | 8 | J | fio W17 (azul), ponta inicial |  |
| 9I | 9 | I | U1 ESP32 DevKit: pino IO18 (GPIO18) [J3.9] | LCD_E |
| 9J | 9 | J | fio W18 (verde), ponta inicial |  |
| 10I | 10 | I | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 10J | 10 | J | fio W3 (amarelo), ponta inicial |  |
| 11A | 11 | A | fio W22 (roxo), ponta inicial |  |
| 11B | 11 | B | U1 ESP32 DevKit: pino IO27 (GPIO27) [J2.11] | LCD_D7 |
| 14B | 14 | B | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 19A | 19 | A | fio W1 (vermelho), ponta inicial |  |
| 19B | 19 | B | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 21A | 21 | A | M2 TCRT5000 (modulo LM393): pino VCC | 3V3 |
| 21D | 21 | D | fio W5 (laranja), ponta final |  |
| 21E | 21 | E | fio W6 (laranja), ponta inicial |  |
| 21F | 21 | F | fio W15 (vermelho), ponta inicial |  |
| 21H | 21 | H | fio W1 (vermelho), ponta final |  |
| 21I | 21 | I | fio W16 (vermelho), ponta inicial |  |
| 21J | 21 | J | M1 HC-SR04: pino VCC | 5V |
| 22A | 22 | A | M2 TCRT5000 (modulo LM393): pino GND | GND |
| 22C | 22 | C | fio W7 (preto), ponta inicial |  |
| 22I | 22 | I | fio W3 (amarelo), ponta final |  |
| 22J | 22 | J | M1 HC-SR04: pino TRIG | TRIG |
| 23A | 23 | A | M2 TCRT5000 (modulo LM393): pino DO | IR_DO |
| 23B | 23 | B | fio W9 (azul), ponta inicial |  |
| 23H | 23 | H | R1 1 kΩ: perna A | ECHO_5V |
| 23J | 23 | J | M1 HC-SR04: pino ECHO | ECHO_5V |
| 24A | 24 | A | M2 TCRT5000 (modulo LM393): pino AO |  |
| 24F | 24 | F | fio W7 (preto), ponta final |  |
| 24G | 24 | G | R3 300 Ω: perna B | GND |
| 24H | 24 | H | fio W8 (preto), ponta final |  |
| 24I | 24 | I | fio W2 (preto), ponta final |  |
| 24J | 24 | J | M1 HC-SR04: pino GND | GND |
| 27F | 27 | F | R2 1 kΩ: perna A | ECHO_NODE |
| 27H | 27 | H | R1 1 kΩ: perna B | ECHO_NODE |
| 27I | 27 | I | fio W4 (verde), ponta inicial |  |
| 28A | 28 | A | P1 Potenciometro rotativo: pino END_A | 3V3 |
| 28E | 28 | E | fio W6 (laranja), ponta final |  |
| 29A | 29 | A | P1 Potenciometro rotativo: pino WIPER | POT_WIPER |
| 29B | 29 | B | fio W10 (roxo), ponta inicial |  |
| 30A | 30 | A | P1 Potenciometro rotativo: pino END_B | GND |
| 30D | 30 | D | fio W8 (preto), ponta inicial |  |
| 30E | 30 | E | fio W11 (preto), ponta inicial |  |
| 30F | 30 | F | R2 1 kΩ: perna B | DIV_MID |
| 30G | 30 | G | R3 300 Ω: perna A | DIV_MID |
| P2:10B | 40 | B | R4 1 kΩ: perna B | GND |
| P2:10D | 40 | D | fio W14 (preto), ponta final |  |
| P2:12A | 42 | A | M3 LCD 2004A V1.1: pino VSS | GND |
| P2:12C | 42 | C | fio W12 (preto), ponta inicial |  |
| P2:12D | 42 | D | fio W14 (preto), ponta inicial |  |
| P2:12E | 42 | E | fio W11 (preto), ponta final |  |
| P2:13A | 43 | A | M3 LCD 2004A V1.1: pino VDD | 5V |
| P2:13E | 43 | E | fio W15 (vermelho), ponta final |  |
| P2:14A | 44 | A | M3 LCD 2004A V1.1: pino V0 | LCD_V0 |
| P2:14B | 44 | B | R4 1 kΩ: perna A | LCD_V0 |
| P2:15A | 45 | A | M3 LCD 2004A V1.1: pino RS | LCD_RS |
| P2:15E | 45 | E | fio W17 (azul), ponta final |  |
| P2:16A | 46 | A | M3 LCD 2004A V1.1: pino RW | GND |
| P2:16C | 46 | C | fio W12 (preto), ponta final |  |
| P2:16D | 46 | D | fio W13 (preto), ponta inicial |  |
| P2:17A | 47 | A | M3 LCD 2004A V1.1: pino E | LCD_E |
| P2:17E | 47 | E | fio W18 (verde), ponta final |  |
| P2:18A | 48 | A | M3 LCD 2004A V1.1: pino D0 |  |
| P2:19A | 49 | A | M3 LCD 2004A V1.1: pino D1 |  |
| P2:20A | 50 | A | M3 LCD 2004A V1.1: pino D2 |  |
| P2:21A | 51 | A | M3 LCD 2004A V1.1: pino D3 |  |
| P2:22A | 52 | A | M3 LCD 2004A V1.1: pino D4 | LCD_D4 |
| P2:22E | 52 | E | fio W19 (branco), ponta final |  |
| P2:23A | 53 | A | M3 LCD 2004A V1.1: pino D5 | LCD_D5 |
| P2:23E | 53 | E | fio W20 (marrom), ponta final |  |
| P2:24A | 54 | A | M3 LCD 2004A V1.1: pino D6 | LCD_D6 |
| P2:24E | 54 | E | fio W21 (laranja), ponta final |  |
| P2:25A | 55 | A | M3 LCD 2004A V1.1: pino D7 | LCD_D7 |
| P2:25E | 55 | E | fio W22 (roxo), ponta final |  |
| P2:26A | 56 | A | M3 LCD 2004A V1.1: pino A | LCD_A |
| P2:26B | 56 | B | R5 300 Ω: perna B | LCD_A |
| P2:27A | 57 | A | M3 LCD 2004A V1.1: pino K | GND |
| P2:27D | 57 | D | fio W13 (preto), ponta final |  |
| P2:29B | 59 | B | R5 300 Ω: perna A | 5V |
| P2:29E | 59 | E | fio W16 (vermelho), ponta final |  |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
