# Aprendizado de Máquina (2026.6, 2ª unidade): requisitos × repositório

Este documento cruza a especificação de projeto da disciplina com o que o MotionLab entrega e indica como reproduzir cada item. O problema de ML é a **classificação de gestos** (NEUTRAL, APPROACH, RETREAT, HOLD) a partir de janelas de 10 leituras do HC-SR04 e do TCRT5000, com 11 features por janela.

## Como rodar

| O quê | Comando (raiz do repositório) |
|---|---|
| Solução completa (broker, ingestão, Airflow, MLflow, API, dashboard) | `docker compose up --build` |
| Interface do Airflow, opcional | `docker compose --profile console up --build` |
| Experimento local completo, sem Docker | `python -m ml.collection --generate-synthetic-corpus --output-dir data/raw/synthetic` e depois `python -m ml.experiment --raw-dir data/raw/synthetic --cohort synthetic --extended-models --learned-baseline --search grid --leave-one-group-out --tune --tracking-uri sqlite:///data/experiments/mlflow.db` |
| Notebook de EDA a partir de um experimento | `python -m ml.academic_notebook data/experiments/synthetic/<id>` |
| Interface do MLflow local | `mlflow ui --backend-store-uri sqlite:///data/experiments/mlflow.db` |

Endereços com Docker: dashboard em <http://127.0.0.1:8767>, API em <http://127.0.0.1:8768>, MLflow em <http://127.0.0.1:5000> e Airflow (perfil `console`) em <http://127.0.0.1:8080>.

## Matriz de requisitos

| Requisito da especificação | Onde está | Situação |
|---|---|---|
| Leitura do bootstrap dataset | `ml/collection/` (gerador e validador), `ml/preprocessing/windowing.py` | Atendido; o corpus atual é **simulado** |
| EDA em notebook com estatísticas descritivas | `notebooks/motionlab_bootstrap.ipynb` (gerado por `ml/academic_notebook.py`) | Atendido |
| Tratamento de dados com justificativa | Seção “Tratamento dos dados e justificativas” do notebook; `ml/preprocessing/filtering.py` | Atendido nesta revisão |
| Mínimo de 5 visualizações interpretadas | 5 figuras de EDA (`ml/eda.py`), gráfico treino × validação e matrizes de confusão | Atendido |
| Holdout | `split_windows_grouped`: participantes de teste reservados antes da EDA | Atendido |
| Validação cruzada | `GroupKFold` por participante (`ml/validation.py`) | Atendido; k-fold estratificado comum vazaria janelas sobrepostas da mesma pessoa |
| Leave-One-Out | `LeaveOneGroupOut` (um participante por vez) | Atendido; LOO por janela não é aplicável (janelas sobrepostas) |
| Estabilidade, sobreajuste, subajuste e generalização | Desvio entre folds, F1 de treino × validação por fold, diagnóstico `fit_diagnosis`, holdout | Atendido nesta revisão |
| Otimização de hiperparâmetros (Grid/Random) | `search_hyperparameters` em `ml/validation.py`, `--search grid` ou `--search random` | Atendido nesta revisão |
| Baseline justificado | Árvore de profundidade 1 (`decision_stump_baseline`) e regras de domínio (`rule_baseline`) | Atendido |
| ≥ 3 modelos da lista (KNN, Árvore, RF, AdaBoost, MLP) | Árvore, Random Forest e MLP; **KNN e AdaBoost** com `--extended-models` | Atendido: os 5 da lista |
| Visualizações de comparação e análise crítica | Matrizes de confusão, F1 por classe, gráfico treino × validação, seção crítica do notebook | Atendido |
| MLflow: parâmetros, métricas, artefatos, modelo salvo | `ml/tracking.py` | Atendido |
| MLflow: múltiplos experimentos | `MotionLab-<coorte>` (baseline e comparação, papéis em tags) e `MotionLab-<coorte>-hiperparametros` (busca) | Atendido nesta revisão |
| Sistema embarcado e MQTT | ESP32 real (`firmware/`) com MQTT/TLS; simulador (`simulator/`, serviço `publisher`) | Atendido |
| Recepção e persistência | `ml/mqtt_ingestion.py` (JSONL) e `ml/iot_ingestion.py` (SQLite) | Atendido |
| Pipeline com Airflow | `ops/mlops/dags/motionlab_experiment.py`: configuração → preparação → experimento → publicação | Atendido; no Compose roda em lote (`dags test`) |
| Modelo integrado ao pipeline e inferências por API | `ml/inference_api.py` observa `data/raw` e gera previsões para dados novos | Atendido |
| Dashboard interativo | MotionLab, painel Motion Intelligence: sinais ao vivo, métricas, previsões e estado do serviço | Atendido com aplicação própria (a especificação cita Streamlit/Dash como exemplos) |
| Docker Compose com execução em um único comando | `docker-compose.yml` na raiz (inclui `ops/mlops/compose.yaml`) | Atendido nesta revisão; ver limites |
| README com equipe, nome, instruções e Google Sites | `README.md` | Atendido após o merge do branch `docs/ajustes-checkpoint` (link do Google Sites) |
| Relatório no template SBC | — | **Pendente**: o relatório de AM ainda não existe (o PDF em `docs/` é o de Sistemas Embarcados) |

