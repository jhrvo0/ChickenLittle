# Protocolo de Coleta do Dataset Físico Real e Pipeline TinyML — MotionPet (Ciclo 5)

> [!IMPORTANT]
> **Status Experimental Atual: `PENDING_PHYSICAL_VALIDATION` / `AWAITING_REAL_DATA`**
>
> - **Firmware de Aquisição Alvo:** `MOTIONPET_FW_VERSION = "0.5.0-cycle5"`
> - **Pinagem Canônica:** `MOTIONPET_PINOUT_STATUS = "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"` ([pinout_config.h](../firmware/main/pinout_config.h))
>
> Toda a cadeia de coleta guiada (`ml.collection`), pré-processamento estritamente causal, treinamento comparativo, avaliação por janela e por evento estabilizado, exportação C++ estática e orquestração automatizada (`ml.real_pipeline`) está implementada e verificada por testes automatizados. Contudo, **nenhuma métrica obtida sobre dados sintéticos representa o desempenho físico real do sensor HC-SR04**.
>
> **REGRA CIENTÍFICA INEGOCIÁVEL:** **É terminantemente proibido misturar amostras sintéticas (`synthetic_simulator`) com dados físicos reais nos diretórios, treinamentos ou relatórios de avaliação real.** Todas as capturas físicas devem ser gravadas exclusivamente em `data/raw/real`.

---

## 1. Pré-requisitos de Segurança Elétrica, Firmware e Bancada

1. **Comissionamento Físico Aprovado (`Etapas A -> B -> C`)**:
   - Seguir integralmente [hardware_safety.md](hardware_safety.md) e [cycle5_bench_checklist.md](cycle5_bench_checklist.md):
     - **`HC-SR04 ECHO -> divisor 1 kΩ / (1 kΩ + 300 Ω) -> GPIO34`**, conforme a netlist atual, após ensaio e medição do pico com instrumento adequado garantindo **`<= 3,30 V`**. Consulte [segurança elétrica](hardware_safety.md).
     - **`TCRT5000`** (`DO -> GPIO35`) e **`Potenciômetro`** (`GPIO36`) alimentados estritamente em **`3,3 V` (`3V3`)** e **barramento `GND` comum**.
2. **Verificação de Dependências e Saúde Metrológica na Bancada**:
   ```powershell
   .\.venv\Scripts\python.exe -m terminal.bench check-deps
   .\.venv\Scripts\python.exe -m terminal.bench inspect --serial-port COMx --duration 5 --reference-cm 25
   .\.venv\Scripts\python.exe -m terminal.diag --serial-port COMx
   ```
   *(Substitua `COMx` pela porta real do ESP32, identificada com `.\.venv\Scripts\python.exe -m terminal.bench ports`).*
3. **Firmware `0.5.0-cycle5` Gravado no ESP32**:
   - Emissão contínua de quadros JSON Lines v1 `sensor_frame` a **`115200 baud`** com período nominal de **`70 ms`** (~`14,3 Hz`, faixa recomendada `60..80 ms` para evitar interferência de eco residual acústico):
   ```json
   {"v":1,"seq":1,"type":"sensor_frame","ts_ms":70,"data":{"distance_cm":24.8,"ir_detected":false,"pot_norm":0.50,"valid_ultrasonic":true}}
   ```
4. **Geometria Padronizada de Bancada**:
   - Fixar o sensor HC-SR04 horizontalmente na borda da protoboard ou levemente inclinado para cima (`~15°`), com cone acústico livre (`~15°..20°`) sem obstáculos estáticos a menos de `80 cm`.
   - Demarcar com fita na bancada três referências visuais de distância frontal: **`10 cm`**, **`25 cm`** e **`45 cm`**.

---

## 2. Taxonomia de Classes: 4 Principais + 2 Experimentais

