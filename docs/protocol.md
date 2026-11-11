# Especificação do Protocolo Serial JSON Lines v1 — MotionPet

Este documento define a especificação formal do **Protocolo Serial JSON Lines v1** utilizado para a comunicação bidirecional entre o microcontrolador ESP32 (ou o simulador de bancada) e o computador hospedeiro (Terminal ASCII e ferramentas de telemetria).

---

## 1. Princípios Gerais e Formato de Enquadramento

1. **Delimitação por Linha (JSON Lines / ndjson)**:
   - Cada mensagem é um objeto JSON UTF-8 completo e serializado em uma única linha terminada obrigatoriamente pelo caractere de quebra de linha `\n` (ASCII 0x0A).
   - O caractere de retorno de carro `\r` (ASCII 0x0D) é opcional na transmissão e deve ser ignorado pelo receptor.
2. **Semântica do Envelope Padrão**:
   - Toda mensagem válida contém os 5 campos do envelope raiz:
     - `v` (*integer*): versão do protocolo (atualmente fixado em `1`).
     - `seq` (*integer*): número de sequência monotônico crescente gerado pelo transmissor (0 a $2^{31}-1$).
     - `type` (*string*): identificador do tipo de mensagem.
     - `ts_ms` (*integer*): timestamp em milissegundos a partir da inicialização da máquina emissora (`millis()`).
     - `data` (*object*): carga útil (*payload*) estruturada específica do tipo de mensagem.

### 1.1 Exemplo do Envelope Canônico

```json
{"v": 1, "seq": 104, "type": "sensor_frame", "ts_ms": 15420, "data": {"distance_cm": 18.4, "ir_detected": false, "pot_norm": 0.42, "valid_ultrasonic": true}}
```

---

## 2. Tipos de Mensagem e Esquemas de Dados

### 2.1 `sensor_frame` (ESP32 $\rightarrow$ Host)
Transmite a leitura bruta e pré-filtrada dos sensores físicos ou simulados.
- **Frequência Típica**: 10 Hz a 20 Hz (intervalo de 50 ms a 100 ms).
- **Campos de `data`**:
  - `distance_cm` (*number | null*): Distância estimada pelo ultrassom em centímetros (faixa válida: $2.0$ a $400.0\text{ cm}$). É `null` caso ocorra *timeout* de eco ou reflexão espúria.
  - `ir_detected` (*boolean*): `true` quando o sensor óptico reflexivo TCRT5000 detecta proximidade imediata ($< 2\text{ cm}$).
  - `pot_norm` (*number*): Valor do potenciômetro normalizado de $0.0$ a $1.0$ (mapeado de 12 bits: $0$ a $4095$ no ADC1).
  - `valid_ultrasonic` (*boolean*): `true` se o pulso de eco foi lido dentro da janela de tempo válida (115 µs a 25 ms).
  - `echo_duration_us` (*integer*, opcional): duração bruta do pulso ECHO, em microssegundos, quando o firmware a disponibiliza. Um pulso pode ser não zero e ainda assim ser inválido. Zero agrupa situações como ECHO preso em nível alto, ausência de subida ou ausência de descida; não distingue essas causas.
  - `acquire_duration_us` (*integer*, opcional): tempo total da aquisição dos sensores desta amostra, em microssegundos. Esses dois campos são diagnósticos digitais: **não medem tensão** nem comprovam a fiação. Clientes e simuladores anteriores podem omiti-los; os clientes não devem depender de sua presença.

```json
{
  "v": 1,
  "seq": 450,
  "type": "sensor_frame",
  "ts_ms": 22500,
  "data": {
    "distance_cm": 24.5,
    "ir_detected": false,
    "pot_norm": 0.50,
    "valid_ultrasonic": true
  }
}
```

---

### 2.2 `gesture_event` (ESP32 / Simulação $\rightarrow$ Host / Pet Domain)
Notifica o reconhecimento de um padrão gestual classificado.
- **Gatilho**: Disparado na conclusão de uma janela de inferência temporal de gestos.
- **Campos de `data`**:
  - `gesture` (*string*): Identificador do gesto reconhecido:
    - `"APPROACH"`: Aproximação rápida da mão em direção ao sensor.
    - `"RETREAT"`: Afastamento deliberado da mão.
    - `"HOLD"`: Mão estática mantida na zona de foco ($10\text{--}25\text{ cm}$).
    - `"NEUTRAL"`: Ausência de movimento ou ausência de alvo.
    - `"IMPULSE"`: Movimento balístico rápido de vai-e-vem (para mini-jogos).
    - `"DOUBLE"`: Dupla aproximação em janela curta (gesto de confirmação/seleção).
  - `confidence` (*number*): Grau de certeza da predição entre $0.0$ e $1.0$.
  - `source` (*string*): Origem do classificador (`"sim_keyboard"`, `"sim_sensor"`, `"rule_baseline"`, `"tinyml"`).
  - `window_ms` (*integer*): Duração da janela temporal analisada em milissegundos (ex: $600\text{ ms}$).

