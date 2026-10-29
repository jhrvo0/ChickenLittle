# MotionPet

Sistema embarcado interativo que combina **ESP32**, **TinyML** (reconhecimento de gestos em séries temporais 1D), um **LCD físico 20×4** e uma **interface rica em ASCII no terminal do notebook**, sincronizados por um protocolo serial **JSON Lines v1**.

---

## Status do Projeto — Ciclos 1 a 5 (`PENDING_PHYSICAL_VALIDATION`)

| Subsistema | Status Atual | Observação |
| :--- | :--- | :--- |
| **Motor de Estado do Pet (`terminal/pet/` & `firmware/pet/`)** | **Implementado e Testado (Python + C++)** | Paridade 1:1 verificada entre `PetEngine` (Python) e `pet_state.cpp` (C++), integrado a moedas, recordes, loja de melhorias e persistência NVS/JSON. |
| **Protocolo Serial JSON Lines v1 (`terminal/communication/` & `firmware/communication/`)** | **Implementado e Testado (Python + C++)** | Envelopes versionados (`v=1`) zero-heap no ESP32 (`sensor_frame`, `gesture_event`, `pet_state`, `lcd_frame`, `ack`, `error`) + comandos de bancada (`DIAG`, `START`, `STOP`, `PERIOD`, `IR`). |
| **Simulador ESP32 + Sensores (`simulator/`)** | **Implementado e Testado** | Simulação determinística 1D do HC-SR04, TCRT5000, potenciômetro, replay `.jsonl`/`.csv`, comandos `DIAG` (`origin=SIMULATOR`) e classificador intercambiável. |
| **Espelho LCD 20×4 & Terminal ASCII (`terminal/renderer/` & `firmware/display/`)** | **Implementado e Testado (Python + C++)** | Renderização diferencial anti-flicker, modo compacto (60 cols) e 6 estados LCD 20×4 dedicados ao Pet Launch. |
| **Infraestrutura de Machine Learning (`ml/` & `firmware/gestures/`)** | **Pronta p/ Coleta Real (`AWAITING_REAL_DATA`)** | Coleta guiada multi-participante, filtro causal, 11 features, seleção multicritério embarcada, guarda anti-sintético (`ml.real_pipeline`) e TinyML C++ estático (`mlp_compact`). |
| **Minijogo `Pet Launch` (`terminal/games/`)** | **Jogável Ponta a Ponta (Ciclo 4/5)** | Loop arcade completo de 10 etapas, física 2D de timestep fixo (`0.02s`), loja de melhorias e validador E2E gestual (`terminal.bench e2e`). |
| **Assistente de Bancada & Painel Diag (`terminal/bench/` & `terminal/diag/`)** | **Implementados e Testados (Ciclo 5)** | Validação incremental Etapas A–D com bloqueios elétricos (`<= 3,30 V`, `2,2 kΩ / 3,3 kΩ`), `DIAG`, inspeção de telemetria e painel ASCII de séries temporais em tempo real. |
| **Firmware C++/FreeRTOS (`firmware/`)** | **Compilado (`0.5.0-cycle5`, `esp32dev`)** | 5 tasks FreeRTOS em `APP_CPU_NUM` (`RAM: 7.2%`, `Flash: 23.3%`). Pinout canônico reconciliado em `GPIO34` (`CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION`). |
| **Validação Física no Hardware Real** | **`PENDING_PHYSICAL_VALIDATION`** | Aguardando conexão física do ESP32 + sensores na bancada (seguir `docs/cycle5_bench_checklist.md`). |

---

## Estrutura do Repositório