A campanha de coleta do Ciclo 5 concentra-se nas **4 classes principais de operação embarcada**, mantendo as 2 classes rápidas explicitamente segregadas como **experimentais**:

| Classe | Categoria | Descrição Cinemática na Bancada (`10 cm` a `45 cm`) | Uso no Produto |
| :--- | :---: | :--- | :--- |
| **`NEUTRAL`** | **Principal** | Ausência de mão no cone acústico, repouso distante (`> 55 cm`), pequenos movimentos laterais fora do eixo ou passagem acidental distante. | Estado base sem disparo de eventos. |
| **`APPROACH`** | **Principal** | Aproximação contínua e intencional da palma da mão aberta em direção ao sensor (ex.: de `~45 cm` até `~12 cm`). | Aproximar / Interagir / Avançar ação. |
| **`RETREAT`** | **Principal** | Afastamento contínuo e intencional da palma da mão para longe do sensor (ex.: de `~12 cm` até `~45 cm`). | Recuar / Cancelar / Soltar ação. |
| **`HOLD`** | **Principal** | Manutenção estacionária da palma aberta na zona ativa (`~12 cm` a `30 cm`) por pelo menos `1,0..1,5 s` (incluindo proximidade curta com eventual apoio de `ir_detected`). | Carregar força no *Pet Launch* / Carinho / Sustentação no *Air Music*. |
| **`IMPULSE`** | *Experimental* | Entrada e retirada brusca da mão em pulso único muito curto (`< 0,6 s`). | *Experimental* — sujeito à resolução temporal de `70 ms` (~`14,3 Hz`). |
| **`DOUBLE`** | *Experimental* | Dois pulsos rápidos consecutivos de aproximação e recuo na mesma janela. | *Experimental* — avaliado separadamente somente se houver separabilidade física comprovada. |

---

## 3. Metadados e Campos Obrigatórios de Registro

Cada sessão capturada por `ml.collection` em `data/raw/real/` registra obrigatoriamente metadados auditáveis de sessão e séries temporais brutas completas:

1. **Identificador de Participante Anonimizado (`participant`)**: código pseudonimizado padronizado (`p01`, `p02`, `p03`, `p04`, `p05`, ...), **sem nenhum dado pessoal sensível (PII)**.
2. **Identificador Único de Sessão (`session_id`)**: carimbo rastreável associando participante, índice de sessão e timestamp UTC.
3. **Classe Alvo (`target_gesture` / `label`)**: classe solicitada ao participante em cada segmento do cronograma guiado (`NEUTRAL`, `APPROACH`, `RETREAT`, `HOLD`, ou classes experimentais em sessões dedicadas).
4. **Leituras Brutas e Sequenciamento (`seq` e `sensor_frame`)**: preservação fiel das leituras sem filtragem destrutiva prévia.
5. **Timestamps (`ts_ms`)**: tempo monotônico em milissegundos emitido pelo firmware (e timestamp de chegada no host) para auditoria de *jitter* e lacunas temporais.
6. **Distância Ultrassônica (`distance_cm`)**: valor em centímetros ou `null` quando ocorrer perda de eco.
7. **Estado Infravermelho (`ir_detected`)** e **Potenciômetro (`pot_norm`)**: leitura booleana do TCRT5000 (`GPIO35`) e leitura normalizada `0.0..1.0` do ADC1 (`GPIO36`).
8. **Registro Explícito de Falhas e Timeouts (`valid_ultrasonic`)**: marcação `valid_ultrasonic: false` em todo eco perdido/timeout acústico, além de contadores consolidados de falhas e descartes seriais nos metadados da sessão.
9. **Condições de Coleta (`--conditions`)**: string descritiva obrigatória registrando ambiente, velocidade e geometria da sessão (ex.: `"bancada_interna_vel_normal"`, `"bancada_interna_vel_lenta"`, `"bancada_interna_vel_rapida"`, `"cone_deslocado_5cm"`).
10. **Versão do Firmware (`firmware_version`)**: registro explícito da versão **`0.5.0-cycle5`** reportada pelo ESP32 (e origem `source = "real_hardware"`).

