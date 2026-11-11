# Segurança elétrica — montagem atual com LCD I²C

O [guia de montagem final](bench_assembly_guide.md) e o [roteiro visual](../hardware/guia_montagem_final.html) descrevem o perfil atual. Os testes individuais foram relatados pelo usuário; o conjunto continua `PENDING_PHYSICAL_VALIDATION` até ser montado e observado. Nenhuma tensão neste documento foi medida automaticamente.

## Alimentação

- GND de referência na P1: **6J**, conforme teste LCD de 05/11 recuperado em [bench_verified_wiring.md](bench_verified_wiring.md). A revisão atual não usa 2J como alternativa.
- Tire a USB antes de alterar fios. Alimente o conjunto pela USB da ESP32; não acrescente outra fonte em paralelo.
- HC-SR04: VCC em **5V** da placa, GND comum, TRIG em GPIO5, ECHO somente pelo divisor até GPIO34. Use o pino identificado na placa, não uma posição presumida. O HC-SR04 padrão especifica alimentação de 5 V.
- TCRT5000: VCC em **3V3**, DO em GPIO35 e GND comum. AO desconectado. Alimentá-lo em 5 V pode colocar 5 V na saída DO.
- LCD com PCF8574, **sem conversor**: VCC em **3V3**, SDA em GPIO21, SCL em GPIO22 e GND comum. Pull-ups típicos seguem VCC. Nunca alimente esse backpack em 5 V com SDA/SCL diretos ao ESP32.
- Na revisão 2, P1 usa um par lateral com +5V/GND; P2 usa um par com +3V3/GND. Os dois − são unidos por F4; os dois + permanecem separados. Use só o primeiro grupo de cinco furos de cada trilho e confira sua continuidade com USB fora. O par da outra lateral de cada placa fica sem fios; não presuma continuidade até a outra ponta, lateral ou placa. O divisor fica na região central da P2.
- Valores usuais para conferir a alimentação: 5V entre 4,75–5,25 V; 3V3 próximo de 3,30 V (referência 3,25–3,35 V). Valores fora disso pedem revisão da alimentação antes do teste conjunto.

GPIO6–11 pertencem à flash; GPIO1/3 atendem à serial e GPIO12 deve ficar livre. GPIO5 é pino de strapping: não acrescente pull-down ou outro circuito nesse sinal. GPIO34/35 são somente entrada e não têm pull-up interno utilizável; DO precisa do pull-up do próprio módulo. Se DO flutuar, confira a placa e seu pull-up em 3V3.

## Divisor do ECHO

```text
ECHO ── R1 1 kΩ ── nó ── R2 1 kΩ ── R3 300 Ω ── GND
                     └── GPIO34
```

R2 e R3 ficam **em série**, não em paralelo. O cálculo prevê 2,83 V para ECHO de 5,00 V. Considerando entrada 4,75–5,25 V e resistores com tolerância individual de 5%, prevê aproximadamente 2,57–3,10 V. São cálculos; o nível real também depende do módulo e dos contatos. O critério conservador do projeto é **até 3,30 V no GPIO**; 3,5 V não é aceito.

Meça os resistores soltos. Faça o ensaio estático descrito no guia, mantendo HC-SR04 e GPIO34 desconectados: alimente temporariamente a entrada de R1 por 5 V e meça o nó. Desenergize e retire o jumper temporário antes de ligar ECHO. O multímetro em ECHO pulsante pode mostrar a média, não o pico; ele não prova o nível alto. Se houver instrumento adequado, registre também o pico real. Dúvida de montagem ou valor acima do limite: mantenha GPIO34 desconectado e corrija.

Para o cálculo no assistente, a resistência inferior equivalente é `--r2 1300`; use as resistências reais se diferirem. Não substitua por 1 kΩ/2 kΩ, que fornece 3,33 V nominais a 5 V. A leitura de distância funcionando, sozinha, não comprova a segurança elétrica.

## LCD e adaptação de nível

Use somente GND/VCC/SDA/SCL do backpack. Os antigos seis sinais, R4 de contraste, R5 de backlight e o jumper físico RW–GND são do projeto **paralelo histórico**. No atual, o HAL PCF8574 mantém P1/RW em zero durante a operação. Não aterre um pino do adaptador por analogia com os 16 contatos do painel.

O PCF8574 aceita alimentação de 2,5–6 V; isso **não especifica a faixa do painel LCD inteiro**. O perfil atual tenta o conjunto em 3,3 V para manter o I²C compatível com a ESP32. Ajuste o contraste e confira a tela. Se o painel precisar de 5 V, use conversor I²C **bidirecional** com LV=3V3, HV=5V, GND comum e um canal para cada sinal. As ligações estão no guia. Resistores de divisor, diodos isolados e conversores unidirecionais não substituem esse circuito I²C.

## Referências

- [Espressif — datasheet ESP32](https://documentation.espressif.com/esp32_datasheet_en.html): características dos GPIOs, limiares e alimentação. O limite de 3,30 V acima é o critério conservador deste projeto.
- [ElecFreaks — HC-SR04, hospedado pela SparkFun](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf): 5 V, pulso TRIG de 10 µs e intervalo sugerido acima de 60 ms. Firmware inicia com 70 ms.
- [Texas Instruments — PCF8574](https://www.ti.com/lit/ds/symlink/pcf8574.pdf): alimentação, I²C de até 100 kHz e características de entrada. Não é datasheet do painel LCD ou do backpack completo.

## Testes pelo guia

O serviço local `terminal.bench.guide` consulta a USB após cada instalação. Ele não mede tensões, não confirma o contato dos jumpers e não enxerga o LCD. As medidas e confirmações informadas no guia são declarações do operador. Testes sem esses dados permanecem pendentes. Não retire o divisor para simplificar: LCD e IR já usam somente jumpers; o HC-SR04 em 5 V exige adaptação de nível no ECHO.

O diagnóstico de iluminação da revisão 4 é temporário: conserva F1–F4, retira F16/F17 e move apenas F14 para P1:+3 e F15 para P1:−4. O LCD recebe 5 V sem ligação SDA/SCL à ESP32. Os trilhos + das duas placas continuam separados e o TCRT5000 não recebe 5 V. Antes de recolocar os sinais, voltar F14 a P2:+3 (3V3) e F15 a P2:−3. Esse modo não é a montagem final nem valida o LCD via serial.
