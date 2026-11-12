# MotionLab — direção visual (redesign 2026-11-11)

Escopo: só a camada visual (`terminal/web/static/`). Contratos de API, motor, ML e firmware não mudam.
As imagens de referência entregues pelo usuário serviram de clima (escuro, sinal, mão, espaço), não de layout.

## 1. Diagnóstico da UI anterior

O que fazia a primeira versão parecer protótipo ("slop"):

1. **Tudo é caixa.** Cada grupo vira `.panel` com borda, fundo em gradiente e raio de 16 px. Caixa dentro de caixa (kv dentro de card dentro de painel). Não há hierarquia: todos os blocos pesam igual.
2. **Texto fazendo o trabalho do desenho.** Cards da home com parágrafos de 25 palavras, `hint` em todo painel, tabela de bindings com coluna "Origem" e dica sob cada gatilho. A tela se lê, não se vê.
3. **Cor sem economia.** Ciano, violeta, âmbar, verde, rosa, amarelo e vermelho aparecem ao mesmo tempo, quase sempre saturados e com `box-shadow` de brilho. O gradiente ciano→violeta→âmbar no título da home é o clichê "futurista".
4. **Tipografia sem voz.** Bahnschrift 600 em todo título, mono 10–11 px em caixa-alta em todo rótulo. Não há contraste de escala (o maior texto de uma tela de trabalho tem 22 px) nem de peso.
5. **Trilho de 232 px com lista de texto** que compete com o conteúdo, e topo com quatro grupos de controles do mesmo peso.
6. **Gráficos genéricos.** Barras cheias de altura crescente no Air Music, ring de looper com trilho grosso cinza, gráfico do Intelligence com grade e marcadores pesados.
7. **Estados pouco legíveis.** "Armado" é um pill verde igual ao de "conectado"; demo aparece como etiqueta solta; real/sintético/pendente usam badges quase idênticos.

## 2. Direção: *instrumento de bancada*

Uma peça de laboratório bem desenhada, não um dashboard: superfície escura e quente, muita área vazia, linhas finas,
números grandes e leves, e luz só onde há sinal. A estética vem do **sinal real** (a distância desenhada, o IR acendendo,
o gesto passando pelo portão), não de enfeite. Referências de família: osciloscópio de estúdio, sintetizador modular,
software de áudio sóbrio.

Três palavras: **preciso, quieto, vivo**.

### Princípios
- **Uma superfície, não cartões.** O conteúdo mora direto no fundo; grupos se separam por espaço e por fios de 1 px. Caixa só para o que é objeto (o slide, o diálogo, o HUD).
- **Luz = informação.** Só brilha o que está ativo agora (IR aceso, nota tocando, gesto disparado). Nada de glow decorativo.
- **Uma cor por canal, e pouca.** Cores semânticas dessaturadas; o resto é escala de cinza quente.
- **Escala tipográfica com contraste.** Títulos e leituras grandes em peso leve (300); rótulos pequenos em mono espaçado. Nada no meio-termo.
- **Texto mínimo.** Rótulo de 1–3 palavras; explicação longa só onde há risco (ações no sistema, avaliação real × sintética).
- **Honestidade visível.** Demo, sintético, real e pendente têm marcas gráficas distintas, não só palavras.

## 3. Sistema visual

### Tipografia (só fontes do sistema: CSP `'self'`, offline)
| Papel | Fonte | Uso |
|---|---|---|
| Display | Segoe UI Variable Display 300 (fallback Segoe UI Light) | títulos de tela (40–64 px), slide, home |
| Numerais | Bahnschrift Light/SemiLight, `tabular-nums` | distância, nota, F1, contadores |
| Texto | Segoe UI Variable Text 400/600 | corpo, botões, listas |
| Rótulo | Cascadia Mono 500, 10.5 px, `letter-spacing .14em`, caixa-alta | eyebrows, eixos, metadados |

Escala: 10.5 · 12 · 13.5 · 15 · 18 · 24 · 36 · 56 · 88 px.

### Paleta
- Fundo `#0a0a0b`; superfície elevada `#121214`; fio `rgba(255,255,255,.07)` / forte `.12`.
- Tinta `#ecebe6` (quente), secundária `#a09e97`, terciária `#64625d`.
- Canais (dessaturados, sem glow): **ultrassom** `#7cc9c0`, **IR** `#e2a15c`, **ML host** `#a99cf0`, **TinyML/simulador** `#dc8fb0`, **regras** = tinta.
- Estados: ok `#8fcf9d`, atenção `#d9b866`, erro `#e0735f`.
- Regra: cor de canal só em traço, ponto ou numeral; preenchimento grande só no estado ativo.

### Luz, profundidade, transparência
- Profundidade por **valor**, não por sombra: fundo → superfície (+3%) → objeto flutuante (+6% e sombra longa e difusa).
- Transparência só em sobreposições (HUD do canvas, HUD de gesto, diálogo) com `backdrop-filter` leve.
- Um único halo ambiente, muito baixo, no canto superior direito da tela (o "horizonte" das referências), sem gradiente arco-íris.

