# Diretório de Dados — MotionPet

Este diretório gerencia o armazenamento local de conjuntos de dados sensoriais brutos, matrizes de características processadas para treinamento e arquivos de persistência de estado do pet.

---

## 1. Estrutura de Subdiretórios

```
data/
├── raw/            # Séries temporais sensoriais brutas capturadas de sessões físicas/simuladas
├── processed/      # Matrizes de features extraídas, normalizadas e particionadas (train/test)
├── saves/          # Arquivos de persistência de estado do pet virtual (pet_save.json)
├── .gitkeep
└── README.md
```

---

## 2. Descrição dos Subdiretórios

### 2.1 `data/raw/`
- Armazena arquivos brutos de telemetria capturados via conexão serial com o firmware do ESP32 ou gerados por geradores de teste.
- **Formato**: Linhas em JSON Lines (`.jsonl`) ou arquivos tabulares delimitados por vírgula (`.csv`).
- **Nomenclatura Padrão**:
  `session_<TIMESTAMP>_<USER_ID>_<GESTO>.jsonl`
  *Exemplo*: `session_1730100000_u01_APPROACH.jsonl`
- **Nota**: Arquivos nesta pasta representam a gravação contínua dos sensores e metadados antes de qualquer filtragem ou extração de features.

### 2.2 `data/processed/`
- Armazena as matrizes estruturadas prontas para consumo pelos algoritmos de aprendizado de máquina em `ml/training/`.
- **Arquivos Típicos**:
  - `features_dataset.csv`: Todas as janelas temporais processadas com as 8 características extraídas (`d_min`, `d_max`, `d_delta`, `d_mean`, `d_std`, `v_mean`, `v_peak`, `sign_inversions`), a coluna de rótulo `label` e as colunas de metadados (`session_id`, `user_id`).
  - `train_features.csv` e `test_features.csv`: Partições geradas pelo split agrupado (*GroupKFold*) sem vazamento de dados (*data leakage*).

### 2.3 `data/saves/`
- Armazena os arquivos de estado persistente do pet virtual para a funcionalidade de salvar/carregar (`SAVE` e `LOAD` no protocolo JSON Lines v1).
- **Arquivo Principal**: `pet_save.json`.
- **Formato**: Snapshot JSON estruturado em conformidade com o esquema de `pet_state` do protocolo. Permite desligar o terminal ou o simulador e retomar a evolução exatamente do mesmo ponto biológico.
