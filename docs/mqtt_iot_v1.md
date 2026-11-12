# MotionLab — contrato MQTT IoT v1 (Fase E)

Estado em 11/11/2026: implementado e verificável em software; rádio/sensores na nova
arquitetura ainda não validados fisicamente. Este contrato estende a Fase C sem
alterar seus tópicos de sessões nem as rotas `/api/ml/*`.

## Transportes e unidade de aquisição

`TaskSensorAcquire` lê uma vez o mesmo `SensorRawFrame` que alimenta USB, TinyML e
a fila IoT. Reconectar Wi-Fi/MQTT não faz parte dessa tarefa. O protocolo USB
JSON Lines v1, seus tipos, sequência de envelopes e sentinela de distância inválida
continuam vigentes. Sequência USB identifica envelopes; `sample_idx` IoT identifica
aquisições. Não comparar os dois contadores como se fossem a mesma coisa.

O tópico anterior `motionlab/v1/sessions/{demo,synthetic,real}` transporta uma sessão
rotulada completa, com 10..10.000 registros, até 4 MiB, IDs acadêmicos e timestamp
civil. Exigi-lo na ESP32 implicaria acumular sessões no heap e inventar participante,
rótulo ou hora UTC. A extensão transporta **uma amostra sem rótulo** por publicação:

`motionlab/v1/devices/<device_id>/samples`

Publicação QoS 1, `retain=false`, até 1.024 bytes. Firmware e consumidor usam MQTT
3.1.1. O usuário do broker deve ser o `device_id`, com acesso somente ao seu tópico.

```json
{"schema_version":1,"kind":"sample","device_id":"esp32_112233aabbcc","session_id":"boot_001122","sample_idx":0,"ts_ms":1000,"data_origin":"real_hardware","distance_cm":40.00,"valid_ultrasonic":true,"ir_detected":false,"valid_ir":true,"captured_at_iso":null,"clock_source":"monotonic_boot","physical_validation":"pending","dropped_total":0}
```

| Campo obrigatório | Semântica |
|---|---|
| `schema_version`, `kind` | Inteiro `1`, string `sample`; não é envelope de sessão acadêmica |
| `device_id` | Firmware: `esp32_` + MAC STA completa, 12 hex minúsculos, estável entre boots |
| `session_id` | `boot_` + 128 bits pseudoaleatórios por inicialização; não é token de segurança nem participante |
| `sample_idx` | Contador de aquisição por boot, inicia em zero; avança mesmo quando a fila descarta |
| `ts_ms` | Tempo monotônico da aquisição desde boot, estendido para 64 bits a partir do relógio da ESP32 |
| `data_origin` | Firmware declara `real_hardware`; testes/simuladores podem declarar `synthetic_simulator` |
| `distance_cm`, `valid_ultrasonic` | Leitura válida finita de 2..400 cm; inválida usa `-1` e `false`, como USB v1 |
| `ir_detected`, `valid_ir` | Booleanos; IR desabilitado ou HAL indisponível usa validade falsa; não inferir repouso disso |
| `captured_at_iso`, `clock_source` | `null`, `monotonic_boot`; não inventar UTC para uma leitura acumulada offline |
| `physical_validation` | Sempre `pending`; o dispositivo não pode atestar sua própria validação física |
| `dropped_total` | Contador acumulado de descartes da fila no instante de enfileirar; imutável nos retries |

O backend aceita IDs ASCII `[A-Za-z0-9_-]`, de 1 a 96 caracteres, e inteiros de
0 a `2^63-1` para compatibilidade com SQLite. O firmware usa contadores de 64 bits;
o teto do consumidor está muito além da vida útil operacional à taxa atual.
Campos desconhecidos não são incorporados ao registro canônico. O backend grava
`received_at_iso` UTC do notebook separadamente; é hora de recepção, não aquisição.

## Integridade, entrega e memória

Chave primária: `(device_id, session_id, sample_idx)`. Conteúdo normalizado idêntico
retorna `duplicate`; conteúdo diferente para a mesma chave é rejeitado. O SHA-256
da amostra consta do recibo local. A recepção fora de ordem é aceita se `ts_ms`
for estritamente crescente e `dropped_total` não decrescente **na ordem da sequência**.
Não há comparação de relógios de boots/dispositivos distintos.

O firmware mantém fila circular estática de **32 amostras**, com política **descartar
a nova amostra** quando cheia. A cabeça permanece imutável até o PUBACK; contadores
e saltos de sequência tornam a perda observável. A 70 ms, a fila guarda cerca de
2,24 s de aquisições; ela não é armazenamento durável nem recuperação de interrupções
longas. Reiniciar a placa perde o conteúdo RAM e inicia outra sessão.

