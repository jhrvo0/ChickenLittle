# Guia do LCD 2004A com adaptador I2C — MotionPet

**Teste isolado; montagem conjunta no [guia final](bench_assembly_guide.md) e no [roteiro visual](../hardware/guia_montagem_final.html).** O usuário relatou que o LCD funcionou; a integração continua `PENDING_PHYSICAL_VALIDATION`. Este teste usa o adaptador I2C (PCF8574) em 3V3 sem conversor, com SDA e SCL diretos à ESP32. A faixa do PCF8574 não garante a do painel LCD inteiro.

## Pinos do adaptador (identifique pela serigrafia, não pela posição)

| Pino | Função |
|---|---|
| 1 | GND |
| 2 | VCC |
| 3 | SDA |
| 4 | SCL |

Os 16 contatos do LCD já estão ligados ao adaptador. Não ligue nada neles.

## Ligações elétricas

| Pino do adaptador | Vai para o pino da ESP32 | Observação |
|---|---|---|
| 1 (GND) | GND | |
| 2 (VCC) | **3V3** | **Nunca 5V.** |
| 3 (SDA) | GPIO21 | Direto |
| 4 (SCL) | GPIO22 | Direto |

Com o adaptador em 3,3V, os pull-ups de SDA e SCL ficam em 3,3V, o mesmo nível da ESP32. Com 5V, as linhas ficariam em 5V e danificariam a ESP32.

**Risco:** o LCD pode ficar fraco em 3,3V. Se os caracteres não aparecerem com o potenciômetro azul, a solução é um conversor de nível I2C, que é uma peça barata.

## Posições na protoboard

A ESP32 está encaixada na protoboard como no guia do HC-SR04, com a USB na linha 1.

No perfil de 38 pinos, confira as inscrições antes de usar estas tiras. Os pinos ocupam B/I; use A/J, que ficam livres. Os antigos exemplos em C/G podiam ficar sob a placa.

| Pino da ESP32 | Pino na tira |
|---|---|
| GND | 6J (tira 6 F–J) |
| 3V3 | 19J (tira 19 F–J) |
| GPIO21 | 14A (tira 14 A–E) |
| GPIO22 | 17A (tira 17 A–E) |

Cada cabo macho-fêmea liga uma tira a um pino do adaptador. A ponta **macho** entra no furo da protoboard. A ponta **fêmea** encaixa no pino do adaptador.

| Pino do adaptador | Ponta macho entra no furo | Ponta fêmea vai no pino |
|---|---|---|
| GND | 6J | GND do adaptador |
| VCC | 19J | VCC do adaptador |
| SDA | 14A | SDA do adaptador |
| SCL | 17A | SCL do adaptador |

Por que o adaptador fica fora da protoboard: os pinos GND, 3V3, GPIO21 e GPIO22 da ESP32 estão em colunas diferentes, e os quatro pinos do adaptador são vizinhos. Encaixado, um pino cairia na tira de outro. Por isso o adaptador fica solto, e cada cabo leva o sinal até um pino dele. Prenda o adaptador com fita para não balançar.

Notas:

- Neste teste isolado, use os furos livres A/J. Na montagem conjunta, o guia final distribui 3V3 e GND em outras tiras para não colocar duas pontas no mesmo furo.
- O HC-SR04 padrão usa **5 V com divisor no ECHO** na montagem final. A indicação anterior de compartilhá-lo com o 3V3 do LCD estava errada. Durante este teste isolado, tire os fios dos sensores.

## Ajustes no adaptador

- **Potenciômetro azul:** é o contraste. Gire com uma chave de fenda pequena até os caracteres aparecerem.
- **Jumper de backlight:** se a placa tiver, mantenha colocado.

## Passo a passo

1. Desligue a USB.
2. Faça as ligações elétricas e os furos da protoboard acima. Confira cada fio pelo nome do pino, não pela cor.
3. Tire os fios do HC-SR04 e de outros módulos. O teste deve ter só o adaptador, o LCD e os cabos.
4. Ligue a USB no computador.
5. Grave o teste isolado (você roda o comando):

   ```bash
   .\.venv\Scripts\python.exe -m platformio run -d teste-lcd -t upload --upload-port COMx
   ```

6. Resultado esperado: o monitor serial mostra `Dispositivo I2C em 0x27` (ou `0x3F`). O LCD mostra três linhas de texto e, na linha 4, `Contador: N` subindo 1 por segundo.

## Se der errado

- **"Nenhum adaptador I2C encontrado":** confira SDA=GPIO21 (14A), SCL=GPIO22 (17A), GND (6J) e VCC=3V3 (19J). Use a porta realmente listada, não uma COM antiga.
- **Endereço encontrado, tela apagada:** gire o potenciômetro azul e verifique o jumper de backlight.
- **Só quadrados escuros:** contraste alto demais. Gire o potenciômetro azul no outro sentido.
- **Texto errado ou falhando:** confira os cabos de SDA e SCL e se há fio encostando em outro furo da tira.

## Depois do teste isolado

- A parte funcional do LCD está validada se o texto estiver legível e o contador andar.
- O firmware do MotionPet **já usa o HAL I2C PCF8574**, com SDA=GPIO21 e SCL=GPIO22. O driver HD44780 trabalha por trás desse HAL; seus bits não são seis ligações físicas à ESP32.
- A etapa D atual usa o perfil I2C de 3V3 e exige tensão medida, conferência dos quatro fios e comparação visual. Veja o guia final para os comandos.
