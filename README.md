# MotionPet

Sistema embarcado interativo que combina **ESP32**, **TinyML** (reconhecimento de gestos em séries temporais 1D), um **LCD físico 20×4** e uma **interface rica em ASCII no terminal do notebook**, sincronizados por um protocolo serial **JSON Lines v1**.

---

## Status do Projeto — Ciclo 1 (Fundação Funcional)

| Subsistema | Status Atual | Observação |
| :--- | :--- | :--- |
| **Motor de Estado do Pet (`terminal/pet/`)** | **Implementado e Testado** | Necessidades, humor, evolução (`EGG` → `CHICK` → `CYBER_ROOSTER`), personalidade emergente e persistência atômica JSON. |
| **Protocolo Serial JSON Lines v1 (`terminal/communication/`)** | **Implementado e Testado** | Envelopes versionados (`v=1`), validação estrita e loopback serial virtual em memória (`VirtualSerialEndpoint`). |
| **Simulador ESP32 + Sensores (`simulator/`)** | **Implementado e Testado** | Simulação determinística 1D do HC-SR04 (~60 ms/amostra, ruído e timeouts), TCRT5000, potenciômetro e replay `.jsonl`/`.csv`. |
| **Espelho LCD 20×4 (`terminal/renderer/lcd20x4.py`)** | **Implementado e Testado** | Garantia estrita de 4 linhas × 20 colunas em ASCII 7-bits imprimível (compatível HD44780). |
| **Terminal ASCII (`terminal/renderer/ascii_terminal.py`)** | **Implementado e Testado** | Cena animada, barras de atributos, espelho do LCD 20×4 em tempo real, telemetria e controle por teclado. |
| **Modos Auxiliares (`Pet Launch`, `Air Music`, `Air Slides`)** | **Interfaces Modulares + Física Base** | Contratos de eventos prontos; loop dedicado do jogo no Ciclo 4 e integrações finais no Ciclo 6. |
| **Pipeline de Machine Learning (`ml/`)** | **Especificado / Estruturado (Ciclo 2)** | Aguardando implementação do pipeline no Ciclo 2 e coleta física real no Ciclo 5 (nenhuma métrica fabricada). |
| **Firmware C++/FreeRTOS (`firmware/`)** | **Headers de Contrato + `platformio.ini` (Ciclo 3)** | Pinout proposto **não validado fisicamente**; consultar obrigatoriamente `docs/hardware_safety.md` antes de energizar. |

---

## Estrutura do Repositório

```text
.
├── firmware/           # Contratos C++/FreeRTOS e platformio.ini (implementação no Ciclo 3)
│   ├── sensors/
│   ├── gestures/
│   ├── display/
│   ├── pet/
│   ├── communication/
│   └── main/
├── terminal/           # Aplicação Python do notebook, motor de domínio e protocolo
│   ├── renderer/       # Renderizadores sincronizados (LCD 20x4 e Terminal ASCII)
│   ├── pet/            # Motor de estado independente de UI, configuração e persistência
│   ├── games/          # Física base e interface modular do Pet Launch (Ciclo 4)
│   ├── modes/          # Interfaces modulares Air Music e Air Slides (Ciclo 6)
│   └── communication/  # Protocolo JSON Lines v1 e transportes Virtual / PySerial
├── ml/                 # Estrutura do pipeline de coleta, treino, avaliação e exportação TinyML (Ciclo 2)
│   ├── collection/
│   ├── preprocessing/
│   ├── training/
│   ├── evaluation/
│   └── export/
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

### 1. Demonstração Executável Automatizada (Sem Hardware)
Executa um roteiro determinístico ponta a ponta: inicialização do nó ESP32 simulado, tráfego JSON Lines v1, gesto ultrassônico `APPROACH`, interações de cuidado, evolução de `EGG` para `CHICK`, salvamento, reset e recarregamento do progresso:

```powershell
.\.venv\Scripts\python.exe -m terminal --demo
```

### 2. Modo Interativo em Tempo Real no Terminal
Abre o painel ASCII animado com controle instantâneo pelo teclado e espelho do LCD 20×4:

```powershell
.\.venv\Scripts\python.exe -m terminal
```

Opções úteis de linha de comando:
- `--name "BitChirp"`: define o nome inicial do pet caso ainda não exista save.
- `--save-path "data/saves/meu_pet.save.json"`: escolhe o arquivo de persistência.
- `--replay "caminho/sessao.jsonl"`: reproduz leituras gravadas de sensores.
- `--frames 20`: executa um número fixo de quadros e encerra.

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
- [`docs/ml_pipeline_spec.md`](docs/ml_pipeline_spec.md) — Especificação do pipeline de Machine Learning e TinyML para séries temporais 1D (Ciclo 2).
