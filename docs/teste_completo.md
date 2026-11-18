# Teste completo do MotionLab (AM + MLOps)

Roteiro para rodar e conferir tudo do zero numa máquina nova: testes automáticos, experimento de
ML, modelo, figuras, stack Docker (MQTT, MLflow, Airflow, API, dashboard) e verificação automática.
Cada passo traz o resultado esperado. Se algo divergir, anote o passo e copie a saída do terminal.

Tempo total: cerca de 40 minutos, a maior parte esperando o primeiro build do Docker.

---

## 0. Pré-requisitos

| Item | Como conferir | Observação |
|---|---|---|
| Git | `git --version` | |
| uv (gerenciador de Python) | `uv --version` | Instalação: https://docs.astral.sh/uv/getting-started/installation/ (o uv baixa o Python 3.13 sozinho) |
| Docker Desktop **aberto** | `docker version` | Docker Compose 2.20 ou mais novo (`docker compose version`). Em Settings → Resources, deixe **pelo menos 6 GB de memória** |
| **Espaço livre em disco: 30 GB ou mais** | macOS/Linux: `df -h ~` · Windows: Explorador de Arquivos | Com o disco cheio o Docker trava e corrompe os próprios dados |
| Node.js 18+ (opcional) | `node --version` | Só para os testes da interface (passo 2) |
| Compilador C (opcional) | macOS: `clang --version` · Linux: `gcc --version` · Windows: Visual Studio Build Tools ou MinGW | Só para a verificação Python × C++ (passo 3). Sem ele, tire `--verify-cpp` do comando |

Nos comandos abaixo, quando houver diferença, aparecem as duas versões: **macOS/Linux** (bash/zsh)
e **Windows** (PowerShell).

---

## 1. Baixar o projeto e preparar o Python

```bash
git clone https://github.com/jhrvo0/ChickenLittle.git
cd ChickenLittle
uv venv .venv --python 3.13
```

Instalar as dependências e ativar o ambiente:

macOS/Linux:
```bash
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-mlops.lock
source .venv/bin/activate
```
Windows:
```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements.txt -r requirements-mlops.lock
.\.venv\Scripts\Activate.ps1
```

O prompt passa a mostrar `(.venv)`. **Todo terminal novo** precisa entrar na pasta `ChickenLittle`
e ativar o ambiente de novo (`source .venv/bin/activate` ou `.\.venv\Scripts\Activate.ps1`); sem isso
o comando `python` não existe ou é o Python errado.

---

## 2. Testes automáticos (cerca de 2 minutos)

```bash
python -m pytest -q -p no:warnings
```
**Esperado:** só `passed` e `skipped` no resumo final, **nenhum `failed`**.

Testes da interface (se tiver Node):
```bash
node --test tests/test_lab_ui.cjs tests/test_web_ui.cjs tests/test_guide_ui.cjs
```
**Esperado:** `fail 0`.

---

## 3. Experimento de ML (1 a 2 minutos)

Gerar o corpus sintético (12 participantes) e rodar o experimento completo: busca de
hiperparâmetros, validação por participante (StratifiedGroupKFold e Leave-One-Group-Out), avaliação
no teste reservado, MLflow local e verificação Python × C++.

```bash
python -m ml.collection --generate-synthetic-corpus --output-dir data/raw/synthetic
```
```bash
python -m ml.experiment --raw-dir data/raw/synthetic --cohort synthetic --extended-models --learned-baseline --search grid --leave-one-group-out --tune --verify-cpp --tracking-uri sqlite:///data/experiments/mlflow.db
```

**Esperado:** no fim, `Experimento salvo em data/experiments/synthetic/<pasta>; cohort=synthetic`.
Os vários `WARNING` do MLflow no meio da saída são normais.

### 3.1 Conferir os números

Guardar o nome da pasta do experimento mais recente:

macOS/Linux:
```bash
ID=$(basename "$(ls -td data/experiments/synthetic/*/ | head -1)") && echo $ID
```
Windows:
```powershell
$ID = (Get-ChildItem data/experiments/synthetic -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name; $ID
```

Mostrar o resultado (igual nos dois sistemas):
```bash
python -c "import json,sys;r='data/experiments/synthetic/'+sys.argv[1];e=json.load(open(r+'/evaluation.json'));m=json.load(open(r+'/manifest.json'));print('selecionado:',m['selected_model'],'| paridade C++:',(m.get('export') or {}).get('cpp_parity',{}).get('passed'));[print(f'{n:25s} F1 {v['test_f1_macro']:.3f}') for n,v in e['models'].items()]" $ID
```

**Esperado** (o experimento é determinístico; os números devem bater):

| Modelo | F1-macro no teste |
|---|---|
| mlp_compact | **0,970** (selecionado) |
| random_forest | 0,953 |
| decision_tree | 0,909 |
| knn | 0,882 |
| adaboost | 0,766 |
| rule_baseline | 0,546 |
| decision_stump_baseline | 0,343 |

E `paridade C++: True` (ou `None`, se o comando rodou sem `--verify-cpp`).

### 3.2 Modelo para o dashboard e figuras do relatório

macOS/Linux:
```bash
mkdir -p data/models && cp data/experiments/synthetic/$ID/models/best_model.joblib data/models/
```
Windows:
```powershell
New-Item -ItemType Directory -Force data/models; Copy-Item data/experiments/synthetic/$ID/models/best_model.joblib data/models/best_model.joblib
```
Figuras (igual nos dois sistemas):
```bash
python -m ml.report_assets data/experiments/synthetic/$ID --output reports/figuras-am
```