---

## 4. Campanha Multi-Participante Recomendada (`>= 5` Participantes) e Particionamento Sem Vazamento

Antes de iniciar as gravações, consulte o plano estruturado da campanha diretamente na CLI:

```powershell
.\.venv\Scripts\python.exe -m ml.collection --plan-campaign
```

### 4.1 Diretrizes da Campanha (`p01..p05+`)

- **Número recomendado de participantes:** **5 ou mais participantes distintos** (`p01`, `p02`, `p03`, `p04`, `p05`, ...).
- **Diversidade intra-participante (`3 a 5` sessões contínuas por pessoa):**
  - Sessão 1: posição frontal centralizada, velocidade normal (`--conditions "bancada_interna_vel_normal"`).
  - Sessão 2: velocidade mais lenta e suave (`--conditions "bancada_interna_vel_lenta"`).
  - Sessão 3: velocidade rápida dentro da cadência natural (`--conditions "bancada_interna_vel_rapida"`).
  - Sessões adicionais (4–5): leve variação de postura/abertura da mão e leve deslocamento angular dentro do cone acústico (`--conditions "bancada_interna_variacao_posicao"`).
- **Reserva Estrita para Avaliação Final de Teste (*Hold-out*):**
  - Com `>= 5` participantes (`strategy = "by_participant"`): **participantes inteiros** são reservados exclusivamente para validação e para o **conjunto final de teste** (ex.: `p01, p02, p03` para treino; `p04` para validação/seleção de hiperparâmetros; `p05` — e participantes extras — bloqueados exclusivamente para avaliação final de teste).
  - Em coletas preliminares com número reduzido de participantes, **sessões inteiras independentes** devem ser reservadas exclusivamente para teste final (`by_session_fallback`), documentando explicitamente que a generalização inter-participante aguarda o fechamento de `p01..p05`. **Jamais** misture janelas deslizantes da mesma sessão entre treino e teste.
- **Isolamento Absoluto contra Dados Sintéticos:**
  - Nenhuma amostra com `source = "synthetic_simulator"` ou gerada por simuladores pode existir em `data/raw/real/` ou participar de treino, validação ou teste do relatório real. O pipeline `ml.real_pipeline` audita a proveniência e aborta caso detecte contaminação sintética.

---

## 5. Procedimento Prático: Coleta Guiada, Treinamento e Exportação C++

### 5.1 Coleta Contínua Guiada Multi-Participante (`--guided`)

Gravar sessões contínuas intercalando `NEUTRAL` entre cada gesto ativo permite medir não apenas F1 por janela, mas também a **taxa real de falsos disparos e latência de estabilização** no `EventStabilizer`:

```powershell
# Exemplo para participante p01 na porta COMx (gravando exclusivamente em data/raw/real):
.\.venv\Scripts\python.exe -m ml.collection `
  --serial-port COMx `
  --participant p01 `
  --schedule "NEUTRAL:20,APPROACH:15,NEUTRAL:15,RETREAT:15,NEUTRAL:15,HOLD:15,NEUTRAL:20" `
  --conditions "bancada_interna_vel_normal" `
  --guided `
  --output-dir data/raw/real
```

*(Repita variando `--participant p01..p05` e `--conditions` conforme o plano da Seção 4.1).*

### 5.2 Coleta Isolada Opcional para Reforço de `NEUTRAL` ou Casos Difíceis

```powershell
.\.venv\Scripts\python.exe -m ml.collection `
  --serial-port COMx `
  --participant p01 `
  --gesture NEUTRAL `
  --samples 60 `
  --conditions "bancada_interna_repouso_e_passagem_distante" `
  --guided `
  --output-dir data/raw/real