```json
{
  "v": 1,
  "seq": 451,
  "type": "gesture_event",
  "ts_ms": 22550,
  "data": {
    "gesture": "APPROACH",
    "confidence": 0.94,
    "source": "tinyml",
    "window_ms": 600
  }
}
```

---

### 2.3 `pet_command` (Host $\rightarrow$ ESP32 ou Teclado $\rightarrow$ Motor)
Comandos manuais ou gerados por interação do usuário no terminal para alterar o estado do pet.
- **Campos de `data`**:
  - `command` (*string*):
    - `"FEED"`: Alimentar o pet (reduz fome, concede XP).
    - `"PLAY"`: Brincar com o pet (aumenta felicidade, gasta energia).
    - `"REST"`: Colocar o pet para dormir ou acordá-lo (recupera energia).
    - `"HEAL"`: Tratar a saúde do pet.
    - `"INTERACT"`: Carinho / interação física genérica.
    - `"SAVE"`: Solicitar persistência do pet na flash/disco.
    - `"LOAD"`: Solicitar recarga do último estado persistido.
    - `"RESET"`: Reiniciar o pet para um novo ovo (`EGG`).
    - `"SWITCH_MODE"`: Alternar entre `MotionPet`, `Pet Launch`, `Air Music`, `Air Slides`.
    - `"TICK"`: Forçar avanço de um ciclo temporal de simulação.
  - `payload` (*object*): Parâmetros adicionais opcionais (ex: `{"mode": "air_music"}`).

Para Pet Launch, `PLAY` com `payload.minigame = "PET_LAUNCH"` aceita `action = "MATCH_RESULT"` com `distance_m`, `score`, `coins_earned` e `xp_earned`, ou `action = "UNLOCK_UPGRADE"` com `upgrade_id` e `cost`. O ESP32 valida e aplica o resultado ou a compra; compras inválidas, repetidas ou sem saldo são rejeitadas. O estado publicado inclui moedas, recordes, total de lançamentos e melhorias. O recebimento do comando não substitui a confirmação de persistência após reinicialização física.

```json
{
  "v": 1,
  "seq": 12,
  "type": "pet_command",
  "ts_ms": 3500,
  "data": {
    "command": "FEED",
    "payload": {
      "food_type": "seed"
    }
  }
}
```

---

### 2.4 `pet_state` (ESP32 $\rightarrow$ Host / Display)
Snapshot completo e determinístico do estado do Pet. É a carga útil enviada pela fonte autoritativa da verdade.
- **Frequência Típica**: 1 Hz a 2 Hz (ou imediatamente após cada comando/transição de humor).
- **Campos de `data`**:
  - `name` (*string*): Nome de registro do pet (ex: `"Chantecler"`).
  - `hunger` (*number*): Nível de fome de $0.0$ (totalmente saciado) a $100.0$ (faminto crítico).
  - `happiness` (*number*): Nível de felicidade de $0.0$ a $100.0$.
  - `energy` (*number*): Nível de energia vital de $0.0$ a $100.0$.
  - `health` (*number*): Nível de integridade física/saúde de $0.0$ a $100.0$.
  - `xp` (*integer*): Pontos de experiência acumulados ($0$ a $\infty$).
  - `level` (*integer*): Nível atual ($1, 2, 3\dots$).
  - `stage` (*string*): Estágio de evolução (`"EGG"`, `"CHICK"`, `"CYBER_ROOSTER"`).
  - `mood` (*string*): Estado emocional derivado (`"ECSTATIC"`, `"HAPPY"`, `"CONTENT"`, `"HUNGRY"`, `"TIRED"`, `"SAD"`, `"SICK"`, `"SLEEPING"`).
  - `personality` (*string*): Traço de personalidade (`"CURIOUS"`, `"PLAYFUL"`, `"FOODIE"`, `"ZEN"`).
  - `animation` (*string*): Sprite/animação em reprodução no momento (`"IDLE"`, `"EATING"`, `"PLAYING"`, `"SLEEPING"`, `"PETTING"`, `"HEALING"`, `"EVOLVING"`, `"SICK"`).
  - `is_sleeping` (*boolean*): Indica se o pet está em repouso biológico.
  - `age_ticks` (*integer*): Total de ticks de vida vividos pelo pet.

```json
{
  "v": 1,
  "seq": 880,
  "type": "pet_state",
  "ts_ms": 44000,
  "data": {
    "name": "Chantecler",
    "hunger": 25,
    "happiness": 85,
    "energy": 90,
    "health": 100,
    "xp": 340,
    "level": 3,
    "stage": "CHICK",
    "mood": "HAPPY",
    "personality": "PLAYFUL",
    "animation": "IDLE",
    "is_sleeping": false,
    "age_ticks": 440
  }
}
```

---

