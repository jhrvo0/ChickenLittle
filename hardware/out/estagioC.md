# Estagio C — TCRT5000

> Adicionar deteccao IR (GPIO35) em 3,3 V. (O potenciometro foi removido.)

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `R3.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 3V3 | 19I | 3V3 | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 15I | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO35 (GPIO35) | 14I | IR_DO | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 6I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 1I | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 19B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 13B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
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

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 1J | 3W | 5V | 4,75-5,25 V | 5V da ESP32 (1J, junto da USB) -> trilho + (vermelho) de baixo | So o HC-SR04 e o LCD usam 5 V. NUNCA ligue o TCRT5000 no trilho +. |
| W2 | preto | 13A | 15X | GND | 0 V | GND da ESP32 -> trilho - (azul) de baixo |  |
| W3 | verde | 26E | 15J | ECHO_NODE | 0 / 2,83 V (pior caso 3,10 V) | No do divisor -> GPIO34 | So instale depois do ensaio do passo 5. |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 1I | 1 | I | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 1J | 1 | J | fio W1 (vermelho), ponta inicial |  |
| 3W | 3 | W | fio W1 (vermelho), ponta final |  |
| 6I | 6 | I | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 6J | 6 | J | M2 TCRT5000 (modulo LM393): pino GND | GND |
| 10A | 10 | A | M1 HC-SR04: pino TRIG | TRIG |
| 10B | 10 | B | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 13A | 13 | A | fio W2 (preto), ponta inicial |  |
| 13B | 13 | B | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 14I | 14 | I | U1 ESP32 DevKit: pino IO35 (GPIO35) [J2.6] | IR_DO |
| 14J | 14 | J | M2 TCRT5000 (modulo LM393): pino DO | IR_DO |
| 15X | 15 | X | fio W2 (preto), ponta final |  |
| 15I | 15 | I | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 15J | 15 | J | fio W3 (verde), ponta final |  |
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
| 29A | 29 | A | R3 300 Ω: perna A | DIV_MID |
| 29D | 29 | D | R2 1 kΩ: perna B | DIV_MID |
| 30X | 30 | X | R3 300 Ω: perna B | GND |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
