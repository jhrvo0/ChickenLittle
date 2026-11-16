# MotionLab · Índice da entrega

**Grupo 5 · CESAR School · Sistemas Embarcados e Aprendizado de Máquina**
Repositório: <https://github.com/jhrvo0/ChickenLittle> · Página do projeto: <https://sites.google.com/view/motionlab-grupo5>

| Integrante | GitHub | Responsabilidade |
|---|---|---|
| João Henrique R. V. de Oliveira | @jhrvo0 | Representação e coordenação |
| Antônio Jose Paes de Andrade Junior | @AntonioPaess | Hardware, sensores e montagem |
| Marco Antônio Maciel | @oMarcoMaciel | Aprendizado de máquina e avaliação dos modelos |
| Jorge Dias | @Jorgedias96 | Interface e experiências interativas |
| João Pedro | @Joaopdornelas | Comunicação e integração Wi-Fi/MQTT |

---

## 1. O projeto em uma página

O MotionLab é um sistema de **interação por gestos sem contato**. Uma ESP32 lê um sensor ultrassônico (HC-SR04) e um infravermelho (TCRT5000) a cada 70 ms. Um modelo de aprendizado de máquina reconhece quatro gestos (neutro, aproximar, afastar e segurar), que controlam desenho, música e slides no computador.

```text
HC-SR04 + TCRT5000 ──► ESP32 / FreeRTOS ──┬── USB · JSON Lines ──► servidor local ──► dashboard MotionLab
                          │ TinyML (MLP)  │
                          └───────────────┴── Wi-Fi · MQTT/TLS ──► Mosquitto ──► consumidor ──► JSONL / SQLite
                                                                                      │
                                     Airflow (preparação → treino/validação → publicação)
                                                    │                     │
                                                 MLflow             API de inferência ──► dashboard
```

| Números | |
|---|---|
| Código Python (aplicação, ML, MLOps) | ~22.700 linhas |
| Firmware C++ (ESP32, FreeRTOS) | ~6.100 linhas |
| Interface web (HTML, CSS, JS) | ~3.100 linhas |
| Testes automatizados | 675 em Python e 20 de interface, todos aprovados |
| Modelos comparados | 5 famílias + 2 baselines |
| Melhor modelo (MLP, teste externo simulado) | F1-macro 0,970, zero falsos acionamentos |

---

## 2. Sistemas Embarcados

### 2.1 Hardware

| Item | Onde está | Evidência |
|---|---|---|
| Lista de componentes e pinos (GPIO5 TRIG, GPIO34 ECHO, GPIO35 IR) | [`firmware/main/pinout_config.h`](../firmware/main/pinout_config.h) | [Ligações verificadas na bancada](bench_verified_wiring.md) |
| Divisor resistivo do ECHO (5 V → ~2,83 V) | [`docs/hardware_safety.md`](hardware_safety.md) | [Foto do divisor](fotos-bancada/detalhe-divisor.jpg) |
| Esquemático e netlist | [`hardware/netlist/motionpet_atual_sem_lcd.json`](../hardware/netlist/motionpet_atual_sem_lcd.json), [`schematics/`](../schematics/) | [Figura do circuito](figuras/circuito.png) |
| Simulação Wokwi | [`hardware/wokwi/montagem_atual/diagram.json`](../hardware/wokwi/montagem_atual/diagram.json) | — |
| Montagem física | — | [Visão geral](fotos-bancada/montagem-geral.jpg), [ESP32](fotos-bancada/detalhe-esp32.jpg), [placas](fotos-bancada/placas-e-divisor.jpg) |

### 2.2 Firmware

| Item | Onde está |
|---|---|
| Tarefas FreeRTOS (aquisição, inferência, comunicação, rede) com prioridades e filas estáticas | [`firmware/main/main.cpp`](../firmware/main/main.cpp), [arquitetura](../firmware/main/README.md) |
| Driver dos sensores com timeout e proteção contra eco preso | [`firmware/sensors/sensors_driver.cpp`](../firmware/sensors/sensors_driver.cpp) |
| Protocolo USB JSON Lines v1 com parser estrito, sem alocação dinâmica | [`firmware/communication/jsonl_protocol.cpp`](../firmware/communication/jsonl_protocol.cpp), [especificação](protocol.md) |
| Classificador TinyML embarcado (MLP exportada para C++) | [`firmware/gestures/`](../firmware/gestures/) |
| Wi-Fi + MQTT 3.1.1 com TLS, QoS 1 e reconexão com backoff | [`firmware/communication/iot_transport.cpp`](../firmware/communication/iot_transport.cpp), [contrato MQTT](mqtt_iot_v1.md) |

