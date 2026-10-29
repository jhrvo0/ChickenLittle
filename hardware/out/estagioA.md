# Estagio A — ESP32 isolado

> Validar alimentacao, USB-Serial e firmware com a placa sozinha na protoboard.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 17B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 22B | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 4I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 10I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

_(vazio)_

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 4I | 4 | I | U1 ESP32 DevKit: pino GND [J3.1] | GND |
| 10I | 10 | I | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 17B | 17 | B | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 22B | 22 | B | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |

## Validacao automatica (software)

- sem observacoes

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
