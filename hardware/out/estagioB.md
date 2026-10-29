# Estagio B — HC-SR04 + divisor de ECHO

> Medir distancia com ECHO protegido (<= 3,30 V no GPIO34). PRIORIDADE MAXIMA.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `R2.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 3.0 V (max 3.15 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor 2,2 k / 3,3 k: 3,00 V nominal @ 5,00 V.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 5B | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 14B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 19B | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 1I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 7I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO5 (GPIO5) | 10I | TRIG | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | VCC | 21J | 5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | TRIG | 22J | TRIG | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | ECHO | 23J | ECHO_5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | GND | 24J | GND | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | A | 23H | ECHO_5V | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | B | 27H | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | A | 27G | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | B | 24G | GND | VALUE_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 19A | 21H | 5V | 4,75-5,25 V | 5V -> VCC do HC-SR04 | Somente HC-SR04 e LCD usam 5 V. NUNCA levar este fio ao TCRT5000 ou ao potenciometro. |
| W2 | preto | 7J | 24I | GND | 0 V | GND -> GND do HC-SR04 | Sem terra comum o ECHO flutua e pode injetar 5 V no GPIO. |
| W3 | amarelo | 10J | 22I | TRIG | 0 / 3,3 V | GPIO5 -> TRIG | GPIO5 e pino de strapping; usa-lo como saida e aceitavel. |
| W4 | verde | 27F | 5A | ECHO_NODE | 0 / 3,00 V (3,15 V max. nominal) | No do divisor -> GPIO34 | NAO instalar antes de medir o no <= 3,30 V (ponto de parada da etapa B). |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 1I | 1 | I | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 5A | 5 | A | fio W4 (verde), ponta final |  |
| 5B | 5 | B | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 7I | 7 | I | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 7J | 7 | J | fio W2 (preto), ponta inicial |  |
| 10I | 10 | I | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 10J | 10 | J | fio W3 (amarelo), ponta inicial |  |
| 14B | 14 | B | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 19A | 19 | A | fio W1 (vermelho), ponta inicial |  |
| 19B | 19 | B | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 21H | 21 | H | fio W1 (vermelho), ponta final |  |
| 21J | 21 | J | M1 HC-SR04: pino VCC | 5V |
| 22I | 22 | I | fio W3 (amarelo), ponta final |  |
| 22J | 22 | J | M1 HC-SR04: pino TRIG | TRIG |
| 23H | 23 | H | R1 2,2 kΩ: perna A | ECHO_5V |
| 23J | 23 | J | M1 HC-SR04: pino ECHO | ECHO_5V |
| 24G | 24 | G | R2 3,3 kΩ: perna B | GND |
| 24I | 24 | I | fio W2 (preto), ponta final |  |
| 24J | 24 | J | M1 HC-SR04: pino GND | GND |
| 27F | 27 | F | fio W4 (verde), ponta inicial |  |
| 27G | 27 | G | R2 3,3 kΩ: perna A | ECHO_NODE |
| 27H | 27 | H | R1 2,2 kΩ: perna B | ECHO_NODE |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)
- [WARN] DIVIDER_MARGIN_THIN: Divisor com tolerancia 5%: pior caso 3.275 V (margem 25 mV ao teto de 3.3 V); nominal 3.00 V

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