### Movimento
- Curva padrão `cubic-bezier(.2,.7,.2,1)`; 160 ms para hover, 320 ms para troca de tela, 600 ms para "respiração" de estado ao vivo.
- Entrada de tela: fade + 4 px. Nada salta ou quica. `prefers-reduced-motion` zera tudo.
- Microinterações carregam estado: o ponto ao vivo respira; o portão de gesto pisca a linha da regra que disparou; o slide desliza na direção do gesto.

### Grid, espaçamento e ritmo
- Base 4 px; passos 8 · 12 · 16 · 24 · 32 · 48 · 64.
- Trilho de 72 px (ícones); topo de 72 px; margem de conteúdo 40 px (24 px abaixo de 1100 px).
- Conteúdo em 12 colunas com calha de 24 px; títulos alinham com a primeira coluna; leituras numéricas alinham à direita.
- Ritmo vertical: título de tela → 32 px → conteúdo; grupos separados por 48 px ou por um fio com 24 px de cada lado.

### Estados
| Estado | Marca |
|---|---|
| hover | tinta sobe para `--ink`, fio fica `.12`; sem deslocamento |
| ativo/selecionado | fio interno de 1 px na cor do canal + texto em tinta plena |
| **armado** | interruptor com trilho claro e rótulo "Armado"; o ponto respira em verde suave |
| pausado/bloqueado | rótulo em tinta terciária, ícone de cadeado, sem cor |
| erro | texto e ponto em `--bad`, sem fundo vermelho |
| **ao vivo** | ponto verde que respira + leitura atualizando; "Ao vivo" só com frames frescos |
| **demo** | marca violeta tracejada `DEMO` em toda leitura derivada do simulador |
| sintético | marca âmbar com hachura; nunca ao lado de número sem o rótulo |
| real | marca sólida verde |
| pendente | contorno tracejado cinza, sem número |

### Linguagem de gráficos e sinais
- Linha fina (1.25 px) e contínua para a distância filtrada; leituras brutas como pontos de 1 px a 35%.
- IR como barra de luz âmbar na base (é um canal binário: liga/desliga).
- Eventos como marcas em trilhas: preenchido = executado, contorno = observado, tracejado = rejeitado.
- Zona ativa como faixa quase invisível; eixos com 3–5 marcas, rótulos mono 10 px.
- Nunca grade densa; nunca gradiente sob a curva.

### Linguagem dos módulos
Cada módulo tem um **objeto central** e controles periféricos:
Control = mapa gesto→ação; Canvas = a obra em tela cheia; Music = a régua de notas; Slides = o slide; Intelligence = a linha do tempo de sinal.

## 4. Conceito por tela

### Home / hub
- **Objetivo visual:** apresentar o instrumento vivo antes de qualquer texto.
- **Composição:** à esquerda, título "MotionLab" em 88 px leve e uma linha de subtítulo; à direita, o **campo do sensor** — arcos concêntricos finos (o cone do ultrassom) com o ponto da mão na distância real e o anel âmbar do IR. Embaixo, índice dos cinco módulos como uma fileira de entradas numeradas (número mono, nome, verbo de 2–3 palavras), separadas por fios, sem cartões. Conexão compacta no canto inferior direito.
- **Clima:** silencioso; o único movimento é o sinal.
- **Ao vivo / gestual:** o campo só se move com frames reais (ou com a marca DEMO).

### Motion Control
- **Objetivo:** ler em um segundo "este gesto faz isto, e está armado".
- **Composição:** coluna de perfis (lista tipográfica) | **mapa gesto→ação** no centro, cada linha com glifo do gatilho, fio conector e ação | coluna de segurança com sliders finos. Atividade como fita de log abaixo do mapa.
- **Seguro:** o interruptor "Ações no sistema" fica isolado no topo da coluna de segurança, com a única explicação longa da tela.
- **Diferencial:** a linha do gatilho acende quando o gesto passa pelo portão.

### Motion Canvas
- **Objetivo:** a obra ocupa 100% da área; a interface some.
- **Composição:** dock flutuante inferior centralizado (estilos | paleta | congelar, explosão | tela cheia | demo); metadados mono no canto inferior esquerdo; marca DEMO no canto inferior direito.
- **Clima:** galeria escura. Paletas reequilibradas para menos neon.

### Air Music
- **Objetivo:** tocar, não configurar.
- **Composição:** nota atual em numerais de 120 px leves à esquerda com frequência abaixo; a **régua de notas** ocupa a largura (marcas verticais finas, tônica destacada, coluna de luz na nota ativa, cursor da mão); controles de som numa coluna à direita sem caixa. Looper embaixo: anel fino + camadas como trilhas horizontais.
- **Gestual:** o cursor da mão é a única linha clara; o IR o tinge de âmbar.

### Air Slides
- **Objetivo:** palco de apresentação.
- **Composição:** o slide como objeto (única superfície elevada da tela), número grande "01 —" e título leve; abaixo, navegação circular ‹ 1/7 › e pontos; acima, escolha do destino (deck integrado × apresentação externa) e o mapa de gestos em pílulas discretas.
- **Gestual:** a seta do gesto aparece sutil na borda e o slide desliza na direção certa.

