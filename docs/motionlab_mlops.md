# MotionLab — auditoria e operação de ML/MLOps

> Estado atual: [Fase C — execução integrada e auditoria dos documentos originais](motionlab_fase_c.md). As tabelas abaixo registram o histórico da frente B, anterior à execução dos containers. Enunciado e template originais agora estão em `docs/academico/`; simulação é expressamente aceita pela disciplina.

Data: 11/11/2026. Frente B: ML, integração e evidência acadêmica. A frente visual pertence ao Claude Code; não houve alteração de HTML/CSS/JS, `session.py`, `server.py` ou firmware nesta entrega. Contrato para o frontend: [motionlab_ml_api.md](motionlab_ml_api.md).

## Diagnóstico de conformidade

Este mapeamento usa o checklist do briefing. O enunciado integral e a rubrica da disciplina não foram fornecidos; a tabela não certifica aprovação formal. “Implementado” descreve software. “Validado fisicamente” exige dados e execução na bancada.

| Requisito | Antes da frente B | Entrega e evidência disponível | Lacuna remanescente |
|---|---|---|---|
| Coleta e origem | Coleta CLI e guiada; `RawSampleRecord`; separação real/demo | Validação de sessão e bloqueio de mistura no experimento e na avaliação da UI | Nenhuma sessão real usada nesta entrega |
| EDA | Pré-processamento e contagens; sem EDA com cinco figuras interpretadas | `ml/eda.py`: classes, participantes, série temporal rotulada, falhas por sessão e correlação; SVG + PNG + interpretações | Repetir com corpus real; revisar rótulos e explicações no relatório |
| Holdout | Treino/validação/teste agrupados implementados | Manifesto registra os grupos; seleção por validação e teste externo separado | Mais participantes e distribuição real representativa |
| Validação cruzada | Divisão agrupada não era CV efetiva | `GroupKFold` apenas em treino + validação; estimadores e scaler reajustados por fold | Examinar variância entre grupos reais |
| Leave-one-out | Não executado | `--leave-one-group-out`; exclui participante/sessão inteiro | LOO por janela é inadequado por sobreposição; LOGO depende de grupos suficientes |
| Baseline e ≥3 modelos | Regras, Decision Tree, Random Forest, MLP já existentes | Reutilizados; F1-macro com universo fixo de quatro classes | Superioridade de ML às regras ainda não comprovada em dados reais |
| Métricas e crítica | F1, confusão, FAR, eventos, latência e memória | FAR informa falta de exemplos neutros; latência identificada como notebook e memória como estimativa | Benchmark ESP32, generalização e análise de erro real pendentes |
| Reprodutibilidade | Seeds e bundles existentes | Corpus normalizado, SHA-256 sem arredondar valores, snapshot e hashes do código, configuração, versões, HEAD/estado sujo, grupos e saída isolada por execução | Reexecuções de medição de tempo não são bit a bit determinísticas; novas coletas são novos datasets |
| MLflow | Ausente | SQLite local; run pai, candidatos filhos, parâmetros, métricas, modelos sklearn, bundles, EDA, código e corpus; tuning opcional | UI web do MLflow e servidor Compose não executados nesta entrega |
| API | Reconhecimento integrado à sessão web | Serviço local `ml.inference_api`, inferência por janela e avaliações por origem; CORS local configurável | Frontend pode consumir o novo contrato; esta entrega não altera seus componentes |
| Dashboard | Motion Intelligence já mostrava reconhecedores, rejeições e coleta | Campos aditivos de proveniência no replay; endpoint agregado de experimentos; ausência real retorna `pending` | Exibição dos novos campos deve ser aplicada pela frente A |
| MQTT | Ausente | Paho v2, publisher demo, envelope versionado, ingestão validada/idempotente e publicação atômica de JSONL | Broker e tráfego MQTT não executados nesta entrega; persistência testada diretamente |
| Airflow | Ausente | DAG manual v3: validação → experimento; demo padrão; um run por vez | Importação/execução no runtime Airflow pendentes |
| Docker Compose | Ausente | MQTT, MLflow, ingestão, API e perfis opcionais demo/Airflow; portas no loopback | Build e subida da stack pendentes; YAML foi inspecionado, não equivale a `docker compose up` |
| TinyML | Exportador estático e verificador C++ já existentes | Exportação e paridade executadas em `data/experiments/`, sem sobrescrever firmware | Upload, inferência e latência física não realizados |
| Relatório SBC | Documentação técnica dispersa | [Base textual](relatorio_sbc_base.md), limitações e critérios de evidência | Aplicar template oficial da disciplina; preencher resultados reais e autores |

## Plano de ação e fronteiras

