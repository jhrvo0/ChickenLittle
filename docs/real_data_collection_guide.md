# Protocolo de Coleta do Dataset Real e Limitações Experimentais — MotionPet (Ciclo 2)

> [!IMPORTANT]
> **Status Experimental Atual: `AWAITING_REAL_DATA`**
>
> Toda a infraestrutura de coleta, validação, pré-processamento causal, treinamento, avaliação (janelas e eventos completos) e exportação C++ estática está funcional e verificada com testes automatizados e paridade nativa em C++. Contudo, **nenhuma métrica obtida sobre dados sintéticos representa o desempenho físico real do sensor HC-SR04**. A validação científica depende da coleta na bancada física descrita abaixo.

---

## 1. Pré-requisitos Antes da Coleta Física

1. **Segurança Elétrica Confirmada**:
   - Seguir integralmente [`docs/hardware_safety.md`](hardware_safety.md), especialmente o **divisor resistivo obrigatório ($5\text{ V} \rightarrow \le 3,3\text{ V}$) no pino `ECHO` do HC-SR04**, alimentação em **3,3 V** para o TCRT5000 e **GND comum**.
2. **Pacote `pyserial` instalado no `.venv`**:
   ```powershell
   .\.venv\Scripts\pip.exe install pyserial
   ```
3. **Firmware de Telemetria no ESP32 (Ciclo 3)**:
   - O ESP32 deve emitir linhas JSON Lines v1 do tipo `sensor_frame` a **115200 baud** com intervalo estável entre **60 ms e 80 ms** (~12,5 Hz a 16,6 Hz) para evitar eco residual acústico:
   ```json
   {"v":1,"seq":1,"type":"sensor_frame","ts_ms":70,"data":{"distance_cm":34.2,"ir_detected":false,"pot_norm":0.5,"valid_ultrasonic":true}}
   ```
4. **Geometria Fixa de Bancada**:
   - Fixar o HC-SR04 apontado horizontalmente ou levemente inclinado para cima ($15^\circ$), sem obstáculos fixos a menos de $80\text{ cm}$ dentro do cone acústico (~$15^\circ\text{--}20^\circ$).
   - Marcar na mesa as referências visuais de distância: $10\text{ cm}$, $25\text{ cm}$ e $45\text{ cm}$.

---

## 2. Procedimento Objetivo de Coleta (`python -m ml.collection`)

### 2.1 Coleta por Sessões Contínuas com `NEUTRAL` e Transições (Recomendado)
Gravar sessões contínuas intercalando repouso (`NEUTRAL`) e gestos ativos permite avaliar tanto a classificação por janela quanto a **taxa real de falsos acionamentos e transições** no `EventStabilizer`:

```powershell
# Exemplo para participante p01 (sessão 01 na porta COM3):
.\.venv\Scripts\python.exe -m ml.collection `
  --serial-port COM3 `
  --participant p01 `
  --session-id session_real_p01_s01 `
  --schedule "NEUTRAL:25,APPROACH:18,NEUTRAL:20,HOLD:22,NEUTRAL:20,RETREAT:18,NEUTRAL:25" `
  --output-dir data/raw
```

Durante a captura, o terminal exibirá o prompt em tempo real (`>>> Execute agora: APPROACH (18 amostras)...`) orientando o participante.

### 2.2 Coleta Isolada por Classe (Opcional para Reforço)
```powershell
.\.venv\Scripts\python.exe -m ml.collection `
  --serial-port COM3 `
  --participant p01 `
  --gesture NEUTRAL `
  --samples 60 `
  --output-dir data/raw
```
*(Incluir em `NEUTRAL`: ausência de mão, pequenos movimentos laterais fora do cone e passagem acidental distante para reduzir falsos positivos).*

### 2.3 Meta Mínima Recomendada de Amostragem Real
- **Participantes:** idealmente **$\ge 4$ pessoas distintas** (mínimo absoluto de 3 participantes para ativar `strategy="by_participant"`, reservando participantes inteiros para validação e teste). Caso apenas 1 pessoa colete inicialmente, gravar **$\ge 6$ sessões independentes** em momentos distintos (`strategy="by_session_fallback"`), documentando que a generalização inter-pessoal permanece não testada.
- **Volume inicial:** 3 a 5 sessões contínuas por participante, variando velocidade moderada/rápida e abertura da mão.

---

## 3. Validação, Treinamento, Avaliação e Exportação C++

Após coletar as sessões reais em `data/raw/` (removendo quaisquer arquivos sintéticos de teste):

```powershell
# 1. Validar integridade, monotonicidade temporal (ts_ms) e taxa de timeouts
.\.venv\Scripts\python.exe -m ml.collection --validate data/raw

# 2. Pré-processamento estritamente causal e extração das 11 features
.\.venv\Scripts\python.exe -m ml.preprocessing --input data/raw --output data/processed/features_dataset.csv

# 3. Treinar Baseline por Regras, Decision Tree, Random Forest e MLP Compacta
.\.venv\Scripts\python.exe -m ml.training --input data/processed/features_dataset.csv --output-dir data/models --seed 42

# 4. Gerar relatório comparativo completo (JSON + Markdown)
.\.venv\Scripts\python.exe -m ml.evaluation --dataset data/processed/features_dataset.csv --models-dir data/models --output-dir data/reports

# 5. Exportar modelo vencedor para C++ estático (ESP32) e verificar paridade nativa
.\.venv\Scripts\python.exe -m ml.export --model data/models/best_model.joblib --dataset data/processed/features_dataset.csv --output firmware/gestures/tinyml_model.h
```

---

## 4. Limitações Experimentais Documentadas

1. **Sensor 1D Escalar (HC-SR04):** mede apenas distância radial ao refletor mais próximo no cone acústico (~$15^\circ$). Movimentos laterais (esquerda/direita) não possuem direção distinguível.
2. **Limite Temporal de Aquisição (~12–20 Hz):** intervalos menores que $50\text{--}60\text{ ms}$ sofrem interferência de ecos residuais. Por isso, gestos muito bruscos (`IMPULSE` e `DOUBLE`) permanecem marcados como **experimentais** até verificação de separabilidade nos dados físicos.
3. **Reflexão Especular e Perda de Eco:** inclinação excessiva da palma da mão pode desviar a onda de $40\text{ kHz}$ para fora do receptor, gerando `timeout` (`valid_ultrasonic=false`). O pipeline mitiga falhas curtas com retenção causal de 2 passos e expõe `invalid_ratio` ao classificador.
4. **Generalização entre Participantes:** caso o treinamento seja feito no modo `by_session_fallback` (< 3 participantes), as métricas refletirão apenas consistência intra-usuário entre sessões, não podendo ser extrapoladas para novos usuários.
5. **Paridade C++ no Host vs Execução no ESP32:** o teste nativo com MSVC `cl.exe` comprova equivalência matemática e ausência de alocação dinâmica do código C gerado, mas latência real em microssegundos e consumo exato de SRAM/Flash no Xtensa LX6 só serão confirmados na placa física (Ciclos 3 e 5).
