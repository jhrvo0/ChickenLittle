# ml/training — Treinamento de Modelos de Classificação de Gestos

Este módulo implementa os algoritmos de aprendizado de máquina para reconhecimento de gestos baseados em distâncias ultrassônicas 1D, conforme as etapas 6, 7, 8 e 9 de `docs/ml_pipeline_spec.md`.

---

## 1. Entradas e Saídas do Ciclo 2

- **Entradas**:
  - Matriz de características gerada por `ml/preprocessing` (`data/processed/features_dataset.csv`).
- **Saídas**:
  - Modelos treinados salvos para análise em desktop (`models/baseline_rules.py`, `models/decision_tree.joblib`, etc.).
  - Histórico de parâmetros e hiperparâmetros de treinamento.

---

## 2. Modelos Contemplados

1. **Baseline Determinístico por Regras (`RuleBaselineClassifier`)**:
   - Classificador sem aprendizado estatístico, baseado estritamente em limiares físicos de velocidade ($\Delta d / \Delta t$) e variância ($\sigma^2$).
   - Serve como ponto de comparação obrigatório de desempenho.
2. **Árvore de Decisão Rasa (`DecisionTreeClassifier`)**:
   - Hiperparâmetros controlados: `max_depth` entre 3 e 5, `min_samples_leaf >= 5`.
   - Modelo prioritário para exportação direta em C++ para o ESP32.
3. **Random Forest (`RandomForestClassifier`)**:
   - Modelo de ensemble de referência (10 a 20 árvores) para avaliar o teto de acurácia antes da compressão.
4. **MLP Compacta (`MLPClassifier`)**:
   - Rede neural rasa (camada oculta de 8 a 16 neurônios) para avaliação de aprendizado não-linear compacto.
