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
| Validação cruzada | `StratifiedGroupKFold` (5 folds, estratificado por classe e agrupado por participante), com `GroupKFold` como alternativa quando uma classe não aparece em grupos suficientes (`ml/validation.py`) | Atendido; o k-fold estratificado comum vazaria janelas sobrepostas da mesma pessoa |
| Leave-One-Out | `LeaveOneGroupOut` (um participante por vez) | Atendido; LOO por janela não é aplicável (janelas sobrepostas) |
| Estabilidade, sobreajuste, subajuste e generalização | Desvio entre folds, F1 de treino × validação por fold, diagnóstico `fit_diagnosis`, holdout | Atendido nesta revisão |
| Otimização de hiperparâmetros (Grid/Random) | `search_hyperparameters` em `ml/validation.py`, `--search grid` ou `--search random` | Atendido nesta revisão |
| Baseline justificado | Árvore de profundidade 1 (`decision_stump_baseline`) e regras de domínio (`rule_baseline`) | Atendido |
| ≥ 3 modelos da lista (KNN, Árvore, RF, AdaBoost, MLP) | Árvore, Random Forest e MLP; **KNN e AdaBoost** com `--extended-models` | Atendido: os 5 da lista |
| Visualizações de comparação e análise crítica | Matrizes de confusão, F1 por classe, gráfico treino × validação, seção crítica do notebook | Atendido |
| Comparação estatística dos modelos | Friedman nos folds do LOGO e Wilcoxon pareado contra o melhor, com correção de Holm (`compare_models_statistically`) | Atendido |
| MLflow: parâmetros, métricas, artefatos, modelo salvo | `ml/tracking.py` | Atendido |
| MLflow: múltiplos experimentos | `MotionLab-<coorte>` (baseline e comparação, papéis em tags) e `MotionLab-<coorte>-hiperparametros` (busca) | Atendido nesta revisão |
| Sistema embarcado e MQTT | ESP32 real (`firmware/`) com MQTT/TLS; simulador (`simulator/`, serviço `publisher`) | Atendido |
| Recepção e persistência | `ml/mqtt_ingestion.py` (JSONL) e `ml/iot_ingestion.py` (SQLite) | Atendido |
| Pipeline com Airflow | `ops/mlops/dags/motionlab_experiment.py`: configuração → preparação → experimento → publicação | Atendido; no Compose roda em lote (`dags test`) |
| Modelo integrado ao pipeline e inferências por API | `ml/inference_api.py` observa `data/raw` e gera previsões para dados novos | Atendido |
| Dashboard interativo | MotionLab, painel Motion Intelligence: sinais ao vivo, métricas, previsões e estado do serviço | Atendido com aplicação própria (a especificação cita Streamlit/Dash como exemplos) |
| Docker Compose com execução em um único comando | `docker-compose.yml` na raiz (inclui `ops/mlops/compose.yaml`) | Atendido nesta revisão; ver limites |
| README com equipe, nome, instruções e Google Sites | `README.md` | Atendido após o merge do branch `docs/ajustes-checkpoint` (link do Google Sites) |
| Relatório no template SBC | `reports/relatorio_aprendizado_maquina.docx` (fonte), `.md` e `.pdf`; figuras e tabelas geradas por `python -m ml.report_assets` | Atualizado em 16/11; o PDF precisa ser reexportado do `.docx` e o grupo deve revisar |

## O que mudou nesta revisão

- **KNN e AdaBoost** entraram como candidatos de comparação. KNN usa `StandardScaler` em pipeline; AdaBoost usa árvores de profundidade 1. Os dois ficam fora da seleção do modelo embarcado, porque o exportador C++ cobre só árvore, floresta e MLP.
- **Busca de hiperparâmetros** por família de modelo, com Grid Search ou Random Search e GroupKFold nos grupos de desenvolvimento. O vencedor de cada família é aplicado antes do treino final. Cada combinação vira um run no experimento MLflow `...-hiperparametros`.
- **Diagnóstico de ajuste:** a validação cruzada passou a registrar o F1 de treino de cada fold, a diferença treino-validação e um rótulo (`overfitting`, `underfitting` ou `balanced`). Os limiares (0,10 de diferença; 0,60 de F1) são convenções do projeto.
- **O DAG do Airflow** passa a rodar a comparação estendida e o Grid Search.
- **`docker-compose.yml` na raiz:** `docker compose up --build` sobe a solução inteira.
- **Notebook:** novas seções de tratamento de dados, otimização e sobreajuste; o caminho do experimento fica relativo à raiz.

