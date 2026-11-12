# ChickenLittle / MotionPet
Sistema embarcado: ESP32 + HC-SR04 (ultrassom) + TCRT5000 (IR) falando JSON Lines v1 por USB serial com uma interface web local no notebook: **MotionLab** (Motion Control, Motion Canvas, Air Music, Air Slides, Motion Intelligence). Arquitetura, diagnóstico e plano: `docs/motionlab_arquitetura.md`. A experiência anterior (pet "Piu-piu", Pet Launch) segue em `/legacy/` (`docs/interface_notebook.md`).

## Mapa
- `firmware/` C++/FreeRTOS (PlatformIO, env `esp32dev`, Arduino); `terminal/` app Python (`web/` interface na porta 8767, `bench/` guia de bancada na 8766, `pet/`, `games/`, `modes/`, `communication/`, `renderer/`, `diag/`); `simulator/` e `ml/` (simulação e pipeline de gestos); `tests/` (pytest + 2 testes `.cjs`); `docs/` (protocolo, ADRs, ligações); `hardware/` (netlist, CAD, `wokwi/montagem_atual/`); `teste-*` (projetos PlatformIO de bancada); `data/` saves.

## Comandos (confirmados em 2026-11-10, PowerShell na raiz)
| Ação | Comando | Resultado |
|---|---|---|
| Testes Python | `.\.venv\Scripts\python.exe -m pytest -q` | 464 passed, 3 skipped (sem `FRITZING_PARTS_DIR`), ~27 s; o resumo final pode não aparecer: use o exit code |
| Teste UI web | `node --test tests/test_web_ui.cjs` | 1 pass |
| Teste UI guia | `node --test tests/test_guide_ui.cjs` | 9 pass |
| Build firmware | `.\.venv\Scripts\python.exe -m platformio run -d firmware` | SUCCESS em ~15 s (cache quente); RAM 7,5%, flash 24,5% |
| Interface web | `.\.venv\Scripts\python.exe -m terminal.web` | MotionLab em http://127.0.0.1:8767/, pet em `/legacy/`. `--demo` roda sem placa (porta DEMO, com roteiro de gestos); servidor subido em 2026-11-11 com `--demo --port 8790` |
| Teste UI MotionLab | `node --test tests/test_lab_ui.cjs` | 7 pass |
| Guia de bancada | `.\.venv\Scripts\python.exe -m terminal.bench.guide` | http://127.0.0.1:8766/ (abre a COM3; não rodado) |
Não confirmados (tocam a placa): `gravar_firmware.bat`, `teste_bancada.bat`, upload, monitor serial.
- `.venv` é Python 3.13 ARM64. Nunca instale com `pip`/`python` soltos: use o `.venv` ou `uv`.

## Ligações atuais da bancada
- ESP32 DevKit de 38 pinos na protoboard P1, USB na COM3, firmware integrado gravado.
- HC-SR04 em 5 V (trilho + da P1, alimentado por P1:1J). TRIG em GPIO5 (P1:10A). ECHO passa por divisor na P2 (1 kΩ em 8C-12C, 1 kΩ em 12D-16D, 300 Ω em 16E-20E, 20A no GND) e chega ao GPIO34 por 12A -> P1:15J.
- TCRT5000 em 3,3 V (trilho + da P2, vindo de P1:19J), GND pelos trilhos a partir de P1:6J, DO em GPIO35 (P1:14J).
- Os dois sensores leem juntos, sem erro (relato do usuário; tensões e precisão da distância não foram medidas).
- Fontes de verdade da montagem vigente: `docs/bench_verified_wiring.md`, `hardware/netlist/motionpet_atual_sem_lcd.json`, `hardware/wokwi/montagem_atual/diagram.json`. Quando o usuário mudar um fio, atualize os três (o `diagram.json` é a memória da montagem).
- Históricos com LCD (não descrevem a bancada): `hardware/netlist/motionpet_final_i2c.json` (ainda lido por `hardware/final_assembly.py`, que gera `hardware/guia_montagem_final.html`; não editar o HTML à mão, um teste compara com o gerador), `hardware/wokwi/montagem_atual/diagram_historico_com_lcd.json`, `teste-lcd/`, `teste-i2c-scan/`.

## Restrições elétricas
- LCD 2004 I2C está FORA da montagem: em 3,3 V o texto fica ilegível; em 5 V precisaria de conversor de nível, que o usuário não tem. Nunca sugerir SDA/SCL direto na ESP32 com o LCD em 5 V. A interface no notebook substitui o LCD.
- ESP32 é 3,3 V: nada de 5 V em GPIO; por isso o ECHO do HC-SR04 passa pelo divisor.
- O usuário não tem multímetro (não peça medições de tensão).
- COM3 é exclusiva: um programa por vez. Antes de usar, pare o que a ocupa (servidor web, guia, monitor serial).

