# Netlist canonica (resumo gerado)

## Estagio A

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.

## Estagio B

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `R3.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.

## Estagio C

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `R3.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.

## Estagio D

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `M3.K`, `M3.RW`, `M3.VSS`, `R3.B`, `R4.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `M3.VDD`, `R5.A`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.
- **LCD_V0** — dominio `ANALOG_LOW`, nominal 0.4 V (max 0.8 V): `M3.V0`, `R4.A`. Contraste do LCD (ajuste na bancada: C07).
- **LCD_A** — dominio `POWER_5V_LED`, nominal 5.0 V (max 5.25 V): `M3.A`, `R5.B`. Anodo do backlight (via R5).
- **LCD_RS** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.RS`, `U1.IO19`. GPIO19 -> RS.
- **LCD_E** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.E`, `U1.IO18`. GPIO18 -> E.
- **LCD_D4** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D4`, `U1.IO21`. GPIO21 -> D4.
- **LCD_D5** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D5`, `U1.IO22`. GPIO22 -> D5.
- **LCD_D6** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D6`, `U1.IO23`. GPIO23 -> D6.
- **LCD_D7** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D7`, `U1.IO27`. GPIO27 -> D7.

## Estagio E

- **GND** — dominio `GND`, nominal 0.0 V (max 0.0 V): `M1.GND`, `M2.GND`, `M3.K`, `M3.RW`, `M3.VSS`, `R3.B`, `R4.B`, `U1.GND@J2.14`, `U1.GND@J3.1`, `U1.GND@J3.7`. Terra comum. Os 3 pinos GND da placa sao ligados entre si pela propria PCB da ESP32.
- **5V** — dominio `5V`, nominal 5.0 V (max 5.25 V): `M1.VCC`, `M3.VDD`, `R5.A`, `U1.5V`. 5 V vindos da USB (pino 5V da ESP32).
- **3V3** — dominio `3V3`, nominal 3.3 V (max 3.35 V): `M2.VCC`, `U1.3V3`. 3,3 V do regulador da ESP32.
- **TRIG** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M1.TRIG`, `U1.IO5`. GPIO5 -> TRIG.
- **ECHO_5V** — dominio `SIGNAL_5V`, nominal 5.0 V (max 5.25 V): `M1.ECHO`, `R1.A`. ECHO bruto do HC-SR04 (pulsos de ~5 V). NUNCA pode tocar um GPIO.
- **ECHO_NODE** — dominio `SIGNAL_3V3`, nominal 2.83 V (max 2.97 V): `R1.B`, `R2.A`, `U1.IO34`. No do divisor: R1 = 1 kΩ em cima; R2 (1 kΩ) + R3 (300 Ω) em serie embaixo = 1,3 kΩ. 2,83 V nominal @ 5,00 V (pior caso 3,10 V).
- **DIV_MID** — dominio `SIGNAL_3V3`, nominal 0.65 V (max 0.69 V): `R2.B`, `R3.A`. Junção entre R2 e R3 (coluna 30). Só liga os dois resistores; não vai a nenhum pino.
- **IR_DO** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M2.DO`, `U1.IO35`. Saida digital do TCRT5000.
- **LCD_V0** — dominio `ANALOG_LOW`, nominal 0.4 V (max 0.8 V): `M3.V0`, `R4.A`. Contraste do LCD (ajuste na bancada: C07).
- **LCD_A** — dominio `POWER_5V_LED`, nominal 5.0 V (max 5.25 V): `M3.A`, `R5.B`. Anodo do backlight (via R5).
- **LCD_RS** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.RS`, `U1.IO19`. GPIO19 -> RS.
- **LCD_E** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.E`, `U1.IO18`. GPIO18 -> E.
- **LCD_D4** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D4`, `U1.IO21`. GPIO21 -> D4.
- **LCD_D5** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D5`, `U1.IO22`. GPIO22 -> D5.
- **LCD_D6** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D6`, `U1.IO23`. GPIO23 -> D6.
- **LCD_D7** — dominio `SIGNAL_3V3`, nominal 3.3 V (max 3.3 V): `M3.D7`, `U1.IO27`. GPIO27 -> D7.