```text
.
├── firmware/           # Firmware C++/FreeRTOS real para ESP32 e platformio.ini (Ciclos 3 a 5)
│   ├── sensors/
│   ├── gestures/
│   ├── display/
│   ├── pet/
│   ├── communication/
│   └── main/
├── terminal/           # Aplicação Python do notebook, motor de domínio, bancada e protocolo
│   ├── bench/          # Assistente CLI de bancada, etapas A-D, pinout canônico e teste E2E (Ciclo 5)
│   ├── diag/           # Painel ASCII em tempo real de diagnóstico e séries temporais (Ciclo 5)
│   ├── renderer/       # Renderizadores sincronizados (LCD 20x4 e Terminal ASCII)
│   ├── pet/            # Motor de estado independente de UI, configuração e persistência
│   ├── games/          # Física 2D, modo jogável, loja e renderer do Pet Launch (Ciclo 4)
│   ├── modes/          # Interfaces modulares Air Music e Air Slides (Ciclo 6)
│   └── communication/  # Protocolo JSON Lines v1 e transportes Virtual / PySerial
├── ml/                 # Pipeline de coleta, treino, avaliação, seleção multicritério e exportação TinyML
│   ├── collection/
│   ├── preprocessing/
│   ├── training/
│   ├── evaluation/
│   ├── export/
│   └── real_pipeline.py
├── simulator/          # Simulador de sensores 1D, replay de datasets e nó ESP32 virtual
├── tests/              # Suíte automatizada pytest
├── data/               # Diretório para saves locais e futuros datasets coletados
├── docs/               # Arquitetura (ADRs), protocolo JSONL, pipeline ML e segurança elétrica
├── pyproject.toml      # Metadados do projeto e configuração do pytest
└── requirements.txt    # Dependências fixadas do ambiente virtual
```

---

## Instalação e Configuração (Windows ARM64 / PowerShell)

O runtime principal do Ciclo 1 utiliza apenas a biblioteca padrão do Python (`>= 3.11`), evitando dependências binárias pesadas no Windows ARM64. O `pytest` é utilizado para a suíte de testes automatizados.

```powershell
# 1. Criar ambiente virtual (caso ainda não exista)
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv

# 2. Instalar dependências do projeto
.\.venv\Scripts\pip.exe install -r requirements.txt

# 3. (Opcional) Instalar pacote local em modo editável para habilitar o atalho 'motionpet'
.\.venv\Scripts\pip.exe install -e .
```

---

## Como Executar

### 1. Demonstrações Executáveis Automatizadas (Sem Hardware)

```powershell
# Demonstração do Ciclo 1 (Tamagotchi + gestos + evolução + persistência)
.\.venv\Scripts\python.exe -m terminal --demo

# Demonstração do Ciclo 4 (Partida completa do Pet Launch em 10 etapas + loja + log de eventos)
.\.venv\Scripts\python.exe -m terminal --launch-demo
```

### 2. Modo Interativo em Tempo Real no Terminal (MotionPet & Pet Launch)
Abre o painel ASCII animado com renderização diferencial anti-flicker e espelho do LCD 20×4:

```powershell
# Iniciar direto no minijogo Pet Launch (ou omitir --mode para abrir no Tamagotchi)
.\.venv\Scripts\python.exe -m terminal --mode pet-launch

# Forçar layout compacto de 60 colunas para janelas pequenas
.\.venv\Scripts\python.exe -m terminal --mode pet-launch --compact
```

Opções úteis de linha de comando:
- `--classifier {sim,ml,embedded}`: seleciona o classificador intercambiável de gestos (degrada graciosamente mesmo sem modelo treinado).
- `--model-path "data/models/best_model.joblib"`: define o artefato usado por `--classifier ml`.
- `--name "BitChirp"`: define o nome inicial do pet caso ainda não exista save.
- `--save-path "data/saves/meu_pet.save.json"`: escolhe o arquivo de persistência.
- `--replay "caminho/sessao.jsonl"`: reproduz leituras gravadas de sensores.
- `--frames 20`: executa um número fixo de quadros e encerra.

### 3. Pipeline Completo de Machine Learning (Ciclo 2)

> **Aviso Experimental:** Dados sintéticos servem exclusivamente para validar o funcionamento do código. Qualquer execução sem dados físicos carimba automaticamente `experimental_status = AWAITING_REAL_DATA`.

