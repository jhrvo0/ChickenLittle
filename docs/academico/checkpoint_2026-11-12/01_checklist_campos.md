# Checklist de preenchimento humano por campo do modelo

Localização conferida na prévia do DOCX no Drive: páginas 1 a 6. O rodapé em cache diz “de 7”; localizar também pelo título da seção. Uma tabela de códigos começa na página 2 e continua na página 3. A infraestrutura começa na página 3 e termina na página 4. **Nada foi preenchido automaticamente no DOCX.**

Legenda: **DISPONÍVEL** = dado com fonte; **GRUPO** = decisão/informação humana; **PARCIAL** = há implementação/evidência limitada; **PENDENTE** = evidência ausente; **DOCENTES** = deixar em branco. As sugestões de situação abaixo são apoio técnico, não avaliação ou nota dos professores.

## Página 1 — identificação e integrantes

| Conferir | Campo exato | Informação disponível / ação humana | Fonte e limite |
|---|---|---|---|
| [ ] | Disciplina | DISPONÍVEL: Sistemas Embarcados – CESAR School | Já consta no modelo |
| [ ] | Professores | DISPONÍVEL: Bella Nunes e Jymmy Barreto | Modelo e enunciado |
| [ ] | Data do Check Point | GRUPO: modelo = 17/11/2026; entrega do relatório = 12/11/2026 informada pelo grupo | Confirmar se a avaliação também mudou; não substituir automaticamente |
| [ ] | Grupo (nº) | GRUPO: número não localizado | Não inferir do proprietário do GitHub |
| [ ] | Título do projeto | DISPONÍVEL: nome usado pela aplicação = MotionLab; repositório = ChickenLittle; MotionPet é histórico | Grupo confirma o título oficial |
| [ ] | Resumo do projeto | GRUPO: redigir as 2–3 linhas | Fatos de apoio: interação gestual; ESP32; distância/presença; interface local; caminho atual USB; MQTT demonstrado com simulação. Não atribuir MQTT físico ao sistema |
| [ ] | Representante do grupo | GRUPO: nome completo não confirmado | Não assumir que o proprietário do repositório seja o representante |
| [ ] | Integrante 1 — nome completo / GitHub / responsabilidade | GRUPO: fornecer os três campos | Existem 7 linhas no modelo; não preencher com autores de commits automaticamente |
| [ ] | Integrante 2 — nome completo / GitHub / responsabilidade | GRUPO: fornecer os três campos | Idem |
| [ ] | Integrante 3 — nome completo / GitHub / responsabilidade | GRUPO: fornecer os três campos | Idem |
| [ ] | Integrante 4 — nome completo / GitHub / responsabilidade | GRUPO: fornecer os três campos | Idem |
| [ ] | Integrante 5 — nome completo / GitHub / responsabilidade | GRUPO: fornecer os três campos | Idem |
| [ ] | Integrante 6 — nome completo / GitHub / responsabilidade | GRUPO: preencher se aplicável | Enunciado: grupo de 5–7, ressalvada manutenção do grupo de Projetos 6 |
| [ ] | Integrante 7 — nome completo / GitHub / responsabilidade | GRUPO: preencher se aplicável | Não inventar integrantes para completar linhas |
| [ ] | Como preencher | Preservar a orientação do modelo | Marcar opções e inserir imagens apenas na revisão humana |

## Página 2 — 1.1 Uso dos sensores e atuadores

Cada linha tem cinco campos: **Componente, Tipo, Função no projeto, Pino(s)/GPIO, Situação**. Inventário detalhado em [hardware e firmware](02_hardware_firmware.md).

| Conferir | Linha / campos | Fatos disponíveis | Situação a avaliar pelo grupo |
|---|---|---|---|
| [ ] | ESP32 — os cinco campos | DevKit 38 pinos; controlador; aquisição, TinyML, FreeRTOS e USB; GPIO5/34/35 | PARCIAL no escopo da disciplina: USB implementado e build aprovado; Wi-Fi/MQTT ausente |
| [ ] | Outro componente 1 — os cinco campos | HC-SR04; sensor; distância; TRIG=GPIO5, ECHO=GPIO34 via divisor; VCC=5 V | Leitura física conjunta relatada em 10/11; precisão/tensão não medidas; sem ensaio novo |
| [ ] | Outro componente 2 — os cinco campos | TCRT5000; sensor; presença/reflexão; DO=GPIO35, VCC=3,3 V; AO desconectado | Alternância física relatada em 10/11; sem ensaio novo |
| [ ] | Outro componente 3 — os cinco campos | Divisor resistivo; circuito passivo de condicionamento; R1=1 kΩ, R2=1 kΩ, R3=300 Ω; ECHO→GPIO34 | Não é sensor nem atuador. Classificar como componente passivo se incluído; 2,83 V é cálculo nominal |
| [ ] | Outro componente 4 — os cinco campos | Protoboards/jumpers; interconexão; duas placas com +5 V e +3,3 V separados, GND comum | Não são atuadores. Alternativa: mencionar nos detalhes do circuito e retirar a linha vazia |

