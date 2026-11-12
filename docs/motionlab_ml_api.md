# Contrato ML v1 para a frente visual

API independente em `http://127.0.0.1:8768`; rotas antigas da interface não mudam. Sua ausência deve aparecer como indisponibilidade, sem impedir os módulos atuais. Na Fase C, o backend passou a oferecer o proxy autenticado `/api/ml/*` na mesma origem do MotionLab. A interface foi conectada posteriormente na Fase D. Operação e evidências: [Fase C](motionlab_fase_c.md); transporte físico preparado em software: [Fase E](motionlab_fase_e.md).

## Inicialização

```powershell
# Só status/relatórios: inferência permanece pendente sem modelo.
.\.venv\Scripts\python.exe -m ml.inference_api

# Usa explicitamente o modelo da última execução sintética completa.
$latestRun = Get-Content data/experiments/synthetic/latest.json -Raw | ConvertFrom-Json
$bundlePath = "data/experiments/synthetic/$($latestRun.experiment_id)/models/best_model.joblib"
.\.venv\Scripts\python.exe -m ml.inference_api --model $bundlePath

# UI de desenvolvimento em outra porta: adicionar origem exata.
.\.venv\Scripts\python.exe -m ml.inference_api --model $bundlePath --ui-origin http://127.0.0.1:8790
```

Com `--model`, o modelo fica fixo até reiniciar. Com `--deployment`, somente uma publicação explícita e atômica pode substituí-lo; `latest` nunca promove modelos sozinho. CORS permite por padrão `http://127.0.0.1:8767` e `http://localhost:8767`, sem credenciais. A CSP do dashboard permite conexões somente à própria origem: o frontend deve usar o proxy abaixo. O servidor não recebe arquivos joblib pela rede.

## Rotas

| Método e rota | Resposta |
|---|---|
| `GET /health` ou `/v1/status` | HTTP 200 se o processo responde; `status=ready` ou `pending` conforme disponibilidade do modelo |
| `GET /v1/evaluations` | HTTP 200; entradas independentes `real`, `synthetic`, `demo` e `schema_version=1` |
| `GET /v1/predictions` | HTTP 200; `status=pending`, `ready` ou `invalid`, `items` e `errors`; previsões automáticas das sessões persistidas |
| `POST /v1/infer` | HTTP 200 com inferência de uma janela; 400 para entrada inválida, 413 acima de 64 KiB e 503 se o modelo estiver pendente |
| `OPTIONS` | Preflight CORS para origens configuradas; 403 para origem não permitida |

`GET /v1/evaluations` sem resultados:

```json
{
  "schema_version": 1,
  "physical_validation": "pending",
  "real": {"status": "pending", "cohort": "real", "metrics": null, "message": "Nenhum experimento completo para esta origem."},
  "synthetic": {"status": "pending", "cohort": "synthetic", "metrics": null, "message": "Nenhum experimento completo para esta origem."},
  "demo": {"status": "pending", "cohort": "demo", "metrics": null, "message": "Nenhum experimento completo para esta origem."}
}
```

Quando `status=evaluated`, a entrada contém `experiment_id`, `dataset_sha256`, `generated_at_iso`, `selected_model`, `software_only`, grupos em `split`, CV em `validation` e métricas por candidato em `metrics`. Cada candidato inclui F1, acurácia, matriz de confusão, métricas por classe, FAR, eventos, latência no notebook e memória estimada. `status=invalid` significa artefatos inconsistentes, não resultado ruim do classificador.

Regras de exibição:

- `pending` → “Pendente”, nunca zero ou um gráfico vazio que pareça resultado medido.
- `synthetic` → “Sintético — verificação do pipeline”. `demo` → “Demonstração — dados sintéticos”.
- `real` → “Avaliação offline sobre dados reais”; ainda observar `physical_validation=pending`.
- `false_activation_rate_neutral_status=pending_no_neutral_samples` → FAR não estimável nessa amostra. O campo numérico antigo é mantido por compatibilidade.
- `latency_scope=notebook_python` e `memory_scope=estimated_esp32` impedem confusão com medições na placa.

