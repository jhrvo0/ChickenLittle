# Dashboard e materiais de demonstração

## Implementação identificada

| Parte | Tecnologia / arquivos | Função disponível |
|---|---|---|
| Estrutura e aparência | `terminal/web/static/index.html`, `lab.css` | Navegação dos módulos, estados de conexão, marcas REAL/SINTÉTICO/DEMO/PENDENTE |
| Controle da aplicação | `lab.js` | Polling de sinais/estado, conexão, perfis, fonte de gestos, gate e ações |
| Motion Canvas | `canvas.js` | Visualização por partículas/ondas/fluxo/pulso usando distância e IR |
| Air Music | `music.js` | Síntese Web Audio, escalas, timbres e looper; áudio não foi validado por escuta nesta preparação |
| Motion Intelligence | `intel.js` e polling em `lab.js` | Sinais, modelos/experimentos e inferências com proveniência explícita |
| Servidor local | `terminal/web/server.py`, `session.py`, `ml_client.py` | HTTP, proteção Host/Origin/chave local, USB ou DEMO e proxy ML |
| Domínio de interação | `terminal/motionlab/` | Sinais, reconhecedores, portão de eventos, perfis e ações; externas desligadas por padrão |
| Experiência anterior | `terminal/web/static/legacy/` | Pet e Pet Launch; não é a tela principal do MotionLab |

O front-end atual é HTML/CSS/JavaScript com Canvas 2D, SVG e Web Audio, sem framework React ou plataforma Node-RED/Grafana. O Node é usado nos testes de código da interface; não é o servidor HTTP principal. Não foi identificado um arquivo Figma atual publicado.

## Telas e dados que o grupo pode documentar

| Tela | Objetivo / informação | Origem e limite |
|---|---|---|
| Início | Apresentação dos cinco módulos e conexão | Captura deve mostrar o estado real de conexão da sessão |
| Motion Control | Perfis de gatilho/ação, fonte regras/ML/TinyML, armar/desarmar e ações | Teclas do notebook não são atuador elétrico da protoboard |
| Motion Canvas | Visual reativo à distância/presença | Mouse/DEMO não devem ser apresentados como sensor físico |
| Air Music | Instrumento por distância e IR | Implementação não comprova áudio ouvido nem teste com a placa |
| Air Slides | Apresentação integrada e possibilidade de teclas externas | Controle de PowerPoint real depende de ensaio próprio; não realizado agora |
| Intelligence 05.1 — Sinais ao vivo | Distância bruta/filtrada, validade, IR, gestos e rejeições | Na sessão consultada: DEMO, sem sensor físico |
| Intelligence 05.2 — Modelos e experimentos | Modelo publicado, origem de treino e avaliações | Resposta atual: coorte DEMO avaliada; REAL e SYNTHETIC sem avaliação publicada nesse serviço; não preencher ausências com zero |
| Intelligence 05.3 — Inferências | Histórico da última janela de sessões persistidas, probabilidades, modelo e origem | Resposta atual: 6 itens, todos de entrada DEMO e treino `synthetic_simulator`; fora do gate de ações |

## Evidência HTTP desta preparação

[Respostas GET preservadas](evidencias/http-antes-capturas.json) e [requisição/resposta POST de inferência](evidencias/http-infer.json). A chave local de autorização não foi gravada nos arquivos de evidência.

| Rota consultada no dashboard existente | Resultado observado |
|---|---|
| `/api/state` | HTTP 200; conectado; porta `DEMO`; origem `DEMO`; mensagem de demonstração sem sensores físicos |
| `/api/live` | HTTP 200; quadros e eventos da demonstração |
| `/api/lab` | HTTP 200; estado do motor/perfis/indicadores |
| `/api/ml/status` | HTTP 200; `ready`, `mlp_compact`, modelo publicado `20261111T200245_b7c2e150`, treino sintético |
| `/api/ml/evaluations` | HTTP 200; DEMO `evaluated`; REAL `pending`; SYNTHETIC `pending` nesse serviço |
| `/api/ml/predictions` | HTTP 200; 6 previsões; `physical_validation=pending` |
| `POST /api/ml/infer` | HTTP 200 com 20 amostras da sessão DEMO já persistida; `input_origin=demo`, `trained_on=[synthetic_simulator]`, `event_gate_applied=false` |

Essas respostas comprovam o funcionamento HTTP e o vínculo ao modelo da demonstração. **Não comprovam a renderização visual dessas telas, a atualização de pixels no navegador, MQTT físico ou desempenho dos sensores.** O usuário informou conclusão da integração visual; código e testes também sustentam sua implementação. A captura visual desta preparação permaneceu bloqueada.