Não listar LCD, potenciômetro, RGB, botões ou atuador físico como componentes em uso. O kit contém peças que não estão na montagem atual. O código histórico não comprova presença de componente na bancada.

## Página 2 — 1.2 Organização do circuito

| Conferir | Campo exato | Evidência / ação | Pendência ou ressalva |
|---|---|---|---|
| [ ] | Esquemático do circuito / Figura 1 | Inserir [circuito atual em PNG](figuras/figura-1-circuito-atual.png), conferido com a netlist | Diagrama técnico, sem foto nem simulação elétrica |
| [ ] | Foto da montagem física / Figura 2 | PENDENTE: foto real feita pelo grupo | Mostrar as duas protoboards, ESP32, HC-SR04, TCRT5000, divisor e GND comum; não alterar fios para obter a foto |
| [ ] | Arquivo no repositório | `hardware/wokwi/montagem_atual/diagram.json`; `hardware/netlist/motionpet_atual_sem_lcd.json`; figura preparada neste pacote | O modelo cita `/schematics`, pasta inexistente; registrar o caminho real e a divergência |
| [ ] | Circuito testado — individualmente / completo | Histórico registra testes individuais e resposta dos dois sensores juntos | Grupo pode indicar o ensaio funcional relatado, com data e limite. Não equivale a aprovação elétrica, precisão ou Wi-Fi/MQTT físico |
| [ ] | Situação — concluído / andamento / não iniciado | PARCIAL: sugestão técnica “Em andamento” no conjunto da disciplina | Foto, validação física documentada e comunicação sem fio pendentes |
| [ ] | Próximos passos | Usar lista factual em [pendências](05_pendencias_validacao.md) | Grupo redige com suas prioridades e responsáveis |

## Páginas 2 e 3 — 2.1 Códigos-fonte

