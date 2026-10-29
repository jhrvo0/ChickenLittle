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
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO34 (GPIO34) | 8B | ECHO_NODE | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 17B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 22B | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 4I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 10I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | IO5 (GPIO5) | 13I | TRIG | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | VCC | 30J | 5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | TRIG | 31J | TRIG | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | ECHO | 32J | ECHO_5V | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| M1 | HC-SR04 | GND | 33J | GND | STANDARD_PINOUT_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | A | 32H | ECHO_5V | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R1 | R1 divisor (ECHO -> no) | B | 36H | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | A | 36G | ECHO_NODE | VALUE_PENDING_PHYSICAL_CONFIRMATION |
| R2 | R2 divisor (no -> GND) | B | 33G | GND | VALUE_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

| id | cor | de_furo | ate_furo | rede | tensao_esperada | funcao | seguranca |
|---|---|---|---|---|---|---|---|
| W1 | vermelho | 22A | 30H | 5V | 4,75-5,25 V | 5V -> VCC do HC-SR04 | Somente HC-SR04 e LCD usam 5 V. NUNCA levar este fio ao TCRT5000 ou ao potenciometro. |
| W2 | preto | 10J | 33I | GND | 0 V | GND -> GND do HC-SR04 | Sem terra comum o ECHO flutua e pode injetar 5 V no GPIO. |
| W3 | amarelo | 13J | 31I | TRIG | 0 / 3,3 V | GPIO5 -> TRIG | GPIO5 e pino de strapping; usa-lo como saida e aceitavel. |
| W4 | verde | 36F | 8A | ECHO_NODE | 0 / 3,00 V (3,15 V max. nominal) | No do divisor -> GPIO34 | NAO instalar antes de medir o no <= 3,30 V (ponto de parada da etapa B). |

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 4I | 4 | I | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 8A | 8 | A | fio W4 (verde), ponta final |  |
| 8B | 8 | B | U1 ESP32 DevKit: pino IO34 (GPIO34) [J2.5] | ECHO_NODE |
| 10I | 10 | I | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 10J | 10 | J | fio W2 (preto), ponta inicial |  |
| 13I | 13 | I | U1 ESP32 DevKit: pino IO5 (GPIO5) [J3.10] | TRIG |
| 13J | 13 | J | fio W3 (amarelo), ponta inicial |  |
| 17B | 17 | B | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 22A | 22 | A | fio W1 (vermelho), ponta inicial |  |
| 22B | 22 | B | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 30H | 30 | H | fio W1 (vermelho), ponta final |  |
| 30J | 30 | J | M1 HC-SR04: pino VCC | 5V |
| 31I | 31 | I | fio W3 (amarelo), ponta final |  |
| 31J | 31 | J | M1 HC-SR04: pino TRIG | TRIG |
| 32H | 32 | H | R1 2,2 kΩ: perna A | ECHO_5V |
| 32J | 32 | J | M1 HC-SR04: pino ECHO | ECHO_5V |
| 33G | 33 | G | R2 3,3 kΩ: perna B | GND |
| 33I | 33 | I | fio W2 (preto), ponta final |  |
| 33J | 33 | J | M1 HC-SR04: pino GND | GND |
| 36F | 36 | F | fio W4 (verde), ponta inicial |  |
| 36G | 36 | G | R2 3,3 kΩ: perna A | ECHO_NODE |
| 36H | 36 | H | R1 2,2 kΩ: perna B | ECHO_NODE |

## Validacao automatica (software)

- [INFO] STRAPPING_PIN_NOTED: IO5 (GPIO5) e pino de strapping (uso como saida e aceitavel)
- [WARN] DIVIDER_MARGIN_THIN: Divisor com tolerancia 5%: pior caso 3.275 V (margem 25 mV ao teto de 3.3 V); nominal 3.00 V

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
