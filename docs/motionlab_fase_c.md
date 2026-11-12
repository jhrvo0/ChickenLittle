# MotionLab — Fase C: integração e auditoria acadêmica

Data: 11/11/2026. Escopo: software com aquisição simulada. Sem COM3, coleta física, alterações de firmware ou arquivos visuais. Esta auditoria substitui o estado operacional da frente B em `motionlab_mlops.md`, que permanece como histórico.

> Registro da Fase C: referências abaixo à integração visual pendente descrevem aquela entrega. A interface Motion Intelligence foi conectada posteriormente na Fase D; a integração física e as demais validações não são comprovadas por essa alteração. Consulte o [índice](README.md) e a [Fase E](motionlab_fase_e.md).

## Conclusão e limites da entrega

Foi executado o caminho **simulador → Mosquitto → consumidor → JSONL → Airflow → preparação/treino/CV/tuning → MLflow HTTP → publicação do modelo → API → backend do dashboard**. Uma sessão nova também foi processada automaticamente depois do treino, sem reiniciar o modelo ou solicitar uma inferência manual. A exibição dos novos resultados acadêmicos na tela do Motion Intelligence ainda depende do Claude Code. Portanto, **a arquitetura de backend foi demonstrada; a entrega acadêmica completa permanece parcial**.

Airflow foi executado no runtime oficial 3.1.6, com banco persistente, XCom e quatro tasks reais, usando `airflow dags test`. Isso não é um mock nem simples importação do DAG. O Compose executa o DAG de ponta a ponta em lote. O scheduler e a UI de `airflow standalone` são um perfil adicional; sua execução contínua não é comprovada por `dags test`.

O enunciado permite sistema embarcado **físico ou simulado**. Assim, a ausência de coleta física não bloqueia essa alternativa acadêmica. Ela limita conclusões sobre pessoas, sensores reais, ESP32 e desempenho embarcado. `physical_validation=pending` é preservado.

## Fontes originais e critérios de avaliação

Os arquivos estavam em Downloads e foram copiados sem alteração para `docs/academico/`. Ambos foram lidos integralmente, incluindo tabelas, instruções finais e conteúdo de cabeçalhos/rodapés do template:

| Fonte | SHA-256 |
|---|---|
| `[CESAR School] - AM - Especificação de Projeto .docx` | `0786c7d1ea7859df77f0f6572f7cf5e9a40c04191371f65351582ed16f5d28ea` |
| `sbc_template.docx` | `5497e7a8fb846cf536c90c85488a18997fb94bd1deebdd9a7976153e07019cb1` |

O projeto vale 60% da segunda unidade e é desenvolvido em grupo. A tabela de avaliação informa Análise de Dados 15%, Modelagem e Validação 30%, MLOps 25% e Comunicação 20%: **a soma é 90%, não 100%**. Não foi atribuída interpretação aos 10% ausentes; o grupo precisa esclarecer com o professor.

O formato SBC é obrigatório, sem alterações de margens, fontes, espaçamento ou colunas. A especificação prevê zero no bloco Comunicação para relatório fora do formato. Também solicita apresentação da arquitetura inteira, justificativas técnicas e discussão de limitações. README deve conter membros com nome/sobrenome e @GitHub, nome da solução, instruções detalhadas e link do Google Sites.

O texto do template manda A4, uma coluna, margens superior/inferior/laterais de 3,5/2,5/3 cm, Times 12, sem cabeçalhos, rodapés ou numeração. O próprio DOCX ainda contém cabeçalhos/rodapés históricos de SIBGRAPI e início de numeração em 101. O original foi preservado; essa divergência precisa ser observada ao preparar o artigo final. Resumo e abstract, para artigo em português, ficam na primeira página e têm até dez linhas cada.

## Contratos e correções

