# Arquitetura de Firmware e Tarefas FreeRTOS — MotionPet (Ciclo 3)

Este documento descreve a arquitetura multitarefa FreeRTOS efetivamente implementada em `firmware/main/main.cpp` para o `ESP-WROOM-32` (`ESP-IDF v4.4.7` / `framework-arduinoespressif32 @ 2.0.17`).

## Extensão IoT da Fase E (somente software, 11/11/2026)

`communication/iot_core.*` implementa a fila fixa de 32 amostras, serialização e máquina de estados testáveis em host. `communication/iot_transport.*` adapta esse núcleo ao Wi-Fi STA e ESP-MQTT já fornecidos pelo SDK; não há dependência externa nova. A aquisição mantém TinyML e USB e apenas copia a mesma leitura para a fila IoT, sem esperar pela rede. O timestamp de aquisição é estendido para 64 bits, incluindo rollover de 32 bits do protocolo USB. O estado de habilitação do IR é aplicado uma vez por ciclo; MQTT distingue IR desabilitado por `valid_ir=false`.

A sexta tarefa `MotionIoT` tem prioridade 1, stack estática de **4096 bytes** e período de 20 ms. A tarefa interna ESP-MQTT usa stack de 6144 bytes e buffers RX/TX de 1024 bytes; o SDK aloca heap limitado para cliente, TCP/Wi-Fi/TLS e uma publicação QoS 1 pendente. Há no máximo uma mensagem no outbox: ela só sai da fila da aplicação após PUBACK. Falha ou timeout destrói o cliente antes de repetir a mesma identidade/conteúdo. PUBACK confirma recepção pelo broker, não gravação pelo consumidor. A fila usa **descarte da amostra nova** quando cheia, preservando a mensagem pendente; sequência avança mesmo no descarte e `dropped_total` é capturado de forma imutável por mensagem. Reiniciar/desenergizar perde o buffer volátil.

Wi-Fi e broker têm backoff de 1–60 s e timeout de 10 s, executados somente na tarefa de rede. TLS valida CA e hostname; `clock_wait` aguarda hora civil SNTP válida antes do handshake, sem alterar os timestamps monotônicos do payload. TCP sem TLS exige opt-in local explícito. Sem SSID, host, senha MQTT e configuração de segurança, a rede permanece `disabled` e USB/TinyML continuam disponíveis. Identidade e sessão aparecem mesmo nesse estado.

Copiar `communication/iot_config.example.h` para `communication/iot_config.local.h` somente no procedimento físico posterior, preenchendo valores privados fora do Git. O ambiente `esp32dev-iot-example` compila o caminho configurado TLS usando apenas placeholders e ignora o header local. Comandos de build não gravam nem acessam a placa:

```powershell
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32dev
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32dev-iot-example
```

`IOT_DIAG` (curto ou `pet_command` JSONL) devolve estado, IDs, ocupação, descartes, PUBACKs, reconexões, erros de publicação e high-water mark em um `ack` v1. Não imprime credenciais nem texto fora do JSONL. O `DIAG` original é preservado. Contrato completo e procedimento físico: `docs/motionlab_fase_e.md` (raiz do projeto). Build e mocks não são validação física de RF, sensores, heap ou latência.

Montagem atual: [guia integrado I²C](../../docs/bench_assembly_guide.md). `main.cpp` seleciona o HAL PCF8574; GPIO21=SDA e GPIO22=SCL, backpack em 3V3 sem conversor. O modo de quatro bits existe entre o expansor e o HD44780, não como seis fios da ESP32 ao LCD.

---

## 1. Topologia de 5 Tarefas Independentes em `APP_CPU_NUM`

Para evitar contenção de cache multicore sem benefício mensurável e manter sincronização determinística, todas as **5 tarefas de aplicação** operam fixadas em `APP_CPU_NUM` (Core 1), comunicando-se exclusivamente por **filas estáticas FreeRTOS** e por um semáforo mutex de curta duração (`g_state_mutex`), sem alocação dinâmica de heap nos laços de tempo real:

| Tarefa FreeRTOS | Prioridade | Stack (Bytes) | Período / Gatilho | Responsabilidade Principal |
| :--- | :---: | :---: | :--- | :--- |
| **`TaskSensorAcquire`** | `4` (Alta) | `3072 B` | `vTaskDelayUntil` (`70 ms` padrão; `50..500 ms`) | Leitura física do HC-SR04 (timeout `25 ms`), TCRT5000 (`DO` + `AO` opcional em ADC1) e potenciômetro (`ADC1_CH0`). Alimenta `g_q_sensor_infer` e, quando ativa, `g_q_sensor_tx`. |
| **`TaskGestureInfer`** | `3` (Média-Alta) | `4096 B` | Bloqueio em `g_q_sensor_infer` (`portMAX_DELAY`) | Filtro causal (`tinyml_filter_step`), buffer circular (`W=10`), extração das 11 features canônicas, inferência TinyML (`tinyml_infer_proba`) e estabilizador temporal com cooldown. |
| **`TaskPetDomain`** | `2` (Média) | `4096 B` | `1000 ms` (`1 Hz`) + bloqueio em `g_q_cmd_pet` | Máquina de estados autoritativa do Pet (`pet_tick`, comandos, gestos, evolução) e persistência NVS com CRC32, skip sem mudança e throttle de `30 s`. |
| **`TaskSerialComm`** | `2` (Média) | `4096 B` | Varredura cooperativa (`5 ms`) | Único proprietário da `UART0` (`115200 baud`). Fluxo 100% puro JSON Lines v1 (`CORE_DEBUG_LEVEL=0`), parser Rx tolerante a falhas e telemetria `DIAG`. |
| **`TaskLcdDisplay`** | `1` (Baixa) | `3072 B` | `vTaskDelayUntil` (`200 ms` / `5 Hz`) | Formatação 20×4 (`lcd_format_pet_frame`), animações e atualização diferencial via HAL I²C PCF8574 a 100 kHz. |

---

## 2. Filas e Instrumentação em Tempo Real

- **Filas FreeRTOS:**
  - `g_q_sensor_infer` (`8 × sizeof(SensorRawFrame)`): `TaskSensorAcquire -> TaskGestureInfer`
  - `g_q_sensor_tx` (`8 × sizeof(SensorRawFrame)`): `TaskSensorAcquire -> TaskSerialComm`
  - `g_q_gesture_pet` (`6 × sizeof(GestureEvent)`): `TaskGestureInfer / Serial Rx -> TaskPetDomain`
  - `g_q_gesture_tx` (`6 × sizeof(GestureEvent)`): `TaskGestureInfer -> TaskSerialComm`
  - `g_q_cmd_pet` (`8 × sizeof(PetCmdQueueItem)`): `TaskSerialComm -> TaskPetDomain`
  - `g_q_pet_reply_tx` (`8 × sizeof(PetReplyQueueItem)`): `TaskPetDomain -> TaskSerialComm`
- **Telemetria (`FirmwareRuntimeMetrics` via comando `DIAG`):**
  - `acq_us` / `max_acq_us` (duração da aquisição física)
  - `inf_us` / `max_inf_us` (latência de filtragem + features + inferência TinyML)
  - `q_si`, `q_tx` (ocupação instantânea das filas)
  - `hwm_s`, `hwm_g`, `hwm_p`, `hwm_c`, `hwm_l` (stack high-water mark em bytes livres de cada task)
  - `heap`, `min_heap` (memória livre atual e mínima histórica)
  - `drop_si`, `drop_tx`, `drop_g`, `to_us`, `nvs_w` (contadores de perda de amostras, timeouts ultrassônicos e gravações NVS)
  - `mdl`, `exp` (identificação explícita do modelo TinyML embarcado e status experimental `AWAITING_REAL_DATA`)
