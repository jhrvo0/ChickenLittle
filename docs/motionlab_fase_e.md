# MotionLab — Fase E: transporte IoT nativo da ESP32

> Atualização: a conexão física posterior, incluindo os descartes observados e os limites do ensaio, está registrada em [bancada IoT de 12/11/2026](motionlab_bancada_iot_2026-11-12.md). O relato abaixo descreve o estado anterior da Fase E.

Data: 11/11/2026. Escopo: implementação e testes **exclusivamente em software**.
Sem COM3, upload, mudança elétrica, alteração visual ou edição do checkpoint.
O pacote `docs/academico/checkpoint_2026-11-12/` e os relatórios originais foram
preservados. Esta fase prepara a validação física; não declara que ela aconteceu.

## Arquitetura entregue

```text
                                  ┌─ fila inferência → TinyML → domínio local
HC-SR04 + TCRT5000 → mesma aquisição├─ fila USB → JSONL v1 → MotionLab atual
                                  └─ fila IoT estática → task de rede → Wi-Fi STA
                                       → MQTT/TLS QoS 1 → Mosquitto autenticado
                                       → consumidor → SQLite isolado sem rótulos
                                       → filtro/features canônicos → modelo configurado
                                       → /v1/predictions → /api/ml/predictions
                                       → Motion Intelligence existente
```

Não há nova arquitetura de aquisição, classificação ou dashboard. A ESP32 segue
fazendo inferência local e USB; o caminho IoT usa a mesma aquisição e a mesma
representação de validade. A classificação no notebook reaproveita as features,
modelo e API já existentes. O novo tópico por amostra evita acumular sessões
acadêmicas inteiras ou inventar rótulos, participantes e hora UTC no firmware.
O contrato completo, chaves e limites estão em [mqtt_iot_v1.md](mqtt_iot_v1.md).

## Firmware, filas e recuperação

`iot_core` é C++ portable: fila circular, serialização, contadores e máquina de
conexão. `iot_transport` adapta ao Wi-Fi Arduino/ESP-MQTT **já fornecidos** pelo
ESP-IDF 4.4.7/Arduino 2.0.17 instalado. Não foi adicionada biblioteca externa.
A API MQTT da versão 4.4 usa configuração plana; não se misturou a API do IDF 5.

`TaskSensorAcquire` apenas copia uma estrutura em região crítica curta; não faz
rede, espera de fila nem alocação de heap. A nova task de prioridade 1 tem pilha
estática de 4.096 bytes. O cliente MQTT tem task própria de prioridade 1 e pilha
de 6.144 bytes. Aquisição/inferência mantêm suas prioridades 4/3.

Fila: **32 amostras / 1.056 bytes**; política descartar a amostra nova quando cheia.
Uma única publicação QoS 1 fica pendente, com a cabeça preservada até PUBACK.
Timeout ou erro destrói cliente/outbox antes de repetir. Backoff Wi-Fi e broker
separados, de 1 a 60 s, timeout de conexão/PUBACK de 10 s. Heap do Wi-Fi/TLS é do
SDK; não se afirma consumo zero de heap. A fila é volátil e não evita perdas em
interrupções prolongadas ou reboot.

Sem header local com SSID, host, senha do broker e CA (ou opt-in TCP de laboratório),
o transporte permanece `disabled`; a interface USB e TinyML funcionam. TLS valida
CA/hostname e aguarda relógio civil via SNTP na task de rede. O payload continua
usando relógio monotônico de aquisição. Sem NTP disponível, `clock_wait` fica
observável e a fila pode descartar; não se desabilita validação de certificado.
O driver também foi corrigido para aceitar a virada modular do timestamp USB de
32 bits, reproduzida em teste C++ de host.

`IOT_DIAG` curto ou em comando JSONL retorna ACK v1 separado do `DIAG` anterior:
estado, dispositivo/sessão, fila, descartes, PUBACKs, reconexões, erro de publicação
e high-water mark da task. Estados: `disabled`, `wifi_backoff`, `wifi_connecting`,
`clock_wait`, `broker_backoff`, `broker_connecting`, `online`. Contadores completos
de aquisição/perdas são de 64 bits; a apresentação compacta dos contadores de
perdas/ACKs no diagnóstico usa seus 32 bits inferiores. Nenhuma senha é impressa.