```powershell
# A. Gerar corpus sintético de verificação do pipeline (ou usar --serial-port COMx para coleta real)
.\.venv\Scripts\python.exe -m ml.collection --generate-synthetic-corpus --output-dir data/raw/synthetic

# B. Validar integridade, ordenação temporal e qualidade das sessões
.\.venv\Scripts\python.exe -m ml.collection --validate data/raw/synthetic

# C. Pré-processamento causal e extração das 11 features temporais
.\.venv\Scripts\python.exe -m ml.preprocessing --input data/raw/synthetic --output data/processed/features_dataset.csv

# D. Treinar Baseline por Regras, Decision Tree, Random Forest e MLP Compacta (split agrupado sem vazamento)
.\.venv\Scripts\python.exe -m ml.training --input data/processed/features_dataset.csv --output-dir data/models --seed 42

# E. Avaliar modelos (janelas + eventos completos com rejeição/estabilização/cooldown) e gerar relatórios JSON/MD
.\.venv\Scripts\python.exe -m ml.evaluation --dataset data/processed/features_dataset.csv --models-dir data/models --output-dir data/reports

# F. Exportar modelo para C++ estático (zero heap) e compilar/testar paridade nativa
.\.venv\Scripts\python.exe -m ml.export --model data/models/best_model.joblib --dataset data/processed/features_dataset.csv --output firmware/gestures/tinyml_model.h

# G. Executar o MotionPet integrado com o classificador de ML
.\.venv\Scripts\python.exe -m terminal --demo --classifier ml --model-path data/models/best_model.joblib
```

### 4. Integração Física de Bancada, Diagnóstico e Dataset Real (Ciclo 5)

> **Regra de Segurança e Honestidade Experimental:** O assistente de bancada **nunca** energiza a montagem nem grava firmware automaticamente. Não aceite `3,5 V` como seguro no `ECHO`: utilize preferencialmente **`R1 = 2,2 kΩ` + `R2 = 3,3 kΩ`** (`3,00 V` @ `5,0 V`; `<= 3,30 V`) no pino canônico **`GPIO34`**, aterre `LCD RW` em `GND` e alimente `TCRT5000`/potenciômetro em `3,3 V`.

```powershell
# A. Verificar dependências, portas COM, checklist de segurança e divisor resistivo (<= 3,30 V)
.\.venv\Scripts\python.exe -m terminal.bench check-deps
.\.venv\Scripts\python.exe -m terminal.bench ports
.\.venv\Scripts\python.exe -m terminal.bench checklist
.\.venv\Scripts\python.exe -m terminal.bench divider --r1 2200 --r2 3300 --measured-v 3.00

# B. Validação incremental guiada (adicione --simulate para testar antes de conectar o ESP32 em COMx)
.\.venv\Scripts\python.exe -m terminal.bench stage A --serial-port COM3
.\.venv\Scripts\python.exe -m terminal.bench stage B --serial-port COM3 --r1 2200 --r2 3300 --measured-echo-v 3.00 --reference-cm 25
.\.venv\Scripts\python.exe -m terminal.bench stage C --serial-port COM3 --component both --vcc-measured-v 3.30
.\.venv\Scripts\python.exe -m terminal.bench stage D --serial-port COM3 --lcd-vdd-v 5.00

# C. Painel ASCII de diagnóstico em tempo real (indica explicitamente HARDWARE REAL vs SIMULADOR)
.\.venv\Scripts\python.exe -m terminal.diag --serial-port COM3
.\.venv\Scripts\python.exe -m terminal.diag --simulate --frames 32

# D. Plano de campanha (>= 5 participantes) e captura guiada real (sem mistura sintética)
.\.venv\Scripts\python.exe -m ml.collection --plan-campaign
.\.venv\Scripts\python.exe -m ml.collection --serial-port COM3 --participant p01 --guided --conditions "bancada_interna_vel_normal" --output-dir data/raw/real

# E. Treino multicritério com dados 100% reais, exportação C++ com paridade e rebuild do firmware
.\.venv\Scripts\python.exe -m ml.real_pipeline --raw-dir data/raw/real --models-dir data/models/real --reports-dir data/reports --export-header firmware/gestures/tinyml_model.h --verify-firmware-build

# F. Validação ponta a ponta do Pet Launch (gestos -> serial -> jogo -> LCD -> persistência)
.\.venv\Scripts\python.exe -m terminal.bench e2e --serial-port COM3
```

