'use strict';
/* Motion Intelligence — telemetria, comparação de reconhecedores, coleta e avaliação.
   Regra de honestidade da interface: número real só aparece com origem dita (real, sintético,
   pendente). Confiança só é desenhada como barra quando é probabilística (ML/TinyML). */
(() => {
  const GLYPH = {APPROACH: '↓', RETREAT: '↑', HOLD: '■', IR_TAP: '•', IR_HOLD: '◉', IR_ON: '+', IR_OFF: '−'};
  const GESTURE_PT = {APPROACH: 'Aproximar', RETREAT: 'Afastar', HOLD: 'Segurar', NEUTRAL: 'Repouso', IR_TAP: 'Toque IR', IR_HOLD: 'Toque longo IR', IR_ON: 'IR ativo', IR_OFF: 'IR livre', IMPULSE: 'Impulso', DOUBLE: 'Duplo'};
  const SOURCE_PT = {rules: 'Regras', ml: 'ML host', device: 'TinyML', ir: 'IR', ui: 'Interface'};
  const REASON_PT = {
    disarmed: 'gestos pausados', low_confidence: 'confiança baixa', cooldown: 'cooldown', repeat_lock: 'repetição bloqueada',
    out_of_zone: 'fora da zona ativa', stale_signal: 'sinal atrasado', unmapped: 'sem ação no perfil', external_disabled: 'ações no sistema desligadas',
    external_unavailable: 'teclas indisponíveis', rate_limited: 'limite de taxa', no_module: 'nenhum módulo aberto', not_core_gesture: 'gesto experimental',
  };
  let ORIGIN = 'NONE';
  const setOrigin = o => { ORIGIN = o || 'NONE'; };
  /** Na demonstração a faixa "device" é o detector heurístico do simulador, não o TinyML. */
  const srcName = s => s === 'device' && ORIGIN === 'DEMO' ? 'Simulador' : (SOURCE_PT[s] || s);
  const LANES = ['rules', 'ml', 'device'];
  const LANE_COLOR = {rules: '#ecebe6', ml: '#a99cf0', device: '#dc8fb0'};
  const fmt = (v, d = 1) => v === null || v === undefined ? '—' : Number(v).toLocaleString('pt-BR', {minimumFractionDigits: d, maximumFractionDigits: d});
  const pct = v => v === null || v === undefined ? '—' : Math.round(v * 100) + '%';
  const reasonText = r => r ? (REASON_PT[r] || String(r)) : '';

  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  /** Agrupa contagens do motor ({fonte: {"rejected:motivo": n}}) por motivo. Pura. */
  function rejectionTotals(counts) {
    const out = {};
    for (const bucket of Object.values(counts || {})) for (const [k, n] of Object.entries(bucket)) {
      if (k.startsWith('rejected:')) { const r = k.slice(9); out[r] = (out[r] || 0) + n; }
    }
    return Object.entries(out).sort((a, b) => b[1] - a[1]);
  }

  // ------------------------------------------------------------ gráfico
  function drawChart(canvas, frames, events, settings) {
    const dpr = Math.min(2, window.devicePixelRatio || 1), rect = canvas.getBoundingClientRect();
    const w = Math.round(rect.width * dpr), h = Math.round(rect.height * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    const N = 220, maxCm = 90, laneH = 22 * dpr, top = laneH * 3 + 18 * dpr, irH = 3 * dpr, bottom = h - irH - 14 * dpr, left = 64 * dpr, right = w - 4 * dpr;
    const mono = `500 ${9.5 * dpr}px "Cascadia Mono", Consolas, monospace`;
    // trilhas de eventos (sempre desenhadas, para a tela vazia já mostrar a estrutura)
    ctx.font = mono; ctx.textAlign = 'left';
    LANES.forEach((lane, i) => {
      const y = laneH * i + laneH / 2;
      ctx.fillStyle = LANE_COLOR[lane]; ctx.globalAlpha = .75; ctx.fillText(srcName(lane).toUpperCase(), 0, y + 3 * dpr); ctx.globalAlpha = 1;
      ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    });
    if (!frames.length) {
      ctx.strokeStyle = '#3d3c39'; ctx.setLineDash([3 * dpr, 5 * dpr]); ctx.beginPath(); ctx.moveTo(left, (top + bottom) / 2); ctx.lineTo(right, (top + bottom) / 2); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = '#64625d'; ctx.textAlign = 'center'; ctx.fillText('SEM FRAMES · CONECTE A ESP32 OU A DEMONSTRAÇÃO', (left + right) / 2, (top + bottom) / 2 - 12 * dpr); return;
    }
    const last = frames[frames.length - 1].seq, first = last - N + 1;
    const X = seq => left + (seq - first) / (N - 1) * (right - left);
    const Y = cm => top + (1 - Math.min(maxCm, Math.max(0, cm)) / maxCm) * (bottom - top);
    if (settings) {
      ctx.fillStyle = 'rgba(124,201,192,0.04)';
      ctx.fillRect(left, Y(settings.far_cm), right - left, Y(settings.near_cm) - Y(settings.far_cm));
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.fillStyle = '#64625d'; ctx.lineWidth = dpr; ctx.textAlign = 'right';
    for (const cm of [20, 45, 70]) { const y = Y(cm); ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke(); ctx.fillText(cm + ' cm', left - 10 * dpr, y + 3 * dpr); }
    const visible = frames.filter(f => f.seq >= first);
    // IR: barra de luz na base
    ctx.fillStyle = 'rgba(255,255,255,0.05)'; ctx.fillRect(left, h - irH - 2 * dpr, right - left, irH);
    ctx.fillStyle = '#e2a15c';
    const step = (right - left) / (N - 1);
    for (const f of visible) if (f.ir) ctx.fillRect(X(f.seq) - step / 2, h - irH - 2 * dpr, step + .5, irH);
    ctx.textAlign = 'left'; ctx.fillStyle = '#64625d'; ctx.fillText('IR', 0, h - 1 * dpr);
    // bruta (pontos) e falhas de leitura (marcas na base)
    ctx.fillStyle = 'rgba(124,201,192,0.35)';
    for (const f of visible) if (f.d !== null && f.v) ctx.fillRect(X(f.seq) - .75 * dpr, Y(f.d) - .75 * dpr, 1.5 * dpr, 1.5 * dpr);
    ctx.fillStyle = 'rgba(224,115,95,0.7)';
    for (const f of visible) if (!f.v) ctx.fillRect(X(f.seq) - .5 * dpr, bottom - 5 * dpr, dpr, 5 * dpr);
    // filtrada
    ctx.strokeStyle = '#7cc9c0'; ctx.lineWidth = 1.5 * dpr; ctx.lineJoin = 'round'; ctx.beginPath(); let pen = false;
    for (const f of visible) { if (f.f === null) { pen = false; continue; } const x = X(f.seq), y = Y(f.f); pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true; }
    ctx.stroke();
    // eventos: cheio = executado/enviado · contorno = observado · tracejado = rejeitado
    ctx.textAlign = 'center'; ctx.font = `500 ${10 * dpr}px "Cascadia Mono", Consolas, monospace`;
    for (const e of events) {
      if (e.frame_seq < first) continue;
      const lane = LANES.indexOf(e.source); if (lane < 0) continue;
      const x = X(e.frame_seq), y = laneH * lane + laneH / 2, color = LANE_COLOR[e.source], r = 7.5 * dpr;
      if (e.status === 'executed' || e.status === 'dispatched') {
        ctx.strokeStyle = color; ctx.globalAlpha = .25; ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(x, y + r); ctx.lineTo(x, bottom); ctx.stroke(); ctx.globalAlpha = 1;
        ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = '#0a0a0b';
      } else {
        ctx.fillStyle = '#0a0a0b'; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = e.status === 'observed' ? 0.55 : 1;
        ctx.strokeStyle = color; ctx.lineWidth = dpr; ctx.setLineDash(e.status === 'rejected' ? [2 * dpr, 2 * dpr] : []); ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = color;
      }
      ctx.fillText(GLYPH[e.gesture] || '?', x, y + 3.5 * dpr);
      ctx.globalAlpha = 1;
    }
  }

  // ------------------------------------------------------------ painéis
  function renderRecognizers(root, lab) {
    const driver = lab.store.settings.driver;
    root.replaceChildren(...lab.recognizers.map(r => {
      const card = el('article', 'panel rec-card'); card.dataset.driver = String(r.source === driver);
      const head = el('header', 'panel-head');
      const title = el('div'); title.append(el('span', 'eyebrow', r.source === 'device' ? 'embarcado' : 'host'), el('h2', '', r.label));
      head.append(title); card.append(head);
      const badges = el('div', 'rec-badges');
      if (r.source === driver) badges.append(el('span', 'badge driver', 'controla os módulos'));
      if (!r.available) badges.append(el('span', 'badge off', r.source === 'device' ? 'sem ESP32' : 'indisponível'));
      if (r.origin === 'synthetic') badges.append(el('span', 'badge synthetic', 'treino sintético'));
      if (r.origin === 'real') badges.append(el('span', 'badge real', 'treino real'));
      if (r.origin === 'deterministic') badges.append(el('span', 'badge', 'sem treino'));
      if (r.origin === 'simulator') badges.append(el('span', 'badge demo', 'simulador'));
      if (r.model) badges.append(el('span', 'badge', r.model.model_name));
      card.append(badges);
      const lastRaw = r.last_raw;
      const lastBox = el('div', 'rec-last');
      lastBox.append(el('b', '', lastRaw ? (GESTURE_PT[lastRaw.label] || lastRaw.label) : '—'), el('span', 'hint', r.source === 'device' ? 'último evento' : 'última janela'));
      card.append(lastBox);
      if (r.kind === 'ml' && lastRaw && typeof lastRaw.confidence === 'number') {
        const bar = el('div', 'conf'), fill = el('span'); fill.style.width = pct(lastRaw.confidence); bar.append(fill); card.append(bar);
      }
      const grid = el('dl', 'kv-grid');
      const kv = (k, v) => { const d = el('div', 'kv'); d.append(el('dt', '', k), el('b', '', v)); grid.append(d); };
      if (r.source !== 'device') {
        kv('Janelas', String(r.windows)); kv('Eventos', String(r.events));
        kv('Latência média', r.latency.mean_ms === null ? '—' : fmt(r.latency.mean_ms, 3) + ' ms');
        kv('Latência p95', r.latency.p95_ms === null ? '—' : fmt(r.latency.p95_ms, 3) + ' ms');
      } else {
        kv('Eventos recebidos', String(r.events)); kv('Origem no fio', lastRaw ? lastRaw.wire_source : '—');
      }
      card.append(grid);
      const note = el('p', 'hint', `Confiança: ${r.confidence_meaning}.` + (r.error ? ' ' + r.error : '') + (r.note ? ' ' + r.note : ''));
      card.append(note);
      return card;
    }));
  }

  function renderFlow(root, lab, live) {
    const a = lab.agreement, p = lab.sample_period;
    const items = [
      ['Regras × ML', a.rules_vs_ml.rate === null ? '—' : pct(a.rules_vs_ml.rate)],
      ['Regras × TinyML', a.rules_vs_device.rate === null ? '—' : pct(a.rules_vs_device.rate)],
      ['Só regras / só ML', `${a.rules_vs_ml.only_a} / ${a.rules_vs_ml.only_b}`],
      ['Período médio', p ? fmt(p.mean_ms, 1) + ' ms' : '—'],
      ['Período p95', p ? p.p95_ms + ' ms' : '—'],
      ['Idade do último frame', live && live.age_ms !== null ? live.age_ms + ' ms' : '—'],
    ];
    root.replaceChildren(...items.map(([k, v]) => { const d = el('div', 'kv'); d.append(el('span', '', k), el('b', '', v)); return d; }));
  }

  function renderRejections(root, lab) {
    const rows = rejectionTotals(lab.counts);
    if (!rows.length) { root.replaceChildren(el('p', 'hint', 'Nenhuma rejeição registrada ainda.')); return; }
    const max = rows[0][1];
    root.replaceChildren(...rows.slice(0, 9).map(([reason, n]) => {
      const row = el('div', 'bar-row'), track = el('div', 'track'), fill = el('span');
      fill.style.width = (100 * n / max) + '%'; track.append(fill);
      row.append(el('span', '', reasonText(reason)), track, el('span', 'n', String(n))); return row;
    }));
  }

  function renderHistory(body, events) {
    const rows = events.filter(e => e.gesture && !['IR_ON', 'IR_OFF'].includes(e.gesture)).slice(-60).reverse();
    body.replaceChildren(...rows.map(e => {
      const tr = el('tr');
      tr.append(el('td', 'mono', (e.t / 1000).toFixed(1) + ' s'));
      const src = el('td'); src.append(el('span', 'src ' + e.source, srcName(e.source))); tr.append(src);
      tr.append(el('td', '', GESTURE_PT[e.gesture] || e.gesture));
      tr.append(el('td', 'mono', e.confidence_kind === 'softmax' ? pct(e.confidence) : e.confidence_kind === 'rule' ? 'n/a' : '—'));
      const out = el('td'); out.append(el('span', 'out ' + e.status, e.status === 'rejected' ? reasonText(e.reason) : e.status === 'observed' ? 'observado' : e.status === 'dispatched' ? 'enviado ao módulo' : 'executado')); tr.append(out);
      tr.append(el('td', 'mono', e.action || '—'));
      return tr;
    }));
  }

  function confusion(names, matrix) {
    const table = el('table', 'cm'), head = el('tr'); head.append(el('th', 'row', 'real \\ prev.'));
    for (const n of names) head.append(el('th', '', n.slice(0, 4)));
    table.append(head);
    const max = Math.max(1, ...matrix.flat());
    matrix.forEach((row, i) => {
      const tr = el('tr'); tr.append(el('th', 'row', names[i]));
      row.forEach((v, j) => { const td = el('td', '', String(v)); const a = v / max; td.style.background = i === j ? `rgba(124,201,192,${0.08 + 0.5 * a})` : v ? `rgba(224,115,95,${0.08 + 0.5 * a})` : 'rgba(255,255,255,0.025)'; tr.append(td); });
      table.append(tr);
    });
    return table;
  }

  function renderEvaluation(realRoot, synthRoot, data) {
    const real = data && data.evaluation ? data.evaluation.real : null;
    if (!real) realRoot.replaceChildren(el('div', 'pending', 'Clique em Avaliar para calcular com as sessões reais gravadas.'));
    else if (real.status === 'pending') realRoot.replaceChildren(el('div', 'pending', real.message));
    else {
      const wrap = el('div');
      const meta = el('p', 'hint', `${real.sessions} sessão(ões) · participantes: ${real.participants.join(', ')} · avaliação por janela, mesma pureza de rótulo do pipeline.`);
      wrap.append(meta);
      if (real.caveat) wrap.append(el('p', 'warn', real.caveat));
      const grid = el('div', 'eval-grid');
      for (const [source, r] of Object.entries(real.results)) {
        const card = el('div', 'eval-card'); card.append(el('h3', '', SOURCE_PT[source] + (r.model_name ? ` · ${r.model_name}` : '')));
        if (!r.available) card.append(el('p', 'hint', r.error || 'Indisponível.'));
        else if (!r.windows) card.append(el('p', 'hint', 'Nenhuma janela rotulada válida.'));
        else {
          const big = el('div', 'metric-big', fmt(r.f1_macro, 3)); big.append(el('small', '', 'F1-macro'), el('span', 'tag real', 'real'));
          card.append(big, el('p', 'hint', `Acurácia ${fmt(r.accuracy, 3)} · falsa ativação em repouso ${pct(r.false_activation_rate_neutral)} · ${r.windows} janelas` + (r.trained_on && r.trained_on.length ? ` · treinado com: ${r.trained_on.join(', ')}` : '')));
          card.append(confusion(r.class_names, r.confusion_matrix));
        }
        grid.append(card);
      }
      wrap.append(grid); realRoot.replaceChildren(wrap);
    }
    const syn = data && data.evaluation ? data.evaluation.synthetic : null;
    if (!syn) { synthRoot.replaceChildren(el('p', 'hint', 'Relatório sintético não encontrado em data/reports/.')); return; }
    const table = el('table'), head = el('tr');
    for (const h of ['Modelo', 'F1 teste', 'Acurácia', 'Falsa ativação']) head.append(el('th', '', h));
    table.append(head);
    for (const [name, m] of Object.entries(syn.models)) { const tr = el('tr'); tr.append(el('td', '', name), el('td', '', fmt(m.test_f1_macro, 3)), el('td', '', fmt(m.accuracy, 3)), el('td', '', pct(m.false_activation_rate_neutral))); table.append(tr); }
    synthRoot.replaceChildren(el('p', 'warn', syn.disclaimer), table);
  }

  function renderCollect(ui, rec, sessions) {
    const active = rec && rec.active;
    ui.start.hidden = !!active; ui.stop.hidden = !active; ui.prompt.hidden = !active;
    ui.participant.disabled = !!active; ui.repeats.disabled = !!active;
    if (active) {
      ui.label.textContent = GESTURE_PT[rec.label] || rec.label;
      ui.text.textContent = rec.prompt + (rec.next_label ? ` · depois: ${GESTURE_PT[rec.next_label] || rec.next_label}` : '');
      ui.bar.style.width = (100 * rec.sample / rec.total) + '%';
      ui.prompt.dataset.origin = rec.origin === 'real' ? 'real' : 'demo';
      ui.meta.textContent = `${rec.origin === 'real' ? 'DADOS REAIS' : 'DEMONSTRAÇÃO (sintético)'} · segmento ${rec.segment}/${rec.segments} · faltam ${rec.segment_left} amostras · ${rec.sample}/${rec.total}`;
    }
    const last = rec && rec.last_result;
    if (last) {
      ui.result.textContent = last.ok ? `${last.message} ${last.samples} amostras em ${last.path}.` + (last.warnings && last.warnings.length ? ' Avisos: ' + last.warnings.join('; ') : '') : `${last.message}` + (last.errors && last.errors.length ? ' ' + last.errors.join('; ') : '');
    }
    if (sessions) ui.sessions.textContent = `Sessões reais: ${sessions.real.length} · de demonstração: ${sessions.demo.length}.`;
  }

  // ================================================================ ML acadêmico (/api/ml/*)
  /* Três papéis de origem nunca se misturam: input_origin (dados da inferência), training_cohort
     (experimento que treinou o modelo publicado) e a coorte de cada avaliação. Ausente/null
     vira PENDENTE, nunca zero; nada sintético ou de demonstração é apresentado como validado na placa. */
  const SVGNS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, text) { const n = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v)); if (text !== undefined) n.textContent = text; return n; }
  const CLASSES = ['NEUTRAL', 'APPROACH', 'RETREAT', 'HOLD'];
  const CLASS_GLYPH = {NEUTRAL: '○', APPROACH: '↓', RETREAT: '↑', HOLD: '■'};
  const COHORTS = ['real', 'synthetic', 'demo'];
  const COHORT_PT = {real: 'Dados físicos', synthetic: 'Simulador · verificação', demo: 'Demonstração'};
  const MODEL_PT = {decision_stump_baseline: 'Árvore depth 1', rule_baseline: 'Regras', decision_tree: 'Decision Tree', random_forest: 'Random Forest', mlp_compact: 'MLP compacto', knn: 'KNN', adaboost: 'AdaBoost'};
  const MODEL_ROLE = {decision_stump_baseline: 'baseline aprendido', rule_baseline: 'referência · sem treino'};
  const MODEL_ORDER = ['decision_stump_baseline', 'rule_baseline', 'decision_tree', 'random_forest', 'mlp_compact', 'knn', 'adaboost'];
  const PROV = {
    real: {kind: 'real', text: 'Real', long: 'Dados físicos declarados no corpus'},
    synthetic: {kind: 'synthetic', text: 'Sintético', long: 'Experimento sintético · verificação do pipeline'},
    demo: {kind: 'demo', text: 'Demo', long: 'Demonstração · dados sintéticos'},
  };
  const PENDING = {kind: 'pending', text: 'Pendente', long: 'Sem evidência'};
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const f3 = v => isNum(v) ? fmt(v, 3) : '—';
  /** Confiança do serviço: nunca arredonda para 100% (não é certeza nem probabilidade calibrada). */
  const confPct = v => !isNum(v) ? '—' : v >= 0.995 && v < 1 ? '>99%' : v > 0 && v < 0.005 ? '<1%' : Math.round(v * 100) + '%';
  const modelName = n => MODEL_PT[n] || n || '—';
  const shortHash = h => typeof h === 'string' && h.length > 16 ? h.slice(0, 8) + '…' + h.slice(-4) : (h || '—');
  const provOf = origin => PROV[origin] || PENDING;
  function provTag(origin, prefix) { const p = provOf(origin); const t = el('span', 'tag ' + p.kind, (prefix ? prefix + ' · ' : '') + p.text); t.title = p.long; return t; }
  function cohortCaption(c) {
    return c === 'real' ? 'Avaliação offline sobre dados reais · benchmark na placa pendente'
      : c === 'synthetic' ? 'Sintético — verificação do pipeline · não é desempenho no hardware'
      : c === 'demo' ? 'Demonstração — dados sintéticos · não é desempenho no hardware' : '';
  }

  /** Estado do serviço a partir da última resposta de /api/ml/status. Pura. */
  function serviceView(res) {
    if (!res) return {state: 'idle', label: 'Serviço ML', detail: 'Aguardando a primeira leitura.'};
    if (res.net) return {state: 'bad', label: 'Sem comunicação', detail: 'O servidor local do MotionLab não respondeu.'};
    if (res.code === 403) return {state: 'bad', label: 'Chave local expirada', detail: 'O painel foi reiniciado: recarregue a página (F5).'};
    const err = res.data && res.data.error;
    if (res.code === 503 && err === 'ml_service_not_configured') return {state: 'off', label: 'Serviço ML não configurado', detail: 'Painel iniciado sem --ml-api-url. Os sinais ao vivo seguem normais.'};
    if (res.code !== 200 || !res.data) return {state: 'bad', label: 'Serviço ML indisponível', detail: 'API parada, sem resposta ou incompatível. Os sinais ao vivo seguem normais.'};
    const s = res.data;
    if (s.deployment_status === 'invalid') return {state: 'bad', label: 'Publicação inválida', detail: 'Hash ou bundle divergente: nenhuma classificação é feita.'};
    if (s.status !== 'ready') return {state: 'pending', label: 'Nenhum modelo publicado', detail: 'Inferência pendente até uma publicação explícita.'};
    return {state: 'ok', label: s.deployment_status === 'fixed' ? 'Modelo fixo' : 'Modelo publicado', detail: `${modelName(s.model_name)} · ${shortHash(s.model_sha256)}`};
  }
  function ageText(ms) {
    if (!isNum(ms)) return '';
    if (ms < 5000) return 'agora';
    if (ms < 60000) return `há ${Math.round(ms / 1000)} s`;
    if (ms < 3600000) return `há ${Math.round(ms / 60000)} min`;
    return `há ${Math.round(ms / 3600000)} h`;
  }
  function timeOf(iso) { const d = new Date(iso); return isNaN(d) ? '—' : d.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit', second: '2-digit'}); }
  function dateOf(iso) { const d = new Date(iso); return isNaN(d) ? '—' : d.toLocaleDateString('pt-BR', {day: '2-digit', month: '2-digit'}) + ' ' + d.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'}); }

  /** Coorte exibida: a escolhida, senão a do treino publicado, senão a primeira avaliada (REAL primeiro). */
  function pickCohort(evals, preferred, trainingCohort) {
    if (!evals) return null;
    const ok = c => evals[c] && evals[c].status === 'evaluated';
    if (preferred && ok(preferred)) return preferred;
    if (trainingCohort && ok(trainingCohort)) return trainingCohort;
    return COHORTS.find(ok) || null;
  }
  /** Previsões persistidas válidas, mais recentes primeiro. */
  function sortedPredictions(data) {
    const items = data && Array.isArray(data.items) ? data.items.filter(p => p && typeof p === 'object') : [];
    return items.slice().sort((a, b) => String(b.generated_at_iso || '').localeCompare(String(a.generated_at_iso || '')));
  }
  /** Frames ao vivo → amostras de /api/ml/infer: só o trecho final com ts estritamente crescente (uma sessão). */
  function samplesFromFrames(frames, max = 512, min = 10) {
    const out = [];
    for (let i = frames.length - 1; i >= 0 && out.length < max; i--) {
      const f = frames[i];
      if (!Number.isInteger(f.ts) || f.ts < 0 || (out.length && f.ts >= out[0].ts_ms)) break;
      const d = isNum(f.d) ? f.d : null;
      out.unshift({ts_ms: f.ts, distance_cm: d, valid_ultrasonic: !!f.v && d !== null, ir_detected: !!f.ir});
    }
    return out.length >= min ? out : null;
  }
  const inferOrigin = origin => ({ESP32_HW: 'real', DEMO: 'demo'})[origin] || null;

  // ---------------------------------------------------------------- serviço
  function renderService(root, view, ageMs, stale) {
    const dot = el('span', 'sdot'); dot.dataset.state = view.state;
    const top = el('span', 'svc-top'); top.append(dot, el('b', '', view.label));
    const age = ageText(ageMs);
    root.replaceChildren(top, el('small', '', view.state === 'ok' ? view.detail : view.label === 'Serviço ML' ? view.detail : ''), el('small', 'svc-age' + (stale ? ' stale' : ''), age ? (stale ? 'desatualizado · leitura ' : 'leitura ') + age : ''));
    root.title = view.detail;
  }
  /** Linha única no topo de B e C: só aparece quando há algo a dizer. */
  function renderNotice(root, view, stale, lastOkIso) {
    const show = view.state !== 'ok' || stale;
    root.hidden = !show; if (!show) return;
    const dot = el('span', 'sdot'); dot.dataset.state = stale && view.state === 'ok' ? 'warn' : view.state;
    root.replaceChildren(dot, el('b', '', stale && view.state === 'ok' ? 'Dados desatualizados' : view.label), el('span', '', view.detail + (stale && lastOkIso ? ` Exibindo a leitura de ${lastOkIso}.` : '')));
  }

  // ---------------------------------------------------------------- B · modelos e experimentos
  function renderPublished(root, status, view) {
    const eyebrow = el('span', 'eyebrow', status && status.deployment_status === 'fixed' ? 'Modelo fixo · sem publicação atômica' : 'Modelo publicado');
    if (!status || status.status !== 'ready') {
      // Sem leitura do serviço, o motivo já está na linha de aviso: aqui só a ausência, sem repetir.
      if (view.state === 'bad' || view.state === 'off' || view.state === 'idle') { root.replaceChildren(eyebrow, el('h2', 'muted', 'Sem leitura do modelo')); return; }
      root.replaceChildren(eyebrow, el('h2', 'muted', 'Nenhum modelo publicado'),
        el('div', 'pending', 'Sem publicação explícita, a inferência fica pendente: nenhum resultado é estimado no lugar dela.'));
      return;
    }
    const ids = el('p', 'ml-ids');
    ids.append(el('span', '', `sha256 ${shortHash(status.model_sha256)}`), el('span', '', `exp ${status.experiment_id || '—'}`));
    ids.title = status.model_sha256 || '';
    const marks = el('div', 'ml-marks');
    marks.append(provTag(status.training_cohort, 'Treino'));
    if (status.physical_validation !== 'validated') { const t = el('span', 'tag pending', 'Validação física · pendente'); t.title = 'Nenhum benchmark na ESP32/sensores reais'; marks.append(t); }
    const trained = Array.isArray(status.trained_on) && status.trained_on.length ? status.trained_on.join(', ') : 'origem não declarada';
    root.replaceChildren(eyebrow, el('h2', '', modelName(status.model_name)), ids, marks,
      el('p', 'hint', `Treinado com: ${trained}.` + (status.experimental_status === 'AWAITING_REAL_DATA' ? ' Aguardando dados reais.' : '')));
  }

  function renderHeadline(root, entry, cohort, hasEvals) {
    if (!entry) {
      root.replaceChildren(el('span', 'eyebrow', 'F1-macro · teste reservado'), el('div', 'ml-f1 none', '—'), el('span', 'tag pending', hasEvals ? 'Pendente · nenhuma avaliação completa' : 'Sem leitura das avaliações'));
      return;
    }
    const sel = entry.selected_model, m = (entry.metrics || {})[sel] || {};
    const cv = (((entry.validation || {}).group_kfold || {}).models || {})[sel] || {};
    const big = el('div', 'ml-f1' + (isNum(m.test_f1_macro) ? '' : ' none'), f3(m.test_f1_macro)); big.dataset.prov = cohort;
    const tag = provTag(cohort);
    const test = ((entry.split || {}).test_groups || []).join(', ');
    const sub = el('p', 'ml-sub', `${modelName(sel)} · teste ${test || '—'} · validação ${f3(m.val_f1_macro)} · CV ${f3(cv.f1_macro_mean)}${isNum(cv.f1_macro_std) ? ' ± ' + f3(cv.f1_macro_std) : ''}`);
    root.replaceChildren(el('span', 'eyebrow', 'F1-macro · teste reservado'), big, tag, el('p', 'ml-caption', cohortCaption(cohort)), sub);
  }

  function renderCohorts(root, evals, active, onPick) {
    root.replaceChildren(...COHORTS.map(c => {
      const e = evals ? evals[c] : null, evaluated = !!(e && e.status === 'evaluated');
      const b = el('button', 'cohort'); b.type = 'button'; b.disabled = !evaluated; b.setAttribute('aria-pressed', String(c === active));
      const head = el('span', 'cohort-head'); head.append(provTag(c), el('span', 'cohort-name', COHORT_PT[c])); b.append(head);
      if (evaluated) {
        const m = (e.metrics || {})[e.selected_model] || {};
        const v = el('span', 'cohort-val'); v.append(el('b', isNum(m.test_f1_macro) ? '' : 'none', f3(m.test_f1_macro)), el('small', '', `F1 teste · ${modelName(e.selected_model)}`)); b.append(v);
        b.append(el('small', 'cohort-meta', `exp ${e.experiment_id} · ${dateOf(e.generated_at_iso)}`));
      } else if (e && e.status === 'invalid') {
        b.append(el('span', 'cohort-bad', 'Artefatos inconsistentes'), el('small', 'cohort-meta', e.message || ''));
      } else {
        b.append(el('span', 'tag pending', 'Pendente'), el('small', 'cohort-meta', !evals ? 'Sem leitura do serviço.' : (e && e.message) || 'Nenhum experimento completo para esta origem.'));
      }
      if (c === 'real' && (!evals || evals.physical_validation !== 'validated')) b.append(el('small', 'cohort-meta', 'Validação física na placa: pendente.'));
      b.addEventListener('click', () => evaluated && onPick(c));
      return b;
    }));
  }

  function renderCompare(root, entry, focus, publishedName, onFocus) {
    const metrics = entry.metrics || {};
    const names = [...MODEL_ORDER.filter(n => n in metrics), ...Object.keys(metrics).filter(n => !MODEL_ORDER.includes(n))];
    const cv = (((entry.validation || {}).group_kfold || {}).models) || {};
    const W = Math.max(420, Math.round(root.clientWidth || 640)), rowH = 50, top = 30, labelW = Math.min(190, Math.round(W * 0.28)), numW = 66;
    const x0 = labelW + 12, x1 = W - numW - 8, H = top + names.length * rowH + 2;
    const X = v => x0 + Math.max(0, Math.min(1, v)) * (x1 - x0);
    const s = svg('svg', {class: 'mlplot', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': 'F1-macro por modelo: folds da validação cruzada, média e desvio, validação e teste reservado'});
    for (const t of [0, .25, .5, .75, 1]) {
      s.append(svg('line', {class: 'axis', x1: X(t), x2: X(t), y1: top - 6, y2: H}));
      s.append(svg('text', {x: X(t), y: 12, 'text-anchor': 'middle'}, fmt(t, 2)));
    }
    s.append(svg('text', {x: W, y: 12, 'text-anchor': 'end'}, 'TESTE'));
    names.forEach((name, i) => {
      const m = metrics[name] || {}, c = cv[name] || {}, y = top + i * rowH + rowH / 2;
      const pub = name === publishedName, g = svg('g', {class: 'row' + (name === focus ? ' focus' : '') + (pub ? ' pub' : ''), tabindex: 0, role: 'button', 'aria-pressed': String(name === focus)});
      g.append(svg('title', {}, `${modelName(name)} — teste ${f3(m.test_f1_macro)} · validação ${f3(m.val_f1_macro)} · CV ${f3(c.f1_macro_mean)}${isNum(c.f1_macro_std) ? ' ± ' + f3(c.f1_macro_std) : ''}`));
      g.append(svg('rect', {class: 'hit', x: -8, y: y - rowH / 2 + 2, width: W + 8, height: rowH - 4, rx: 4}));
      g.append(svg('text', {class: 'name', x: 0, y: y - 1}, modelName(name)));
      const role = pub ? 'publicado' : name === entry.selected_model ? 'selecionado' : MODEL_ROLE[name] || 'candidato';
      g.append(svg('text', {class: 'role' + (pub ? ' pub' : ''), x: 0, y: y + 14}, role.toUpperCase()));
      g.append(svg('line', {class: 'base', x1: X(0), x2: X(1), y1: y, y2: y}));
      if (isNum(c.f1_macro_mean)) {
        const sd = isNum(c.f1_macro_std) ? c.f1_macro_std : 0;
        g.append(svg('line', {class: 'cv', x1: X(c.f1_macro_mean - sd), x2: X(c.f1_macro_mean + sd), y1: y, y2: y}));
        g.append(svg('line', {class: 'cvm', x1: X(c.f1_macro_mean), x2: X(c.f1_macro_mean), y1: y - 7, y2: y + 7}));
      }
      for (const f of (Array.isArray(c.folds) ? c.folds : [])) if (isNum(f.f1_macro)) g.append(svg('circle', {class: 'fold', cx: X(f.f1_macro), cy: y - 12, r: 1.9}));
      if (isNum(m.val_f1_macro)) g.append(svg('circle', {class: 'val', cx: X(m.val_f1_macro), cy: y, r: 4.5}));
      if (isNum(m.test_f1_macro)) g.append(svg('circle', {class: 'test', cx: X(m.test_f1_macro), cy: y, r: 5}));
      g.append(svg('text', {class: 'num' + (isNum(m.test_f1_macro) ? '' : ' none'), x: W, y: y + 6, 'text-anchor': 'end'}, f3(m.test_f1_macro)));
      g.addEventListener('click', () => onFocus(name));
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(name); } });
      s.append(g);
    });
    root.replaceChildren(s);
  }

  function matrixView(names, matrix) {
    const table = el('table', 'cm cm2'), head = el('tr'); head.append(el('th', 'corner', 'verdade ↓ · previsto →'));
    for (const n of names) { const th = el('th', '', CLASS_GLYPH[n] || n.slice(0, 2)); th.title = GESTURE_PT[n] || n; head.append(th); }
    table.append(head);
    matrix.forEach((row, i) => {
      const tr = el('tr'), total = row.reduce((a, b) => a + (isNum(b) ? b : 0), 0);
      tr.append(el('th', 'row', GESTURE_PT[names[i]] || names[i]));
      row.forEach((v, j) => {
        const share = total && isNum(v) ? v / total : 0, td = el('td', i === j ? 'hit' : v ? 'miss' : '', isNum(v) ? String(v) : '—');
        td.style.setProperty('--a', String(i === j ? 0.1 + 0.55 * share : v ? 0.12 + 0.6 * share : 0));
        td.title = `${GESTURE_PT[names[i]] || names[i]} → ${GESTURE_PT[names[j]] || names[j]}: ${v} de ${total}`;
        tr.append(td);
      });
      table.append(tr);
    });
    return table;
  }

  function renderFocus(root, entry, name, publishedName) {
    const m = entry && (entry.metrics || {})[name];
    if (!m) { root.replaceChildren(); return; }
    const cv = (((entry.validation || {}).group_kfold || {}).models || {})[name] || {};
    const head = el('header', 'panel-head'), title = el('div');
    title.append(el('span', 'eyebrow', name === publishedName ? 'Em foco · publicado' : 'Em foco'), el('h2', '', modelName(name)));
    head.append(title); root.replaceChildren(head);
    const names = m.per_class && typeof m.per_class === 'object' ? Object.keys(m.per_class) : CLASSES;
    if (Array.isArray(m.confusion_matrix) && m.confusion_matrix.length === names.length) root.append(matrixView(names, m.confusion_matrix));
    else root.append(el('div', 'pending', 'Matriz de confusão ausente neste experimento.'));
    const grid = el('dl', 'kv-grid ml-kv');
    const kv = (k, v, scope, pending) => { const d = el('div', 'kv'); d.append(el('dt', '', k), el('b', pending ? 'none' : '', v)); if (scope) d.append(el('small', '', scope)); grid.append(d); };
    kv('Acurácia', f3(m.accuracy), 'teste reservado');
    kv('CV média ± dp', isNum(cv.f1_macro_mean) ? `${f3(cv.f1_macro_mean)} ± ${f3(cv.f1_macro_std)}` : '—', isNum(cv.valid_folds) ? `${cv.valid_folds} folds · desenvolvimento` : 'desenvolvimento', !isNum(cv.f1_macro_mean));
    const far = m.far_neutral || {};
    if (far.status === 'evaluated' && isNum(far.value)) kv('Falsa ativação em repouso', `${fmt(100 * far.value, 1)}%`, isNum(far.support) ? `${far.support} janelas neutras` : '');
    else kv('Falsa ativação em repouso', 'não estimável', 'sem janelas neutras suficientes', true);
    const ev = m.event_level || {};
    kv('Eventos', isNum(ev.event_f1) ? `F1 ${f3(ev.event_f1)}` : '—', isNum(ev.true_episodes) ? `${ev.matched_episodes}/${ev.true_episodes} episódios · ${ev.false_activations} falsos` : '', !isNum(ev.event_f1));
    kv('Latência média', isNum(m.latency_mean_ms) ? `${fmt(m.latency_mean_ms, 3)} ms` : '—', m.latency_scope === 'notebook_python' ? 'no notebook (Python), não na placa' : (m.latency_scope || ''), !isNum(m.latency_mean_ms));
    const mem = m.memory || {};
    kv('Memória', isNum(mem.estimated_esp32_flash_bytes) ? `${fmt(mem.estimated_esp32_flash_bytes / 1024, 1)} KB` : '—', m.memory_scope === 'estimated_esp32' ? `estimativa ESP32 · ${isNum(mem.estimated_esp32_sram_bytes) ? mem.estimated_esp32_sram_bytes + ' B SRAM' : ''}` : (m.memory_scope || ''), !isNum(mem.estimated_esp32_flash_bytes));
    root.append(grid);
  }

  function renderTuning(root, tuning) {
    const trials = tuning && Array.isArray(tuning.trials) ? tuning.trials.filter(t => t && isNum(t.cv_f1_macro)) : [];
    const head = el('header', 'panel-head'), title = el('div');
    if (!trials.length) { title.append(el('span', 'eyebrow', 'Tuning'), el('h2', '', 'Hiperparâmetros')); head.append(title); root.replaceChildren(head, el('div', 'pending', 'Nenhuma busca de hiperparâmetros registrada neste experimento.')); return; }
    const param = Object.keys(trials[0]).find(k => !['status', 'cv', 'cv_f1_macro'].includes(k)) || 'param';
    const modelKey = Object.keys(((trials[0].cv || {}).models) || {})[0];
    title.append(el('span', 'eyebrow', `Tuning · ${modelName(modelKey)}`), el('h2', '', param === 'dt_max_depth' ? 'Profundidade máxima' : param)); head.append(title);
    const sd = t => { const v = ((((t.cv || {}).models) || {})[modelKey] || {}).f1_macro_std; return isNum(v) ? v : 0; };
    const lo = Math.max(0, Math.floor(Math.min(...trials.map(t => t.cv_f1_macro - sd(t))) * 10) / 10);
    const hi = Math.min(1, Math.ceil(Math.max(...trials.map(t => t.cv_f1_macro + sd(t))) * 10) / 10 || 1);
    const W = Math.max(240, Math.round(root.clientWidth || 300)), H = 168, l = 40, r = 16, t0 = 14, b = 34;
    const X = i => trials.length === 1 ? (l + W - r) / 2 : l + i * (W - l - r) / (trials.length - 1), Y = v => t0 + (1 - (v - lo) / ((hi - lo) || 1)) * (H - t0 - b);
    const s = svg('svg', {class: 'mlplot tune', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'F1-macro médio da validação cruzada por valor testado'});
    for (const v of [lo, (lo + hi) / 2, hi]) { s.append(svg('line', {class: 'axis', x1: l, x2: W - r, y1: Y(v), y2: Y(v)})); s.append(svg('text', {x: l - 8, y: Y(v) + 3, 'text-anchor': 'end'}, fmt(v, 2))); }
    s.append(svg('polyline', {class: 'tline', points: trials.map((t, i) => `${X(i)},${Y(t.cv_f1_macro)}`).join(' ')}));
    const chosen = tuning['selected_' + param];
    trials.forEach((t, i) => {
      const sel = t[param] === chosen, d = sd(t);
      if (d) s.append(svg('line', {class: 'terr', x1: X(i), x2: X(i), y1: Y(t.cv_f1_macro - d), y2: Y(t.cv_f1_macro + d)}));
      s.append(svg('circle', {class: 'tpt' + (sel ? ' sel' : ''), cx: X(i), cy: Y(t.cv_f1_macro), r: sel ? 5 : 4}));
      s.append(svg('text', {class: sel ? 'sel' : '', x: X(i), y: H - 16, 'text-anchor': 'middle'}, String(t[param])));
      s.append(svg('text', {class: 'val' + (sel ? ' sel' : ''), x: X(i), y: H - 3, 'text-anchor': 'middle'}, sel ? 'ESCOLHIDA' : f3(t.cv_f1_macro)));
    });
    const status = tuning.status === 'selected_on_development_cv' ? 'Escolha pela CV de desenvolvimento; o teste reservado não escolhe hiperparâmetros.' : (tuning.status || '');
    root.replaceChildren(head, s, el('p', 'hint', [status, tuning.caveat].filter(Boolean).join(' ')));
  }

  function renderPipeline(root, entry, status, view, titleNode, cohort) {
    if (titleNode) titleNode.textContent = cohort === 'real' ? 'Do sensor físico à API' : entry ? 'Do sensor simulado à API' : 'Do sensor à API';
    const split = (entry && entry.split) || {}, eda = (entry && entry.eda) || {};
    const groups = [...(split.train_groups || []), ...(split.validation_groups || []), ...(split.test_groups || [])];
    const dist = eda.class_distribution && typeof eda.class_distribution === 'object' ? Object.values(eda.class_distribution).filter(isNum).reduce((a, b) => a + b, 0) : null;
    const orch = entry && entry.orchestration, tr = entry && entry.tracking;
    const uriLocal = tr && /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(tr.tracking_uri || '');
    const sameExp = status && entry && status.experiment_id === entry.experiment_id;
    const dep = status ? status.deployment_status : null;
    const nodes = [
      ['Aquisição', entry ? 'ok' : 'pending', entry ? `${groups.length} participantes` : 'Sem corpus avaliado', entry ? `MQTT → JSONL · ${dist ? dist + (eda.scope === 'development_only' ? ' janelas de desenvolvimento' : ' janelas') : ''} · sha ${shortHash(entry.dataset_sha256)}` : ''],
      ['Airflow', orch && orch.run_id ? 'ok' : 'pending', orch && orch.dag_id ? orch.dag_id : 'Sem execução registrada', orch && orch.run_id ? orch.run_id : ''],
      ['MLflow', tr && tr.status === 'logged' ? 'ok' : 'pending', tr && tr.run_id ? `run ${tr.run_id.slice(0, 8)}…` : 'Sem run registrado', tr && tr.run_id ? `experimento ${tr.experiment_id} · ${tr.tracking_uri}${uriLocal ? '' : ' (rede interna do Compose)'}` : ''],
      ['Publicação', dep === 'published' ? (sameExp ? 'ok' : 'warn') : dep === 'fixed' ? 'warn' : dep === 'invalid' ? 'bad' : 'pending',
        dep === 'published' ? 'deployment.json' : dep === 'fixed' ? 'Bundle fixo' : dep === 'invalid' ? 'Publicação inválida' : status ? 'Não publicado' : 'Sem leitura',
        dep === 'published' ? (sameExp ? 'publica este experimento' : `publica outro experimento: ${status.experiment_id}`) : dep === 'fixed' ? 'sem publicação atômica' : ''],
      ['API', view.state === 'ok' ? 'ok' : view.state === 'pending' ? 'pending' : 'bad', view.state === 'ok' ? 'Inferência ativa' : view.label, view.state === 'ok' ? `${modelName(status.model_name)} · ${shortHash(status.model_sha256)}` : ''],
    ];
    const list = el('ol', 'ml-path');
    for (const [step, state, value, detail] of nodes) { const li = el('li'); li.dataset.state = state; li.append(el('span', 'step', step), el('b', '', value), el('small', '', detail)); list.append(li); }
    root.replaceChildren(list);
  }

  // ---------------------------------------------------------------- C · inferências
  function probBar(probabilities, label) {
    const bar = el('span', 'prob');
    if (!probabilities || typeof probabilities !== 'object') { bar.classList.add('none'); return bar; }
    const keys = CLASSES.filter(k => isNum(probabilities[k])).concat(Object.keys(probabilities).filter(k => !CLASSES.includes(k) && isNum(probabilities[k])));
    for (const k of keys) { const s = el('span', k === label ? 'top' : ''); s.style.flexGrow = String(probabilities[k]); s.title = `${GESTURE_PT[k] || k}: ${fmt(100 * probabilities[k], 1)}%`; bar.append(s); }
    bar.title = keys.map(k => `${GESTURE_PT[k] || k} ${fmt(100 * probabilities[k], 1)}%`).join(' · ');
    return bar;
  }
  function labelLine(label, cls) {
    const line = el('div', cls); line.append(el('span', 'inf-glyph', label ? CLASS_GLYPH[label] || '·' : ''), el('span', 'inf-name', GESTURE_PT[label] || label || '—')); return line;
  }

  function renderInfLatest(root, preds, status, view) {
    const items = sortedPredictions(preds), eyebrow = el('span', 'eyebrow', 'Última sessão persistida');
    if (!items.length) {
      const why = !preds ? (view.state === 'ok' || view.state === 'idle' ? 'Aguardando a leitura das previsões.' : 'Sem leitura do serviço: nenhuma previsão é exibida.')
        : preds.status === 'invalid' ? 'Arquivo de previsões ilegível: nenhuma previsão é exibida no lugar dele.'
        : status && status.status !== 'ready' ? 'Sem modelo publicado, nenhuma sessão é classificada.'
        : 'Nenhuma sessão persistida foi processada pelo modelo publicado ainda.';
      root.replaceChildren(eyebrow, labelLine(null, 'inf-label none'), el('div', 'pending', why));
      return;
    }
    const p = items[0];
    const conf = el('div', 'inf-conf');
    conf.append(el('b', isNum(p.confidence) ? '' : 'none', isNum(p.confidence) ? confPct(p.confidence) : '—'), el('small', '', 'confiança · não calibrada'));
    const row = el('div', 'inf-row'); row.append(labelLine(p.label, 'inf-label'), conf);
    const marks = el('div', 'ml-marks');
    marks.append(provTag(p.input_origin, 'Entrada'), provTag(p.training_cohort, 'Treino'));
    const persisted = el('span', 'tag persisted', 'Sessão persistida'); persisted.title = 'Última janela causal de uma sessão gravada · fora do portão de gestos'; marks.append(persisted);
    const meta = el('p', 'ml-ids');
    meta.append(el('span', '', p.session_id || '—'), el('span', '', `${dateOf(p.generated_at_iso)}`), el('span', '', `${isNum(p.samples) ? p.samples : '—'} amostras · ${isNum(p.windows) ? p.windows : '—'} janelas`), el('span', '', `${modelName(p.model_name)} · ${shortHash(p.model_sha256)}`));
    root.replaceChildren(eyebrow, row, probBar(p.probabilities, p.label), marks, meta);
  }

  function renderInfLive(root, events, origin, fresh) {
    const last = (events || []).filter(e => e.gesture && !['IR_ON', 'IR_OFF'].includes(e.gesture)).slice(-1)[0];
    const mark = origin === 'ESP32_HW' ? provTag('real', 'Sinal') : origin === 'DEMO' ? provTag('demo', 'Sinal') : el('span', 'tag pending', 'Sem sinal');
    const live = el('span', 'live-mark' + (fresh ? ' on' : ''), fresh ? 'ao vivo' : 'parado');
    const head = el('div', 'ml-marks'); head.append(live, mark);
    if (!last) { root.replaceChildren(labelLine(null, 'inf-label small none'), head); return; }
    const line = labelLine(last.gesture, 'inf-label small'); line.dataset.src = last.source;
    const out = last.status === 'rejected' ? `rejeitado · ${reasonText(last.reason)}` : last.status === 'observed' ? 'observado' : last.status === 'dispatched' ? 'enviado ao módulo' : 'executado';
    root.replaceChildren(line, head, el('p', 'ml-ids', `${srcName(last.source)} · t ${(last.t / 1000).toFixed(1)} s · ${out}`));
  }

  function renderQuery(root, q) {
    if (!q) { root.replaceChildren(); return; }
    if (q.busy) { root.replaceChildren(el('p', 'hint', 'Consultando o serviço…')); return; }
    if (q.error) { const p = el('p', 'q-err'); p.append(el('span', 'sdot'), el('span', '', q.error)); p.firstChild.dataset.state = 'bad'; root.replaceChildren(p); return; }
    const r = q.result, box = el('div', 'q-result');
    const head = el('div', 'inf-row'); head.append(labelLine(r.label, 'inf-label small'), el('b', 'q-conf', isNum(r.confidence) ? confPct(r.confidence) : '—'));
    const marks = el('div', 'ml-marks'); marks.append(provTag(r.input_origin, 'Entrada'), provTag(r.training_cohort, 'Treino'), el('span', 'tag', 'janela única'));
    box.append(head, probBar(r.probabilities, r.label), marks, el('p', 'ml-ids', `${q.samples} amostras enviadas · ${q.at} · ${modelName(r.model_name)}`));
    root.replaceChildren(box);
  }

  function renderLedger(body, preds) {
    const items = sortedPredictions(preds), rows = [];
    for (const p of items.slice(0, 40)) {
      const tr = el('tr');
      tr.append(el('td', 'mono', timeOf(p.generated_at_iso)));
      const sid = el('td', 'mono sid', p.session_id || '—'); sid.title = `corpus ${p.dataset_sha256 || '—'}`; tr.append(sid);
      const o = el('td'); o.append(provTag(p.input_origin)); tr.append(o);
      const lab = el('td', 'pred'); lab.append(el('span', 'g', CLASS_GLYPH[p.label] || '?'), el('span', '', GESTURE_PT[p.label] || p.label || '—')); tr.append(lab);
      const pb = el('td'); pb.append(probBar(p.probabilities, p.label)); tr.append(pb);
      tr.append(el('td', 'mono num', isNum(p.confidence) ? confPct(p.confidence) : '—'));
      tr.append(el('td', 'mono num', `${isNum(p.samples) ? p.samples : '—'} / ${isNum(p.windows) ? p.windows : '—'}`));
      const mdl = el('td', 'mono'); mdl.textContent = `${modelName(p.model_name)} · ${shortHash(p.model_sha256).slice(0, 8)}`; mdl.append(' ', provTag(p.training_cohort)); tr.append(mdl);
      const st = el('td'); const s = el('span', 'state ' + (p.status === 'ready' ? 'ok' : 'pending'), p.status === 'ready' ? 'processada' : (p.status || 'pendente')); st.append(s); tr.append(st);
      rows.push(tr);
    }
    for (const e of (preds && Array.isArray(preds.errors) ? preds.errors : [])) {
      const tr = el('tr', 'err');
      tr.append(el('td', 'mono', '—'), el('td', 'mono sid', e.file || '—'));
      const o = el('td'); o.append(provTag(e.cohort)); tr.append(o);
      const msg = el('td'); msg.colSpan = 5; msg.textContent = `Sessão não classificada · ${e.error || 'erro'}`; tr.append(msg);
      const st = el('td'); st.append(el('span', 'state bad', 'falhou')); tr.append(st);
      rows.push(tr);
    }
    if (!rows.length) { const tr = el('tr'), td = el('td', 'empty'); td.colSpan = 9; td.textContent = 'Nenhuma inferência de sessão persistida disponível.'; tr.append(td); rows.push(tr); }
    body.replaceChildren(...rows);
  }

  const MLLib = {serviceView, pickCohort, sortedPredictions, samplesFromFrames, inferOrigin, provOf, ageText, shortHash, modelName, cohortCaption,
    renderService, renderNotice, renderPublished, renderHeadline, renderCohorts, renderCompare, renderFocus, renderTuning, renderPipeline,
    renderInfLatest, renderInfLive, renderQuery, renderLedger};

  globalThis.IntelLib = {setOrigin, srcName, drawChart, renderRecognizers, renderFlow, renderRejections, renderHistory, renderEvaluation, renderCollect, rejectionTotals, GESTURE_PT, SOURCE_PT, REASON_PT, GLYPH, reasonText, ML: MLLib};
})();