1. Preservar o reconhecimento e o gate existentes. Evoluir o pipeline por um comando novo, sem mudar as rotas `/api/live`, `/api/lab` ou `/api/experience`.
2. Executar corpus separado por origem, reservar teste antes da EDA e registrar tudo em um diretório novo. Esse caminho está implementado.
3. Disponibilizar API e contratos aditivos; a frente visual decide a apresentação sem precisar conhecer arquivos internos de ML.
4. Subir e verificar a stack MLOps em uma janela com memória disponível. Airflow fica em perfil opcional e usa paralelismo 1.
5. Coletar sessões reais com o firmware já instalado, em etapa posterior conduzida com o usuário. Repetir EDA, treino e avaliação real sem incorporar demonstrações.
6. Congelar um conjunto de teste antes de tuning; comparar baseline e modelos por grupo e por eventos. Só então discutir promoção para a UI ou TinyML.

Responsabilidade: Claude em `terminal/web/static/`; Codex em `ml/`, `ops/mlops/`, docs e testes. A única alteração desta entrega no backend visual é aditiva em `terminal/motionlab/dataset.py`: bloqueio de corpus contaminado e metadados de avaliação. Arquivos compartilhados `session.py` e `server.py` não precisaram de edição.

## Ambiente local reproduzível

Use o venv do projeto. O lock universal fixa dependências do pipeline, com wheel de `cryptography` compatível com Windows ARM64. Não inclui Airflow no notebook; o runtime dele está no container próprio.

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements.txt -r requirements-mlops.lock --only-binary :all:
```

O runtime visual continua funcionando sem instalar os extras de MLOps. As importações de matplotlib e MLflow ocorrem apenas ao solicitar os respectivos passos. O lock pode ser regenerado explicitamente:

```powershell
uv pip compile pyproject.toml --extra mlops --universal -c requirements.txt --output-file requirements-mlops.lock
```

## Experimento completo sem hardware

```powershell
# Gera somente dados declaradamente sintéticos, caso o corpus ainda não exista.
.\.venv\Scripts\python.exe -m ml.collection --generate-synthetic-corpus --output-dir data/raw/synthetic

