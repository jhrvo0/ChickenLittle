# Revisão de firmware e testes (12/11/2026)

Revisão do código feita após o Check Point, em um clone limpo do repositório em macOS (Python 3.13, Node 25). O objetivo foi rodar toda a verificação automatizada sem os arquivos locais da bancada (`data/models/`, `ops/iot/local/`) e corrigir o que impedia a reprodução ou o que a leitura do firmware apontou.

## Resultado dos testes

| Verificação | Antes | Depois |
|---|---|---|
| `pytest` só com `requirements.txt` | Coleta interrompida: falta `cryptography` | Documentado: instalar também `requirements-mlops.lock` |
| `pytest` completo, em clone limpo | 658 coletados; **2 falhas** em `test_firmware_cycle3.py` | 662 coletados; **657 aprovados, 5 pulados, 0 falhas** |
| `node --test` (3 arquivos) | 12 executados, **1 falha** (`test_guide_ui.cjs` não carrega) | **20 aprovados, 0 falhas** |
| Build PlatformIO `esp32dev` | Não concluído nesta máquina | **Não verificado**: ver “Build do firmware” |

Os 5 testes pulados: 3 dependem de `FRITZING_PARTS_DIR`; 2 de provisionamento do broker só rodam no Windows/WSL.

## Problemas encontrados e correções

### 1. Testes TinyML falhavam em clone limpo

`_load_or_build_engineering_bundles()` em `tests/test_firmware_cycle3.py` carrega os modelos de `data/models/` (ignorado pelo Git). Sem eles, treina um modelo na hora, mas chamava `train_candidate_models(split, pre_cfg, TrainingConfig(...))`: passava o split no lugar das janelas e trocava a ordem das configurações, o que gerava `AttributeError: 'PreprocessingConfig' object has no attribute 'seed'`. Na máquina da bancada o caminho nunca era executado, por isso as evidências do checkpoint passavam.

**Correção:** chamada alinhada à assinatura usada em `ml/experiment.py` (`windows, TrainingConfig, PreprocessingConfig`). Com isso a paridade Python ↔ C++ passou amostra a amostra. O modelo treinado num corpus sintético pequeno (6 participantes) reconhece APPROACH e RETREAT, mas não HOLD; o mínimo de eventos exigido continua 3 para os modelos de `data/models/` e passa a 2 no clone limpo, só para garantir que a comparação não seja vazia.

### 2. Teste do guia de montagem quebrava com CRLF

`tests/test_guide_ui.cjs` procurava `const slides=[...];\n`. Com `core.autocrlf=true` (padrão do Git no Windows) o `hardware/guia_montagem_final.html` sai com CRLF e o arquivo inteiro de testes falhava ao carregar, escondendo 9 testes. **Correção:** a expressão aceita `\r?\n`.

### 3. LCD inexistente ainda era acionado pelo firmware

O LCD saiu da montagem em 10/11, mas `setup()` inicializava o I²C (GPIO21/22), tocava a animação de boot (cerca de 3 s de espera) e a tarefa do LCD escrevia no barramento a cada 200 ms.

**Correção:** nova opção `MOTIONLAB_LCD_HW_ENABLED` em `firmware/main/pinout_config.h`, com padrão `0`. Sem ela, o driver do LCD não é inicializado e `lcd_ctx_render_frame()` retorna sem I/O. A tarefa continua montando o quadro 20×4 que é enviado ao notebook pela interface legada. Para voltar a usar o LCD: `-D MOTIONLAB_LCD_HW_ENABLED=1`.

### 4. Tarefa de rede disputava o núcleo com a aquisição

Todas as tarefas, inclusive `MotionIoT`, rodavam no núcleo 1. A aquisição do HC-SR04 tem a maior prioridade e espera o eco em laço ativo por até 25 ms a cada 70 ms; nesse tempo a tarefa de rede não roda no núcleo 1. No ensaio de bancada houve 89 descartes acumulados.

**Correção:** `MotionIoT` passa para o núcleo 0 (`PRO_CPU_NUM`), onde já ficam o Wi-Fi e o lwIP. A fila compartilhada usa `portMUX`, que é seguro entre núcleos. **Ainda não medido na placa:** é preciso repetir o ensaio de `docs/motionlab_bancada_iot_2026-11-12.md` para saber se os descartes diminuem.

### 5. Falha de alocação das primitivas do RTOS não era tratada

`setup()` não conferia o retorno de `xSemaphoreCreateMutex()` e `xQueueCreate()`. **Correção:** se alguma falhar, nenhuma tarefa é criada e a placa fica ociosa, em vez de as tarefas usarem handles nulos.

Os itens 3 a 5 têm testes de regressão em `tests/test_firmware_review_fixes.py`.

## Build do firmware

Comando: `python -m platformio run -d firmware -e esp32dev`.

**As mudanças de firmware desta revisão não foram compiladas.** Em um clone limpo, o PlatformIO baixou a versão mais recente da plataforma `espressif32`, que trouxe toolchains extras (por exemplo, `toolchain-riscv32-esp`), e a instalação parou por falta de espaço em disco. Antes do merge, rode o build na máquina da bancada, onde o toolchain já está instalado; o registro anterior (`docs/academico/checkpoint_2026-11-12/evidencias/build-firmware.log`) usava `framework-arduinoespressif32 @ 2.0.17` (ESP-IDF 4.4).

Isso também mostra um risco de reprodutibilidade: `firmware/platformio.ini` declara `platform = espressif32` sem versão. `communication/iot_transport.cpp` usa a configuração do ESP-MQTT do IDF 4.4 e não compila com o Arduino-ESP32 3.x / IDF 5. Recomenda-se fixar a versão da plataforma que fornece o Arduino-ESP32 2.0.17, depois de confirmar o número exato com `pio pkg list -d firmware` na máquina da bancada.

## O que continua pendente

- Compilar o firmware com estas mudanças (`platformio run -d firmware`) e fixar a versão da plataforma em `platformio.ini`.

- Gravar o firmware na placa e repetir o ensaio IoT de 30 s a 70 ms, comparando os descartes com o registro de 12/11.
- Confirmar na placa que o boot sem LCD não mostra regressões no fluxo USB e na interface legada.
- Envio em lote (várias amostras por mensagem MQTT) para reduzir a dependência da latência do PUBACK; não implementado nesta revisão porque muda o contrato `docs/mqtt_iot_v1.md` e o consumidor.
- Medição do eco por interrupção ou RMT em vez de espera ativa.