## Configuração segura e separação da Fase C

O exemplo público é `firmware/communication/iot_config.example.h`; copiar para
`iot_config.local.h`, ignorado pelo Git, somente quando formos validar a placa.
O binário compilado incorpora credenciais: mantê-lo privado. O ambiente
`esp32dev-iot-example` compila o ramo TLS com placeholders e ignora o header local;
**não é firmware pronto para uso**, pois o certificado do exemplo é deliberadamente
um placeholder. O ambiente padrão continua `esp32dev`.

`ops/iot/compose.yaml` cria um broker independente, sem reiniciar o Compose da Fase C.
Apenas TLS/8883, autenticação obrigatória, ACL, persistência e limites de filas/memória.
Não há listener público anônimo. `MOTIONLAB_BROKER_BIND_IP` deve ser um IP privado
pertencente ao host do Docker; não há padrão `0.0.0.0`. Nenhum redirecionamento de
porta no roteador deve ser criado. O broker loopback da Fase C permanece inalterado.

Preparar em `ops/iot/local/` (ignorado): `passwords` gerado por `mosquitto_passwd`,
`ca.crt`, `server.crt` e `server.key`. Senhas são digitadas interativamente, sem `-b`
nem argv; conta por MAC com username igual ao `device_id`, mais `motionlab_ingest`
e, se necessário, `motionlab_simulator`. O certificado deve ter SAN com o nome/IP
exato configurado no firmware. Chaves e arquivo de senhas precisam ser restritos
ao operador e legíveis pelo usuário do Mosquitto no container (UID 1883). A ACL
de exemplo restringe cada dispositivo a `motionlab/v1/devices/%u/samples`.

Nesta máquina o Engine roda **dentro do WSL**, não no host Windows. O IP LAN do
Windows não pertence ao Engine; colocá-lo diretamente no Compose pode falhar ao
fazer bind. Para uso futuro, escolher uma destas opções com o usuário:

1. Broker num host Linux privado acessível à ESP32, com o bind no IP desse host.
2. Broker no WSL com encaminhamento Windows→WSL apenas de 8883 e regra de firewall
   privada limitada ao IP da ESP32. Preparar então um script administrativo revisável
   conforme as regras globais; não criar regra, portproxy ou mudança de rede agora.
3. Broker nativo no notebook, instalado em escopo de usuário quando autorizado,
   adaptando caminhos do `.conf` e bind explícito ao IP privado Windows.

Não foi validado alcance pela LAN/WSL. A integração desta fase usa apenas loopback.
Autenticação sem TLS não protege credenciais contra escuta; o opt-in TCP do firmware
é para laboratório controlado e não é o exemplo de implantação LAN.

### Alternativa de encaminhamento sem instalar broker no Windows

O Windows e o WSL desta máquina usam interfaces diferentes: na verificação local,
o Windows estava em `192.168.15.14` e o WSL em `172.19.130.242`; o WSL não conseguiu
fazer bind no endereço do Windows. Esses endereços podem mudar. Para reutilizar o
broker TLS no WSL, `ops/iot/lan_relay.py` oferece um encaminhador TCP no Windows:
ele escuta um IPv4 privado específico, aceita somente a rede explicitamente indicada
e encaminha para `127.0.0.1:8883`. O TLS permanece entre a ESP32 e o Mosquitto;
o relay não termina TLS nem precisa das credenciais. Não use `0.0.0.0`.

Depois de preparar certificados, senha, ACL e broker como descrito acima, publicar
o broker no loopback do WSL e confirmar que o Windows o alcança por `127.0.0.1:8883`.
Com a rede Wi-Fi privada e o endereço da ESP32 confirmados, em outro terminal:

```powershell
# Exemplos: substitua os endereços pelos atuais; prefira o IPv4 da ESP32 com /32.
.\.venv\Scripts\python.exe ops/iot/lan_relay.py `
  --listen-address 192.168.15.14 --allow-network 192.168.15.30/32
