# ml/evaluation — Avaliação Multivariada e Diagnóstico de Modelos

Este módulo implementa a etapa 10 do pipeline de ML, avaliando quantitativamente a capacidade de generalização dos modelos treinados sobre dados nunca vistos durante o treinamento.

---

## 1. Entradas e Saídas do Ciclo 2

- **Entradas**:
  - Modelos treinados gerados por `ml/training/`.
  - Conjunto de teste particionado por grupo (`data/processed/test_features.csv`).
- **Saídas**:
  - Relatório consolidado em formato JSON ou Markdown (`reports/evaluation_summary.json`).
  - Matrizes de confusão normalizadas para cada modelo avaliado.

---

## 2. Métricas de Avaliação Obrigatórias

1. **F1-Score Macro**:
   - Média aritmética dos F1-scores de cada uma das classes (`APPROACH`, `RETREAT`, `HOLD`, `NEUTRAL`), impedindo distorções causadas por desbalanceamento de classes.
2. **Matriz de Confusão Normalizada por Linha**:
   - Identifica se o gesto `HOLD` está sendo confundido com `NEUTRAL`, ou se falsos disparos de `APPROACH` ocorrem durante movimentações de afastamento.
3. **Taxa de Falsos Disparos em Repouso (*False Alarm Rate on Neutral*)**:
   - Probabilidade condicional de disparar qualquer gesto ativo quando a mão do usuário está em repouso ou fora do cone sensorial. Deve ser minimizada para evitar reações espúrias do pet.
4. **Comparativo contra o Baseline**:
   - Demonstração estatística de ganho em relação ao classificador baseado em regras.
