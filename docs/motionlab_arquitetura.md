# MotionLab — auditoria, arquitetura e plano de migração

Data: 2026-11-11. Este documento registra a auditoria e o plano da migração para MotionLab. A seção 1 é um retrato anterior à reformulação, não o estado atual: os reconhecedores selecionados hoje acionam os módulos, e as fases posteriores acrescentaram integração ML/MLOps e IoT em software. Para navegação e estado atual, veja o [README](../README.md) e o [índice](README.md).

Correção posterior: a suspeita de defeito no treino registrada na seção 1 não se confirmou; `TrainingConfig.seed` existe e o pipeline sintético foi executado com saídas isoladas. Isso não constitui avaliação com dados físicos.

## 1. Diagnóstico do estado real (antes da reformulação)

| Área | Estado verificado no código | Evidência |
|---|---|---|
| Protocolo JSON Lines v1 | Implementado nos dois lados, com parser estrito no firmware e testes | `terminal/communication/protocol.py`, `firmware/communication/` |
| Firmware | Compila; 5 tasks; emite `sensor_frame` (~14 Hz, 70 ms) e `gesture_event` do TinyML (`mlp_compact`) com estabilizador (conf ≥ 0,60, 2 janelas, cooldown 700 ms); continua rodando o motor do pet com autosave NVS | `firmware/main/main.cpp`, `firmware/gestures/` |
| Modelo TinyML | **Treinado só com dados sintéticos** (`data_origins: synthetic_simulator`, `AWAITING_REAL_DATA`). As métricas do relatório (F1 0,886) validam o pipeline, não o desempenho real | `data/models/best_model.meta.json`, `data/reports/evaluation_report.md` |
| Dados reais | Nenhuma sessão real em `data/raw/` (só `synthetic/`) | `data/raw/` |
| Uso do classificador na interface web | **Decorativo.** `MotionPetSession` cria o cliente com `dispatch_gesture_events=False` e controla tudo por zonas de distância fixas e borda do IR em `_sensor_controls`; o `gesture_event` só é exibido | `terminal/web/session.py` |
| Confiança das regras | O `RuleBaselineModel` devolve 0,85 fixo para a classe escolhida: não é probabilidade | `ml/training/models.py` |
| Confiança do MLP | Máximo do softmax, não calibrado | `ml/classifiers.py`, `tinyml_model.h` |
| Pet / Pet Launch | Funcionais e testados; o firmware mantém o pet como domínio autoritativo | `terminal/pet`, `terminal/games`, `firmware/pet` |
| Air Music / Air Slides | Mínimos: nota por distância e slide por zona; sem looper, timbres ou controle externo | `terminal/modes/` |
| Simulador | Determinístico 1D, usado pela porta DEMO | `simulator/` |
| Validação física | Sensores leem juntos (relato do usuário); nada de precisão, latência ou ML em hardware | `AGENTS.md`, `docs/cycle5_bench_checklist.md` |
| Treino | `ml/training` tem um bug conhecido (`AGENTS.md`): o caminho de re-treino real está pendente | `ml/training/trainer.py` |

### Dependências relevantes
- O firmware decide sozinho o que fazer com o pet a partir dos gestos (exceto em `PET_LAUNCH`). Isso independe do host e não atrapalha os módulos novos; o autosave NVS tem intervalo mínimo antidesgaste.
- A interface web depende de `TerminalHostClient` (protocolo, ACK, erros) e da fila de ações de `MotionPetSession` (prazo, tamanho limitado). Essas garantias são preservadas.
- Os testes `test_web_app.py`, `test_backend_review_fixes.py` e `test_web_ui.cjs` descrevem o comportamento do pet; o pet continua acessível como **experiência legada** (`/legacy/`).

## 2. O que foi reaproveitado, substituído e mantido como legado

- **Reaproveitado sem mudança**: protocolo, transporte, `TerminalHostClient` (só ganhou dois listeners opcionais), filtro causal, extração de 11 features, `EventStabilizer`, `MLGestureClassifier`, `RuleBaselineModel`, `RawSampleRecord`, `validate_session_records`, `evaluate_classification_metrics`, simulador e firmware.
- **Substituído na experiência principal**: pet, Pet Launch e a interface infantil deram lugar à interface MotionLab (`terminal/web/static/index.html`, `lab.*`).
- **Legado documentado**: a interface antiga foi movida para `terminal/web/static/legacy/` e é servida em `/legacy/`. As regras automáticas sensor→pet (`_sensor_controls`) só valem quando a experiência legada está ativa. O firmware continua com o pet (ver §6).