## Inferência por amostras

O corpo declara a origem da entrada separadamente da origem do treino. Uma sequência `real` processada por modelo sintético continua com `trained_on=["synthetic_simulator"]`.

```powershell
$samples = 0..9 | ForEach-Object {
    @{ ts_ms = $_ * 75; distance_cm = 15.0; valid_ultrasonic = $true; ir_detected = $false }
}
$body = @{ schema_version = 1; input_origin = 'demo'; samples = @($samples) } | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8768/v1/infer -Method Post -ContentType application/json -Body $body
```

São aceitas de `window_size` (padrão 10) a 512 amostras de uma mesma sessão, em ordem temporal. O serviço reinicia o filtro para cada requisição e classifica a última janela válida desse prefixo. Para paridade com um fluxo contínuo, envie o mesmo prefixo causal; enviar apenas uma janela com filtro reiniciado pode produzir diferenças. Esta rota é estateless, não um substituto do `MLGestureClassifier` com estado usado no MotionLab.

Alternativamente, envie `features` com exatamente 11 números finitos e `feature_names` na ordem canônica: `d_min`, `d_max`, `d_mean`, `d_std`, `d_delta`, `v_mean`, `v_peak`, `trend_slope`, `sign_inversions`, `ir_active_ratio`, `invalid_ratio`. Os dois formatos são mutuamente exclusivos.

A resposta inclui `source=ml_host`, `label`, `confidence`, `probabilities`, `input_origin`, `trained_on`, nome/hash do modelo, experimento, `scope=single_window` e `event_gate_applied=false`. Confiança não é probabilidade calibrada. A API não emite ações; os módulos continuam usando o gate do MotionLab. `source=device`/TinyML é evidência separada do firmware, nunca inferida deste serviço.

## Campos aditivos na avaliação existente da UI

O replay de `terminal/motionlab/dataset.py` conserva seus campos anteriores e acrescenta:

- No topo: `evaluation_scope=exploratory_replay`, `physical_validation=pending`.
- Em cada resultado: `provenance`, com independência, sobreposição de participantes/sessões, origem do treino e ressalva.
- `independence` pode ser `rules_without_training`, `independence_unknown` (bundles antigos), `overlaps_development` ou `independent_of_recorded_development`.
- Se a pasta `real` tiver alguma amostra de outra origem: `status=invalid_data`, sem calcular métricas.

Replay exploratório de todas as sessões não é o holdout acadêmico. Para a comparação formal, consumir os experimentos de `/v1/evaluations`. Todos os campos novos são aditivos; o frontend deve tolerar sua ausência em versões anteriores.

## Extensão Fase C para o Claude Code

Configurar o backend com `python -m terminal.web --demo --ml-api-url http://127.0.0.1:8768`. Dentro do Compose a URL interna é `http://api:8768`. A URL é definida pelo operador, nunca pelo corpo da requisição. Não há mudanças em `/api/live`, `/api/lab`, `/api/experience` ou no gate.

| Frontend na origem do dashboard | API interna | Contrato |
|---|---|---|
| `GET /api/ml/status` | `/v1/status` | Estado do modelo, hash, `training_cohort`, `trained_on`, `deployment_status` |
| `GET /api/ml/evaluations` | `/v1/evaluations` | Holdout acadêmico; `real`, `synthetic`, `demo` separados; inclui `eda`, `tuning`, `tracking`, `orchestration` |
| `GET /api/ml/predictions` | `/v1/predictions` | Última janela causal de cada sessão persistida, sem filtragem pelos rótulos verdadeiros |
| `POST /api/ml/infer` | `/v1/infer` | Mesmo corpo e resposta do serviço independente; limite 64 KiB |