- **MQTT v1 preservado:** sessão completa, tópico e `cohort` coincidentes, origem obrigatória, índices contíguos, timestamps crescentes e persistência atômica. QoS 1 é complementado por recibo em `motionlab/v1/receipts/<session_id>`, contendo hash do corpus. Publisher só termina depois da confirmação da aplicação.
- **Persistência:** JSONL por sessão, separado em `real`, `synthetic`, `demo`; JSON de metadados/previsões; SQLite para MLflow e metadados do Airflow. Um servidor PostgreSQL separado não é obrigatório no enunciado e não foi acrescentado.
- **Airflow:** configuração → snapshot validado e features preparadas → experimento → publicação. Código científico usa venv separado do Airflow, evitando substituir suas dependências. A configuração e o manifesto registram o run exato do DAG.
- **Modelo:** `latest.json` continua catálogo, sem promoção implícita. Apenas `deployment.json`, validado por manifesto, origem e SHA-256, promove o modelo da demonstração. Outros cohorts exigem decisão do operador. Publicação inválida ou bundle ilegível deixam a inferência pendente, sem previsões fictícias.
- **Consumo automático:** worker da API detecta sessões persistidas, usa filtro causal, classifica a última janela e publica resultados identificados por modelo, corpus e versão de processamento. Rótulos verdadeiros não selecionam a janela de inferência. Cache sobrevive ao restart e não mistura modelos diferentes.
- **Dashboard:** novas rotas autenticadas `/api/ml/status`, `/evaluations`, `/predictions`, `/infer` no backend. São da mesma origem e funcionam com a CSP existente. `/api/live`, `/api/lab`, `/api/experience`, ações e gate mantêm os contratos anteriores. Nenhum HTML/CSS/JS foi alterado nesta fase.
- **Baseline acadêmico:** o DAG habilita uma árvore de profundidade 1 aprendida, além de Decision Tree, Random Forest, MLP e regras. A configuração antiga continua com os quatro candidatos anteriores; regras permanecem referência de domínio e não são apresentadas como aprendizado estatístico.
- **Evidência ausente:** relatório Markdown escreve FAR não estimável; MLflow omite essa métrica e registra status/suporte; a seleção não dá crédito de FAR quando não há neutros. API oferece `far_neutral.value=null`, preservando os campos antigos por compatibilidade.
- **Reprodução:** snapshot inclui `ml`, `terminal` e `simulator`; importação fora do checkout foi testada. Bases Docker fixadas por digest, dependências do servidor em `ops/mlops/requirements-server.lock`, builds sequenciais e exclusões de dados/venvs no contexto Docker.