## Regras para agentes
- Tudo que envolve a placa (COM3, gravar firmware, monitor serial) é feito só pela thread principal com o usuário, um passo por vez. Subagentes e threads delegadas não tocam na COM3 (a parte física é do usuário e subagente não fala com ele).
- Sem commit, push, merge ou instalação global sem pedido explícito.
- No máximo 2-3 agentes simultâneos (16 GB de RAM).
- Escolha de modelos (preferência do usuário, 2026-11-10): implementação com Claude Sonnet 5.5 (não Codex Terra); design visual com Claude Fable 5.2 em esforço xhigh; aplicação de design pelo orquestrador ou por um Opus 5.5 em esforço high; revisão difícil e segunda opinião com Codex Sol, sem editar.
- Worktree só a partir de um commit; partes em paralelo nunca mexem nos mesmos arquivos; merge só com aprovação.
- Relato de subagente não é prova: o orquestrador confere o diff e roda a verificação.
- Decisões duráveis vão para este arquivo.

## Worktrees
- Não há `.venv` na worktree: rode `Y:\src\ChickenLittle\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` a partir da raiz da worktree (o `pythonpath = "."` do pyproject importa o código da worktree).
- Falhas esperadas só na worktree (ambiente, não código): `test_firmware_cycle3.py::test_tinyml_*` (falta `data/models/`, ignorado pelo git) e `tests/test_guide_ui.cjs` (o checkout da worktree sai com CRLF em `hardware/guia_montagem_final.html`). No checkout principal os três passam.
- (Corrigido na anotação em 2026-11-11) O treino NÃO está quebrado: `trainer.py:161` usa `TrainingConfig.seed`, que existe; `python -m ml.real_pipeline --raw-dir data/raw/synthetic --allow-synthetic-dry-run` (com `--models-dir/--reports-dir/--export-header` apontando para pasta temporária) roda fim a fim com paridade C++ aprovada. Não rode sem esses três argumentos: o padrão sobrescreve `firmware/gestures/tinyml_model.h`.

## Antes de entregar
- Python/web: `pytest` completo (+ `node --test` se mexeu em `terminal/web/static` ou no guia). Firmware: build PlatformIO. Mudança de ligação: atualizar `diagram.json` e docs.

## MotionLab (2026-11-11)
- Código: `terminal/motionlab/` (sinais, IR, reconhecedores, portão, perfis, ações, coleta/avaliação); integração em `terminal/web/session.py` (`engine`, `/api/live`, `/api/lab`, `/api/experience`); UI em `terminal/web/static/{index.html,lab.*,canvas.js,music.js,intel.js}`; legado em `static/legacy/`.
- Testes: `tests/test_motionlab.py`, `tests/test_motionlab_web.py`, `tests/test_lab_ui.cjs`.
- Dados locais (ignorados pelo git): `data/motionlab/settings.json` (perfis/ajustes), `data/raw/real/` (coleta real), `data/raw/demo/` (coleta da demonstração, sintética).