Todos exigem `X-MotionPet-Key`, obtido do meta `motionpet-key` já presente na página, e preservam as validações de Host e Origin. Exemplo de consumo sem modificar o layout:

```javascript
const key = document.querySelector('meta[name="motionpet-key"]').content;
const response = await fetch('/api/ml/predictions', {
  headers: { 'X-MotionPet-Key': key }
});
if (!response.ok) {
  // Mostrar indisponível; manter os módulos existentes utilizáveis.
} else {
  const result = await response.json();
  // pending: ainda não há previsão; nunca substituir por zero.
  // input_origin, training_cohort e trained_on têm papéis independentes.
}
```

Antes da primeira sessão processada:

```json
{"schema_version":1,"status":"pending","items":[],"physical_validation":"pending"}
```

Após processamento, `items[]` contém os campos reais da resposta `/v1/infer`, mais `session_id`, `dataset_sha256` da entrada, `samples`, `windows`, `window_end_ts_ms`, `generated_at_iso`, `processing_version=1` e `scope=last_window_of_session`. Não há números de exemplo inventados neste contrato; respostas capturadas estão nos artefatos de integração citados na Fase C. O worker usa o modelo publicado, não retreina; reiniciar mantém o cache identificado por hash do modelo, corpus e versão de processamento. Arquivos inválidos aparecem em `errors`, sem previsão fictícia.

Mapeamento obrigatório de proveniência:

- `input_origin=real` → REAL, sensor físico declarado no corpus.
- `input_origin=synthetic` → SYNTHETIC, experimento sintético.
- `input_origin=demo` → DEMO, demonstração da aplicação, mesmo com `trained_on=["synthetic_simulator"]`.
- `training_cohort` descreve o experimento que treinou o modelo publicado; é `null` para bundle fixo legado sem essa informação. Não inferir REAL a partir de uma entrada real.
- `status=pending`, `metrics=null`, modelo ausente ou FAR não estimável → PENDING. Falha de conexão → indisponível; ausência de evidência não vira desempenho zero.
- `physical_validation=pending` é separado da validade da demonstração simulada, expressamente aceita pelo enunciado.

Cada modelo em `/v1/evaluations` acrescenta `far_neutral={status,value,support}`; `value=null` quando não estimável. O campo numérico antigo `false_activation_rate_neutral` permanece por retrocompatibilidade e só pode ser exibido com status `evaluated`. `eda.figures[].path` é caminho de artefato, não URL HTTP; figuras exportáveis estão no notebook/run. `tracking` identifica o run MLflow e sua URI pode ser interna ao Compose. `orchestration.run_id` permite conferir as quatro tasks no Airflow. O replay existente continua exploratório e não substitui o holdout.

| Estado | HTTP / comportamento |
|---|---|
| Modelo ainda não publicado | `/status` 200 com `status=pending`; `/infer` 503 `model_pending` |
| Publicação inválida, hash divergente ou bundle corrompido | `deployment_status=invalid`, sem classificação; `/infer` 503 |
| Serviço ML não configurado no dashboard | 503 `ml_service_not_configured`, `status=unavailable`, `metrics=null` |
| API parada, timeout ou resposta incompatível | 503 `ml_service_unavailable`, `metrics=null`; `/api/live` segue funcionando |
| Entrada inválida / grande demais | API independente: 400 `invalid_request` / 413 `payload_size`; proxy também valida corpo e pode responder 400 antes do encaminhamento |
| Chave local ausente / Host ou Origin externos | 403 no backend do dashboard |
| Sem experimentos de uma origem | 200 com essa origem `pending`, `metrics=null` |

Na interface atual, o polling de status e previsões ocorre a cada 10 s e o de avaliações a cada 60 s; em falha, a tentativa é a cada 30 s, somente com a tela visível. Essas chamadas são separadas do polling dos sensores. Serviço e proxy foram exercitados por HTTP na Fase C; a ligação visual ocorreu na Fase D.
