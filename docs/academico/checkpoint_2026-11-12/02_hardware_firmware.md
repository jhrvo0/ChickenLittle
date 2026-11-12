# Inventário factual do hardware e do firmware

## Fontes e nível de evidência

As fontes da bancada são `docs/bench_verified_wiring.md`, `hardware/netlist/motionpet_atual_sem_lcd.json` (revisão 5) e `hardware/wokwi/montagem_atual/diagram.json`. Foram lidas nesta preparação e comparadas com `firmware/main/pinout_config.h`. A [conferência estática](evidencias/circuito-conferencia.json) não executa a placa, não mede tensão e não comprova contato de fio.

| Componente em uso | Tipo / função | Sinal e ligação | Estado sustentado |
|---|---|---|---|
| ESP32 DevKit de 38 pinos | Controlador; aquisição e classificação; USB | Alimentação USB; HC/IR nos GPIOs abaixo | Firmware integrado previamente gravado segundo registro; build atual aprovado; nenhuma gravação ou leitura serial nesta preparação |
| HC-SR04 | Sensor de distância por tempo de voo ultrassônico | VCC=5 V; GND comum; TRIG=GPIO5 em P1:10A; ECHO passa pelo divisor até GPIO34 em P1:15J | Registro de 10/11: distância responde ao alvo, junto com IR. Exatidão e tensões não medidas |
| TCRT5000 com módulo digital | Sensor de reflexão/presença próxima | VCC=3,3 V; GND comum; DO=GPIO35 em P1:14J; AO sem ligação | Registro de 10/11: alterna DETECTADO/LIVRE ao mover cartão; sem novo ensaio |
| R1=1 kΩ, R2=1 kΩ, R3=300 Ω | Condicionamento passivo do ECHO | R1 P2:8C–12C; R2 P2:12D–16D; R3 P2:16E–20E; P2:20A→GND | Montagem relatada; valores nominais do registro, sem medição nesta tarefa |
| Duas protoboards e jumpers | Interconexão e distribuição de alimentação | P1 positivo em 5 V por P1:1J; P2 positivo em 3,3 V por P1:19J; GND de P1:6J interliga os negativos | Não unir os dois trilhos positivos; nenhuma mudança física nesta preparação |
| USB | Alimentação e transporte serial | UART0/USB a 115.200 baud; porta registrada COM3 | Caminho existente; porta não acessada nesta tarefa |

Não há LCD, potenciômetro, LED RGB, botão, motor, relé ou outro atuador externo confirmado na montagem vigente. LCD e potenciômetro aparecem no histórico/código e não devem entrar como hardware em uso no relatório. A saída visual e sonora do notebook é software, não um atuador externo ligado aos GPIOs.

## Ligações do divisor e níveis

```text
HC-SR04 ECHO ── R1 1 kΩ ──●── R2 1 kΩ ── R3 300 Ω ── GND
                          │
                          └── GPIO34 da ESP32
```

O cálculo ideal é `5 × (1000 + 300) / (1000 + 1000 + 300) = 2,826... V`. **2,83 V é previsão nominal, não valor medido.** Não há multímetro disponível ao usuário. O ECHO de 5 V permanece condicionado pelo divisor; o desenho não propõe mudança de ligação. O TCRT5000 permanece em 3,3 V. O LCD está fora e não recebe SDA/SCL em 5 V direto.

## Esquemático vigente e a foto que falta

- [Figura 1 em SVG](figuras/figura-1-circuito-atual.svg) e [PNG](figuras/figura-1-circuito-atual.png): esquema técnico preparado a partir da netlist vigente, com fonte e limites visíveis.
- `hardware/wokwi/montagem_atual/diagram.json`: memória vigente da protoboard, com ressalvas. O TCRT é representado por uma peça LDR; a ESP32 virtual aparece separada e **não tem fios `esp:*` no JSON**. As ligações terminam em furos P1, cujo mapeamento físico consta na documentação. Não é prova de simulação funcional de firmware no Wokwi.
- `hardware/netlist/motionpet_atual_sem_lcd.json`: inventário de 13 fios, três resistores e GPIOs 5/34/35; sem LCD.
- `hardware/out/esquematico_estagio*.png`, `montagem_final_i2c.png` e `hardware/guia_montagem_final.html`: desenhos históricos com outros perfis; **não usar como foto ou esquema vigente**.
- Nenhuma foto física foi encontrada em `docs/`, `hardware/` ou `.claude/` na busca pelos formatos JPG/JPEG/WebP; os PNGs identificados em `hardware/out/` são desenhos gerados. Isso não prova que não exista uma foto em telefone ou fora do projeto.

