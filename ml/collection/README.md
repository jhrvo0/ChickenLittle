# ml/collection — Coleta de Dados e Anotação com Metadados

Este módulo é responsável por guiar e capturar sessões de gravação de dados físicos de sensores (HC-SR04, TCRT5000, potenciômetro) transmitidos via serial pelo firmware de telemetria ou gerados por simuladores instrumentados no Ciclo 2.

---

## 1. Entradas e Saídas do Ciclo 2

- **Entradas**:
  - Stream contínuo de quadros `sensor_frame` via conexão Serial (115200 baud) ou loopback de testes.
  - Parâmetros da sessão fornecidos pelo operador:
    - `--user`: Identificador anônimo do operador (ex: `user_01`, `user_02`).
    - `--gesture`: Rótulo do gesto executado (`APPROACH`, `RETREAT`, `HOLD`, `NEUTRAL`).
    - `--duration`: Duração em segundos da rodada de coleta (ex: 30s).
- **Saídas**:
  - Arquivos brutos gravados em `data/raw/` seguindo a convenção de nomenclatura:
    `session_<timestamp>_<user_id>_<gesture>.jsonl` ou `.csv`.

---

## 2. Metadados Obrigatórios por Registro

Cada arquivo gravado deve conter no cabeçalho ou em cada linha os metadados:
1. `session_id`: UUID ou timestamp único da sessão.
2. `user_id`: Código da pessoa executando o movimento.
3. `sample_rate_hz`: Frequência de amostragem configurada (ex: 20 Hz).
4. `target_gesture`: Gesto alvo que estava sendo gravado.
5. `ts_ms`: Timestamp relativo em milissegundos emitido pelo microcontrolador.
6. `distance_cm`: Leitura bruta do sensor ultrassônico.
7. `ir_detected`: Estado booleano do sensor TCRT5000.