Contrato completo e exemplos para o Claude: [motionlab_ml_api.md](motionlab_ml_api.md#extensão-fase-c-para-o-claude-code). `input_origin`, `training_cohort` e `trained_on` são independentes. REAL, SYNTHETIC, DEMO e PENDING nunca são convertidos uns nos outros para preencher o dashboard.

## Auditoria contra a especificação original

“Atendido” nesta tabela significa atendido na demonstração **simulada de software**, quando indicada. Não significa comprovação física ou aceite formal do professor.

| Requisito original | Classificação | Evidência / limite |
|---|---|---|
| Bootstrap, EDA em notebook, estatísticas e preparação justificada | Atendido | `notebooks/motionlab_bootstrap.ipynb`, gerado e executado sobre o corpus do run; lê dados, separa grupos, calcula estatísticas, explica filtro causal, flags e scaler |
| Mínimo de cinco visualizações interpretadas | Atendido | Cinco figuras EDA de desenvolvimento, SVG/PNG, interpretações no manifesto e notebook; uma figura comparativa adicional com matrizes |
| Holdout e validação cruzada | Atendido | Manifesto reserva participante de teste antes da EDA; GroupKFold reajusta modelos e scaler só no desenvolvimento |
| Leave-One-Out quando aplicável | Atendido com justificativa | LOGO exclui grupo inteiro; LOO por janela sobreposta criaria dependência. Com quatro grupos de desenvolvimento, LOGO e GroupKFold podem coincidir |
| Estabilidade, overfitting/underfitting e generalização | Atendido no cenário simulado | Notebook executa F1 de treino/validação/teste, diferenças e média/desvio dos folds; análise concreta abaixo. Transpor a discussão para o relatório/apresentação ainda é necessário |
| Otimização e justificativa | Atendido | Busca em grade explícita de profundidades 3/5/7, somente desenvolvimento; trials e escolha registrados. Espaço limitado pelo orçamento embarcado; teste externo não escolhe hiperparâmetros |
| Baseline treinado e justificativa | Atendido | `decision_stump_baseline`, árvore depth 1 aprendida e de baixa capacidade, com métricas; regras são referência adicional |
| Pelo menos três modelos distintos e métricas apropriadas | Atendido | Decision Tree, Random Forest e MLP; F1 macro, acurácia, suporte, confusão, FAR e eventos. Baseline aprendido separado |
| Visualização comparativa e análise crítica | Atendido no cenário simulado | Matrizes e resultados do run no notebook, menor recall calculado e análise abaixo; conclusões limitadas ao gerador |
| MLflow: parâmetros, métricas, artefatos, modelos e experimentação | Atendido | Servidor HTTP real; pai + cinco candidatos + três trials, todos FINISHED, modelos/artefatos persistidos. São nove runs dentro de `MotionLab-demo`; cohorts têm experimentos separados |
| Aquisição simulada → MQTT → persistência | Atendido | Cinco participantes simulados, recibos com hashes e JSONL; nova sessão posterior; testes de duplicação, conflito e tópico incorreto |
| Airflow: fluxo automatizado de preparação/disponibilização | Atendido na demonstração em lote | Compose liga publisher confirmado ao DAG real de quatro tasks; snapshot, CSV de features, treino, MLflow e publicação. Scheduler/UI contínuos não comprovados por esse modo |
| Console/scheduler contínuo do Airflow | Bloqueado nesta rodada por memória | Perfil `console` preparado; orçamento insuficiente para validá-lo com os demais aplicativos. O runtime do DAG em lote foi executado |
| Modelo validado integrado e consumo automático de novos dados | Atendido | Publicação identificada pelo experimento; nova sessão MQTT passa automaticamente ao worker e `/v1/predictions`, sem novo treino |
| Inferências disponíveis por API | Atendido | HTTP `/v1/infer`, previsão automática e proxy do dashboard exercitados; saída/proveniência conferidas |
| Dashboard interativo com aquisição, indicadores, métricas, inferências e monitoramento | Parcial | Interface existente servida; backend consome API e mantém módulos durante falha dela. **Novas métricas e previsões ainda não foram ligadas à tela pelo Claude** |
| Compose com principais serviços e um comando | Atendido para backend; apresentação parcial | MQTT, persistência, Airflow, MLflow, API e dashboard no mesmo Compose; `stack.ps1` contorna paths/Buildx/WSL deste Windows. Lacuna visual impede declarar toda a apresentação final concluída |
| Reprodutibilidade | Atendido no escopo de software | Locks, digests, seed, corpus e hashes, código, grupos, IDs de runs e verificador. Tempo/latência não são bit a bit determinísticos |
| Demonstração final de toda a arquitetura | Parcial | Backend real demonstrado; apresentação visual final e discussão do grupo pendentes |
| Relatório PDF no template SBC | Pendente | Há base textual e evidências; não há artigo final diagramado/PDF com autores e referências concluídas |
| README com equipe/@GitHub/Google Sites | Parcial | Nome e execução documentados; dados da equipe e URL oficial precisam ser fornecidos, sem inventar identidades |

## Resultados do cenário final e análise

Experimento `20261111T200245_b7c2e150`, cohort DEMO: **896 amostras, 395 janelas, cinco participantes simulados**, três grupos de treino, um de validação e um de teste reservado. Airflow `manual__2026-11-11T20:02:37.415864+00:00`, quatro tasks `success`, duração 50,206 s. MLflow: pai `2891cdd2ced34bb5bbe337e096d59768`, oito filhos `FINISHED` e cinco modelos salvos. Dataset SHA-256 `9951827210f1f27a06157c8a0d3c31bf76e33f76943aa7ed09259c1bf0e514eb`; modelo publicado SHA-256 `8e6dc933beeb1a794a26d3509a2f6e7054a0eef41bedc364f74d5a8a1c30b218`.

Valores abaixo foram lidos do run e das células executadas do notebook, não criados para apresentação. F1 macro usa as quatro classes do contrato; desvio é o desvio populacional entre quatro folds de desenvolvimento, não intervalo de confiança.

| Modelo | F1 treino | F1 validação | F1 teste reservado | F1 médio CV | Desvio CV |
|---|---:|---:|---:|---:|---:|
| Árvore depth 1, baseline aprendido | 0,3391 | 0,3279 | 0,3548 | 0,3383 | 0,0075 |
| Regras, referência de domínio | 0,5057 | 0,5253 | 0,5718 | 0,5092 | 0,0128 |
| Decision Tree | 0,9309 | 0,7379 | 0,5961 | 0,7151 | 0,0361 |
| Random Forest | 0,9716 | 0,8729 | 0,8466 | 0,8055 | 0,1021 |
| MLP compacto | 0,9929 | 0,8962 | 0,9713 | 0,8555 | 0,0440 |

A árvore simples apresenta baixo desempenho em treino e validação, compatível com a capacidade limitada de apenas duas folhas para quatro classes: é uma referência aprendida de subajuste, não o modelo de produção. A árvore mais profunda tem diferença treino–validação de aproximadamente 0,193 e queda adicional no participante de teste; isso é um indício de sobreajuste ou mudança entre grupos neste gerador. A floresta reduz a queda no teste, mas tem a maior variabilidade entre folds. O MLP foi selecionado pelos critérios de validação e custo estimado; o F1 maior no teste do que na validação mostra que o participante reservado foi mais favorável nessa partição. Não autoriza escolher novamente pelo teste nem concluir ausência de sobreajuste.

As matrizes no notebook mostram quais classes geram os erros; as células também identificam a menor revocação por modelo, para evitar que F1 agregado esconda uma classe fraca. Somente cinco participantes **simulados** sustentam estes valores. Diferenças entre folds não comprovam significância estatística, e a proximidade do problema com as regras do gerador pode facilitar ML. Nenhuma dessas métricas demonstra generalização para pessoas/sensores físicos. Repetições para depurar software não são novos testes independentes de hipótese.

Verificações finais: `pytest` **594 casos, 591 aprovados, 3 pulados, zero falhas/erros**, 114,264 s nesta máquina sob carga; os três skips dependem de `FRITZING_PARTS_DIR`. `node --test` **17 aprovados**, zero falhas. Verificador de stack: **13 checks reais aprovados**, incluindo estado do DAG, oito filhos e cinco modelos no MLflow, inferência HTTP, proxy, nova sessão, duplicação, entradas inválidas e reinícios. Drill separado: DAG inválido retornou código 1 e preservou a publicação. Os nove arquivos visuais mantiveram os hashes iniciais, o staged ficou byte a byte idêntico e não há diff de firmware.

## Ambiente, incidentes e encerramento

Windows ARM64, sem administrador Windows, Engine Linux ARM64 no WSL; limite WSL existente de 6 GB foi preservado. As imagens consultadas oferecem ARM64. O ambiente tinha aproximadamente 2 GB livres antes da subida; a memória oscilou durante builds, com recuperação depois deles.

Incidentes encontrados e tratados:

1. Docker Buildx ausente: o launcher usa o builder clássico existente (`DOCKER_BUILDKIT=0`), sem instalação global.
2. Consulta inicial ao Docker Hub sofreu timeout, mas os pulls posteriores funcionaram.
3. MLflow sofreu OOM com limite de 512 MB. Limite passou a 1 GB e jobs GenAI não usados foram desativados; consumo observado em regime aproximadamente 365–422 MiB. Isso é consumo amostrado, não pico garantido.
4. Volume novo do Airflow tinha proprietário root e o entrypoint aguardava um banco ainda não migrado. Serviço de inicialização ajusta **somente esse volume**, com usuário root no container, e a migração ocorre antes do DAG. Não há elevação no Windows.
5. A instância WSL encerrou junto com os containers entre chamadas sem um processo persistente. Um helper com flag exclusiva da tarefa mantém a janela da demonstração; PID é registrado e remover a flag faz o processo Linux terminar. Nenhuma configuração global do WSL foi alterada. A janela desse helper é de duas horas; para uso contínuo, manter uma sessão WSL ativa.
6. Falha provocada de DAG (`cohort=invalid`) retorna código 1, tasks downstream `upstream_failed`, sem substituir `deployment.json`. Falhas de broker, consumidor, API e MLflow foram exercitadas com recuperação.

Os logs do operador Python externo também contêm a checagem opcional de `pendulum` ausente no venv científico. As funções não usam contexto temporal do Airflow nesse ambiente; as quatro tasks terminaram em `success`. Essa mensagem não foi contabilizada como falha de execução, nem usada para omitir o estado real do DAG.

O perfil opcional `console` executa `airflow standalone` com limite próprio de 1800 MB. **Não foi iniciado nesta validação por orçamento de RAM**: a amostra registrada em `memory-before-console.json` tinha cerca de 1,35 GiB livre, e houve amostras inferiores a 1 GiB durante a rodada final. Ele não é necessário ao DAG em lote e não deve ser confundido com a evidência deste último. Scheduler/API/UI contínuos seguem não validados. Só iniciar com memória disponível; não encerrar aplicativos do usuário para acomodá-lo.

Encerramento usa `compose down` sem `-v`: containers e rede da tarefa são removidos, dados e volumes persistem. Imagens e cache de build também permanecem. Não usar `docker system prune`, reset ou clean para repetir a demonstração.

## Procedimento reproduzível no notebook Windows

Da raiz do projeto, sem monitor serial e sem conectar placa:

```powershell
# Um comando: build sequencial, todos os serviços, publicação, DAG e espera pelo término.
./ops/mlops/stack.ps1 -DataDir data/experiments/phase-c/delivery-stack

# Verificação discriminante: ID do DAG publicado, quatro tasks, oito filhos MLflow,
# HTTP de inferência, nova sessão MQTT, duplicatas, entradas inválidas e falhas/restarts.
./.venv/Scripts/python.exe ops/mlops/verify_stack.py --data-root data/experiments/phase-c/delivery-stack --output data/experiments/phase-c/integration-delivery.json --faults

# Encerrar todos os serviços da tarefa, preservar dados e parar seu helper WSL.
./ops/mlops/stack.ps1 -Encerrar -DataDir data/experiments/phase-c/delivery-stack
```

URLs durante a execução: dashboard `http://127.0.0.1:8767/`, API `http://127.0.0.1:8768`, MLflow `http://127.0.0.1:5000/`. Portas publicadas somente no loopback. A porta 8790 que já estava em uso por outro processo não pertence a esta stack.

Em Linux com Docker/Buildx disponíveis, o caminho direto é `docker compose -f ops/mlops/compose.yaml up -d --build`. No Windows desta máquina, o wrapper `docker` não traduz paths de build/bind e não há Buildx: usar o launcher verificado acima. O Compose padrão usa `data/experiments/phase-c/stack`; `MOTIONLAB_DATA_DIR` pode definir uma pasta isolada. Não apontar uma demonstração para dados reais inadvertidamente. Repetir a subida preserva sessões anteriores e cria um novo batch de demonstração e experimento; para uma execução limpa e rastreável, escolher outra pasta, sem apagar a anterior.

Para regenerar o notebook a partir de um run completo:

```powershell
$latest = Get-Content data/experiments/phase-c/delivery-stack/experiments/demo/latest.json -Raw | ConvertFrom-Json
./.venv/Scripts/python.exe -m ml.academic_notebook "data/experiments/phase-c/delivery-stack/experiments/demo/$($latest.experiment_id)"
```

O notebook contém saídas das células realmente executadas pelo gerador e imagens incorporadas, sem depender de um servidor Jupyter. Para reexecutá-lo no Jupyter de outro ambiente, instalar as dependências do projeto e ajustar `MOTIONLAB_RUN_DIR` para o corpus/run copiado; não há registro global de kernel feito por esta fase.

## Evidências verificáveis

Tudo abaixo fica em `data/experiments/phase-c/`, ignorado pelo git; preservar esses arquivos para o relatório. IDs do experimento, corpus, modelo e DAG são a ligação entre cada etapa. Os arquivos gerados são evidência local, não publicação de resultados físicos.

| Evidência | Conteúdo |
|---|---|
| `status-before.txt`, `staged-before.patch`, `unstaged-before.patch`, `hashes-before.json` | Estado inicial, três renomes staged e alterações anteriores preservadas |
| `pytest-final.xml` / `.log` | Suíte completa, contagem, skips e avisos reais |
| `node-final.log` | Testes das interfaces e guia |
| `integration-delivery.json` / `.log` | Checks reais do cenário final e IDs que conferem com Airflow/MLflow |
| `one-command-delivery.log` | Execução do launcher final |
| `services-delivery.log` | Logs da stack final, sem incluir a chave local do dashboard |
| `delivery-stack/pipeline/deployment.json`, `predictions.json` | Publicação explícita e previsões reais do modelo sobre sessões simuladas |
| `delivery-stack/experiments/demo/<id>/manifest.json`, `evaluation.json`, `eda/`, `source/`, `corpus.jsonl` | Corpus, código, configuração, modelos, métricas, grupos e figuras |
| `delivery-stack/pipeline/airflow-failure-drill.json` | DAG com falha provocada e publicação preservada |
| `images.txt` e `shutdown-delivery.log` | Arquitetura/digests e encerramento |

Não foi feito commit, push, merge, reset, clean, instalação global, upload de firmware, conexão serial ou coleta física. O relatório SBC final, dados da equipe, Google Sites e implementação visual dos novos campos permanecem pendentes.