### Atalhos de Teclado no Modo Interativo

| Tecla | Ação |
| :---: | :--- |
| `F` | Alimentar o pet (`FEED`) |
| `P` | Brincar com o pet (`PLAY`) |
| `R` | Alternar sono / acordar (`REST`) |
| `C` | Curar / cuidar da saúde (`HEAL`) |
| `I` | Fazer carinho (`INTERACT`) |
| `1` / `2` / `3` / `4` | Simular trajetória 1D de gesto no HC-SR04 (`APPROACH`, `RETREAT`, `HOLD`, `NEUTRAL`) |
| `+` / `-` | Ajustar posição do potenciômetro simulado |
| `T` | Avançar manualmente um tick biológico |
| `S` / `L` / `N` | Salvar progresso / Recarregar progresso / Resetar pet |
| `M` | Alternar entre `MOTION_PET`, `PET_LAUNCH`, `AIR_MUSIC` e `AIR_SLIDES` |
| `ENTER` ou `E` / Gesto `APPROACH` (`1`) | **Pet Launch:** Selecionar pet / Confirmar etapa / Disparar lançamento |
| `SPACE` ou `H` / Gesto `HOLD` (`3`) | **Pet Launch:** Carregar barra de força (zona Sweet-Spot: `80%..95%`) |
| `B` ou `ESC` / Gesto `RETREAT` (`2`) | **Pet Launch:** Cancelar carga ou voltar ao menu anterior |
| `W` / `Z` (ou `+` / `-` POT) | **Pet Launch:** Ajustar ângulo de lançamento (`20°..70°`) |
| `U` ou `7` / `8` / `9` | **Pet Launch:** Desbloquear melhorias na loja (`Estilingue Pro`, `Capa Aero`, `Botas de Mola`) |
| `Q` | Encerrar aplicação com segurança |

---

## Executar Testes Automatizados

```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## Documentação Técnica e Segurança de Hardware

- [`docs/architecture.md`](docs/architecture.md) — Arquitetura dual-interface, ADRs e separação entre simulação e hardware.
- [`docs/protocol.md`](docs/protocol.md) — Especificação do protocolo serial JSON Lines v1.
- [`docs/hardware_safety.md`](docs/hardware_safety.md) — **Leitura obrigatória antes da montagem física**: divisor resistivo para o pino `ECHO` (5 V → 3,3 V) do HC-SR04, aterramento de `RW` e compatibilidade lógica do LCD 2004A V1.1, restrições de GPIOs do ESP32 e checklist de bancada.
- [`docs/bench_assembly_guide.md`](docs/bench_assembly_guide.md) — **Guia incremental de bancada (Ciclo 3)**: montagem em 4 estágios (priorizando P0 HC-SR04), checklist de multímetro pré-energização e comandos de gravação/coleta real.
- [`docs/ml_pipeline_spec.md`](docs/ml_pipeline_spec.md) — Especificação do pipeline de Machine Learning e TinyML para séries temporais 1D (Ciclo 2).
- [`docs/real_data_collection_guide.md`](docs/real_data_collection_guide.md) — Procedimento passo a passo para coleta multi-participante do dataset físico real na bancada e limitações experimentais.
- [`docs/cycle5_bench_checklist.md`](docs/cycle5_bench_checklist.md) — **Checklist físico rápido e objetivo (Ciclo 5)**: tabela canônica única (`GPIO34`), regras elétricas (`<= 3,30 V`) e comandos das Etapas A–D até o teste E2E do Pet Launch.
