# Estagio E — Montagem completa

> Todos os componentes conectados, separados visualmente em alimentacao, sensores, LCD e controle.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `M3.K`, `M3.RW`, `M3.VSS`, `P1.END_B`, `R2.B`, `R3.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `M3.VDD`, `R4.A`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `P1.END_A`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 3.0 V (max 3.15 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor 2,2 k / 3,3 k: 3,00 V nominal @ 5,00 V.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.
- **POT_WIPER** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `P1.WIPER`, `U1.VP`. Cursor do potenciometro.
- **LCD_V0** — dominio `ANALOG_LOW`, nominal 0.0 V (max 0.8 V): `M3.V0`, `R3.A`. Contraste do LCD (ver item C07).
- **LCD_A** — dominio `POWER_5V_LED`, nominal 5.0 V (max 5.25 V): `M3.A`, `R4.B`. Anodo do backlight (via R4).
- **LCD_RS** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.RS`, `U1.IO19`. GPIO19 -> RS.
- **LCD_E** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.E`, `U1.IO18`. GPIO18 -> E.
- **LCD_D4** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D4`, `U1.IO21`. GPIO21 -> D4.
- **LCD_D5** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D5`, `U1.IO22`. GPIO22 -> D5.
- **LCD_D6** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D6`, `U1.IO23`. GPIO23 -> D6.
- **LCD_D7** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D7`, `U1.IO27`. GPIO27 -> D7.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 3V3 | 4B | 3V3 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | VP (GPIO36) | 6B | POT_WIPER | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 8B | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO35 (GPIO35) | 9B | IR_DO | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO27 (GPIO27) | 14B | LCD_D7 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 17B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 22B | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 4I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO23 (GPIO23) | 5I | LCD_D6 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO22 (GPIO22) | 6I | LCD_D5 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO21 (GPIO21) | 9I | LCD_D4 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 10I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO19 (GPIO19) | 11I | LCD_RS | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO18 (GPIO18) | 12I | LCD_E | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO5 (GPIO5) | 13I | TRIG | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | VCC | 30J | 5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | TRIG | 31J | TRIG | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | ECHO | 32J | ECHO_5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | GND | 33J | GND | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | A | 32H | ECHO_5V | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | B | 36H | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | A | 36G | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | B | 33G | GND | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| M2 | TCRT5000 (modulo LM393) | VCC | 27A | 3V3 | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | GND | 28A | GND | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | DO | 29A | IR_DO | PIN_ORDER_UNCONFIRMED |
| M2 | TCRT5000 (modulo LM393) | AO | 30A | (sem conexao: NC) | PIN_ORDER_UNCONFIRMED |
| P1 | Potenciometro rotativo | END_A | 34A | 3V3 | PENDING_PHYSICAL_CONFIRMATION |
| P1 | Potenciometro rotativo | WIPER | 35A | POT_WIPER | PENDING_PHYSICAL_CONFIRMATION |
| P1 | Potenciometro rotativo | END_B | 36A | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | VSS | 46J | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | VDD | 47J | 5V | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | V0 | 48J | LCD_V0 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RS | 49J | LCD_RS | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | RW | 50J | GND | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | E | 51J | LCD_E | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D0 | 52J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D1 | 53J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D2 | 54J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D3 | 55J | (sem conexao: NC) | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D4 | 56J | LCD_D4 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D5 | 57J | LCD_D5 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D6 | 58J | LCD_D6 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | D7 | 59J | LCD_D7 | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | A | 60J | LCD_A | PENDING_PHYSICAL_CONFIRMATION |
| M3 | LCD 2004A V1.1 | K | 61J | GND | PENDING_PHYSICAL_CONFIRMATION |
| R3 | R3 contraste V0 -> GND | A | 48G | LCD_V0 | DESIGN_ISSUE_FLAGGED |
| R3 | R3 contraste V0 -> GND | B | 44G | GND | DESIGN_ISSUE_FLAGGED |
| R4 | R4 backlight 5 V -> A (condicional) | A | 63G | 5V | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |
| R4 | R4 backlight 5 V -> A (condicional) | B | 60G | LCD_A | CONDITIONAL_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 22A | 30H | 5V | 4,75-5,25 V | 5V -> VCC do HC-SR04 | Somente HC-SR04 e LCD usam 5 V. NUNCA levar este fio ao TCRT5000 ou ao potenciometro. |
| W2 | preto | 10J | 33I | GND | 0 V | GND -> GND do HC-SR04 | Sem terra comum o ECHO flutua e pode injetar 5 V no GPIO. |
| W3 | amarelo | 13J | 31I | TRIG | 0 / 3,3 V | GPIO5 -> TRIG | GPIO5 e pino de strapping; usa-lo como saida e aceitavel. |
| W4 | verde | 36F | 8A | ECHO_NODE | 0 / 3,00 V (3,15 V max. nominal) | No do divisor -> GPIO34 | NAO instalar antes de medir o no <= 3,30 V (ponto de parada da etapa B). |
| W5 | laranja | 4A | 27B | 3V3 | 3,25-3,35 V | 3V3 -> VCC do TCRT5000 | NUNCA ligar o TCRT5000 em 5 V. |
| W6 | laranja | 27C | 34C | 3V3 | 3,25-3,35 V | 3V3 -> extremo do potenciometro | NUNCA ligar o potenciometro em 5 V. |
| W7 | preto | 17A | 28B | GND | 0 V | GND -> GND do TCRT5000 |  |
| W8 | preto | 28C | 36C | GND | 0 V | GND -> extremo do potenciometro |  |
| W9 | azul | 29B | 9A | IR_DO | 0 / 3,3 V | DO -> GPIO35 |  |
| W10 | roxo | 35B | 6A | POT_WIPER | 0-3,3 V | Cursor -> GPIO36 (VP) |  |
| W12 | preto | 33H | 44I | GND | 0 V | GND -> no de terra do LCD |  |
| W13 | preto | 44H | 46H | GND | 0 V | GND -> VSS (pino 1) |  |
| W14 | preto | 44F | 50I | GND | 0 V | GND -> RW (pino 5) | OBRIGATORIO: RW = 0,0 Ohm para GND antes de ligar. |
| W15 | preto | 50H | 61I | GND | 0 V | GND -> K (pino 16) |  |
| W16 | vermelho | 30G | 47I | 5V | 4,75-5,25 V | 5V -> VDD (pino 2) | Se os caracteres vierem corrompidos, ver contingencia do diodo em docs/hardware_safety.md. |
| W17 | vermelho | 47H | 63H | 5V | 4,75-5,25 V | 5V -> R4 (backlight) |  |
| W18 | azul | 11J | 49I | LCD_RS | 0 / 3,3 V | GPIO19 -> RS (pino 4) |  |
| W19 | verde | 12J | 51I | LCD_E | 0 / 3,3 V | GPIO18 -> E (pino 6) |  |
| W20 | branco | 9J | 56I | LCD_D4 | 0 / 3,3 V | GPIO21 -> D4 (pino 11) |  |
| W21 | marrom | 6J | 57I | LCD_D5 | 0 / 3,3 V | GPIO22 -> D5 (pino 12) |  |
| W22 | laranja | 5J | 58I | LCD_D6 | 0 / 3,3 V | GPIO23 -> D6 (pino 13) |  |
| W23 | roxo | 14A | 59I | LCD_D7 | 0 / 3,3 V | GPIO27 -> D7 (pino 14) |  |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 4A | 4 | A | fio W5 (laranja), ponta inicial |  |
| 4B | 4 | B | U1 ESP32 DevKit: pino 3V3 [J2.1] | 3V3 |
| 4I | 4 | I | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 5I | 5 | I | U1 ESP32 DevKit: pino IO23 (GPIO23) [J3.2] | LCD_D6 |
| 5J | 5 | J | fio W22 (laranja), ponta inicial |  |
| 6A | 6 | A | fio W10 (roxo), ponta final |  |
| 6B | 6 | B | U1 ESP32 DevKit: pino VP (GPIO36) [J2.3] | POT_WIPER |
| 6I | 6 | I | U1 ESP32 DevKit: pino IO22 (GPIO22) [J3.3] | LCD_D5 |
| 6J | 6 | J | fio W21 (marrom), ponta inicial |  |
| 8A | 8 | A | fio W4 (verde), ponta final |  |
| 8B | 8 | B | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 9A | 9 | A | fio W9 (azul), ponta final |  |
| 9B | 9 | B | U1 ESP32 DevKit: pino IO35 (GPIO35) [J2.6] | IR_DO |
| 9I | 9 | I | U1 ESP32 DevKit: pino IO21 (GPIO21) [J3.6] | LCD_D4 |
| 9J | 9 | J | fio W20 (branco), ponta inicial |  |
| 10I | 10 | I | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 10J | 10 | J | fio W2 (preto), ponta inicial |  |
| 11I | 11 | I | U1 ESP32 DevKit: pino IO19 (GPIO19) [J3.8] | LCD_RS |
| 11J | 11 | J | fio W18 (azul), ponta inicial |  |
| 12I | 12 | I | U1 ESP32 DevKit: pino IO18 (GPIO18) [J3.9] | LCD_E |
| 12J | 12 | J | fio W19 (verde), ponta inicial |  |
| 13I | 13 | I | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 13J | 13 | J | fio W3 (amarelo), ponta inicial |  |
| 14A | 14 | A | fio W23 (roxo), ponta inicial |  |
| 14B | 14 | B | U1 ESP32 DevKit: pino IO27 (GPIO27) [J2.11] | LCD_D7 |
| 17A | 17 | A | fio W7 (preto), ponta inicial |  |
| 17B | 17 | B | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 22A | 22 | A | fio W1 (vermelho), ponta inicial |  |
| 22B | 22 | B | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 27A | 27 | A | M2 TCRT5000 (modulo LM393): pino VCC | 3V3 |
| 27B | 27 | B | fio W5 (laranja), ponta final |  |
| 27C | 27 | C | fio W6 (laranja), ponta inicial |  |
| 28A | 28 | A | M2 TCRT5000 (modulo LM393): pino GND | GND |
| 28B | 28 | B | fio W7 (preto), ponta final |  |
| 28C | 28 | C | fio W8 (preto), ponta inicial |  |
| 29A | 29 | A | M2 TCRT5000 (modulo LM393): pino DO | IR_DO |
| 29B | 29 | B | fio W9 (azul), ponta inicial |  |
| 30A | 30 | A | M2 TCRT5000 (modulo LM393): pino AO |  |
| 30G | 30 | G | fio W16 (vermelho), ponta inicial |  |
| 30H | 30 | H | fio W1 (vermelho), ponta final |  |
| 30J | 30 | J | M1 HC-SR04: pino VCC | 5V |
| 31I | 31 | I | fio W3 (amarelo), ponta final |  |
| 31J | 31 | J | M1 HC-SR04: pino TRIG | TRIG |
| 32H | 32 | H | R1 2,2 kΩ: perna A | ECHO_5V |
| 32J | 32 | J | M1 HC-SR04: pino ECHO | ECHO_5V |
| 33G | 33 | G | R2 3,3 kΩ: perna B | GND |
| 33H | 33 | H | fio W12 (preto), ponta inicial |  |
| 33I | 33 | I | fio W2 (preto), ponta final |  |
| 33J | 33 | J | M1 HC-SR04: pino GND | GND |
| 34A | 34 | A | P1 Potenciometro rotativo: pino END_A | 3V3 |
| 34C | 34 | C | fio W6 (laranja), ponta final |  |
| 35A | 35 | A | P1 Potenciometro rotativo: pino WIPER | POT_WIPER |
| 35B | 35 | B | fio W10 (roxo), ponta inicial |  |
| 36A | 36 | A | P1 Potenciometro rotativo: pino END_B | GND |
| 36C | 36 | C | fio W8 (preto), ponta final |  |
| 36F | 36 | F | fio W4 (verde), ponta inicial |  |
| 36G | 36 | G | R2 3,3 kΩ: perna A | ECHO_NODE |
| 36H | 36 | H | R1 2,2 kΩ: perna B | ECHO_NODE |
| 44F | 44 | F | fio W14 (preto), ponta inicial |  |
| 44G | 44 | G | R3 1 kΩ: perna B | GND |
| 44H | 44 | H | fio W13 (preto), ponta inicial |  |
| 44I | 44 | I | fio W12 (preto), ponta final |  |
| 46H | 46 | H | fio W13 (preto), ponta final |  |
| 46J | 46 | J | M3 LCD 2004A V1.1: pino VSS | GND |
| 47H | 47 | H | fio W17 (vermelho), ponta inicial |  |
| 47I | 47 | I | fio W16 (vermelho), ponta final |  |
| 47J | 47 | J | M3 LCD 2004A V1.1: pino VDD | 5V |
| 48G | 48 | G | R3 1 kΩ: perna A | LCD_V0 |
| 48J | 48 | J | M3 LCD 2004A V1.1: pino V0 | LCD_V0 |
| 49I | 49 | I | fio W18 (azul), ponta final |  |
| 49J | 49 | J | M3 LCD 2004A V1.1: pino RS | LCD_RS |
| 50H | 50 | H | fio W15 (preto), ponta inicial |  |
| 50I | 50 | I | fio W14 (preto), ponta final |  |
| 50J | 50 | J | M3 LCD 2004A V1.1: pino RW | GND |
| 51I | 51 | I | fio W19 (verde), ponta final |  |
| 51J | 51 | J | M3 LCD 2004A V1.1: pino E | LCD_E |
| 52J | 52 | J | M3 LCD 2004A V1.1: pino D0 |  |
| 53J | 53 | J | M3 LCD 2004A V1.1: pino D1 |  |
| 54J | 54 | J | M3 LCD 2004A V1.1: pino D2 |  |
| 55J | 55 | J | M3 LCD 2004A V1.1: pino D3 |  |
| 56I | 56 | I | fio W20 (branco), ponta final |  |
| 56J | 56 | J | M3 LCD 2004A V1.1: pino D4 | LCD_D4 |
| 57I | 57 | I | fio W21 (marrom), ponta final |  |
| 57J | 57 | J | M3 LCD 2004A V1.1: pino D5 | LCD_D5 |
| 58I | 58 | I | fio W22 (laranja), ponta final |  |
| 58J | 58 | J | M3 LCD 2004A V1.1: pino D6 | LCD_D6 |
| 59I | 59 | I | fio W23 (roxo), ponta final |  |
| 59J | 59 | J | M3 LCD 2004A V1.1: pino D7 | LCD_D7 |
| 60G | 60 | G | R4 150 Ω: perna B | LCD_A |
| 60J | 60 | J | M3 LCD 2004A V1.1: pino A | LCD_A |
| 61I | 61 | I | fio W15 (preto), ponta final |  |
| 61J | 61 | J | M3 LCD 2004A V1.1: pino K | GND |
| 63G | 63 | G | R4 150 Ω: perna A | 5V |
| 63H | 63 | H | fio W17 (vermelho), ponta final |  |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)
- [WARN] DIVIDER_MARGIN_THIN: Divisor com tolerancia 5%: pior caso 3.275 V (margem 25 mV ao teto de 3.3 V); nominal 3.00 V

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
