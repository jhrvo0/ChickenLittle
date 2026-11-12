# Base textual para relatório SBC — MotionLab

Atualização Fase C: a [auditoria contra os documentos originais e os resultados executados](motionlab_fase_c.md) contém a integração simulada MQTT/Airflow/MLflow/API, notebook, métricas e limitações atuais. Os trechos históricos abaixo que descrevem containers ainda não executados referem-se à frente B. O enunciado aceita aquisição simulada; dados reais são necessários para conclusões físicas, sem constituir exigência dessa alternativa. Este Markdown continua sendo apoio; o artigo final deve usar o DOCX SBC fornecido e ser entregue em PDF.

Este é conteúdo de apoio, não um artigo final diagramado no template SBC. Autores, instituição, referências finais e resultados reais precisam ser preenchidos. O mapeamento dos requisitos está em [motionlab_mlops.md](motionlab_mlops.md).

## Título proposto

MotionLab: interação gestual com sensores de baixo custo e avaliação rastreável de modelos compactos

## Resumo provisório

O MotionLab integra sensores ultrassônico e infravermelho a experiências interativas no navegador. O sistema distingue regras determinísticas, modelos executados no notebook e inferência TinyML no dispositivo. O pipeline compara um baseline e três modelos, aplica particionamento agrupado e registra dados, configuração, código e métricas em experimentos rastreáveis. A implementação foi exercitada com dados sintéticos e testes de software. A generalização para gestos de usuários e o desempenho físico no dispositivo permanecem pendentes de coleta e avaliação sistemática. Resultados sintéticos são tratados exclusivamente como evidência de funcionamento do pipeline.

## 1. Problema e objetivo

Investigar se modelos compactos oferecem benefício sobre regras explícitas no reconhecimento de gestos temporais de distância. A pergunta científica requer participantes independentes e avaliação de falsos acionamentos durante repouso; uma interface visual responsiva não basta para respondê-la.

## 2. Arquitetura

ESP32 → JSON Lines v1 → notebook → reconhecedores paralelos → gate de segurança → módulos MotionLab. Distância contínua e eventos discretos do IR têm papéis separados. O serviço HTTP de ML fornece inferências por janela e relatórios; ele não substitui o gate nem controla o hardware. Um caminho MQTT de laboratório persiste sessões completas e um DAG Airflow manual pode orquestrar a avaliação. O Compose descreve esses serviços, cuja execução integrada ainda precisa ser validada.

## 3. Materiais e método

Descrever ESP32, HC-SR04 e TCRT5000 da montagem vigente, sem LCD. O ultrassom fornece um sinal escalar; não permite reconstruir movimento lateral ou pose da mão. O IR é um sinal discreto. Não houve alteração do firmware nesta etapa.

Coletar séries com participante pseudônimo, sessão, timestamp, índice, distância/validade, IR, rótulo solicitado e origem explícita. Distinguir rótulo solicitado de gesto efetivamente observado. Registrar condições de coleta e problemas de qualidade. Congelar o teste antes da exploração e guardar seu hash.

Aplicar filtro causal, janelamento e onze características existentes. Isolar estado por sessão. Usar split por participante quando possível; fallback por sessão limita a inferência de generalização entre pessoas. Ajustar StandardScaler somente no treino de cada fold. Aplicar GroupKFold e opcional LOGO no desenvolvimento; nunca LOO sobre janelas sobrepostas.

Comparar regras, árvore, floresta e MLP compacta. Documentar sementes, hiperparâmetros e o critério de seleção multicritério na validação. Se usar tuning, relatar espaço de busca e sua restrição ao desenvolvimento. Não apresentar CV reutilizada para tuning como avaliação independente. Avaliar os candidatos no holdout externo depois da escolha; não escolher retrospectivamente o melhor F1 de teste.

## 4. Resultados a preencher

Separar rigorosamente duas tabelas: verificação sintética de software e resultados reais. Não preencher a tabela real com métricas sintéticas. Extrair de `evaluation.json` F1-macro com quatro classes, precisão/recall/F1 por classe, suporte, matriz de confusão, FAR em neutro, F1 por eventos e rejeições. Explicar cada uma das cinco figuras EDA com seu contexto e suas limitações.

Registrar `experiment_id`, hash do corpus, grupos, origem, versão do código e run MLflow. A latência disponível é de inferência Python no notebook. SRAM/Flash são estimadas. Paridade C++ comprova concordância numérica da implementação nas entradas exercitadas, sem comprovar acurácia física ou tempo de execução na ESP32.

No estado desta entrega: **avaliação real pendente; nenhuma conclusão de superioridade de ML às regras está sustentada**.

## 5. Discussão e ameaças à validade

- **Validade interna:** cronograma pode diferir da execução humana; timeouts, transições ambíguas e sobreposição temporal podem enviesar métricas. Estado causal e grupos reduzem vazamento, mas não corrigem rótulos errados.
- **Validade externa:** poucas pessoas, uma posição de sensor e ambientes semelhantes não representam usuários e condições distintos. Fallback por sessão não demonstra generalização entre pessoas.
- **Validade de construto:** F1 de janelas não mede sozinho a experiência; repetição, falsos acionamentos, rejeições e latência de ponta a ponta importam. Confiança softmax não foi calibrada.
- **Validade de conclusão:** folds correlacionados não são amostras independentes; desvio entre folds não é intervalo de confiança. Não afirmar significância sem desenho e amostra adequados. Reuso do teste após observar resultados exige novo conjunto reservado.
- **Proveniência:** origem é metadata declarada; testes com fixtures marcadas `real_hardware` não são coleta humana. Misturas são bloqueadas, mas autenticidade física requer protocolo e registro de coleta.
- **Limites operacionais:** software MLOps local testado não implica que broker, Airflow e containers foram executados. Registrar separadamente as evidências futuras de cada integração.

## 6. Conclusão provisória

A contribuição demonstrada é uma base de software que separa reconhecimento, interação e evidência experimental, com rastreabilidade e caminhos de integração. O desempenho real e a utilidade de aprendizado estatístico diante das regras permanecem questões abertas para a próxima etapa experimental.

## Referências técnicas iniciais

- [scikit-learn — validação cruzada e grupos](https://scikit-learn.org/stable/modules/cross_validation.html).
- [MLflow — rastreamento de experimentos](https://mlflow.org/docs/latest/ml/tracking/).
- [Eclipse Paho — cliente MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
- [Apache Airflow — documentação](https://airflow.apache.org/docs/apache-airflow/stable/).

Adicionar referências acadêmicas pertinentes ao problema e formatá-las conforme o template e a rubrica efetivamente adotados pela disciplina.