**Esperado:** `data/models/best_model.joblib` existe e `reports/figuras-am/` tem `01_classes.png` até
`07_matrizes.png` e `tabelas.json`.

> O `tabelas.json` aparece como modificado no `git status` porque o ID do experimento mudou. Não
> precisa commitar; para descartar: `git restore reports/figuras-am/tabelas.json`.

---

## 4. Stack Docker (5 a 15 minutos na primeira vez)

Construir as duas imagens do projeto, uma vez só, e subir:

```bash
docker compose build api airflow
```
```bash
docker compose up -d
```
```bash
docker compose --profile console up -d --no-deps airflow-ui
```

Esperar 1 a 2 minutos e conferir:
```bash
docker compose ps -a
```

**Esperado:**

| Serviço | Estado |
|---|---|
| `mqtt`, `ingest`, `mlflow`, `api`, `dashboard` | `Up ... (healthy)` |
| `publisher`, `airflow` | `Exited (0)` (rodam uma vez e terminam; é o comportamento correto) |
| `airflow-init` | `Exited (0)` |
| `airflow-ui` | `Up` |

Se algum serviço não estiver assim: `docker compose logs <serviço>`.

---

## 5. Verificação automática da stack (alguns minutos)

```bash
python ops/mlops/verify_stack.py --faults
```

**Esperado:** 14 checks com `"status": "passed"` e o status final `passed`. O teste derruba e
reinicia serviços de propósito (tolerância a falhas); é normal ver containers reiniciando.

---

## 6. Conferir no navegador

Use sempre `127.0.0.1`, **nunca `localhost`** (o dashboard recusa `localhost` por segurança).

| Endereço | O que conferir |
|---|---|
| http://127.0.0.1:8767/ | O dashboard abre (modo DEMO). Em **Motion Intelligence**, os sinais se mexem |
| http://127.0.0.1:5000/ | MLflow: experimentos `MotionLab-demo` e `MotionLab-demo-hiperparametros`, com runs |
| http://127.0.0.1:8080/ | Airflow: login `admin`; o DAG `motionlab_experiment` tem as 4 tarefas em verde |
| http://127.0.0.1:8768/v1/status | API: JSON com o modelo publicado e o hash |

Senha do `admin` do Airflow:

macOS/Linux:
```bash
docker compose logs airflow-ui | grep -i password
```
Windows:
```powershell
docker compose logs airflow-ui | Select-String -Pattern password
```

> **macOS:** se o MLflow (porta 5000) não abrir, desligue o Receptor AirPlay em Ajustes do Sistema →
> Geral → AirDrop e Handoff.

---

## 7. Dados novos pelo MQTT e inferência automática

Publicar novas sessões rotuladas (simulando o sistema embarcado):
```bash
docker compose run --rm publisher
```
```bash
docker compose logs --tail 20 ingest
```

**Esperado:** nos logs, as sessões recebidas, validadas e gravadas, com recibo. Em seguida, no
dashboard http://127.0.0.1:8767/ → **Motion Intelligence → Inferências**, essas sessões aparecem
com a previsão feita pela API, sem ninguém chamar a API manualmente.

---

## 8. Dashboard local com "ML no host" (sem placa)

Num terminal novo (entre na pasta e ative o ambiente):
```bash
python -m terminal.web --port 8790 --demo --ml-api-url http://127.0.0.1:8768
```

Abra http://127.0.0.1:8790/, clique em **Demo** e, no seletor **Fonte**, alterne entre **Regras** e
**ML no host**.

**Esperado:** os gestos (APPROACH, RETREAT, HOLD) aparecem com a confiança nas duas fontes. Se
"ML no host" estiver indisponível, falta o `data/models/best_model.joblib` (passo 3.2).

Com a ESP32 conectada, rode o mesmo comando sem `--demo` e clique em **Conectar**. Feche antes
qualquer outro programa que use a porta serial.

---

## 9. Desligar sem apagar dados

```bash
docker compose --profile console down
```
Nunca use `-v` (apaga os volumes). No terminal do dashboard do passo 8: `Ctrl+C`.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `zsh: command not found: python` | Ambiente não ativado: `source .venv/bin/activate` (Windows: `.\.venv\Scripts\Activate.ps1`) |
| `no such file or directory: ID` | Digitou `<ID>` literalmente. Use a variável `$ID` do passo 3.1 ou o nome real da pasta |
| `image "motionlab-runtime:phase-c": already exists` | Builds paralelos da mesma imagem. Rode `docker compose build api airflow` antes do `up` |
| `pull access denied for motionlab-airflow` | A imagem do Airflow é local. Rode `docker compose build api airflow` antes do `up` |
| `input/output error` em `/var/lib/desktop-containerd/...` ou build parado sem progresso | Disco cheio. Libere 30 GB ou mais, depois Docker Desktop → Troubleshoot → **Clean / Purge data** e refaça o passo 4 |
| Página "Use o endereço local informado" | Abriu por `localhost`; troque por `127.0.0.1` |
| MLflow não abre no Mac | Receptor AirPlay ocupando a porta 5000 (ver passo 6) |
| `airflow` em `Exited (1)` | `docker compose logs airflow`; em geral falta memória para o Docker (Settings → Resources) |
| Paridade C++ falhou ou não rodou | Falta compilador C; rode o experimento sem `--verify-cpp` |
