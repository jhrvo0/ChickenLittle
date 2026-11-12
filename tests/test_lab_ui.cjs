// Funções puras do frontend do MotionLab (carregadas no Node sem DOM).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function load() {
  const context = {console, performance: {now: () => 0}, Math, Number, JSON, Object, Array, String, Float32Array};
  context.globalThis = context;
  vm.createContext(context);
  for (const f of ['canvas.js', 'music.js', 'intel.js', 'lab.js']) vm.runInContext(fs.readFileSync('terminal/web/static/' + f, 'utf8'), context, {filename: f});
  return context;
}

test('lab.js sem DOM só exporta o núcleo e não inicia nada', () => {
  const g = load();
  assert.ok(g.LabCore && g.IntelLib && g.AirMusicLib && g.MotionCanvasLib);
});

test('conexão: nunca diz "ao vivo" sem leituras e rotula a demonstração', () => {
  const {connectionView} = load().LabCore;
  assert.equal(connectionView(null).state, 'off');
  assert.equal(connectionView({status: 'connected', live: false, message: 'x'}).state, 'stale');
  assert.equal(connectionView({status: 'connected', live: true, origin: 'DEMO'}).label, 'Demonstração');
  assert.equal(connectionView({status: 'connected', live: true, origin: 'ESP32_HW', port: 'COM3', frames: 9}).state, 'live');
});

test('HUD: observado não aparece; rejeição mostra o motivo; confiança só para softmax', () => {
  const g = load(), {describeEvent} = g.LabCore, IL = g.IntelLib;
  const catalog = {'slides.next': {label: 'Deck: próximo slide'}};
  assert.equal(describeEvent({status: 'observed', gesture: 'APPROACH', source: 'ml'}, catalog, IL), null);
  const rej = describeEvent({status: 'rejected', reason: 'cooldown', gesture: 'RETREAT', source: 'rules', confidence: .85, confidence_kind: 'rule'}, catalog, IL);
  assert.match(rej.title, /cooldown/); assert.doesNotMatch(rej.detail, /%/);
  const ok = describeEvent({status: 'dispatched', action: 'slides.next', gesture: 'APPROACH', source: 'ml', confidence: .91, confidence_kind: 'softmax'}, catalog, IL);
  assert.equal(ok.title, 'Deck: próximo slide'); assert.match(ok.detail, /91%/);
  IL.setOrigin('DEMO'); assert.equal(IL.srcName('device'), 'Simulador');
  IL.setOrigin('ESP32_HW'); assert.equal(IL.srcName('device'), 'TinyML');
});

test('buffer por cursor não duplica nem cresce sem limite', () => {
  const {mergeById} = load().LabCore, buf = [];
  mergeById(buf, [{seq: 1}, {seq: 2}], 'seq', 3);
  mergeById(buf, [{seq: 2}, {seq: 3}, {seq: 4}], 'seq', 3);
  assert.deepEqual(buf.map(x => x.seq), [2, 3, 4]);
});

test('música: escala, nota por distância (perto = agudo) e camada cíclica do looper', () => {
  const {scaleNotes, pickNote, valueAt, noteName, loopSeconds} = load().AirMusicLib;
  const notes = scaleNotes(57, 'pent_major', 2);
  assert.equal(notes.length, 11); assert.equal(noteName(notes[0]), 'A3');
  assert.equal(pickNote(0, notes), notes.at(-1)); assert.equal(pickNote(1, notes), notes[0]); assert.equal(pickNote(null, notes), null);
  const ev = [{t: 0.5, midi: 60}, {t: 1.0, midi: null}, {t: 2.0, midi: 64}];
  assert.equal(valueAt(ev, 0.2), 64); assert.equal(valueAt(ev, 0.7), 60); assert.equal(valueAt(ev, 1.5), null); assert.equal(valueAt(ev, 2.2), 64);
  assert.ok(Math.abs(loopSeconds(90, 2) - 5.333) < 1e-3);
});

test('canvas: a mola segue o alvo sem ultrapassar', () => {
  const {spring} = load().MotionCanvasLib;
  let v = 0, vel = 0, max = 0;
  for (let i = 0; i < 120; i++) { [v, vel] = spring(v, vel, 1, 9, 1 / 60); max = Math.max(max, v); }
  assert.ok(v > 0.99 && max <= 1.0001);
});

