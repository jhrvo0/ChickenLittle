# MotionPet

**Interface gráfica do notebook — Piu-piu.** Execute `.\.venv\Scripts\python.exe -m terminal.web` e abra **http://127.0.0.1:8767/**. O aplicativo local reúne pet animado, cuidados, evolução, Pet Launch com física e loja, música e slides, controlados pelos dois sensores reais. Escolha a porta USB e conecte pela interface; feche antes outros monitores da mesma porta. Veja [as instruções e controles](docs/interface_notebook.md).

**Configuração escolhida em 10/11/2026: sem LCD.** ESP32, HC-SR04 e TCRT5000, com visualização pelo terminal do computador. O usuário confirmou os dois sensores respondendo juntos no painel serial; tensões e exatidão da distância não foram medidas. O [desenho sem LCD](hardware/wokwi/montagem_atual/diagram_sem_lcd.json) e o [registro da bancada](hardware/wokwi/montagem_atual/README.md) descrevem essa configuração. A retirada dos dois cabos de alimentação do LCD ainda aguarda confirmação.

Sistema embarcado interativo que combina **ESP32**, sensores de distância e presença, reconhecimento de gestos e uma **interface gráfica local no notebook**, sincronizados por um protocolo serial **JSON Lines v1**. O terminal ASCII e o suporte ao LCD físico permanecem disponíveis como recursos anteriores; o LCD não faz parte da configuração escolhida.

**Guia anterior com LCD — revisão 4 (10/11/2026):** duas protoboards com trilhos: P1 distribui 5 V, P2 distribui 3V3 e os GNDs são unidos. LCD I²C e TCRT5000 usam somente jumpers; o divisor do ECHO fica separado na P2 e protege o GPIO34 do HC-SR04 em 5 V. Abra o [guia visual](hardware/guia_montagem_final.html) ou o [guia escrito](docs/bench_assembly_guide.md). Para os botões **Testar ESP32/LCD/TCRT5000/HC-SR04/conjunto**, rode `.\.venv\Scripts\python.exe -m terminal.bench.guide` e abra [o guia local](http://127.0.0.1:8766/). O diagnóstico de iluminação do LCD preserva F1–F4 e orienta a mudança temporária apenas de F14/F15, com SDA/SCL removidos antes de usar 5 V e retorno a 3V3 antes dos sinais. Os testes individuais foram relatados pelo usuário; a integração física continua pendente. Os desenhos de LCD paralelo em `hardware/out/` e Wokwi são históricos.

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
| **Assistente de Bancada & Painel Diag (`terminal/bench/` & `terminal/diag/`)** | **Implementados e Testados (Ciclo 5)** | Validação incremental Etapas A–D com verificações elétricas informadas pelo operador, `DIAG`, inspeção de telemetria e painel ASCII. Para a netlist atual, passe explicitamente `--r1 1000 --r2 1300`. |
| **Firmware C++/FreeRTOS (`firmware/`)** | **Compilado (`0.5.0-cycle5`, `esp32dev`)** | 5 tasks FreeRTOS em `APP_CPU_NUM`; build de 10/11/2026: RAM 7,5%, flash 24,5%. ECHO em GPIO34 e LCD I²C em GPIO21/22; validação física conjunta pendente. |
| **Validação Física no Hardware Real** | **`PENDING_PHYSICAL_VALIDATION`** | Funcionamento individual de HC-SR04, TCRT5000 e LCD relatado pelo usuário; falta verificar a montagem conjunta e registrar as medições (`docs/cycle5_bench_checklist.md`). |

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

O firmware atual lê saves NVS anteriores e os converte para o formato v2 no próximo salvamento. Depois dessa conversão, um firmware antigo não consegue ler o save v2; antes de testar em uma placa com dados importantes, preserve um backup compatível com seu procedimento de bancada.

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

### Interface gráfica local

```powershell
.\.venv\Scripts\python.exe -m terminal.web
```

Abra **http://127.0.0.1:8767/** e conecte a ESP32 pela porta listada. O pet aparece como **Piu-piu**, preservando o progresso da placa. Não é necessário instalar dependências de frontend nem usar serviços externos. Para disponibilizar uma demonstração explicitamente identificada, use `--demo` e escolha a porta DEMO. As instruções completas estão em [interface_notebook.md](docs/interface_notebook.md).

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

> **Segurança e honestidade experimental:** o assistente não energiza a montagem nem grava firmware. A montagem atual usa `R1 = 1 kΩ` e `R2 + R3 = 1,3 kΩ` no divisor do ECHO para `GPIO34`; verifique o divisor antes de conectar o GPIO e nunca aceite mais de `3,30 V` no nó. Alimente TCRT5000 e backpack LCD I²C em `3,3 V`, com GND comum. Use somente os quatro pinos do backpack; não adicione fio de RW. O potenciômetro de entrada foi removido e está desativado. Veja [segurança elétrica](docs/hardware_safety.md).

Nos comandos abaixo, substitua `COM3` e `<tensao_medida>` pelos dados reais; o assistente não mede as tensões.

```powershell
# A. Verificar dependências, portas COM, checklist de segurança e divisor resistivo (<= 3,30 V)
.\.venv\Scripts\python.exe -m terminal.bench check-deps
.\.venv\Scripts\python.exe -m terminal.bench ports
.\.venv\Scripts\python.exe -m terminal.bench checklist
.\.venv\Scripts\python.exe -m terminal.bench divider --r1 1000 --r2 1300 --measured-v <tensao_medida>

# B. Validação incremental guiada (adicione --simulate para testar antes de conectar o ESP32 em COMx)
.\.venv\Scripts\python.exe -m terminal.bench stage A --serial-port COM3
.\.venv\Scripts\python.exe -m terminal.bench stage B --serial-port COM3 --r1 1000 --r2 1300 --measured-echo-v <tensao_medida> --reference-cm 25
.\.venv\Scripts\python.exe -m terminal.bench stage C --serial-port COM3 --component ir --vcc-measured-v <tensao_medida>
.\.venv\Scripts\python.exe -m terminal.bench stage D --serial-port COM3 --lcd-vdd-v <tensao_medida>
# Depois de conferir VCC=3V3, os quatro fios e a imagem no LCD fisico:
.\.venv\Scripts\python.exe -m terminal.bench stage D --serial-port COM3 --lcd-vdd-v <tensao_medida> --i2c-wiring-confirmed --visual-confirmed

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

## Eletrônica e CAD (Ciclo 5 — pós-handoff)

A montagem em protoboard agora tem uma **fonte única de verdade** (`hardware/netlist/motionpet.netlist.json`) e artefatos gerados dela:
guia HTML navegável, SVG/PNG da protoboard e do esquemático, `.fzz` do Fritzing, projeto Wokwi, tabelas fio a fio e mapa de furos.

- Comece por **`hardware/out/guia_montagem.html`** (aba **B ★** = HC-SR04 + divisor de ECHO) e leia `hardware/README.md`.
- Decisões, descobertas e limites: `docs/cad_decisions.md`. MCPs avaliados e estado real: `hardware/mcp/README.md`.
- Regenerar: `python -m hardware.build [--png]` · Testar: `python -m pytest tests/test_hardware_cad.py`.
- **Status inalterado: `PENDING_PHYSICAL_VALIDATION`** — nenhuma validação física foi feita; confirmações pendentes C01–C09 na netlist.