## 3. Arquitetura-alvo

```
HC-SR04 + TCRT5000
   │  (ESP32: aquisição 70 ms, TinyML + estabilizador embarcados)
   ▼
sensor_frame ──────────────┬──────────────────────────── gesture_event (source=tinyml)
   │                       │                                   │
   ▼                       ▼                                   ▼
SignalTracker         IrTracker                         reconhecedor "device"
(contínuo: distância  (discreto: IR_TAP, IR_HOLD,
 filtrada, posição     bordas)
 0..1, velocidade)         │
   │              reconhecedores no host (mesma janela,
   │              filtro, features e estabilizador):
   │               • "rules"  → RuleBaselineModel
   │               • "ml"     → bundle .joblib (mlp_compact)
   │                       │
   │                       ▼
   │               GestureGate (fonte escolhida = driver):
   │               armado? confiança mínima? cooldown? repetição?
   │               zona ativa? sinal recente?
   │                       │
   │                       ▼
   │               Perfil do módulo ativo: gatilho → ação (catálogo fechado)
   │                       │
   │            ┌──────────┴───────────┐
   │            ▼                      ▼
   │     ação interna (UI)      ação externa (tecla de sistema,
   │     canvas/music/slides    allowlist + chave "externo" + limite de taxa)
   ▼
módulos no navegador (Canvas, Music: controle contínuo direto pela distância)
```

Separação pedida:
1. **Leitura contínua** (`signal`): distância bruta, filtrada, posição normalizada, velocidade, validade e idade.
2. **IR discreto** (`ir`): estado, `IR_TAP` (< 600 ms) e `IR_HOLD` (≥ 900 ms, uma vez por toque). Não é classificado por ML.
3. **Gestos por regra** (`source: rules`) e 4. **gestos por ML** (`source: ml` no host, `source: device` para o TinyML da ESP32), sempre registrados lado a lado; só a fonte escolhida como *driver* dispara ações.
5. **Comandos** (`action`): registrados com o desfecho (`executed`, `dispatched`, `rejected` + motivo).

Distância → frequência musical e intensidade de partículas continua **leitura direta**: classificar isso com ML seria pior (latência de janela, discretização).

### Decisões
- **Driver padrão = regras.** O modelo ML só viu dados sintéticos; colocá-lo como padrão seria afirmar desempenho sem evidência. O usuário escolhe `ml` ou `device` na interface, e a escolha **de fato** passa a controlar os módulos.
- **Mesma janela, filtro e estabilizador para regras e ML** (reuso do `MLGestureClassifier` com um bundle em memória do `RuleBaselineModel`): a comparação fica justa.
- **Confiança**: só é aplicada e exibida como número para fontes probabilísticas (`ml`, `device`, rotuladas "softmax não calibrado"). Para regras aparece "n/a".
- **Ações externas**: catálogo fechado de teclas (mídia e apresentação) enviado por `user32.keybd_event` (só Windows, sem dependência nova). Nada de execução de comando arbitrário. Exige a chave "Ações no sistema" ligada (sempre desligada ao iniciar), gestos armados (desarmam ao desconectar) e respeita o intervalo mínimo de 350 ms e o máximo de 8 por 10 s.
- **Tempo real na UI**: `GET /api/live` com cursor (frames e eventos desde o último id), lido a cada ~70 ms, sem perder frames. Alternativa SSE descartada porque `EventSource` não envia o cabeçalho da chave local.
- **Renderização do Canvas**: Canvas 2D com composição aditiva e contagem de partículas adaptativa ao FPS. WebGL daria mais partículas, mas exigiria shaders e um caminho de fallback; para 1 sinal 1D + IR, o Canvas 2D atinge 60 fps com ~1500 a 2500 partículas e respeita a CSP `script-src 'self'` sem bibliotecas.
- **Áudio**: Web Audio API nativa (osciladores, filtro, delay, compressor). O looper grava eventos de parâmetros, não áudio.
- **Coleta**: a gravação guiada usa o mesmo cronograma e o mesmo formato `RawSampleRecord` de `ml.collection` e salva em `data/raw/real/` só quando a origem é `ESP32_HW`. A demonstração vai para `data/raw/demo/` com `data_origin=synthetic_simulator`, sem contaminar os dados reais.
- **Avaliação**: F1-macro e matriz de confusão por janela (rótulo de pureza ≥ 0,6, como no pipeline), calculados reproduzindo as sessões gravadas pelos reconhecedores do host. Sem sessões reais, o painel mostra "pendente". O relatório sintético aparece separado e marcado.

