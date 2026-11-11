# Estagio A — ESP32 isolado

> **CAD paralelo histórico.** Para a montagem atual com LCD I²C, use [o guia final](../guia_montagem_final.html). D/E antigos não se aplicam ao backpack.

> Validar alimentacao, USB-Serial e firmware com a placa sozinha na protoboard.

> Status: `PENDING_PHYSICAL_VALIDATION`. Este documento e GERADO de `hardware/netlist/motionpet.netlist.json`.

## Redes eletricas

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `U1.GND@J2.14`, `U1.GND@J2.18`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. A serigrafia da placa fotografada mostra 4 pinos GND; sua continuidade interna e uma hipotese a verificar fisicamente.

## Componentes e furos

| componente | descricao | pino | furo | rede | estado |
|---|---|---|---|---|---|
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 6I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 2I | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | 5V | 1I | 5V | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 19B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |
| U1 | ESP32 DevKit (ESP-WROOM-32, USB-C) | GND | 13B | GND | ASSUMED_PENDING_PHYSICAL_CONFIRMATION |

## Fios (fio a fio)

_(vazio)_

## Mapa de furos ocupados

| furo | coluna | fileira | ocupante | rede |
|---|---|---|---|---|
| 1I | 1 | I | U1 ESP32 DevKit: pino 5V [J2.19] | 5V |
| 2I | 2 | I | U1 ESP32 DevKit: pino GND [J2.18] | GND |
| 6I | 6 | I | U1 ESP32 DevKit: pino GND [J2.14] | GND |
| 13B | 13 | B | U1 ESP32 DevKit: pino GND [J3.7] | GND |
| 19B | 19 | B | U1 ESP32 DevKit: pino GND [J3.1] | GND |

## Validacao automatica (software)

- sem observacoes

_A validacao acima e de CONSISTENCIA (software). Nao substitui medicoes com multimetro._
