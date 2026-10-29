# Arquitetura de Firmware e Tarefas FreeRTOS — MotionPet

Este documento descreve a topologia multitarefa preemptiva projetada para o firmware do ESP-WROOM-32, estruturada para implementação no **Ciclo 3**, em conformidade com o **ADR-01**.

---

## 1. Topologia de Tarefas e Alocação de Núcleos (Dual-Core)

O processador ESP32 conta com dois núcleos Xtensa LX6 de 32 bits operando a 240 MHz. Para garantir temporização rígida nos sensores e evitar que operações de I/O bloqueiem a inferência ou o ciclo biológico do pet, as tarefas são distribuídas entre os dois núcleos:

```
+-----------------------------------------------------------------------------------+
|                                   ESP32 Dual Core                                 |
|                                                                                   |
|  [ CORE 0 - Protocolo & Display ]             [ CORE 1 - Tempo Real & Domínio ]   |
|                                                                                   |
|  +-----------------------------+              +-----------------------------+     |
|  | TaskDisplayAndSerial        |              | TaskSensorAcquire           |     |
|  | - Prioridade: 1             |              | - Prioridade: 4 (Alta)      |     |
|  | - Pilha: 4096 bytes         |              | - Pilha: 3072 bytes         |     |
|  | - Refresh LCD (5 Hz)        |              | - Amostragem HC-SR04/IR     |     |
|  | - Tx/Rx JSON Lines v1       |              | - Período: 50 ms (20 Hz)    |     |
|  +--------------^--------------+              +--------------+--------------+     |
|                 |                                            |                    |
|        xQueueSend (Serial Tx)                         q_sensor_frames             |
|                 |                                            v                    |
|  +--------------+--------------+              +-----------------------------+     |
|  | q_pet_commands (Serial Rx)  |              | TaskGestureInfer            |     |
|  +--------------+--------------+              | - Prioridade: 3             |     |
|                 |                             | - Pilha: 4096 bytes         |     |
|                 |                             | - Extração Features/TinyML  |     |
|                 |                             | - Período: 50 ms            |     |
|                 |                             +--------------+--------------+     |
|                 |                                            |                    |
|                 |                                     q_gesture_events            |
|                 +---------------------+                      |                    |
|                                       v                      v                    |
|                               +------------------------------+                    |
|                               | TaskPetDomain                                     |
|                               | - Prioridade: 2                                   |
|                               | - Pilha: 4096 bytes                               |
|                               | - Ciclo Biológico (1 Hz)                          |
|                               | - Máquina de Estados Autoritativa                 |
|                               | - Mutex: xPetStateMutex                           |
|                               +---------------------------------------------------+
+-----------------------------------------------------------------------------------+
```

---

## 2. Detalhamento das Tarefas FreeRTOS

### 2.1 `TaskSensorAcquire` (Núcleo 1)
- **Responsabilidade**: Aquisição física em tempo real de todos os periféricos de entrada.
  1. Gera pulso de $10\,\mu\text{s}$ no pino `TRIG` do HC-SR04.
  2. Mede a duração em microssegundos do pino `ECHO` usando `pulseIn` ou temporizador de interrupção com timeout seguro de $25\,\text{ms}$.
  3. Realiza leitura digital do sensor TCRT5000 (`GPIO35`).
  4. Realiza conversão A/D de 12 bits do potenciômetro (`GPIO36` no ADC1).
  5. Monta a estrutura `SensorRawFrame`.
- **Período**: $50\,\text{ms}$ ($20\,\text{Hz}$ fixos), respeitando o tempo de decaimento acústico do HC-SR04.
- **Prioridade**: **4 (Alta)** — deve interromper tarefas de domínio para manter precisão de amostragem.
- **Comunicação**: Enfileira o quadro na fila `q_sensor_frames` (tamanho: 4 quadros).

### 2.2 `TaskGestureInfer` (Núcleo 1)
- **Responsabilidade**: Classificação temporal de gestos.
  1. Consome quadros da fila `q_sensor_frames`.
  2. Alimenta buffer circular de janelamento deslizante ($12$ amostras $\approx 600\,\text{ms}$).
  3. Extrai o vetor de 8 características (`d_mean`, `d_std`, `v_mean`, `v_peak`, etc.).
  4. Executa inferência via baseline de regras ou modelo TinyML compilado em C++.
  5. Aplica filtro de histerese para evitar múltiplos disparos do mesmo gesto.
- **Período**: Acionada pela chegada de cada quadro de sensor ($20\,\text{Hz}$).
- **Prioridade**: **3 (Média-Alta)**.
- **Comunicação**: Despacha `GestureEvent` para a fila `q_gesture_events`.

### 2.3 `TaskPetDomain` (Núcleo 1)
- **Responsabilidade**: Motor de regras de negócio e biologia do pet virtual (Fonte Autoritativa da Verdade).
  1. Mantém a estrutura global `PetStateSnapshot`.
  2. A cada $1000\,\text{ms}$ ($1\,\text{Hz}$), invoca `pet_tick(&pet)` (decaimento de fome, energia, humor).
  3. Processa comandos recebidos da fila `q_pet_commands` (alimentar, brincar, dormir).
  4. Reage a eventos da fila `q_gesture_events` (ex: `APPROACH` $\rightarrow$ alimentação/carinho).
  5. Avalia evolução de estágio (`EGG` $\rightarrow$ `CHICK` $\rightarrow$ `CYBER_ROOSTER`).
  6. Atualiza o buffer de caracteres do LCD com o status corrente.
- **Período**: $1000\,\text{ms}$ para tick biológico + desbloqueio imediato em filas de eventos.
- **Prioridade**: **2 (Média)**.
- **Sincronização**: Protege leitura e escrita do estado pelo semáforo mutex `xPetStateMutex`.

### 2.4 `TaskDisplayAndSerial` (Núcleo 0)
- **Responsabilidade**: Gerenciamento de periféricos lentos de I/O e comunicação externa.
  1. **Display LCD 2004A**: Atualiza as 4 linhas de 20 caracteres via barramento de 4 bits em intervalos de $200\,\text{ms}$ ($5\,\text{Hz}$).
  2. **Serial Rx**: Faz varredura não-bloqueante da porta Serial USB. Ao encontrar terminador `\n`, decodifica comando JSON com `jsonl_parse_pet_command` e envia para `q_pet_commands`.
  3. **Serial Tx**: Transmite quadros `sensor_frame` ($10\,\text{Hz}$), `pet_state` ($1\,\text{Hz}$) e `gesture_event` (sob demanda) formatados em JSON Lines v1.
- **Período**: Loop contínuo com pausa cooperativa `vTaskDelay(pdMS_TO_TICKS(10))`.
- **Prioridade**: **1 (Baixa)** — impede que latências de I/O serial ou escrita lenta do LCD afetem a amostragem de sensores.

---

## 3. Gestão de Memória e Filas FreeRTOS

Para assegurar estabilidade contínua sem fragmentação de memória (*heap fragmentation*):
1. Todas as filas (`q_sensor_frames`, `q_gesture_events`, `q_pet_commands`) utilizam alocação estática `xQueueCreateStatic` ou são alocadas uma única vez na inicialização no `setup()`.
2. Buffers de formatação JSON (`char buffer[JSONL_LINE_BUFFER_SIZE]`) são alocados nas pilhas locais das tarefas ou em memória estática global (`.bss`), nunca via `malloc` ou `String` dinâmica do Arduino.