A Figura 2 precisa ser uma fotografia real feita pelo grupo. Preferir vista superior bem iluminada, mostrando ESP32, os dois sensores, divisor e ambas as protoboards. Uma foto permite documentar disposição; não comprova tensão, precisão ou funcionamento. Não é necessário alterar a montagem para fotografá-la.

## Firmware compilado e FreeRTOS

| Tarefa de aplicação | Prioridade | Pilha solicitada | Operação |
|---|---:|---:|---|
| `TaskSensorAcquire` | 4 | 3.072 B | Aquisição periódica, 70 ms padrão (configurável 50–500 ms); ultrassom com timeout 25 ms; leitura IR; entrega a filas |
| `TaskGestureInfer` | 3 | 4.096 B | Espera a fila de sensores; filtro causal, janela de 10, 11 features, TinyML e estabilização |
| `TaskPetDomain` | 2 | 4.096 B | Estado legado do pet, comandos e persistência NVS limitada por intervalo |
| `TaskSerialComm` | 2 | 4.096 B | Proprietária da serial; parser e emissões JSON Lines v1; diagnóstico |
| `TaskLcdDisplay` | 1 | 3.072 B | Código histórico de exibição, ainda compilado apesar de não haver LCD físico |

As cinco tarefas usam `xTaskCreatePinnedToCore(..., APP_CPU_NUM)`. A sincronização usa mutex e filas FreeRTOS. **As filas e tarefas são criadas com APIs de alocação dinâmica na inicialização** (`xQueueCreate`, `xTaskCreatePinnedToCore`); não sustentar a expressão “filas estáticas FreeRTOS” de documentos antigos como se fossem `xQueueCreateStatic`. Buffers e lógica crítica têm tratamento próprio de alocação; isso é diferente de heap zero para todo o firmware. Não foi realizada auditoria temporal do escalonador na placa.

Arquivos: `firmware/main/main.cpp`, `firmware/main/pinout_config.h`, `firmware/main/telemetry_metrics.h`, `firmware/sensors/`, `firmware/gestures/`, `firmware/communication/`, `firmware/pet/`, `firmware/platformio.ini`.

O build observou Arduino-ESP32 2.0.17 e ESP-IDF 4.4.7, ambiente `esp32dev`, linguagem C++17. A versão de aplicação declarada em `pinout_config.h` é `0.5.0-cycle5`. O firmware atual conserva USB e domínio legado. Nenhuma biblioteca ou rotina de Wi-Fi/MQTT foi acrescentada.

## Memória e desempenho que podem constar como evidência

| Medida | Valor / fonte | O que não significa |
|---|---|---|
| RAM estática do binário | 24.668 de 327.680 B; 7,5%, log PlatformIO atual | Não inclui toda a memória dinâmica futura de Wi-Fi, filas, stacks e conexões |
| Flash do binário | 322.881 de 1.310.720 B; 24,6%, log PlatformIO atual | Não é projeção do firmware com rede |
| Tempo de build | 15,68 s nesta execução | Não é latência de sensor ou inferência |
| Período de aquisição | 70 ms configurado, cerca de 14,3 Hz por cálculo | Frequência efetiva depende da execução; não medida fisicamente nesta rodada |
| Tempo de aquisição/inferência, heap mínimo e pilhas | Instrumentação existente em `DIAG` | Não houve consulta `DIAG` nesta preparação; sem valores físicos novos |
| Modelo embarcado | TinyML `mlp_compact`, origem sintética / `AWAITING_REAL_DATA` | Compilação e paridade de software não validam reconhecimento de gestos de pessoas na bancada |

## Documentação com trechos históricos

`firmware/main/README.md` ainda descreve LCD como montagem e fala em filas estáticas. `hardware/README.md` ainda remete a desenho anterior e à retirada de cabos do LCD como pendente. `README.md`, `docs/motionlab_arquitetura.md` e `docs/motionlab_fase_c.md` contêm estados de etapas anteriores (por exemplo integração visual pendente). Para o checkpoint, usar o código atual, as evidências identificadas neste pacote e os registros mais recentes, sem tratar essas descrições antigas como nova medição. Os arquivos existentes foram preservados, sem reescrita nesta preparação.