test('rejeições agregadas por motivo, maiores primeiro', () => {
  const {rejectionTotals} = load().IntelLib;
  const rows = rejectionTotals({rules: {'rejected:cooldown': 3, dispatched: 2}, ir: {'rejected:disarmed': 5, 'rejected:cooldown': 1}});
  assert.deepEqual(JSON.parse(JSON.stringify(rows)), [['disarmed', 5], ['cooldown', 4]]);
});

// ---- Motion Intelligence · ML acadêmico. FIXTURES de teste (formato de /api/ml/*, valores fictícios só para lógica).
test('ML: estado do serviço distingue não configurado, indisponível, 403, pendente, inválido e publicado', () => {
  const {serviceView} = load().IntelLib.ML;
  assert.equal(serviceView(null).state, 'idle');
  assert.equal(serviceView({code: 0, net: true}).label, 'Sem comunicação');
  assert.equal(serviceView({code: 403, data: {}}).label, 'Chave local expirada');
  assert.equal(serviceView({code: 503, data: {error: 'ml_service_not_configured', status: 'unavailable'}}).state, 'off');
  assert.equal(serviceView({code: 503, data: {error: 'ml_service_unavailable', metrics: null}}).label, 'Serviço ML indisponível');
  assert.equal(serviceView({code: 200, data: {status: 'pending', deployment_status: 'pending'}}).label, 'Nenhum modelo publicado');
  assert.equal(serviceView({code: 200, data: {status: 'pending', deployment_status: 'invalid'}}).label, 'Publicação inválida');
  assert.equal(serviceView({code: 200, data: {status: 'ready', deployment_status: 'published', model_name: 'mlp_compact', model_sha256: 'a'.repeat(64)}}).state, 'ok');
});

test('ML: coorte exibida nunca é pendente; REAL vence quando avaliado; null não vira zero', () => {
  const {pickCohort, provOf} = load().IntelLib.ML;
  const evals = {physical_validation: 'pending', real: {status: 'pending', metrics: null}, synthetic: {status: 'invalid'}, demo: {status: 'evaluated'}};
  assert.equal(pickCohort(evals, 'real', 'demo'), 'demo');
  assert.equal(pickCohort(evals, null, null), 'demo');
  assert.equal(pickCohort({real: {status: 'pending'}, synthetic: {status: 'pending'}, demo: {status: 'pending'}}, null, 'demo'), null);
  assert.equal(pickCohort({real: {status: 'evaluated'}, demo: {status: 'evaluated'}}, null, null), 'real');
  assert.equal(provOf('demo').kind, 'demo'); assert.equal(provOf('synthetic').kind, 'synthetic');
  assert.equal(provOf(null).kind, 'pending'); assert.equal(provOf('synthetic_simulator').kind, 'pending');
});

test('ML: previsões ordenadas por data e amostras de inferência só do trecho contínuo', () => {
  const {sortedPredictions, samplesFromFrames, inferOrigin} = load().IntelLib.ML;
  const s = sortedPredictions({items: [{session_id: 'a', generated_at_iso: '2026-11-11T20:03:28Z'}, null, {session_id: 'b', generated_at_iso: '2026-11-11T20:05:12Z'}]});
  assert.deepEqual(s.map(p => p.session_id), ['b', 'a']);
  assert.equal(sortedPredictions({status: 'pending', items: []}).length, 0);
  // Reconexão no meio: ts reinicia e só o trecho final (crescente) é enviado.
  const frames = [...Array(5)].map((_, i) => ({ts: 9000 + i, d: 20, v: true, ir: false})).concat([...Array(12)].map((_, i) => ({ts: i * 75, d: i === 3 ? null : 15, v: i !== 3, ir: i === 4})));
  const out = samplesFromFrames(frames);
  assert.equal(out.length, 12); assert.equal(out[0].ts_ms, 0);
  assert.deepEqual(JSON.parse(JSON.stringify(out[3])), {ts_ms: 225, distance_cm: null, valid_ultrasonic: false, ir_detected: false});
  assert.equal(samplesFromFrames(frames.slice(0, 5)), null);
  assert.equal(inferOrigin('ESP32_HW'), 'real'); assert.equal(inferOrigin('DEMO'), 'demo'); assert.equal(inferOrigin('NONE'), null);
});