# Baseline + três modelos, cinco figuras de EDA, GroupKFold, LOGO,
# tuning limitado da árvore, holdout, exportação isolada, paridade e MLflow.
.\.venv\Scripts\python.exe -m ml.experiment --raw-dir data/raw/synthetic --cohort synthetic --leave-one-group-out --tune --verify-cpp --tracking-uri sqlite:///data/mlflow/tracking.db
```

O comando retorna o diretório exato da execução em `data/experiments/synthetic/<experiment_id>/`. A origem precisa corresponder a **todos** os registros: `real` aceita somente `real_hardware`; `demo` e `synthetic` aceitam somente `synthetic_simulator`. A diferença demo/synthetic é a finalidade declarada pelo produtor; a metadata não prova a origem física de uma amostra. Mistura é bloqueada, não filtrada silenciosamente.

Cada execução preserva:

- `manifest.json`: status, origem, hash, ambiente, configuração, qualidade, grupos, CV/LOGO, tuning, tracking e exportação.
- `corpus.jsonl`, `features.csv`, `source/`: entradas normalizadas e código necessário à reprodução do pipeline.
- `models/*.joblib` e `.meta.json`: quatro candidatos e cópia do selecionado; grupos de treino/desenvolvimento e identificadores de rastreabilidade.
- `evaluation.json` e `.md`: avaliação externa dos candidatos; escolha feita na validação, sem escolher pelo F1 de teste.
- `eda/`: cinco figuras PNG/SVG, interpretações e resumo estruturado no manifesto.
- `export/tinyml_model.h`: código gerado; o firmware do repositório não é destino deste comando.

`latest.json` só aponta para uma execução após sucesso de todos os passos solicitados. Uma falha conserva manifesto `failed` e não substitui o último resultado completo. O experimento não promove automaticamente o modelo da aplicação.

O `--tune` compara somente profundidades 3, 5 e 7 de Decision Tree, com desempate pela menor profundidade. O teste externo não entra nos trials. CV reutilizada depois do tuning é descritiva e não é estimativa independente; o holdout externo permanece a avaliação final. Com poucos grupos, folds sem todas as classes no treino são explicitamente incompletos, sem médias artificiais de sucesso. LOGO e GroupKFold com tantos folds quanto grupos são equivalentes; não são duas evidências independentes.

O caminho antigo `ml.real_pipeline` continua disponível e mantém seus defaults históricos, inclusive destino no firmware. Para este trabalho use **`ml.experiment`**, cujo destino padrão é isolado.

## MLflow

Experimentos separados: `MotionLab-real`, `MotionLab-synthetic` e `MotionLab-demo`. Cada execução registra um pai, quatro candidatos filhos (`baseline` ou `comparison`) e, quando solicitado, três filhos `tuning`. As métricas de teste são registradas após a escolha. Registrar métricas não autoriza usá-las repetidamente para refazer a seleção.

O cliente `mlflow-skinny` com SQLite foi executado localmente. Os modelos usam a flavor sklearn com código do pipeline e serialização `cloudpickle`, coerente com os bundles joblib existentes. Carregue somente artefatos locais confiáveis. O servidor completo, com UI, é fornecido pelo serviço `mlflow` do Compose; o extra local não instala toda a stack de servidor.

O snapshot permite reproduzir código ainda não commitado sem capturar `.env` ou credenciais. O corpus contém identificadores de participantes e pode ser copiado para os artefatos MLflow; use identificadores pseudônimos e só publique coletas autorizadas.

## MQTT, Airflow e Compose

Os arquivos estão em `ops/mlops/`. Em Windows, `docker` chama o Engine do WSL. Nesta máquina a memória livre era aproximadamente 2 GB no início da tarefa; a stack não foi iniciada. Configuração preparada não é validação de containers.

```powershell
docker compose -f ops/mlops/compose.yaml config
docker compose -f ops/mlops/compose.yaml up -d --build mqtt mlflow ingest api

# Após ingest estar conectado e inscrito (logs), publica cinco sessões demo.
docker compose -f ops/mlops/compose.yaml logs ingest
docker compose -f ops/mlops/compose.yaml --profile demo run --rm publisher

# Opcional, mais pesado: runtime acadêmico de orquestração.
docker compose -f ops/mlops/compose.yaml --profile orchestration up -d --build airflow
```

As portas são MQTT 1883, MLflow 5000, API 8768 e Airflow 8080, publicadas apenas em `127.0.0.1`. O broker permite acesso anônimo na rede local do Compose; esta é uma configuração de laboratório, sem autenticação de participantes. O Airflow usa `standalone`, volume persistente e DAG manual `motionlab_experiment`. O padrão é `{"cohort":"demo"}`; `real`/`synthetic` são escolhas explícitas da configuração do run. O DAG não abre portas seriais nem grava firmware. SQLite + standalone são adequados à demonstração local, não a uma implantação distribuída.

Tópicos: `motionlab/v1/sessions/demo`, `/synthetic` e `/real`. Cada mensagem QoS 1 contém uma sessão completa (até 4 MiB no consumidor). Exemplo executável de construção do envelope:

```python
from ml.collection.synthetic import generate_synthetic_session

rows = generate_synthetic_session("demo_p01", "session_demo_p01", seed=42)
payload = {"schema_version": 1, "cohort": "demo", "records": [r.to_dict() for r in rows]}
```

`data_origin` e campos de rastreabilidade são obrigatórios; tópico e cohort precisam coincidir. O consumidor grava por origem, exige índices contíguos e timestamps crescentes e reconhece a mensagem após persistência. Mensagens inválidas são rejeitadas com log e ACK; erro de disco não recebe ACK. A assinatura usa sessão persistente com client ID fixo `motionlab-ingest-v1`: rode apenas uma instância desse consumidor por broker. Mesmo `session_id` e conteúdo são deduplicados; conteúdo conflitante é rejeitado. O consumidor padrão nem se inscreve no tópico real; `--allow-real` é necessário, sem converter dados sintéticos em reais. Aguarde os logs `subscribed` antes de publicar.

O publisher é uma demonstração de sensores, não uma emulação física validada. A entrega entre publicador e consumidor depende de o consumidor já estar inscrito: QoS 1 não substitui um protocolo de confirmação de sessão pela aplicação. Não há bridge serial→MQTT neste escopo.

Para executar componentes fora do Docker, com um broker já disponível:

```powershell
.\.venv\Scripts\python.exe -m ml.mqtt_ingestion consume
.\.venv\Scripts\python.exe -m ml.mqtt_ingestion publish-demo
.\.venv\Scripts\python.exe -m ml.experiment --raw-dir data/raw/demo --cohort demo
```

## Evidência e próximos passos físicos

Contam como evidência de **software**: testes, chamadas HTTP reais em loopback, rastreamento SQLite real, figuras exportadas, CV agrupada sobre simulação e paridade numérica C++. Não contam como desempenho físico: F1 sintético, dados gerados nos testes, latência Python ou estimativa de memória embarcada. `physical_validation=pending` persiste mesmo ao avaliar offline um corpus declarado real.

Para validação posterior, sem exigir novo firmware:

1. Usar a coleta guiada existente com a placa e identificadores pseudônimos. COM3 deve estar disponível e ser usada somente pela thread principal com o usuário.
2. Coletar ao menos três grupos independentes para o holdout; preferir mais participantes e sessões em horários/condições distintos. Três é o mínimo operacional, não garantia estatística.
3. Revisar qualidade temporal e rótulos; registrar condições e falhas. Preservar repouso longo para medir falsos acionamentos.
4. Reservar participantes/sessões de teste antes da exploração e executar `ml.experiment --raw-dir data/raw/real --cohort real ...`.
5. Comparar regras e ML no mesmo conjunto reservado, por classe e evento. Relatar variância entre grupos, suporte, falhas e limitações; não prometer significância estatística sem amostra suficiente.
6. Validar uso gestual real e rejeições. Medição/embarque de um novo TinyML fica em tarefa específica autorizada; não faz parte desta entrega.

## Verificações desta entrega

Executadas em 11/11/2026:

| Comando / verificação | Resultado observado |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q --junitxml=data/experiments/pytest-results.xml` | 584 casos, **581 aprovados e 3 pulados**, zero falhas/erros, 55,818 s. Os skips exigem `FRITZING_PARTS_DIR`. |
| `node --test tests/test_web_ui.cjs tests/test_guide_ui.cjs tests/test_lab_ui.cjs` | **17 aprovados**, zero falhas, aproximadamente 0,15 s. |
| `ml.experiment` com corpus sintético, `--leave-one-group-out --tune --verify-cpp --tracking-uri sqlite:///data/mlflow/tracking.db` | Sucesso; execução `20261111T191103_0b31c562`, 1.789 amostras, 798 janelas, 5 participantes simulados. |
| Verificador C++ da execução acima | 162 janelas, concordância de classes 100%, diferença máxima de probabilidade `4,3e-7`; compilação/execução nativa MSVC e verificação de sintaxe Xtensa aprovadas. Não executado na placa. |
| MLflow SQLite | Pai `3b731eead0f5471890d5ab0ab7e80e54` e 7 filhos concluídos: 1 baseline, 3 comparações e 3 trials de tuning. Os testes também recarregam os quatro modelos registrados e comparam predições. |
| API HTTP em servidor loopback nos testes | Inferência confere com o estimador local; avaliações mantêm `real=pending`; entrada inválida retorna 400; preflight CORS local retorna 204. |
| Persistência MQTT | Testes de idempotência, conflito, origem, campos ausentes, NaN, índices e travessia de diretório. Broker/rede MQTT não exercitados. |
| `python -m compileall -q ml ops/mlops/dags` e leitura de `compose.yaml` com PyYAML | Sintaxe Python e YAML válidas; seis serviços descritos. Não é importação de DAG pelo Airflow nem validação pelo Engine Docker. |
| `git diff --check`; `git diff --quiet -- firmware` | Sem erro de whitespace; nenhum diff no firmware. |

Logs e JUnit ficam em `data/experiments/` (ignorados pelo git). A suíte rápida usa MLP com 80 iterações e emite avisos de não convergência esperados para fixture sintética; eles não representam treino final nem evidência de qualidade. MLflow/SQLAlchemy também emitem aviso de depreciação sem falha de execução. O pipeline completo usa a configuração padrão, registrada no manifesto.

## Arquivos desta frente

Esta lista exclui as alterações do MotionLab/redesign que já estavam no checkout e foram preservadas.

| Área | Arquivos criados ou modificados nesta frente |
|---|---|
| Pipeline e rastreamento | `ml/experiment.py`, `ml/validation.py`, `ml/eda.py`, `ml/tracking.py`, `ml/training/trainer.py` |
| Avaliação e API | `ml/evaluation/metrics.py`, `ml/evaluation/report.py`, `ml/inference_api.py`, `ml/provenance.py`, `terminal/motionlab/dataset.py` |
| Ingestão e infraestrutura | `ml/mqtt_ingestion.py`, `ops/mlops/compose.yaml`, `ops/mlops/Dockerfile`, `ops/mlops/Dockerfile.airflow`, `ops/mlops/mosquitto.conf`, `ops/mlops/dags/motionlab_experiment.py` |
| Dependências e artefatos locais | `pyproject.toml`, `requirements-mlops.lock`, `.gitignore` |
| Documentação e coordenação | `README.md`, `AGENTS.md`, `docs/motionlab_mlops.md`, `docs/motionlab_ml_api.md`, `docs/relatorio_sbc_base.md` |
| Testes | `tests/test_mlops.py` (21 casos) |