## O que mudou nesta revisão

- **KNN e AdaBoost** entraram como candidatos de comparação. KNN usa `StandardScaler` em pipeline; AdaBoost usa árvores de profundidade 1. Os dois ficam fora da seleção do modelo embarcado, porque o exportador C++ cobre só árvore, floresta e MLP.
- **Busca de hiperparâmetros** por família de modelo, com Grid Search ou Random Search e GroupKFold nos grupos de desenvolvimento. O vencedor de cada família é aplicado antes do treino final. Cada combinação vira um run no experimento MLflow `...-hiperparametros`.
- **Diagnóstico de ajuste:** a validação cruzada passou a registrar o F1 de treino de cada fold, a diferença treino-validação e um rótulo (`overfitting`, `underfitting` ou `balanced`). Os limiares (0,10 de diferença; 0,60 de F1) são convenções do projeto.
- **O DAG do Airflow** passa a rodar a comparação estendida e o Grid Search.
- **`docker-compose.yml` na raiz:** `docker compose up --build` sobe a solução inteira.
- **Notebook:** novas seções de tratamento de dados, otimização e sobreajuste; o caminho do experimento fica relativo à raiz.

## Resultado de referência (corpus simulado, seed 42)

Execução local com o comando da tabela “Como rodar”, 5 participantes simulados (3 de treino, 1 de validação, 1 de teste). Os números descrevem o simulador, não pessoas reais.

| Modelo | F1 CV (validação) | F1 treino (CV) | Diagnóstico | F1 holdout |
|---|---|---|---|---|
| Regras (referência) | 0,53 ± 0,01 | 0,53 | subajuste | 0,55 |
| Árvore profundidade 1 (baseline) | 0,34 ± 0,02 | 0,34 | subajuste | 0,33 |
| Árvore de decisão | 0,85 ± 0,08 | 0,99 | sobreajuste | 0,79 |
| Random Forest | 0,88 ± 0,07 | 0,99 | sobreajuste | 0,88 |
| MLP | 0,94 ± 0,02 | 1,00 | equilibrado | 0,91 |
| KNN | 0,87 ± 0,06 | 1,00 | (memoriza o treino) | 0,84 |
| AdaBoost | 0,66 ± 0,09 | 0,76 | sobreajuste | 0,60 |

Com 4 grupos de desenvolvimento, GroupKFold e LeaveOneGroupOut produzem a mesma partição; não são duas evidências independentes. Os valores mudam a cada execução da busca, porque os hiperparâmetros escolhidos dependem do corpus.

## Limites e pendências

- **Relatório SBC de AM:** precisa ser escrito pelo grupo no template anexo à especificação.
- **Docker:** o Compose da raiz foi validado com `docker compose config` (todos os serviços e caminhos resolvem), mas a stack não foi subida nesta revisão. Antes da apresentação, rode `docker compose up --build` e `python ops/mlops/verify_stack.py --faults`; o verificador foi atualizado para esperar KNN, AdaBoost e o experimento de hiperparâmetros.
- **Dados reais:** todos os modelos foram treinados com dados simulados. A coleta com participantes segue em `docs/real_data_collection_guide.md`.
- **Airflow:** no Compose, o DAG roda uma vez em lote. O scheduler contínuo fica no perfil `console`.
- **Dashboard:** é a aplicação MotionLab, não Streamlit ou Dash; vale confirmar com o professor que atende ao requisito.