Revisão de 16/11:

- **Corpus bootstrap com 12 participantes** (padrão de `ml.collection`): o teste externo passa a ter 2 participantes e o LOGO (10 folds) deixa de coincidir com o k-fold (5 folds).
- **`StratifiedGroupKFold`** na validação cruzada e na busca, que é o k-fold estratificado da especificação sem misturar participantes.
- **Comparação estatística** (`model_comparison` no manifesto): Friedman e Wilcoxon com Holm, também no notebook e no relatório.
- **Simulador a 70 ms**, o período do firmware (antes 75 ms), e **variação entre participantes na demo** publicada por MQTT (antes os cinco eram idênticos, o que deixava a avaliação da demo otimista).
- **`ml/report_assets.py`** gera figuras e `tabelas.json` do relatório a partir do experimento; o relatório foi reescrito com essas tabelas, referências bibliográficas e a comparação estatística.

## Resultado de referência (corpus simulado, seed 42)

Experimento `20261116T230322_c96f733d`: 4303 leituras, 1918 janelas, 12 participantes simulados (7 de treino, 3 de validação e 2 de teste: sim_p04 e sim_p10). Comando: o da tabela “Como rodar”, com `--verify-cpp`. Os números descrevem o simulador, não pessoas reais.

| Modelo | F1 SGKF (5 folds) | F1 LOGO (10 folds) | F1 treino | Diagnóstico | F1 teste |
|---|---|---|---|---|---|
| Árvore profundidade 1 (baseline) | 0,329 ± 0,011 | 0,328 ± 0,014 | 0,330 | subajuste | 0,343 |
| Regras (referência) | 0,530 ± 0,014 | 0,529 ± 0,024 | 0,531 | subajuste | 0,546 |
| Árvore de decisão | 0,897 ± 0,035 | 0,895 ± 0,050 | 0,976 | equilibrado | 0,909 |
| Random Forest | 0,932 ± 0,031 | 0,933 ± 0,043 | 0,979 | equilibrado | 0,953 |
| KNN | 0,917 ± 0,027 | 0,921 ± 0,034 | 1,000 | equilibrado | 0,882 |
| AdaBoost | 0,629 ± 0,024 | 0,642 ± 0,050 | 0,660 | equilibrado | 0,766 |
| MLP | 0,982 ± 0,016 | 0,983 ± 0,018 | 0,999 | equilibrado | 0,970 |

Friedman nos 10 folds do LOGO: p = 1.2e-10. A MLP ficou em 1º em todos os folds e é melhor que cada outro modelo no Wilcoxon com Holm (p = 0.012, o menor possível com 10 folds). Modelo selecionado para a ESP32: MLP; paridade Python/C++ em 320 janelas: 100%. Figuras e tabelas completas: `reports/figuras-am/` e `reports/figuras-am/tabelas.json`.

O resultado anterior, com 5 participantes, está registrado em [entrega_am_2026-11-15.md](entrega_am_2026-11-15.md).

## Limites e pendências

- **Relatório SBC de AM:** [editável](../reports/relatorio_aprendizado_maquina.docx) e [texto](../reports/relatorio_aprendizado_maquina.md) atualizados em 16/11. **O PDF precisa ser reexportado do `.docx`** (Word, Google Docs ou LibreOffice) antes da entrega. O grupo deve revisar conteúdo, autoria.
- **Docker:** em 15/11, o Compose da raiz foi compilado e iniciado, o DAG completou as quatro tarefas e o verificador `--faults` aprovou 14 checks, incluindo KNN, AdaBoost, MLflow de hiperparâmetros e recuperação de serviços. Evidências e limites em [entrega de AM](entrega_am_2026-11-15.md). A execução foi uma demonstração simulada; não comprova desempenho físico.
- **Dados reais:** todos os modelos foram treinados com dados simulados. A coleta com participantes segue em `docs/real_data_collection_guide.md`.
- **Airflow:** no Compose, o DAG roda uma vez em lote. O scheduler contínuo fica no perfil `console`.
- **Dashboard:** é a aplicação MotionLab, não Streamlit ou Dash; vale confirmar com o professor que atende ao requisito.