```

O certificado do broker precisa conter o IPv4 do Windows no SAN e o firmware deve
conectar a esse mesmo IPv4. O usuário precisa manter o processo ativo e encerrá-lo
ao fim da bancada. O firewall do Windows ainda pode bloquear a entrada: se necessário,
preparar uma regra administrativa revisável, limitada à rede privada e ao IP da ESP32;
nenhuma regra é criada pelo relay. O IP da placa precisa ser conhecido antes de usar
o filtro `/32`; não adivinhar nem inserir senha Wi-Fi em comandos ou documentação.

**Limite:** o relay foi exercitado apenas em loopback com dados de teste. Ainda não
foram verificados o acesso pelo endereço Wi-Fi, o encaminhamento Windows → WSL,
o comportamento do firewall ou uma conexão física da ESP32. Um teste de loopback não
substitui essas etapas; se o loopback do WSL não estiver acessível ao Windows, ajustar
o ambiente antes de tentar a placa.

Consumidor e API existentes aceitam ativação explícita, sem modificar rotas:

```powershell
# Pré-condição: broker privado/TLS preparado; usuário/senha somente no ambiente
# MOTIONLAB_MQTT_USERNAME e MOTIONLAB_MQTT_PASSWORD do processo, sem registrá-los.
.\.venv\Scripts\python.exe -m ml.mqtt_ingestion consume `
  --host motionlab-broker.local --port 8883 --mqtt-ca ops/iot/local/ca.crt `
  --allow-devices --allow-real --client-id motionlab-iot-ingest-v1 `
  --data-root data/experiments/phase-e/live/raw --iot-db data/iot/telemetry.sqlite3

# Em processo separado, com publicação de modelo confiável escolhida explicitamente:
.\.venv\Scripts\python.exe -m ml.inference_api `
  --deployment data/experiments/phase-c/delivery-stack/pipeline/deployment.json `
  --experiments-root data/experiments/phase-c/delivery-stack/experiments `
  --watch-iot-db data/iot/telemetry.sqlite3 --predictions data/iot/predictions.json `
  --port 8769
```

O endpoint da API configurado no MotionLab deve apontar para esse processo na futura
validação. A porta 8769 é um exemplo livre a conferir; não trocar nem parar a API
usada pelo grupo. Um único worker pode observar tanto `--watch-raw-root` quanto
`--watch-iot-db`; não executar dois processos escrevendo o mesmo predictions.json.
O client ID do consumidor deve ser estável e exclusivo no broker.

## Proveniência e compatibilidade

O consumidor de sessões completas/simulador permanece compatível. Amostras IoT
vão para SQLite separado; recebê-las não inicia treino, seleção, avaliação ou
alteração de `latest`. A inferência produz `scope=live_iot_unlabelled`, sem rótulo
verdadeiro e sem alimentar `data/raw/real`. A avaliação acadêmica continua exigindo
coleta rotulada e partição por grupos, incluindo teste reservado.

`real_hardware` é uma declaração, inclusive quando publicada por host de testes.
Não implica bancada verificada, precisão, qualidade do modelo ou desempenho físico.
`physical_validation=pending` acompanha persistência e previsões. A API do dashboard
permanece v1; a nova fonte aparece entre suas previsões existentes. Nenhum componente
visual, mecanismo de gesto do navegador ou rota `/api/ml/*` foi redesenhado.

## Evidências de software e memória

| Nível | Evidência desta fase | Limite |
|---|---|---|
| Implementado | Transporte ESP32, núcleo, backend, TLS/ACL, inferência IoT | Código inspecionado, ainda sem execução na placa |
| Compilado | `esp32dev` e `esp32dev-iot-example`, ambos SUCCESS | Compilação Xtensa, não execução ESP32 |
| Testado em host | 21 testes IoT C++ real em DLL + regressões USB/sensores; 37 testes backend | Eventos/rede do núcleo são injetados; driver Wi-Fi real não roda no host |
| Regressão | 652 testes Python: **649 aprovados, 3 skips**, 0 erros/falhas, 53,834 s; 20 JavaScript aprovados | Skips exigem `FRITZING_PARTS_DIR`; avisos conhecidos de MLP fixture/SQLAlchemy |
| Integração | 8 verificações: Mosquitto real/TLS, autenticação, ACL, duplicação/conflitos/pacote inválido, reinícios, simulador antigo, SQLite, inferência, HTTP e proxy do dashboard | Publicador no notebook, inclusive fixture gerada pelo serializador C++ |
| Física | **Pendente** | Não houve Wi-Fi da ESP32, upload, sensor→MQTT físico nem medição de heap na placa |