### Motion Intelligence
- **Objetivo:** transparência técnica com elegância de instrumento.
- **Composição:** linha do tempo de sinal em largura total (sem caixa) com trilhas de eventos por fonte; três reconhecedores em colunas separadas por fios (o que comanda tem filete superior na cor do canal); fluxo e rejeições lado a lado; histórico em tabela leve; coleta e avaliação em seção final com marcas de proveniência.
- **Inteligente/honesto:** F1 só aparece com marca REAL; o relatório sintético fica recolhido e marcado como SINTÉTICO.

### Conexão / demo / sem dispositivo
- **Topo:** pílula de status (ponto + rótulo) clicável que abre o diálogo de conexão.
- **Sem dispositivo:** áreas de sinal mostram um traço tracejado plano e uma frase curta; nada de número inventado.
- **Demo:** marca `DEMO` tracejada violeta no topo e em cada módulo que desenha sinal.
- **Erro:** ponto vermelho + mensagem do servidor, sem fundo vermelho.

### /legacy
Mantido como está (experiência anterior, tema próprio). O acesso é um ícone discreto no rodapé do trilho.

## 5. Implementação
- `terminal/web/static/index.html`: trilho de ícones (SVG inline), topo reorganizado, home com campo do sensor, marcação por tela. Todos os IDs usados pelo JS foram preservados.
- `terminal/web/static/lab.css`: reescrito sobre os tokens acima.
- `lab.js`: desenho da faixa do topo, campo do sensor na home (novo), régua de notas e anel do looper; linha de binding com fio; slide com índice e pontos; dock do canvas com amostras de paleta. Polling, eventos, API e funções testadas (`LabCore`) intactos.
- `intel.js`: gráfico redesenhado (trilhas sempre visíveis, IR como barra de luz, eventos com linha até a curva), cores dos canais, marca `demo` para o simulador, marca `real` no F1, origem na caixa de coleta.
- `canvas.js`: paletas menos saturadas (Aurora, Brasa, Grafite, Líquen) e fundo `#08080a`.
- Nenhum arquivo novo servido (o servidor tem lista fechada de estáticos); ícones são SVG inline em `index.html`, sem `style=""` (CSP `style-src 'self'`).

## 5b. Fase D — ML/MLOps no Motion Intelligence (2026-11-11)
Sem redesign: a tela ganhou três níveis numa fileira tipográfica (05.1 · 05.2 · 05.3), como o índice da home, e o estado do serviço ML à direita.
- **05.1 Sinais ao vivo:** conteúdo anterior intacto; o replay passou a se chamar "Replay exploratório · não é o holdout". O gráfico só é desenhado com este nível aberto.
- **05.2 Modelos e experimentos** (`/api/ml/status` + `/api/ml/evaluations`): modelo publicado em tipografia grande (nome, sha, experimento, marcas "Treino · origem" e "Validação física · pendente"); F1-macro do teste reservado em 96 px com fio na marca da coorte; livro de coortes REAL · SINTÉTICO · DEMO (REAL sempre primeiro, pendente sem número); *dot plot* único com folds da CV, média ± dp, validação (círculo vazado) e teste (ponto cheio; lavanda = publicado), linha clicável que põe o modelo em foco; matriz de confusão normalizada por linha + métricas com escopo escrito (latência "no notebook", memória "estimativa ESP32", FAR "não estimável"); curva do tuning com barras de dp; rastreabilidade como caminho de sinal Aquisição → Airflow → MLflow → Publicação → API (ponto cheio = evidência, tracejado = pendente, âmbar = publica outro experimento).
- **05.3 Inferências** (`/api/ml/predictions` + `POST /api/ml/infer`): a última sessão persistida (glifo lavanda, marca "Sessão persistida", entrada × treino separados, distribuição de probabilidades) ao lado do gesto ao vivo do portão (cor do canal da fonte, ponto "ao vivo"); botão "Classificar a janela atual" envia os frames ao vivo com `input_origin` real/demo e mostra o resultado como "janela única"; histórico em tabela leve com erros do worker como linhas "falhou".
- **Honestidade:** `null`/ausente → "—" em tinta apagada ou marca PENDENTE; confiança nunca arredonda para 100% (">99%") e é dita "não calibrada"; coorte pendente não é clicável.
- **Falhas e ritmo:** status e previsões a cada 10 s, avaliações a cada 60 s, só com a tela visível; em falha só o status é consultado, a cada 30 s, e a volta recarrega tudo. Dados antigos ficam a 50% de opacidade com "Dados desatualizados · exibindo a leitura de HH:MM:SS"; 503 não configurado / indisponível, 403 e falta de comunicação têm textos próprios numa única linha de aviso.

## 6. Próximos refinamentos
- Tela cheia do Air Slides com o mesmo tratamento do canvas (controles somem, aparecem no hover).
- Variação de densidade do Motion Control para telas < 1280 px (hoje a coluna de segurança desce).
- Ilustração do gesto (aproximar/afastar/segurar) como microanimação no glifo do gatilho.
- Revisar a `/legacy/` só se ela continuar no roteiro de demonstração.