## 4. Critérios de aceite (verificáveis)
1. Sem placa, a interface não inventa leituras; a DEMO é rotulada em todos os módulos.
2. Gestos só executam ações com o controle armado; desconectar desarma.
3. Ação externa só sai com a chave ligada, a ação no catálogo e dentro do limite de taxa (teste com emissor falso).
4. Trocar o driver para `ml` faz o evento ML (e não o de regra) executar a ação (teste).
5. Rejeições registradas com motivo (`low_confidence`, `cooldown`, `repeat_lock`, `disarmed`, `out_of_zone`, `stale_signal`, `unmapped`, `external_disabled`, `rate_limited`).
6. Gravação guiada gera arquivo aceito por `ml.preprocessing` e `validate_session_records`; DEMO nunca grava em `data/raw/real`.
7. Métricas no painel saem só de sessões reais gravadas; o relatório sintético aparece marcado como tal.
8. Pet e Pet Launch continuam funcionando em `/legacy/`; testes antigos passam.

## 5. Sequência de implementação
0. Auditoria (este documento).
1. Fundação: `terminal/motionlab/` (sinais, IR, reconhecedores, gate, perfis, ações), APIs `/api/live` e `/api/lab`, nova casca da UI e o legado em `/legacy/`.
2. Motion Control (perfis, mapeamentos, thresholds, armar, ações externas) e Motion Canvas (4 estilos, gestos, tela cheia, demo).
3. Motion Intelligence (séries temporais, faixas por fonte, rejeições, concordância, latência, coleta guiada, avaliação real).
4. Air Slides Pro (deck integrado + controle de apresentação externa por teclas) e Air Music Pro (timbres, escala, efeitos, looper com camadas).
5. Testes, documentação e plano de validação física (§8).

## 6. Limitações conhecidas
- **Firmware inalterado**: o pet segue rodando na ESP32 (ticks, gestos aplicados ao pet, autosave NVS com intervalo mínimo). Um "modo lab" no firmware, que pausaria o pet, exige gravar e validar na placa; ficou como próximo passo.
- **Teclas vão para a janela em foco**: é assim que funcionam os passadores de slide USB. Se a janela em foco for o navegador do MotionLab, a tecla vai para ele. Por causa do UIPI do Windows, não chegam a janelas executadas como administrador.
- **Latência ponta a ponta** (mão → ação) não é medida sem referência externa. O painel mostra a latência de inferência no host, o intervalo entre frames e a idade do último frame.
- **"Concordância" regras × ML** não é acurácia: sem rótulo, mede só se as duas fontes concordam.
- **Modelos em `data/models/` são ignorados pelo git**: num clone limpo, a fonte `ml` aparece como "modelo ausente".

## 7. Nome
MotionLab foi adotado como identidade principal do projeto. Identificadores internos e o cabeçalho `X-MotionPet-Key` permanecem por compatibilidade; sua alteração exigiria revisão coordenada de consumidores e testes.

## 8. Plano de validação com hardware (pendente, com o usuário)
1. Gravar o firmware atual (não muda) e conectar pela interface em COM3.
2. Motion Intelligence: conferir a série temporal com a mão a 10, 20 e 40 cm (régua) e anotar o desvio.
3. Gravar pelo menos 3 participantes × 2 sessões guiadas (`data/raw/real/`).
4. Avaliar no painel: F1-macro e matriz de confusão de regras × ML com dados reais; registrar em `data/reports/`.
5. Treinar e avaliar com dados físicos autorizados e comparar com o modelo sintético. Preferir `python -m ml.experiment`, que isola os artefatos; o caminho histórico `ml.real_pipeline` pode sobrescrever o header do firmware com os destinos padrão.
6. Motion Control: com a chave externa ligada, testar `present.next` no PowerPoint/PDF e as teclas de mídia num player; anotar falsos positivos em 5 min de uso normal.