## Capturas manuais necessárias

Usar a interface existente em `http://127.0.0.1:8790/` enquanto o processo continuar ativo. Abrir por **127.0.0.1**, pois o servidor valida o Host; trocar por `localhost` pode resultar em HTTP 403.

| Nome sugerido | Tela / ação humana | O que precisa aparecer | Uso no modelo |
|---|---|---|---|
| `figura-4-dashboard-demo.png` | Abrir Motion Intelligence → 05.1 Sinais ao vivo | Nome da tela, distância/IR, série temporal, selo DEMO e estado de conexão | Figura 4 — dashboard em funcionamento, com legenda de software |
| `figura-5-prototipo-motionlab.png` | Abrir Início ou Motion Canvas da interface atual | Navegação e tela completa; indicar que é o protótipo funcional implementado | Figura 5 — imagem do front-end |
| `apoio-05-2-modelos-demo.png` | Intelligence → 05.2 Modelos e experimentos | Origem DEMO, modelo publicado, REAL pendente | Apoio técnico, se houver espaço |
| `apoio-05-3-inferencias-demo.png` | Intelligence → 05.3 Inferências | Identificador da sessão, entrada DEMO, treino sintético e previsões | Apoio técnico, se houver espaço |

Não remover o selo DEMO, preencher painéis vazios artificialmente ou renomear a imagem como validação física. Evitar capturar a aba de Classroom, WhatsApp ou dados pessoais ao redor. Capturar somente a janela relevante, preservar a imagem original e registrar horário, URL, origem e breve descrição numa nota junto ao arquivo. Os nomes acima são **reservas para arquivos a produzir manualmente**, não links para screenshots existentes.

A ferramenta de navegação encerrou a captura automática porque a revisão automática não conseguiu confirmar a URL ativa no Chrome/Windows. Não houve tentativa de contornar o bloqueio com outro mecanismo de controle de navegador. Este pacote não contém screenshots fabricados nem uma imagem de UI gerada para ocupar o lugar de evidência real.

## Procedimento de demonstração em software sem placa

1. Usar o dashboard existente e conferir no chip de conexão que a origem é **DEMO**. Não selecionar COM3.
2. Se a instância estiver desconectada e tiver sido iniciada com `--demo`, escolher exclusivamente **DEMO — sem ESP32**. Essa decisão e operação ficam para o apresentador; a sessão consultada nesta preparação já estava em DEMO.
3. Mostrar Início e os cinco módulos. Em Sinais ao vivo, observar variação dos dados gerados pelo simulador e registrar a origem.
4. Em 05.2, mostrar o experimento DEMO publicado e os estados pendentes das origens sem avaliação. Não usar F1 sintético como desempenho físico do dispositivo.
5. Em 05.3, relacionar a sessão `mqtt_demo_p01_42_6160d119` ao [recibo MQTT histórico](evidencias/mqtt-recibos-fase-c.txt), à [publicação do modelo](evidencias/fase-c-deployment.json) e à resposta de previsões. As previsões exibidas são de sessões persistidas na demonstração anterior; não afirmar que há broker em execução agora.
6. Explicar os dois fluxos de software independentes: DEMO serial virtual alimenta os sinais ao vivo; corpus recebido anteriormente por MQTT alimenta a inferência acadêmica.
7. Manter ações externas desabilitadas para esta demonstração de evidências; não é necessário enviar teclas para outros aplicativos ou alegar controle de atuador físico.

Se os processos existentes não estiverem mais ativos, os comandos abaixo descrevem a reprodução **software**, sem placa. Eles consultam o cache de previsões existente, sem ativar o worker de escrita. Não é necessário subir Docker para mostrar API e dashboard com os artefatos já disponíveis.

```powershell
# Executar da raiz do projeto, em dois terminais, só se os serviços não estiverem ativos.
# Escolher outra porta/configuração se houver conflito; não parar processos do usuário.
.\.venv\Scripts\python.exe -m ml.inference_api --deployment data/experiments/phase-c/delivery-stack/pipeline/deployment.json --experiments-root data/experiments/phase-c/delivery-stack/experiments --predictions data/experiments/phase-c/delivery-stack/pipeline/predictions.json
.\.venv\Scripts\python.exe -m terminal.web --demo --port 8790 --ml-api-url http://127.0.0.1:8768
```

Os comandos acima apenas expõem o cache persistido existente; não incluem `--watch-raw-root` e não iniciam geração contínua de novas previsões. A reprodução da stack inteira e dos testes de falha permanece documentada em `docs/motionlab_fase_c.md`; não executá-la às pressas com pouca RAM para fazer as imagens de amanhã.