Só existe uma publicação QoS 1 pendente. O buffer JSON tem 1.024 bytes; os buffers
MQTT de entrada/saída têm 1.024 bytes cada. Timeout de conexão/PUBACK: 10 s; rede do
cliente: 2 s; backoff exponencial separado para Wi-Fi e broker: 1..60 s. Falha ou
timeout destrói o cliente e sua única possível entrada no outbox antes de tentar
novamente a mesma cabeça. Não existe crescimento ilimitado de filas de publicação.
Wi-Fi/TLS/IDF usam heap interno: o seu pico real precisa ser medido na placa.

### Cadência experimental da task de rede

Em um ensaio físico a 70 ms com TLS, a aquisição produziu amostras mais rápido do
que o caminho MQTT as confirmou; a fila encheu e houve descartes. Como a task também
esperava 20 ms após cada ação (inclusive entre processar um PUBACK e tentar a próxima
amostra), o firmware passou a esperar **1 ms online** e 20 ms nos demais estados,
sempre cedendo pelo menos um tick. A configuração atual de 1.000 ticks/s permite a
espera de 1 ms. A mudança preserva a fila limitada, QoS 1 e uma única publicação em
voo; aumenta a frequência de despertar da task e pode aumentar uso de CPU/energia.
O modem-sleep Wi-Fi também foi desativado para reduzir a latência de recepção dos
PUBACKs, com possível aumento do consumo de energia da ESP32.

Um teste do núcleo C++ em host simulou aquisição a 70 ms e confirmou ordem e apenas
uma publicação pendente: com PUBACK fixo em 40 ms não houve descarte; com 100 ms,
a fila limitada eventualmente descartou. São cenários simulados, sem Wi-Fi, broker,
FreeRTOS ou TLS: não medem desempenho físico nem garantem entrega sem perdas. Um
[ensaio físico posterior](motionlab_bancada_iot_2026-11-12.md) combinou as duas
alterações: a 70 ms, 432 amostras chegaram em 30 segundos sem novos descartes nessa
janela. O consumo de CPU/energia e o comportamento em interrupções longas ainda
precisam ser medidos; a fila limitada pode causar perdas.

QoS 1 permite duplicatas. PUBACK da ESP32 confirma recepção pelo **broker**, não
COMMIT no notebook. O consumidor usa sessão MQTT persistente/client ID estável,
ACK manual somente depois do COMMIT SQLite (`WAL`, `synchronous=FULL`). Erros de disco
escapam sem ACK, para recuperação com reinício do consumidor; mensagens inválidas
são rejeitadas com log e ACK, evitando retry infinito. Iniciar o consumidor e
confirmar SUBACK antes de habilitar publicações. Interrupções que excedam limites
de fila do dispositivo/broker podem causar perda; QoS 1 não garante aquisição sem
perdas nem durabilidade contra queda de energia do broker antes de seu autosave.

## Persistência, origem e inferência

`--allow-devices` habilita o novo tópico; `--allow-real` adicional permite armazenar
declarações `real_hardware`. O padrão antigo continua só com sessões demo/sintéticas.
Telemetria é persistida em SQLite isolado, nunca automaticamente em
`data/raw/{real,synthetic,demo}`. Origem declarada não é identidade física verificada:
um host de testes também pode publicar esse payload. Autenticação e ACL restringem
quem publica, mas não substituem o procedimento de bancada e seu registro.

`--watch-iot-db` na API ativa a leitura para inferência, com no máximo 64 sessões e
512 amostras por sessão. Reordena pelo índice; uma lacuna interrompe a janela, sem
interpolação. Reutiliza `CausalSignalFilter`, as 11 features canônicas e o modelo
explicitamente configurado. Cada snapshot reinicia o filtro no contexto limitado
de até 512 amostras; isso não promete equivalência bit a bit com um filtro rodando
indefinidamente. A janela final ancora no último timestamp, inclusive com contagem
ímpar. IR inválido na janela suspende a inferência até haver janela válida.

Previsões usam `scope=live_iot_unlabelled`, `processing_version=2`, IDs/hash,
`physical_validation=pending`. O endpoint `/v1/predictions` e o proxy
`/api/ml/predictions` mantêm seu envelope e os campos anteriores. `input_origin=real`
significa origem **declarada** do input; não significa validação física. Nenhum
rótulo, participante, score de avaliação ou inclusão em holdout é criado. Exportar
para corpus acadêmico exige outra coleta/procedimento explícito com rotulagem e
separação de grupos; esse passo não é automatizado pela Fase E.

Referências de API: [ESP-MQTT do ESP-IDF 4.4.7](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/protocols/mqtt.html),
[Paho Python 2.x](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[configuração Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html).