### 2.3 Comunicação e infraestrutura

| Tópico MQTT | Publica | Assina | Conteúdo |
|---|---|---|---|
| `motionlab/v1/devices/<id>/samples` | ESP32 (TLS, QoS 1) | consumidor → SQLite | uma amostra por mensagem |
| `motionlab/v1/sessions/{demo,synthetic,real}` | coleta/simulador | ingestão → JSONL → Airflow | sessão rotulada completa |
| `motionlab/v1/receipts/<sessão>` | ingestão | publicador | recibo com hash SHA-256 |

- **Ensaio físico de rede:** 432 amostras em 30 s a 70 ms, sem descartes na janela, e reconexão após reiniciar o broker ([relato](motionlab_bancada_iot_2026-11-12.md)).
- **Broker:** Mosquitto local em Docker; broker de rede local com TLS e ACL em [`ops/iot/`](../ops/iot/).

### 2.4 Aplicação (dashboard)

Aplicação web própria com cinco módulos: **Motion Control** (gestos → ações), **Motion Canvas** (desenho pela distância), **Air Music** (notas e efeitos), **Air Slides** (passar slides) e **Motion Intelligence** (sinais ao vivo, modelos e inferências). Toda tela indica a origem do dado: REAL, SINTÉTICO ou DEMO.

- Código: [`terminal/web/`](../terminal/web/)
- Capturas: [início](capturas-motionlab/01-inicio-demo.jpg), [sinais](capturas-motionlab/02-sinais-demo.jpg), [Motion Canvas](capturas-motionlab/03-canvas-demo.jpg), [Motion Intelligence com a API](evidencias/am-2026-11-15/dashboard.jpg)
- Segurança: servidor só em `127.0.0.1`, verificação de Host e Origin, chave por sessão e CSP restritiva.

### 2.5 Documentação

- [README](../README.md) com equipe, execução e limites
- [Relatório final em formato SBC](Projeto_Embarcados_Grupo5.pdf) ([editável](Projeto_Embarcados_Grupo5.docx))
- [Índice completo da documentação](README.md)

---

## 3. Aprendizado de Máquina

Matriz completa da especificação × repositório: [`docs/aprendizado_maquina.md`](aprendizado_maquina.md).

### 3.1 Dados e análise (bloco de 15%)

| Requisito | Entrega |
|---|---|
| Leitura do bootstrap dataset | Corpus de 12 participantes simulados × 2 sessões, 4.303 leituras, 1.918 janelas ([gerador](../ml/collection/synthetic.py)) |
| EDA em notebook | [`notebooks/motionlab_bootstrap.ipynb`](../notebooks/motionlab_bootstrap.ipynb), executado |
| Estatísticas descritivas | Tabela dos 11 atributos (relatório, Tabela 1) |
| Tratamento com justificativa | Valores ausentes por retenção causal e saturação, mediana e EMA, descarte de janelas ambíguas, padronização só no treino de cada fold |
| ≥ 5 visualizações interpretadas | 7 figuras: [classes](../reports/figuras-am/01_classes.png), [participantes](../reports/figuras-am/02_participants.png), [traço temporal](../reports/figuras-am/03_trace.png), [leituras inválidas](../reports/figuras-am/04_invalid.png), [correlações](../reports/figuras-am/05_correlations.png), [treino × validação](../reports/figuras-am/06_ajuste.png), [matrizes de confusão](../reports/figuras-am/07_matrizes.png) |

### 3.2 Modelagem e validação (bloco de 30%)

| Requisito | Entrega |
|---|---|
| Holdout | 2 participantes reservados antes da EDA (320 janelas) |
| Validação cruzada | `StratifiedGroupKFold`, 5 folds, estratificado por classe sem misturar participantes |
| Leave-One-Out | `LeaveOneGroupOut`, 10 folds; o LOO por janela vazaria janelas sobrepostas da mesma pessoa |
| Estabilidade e ajuste | Desvio entre folds, F1 de treino × validação e diagnóstico de sobreajuste ou subajuste |
| Otimização de hiperparâmetros | Grid Search em 67 combinações nas 5 famílias ([código](../ml/validation.py)) |
| Baseline | Árvore de profundidade 1 e regras de domínio |
| ≥ 3 modelos | Árvore de decisão, Random Forest, AdaBoost, KNN e MLP |
| Comparação crítica | Matrizes de confusão, F1 por classe, teste de Friedman e Wilcoxon com correção de Holm |