### 2.5 `lcd_frame` (ESP32 $\leftrightarrow$ Host / Mirror Display)
Representação exata das 4 linhas do display LCD 2004A. Usado para que o simulador ou o terminal espelhem em tela os 80 caracteres presentes no LCD físico.
- Durante `PET_LAUNCH`, o host também envia este quadro ao ESP32, até 5 vezes por segundo. O ESP32 o usa enquanto o modo estiver ativo; se os quadros pararem por 2 segundos ou o modo mudar, volta à tela local do pet. A confirmação visual do LCD físico continua necessária.
- As quatro linhas devem ter exatamente 20 caracteres ASCII imprimíveis. Quadros inválidos são rejeitados. O envio ao dispositivo não comprova, por si só, que o display recebeu ou exibiu o conteúdo.
- **Campos de `data`**:
  - `lines` (*array of strings*): Exatamente 4 strings com 20 caracteres cada. Caracteres faltantes devem ser preenchidos com espaços em branco (`' '`).

```json
{
  "v": 1,
  "seq": 881,
  "type": "lcd_frame",
  "ts_ms": 44050,
  "data": {
    "lines": [
      "Chantecler   Lv:03  ",
      "Fome:[==--] H:[====]",
      "Humor: FELIZ ^_^    ",
      "Gesto: HOLD (22cm)  "
    ]
  }
}
```

---

### 2.6 `ack` e `error` (Diagnóstico e Confirmação)
- `ack`: Confirma o recebimento e processamento com sucesso de um comando crítico.
  - `ref_seq` (*integer*): O número de sequência da mensagem confirmada.
  - `status` (*string*): `"OK"` ou mensagem de status.
- `error`: Notifica falha de decodificação de mensagem, parâmetro ilegal ou falha de hardware.
  - `code` (*string*): Código de erro padronizado (`"ERR_JSON_PARSE"`, `"ERR_UNKNOWN_CMD"`, `"ERR_SENSOR_TIMEOUT"`).
  - `message` (*string*): Descrição legível da ocorrência.

```json
{
  "v": 1,
  "seq": 13,
  "type": "ack",
  "ts_ms": 3520,
  "data": {
    "ref_seq": 12,
    "status": "OK"
  }
}
```

```json
{
  "v": 1,
  "seq": 999,
  "type": "error",
  "ts_ms": 50120,
  "data": {
    "code": "ERR_JSON_PARSE",
    "message": "Unterminated string at offset 38"
  }
}
```

---

## 3. Resiliência, Detecção de Erros e Controle de Sequência

### 3.1 Controle de Sequência (`seq`)
- Cada nó (ESP32 ou Host) mantém seu próprio contador atômico `_seq_tx`.
- O receptor inspeciona o campo `seq` de mensagens do mesmo tipo para:
  1. Detectar perda de pacotes: se $seq_{atual} - seq_{anterior} > 1$, houve descarte de linhas pela serial ou saturação de buffer.
  2. Detectar reinicialização súbita do microcontrolador: se $seq_{atual} < seq_{anterior}$, o ESP32 sofreu *brownout* ou *reboot*.

### 3.2 Tolerância a Ruído e Desserialização Robusta
- A camada de transporte lê chunks de bytes arbitrários da porta serial (`pySerial` ou buffers de hardware).
- O acumulador de buffer concatena os bytes até localizar o caractere terminador `\n`.
- Se a linha não iniciar com `{` ou não terminar com `}`, ou se `json.loads()` / `deserializeJson()` disparar exceção:
  1. A linha defeituosa é imediatamente descartada.
  2. Um contador de erros de frame é incrementado para diagnóstico.
  3. O parser permanece sincronizado para a próxima linha válida sem travar a thread de leitura.
- O parser do firmware (`jsonl_protocol.cpp`, sem alocação dinâmica) valida a linha inteira como JSON estrito (RFC 8259, profundidade máxima 8, sem lixo após o objeto) e rejeita com `ERR_JSON_PARSE` vírgulas/dois-pontos faltando ou sobrando, escapes inválidos e números malformados. Os campos do envelope (`v`, `seq`, `type`, `ts_ms`, `data`) só valem como membros diretos do objeto raiz; chave repetida no mesmo objeto invalida o campo. Campos inteiros (`v`, `seq`, `ts_ms`, `period_ms`, `score` etc.) aceitam só inteiros sem sinal, sem fração, expoente ou sufixo (`1e2`, `12abc`, `1.5`, `-1` e zeros à esquerda são rejeitados) e que caibam em 32 bits. Parâmetros de `pet_command` são lidos de `data` ou, na falta, de `data.payload`; strings maiores que o buffer de destino são rejeitadas, não truncadas.

### 3.3 Abstração Transparente de Transporte
O mesmo motor de parsing opera sobre duas implementações intercambiáveis de transporte:
- `VirtualSerialLoopback`: Fila bidirecional em memória baseada em `queue.Queue` da biblioteca padrão, utilizada para execução de testes unitários e modo simulador (Ciclo 1) sem hardware físico.
- `PySerialTransport`: Driver para portas seriais COM físicas do sistema operacional (ex: `COM3`, `/dev/ttyUSB0`) operando a 115200 baud, 8N1.
Ambos os transportes implementam os métodos idênticos `read_line(timeout_sec)` e `write_line(line_str)`.
