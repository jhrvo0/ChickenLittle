# Dados locais do MotionLab

Este diretório reúne dados de execução, sessões e artefatos gerados. A maior parte não é versionada; consulte as regras exatas em [.gitignore](../.gitignore).

| Caminho | Conteúdo |
|---|---|
| `raw/real/` | Sessões declaradas como coleta física; exigem cuidados com dados de participantes. |
| `raw/synthetic/` | Corpus sintético para verificar e estudar o pipeline. |
| `raw/demo/` | Sessões da demonstração, de origem simulada. |
| `processed/` · `models/` · `reports/` | Features, modelos e relatórios do fluxo histórico. |
| `experiments/` · `mlflow/` | Execuções isoladas, rastreabilidade e artefatos de experimentos. |
| `iot/` · `motionlab/` · `saves/` | Telemetria IoT, ajustes locais e estados persistidos. |

O pipeline atual extrai 11 características por janela; a definição está em [ml/schemas.py](../ml/schemas.py) e a implementação em [ml/preprocessing/features.py](../ml/preprocessing/features.py). Os dados sintéticos não medem desempenho em pessoas ou sensores reais. Veja [ML/MLOps](../docs/motionlab_mlops.md) e [coleta real](../docs/real_data_collection_guide.md) para metodologia e limites.
