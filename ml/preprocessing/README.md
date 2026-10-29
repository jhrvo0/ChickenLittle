# ml/preprocessing — Filtragem, Janelamento e Extração de Features

Este módulo implementa as etapas 2, 3, 4 e 5 do pipeline de Machine Learning (conforme especificado em `docs/ml_pipeline_spec.md`).

---

## 1. Entradas e Saídas do Ciclo 2

- **Entradas**:
  - Arquivos de séries temporais brutas localizados em `data/raw/` (`.jsonl` ou `.csv`).
- **Saídas**:
  - Conjuntos de dados processados em `data/processed/`:
    - `features_dataset.csv` (matriz com colunas de características + coluna `label` + coluna de grupo `session_id`/`user_id`).
    - Metadados de escalonamento ou normalização (se aplicável).

---

## 2. Etapas de Processamento

1. **Tratamento de Timeouts e Saturação**:
   - Converte leituras nulas (`null`) ou leituras com distância $> 100\text{ cm}$ para o valor fixo de teto ($100.0\text{ cm}$).
2. **Filtragem de Ruído**:
   - Filtro de mediana móvel com janela de 3 amostras para remoção de picos espúrios de reflexão.
3. **Janelamento Deslizante**:
   - Extração de janelas de $600\text{ ms}$ ($12$ amostras a $20\text{ Hz}$) com avanço de $50\text{ ms}$ ($1$ amostra).
4. **Vetor de Características (Features)**:
   - Extração estrita das 8 características implementadas no header C++ `firmware/gestures/gesture_classifier.h`:
     1. `d_min`: menor distância observada na janela.
     2. `d_max`: maior distância observada na janela.
     3. `d_delta`: diferença entre a última e a primeira leitura ($d_{fim} - d_{inicio}$).
     4. `d_mean`: média aritmética das distâncias.
     5. `d_std`: desvio padrão amostral.
     6. `v_mean`: velocidade média estimada ($\Delta d / \Delta t$).
     7. `v_peak`: pico máximo de velocidade instantânea observada.
     8. `sign_inversions`: quantidade de mudanças de direção de deslocamento.
5. **Divisão de Partição sem Vazamento**:
   - Métodos utilitários para gerar partições `train`, `val`, `test` utilizando agrupamento estrito por `user_id` ou `session_id` (*GroupKFold*).