**Resultados no teste externo (dados simulados):**

| Modelo | F1 validação (5 folds) | F1 teste | Falsos acionamentos |
|---|---|---|---|
| Árvore prof. 1 (baseline) | 0,329 | 0,343 | 12,7% |
| Regras (referência) | 0,530 | 0,546 | 10,2% |
| AdaBoost | 0,629 | 0,766 | 9,0% |
| KNN | 0,917 | 0,882 | 2,4% |
| Árvore de decisão | 0,897 | 0,909 | 3,0% |
| Random Forest | 0,932 | 0,953 | 1,8% |
| **MLP** | **0,982** | **0,970** | **0,0%** |

A MLP é melhor que todos os outros modelos com significância estatística (Friedman p = 1,2 × 10⁻¹⁰). Exportada para C++, ocupa cerca de 4 KB de flash e reproduz 100% das previsões do Python.

### 3.3 MLOps (bloco de 25%)

| Requisito | Entrega | Evidência |
|---|---|---|
| MLflow: parâmetros, métricas, artefatos, modelo | [`ml/tracking.py`](../ml/tracking.py) | [Captura](evidencias/am-2026-11-15/mlflow.jpg) |
| MLflow: múltiplos experimentos | Comparação de modelos + experimento de hiperparâmetros (um run por combinação) | idem |
| Aquisição e MQTT | ESP32 física com TLS e simulador no Compose | [Ensaio de rede](motionlab_bancada_iot_2026-11-12.md) |
| Persistência | JSONL rotulado e SQLite por amostra, com deduplicação | [`ml/mqtt_ingestion.py`](../ml/mqtt_ingestion.py), [`ml/iot_ingestion.py`](../ml/iot_ingestion.py) |
| Pipeline Airflow | DAG com 4 tarefas: configuração → preparação → experimento → publicação | [DAG](../ops/mlops/dags/motionlab_experiment.py), [captura](evidencias/am-2026-11-15/airflow.jpg) |
| Integração e API | A API observa dados novos e gera previsões automaticamente | [`ml/inference_api.py`](../ml/inference_api.py), [captura](evidencias/am-2026-11-15/api-status.jpg) |
| Dashboard | Motion Intelligence: sinais ao vivo, métricas, previsões e estado dos serviços | [captura](evidencias/am-2026-11-15/dashboard.jpg) |
| Docker com um comando | `docker compose up --build` na raiz | [Verificação: 14 checks aprovados](evidencias/am-2026-11-15/verify-stack.log) |

### 3.4 Comunicação (bloco de 20%)

- Relatório no template SBC: [PDF](../reports/relatorio_aprendizado_maquina.pdf), [editável](../reports/relatorio_aprendizado_maquina.docx) e [texto](../reports/relatorio_aprendizado_maquina.md)
- Figuras e tabelas geradas por código a partir do experimento ([`ml/report_assets.py`](../ml/report_assets.py)), sem números digitados à mão

---

## 4. Roteiro de demonstração (cerca de 10 minutos)

1. **Hardware (1 min):** mostrar a montagem e o divisor do ECHO; mão se aproximando e o sinal chegando ao dashboard.
2. **Dashboard (2 min):** Motion Canvas e Air Music respondendo à distância; Motion Control com um gesto disparando uma ação.
3. **Pipeline (3 min):** `docker compose up --build`; sessão chegando pelo MQTT, DAG com as 4 tarefas concluídas no Airflow.
4. **MLflow (2 min):** os dois experimentos, a comparação dos 7 modelos e um run do Grid Search.
5. **Inferência (1 min):** `/v1/status` da API e as previsões no Motion Intelligence.
6. **Resultados (1 min):** tabela do teste externo, matriz de confusão da MLP e o teste estatístico.

Para reproduzir tudo a partir de um clone: [README › Instalação e execução](../README.md#instalação-e-execução).

---

## 5. Limitações conhecidas e próximos passos

- **Dados reais:** os modelos foram treinados e avaliados com dados simulados. A coleta com participantes reais está planejada ([guia de coleta](real_data_collection_guide.md)), com os participantes de teste reservados antes da análise.
- **Desempenho na placa:** latência e memória do modelo medidas na ESP32 ainda pendentes; a paridade Python/C++ foi verificada no computador.
- **Rede:** ensaios longos com quedas prolongadas do broker e tráfego IPv6 ainda não foram realizados.
- **Atuador físico:** os gestos acionam música, desenho e slides no computador; não há atuador na placa.