## Decisões
- 2026-11-12: Wi-Fi/MQTT/TLS da ESP32 foi exercitado fisicamente até o consumidor SQLite; `docs/motionlab_bancada_iot_2026-11-12.md` registra evidências e limites. Firmware gravado com polling MQTT rápido e modem-sleep Wi-Fi desativado: 432 amostras em 30 s a 70 ms sem novos descartes na janela; após reinício breve do broker, reconectou. Houve descartes acumulados e faltam ensaios longos/queda prolongada e validação de gestos. Configuração privada, certificados, backup da flash e dados da bancada ficam em `ops/iot/local/`, ignorado pelo Git e restrito; firmware compilado com configuração local incorpora credenciais.
- 2026-11-11 (Fase F): MotionLab é a identidade principal; `applications/`, `esp32-esp8266/` e `schematics/` são índices para os diretórios funcionais existentes, sem cópia de código. A aceitação dessa equivalência pelos professores ainda deve ser confirmada. Começar a navegação por `docs/README.md`; pendências de publicação em `docs/publicacao.md`. O checkpoint em `docs/academico/` é um retrato histórico e não deve ser alterado nesta fase.
- 2026-11-11 (Fase E, software): Wi-Fi STA/ESP-MQTT QoS 1/TLS opcionalmente configurado por `firmware/communication/iot_config.local.h` ignorado; sem configuração, USB/TinyML continuam e IoT fica disabled. Fila estática32/drop-new, um publish pendente; contrato por amostra em `docs/mqtt_iot_v1.md`, procedimento/evidências em `docs/motionlab_fase_e.md`. Tópico `motionlab/v1/devices/<device_id>/samples`; sessão por boot e sequência por aquisição; `valid_ir` explícito. Backend só assina com `--allow-devices` (+`--allow-real` para origem física declarada), persiste SQLite isolado e API pode usar `--watch-iot-db` sem treino/holdout nem mudança das rotas. Broker LAN TLS/ACL independente em `ops/iot/`, sem alterar a stack loopback da Fase C. `real_hardware` nunca atesta validação: `physical_validation=pending`. Build exemplo `esp32dev-iot-example` compila TLS/placeholders sem ler header privado; não gravar esse exemplo. Nenhuma etapa física executada.
- 2026-11-11 (Fase D): Motion Intelligence em três níveis (05.1 ao vivo · 05.2 modelos · 05.3 inferências) consumindo `/api/ml/*` só pelo frontend (`intel.js` desenha, `lab.js` faz o polling: 10 s status/previsões, 60 s avaliações, 30 s em falha, só com a tela visível). Detalhes em `docs/design/motionlab_direcao_visual.md` §5b. Teste visual sem Docker: subir só `python -m ml.inference_api --deployment data/experiments/phase-c/delivery-stack/pipeline/deployment.json --experiments-root data/experiments/phase-c/delivery-stack/experiments --predictions <cópia de predictions.json>` e a config `motionlab-demo-ml` de `.claude/launch.json` (8790); abrir por `127.0.0.1` (Host `localhost` recebe 403).
- 2026-11-11 (Fase C): demonstração software sem placa validada com MQTT → JSONL → Airflow real em lote (`dags test`, quatro tasks) → MLflow HTTP → publicação explícita → API → backend do dashboard. `ops/mlops/stack.ps1` traduz paths para WSL, build sequencial clássico (Buildx ausente), mantém helper com flag e espera o DAG; `-Encerrar` remove só containers/rede da stack e helper, preservando volumes/dados. Default isolado em `data/experiments/phase-c/stack`; `-DataDir` escolhe outra pasta. Verificador: `python ops/mlops/verify_stack.py --faults` (usar `--data-root` correspondente). UI consome `/api/ml/*` com a chave local; contrato em `docs/motionlab_ml_api.md`, auditoria em `docs/motionlab_fase_c.md`. Não alterar visual: ligação dos novos campos ao Motion Intelligence continua com Claude. Especificação e template originais em `docs/academico/`; simulação é aceita, pesos somam 90%, artigo SBC/equipe/Google Sites ainda pendentes. Airflow standalone/scheduler é perfil opcional, separado da evidência de DAG em lote. Nunca promover `latest` implicitamente nem usar rótulos verdadeiros para escolher janela de inferência.
- 2026-11-11 (frente B ML/MLOps): Claude cuida de `terminal/web/static/`; Codex de `ml/`, `ops/mlops/`, contratos, docs e testes. Preferir `python -m ml.experiment` para execuções acadêmicas: artefatos isolados em `data/experiments/{real,synthetic,demo}/`, snapshot/hash de código e corpus, CV/LOGO só no desenvolvimento, teste reservado e exportação sem tocar firmware. MLflow é opcional via `--tracking-uri`; `--tune` limita busca à árvore na CV. API independente `python -m ml.inference_api` na 8768; contrato em `docs/motionlab_ml_api.md`, auditoria em `docs/motionlab_mlops.md`. Não tratar o replay exploratório da UI como holdout; observar `provenance`. Broker MQTT, runtime Airflow e Compose preparados ainda exigem execução integrada. Não abrir COM3 nem gravar firmware nesta frente.
- 2026-11-11: redesign visual do MotionLab ("instrumento de bancada"): tokens, tipografia e marcas de proveniência (REAL sólido · SINTÉTICO hachura · DEMO tracejado · PENDENTE contorno) em `docs/design/motionlab_direcao_visual.md`. Novos dados expostos à UI devem usar essas marcas. Ícones são SVG inline no `index.html` (o servidor só serve uma lista fechada de estáticos).
- 2026-11-11: MotionLab substitui o pet como experiência principal. Fonte padrão de gestos = regras (o modelo ML/TinyML só viu dados sintéticos); ML e TinyML são selecionáveis e de fato controlam os módulos. Ações externas: só teclas de um catálogo fechado (`terminal/motionlab/actions.py`), chave desligada a cada início, gestos desarmados ao conectar/desconectar, limite de 8 teclas/10 s. Firmware não foi alterado.
- 2026-11-11: as regras automáticas sensor→pet (`MotionPetSession._sensor_controls`) só valem com a experiência legada ativa (`/legacy/` envia `POST /api/experience`).
- 2026-11-10: LCD fora da montagem; a interface no notebook (`terminal.web`) substitui o LCD. O usuário retirou também os cabos de alimentação do LCD: não sobra fio dele na bancada.
- 2026-11-10: a netlist vigente é `motionpet_atual_sem_lcd.json`; `motionpet_final_i2c.json` ficou como perfil histórico com LCD porque o gerador do guia depende dele.
