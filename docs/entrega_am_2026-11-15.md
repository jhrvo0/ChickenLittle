# Entrega de Aprendizado de Máquina

> **Atualização em 16/11:** este documento registra a execução de 15/11 com 5 participantes. Os resultados vigentes (12 participantes, StratifiedGroupKFold, comparação estatística e relatório reescrito) estão em [aprendizado_maquina.md](aprendizado_maquina.md#resultado-de-referência-corpus-simulado-seed-42).

Esta revisão foi iniciada em 15/11/2026, após os merges dos PRs #1, #2 e #3 (HEAD `51dd39d`). A branch local é `verificacao/entrega-ml`. Não houve commit, push, merge, acesso serial nem gravação da placa.

## Como se situar no trabalho

O problema é classificar quatro gestos com dois sensores: neutro, aproximação, afastamento e permanência. A parte de AM precisa demonstrar que a comparação é válida e reproduzível, explicar os erros e mostrar o modelo integrado ao sistema. A nota depende da rubrica e da avaliação do professor; passar testes não equivale a cumprir toda a avaliação acadêmica.

O código já contém os cinco modelos da lista (árvore, floresta, MLP, KNN e AdaBoost), duas referências de baseline, busca de hiperparâmetros, EDA, validação por participante, MLflow, Airflow e API. O ponto principal a dominar é a separação dos participantes: janelas sobrepostas da mesma sessão não podem aparecer em treino e teste.

## Evidências desta execução

- [Logs, manifesto e métricas](evidencias/am-2026-11-15/).
- [Notebook executado](../notebooks/motionlab_bootstrap.ipynb).
- [Relatório SBC em PDF](../reports/relatorio_aprendizado_maquina.pdf), [editável](../reports/relatorio_aprendizado_maquina.docx) e [texto](../reports/relatorio_aprendizado_maquina.md). É candidato à revisão do grupo, não submissão automática. Autores foram preservados conforme o README.
- Experimento local `20261116T021459_3b94f6f7`: 1.789 leituras, 798 janelas, cinco participantes **simulados**; treino com três, validação com um e teste com um. O ID usa UTC; o início local foi em 15/11.
- F1-macro no teste: regras 0,5518; baseline árvore rasa 0,3342; árvore 0,7856; floresta 0,8843; MLP 0,9094; KNN 0,8375; AdaBoost 0,5951. São resultados do simulador.
- Busca completa: 67 combinações nas cinco famílias, com GroupKFold apenas no desenvolvimento. GroupKFold e LOGO coincidem neste conjunto de quatro grupos; não são evidências independentes.
- Dois experimentos MLflow locais concluídos: `MotionLab-synthetic` e `MotionLab-synthetic-hiperparametros`, em `data/experiments/mlflow.db` (ignorado pelo Git).
- Paridade Python/C++ nativa aprovada em 162 janelas; execução e tempo na ESP32 continuam pendentes.

## Reprodução local

Usar Python >=3.11 em `.venv` (a execução usou 3.12.14). Estes comandos são para macOS/Linux; no Windows, adaptar `.venv/bin/python` para `.venv\Scripts\python.exe`. O `uv` não estava disponível nesta máquina; a instalação usou o pip do próprio ambiente, sem instalação global.

```sh
.venv/bin/python -m pip install -r requirements.txt -r requirements-mlops.lock
.venv/bin/python -m pytest -q --junitxml=docs/evidencias/am-2026-11-15/pytest.xml
node --test tests/test_lab_ui.cjs tests/test_web_ui.cjs tests/test_guide_ui.cjs
.venv/bin/python -m ml.collection --generate-synthetic-corpus --output-dir data/raw/synthetic
.venv/bin/python -m ml.experiment --raw-dir data/raw/synthetic --cohort synthetic --extended-models --learned-baseline --search grid --leave-one-group-out --tune --verify-cpp --tracking-uri sqlite:///data/experiments/mlflow.db
.venv/bin/python -m ml.academic_notebook data/experiments/synthetic/<run>
```

Cada experimento gera seu diretório e seu identificador; use o caminho exibido pelo comando. Artefatos em `data/experiments/` são locais; as cópias selecionadas em `docs/evidencias/` preservam os resultados desta execução. Regenerar o corpus muda metadados e pode mudar seu hash; o manifesto identifica a versão efetivamente usada. Não altere modelos ou hiperparâmetros com base nos erros do teste reservado.

O verificador da stack tinha uma chamada fixa ao WSL. Foi corrigido para usar Docker nativo no macOS/Linux e preservar Windows/WSL. `--compose-file` permite indicar outro checkout no WSL. Dois testes cobrem os dois caminhos.

## Demonstração final e pendências do grupo

1. Iniciar a stack com `docker compose up --build`. Mostrar uma sessão **simulada** chegando pelo MQTT, o JSONL persistido e as quatro tarefas do DAG concluídas. O perfil `console` fornece a interface do Airflow.
2. Abrir MLflow e explicar parâmetros, métricas, modelos e os dois experimentos. Comparar baselines com as cinco famílias e mostrar os erros de HOLD.
3. Mostrar `/v1/status`, inferência e Motion Intelligence. Explicar que API pronta e origem física não comprovam acurácia física. Rodar o verificador com `--faults` e mostrar recuperação dos serviços.
4. Coletar participantes reais seguindo [o guia](real_data_collection_guide.md), com autorização e sessões independentes. Reservar participantes antes da EDA, manter coortes separadas e executar novo experimento `--cohort real`.
5. Revisar o artigo SBC: nomes, afiliação, análise, limite de páginas e referências exigidas pela disciplina. A especificação integral de AM não está anexada nesta cópia; a matriz do repositório e o prompt são as referências disponíveis, não substituem a rubrica original.
6. Confirmar com o professor a aceitação do dashboard próprio e dos índices de diretórios. Autoria de commits, Issues/Projects e licença exigem decisão do grupo; não criar contribuições fictícias ou escolher licença por conta própria.
7. Na máquina da bancada, compilar e confirmar a plataforma instalada antes de fixar sua versão. Não foi instalado PlatformIO aqui; não foram compiladas nem gravadas mudanças de firmware. Ensaios físicos devem ser conduzidos com o responsável pela placa.

As evidências do checkpoint de Embarcados permanecem como registro histórico. Não atualizar seus números retrospectivamente; citar esta execução separadamente.

## Resultado final da verificação

- **674 testes Python coletados: 669 aprovados, cinco pulados, zero falhas/erros**. Três skips exigem `FRITZING_PARTS_DIR`; dois exigem Windows/WSL. XML e log estão nas evidências. As advertências de convergência vêm de testes que limitam propositalmente o treino a 80 iterações; o log as conserva.
- **20 testes de interface aprovados**.
- **Compose compilado e iniciado na raiz**, com `docker compose up --build -d`. O modo destacado foi usado para acompanhar os logs sem bloquear a sessão. O Docker Desktop precisou ser iniciado fora do sandbox; a mensagem inicial de executável ausente não era o estado final.
- **14 checks de integração e recuperação aprovados**, via `.venv/bin/python ops/mlops/verify_stack.py --faults --output docs/evidencias/am-2026-11-15/integration.json`. O comando padrão agora usa o Compose da raiz no macOS/Linux, para atingir o mesmo projeto iniciado ali. Windows/WSL mantém o caminho da bancada; quem iniciar pela raiz no Windows deve passar `--compose-file /mnt/<caminho>/docker-compose.yml` explicitamente.
- DAG `manual__2026-11-16T02:22:20.709198+00:00`: quatro tarefas aprovadas; total 23,50 s. A tarefa `experiment`, incluindo Grid Search, treino e MLflow, levou 20,77 s, com limites de 1 CPU e 1,4 GB. Não foi medido separadamente o tempo exclusivo da grade; não foi necessário trocar para busca aleatória.
- Comparação estendida no MLflow da stack: sete modelos salvos (cinco famílias e dois baselines), dez runs filhos no experimento de comparação, mais o experimento `MotionLab-demo-hiperparametros`.
- Coorte **DEMO** da stack: run `20261116T022223_2905d60b`, MLP publicada, F1-macro 0,966 em 80 janelas de teste. É um corpus diferente do experimento **synthetic** local de 162 janelas de teste; não comparar os valores como melhoria de modelo. Ambos têm origem simulada e validação física pendente.
- [Captura do dashboard](evidencias/am-2026-11-15/dashboard.jpg), [MLflow](evidencias/am-2026-11-15/mlflow.jpg), [API](evidencias/am-2026-11-15/api-status.jpg) e [Airflow](evidencias/am-2026-11-15/airflow.jpg). A revisão visual do painel confirmou modelo publicado, cinco candidatos e identificação DEMO. O campo histórico `visual_integration=manual_review` no verificador não realiza uma inspeção visual; esta captura é a evidência separada.
- Airflow console foi iniciado com `docker compose --profile console up -d --no-deps airflow-ui`, usando o histórico existente, e parado após a captura para liberar memória. Dashboard, API, MLflow, broker e consumidor ficaram ativos. Para encerrar os serviços desta execução: `docker compose --profile console down` (preserva os volumes; não usar `-v`).

Pendências finais: coleta/avaliação real, ensaio do firmware na bancada, revisão do artigo pelo grupo e confirmação da rubrica com o professor. A licença, a autoria de contribuições e a aceitação da estrutura exigem decisão humana. Nenhuma dessas pendências foi marcada como concluída por inferência.

## Encerramento após a revisão

Por solicitação do usuário, os containers e a rede desta execução foram removidos com `docker compose --profile console down`, preservando volumes e dados. O Docker Desktop/VM foi parado com `docker desktop stop`; não restou processo `com.docker.backend` nem listeners da demonstração nas portas 8767, 8768 e 8080. A porta 5000 restante pertence ao Control Center do macOS, não ao MLflow. As abas temporárias já estavam encerradas. A regra de encerrar recursos iniciados pelo agente foi registrada no docs/README.md.