Build comparativo medido pelo linker/PlatformIO, mesma placa e partição de aplicação:

| Build | RAM estática (de 327.680 B) | Flash aplicação (de 1.310.720 B) |
|---|---:|---:|
| Antes da Fase E | 24.668 B (7,5%) | 322.881 B (24,6%) |
| Novo padrão, IoT sem credenciais | 55.260 B (16,9%) | 921.133 B (70,3%) |
| Novo exemplo TLS | 55.568 B (17,0%) | 936.789 B (71,5%) |
| Acréscimo do exemplo TLS | **30.900 B** | **613.908 B** |

`nm` confirma fila 1.056 B, payload 1.024 B, stack estática da task IoT 4.096 B.
Esses valores **não medem heap/pico de TLS, fragmentação, tempo de CPU, RF ou
autonomia**. Existe espaço de flash no build; margem de heap/stack efetiva, latência
e comportamento sob desconexão só podem ser confirmados posteriormente na placa.

Comandos executáveis sem placa:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=data/experiments/phase-e/pytest.xml
node --test tests/test_web_ui.cjs tests/test_guide_ui.cjs tests/test_lab_ui.cjs
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32dev -e esp32dev-iot-example

# Conferir memória antes. Usa só broker64MB já em cache, OpenSSL do Git e recursos
# exclusivos da execução; não sobe Airflow/MLflow nem interrompe outros servidores.
.\.venv\Scripts\python.exe ops/iot/verify_broker.py --compile-firmware-host
```

Logs/JUnit/JSON ficam em `data/experiments/phase-e/`, ignorado. `integration.json`
registra os checks e sua pasta isolada. O verificador remove apenas seu container
de nome aleatório e processos que ele próprio criou; não usa down/prune na Fase C.
Credenciais/certificados gerados são efêmeros de teste, não configuração da bancada.
Antes/depois, hashes verificam os arquivos protegidos e o staged anterior permanece
com os mesmos três renomes. Nenhum commit, push, merge, reset ou clean foi feito.

## Procedimento físico posterior — executar com o usuário, um passo por vez

**Nenhum passo abaixo foi executado nesta fase.** Registrar operador, data/hora,
device/session, versão/hash do binário, logs, condições de rede, falhas e recuperação.

1. Conferir visualmente a montagem contra `docs/bench_verified_wiring.md`, a netlist
   atual sem LCD e `hardware/wokwi/montagem_atual/diagram.json`. Manter o divisor do
   ECHO, HC-SR04 em 5 V, GPIOs em 3,3 V, TCRT5000 em 3,3 V e LCD fora. Não alterar
   fios nem pedir medição de tensão sem instrumento.
2. Identificar com o usuário quem usa COM3; combinar interrupção somente na janela
   de bancada. Fechar o proprietário da porta com autorização e confirmar exclusividade.
   Registrar versão/DIAG atuais. Não abrir um segundo monitor simultâneo.
3. **Backup antes do upload:** ler ID/tamanho de flash com esptool, confirmar tamanho
   real e então fazer `read_flash 0x0 <tamanho_confirmado> <backup.bin>` na COM3 usando
   o esptool do venv. Guardar SHA-256, comando, bootloader/partições e caminho privado.
   Um `firmware.bin` compilado no notebook não prova ser o firmware atual da placa.
   Se o backup não for obtido/verificado, parar antes de gravar.
4. Preparar o broker LAN/TLS/ACL sem exposição pública. Resolver o acesso Windows/WSL
   e eventual firewall com procedimento administrativo separado; testar TLS/credenciais
   no notebook e negar acesso anônimo, senha incorreta e tópico de outra conta.
5. Copiar o header de exemplo para o arquivo local ignorado e preencher Wi-Fi, host,
   senha do usuário correspondente à MAC, CA pública e NTP autorizado. Não copiar
   chave privada do broker para a ESP32. Conferir que host/IP coincide com SAN.
6. Compilar `esp32dev` localmente, arquivar hash/binário privado e revisar a comparação
   com o backup. Combinar o upload e gravar uma vez, pela thread principal. O ambiente
   `esp32dev-iot-example` com placeholders nunca deve ser usado na bancada.
7. Confirmar boot e serial JSONL v1 com o mesmo cliente usado antes. Conferir sensores,
   TinyML/gestos e `DIAG`; não considerar UART ROM inicial evidência de protocolo quebrado.
8. Executar `IOT_DIAG`: conferir device/session, `wifi_connecting`, `clock_wait` quando
   aplicável e `online`. Se houver falha, resolver por estado sem despejar credenciais.
9. Iniciar consumidor com `--allow-devices --allow-real`, DB exclusivo e client ID
   estável; aguardar `subscribed` antes da coleta. Confirmar amostras e COMMIT no SQLite,
   validade e monotonicidade. O campo `real_hardware` sozinho não comprova esta etapa.
10. Iniciar API de teste em porta livre com `--watch-iot-db`, modelo explícito e arquivo
    de previsões separado. Conferir `/v1/predictions`, proxy e exibição no Motion
    Intelligence sem perturbar o servidor do grupo. Registrar `trained_on` do modelo:
    modelo só treinado em simulação continua experimental com entradas físicas.
11. Comparar USB/MQTT no mesmo período pela distância, IR, validade e timestamp modular
    comum. Não exigir igualdade dos contadores de envelope USB e aquisição IoT.
    Registrar saltos, perdas da fila, PUBACKs e atrasos; conferir aquisição/TinyML ativos.
12. Desconectar apenas o Wi-Fi da bancada e depois parar apenas o broker de teste,
    separadamente. Observar fila limitada, descartes e backoff; recuperar cada um e
    confirmar sessão/seq/conteúdo preservados nos retries, sem ações gestuais indevidas.
    Medir heap mínimo e HWM durante TLS/reconexão via diagnósticos; não usar RAM estática
    do build como se fosse essa medição. Reboot deve gerar outra sessão e perder a fila.
13. Arquivar registros verificáveis da sessão e classificar o que de fato foi validado.
    Se necessário, restaurar o backup somente com o usuário e autorização de gravação.
    Não marcar todo o projeto como validado por uma única conexão bem-sucedida.

Para a disciplina, continuam pendentes: procedimento físico registrado (quando a
modalidade física for adotada), medições reais de heap/latência/perdas, generalização
dos modelos com corpus físico reservado, e a conclusão pelo grupo dos documentos,
capturas e entregas acadêmicas. Esta fase não altera nem completa automaticamente
o artigo SBC, autores/equipe, Google Sites ou o relatório do checkpoint.

## Arquivos da implementação

Criados: `firmware/communication/iot_core.{h,cpp}`, `iot_transport.{h,cpp}`,
`iot_config.example.h`, `ml/iot_ingestion.py`, `ops/iot/{compose.yaml,
mosquitto-lan.conf,mosquitto-lan.acl,verify_broker.py}`, `tests/test_firmware_iot.py`,
`tests/test_iot_ingestion.py`, este documento e `docs/mqtt_iot_v1.md`.

Modificados nesta fase: `firmware/main/{main.cpp,README.md}`,
`firmware/communication/jsonl_protocol.cpp`, `firmware/sensors/sensors_driver.cpp`,
`firmware/platformio.ini`, `ml/{mqtt_ingestion.py,prediction_worker.py,inference_api.py}`,
`.gitignore`, a exclusão de segredos locais no contexto em `.dockerignore` e a decisão
técnica no `AGENTS.md`. As demais alterações presentes no
checkout são anteriores à fase e foram preservadas.