```

### 5.3 Execução Automatizada do Pipeline Real Ponta a Ponta (`ml.real_pipeline`)

Após concluir a coleta das sessões reais em `data/raw/real`, execute o orquestrador único do Ciclo 5, que valida a pureza dos dados reais (bloqueando dados sintéticos), extrai as 11 *features* causais, treina os modelos candidatos (*Rule-Based Baseline*, *Decision Tree*, *Random Forest*, *MLP Compacta*), gera os relatórios comparativos honestos em `data/reports`, exporta o modelo vencedor para `firmware/gestures/tinyml_model.h` com verificação de paridade C++ e confere a compilação do firmware:

```powershell
.\.venv\Scripts\python.exe -m ml.real_pipeline `
  --raw-dir data/raw/real `
  --models-dir data/models `
  --reports-dir data/reports `
  --export-header firmware/gestures/tinyml_model.h `
  --verify-firmware-build
```

*(Caso deseje inspecionar cada etapa isoladamente para depuração, os módulos individuais permanecem disponíveis:)*
```powershell
.\.venv\Scripts\python.exe -m ml.collection --validate data/raw/real
.\.venv\Scripts\python.exe -m ml.preprocessing --input data/raw/real --output data/processed/real_features_dataset.csv
.\.venv\Scripts\python.exe -m ml.training --input data/processed/real_features_dataset.csv --output-dir data/models --seed 42
.\.venv\Scripts\python.exe -m ml.evaluation --dataset data/processed/real_features_dataset.csv --models-dir data/models --output-dir data/reports
.\.venv\Scripts\python.exe -m ml.export --model data/models/best_model.joblib --dataset data/processed/real_features_dataset.csv --output firmware/gestures/tinyml_model.h
```

### 5.4 Regravação Manual do Firmware e Validação Ponta a Ponta na Placa

Com `firmware/gestures/tinyml_model.h` atualizado pelo modelo real:

```powershell
# 1. Gravar manualmente o firmware atualizado no ESP32
pio run -d firmware -t upload --upload-port COMx

# 2. Validar inferência embarcada e telemetria ponta a ponta
.\.venv\Scripts\python.exe -m terminal.bench e2e --serial-port COMx
```

---

## 6. Limitações Experimentais Documentadas

1. **Sensor Escalar 1D (`HC-SR04`)**: mede unicamente a distância radial até o refletor acústico mais próximo dentro do cone de `~15°`. Movimentos puramente laterais (esquerda/direita) não possuem assinatura direcional própria.
2. **Cadência Acústica (~`12,5` a `16,6 Hz` / `70 ms` nominal)**: períodos inferiores a `50 ms` sofrem reverberação de ecos residuais de `40 kHz`. Por essa razão física, gestos ultrarrápidos (`IMPULSE` e `DOUBLE`) permanecem classificados como **experimentais** até comprovação empírica em bancada.
3. **Reflexão Especular e Perda de Eco (`valid_ultrasonic = false`)**: inclinação acentuada da mão pode refletir a frente de onda para fora do receptor, produzindo timeouts pontuais. O pré-processador aplica retenção causal curta (máximo de 2 amostras) e fornece `invalid_ratio` ao classificador para evitar transições espúrias.
4. **Fronteira de Generalização Inter-Participante**: métricas de generalização para novos usuários só têm validade estatística quando calculadas sobre participantes inteiros retidos no conjunto de teste (`>= 5` participantes recomendados). Avaliações preliminares por sessão (`by_session_fallback`) medem apenas repetibilidade intra-usuário.
5. **Paridade Matemática Host vs Execução Real no `ESP-WROOM-32`**: a verificação nativa C++ garante equivalência numérica e alocação estática zero-heap, enquanto o teste `terminal.bench e2e` após regravação confirma latência em tempo real, estabilidade de filas FreeRTOS e resposta interativa nos modos *Tamagotchi*, *Pet Launch* e *Air Music*.