| Conferir | Campo / linha | Tecnologia e caminho disponíveis | Progresso / situação |
|---|---|---|---|
| [ ] | Firmware — tecnologias / linguagem | C++17; Arduino-ESP32 2.0.17 / ESP-IDF 4.4.7; FreeRTOS; PlatformIO | Build atual aprovado |
| [ ] | Firmware — caminho | `firmware/`, entrada `firmware/main/main.cpp`, configuração `firmware/platformio.ini` | Modelo pede `/esp32-esp8266`; nome real difere |
| [ ] | Firmware — progresso ____ % | GRUPO: não há denominador de escopo fechado nem medição de percentual | Não preencher automaticamente. Se exigido número, grupo define critérios e cálculo explícitos |
| [ ] | Firmware — situação | PARCIAL: aquisição, serial, classificação e pet implementados; Wi-Fi/MQTT não implementado | Sugestão “Em andamento” |
| [ ] | Back-End — tecnologias / linguagem | Python 3.13 no venv; servidor HTTP da stdlib; pyserial; NumPy/scikit-learn; Paho MQTT; Airflow; MLflow | Não usa Flask/Django por padrão |
| [ ] | Back-End — caminho | `terminal/web/{server.py,session.py,ml_client.py}`, `terminal/motionlab/`, `ml/`, `ops/mlops/` | Modelo pede `/applications`; nome real difere |
| [ ] | Back-End — progresso ____ % | GRUPO: percentual não medido | Serviços e testes não definem, sozinhos, percentual do projeto |
| [ ] | Back-End — situação | PARCIAL: serial, API e pipeline MQTT simulado implementados; recepção da ESP32 por rede ainda não integrada | Sugestão “Em andamento” no escopo de Embarcados |
| [ ] | Front-End — tecnologias / linguagem | HTML, CSS, JavaScript, SVG inline; Canvas 2D; Web Audio | Sem React/Node-RED/Grafana/Figma identificados como implementação atual |
| [ ] | Front-End — caminho | `terminal/web/static/{index.html,lab.css,lab.js,canvas.js,music.js,intel.js}` | Versão anterior em `static/legacy/` |
| [ ] | Front-End — progresso ____ % | GRUPO: percentual não medido | Cinco módulos implementados não equivalem a 100% dos requisitos físicos |
| [ ] | Front-End — situação | Interface implementada; 20 testes Node aprovados; HTTP/API disponíveis; usuário informa integração visual concluída | Aceite visual/capturas desta rodada e demonstração física ainda pendentes |
| [ ] | O que já funciona | Apoio factual: [inventário](02_hardware_firmware.md), [evidências](README.md#verificações-desta-preparação) | Grupo redige; separar código, teste, simulação e relato físico |
| [ ] | Próximos passos | Foto, screenshots, equipe, organização/publicação do Git e futura rede da ESP32 | Não prometer desenvolvimento Wi-Fi antes da entrega de amanhã |

## Página 3 — 3.1 Fluxo de comunicação

| Conferir | Campo exato | Evidência / informação disponível | Limite |
|---|---|---|---|
| [ ] | Diagrama da arquitetura / Figura 3 | [Arquitetura em PNG](figuras/figura-3-arquitetura.png) e [fontes/fluxos](03_arquitetura_mqtt.md) | USB atual, MQTT de software e futuro Wi-Fi diferenciados |
| [ ] | Descrição do fluxo | Caminho USB, caminho MQTT simulado, retornos de ACK e ausência de atuador físico estão inventariados | Grupo escreve a descrição; não dizer que a ESP32 publica no broker hoje |
| [ ] | Tópico MQTT / Publisher / Subscriber / Payload | Tabela completa em [arquitetura e MQTT](03_arquitetura_mqtt.md#tópicos-existentes) | Incluir o recibo de aplicação, além da sessão |
| [ ] | Situação | PARCIAL para comunicação exigida na disciplina | MQTT simulado integrado; Wi-Fi/MQTT da placa ainda não iniciado |
| [ ] | Próximos passos | Futuro transporte da ESP32, acesso LAN ao broker, validação de reconexão e IPv6 | Implementação suspensa nesta preparação |

## Páginas 3 e 4 — 3.2 Infraestrutura local e nuvem

| Conferir | Campo exato | Informação disponível | Pendência |
|---|---|---|---|
| [ ] | Broker MQTT — local / ESP32 / nuvem | Local no notebook via Docker/WSL, Mosquitto 2.0.22 no Compose da Fase C | Não está na ESP32; porta do host publicada em `127.0.0.1:1883`, inacessível pela LAN da placa |
| [ ] | Back-end e dashboard — local / nuvem / detalhes | Local, Windows 11 ARM64; Python; API 8768 e dashboard 8790 observados nesta rodada | A porta padrão do dashboard é 8767; 8790 é configuração de demonstração |
| [ ] | Serviços de nuvem | Nenhum serviço de nuvem de execução identificado | GitHub é hospedagem de código, não backend/broker em nuvem; confirmar serviços externos eventualmente usados pelo grupo |
| [ ] | Situação (continua na página 4) | Infraestrutura local demonstrada em software; integração da placa por rede pendente | Sugestão “Em andamento” no escopo final da disciplina |
| [ ] | Próximos passos (página 4) | Acesso LAN, ensaio físico e esclarecimento de IPv6 | Não alterar firewall, WSL ou visibilidade neste trabalho |

## Página 4 — 4. Documentação Git

| Conferir | Campo exato | Evidência / informação disponível | Pendência |
|---|---|---|---|
| [ ] | URL do repositório | `https://github.com/jhrvo0/ChickenLittle` | Preservar URL real |
| [ ] | Visibilidade | Consulta autenticada: **PRIVATE / privado** | Enunciado exige público; não foi alterada |
| [ ] | Gestão de tarefas — Projects / Issues / não utilizado | API de Issues retornou lista vazia; `has_projects=true` só indica recurso habilitado | GRUPO confirma se há uso de Projects ou gestão fora do GitHub. Não inferir uso a partir de habilitação |
| [ ] | Commits do grupo — todos já fizeram | Histórico local tem 21 commits em HEAD e um nome de autor: João Henrique | Não há lista do grupo nem comprovação de contribuição de todos; não marcar sem confirmação |
| [ ] | Total aproximado de commits | DISPONÍVEL: **21 no HEAD local consultado**, incluindo o histórico existente | Não contar alterações não commitadas como commits |
| [ ] | README.md — situação / observações | Presente, com execução e limites; contém trechos de estado anteriores e faltam equipe/@GitHub/Google Sites | Conteúdo parcial; dados e revisão humana pendentes |
| [ ] | /docs — situação / observações | Documentação técnica e fontes acadêmicas presentes | Relatório humano final/PDF, foto e validações ainda faltam |
| [ ] | /applications — situação / observações | Pasta literal ausente; equivalentes em `terminal/`, `terminal/web/`, `ml/` | Registrar equivalência e confirmar aceite dos nomes; não declarar pasta existente |
| [ ] | /esp32-esp8266 — situação / observações | Pasta literal ausente; firmware em `firmware/` | Mesma ressalva |
| [ ] | /schematics — situação / observações | Pasta literal ausente; netlist/Wokwi em `hardware/` | Mesma ressalva; não mover arquivos às pressas |

O conteúdo atual tem muitas alterações não commitadas e arquivos novos; **presença local não comprova publicação no GitHub**. Esta tarefa não fez commit ou push. O enunciado de Embarcados diz que os itens por diretório são obrigatórios; os nomes diferentes precisam ser tratados explicitamente pelo grupo/professores.

## Página 5 — 5.1 Dashboard

| Conferir | Campo exato | Informação disponível | Limite / ação |
|---|---|---|---|
| [ ] | Tecnologia | HTML/CSS/JavaScript, Canvas 2D/Web Audio; backend HTTP Python; ML por API | Não substituir por tecnologia ilustrativa do modelo |
| [ ] | Dados exibidos | Distância, validade/idade, IR, gestos/rejeições/ações; avaliações e inferências com origem/treino identificados | Ver inventário da UI; no HTTP atual, entrada DEMO e treino sintético |
| [ ] | Atualização em tempo real — sim / parcial / ainda não | Implementado polling de sinais (~70 ms) e estado (~1 s); HTTP retorna quadros DEMO atuais | Evidência de software; frequência física efetiva não medida nesta rodada |
| [ ] | Envia comandos aos atuadores — sim / não / previsto | **Não há atuador físico na montagem vigente** | Ações em música/canvas/slides e comandos do pet são software; não provar motor, relé ou LED comandado |
| [ ] | Situação | Interface implementada; teste de código e HTTP aprovado | Grupo decide situação com escopo explícito; caminho Wi-Fi físico continua pendente |
| [ ] | Próximos passos | Capturas manuais, foto, ensaio com placa e ensaio de rede posterior | Nenhum dado DEMO deve ser apresentado como medição física |

## Página 5 — 5.2 Protótipo do Front-End e imagens

| Conferir | Campo exato | Informação disponível | Ação humana |
|---|---|---|---|
| [ ] | Ferramenta e link | Protótipo funcional é a própria interface: `http://127.0.0.1:8790/` na demonstração atual | URL local não abre no computador dos docentes. Nenhum link Figma/publicação pública atual confirmado |
| [ ] | Telas previstas | Início; Motion Control; Motion Canvas; Air Music; Air Slides; Motion Intelligence (ao vivo, modelos, inferências); legado `/legacy/` | Detalhes em [dashboard](04_dashboard_evidencias.md) |
| [ ] | Print do dashboard / Figura 4 | PENDENTE: screenshot manual da interface em execução | [Roteiro de captura](04_dashboard_evidencias.md#capturas-manuais-necessárias) |
| [ ] | Imagem do protótipo do Front-End / Figura 5 | PENDENTE: screenshot manual de outra tela do protótipo funcional atual | Não usar imagem de redesign antigo do pet como MotionLab atual |

## Página 6 — painel dos docentes

Deixar sem preenchimento pelo grupo: observações e “Atende?” dos oito pontos (sensores, circuito, códigos, fluxo, infraestrutura, Git, dashboard, protótipo); evolução; nota /15; parecer/encaminhamentos; docente/data. O checklist apenas identifica esses campos. Não simular avaliação, assinatura ou nota.

## Rodapés e revisão final

- [ ] Preencher “Grupo ____” nos rodapés com o número confirmado, preservando o layout.
- [ ] Conferir paginação real no editor; os valores “de 7” estão em cache e divergem da prévia de 6 páginas.
- [ ] Manter identificação de DEMO/SINTÉTICO e as ressalvas das figuras técnicas.
- [ ] Grupo redigir resumo, funcionamento, descrições e próximos passos; usar IA apenas dentro das regras declaradas da disciplina.
- [ ] Revisar todos os campos entre colchetes; nenhum percentual é fornecido por este pacote.
- [ ] Exportar/revisar a versão a entregar sem escrever no painel dos docentes; confirmar formato e horário do envio de amanhã no canal oficial.
