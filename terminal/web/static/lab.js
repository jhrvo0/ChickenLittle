'use strict';
/* MotionLab — casca da aplicação: conexão, navegação, sinal ao vivo, HUD de gestos,
   Motion Control (perfis e segurança), Air Slides e a ligação com Canvas, Música e Intelligence.

   Fluxo de dados: GET /api/live (~70 ms, com cursor de frames e eventos, sem perder nada) e
   GET /api/lab (1 s, configuração e estatísticas). Ações internas chegam como eventos com
   `status: "dispatched"`; o módulo aberto as executa. A interface nunca inventa leitura: sem
   ESP32, mostra vazio; a demonstração é sempre rotulada. */
(() => {
  // ================================================================== núcleo puro (testado no Node)
  const TRIGGERS = ['APPROACH', 'RETREAT', 'HOLD', 'IR_TAP', 'IR_HOLD'];
  const TRIGGER_INFO = {
    APPROACH: {glyph: '↓', name: 'Aproximar', hint: 'mão vem em direção ao sensor', kind: 'gesture'},
    RETREAT: {glyph: '↑', name: 'Afastar', hint: 'mão se afasta do sensor', kind: 'gesture'},
    HOLD: {glyph: '■', name: 'Segurar', hint: 'mão parada na zona ativa', kind: 'gesture'},
    IR_TAP: {glyph: '•', name: 'Toque no IR', hint: 'cartão/dedo perto do IR por < 0,6 s', kind: 'ir'},
    IR_HOLD: {glyph: '◉', name: 'Toque longo no IR', hint: 'manter perto do IR', kind: 'ir'},
  };
  const CONTEXT_PT = {control: 'Motion Control', canvas: 'Motion Canvas', music: 'Air Music', slides: 'Air Slides'};
  const VIEWS = {
    home: {code: '00', title: 'Início'}, control: {code: '01', title: 'Motion Control'}, canvas: {code: '02', title: 'Motion Canvas'},
    music: {code: '03', title: 'Air Music'}, slides: {code: '04', title: 'Air Slides'}, intelligence: {code: '05', title: 'Motion Intelligence'},
  };
  const MAX_FRAMES = 600, MAX_EVENTS = 400;

  function mergeById(buffer, incoming, key, max) {
    const lastId = buffer.length ? buffer[buffer.length - 1][key] : 0;
    for (const item of incoming) if (item[key] > lastId) buffer.push(item);
    if (buffer.length > max) buffer.splice(0, buffer.length - max);
    return buffer;
  }
  function formatCm(cm) { return cm === null || cm === undefined ? '—' : cm.toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1}) + ' cm'; }
  function connectionView(conn) {
    if (!conn) return {state: 'off', label: 'Desconectado', detail: 'Escolha a porta USB'};
    if (conn.status === 'connecting') return {state: 'connecting', label: 'Conectando…', detail: conn.port || ''};
    if (conn.status === 'error') return {state: 'error', label: 'Erro de conexão', detail: conn.message || ''};
    if (conn.status !== 'connected') return {state: 'off', label: 'Desconectado', detail: 'Escolha a porta USB'};
    if (!conn.live) return {state: 'stale', label: 'Sem leituras', detail: conn.message || ''};
    if (conn.origin === 'DEMO') return {state: 'demo', label: 'Demonstração', detail: 'Simulador · sem sensores físicos'};
    return {state: 'live', label: 'ESP32 ao vivo', detail: `${conn.port} · ${conn.frames} frames`};
  }
  /** Texto do HUD para um evento do motor (ou `null` quando não deve aparecer). */
  function describeEvent(e, catalog, intel) {
    if (!e || e.status === 'observed' || e.reason === 'no_module') return null;
    if (e.source === 'ui') return null;
    const info = TRIGGER_INFO[e.gesture] || {glyph: '?', name: e.gesture};
    const srcName = intel ? intel.srcName(e.source) : e.source;
    const conf = e.confidence_kind === 'softmax' && typeof e.confidence === 'number' ? ` · ${Math.round(e.confidence * 100)}%` : '';
    const action = e.action ? (catalog[e.action] ? catalog[e.action].label : e.action) : null;
    if (e.status === 'rejected') return {kind: 'rejected', glyph: info.glyph, title: `${info.name} — ${(intel && intel.reasonText(e.reason)) || e.reason}`, detail: `${srcName}${conf}${action ? ' · ' + action : ''}`};
    if (e.action === 'lab.toggle_armed') return {kind: 'ok', glyph: info.glyph, title: e.detail === 'armed' ? 'Gestos ativados' : 'Gestos pausados', detail: `${srcName} · ${info.name}`};
    return {kind: TRIGGER_INFO[e.gesture] && TRIGGER_INFO[e.gesture].kind === 'ir' ? 'ir' : 'ok', glyph: info.glyph, title: action || info.name, detail: `${info.name} · ${srcName}${conf}`};
  }
  const Core = {mergeById, formatCm, connectionView, describeEvent, TRIGGERS, TRIGGER_INFO};
  globalThis.LabCore = Core;
  if (typeof document === 'undefined' || !document.getElementById('app')) return;

  // ================================================================== estado e utilitários
  const $ = id => document.getElementById(id);
  const IL = globalThis.IntelLib, ML = globalThis.AirMusicLib, CL = globalThis.MotionCanvasLib;
  const S = {
    view: 'home', conn: null, live: null, lab: null, frames: [], events: [], cursor: {f: 0, e: 0},
    primed: false, catalog: {}, editing: null, evaluation: null, demo: {canvas: false, music: false},
    slide: 0, slidesBlank: false, lastHistoryRender: 0,
  };
  const key = () => (document.querySelector('meta[name="motionpet-key"]') || {}).content || '';
  async function api(path, data) {
    const options = {headers: {'X-MotionPet-Key': key()}, cache: 'no-store'};
    if (data !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(data); }
    const response = await fetch(path, options);
    let result; try { result = await response.json(); } catch (_) { throw new Error('Resposta ilegível do servidor local.'); }
    if (!response.ok || result.ok === false) throw new Error(result.error || 'Não foi possível completar a ação.');
    return result;
  }
  let toastTimer = null;
  function toast(message, kind = 'error') {
    const el = $('toast'); el.textContent = message; el.dataset.kind = kind; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
  }
  async function lab(cmd, extra = {}) {
    try {
      const result = await api('/api/lab', {cmd, ...extra});
      if (result.lab && result.lab.store) applyLab(result.lab);
      return result.lab;
    } catch (error) { toast(error.message); throw error; }
  }
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  const isLive = () => !!(S.conn && S.conn.live);

  // ================================================================== conexão
  async function loadPorts() {
    try {
      const {ports} = await api('/api/ports');
      for (const id of ['ports', 'dialog-ports']) {
        const select = $(id), previous = select.value; select.replaceChildren();
        if (!ports.length) select.add(new Option('Nenhuma porta encontrada', ''));
        for (const p of ports) select.add(new Option(`${p.device} — ${p.description}`, p.device));
        if (ports.some(p => p.device === previous)) select.value = previous;
        else if (ports.some(p => p.device === 'COM3')) select.value = 'COM3';
      }
    } catch (error) { toast(error.message); }
  }
  async function connect(port) {
    if (!port) { toast('Escolha uma porta.'); return; }
    try { await api('/api/connect', {port}); } catch (error) { toast(error.message); }
  }
  async function disconnect() { try { await api('/api/disconnect', {}); } catch (error) { toast(error.message); } }
  $('connect').addEventListener('click', () => connect($('ports').value));
  $('disconnect').addEventListener('click', disconnect);
  $('refresh-ports').addEventListener('click', loadPorts);
  $('dialog-connect').addEventListener('click', () => connect($('dialog-ports').value));
  $('dialog-disconnect').addEventListener('click', disconnect);
  $('dialog-refresh').addEventListener('click', loadPorts);
  $('conn-chip').addEventListener('click', () => { loadPorts(); $('conn-dialog').showModal(); });

  function renderConnection() {
    const v = connectionView(S.conn);
    for (const id of ['conn-dot', 'hero-dot']) $(id).dataset.state = v.state;
    $('conn-label').textContent = v.label; $('conn-detail').textContent = v.detail;
    $('hero-status').textContent = v.label;
    $('hero-message').textContent = S.conn ? S.conn.message : '';
    $('dialog-message').textContent = S.conn ? S.conn.message : '';
    $('hero-origin').textContent = S.conn && S.conn.origin !== 'NONE' ? (S.conn.origin === 'ESP32_HW' ? 'ESP32 real' : 'Demonstração') : '—';
    $('hero-frames').textContent = S.conn ? String(S.conn.frames) : '0';
    const period = S.lab && S.lab.sample_period;
    $('hero-period').textContent = period ? `${Math.round(period.mean_ms)} ms` : '—';
    const connected = S.conn && S.conn.status === 'connected';
    $('connect').disabled = !!connected; $('disconnect').disabled = !connected;
    $('dialog-connect').disabled = !!connected; $('dialog-disconnect').disabled = !connected;
    $('demo-badge').hidden = !(S.conn && S.conn.origin === 'DEMO');
  }

  // ================================================================== navegação
  function setView(view) {
    if (!VIEWS[view]) view = 'home';
    const previous = S.view; S.view = view;
    for (const sec of document.querySelectorAll('.view')) sec.hidden = sec.dataset.view !== view;
    for (const a of document.querySelectorAll('.rail-list [data-nav]')) {
      if (a.dataset.nav === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    }
    $('view-code').textContent = VIEWS[view].code; $('view-title').textContent = VIEWS[view].title;
    document.title = `${VIEWS[view].title} — MotionLab`;
    lab('module', {module: view}).catch(() => {});
    if (view === 'canvas') ensureCanvas().start(); else if (canvasApp) canvasApp.stop();
    if (previous === 'music' && view !== 'music' && musicApp) musicApp.silenceLive();
    if (view === 'intelligence' && !S.evaluation) evaluate();
    if (view === 'intelligence') setLevel(MLS.level);
    if (view === 'control') renderControl();
  }
  window.addEventListener('hashchange', () => setView(location.hash.slice(1)));

  // ================================================================== polling
  async function liveLoop() {
    try {
      const data = await api(`/api/live?f=${S.cursor.f}&e=${S.cursor.e}`);
      S.live = data; S.conn = data.connection; IL.setOrigin(data.origin);
      if (data.frame_seq < S.cursor.f || data.event_seq < S.cursor.e) { S.frames = []; S.events = []; }
      mergeById(S.frames, data.frames, 'seq', MAX_FRAMES);
      mergeById(S.events, data.events, 'id', MAX_EVENTS);
      S.cursor = {f: data.frame_seq, e: data.event_seq};
      // Na primeira leitura só sincroniza: ações antigas nunca são reexecutadas ao abrir a página.
      if (S.primed) for (const e of data.events) onEvent(e);
      S.primed = true;
      renderLive();
    } catch (error) {
      if (S.conn && S.conn.status === 'connected') S.conn = {...S.conn, live: false, message: 'Servidor local sem resposta.'};
      // Servidor reiniciado: a chave local mudou e só recarregar a página resolve.
      if (/Reabra a página/.test(error.message) && !S._keyWarned) { S._keyWarned = true; toast('O servidor do MotionLab foi reiniciado. Recarregue a página (F5).'); }
      renderConnection();
    } finally {
      setTimeout(liveLoop, document.hidden ? 1000 : 70);
    }
  }
  async function labLoop() {
    try { applyLab(await api('/api/lab')); } catch (_) { /* liveLoop já sinaliza */ }
    finally { setTimeout(labLoop, document.hidden ? 3000 : 1000); }
  }
  function applyLab(data) {
    S.lab = data;
    S.catalog = Object.fromEntries(data.catalog.map(a => [a.id, a]));
    if (data.store.load_error && !S._loadWarned) { S._loadWarned = true; toast(data.store.load_error, 'info'); }
    $('driver').value = data.store.settings.driver;
    renderArm(); renderConnection();
    if (S.view === 'control') renderControl();
    if (S.view === 'slides') renderSlidesMap();
    if (S.view === 'intelligence') renderIntel();
  }

  // ================================================================== sinal ao vivo / topo
  function renderLive() {
    renderConnection(); renderArm();
    const sig = S.live && S.live.signal, fresh = S.live && S.live.age_ms !== null && S.live.age_ms < 1000;
    $('readout-distance').textContent = fresh && sig && sig.filtered_cm !== null ? formatCm(sig.filtered_cm) : '—';
    const irOn = !!(fresh && S.live.ir.active);
    $('readout-ir').dataset.on = String(irOn); $('readout-ir-text').textContent = !fresh ? '—' : irOn ? 'ativo' : 'livre';
    if (S.view === 'intelligence' || S.view === 'home') { const rec = S.live.recording; if (rec && S.view === 'intelligence') IL.renderCollect(collectUI, rec, S.lab && S.lab.sessions); }
    if (S.view === 'control' && S.live) $('cooldown-left').textContent = S.live.cooldown_left_ms ? `cooldown ${S.live.cooldown_left_ms} ms` : '';
    if (S.view === 'control') renderActivity();
  }
  function renderArm() {
    const armed = !!(S.live ? S.live.armed : S.lab && S.lab.armed);
    $('arm').setAttribute('aria-checked', String(armed));
    $('arm-text').textContent = armed ? 'Armado' : 'Pausado';
  }
  $('arm').addEventListener('click', () => {
    const armed = $('arm').getAttribute('aria-checked') === 'true';
    lab('arm', {value: !armed}).then(() => { if (S.live) S.live.armed = !armed; renderArm(); }).catch(() => {});
  });
  $('driver').addEventListener('change', e => lab('settings', {changes: {driver: e.target.value}}).catch(() => {}));

  function currentInput(view) {
    if (S.demo[view]) return {...demoSignal.sample(), demo: true};
    const sig = S.live && S.live.signal, fresh = S.live && S.live.age_ms !== null && S.live.age_ms < 1000;
    if (!fresh || !sig) return {position: null, velocity: 0, ir: false, demo: false, stale: true};
    return {position: sig.present ? sig.position : null, velocity: sig.velocity_cm_s, ir: !!S.live.ir.active, demo: false};
  }
  // Cores dos canais (mesmas de lab.css).
  const C = {ink: '#ecebe6', ink2: '#a09e97', ink3: '#64625d', ink4: '#3d3c39', line: 'rgba(255,255,255,0.07)', line2: 'rgba(255,255,255,0.12)',
    ultra: '#7cc9c0', ir: '#e2a15c', ml: '#a99cf0', dev: '#dc8fb0', bad: '#e0735f', num: 'Bahnschrift, "Segoe UI", sans-serif', mono: '"Cascadia Mono", Consolas, monospace'};
  const LAYER_COLORS = [C.ultra, C.ml, C.ir, C.dev];
  function fitCanvas(c) {
    const dpr = Math.min(2, window.devicePixelRatio || 1), r = c.getBoundingClientRect();
    const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    return {ctx: c.getContext('2d'), w, h, dpr};
  }
  const isFresh = () => !!(S.live && S.live.age_ms !== null && S.live.age_ms < 1000);
  function drawStrip() {
    const c = $('strip-canvas'); if (!c.offsetParent) return;
    const {ctx, w, h, dpr} = fitCanvas(c);
    ctx.clearRect(0, 0, w, h);
    const fr = S.frames.slice(-100), step = w / 100;
    if (!fr.length || !isFresh()) {
      ctx.strokeStyle = C.ink4; ctx.lineWidth = dpr; ctx.setLineDash([3 * dpr, 4 * dpr]);
      ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke(); ctx.setLineDash([]); return;
    }
    const last = fr[fr.length - 1].seq;
    ctx.fillStyle = C.ir;
    for (const f of fr) if (f.ir) ctx.fillRect(w - (last - f.seq + 1) * step, h - 1.5 * dpr, step, 1.5 * dpr);
    ctx.strokeStyle = C.ultra; ctx.lineWidth = 1.25 * dpr; ctx.lineJoin = 'round'; ctx.beginPath(); let pen = false, lx = 0, ly = 0;
    for (const f of fr) {
      if (f.f === null) { pen = false; continue; }
      const x = w - (last - f.seq) * step - step / 2, y = 3 * dpr + (Math.min(90, f.f) / 90) * (h - 8 * dpr);
      pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true; lx = x; ly = y;
    }
    ctx.stroke();
    if (pen) { ctx.fillStyle = C.ink; ctx.beginPath(); ctx.arc(lx, ly, 2 * dpr, 0, Math.PI * 2); ctx.fill(); }
  }

  /** Campo do sensor na home: o cone do ultrassom com a mão na distância medida e ecos dos últimos frames. */
  function drawHomeField(now) {
    const c = $('home-field'); if (!c || !c.offsetParent) return;
    const {ctx, w, h, dpr} = fitCanvas(c);
    ctx.clearRect(0, 0, w, h);
    const fresh = isFresh(), demo = !!(S.conn && S.conn.origin === 'DEMO');
    const x0 = 18 * dpr, y0 = h / 2 - 8 * dpr, R = w - x0 - 56 * dpr, maxCm = 90;
    const th = Math.min(0.5, Math.asin(Math.min(0.95, (h / 2 - 40 * dpr) / R)));
    const r = cm => (Math.min(maxCm, Math.max(0, cm)) / maxCm) * R;
    const arc = radius => { ctx.beginPath(); ctx.arc(x0, y0, radius, -th, th); };
    const st = S.lab && S.lab.store.settings;
    if (st) {
      ctx.fillStyle = 'rgba(124,201,192,0.035)'; ctx.beginPath();
      ctx.arc(x0, y0, r(st.far_cm), -th, th); ctx.arc(x0, y0, r(st.near_cm), th, -th, true); ctx.closePath(); ctx.fill();
    }
    ctx.strokeStyle = C.line; ctx.lineWidth = dpr;
    for (const a of [-th, th]) { ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(a) * R, y0 + Math.sin(a) * R); ctx.stroke(); }
    ctx.font = `500 ${9.5 * dpr}px ${C.mono}`; ctx.fillStyle = C.ink4; ctx.textAlign = 'center';
    for (const cm of [10, 20, 40, 60, 80]) {
      ctx.strokeStyle = C.line; arc(r(cm)); ctx.stroke();
      ctx.fillText(String(cm), x0 + Math.cos(th) * r(cm), y0 + Math.sin(th) * r(cm) + 16 * dpr);
    }
    ctx.strokeStyle = C.line2; ctx.setLineDash([2 * dpr, 5 * dpr]); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + R, y0); ctx.stroke(); ctx.setLineDash([]);
    // sensor: os dois "olhos" do HC-SR04; o IR acende um halo âmbar em volta
    const irOn = !!(fresh && S.live.ir.active);
    for (const dy of [-7, 7]) { ctx.strokeStyle = C.ink3; ctx.lineWidth = 1.2 * dpr; ctx.beginPath(); ctx.arc(x0, y0 + dy * dpr, 4.5 * dpr, 0, Math.PI * 2); ctx.stroke(); }
    if (irOn) {
      ctx.fillStyle = 'rgba(226,161,92,0.14)'; ctx.beginPath(); ctx.arc(x0, y0, 26 * dpr, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = C.ir; ctx.lineWidth = 1.25 * dpr; ctx.beginPath(); ctx.arc(x0, y0, 18 * dpr, 0, Math.PI * 2); ctx.stroke();
    }
    const sig = S.live && S.live.signal, cm = fresh && sig && sig.filtered_cm !== null ? sig.filtered_cm : null;
    ctx.font = `500 ${10 * dpr}px ${C.mono}`;
    if (demo) { ctx.textAlign = 'right'; ctx.fillStyle = C.ml; ctx.fillText('DEMO · SIMULADOR', w - 4 * dpr, 16 * dpr); }
    if (cm === null) {
      ctx.fillStyle = C.ink3; ctx.textAlign = 'left'; ctx.font = `500 ${10.5 * dpr}px ${C.mono}`;
      ctx.fillText(S.conn && S.conn.status === 'connected' && fresh ? 'SEM MÃO NO CAMPO' : 'SEM SINAL', x0 + 40 * dpr, y0 - 14 * dpr);
      return;
    }
    // o pulso do ultrassom saindo até a mão
    const p = (now % 1400) / 1400;
    ctx.strokeStyle = `rgba(124,201,192,${0.22 * (1 - p)})`; ctx.lineWidth = dpr; arc(r(cm) * p); ctx.stroke();
    // ecos dos últimos frames
    const recent = S.frames.slice(-10, -1).filter(f => f.f !== null);
    recent.forEach((f, i) => { ctx.strokeStyle = `rgba(124,201,192,${0.02 + 0.07 * (i / recent.length)})`; ctx.lineWidth = dpr; arc(r(f.f)); ctx.stroke(); });
    const rx = r(cm);
    ctx.strokeStyle = C.ultra; ctx.lineWidth = 1.5 * dpr; arc(rx); ctx.stroke();
    ctx.fillStyle = C.ink; ctx.beginPath(); ctx.arc(x0 + rx, y0, 3.5 * dpr, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(236,235,230,0.25)'; ctx.beginPath(); ctx.arc(x0 + rx, y0, 9 * dpr, 0, Math.PI * 2); ctx.stroke();
    const label = cm.toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1});
    const numFont = `300 ${34 * dpr}px ${C.num}`, unitFont = `500 ${10 * dpr}px ${C.mono}`;
    ctx.font = numFont; const lw = ctx.measureText(label).width; ctx.font = unitFont; const uw = ctx.measureText('CM').width;
    const tx = rx < R - 170 * dpr ? x0 + rx + 20 * dpr : x0 + rx - 20 * dpr - lw - 8 * dpr - uw;
    ctx.textAlign = 'left'; ctx.font = numFont; ctx.fillStyle = C.ink; ctx.fillText(label, tx, y0 - 20 * dpr);
    ctx.font = unitFont; ctx.fillStyle = C.ink3; ctx.fillText('CM', tx + lw + 8 * dpr, y0 - 20 * dpr);
  }

  // ================================================================== eventos → módulos + HUD
  let hudTimer = null;
  function showHud(e) {
    const d = describeEvent(e, S.catalog, IL); if (!d) return;
    const hud = $('gesture-hud');
    hud.classList.remove('leaving'); hud.hidden = false; hud.dataset.kind = d.kind;
    $('hud-glyph').textContent = d.glyph; $('hud-title').textContent = d.title; $('hud-detail').textContent = d.detail;
    hud.style.animation = 'none'; void hud.offsetWidth; hud.style.animation = '';
    clearTimeout(hudTimer);
    hudTimer = setTimeout(() => { hud.classList.add('leaving'); setTimeout(() => { hud.hidden = true; }, 350); }, 1700);
  }
  function onEvent(e) {
    if (e.gesture === 'IR_ON' || e.gesture === 'IR_OFF') return;
    showHud(e);
    if (S.view === 'control' && TRIGGERS.includes(e.gesture) && e.status !== 'observed') flashBinding(e.gesture);
    if (e.status !== 'dispatched' || !e.action || e.context !== S.view) return;
    try {
      if (e.context === 'canvas') ensureCanvas().action(e.action);
      else if (e.context === 'music') { ensureMusic().action(e.action); renderMusic(); }
      else if (e.context === 'slides') slidesAction(e.action);
    } catch (error) { toast(error.message); }
  }

  // ================================================================== Motion Control
  function profilesFor(ctx) { return S.lab ? S.lab.store.profiles.filter(p => p.context === ctx) : []; }
  function editingProfile() {
    if (!S.lab) return null;
    const store = S.lab.store;
    const prof = store.profiles.find(p => p.id === S.editing) || store.profiles.find(p => p.id === store.active.control);
    S.editing = prof ? prof.id : null; return prof;
  }
  function renderControl() {
    if (!S.lab) return;
    const store = S.lab.store, prof = editingProfile(), list = $('profile-list');
    list.replaceChildren();
    for (const ctx of ['control', 'slides', 'canvas', 'music']) {
      list.append(el('li', 'eyebrow', CONTEXT_PT[ctx]));
      for (const p of profilesFor(ctx)) {
        const li = el('li'), b = el('button'); b.type = 'button';
        b.setAttribute('aria-pressed', String(p.id === S.editing));
        const name = el('span', '', p.name), tag = el('small', '', store.active[ctx] === p.id ? 'ATIVO' : p.builtin ? 'FÁBRICA' : '');
        b.append(name, tag);
        b.addEventListener('click', async () => { S.editing = p.id; if (store.active[ctx] !== p.id) await lab('profile_activate', {context: ctx, id: p.id}).catch(() => {}); renderControl(); });
        li.append(b); list.append(li);
      }
    }
    if (!prof) return;
    $('profile-name').textContent = `${prof.name} · ${CONTEXT_PT[prof.context]}`;
    $('profile-reset').hidden = !prof.builtin; $('profile-delete').hidden = !!prof.builtin;
    $('profile-name-field').hidden = !!prof.builtin;
    if (document.activeElement !== $('profile-name-input')) $('profile-name-input').value = prof.name;
    const allowed = S.lab.catalog.filter(a => a.contexts.includes(prof.context));
    const body = $('bindings-body');
    const bodySig = JSON.stringify(prof.bindings) + store.settings.driver;
    if (body.dataset.profile !== prof.id || body.dataset.sig !== bodySig) {
      body.dataset.profile = prof.id; body.dataset.sig = bodySig;
      body.replaceChildren(...TRIGGERS.map(trigger => {
        const info = TRIGGER_INFO[trigger], tr = el('tr', 'binding-row'); tr.dataset.trigger = trigger;
        const t = el('td'), tw = el('div', 'trigger'), g = el('span', 'trigger-glyph ' + info.kind, info.glyph), tx = el('div');
        tw.title = info.hint;
        tx.append(document.createTextNode(info.name), el('small', '', info.kind === 'ir' ? 'IR · direto' : 'ultrassom · ' + IL.srcName(S.lab.store.settings.driver)));
        tw.append(g, tx); t.append(tw);
        const src = el('td'); src.setAttribute('aria-hidden', 'true'); src.append(el('span', 'wire'));
        const sel = el('select'); sel.add(new Option('— nenhuma —', ''));
        for (const kind of ['system', 'internal', 'external']) {
          const group = allowed.filter(a => a.kind === kind); if (!group.length) continue;
          const og = document.createElement('optgroup'); og.label = {system: 'MotionLab', internal: 'Módulo', external: 'Sistema (teclas)'}[kind];
          for (const a of group) og.append(new Option(a.label, a.id)); sel.append(og);
        }
        sel.value = prof.bindings[trigger] || '';
        sel.addEventListener('change', () => saveBinding(prof, trigger, sel.value));
        const a = el('td'); a.append(sel);
        const test = el('td'), tb = el('button', 'btn ghost small', 'Testar'); tb.type = 'button';
        tb.addEventListener('click', () => { const id = sel.value; if (!id) return; testAction(id); });
        test.append(tb);
        tr.append(t, src, a, test); return tr;
      }));
    }
    renderSafety();
    renderActivity();
  }
  async function saveBinding(prof, trigger, action) {
    const bindings = {...prof.bindings}; if (action) bindings[trigger] = action; else delete bindings[trigger];
    try { await lab('profile_save', {profile: {...prof, bindings}}); $('bindings-status').textContent = 'Salvo.'; } catch (_) { renderControl(); }
  }
  async function testAction(id) {
    const spec = S.catalog[id];
    if (spec && spec.kind === 'internal' && !spec.contexts.includes('control')) { toast(`Abra ${CONTEXT_PT[spec.contexts[0]]} para ver esta ação.`, 'info'); return; }
    try { await lab('test_action', {action: id}); toast(`Ação enviada: ${spec ? spec.label : id}`, 'info'); } catch (_) {}
  }
  $('profile-new').addEventListener('click', async () => {
    const base = editingProfile(); if (!base) return;
    const id = 'custom-' + Date.now().toString(36);
    await lab('profile_save', {profile: {id, name: `Cópia de ${base.name}`.slice(0, 40), context: base.context, bindings: base.bindings}}).catch(() => {});
    S.editing = id; renderControl();
  });
  $('profile-reset').addEventListener('click', () => { const p = editingProfile(); if (p) lab('profile_reset', {id: p.id}).catch(() => {}); });
  $('profile-delete').addEventListener('click', () => { const p = editingProfile(); if (p && confirm(`Apagar o perfil “${p.name}”?`)) lab('profile_delete', {id: p.id}).then(() => { S.editing = null; renderControl(); }).catch(() => {}); });
  $('profile-name-input').addEventListener('change', e => { const p = editingProfile(); if (p && !p.builtin && e.target.value.trim()) lab('profile_save', {profile: {...p, name: e.target.value.trim()}}).catch(() => {}); });

  const SLIDERS = [
    ['min-confidence', 'min_confidence', v => v.toLocaleString('pt-BR', {minimumFractionDigits: 2})],
    ['cooldown', 'cooldown_ms', v => `${v} ms`], ['far', 'far_cm', v => `${v} cm`], ['near', 'near_cm', v => `${v} cm`],
    ['ir-hold', 'ir_hold_ms', v => `${v} ms`],
  ];
  const sliderTimers = {};
  for (const [id, keyName, fmt] of SLIDERS) {
    $(id).addEventListener('input', e => {
      const value = Number(e.target.value); $(id + '-out').textContent = fmt(value);
      clearTimeout(sliderTimers[id]);
      sliderTimers[id] = setTimeout(() => lab('settings', {changes: {[keyName]: value}}).catch(() => renderSafety(true)), 250);
    });
  }
  $('repeat-lock').addEventListener('change', e => lab('settings', {changes: {repeat_lock: e.target.checked}}).catch(() => {}));
  $('external').addEventListener('click', () => {
    const on = $('external').getAttribute('aria-checked') === 'true';
    lab('external', {value: !on}).catch(() => {});
  });
  function renderSafety(force) {
    const s = S.lab.store.settings;
    for (const [id, keyName, fmt] of SLIDERS) {
      if (document.activeElement === $(id) && !force) continue;
      $(id).value = s[keyName]; $(id + '-out').textContent = fmt(s[keyName]);
    }
    $('repeat-lock').checked = !!s.repeat_lock;
    const ext = $('external'); ext.setAttribute('aria-checked', String(!!S.lab.external_enabled)); ext.disabled = !S.lab.external_available;
    $('external-reason').hidden = S.lab.external_available; $('external-reason').textContent = S.lab.external_reason || '';
  }
  function renderActivity() {
    const list = $('activity'); if (!list) return;
    const rows = S.events.filter(e => e.gesture && !['IR_ON', 'IR_OFF'].includes(e.gesture) && e.status !== 'observed').slice(-30).reverse();
    const sig = rows.length ? rows[0].id + ':' + rows.length : '0';
    if (list.dataset.sig === sig) return; list.dataset.sig = sig;
    list.replaceChildren(...rows.map(e => {
      const li = el('li'), info = TRIGGER_INFO[e.gesture] || {name: e.gesture};
      li.append(el('span', 't', (e.t / 1000).toFixed(1) + ' s'), el('span', 'src ' + e.source, IL.srcName(e.source)),
        el('span', 'what', info.name + (e.action ? ' → ' + ((S.catalog[e.action] || {}).label || e.action) : '')),
        el('span', 'out ' + e.status, e.status === 'rejected' ? IL.reasonText(e.reason) : e.status === 'dispatched' ? 'enviado' : 'executado'));
      return li;
    }));
  }
  function flashBinding(trigger) {
    const row = document.querySelector(`.binding-row[data-trigger="${trigger}"]`); if (!row) return;
    row.classList.remove('flash'); void row.offsetWidth; row.classList.add('flash');
  }

  // ================================================================== Air Slides
  const DECK = [
    {eyebrow: 'MotionLab · 01', title: 'Dois sensores, uma plataforma.', body: 'Um ultrassom mede a distância da mão; um infravermelho percebe toques curtos e longos. Isso basta para controle, arte e música.'},
    {eyebrow: 'Arquitetura · 02', title: 'Do sensor à ação, em camadas.', list: ['ESP32 adquire a 70 ms e roda TinyML', 'Host compara regras e ML na mesma janela', 'Um portão de segurança decide se a ação sai', 'Módulos consomem eventos, não leituras cruas']},
    {eyebrow: 'Controle contínuo · 03', title: 'Nem tudo precisa de ML.', body: 'A nota musical e a energia das partículas seguem a distância diretamente. Classificar isso com ML só acrescentaria latência.'},
    {eyebrow: 'Gestos · 04', title: 'Aproximar, afastar, segurar.', body: 'Três gestos 1D reconhecidos por regras, por um MLP no host e pelo mesmo modelo embarcado na ESP32. Você escolhe qual fonte comanda.'},
    {eyebrow: 'Segurança · 05', title: 'Nenhuma ação por acidente.', list: ['Gestos começam pausados e pausam ao desconectar', 'Confiança mínima, cooldown e trava de repetição', 'Teclas do sistema só de uma lista fechada', 'Limite rígido de 8 teclas a cada 10 s']},
    {eyebrow: 'Avaliação · 06', title: 'Métrica só com dado real.', body: 'O modelo atual foi treinado com dados sintéticos. A coleta guiada grava sessões reais; o F1-macro e a matriz de confusão saem só delas.'},
    {eyebrow: 'Próximo passo · 07', title: 'O próximo movimento é seu.', body: 'Avance com a mão, volte afastando, ou toque no IR. Com “Apresentação externa”, os mesmos gestos passam slides no PowerPoint.'},
  ];
  function renderSlide(direction) {
    const s = DECK[S.slide], node = $('slide');
    const draw = () => {
      node.replaceChildren(el('span', 's-index', String(S.slide + 1).padStart(2, '0')), el('h2', '', s.title), el('span', 's-eyebrow', s.eyebrow.replace(/\s*·\s*\d+$/, '')));
      if (s.body) node.append(el('p', '', s.body));
      if (s.list) { const ul = el('ul'); for (const item of s.list) ul.append(el('li', '', item)); node.append(ul); }
      node.className = 'slide';
    };
    if (direction) { node.className = 'slide ' + (direction > 0 ? 'out-left' : 'out-right'); setTimeout(draw, 180); } else draw();
    $('slide-count').textContent = `${S.slide + 1} / ${DECK.length}`;
    $('slide-progress').style.width = `${100 * (S.slide + 1) / DECK.length}%`;
    const dots = $('slide-dots');
    if (dots.children.length !== DECK.length) dots.replaceChildren(...DECK.map(() => el('i')));
    [...dots.children].forEach((d, i) => d.classList.toggle('on', i === S.slide));
    $('deck').dataset.blank = String(S.slidesBlank);
  }
  function slideGo(delta) {
    const next = Math.max(0, Math.min(DECK.length - 1, S.slide + delta));
    S.slidesBlank = false;
    const flash = $('slide-flash'); flash.className = 'slide-flash'; void flash.offsetWidth;
    flash.className = 'slide-flash ' + (delta > 0 ? 'next' : 'prev'); flash.textContent = delta > 0 ? '›' : '‹';
    if (next !== S.slide) { S.slide = next; renderSlide(delta); } else renderSlide();
  }
  function slidesAction(action) {
    if (action === 'slides.next') slideGo(1);
    else if (action === 'slides.prev') slideGo(-1);
    else if (action === 'slides.blank') { S.slidesBlank = !S.slidesBlank; renderSlide(); }
  }
  function renderSlidesMap() {
    if (!S.lab) return;
    const active = S.lab.store.active.slides, prof = S.lab.store.profiles.find(p => p.id === active);
    for (const b of document.querySelectorAll('[data-slides-target]')) b.setAttribute('aria-checked', String(b.dataset.slidesTarget === active));
    $('slides-external-help').hidden = !(prof && Object.values(prof.bindings).some(a => a.startsWith('present.')));
    const map = $('slides-map'); map.replaceChildren();
    if (prof) for (const t of TRIGGERS) if (prof.bindings[t]) { const pill = el('span', 'map-pill'); pill.title = TRIGGER_INFO[t].name; pill.append(el('span', 'g', TRIGGER_INFO[t].glyph), el('b', '', (S.catalog[prof.bindings[t]] || {}).label || prof.bindings[t])); map.append(pill); }
  }
  for (const b of document.querySelectorAll('[data-slides-target]')) b.addEventListener('click', () => lab('profile_activate', {context: 'slides', id: b.dataset.slidesTarget}).then(renderSlidesMap).catch(() => {}));
  $('slide-prev').addEventListener('click', () => slideGo(-1));
  $('slide-next').addEventListener('click', () => slideGo(1));
  $('slide-full').addEventListener('click', () => { const d = $('deck'); (document.fullscreenElement ? document.exitFullscreen() : d.requestFullscreen()).catch(() => {}); });
  $('deck').addEventListener('keydown', e => { if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); slideGo(1); } if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); slideGo(-1); } });

  // ================================================================== Motion Canvas
  const demoSignal = new CL.DemoSignal();
  let canvasApp = null;
  function ensureCanvas() {
    if (canvasApp) return canvasApp;
    canvasApp = new CL.MotionCanvas($('art'));
    canvasApp.onStats = ({fps, count}) => { $('canvas-fps').textContent = `${fps} fps`; $('canvas-count').textContent = count ? `${count} partículas` : 'vetorial'; };
    new ResizeObserver(() => canvasApp.resize()).observe($('canvas-stage'));
    renderCanvasHud(); return canvasApp;
  }
  function renderCanvasHud() {
    if (!canvasApp) return;
    for (const b of document.querySelectorAll('[data-style]')) b.setAttribute('aria-pressed', String(b.dataset.style === canvasApp.style.id));
    $('canvas-style-name').textContent = canvasApp.style.name; $('canvas-palette-name').textContent = canvasApp.palette.name;
    const freeze = $('canvas-freeze'), freezeLabel = canvasApp.frozen ? 'Descongelar' : 'Congelar';
    freeze.setAttribute('aria-pressed', String(canvasApp.frozen)); freeze.title = freezeLabel; freeze.setAttribute('aria-label', freezeLabel);
    [...$('canvas-palette').children].forEach((dot, i) => { const c = canvasApp.palette.colors[i]; dot.style.background = `rgb(${c[0]},${c[1]},${c[2]})`; });
    $('canvas-demo').setAttribute('aria-pressed', String(S.demo.canvas));
    const serverDemo = !!(S.conn && S.conn.origin === 'DEMO');
    $('canvas-demo-banner').hidden = !(S.demo.canvas || serverDemo);
    $('canvas-demo-banner').textContent = S.demo.canvas ? 'Demo · mouse ↕ · espaço = IR' : 'Demo · simulador';
    $('canvas-demo-banner').title = S.demo.canvas ? 'Sinal sintético no navegador' : 'Simulador do servidor, sem sensores físicos';
  }
  for (const b of document.querySelectorAll('[data-style]')) b.addEventListener('click', () => { ensureCanvas().setStyle(b.dataset.style); renderCanvasHud(); });
  $('canvas-palette').addEventListener('click', () => { ensureCanvas().action('canvas.next_palette'); renderCanvasHud(); });
  $('canvas-freeze').addEventListener('click', () => { ensureCanvas().action('canvas.freeze'); renderCanvasHud(); });
  $('canvas-burst').addEventListener('click', () => ensureCanvas().action('canvas.burst'));
  $('canvas-fullscreen').addEventListener('click', () => { const s = $('canvas-stage'); (document.fullscreenElement ? document.exitFullscreen() : s.requestFullscreen()).catch(() => {}); });
  $('canvas-demo').addEventListener('click', () => { S.demo.canvas = !S.demo.canvas; renderCanvasHud(); });
  $('canvas-stage').addEventListener('pointermove', e => { if (!S.demo.canvas) return; const r = $('canvas-stage').getBoundingClientRect(); demoSignal.point((e.clientY - r.top) / r.height); });
  let demoIrSince = 0;
  document.addEventListener('keydown', e => {
    if (e.code !== 'Space' || e.repeat || !((S.view === 'canvas' && S.demo.canvas) || (S.view === 'music' && S.demo.music))) return;
    e.preventDefault(); demoSignal.ir = true; demoIrSince = performance.now();
  });
  document.addEventListener('keyup', e => {
    if (e.code !== 'Space' || !demoSignal.ir) return;
    demoSignal.ir = false;
    // Na demonstração o toque curto no espaço imita o IR_TAP do perfil (sem passar pelo servidor).
    if (performance.now() - demoIrSince < 600) {
      if (S.view === 'canvas') { ensureCanvas().action('canvas.next_style'); renderCanvasHud(); }
      if (S.view === 'music') { try { ensureMusic().action('music.toggle_record'); } catch (error) { toast(error.message); } renderMusic(); }
    }
  });

  // ================================================================== Air Music
  let musicApp = null;
  function ensureMusic() {
    if (musicApp) return musicApp;
    musicApp = new ML.AirMusic(); musicApp.onChange = renderMusic;
    const scale = $('scale'), root = $('root');
    for (const [id, s] of Object.entries(ML.SCALES)) scale.add(new Option(s.name, id));
    for (let m = 48; m <= 64; m++) root.add(new Option(ML.noteName(m), String(m)));
    scale.value = musicApp.scale; root.value = String(musicApp.root);
    $('timbres').replaceChildren(...ML.TIMBRES.map(t => { const b = el('button', 'chip', t.name); b.type = 'button'; b.dataset.timbre = t.id; b.addEventListener('click', () => musicApp.setTimbre(t.id)); return b; }));
    return musicApp;
  }
  function renderMusic() {
    const m = ensureMusic();
    $('audio-toggle').textContent = m.enabled ? 'Desativar áudio' : 'Ativar áudio';
    $('audio-toggle').classList.toggle('primary', !m.enabled);
    for (const b of document.querySelectorAll('[data-timbre]')) b.setAttribute('aria-pressed', String(b.dataset.timbre === m.timbre));
    $('music-note').textContent = m.muted ? 'mudo' : ML.noteName(m.current);
    $('music-freq').textContent = m.current === null ? '— Hz' : `${ML.midiToFreq(m.current).toFixed(1)} Hz`;
    $('music-gate').textContent = m.current === null ? 'Sem mão' : 'Tocando';
    const rec = $('loop-record'); rec.setAttribute('aria-pressed', String(!!m.recording)); rec.textContent = m.recording ? 'Parar gravação' : 'Gravar';
    $('loop-play').textContent = m.playing ? 'Pausar loops' : 'Tocar loops'; $('loop-play').disabled = !m.layers.length;
    $('loop-undo').disabled = !m.layers.length && !m.recording;
    $('looper-state').textContent = m.recording ? `Gravando camada ${m.layers.length + 1}` : m.playing ? `Tocando ${m.layers.length} camada(s)` : m.layers.length ? 'Pausado' : 'Vazio';
    $('bpm').disabled = $('bars').disabled = m.layers.length > 0 || !!m.recording;
    const layers = $('layers');
    if (!m.layers.length) layers.replaceChildren(el('li', 'empty', 'Nenhuma camada. Ative o áudio, toque e grave com o IR ou o botão.'));
    else layers.replaceChildren(...m.layers.map((l, i) => {
      const li = el('li'), b = el('button', '', l.muted ? 'mudo' : 'som'); b.type = 'button'; b.setAttribute('aria-pressed', String(l.muted));
      b.addEventListener('click', () => m.toggleLayer(i));
      const notes = l.events.filter(e => e.midi !== null).length;
      li.append(el('span', 'n', String(i + 1)), el('span', '', ML.TIMBRES.find(t => t.id === l.timbre).name), el('span', 'meta', `${notes} notas · ${l.length.toFixed(1)} s`), b);
      return li;
    }));
    $('music-demo-toggle').setAttribute('aria-pressed', String(S.demo.music)); $('music-demo').hidden = !S.demo.music;
  }
  $('audio-toggle').addEventListener('click', async () => { const m = ensureMusic(); try { m.enabled ? m.disable() : await m.enable(); } catch (error) { toast(error.message); } renderMusic(); });
  $('scale').addEventListener('change', e => { ensureMusic().scale = e.target.value; });
  $('root').addEventListener('change', e => { ensureMusic().root = Number(e.target.value); });
  const MUSIC_SLIDERS = [['octaves', 'octaves', v => `${v} oitava${v > 1 ? 's' : ''}`], ['volume', 'volume', v => `${Math.round(v * 100)}%`], ['brightness', 'brightness', v => `${Math.round(v * 100)}%`], ['echo', 'echo', v => `${Math.round(v * 100)}%`], ['space', 'space', v => `${Math.round(v * 100)}%`]];
  for (const [id, prop, fmt] of MUSIC_SLIDERS) $(id).addEventListener('input', e => { const m = ensureMusic(), v = Number(e.target.value); m[prop] = v; $(id + '-out').textContent = fmt(v); m.applyMix(); });
  $('bpm').addEventListener('change', e => { ensureMusic().bpm = Number(e.target.value); musicApp.applyMix(); });
  $('bars').addEventListener('change', e => { ensureMusic().bars = Number(e.target.value); });
  $('loop-record').addEventListener('click', () => { try { ensureMusic().action('music.toggle_record'); } catch (error) { toast(error.message); } renderMusic(); });
  $('loop-play').addEventListener('click', () => ensureMusic().togglePlay());
  $('loop-undo').addEventListener('click', () => ensureMusic().undo());
  $('music-demo-toggle').addEventListener('click', () => { S.demo.music = !S.demo.music; renderMusic(); });
  $('pitch-canvas').addEventListener('pointermove', e => { if (!S.demo.music) return; const r = $('pitch-canvas').getBoundingClientRect(); demoSignal.point(1 - (e.clientX - r.left) / r.width); });

  function drawPitch(input) {
    const m = ensureMusic(), {ctx, w, h, dpr} = fitCanvas($('pitch-canvas')), notes = m.notes, n = notes.length;
    ctx.clearRect(0, 0, w, h);
    const base = h - 30 * dpr, colW = w / n;
    ctx.strokeStyle = C.line2; ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(0, base + 0.5); ctx.lineTo(w, base + 0.5); ctx.stroke();
    ctx.textAlign = 'center';
    notes.forEach((note, i) => {
      const x = i * colW + colW / 2, active = note === m.current, isRoot = (note - m.root) % 12 === 0;
      if (active) {
        const g = ctx.createLinearGradient(0, base, 0, 0); g.addColorStop(0, 'rgba(124,201,192,0.30)'); g.addColorStop(1, 'rgba(124,201,192,0)');
        ctx.fillStyle = g; ctx.fillRect(x - colW * 0.42, 0, colW * 0.84, base);
      }
      ctx.strokeStyle = active ? C.ultra : isRoot ? C.ink3 : C.ink4; ctx.lineWidth = (active ? 2 : 1) * dpr;
      const tick = active ? base * 0.9 : isRoot ? base * 0.32 : base * 0.16;
      ctx.beginPath(); ctx.moveTo(x, base); ctx.lineTo(x, base - tick); ctx.stroke();
      ctx.fillStyle = active ? C.ink : isRoot ? C.ink2 : C.ink3; ctx.font = `${active ? 500 : 400} ${10.5 * dpr}px ${C.mono}`;
      ctx.fillText(ML.noteName(note), x, base + 19 * dpr);
      m.layers.forEach((l, k) => {
        if (!(m.playing && !l.muted && l.voice.midi === note)) return;
        ctx.fillStyle = LAYER_COLORS[k]; ctx.beginPath(); ctx.arc(x, base - tick - (10 + 9 * k) * dpr, 3 * dpr, 0, Math.PI * 2); ctx.fill();
      });
    });
    if (input.position !== null && input.position !== undefined) {
      const x = (1 - input.position) * w;
      ctx.strokeStyle = input.ir ? C.ir : 'rgba(236,235,230,0.85)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, base); ctx.stroke();
      ctx.fillStyle = input.ir ? C.ir : C.ink; ctx.beginPath(); ctx.arc(x, base, 3.5 * dpr, 0, Math.PI * 2); ctx.fill();
    } else {
      ctx.fillStyle = C.ink3; ctx.font = `500 ${10.5 * dpr}px ${C.mono}`;
      ctx.fillText(input.stale && !S.demo.music ? 'SEM SINAL · CONECTE A ESP32 OU USE DEMO' : 'APROXIME A MÃO · PERTO = AGUDO', w / 2, base * 0.45);
    }
  }
  function drawLoopRing() {
    const m = ensureMusic(), {ctx, w, dpr} = fitCanvas($('loop-ring')), cx = w / 2, R = w / 2 - 8 * dpr;
    ctx.clearRect(0, 0, w, w);
    ctx.strokeStyle = C.line2; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(cx, cx, R, 0, Math.PI * 2); ctx.stroke();
    const beats = (m.bars || 2) * 4;
    for (let b = 0; b < beats; b++) {
      const a = -Math.PI / 2 + 2 * Math.PI * b / beats, len = (b % 4 === 0 ? 7 : 3.5) * dpr;
      ctx.strokeStyle = b % 4 === 0 ? C.ink3 : C.ink4;
      ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * R, cx + Math.sin(a) * R); ctx.lineTo(cx + Math.cos(a) * (R - len), cx + Math.sin(a) * (R - len)); ctx.stroke();
    }
    ctx.lineCap = 'round';
    m.layers.forEach((l, i) => {
      const rr = R - (18 + i * 11) * dpr;
      ctx.strokeStyle = C.line; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(cx, cx, rr, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = l.muted ? C.ink4 : LAYER_COLORS[i]; ctx.lineWidth = 3 * dpr;
      for (let k = 0; k < l.events.length; k++) {
        const e = l.events[k]; if (e.midi === null) continue;
        const end = k + 1 < l.events.length ? l.events[k + 1].t : l.length;
        ctx.beginPath(); ctx.arc(cx, cx, rr, -Math.PI / 2 + 2 * Math.PI * e.t / l.length, -Math.PI / 2 + 2 * Math.PI * end / l.length); ctx.stroke();
      }
    });
    ctx.lineCap = 'butt';
    const p = m.position();
    if (p !== null) {
      const a = -Math.PI / 2 + 2 * Math.PI * p;
      ctx.fillStyle = m.recording ? C.bad : C.ink; ctx.beginPath(); ctx.arc(cx + Math.cos(a) * R, cx + Math.sin(a) * R, 4 * dpr, 0, Math.PI * 2); ctx.fill();
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = m.recording ? C.bad : C.ink; ctx.font = `300 ${26 * dpr}px ${C.num}`;
    ctx.fillText(m.recording ? 'REC' : `${m.layers.length}/4`, cx, cx - 2 * dpr);
    ctx.fillStyle = C.ink3; ctx.font = `500 ${8.5 * dpr}px ${C.mono}`;
    ctx.fillText(m.playing ? 'TOCANDO' : 'CAMADAS', cx, cx + 20 * dpr);
    ctx.textBaseline = 'alphabetic';
  }

  // ================================================================== Intelligence
  const collectUI = {start: $('record-start'), stop: $('record-stop'), prompt: $('collect-prompt'), participant: $('participant'), repeats: $('repeats'),
    label: $('prompt-label'), text: $('prompt-text'), bar: $('prompt-bar'), meta: $('prompt-meta'), result: $('collect-result'), sessions: $('collect-sessions')};
  function renderIntel() {
    if (!S.lab) return;
    IL.renderRecognizers($('recognizers'), S.lab);
    IL.renderFlow($('intel-flow'), S.lab, S.live);
    IL.renderRejections($('intel-rejections'), S.lab);
    IL.renderCollect(collectUI, S.live ? S.live.recording : S.lab.recording, S.lab.sessions);
  }
  async function evaluate() {
    try { const result = await api('/api/lab', {cmd: 'evaluate'}); S.evaluation = result.lab; IL.renderEvaluation($('eval-real'), $('eval-synthetic'), S.evaluation); }
    catch (error) { toast(error.message); }
  }
  $('evaluate').addEventListener('click', evaluate);
  $('record-start').addEventListener('click', () => lab('record_start', {participant: $('participant').value.trim(), repeats: Number($('repeats').value)}).catch(() => {}));
  $('record-stop').addEventListener('click', () => lab('record_stop').catch(() => {}));

  // ================================================================== Intelligence · níveis e serviço ML
  /* Leituras acadêmicas têm ritmo próprio: status e previsões a cada 10 s, avaliações a cada 60 s,
     só com a tela visível; em falha, só o status é consultado, a cada 30 s. Nada disso entra no polling de 70 ms. */
  const MLX = IL.ML, ML_FAST = 10000, ML_SLOW = 60000, ML_BACKOFF = 30000;
  const MLS = {level: 'live', res: {}, data: {}, okAt: {}, triedAt: {}, busy: false, cohort: null, focus: null, query: null};
  try { const saved = sessionStorage.getItem('motionlab.intel.level'); if (['live', 'models', 'inference'].includes(saved)) MLS.level = saved; } catch (_) {}
  async function mlFetch(path, body) {
    const options = {headers: {'X-MotionPet-Key': key()}, cache: 'no-store'};
    if (body !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    try {
      const response = await fetch(path, options);
      let data = null; try { data = await response.json(); } catch (_) {}
      return {code: response.status, data};
    } catch (_) { return {code: 0, data: null, net: true}; }
  }
  async function mlPoll(force) {
    if (MLS.busy || S.view !== 'intelligence' || document.hidden) return;
    const now = Date.now(), failing = !!(MLS.res.status && MLS.res.status.code !== 200);
    const fastEvery = failing ? ML_BACKOFF : ML_FAST, jobs = [];
    if (force || now - (MLS.triedAt.status || 0) >= fastEvery) jobs.push('status', 'predictions');
    if (force || now - (MLS.triedAt.evaluations || 0) >= (MLS.data.evaluations && !failing ? ML_SLOW : fastEvery)) jobs.push('evaluations');
    if (!jobs.length) return;
    MLS.busy = true;
    try {
      // Serviço fora do ar: só o status é consultado até ele voltar (sem rajadas de 503).
      const run = failing && !force ? ['status'] : [...new Set(jobs)];
      await Promise.all(run.map(async name => {
        MLS.triedAt[name] = Date.now();
        const res = await mlFetch('/api/ml/' + name);
        MLS.res[name] = res;
        if (res.code === 200 && res.data) { MLS.data[name] = res.data; MLS.okAt[name] = Date.now(); }
      }));
      // Voltou depois de uma falha: completa as outras leituras na mesma rodada.
      if (failing && !force && MLS.res.status.code === 200) { MLS.busy = false; await mlPoll(true); return; }
    } finally { MLS.busy = false; }
    renderMl();
  }
  function mlStale(name, every) { return !!(MLS.okAt[name] && MLS.res[name] && (MLS.res[name].code !== 200 || Date.now() - MLS.okAt[name] > every * 3)); }
  function setLevel(level) {
    MLS.level = level;
    try { sessionStorage.setItem('motionlab.intel.level', level); } catch (_) {}
    for (const b of document.querySelectorAll('.intel-levels .level')) b.setAttribute('aria-pressed', String(b.dataset.level === level));
    for (const n of document.querySelectorAll('#view-intelligence [data-level]:not(button)')) n.hidden = n.dataset.level !== level;
    renderMl();
    if (Date.now() - (MLS.triedAt.status || 0) > 3000) mlPoll(true);
  }
  for (const b of document.querySelectorAll('.intel-levels .level')) b.addEventListener('click', () => setLevel(b.dataset.level));
  $('ml-service').addEventListener('click', () => mlPoll(true));

  function renderMl() {
    const view = MLX.serviceView(MLS.res.status), status = view.state === 'off' ? null : MLS.data.status || null;
    const staleStatus = mlStale('status', ML_FAST), now = Date.now();
    MLX.renderService($('ml-service'), view, MLS.okAt.status ? now - MLS.okAt.status : null, staleStatus);
    const evals = view.state === 'off' ? null : MLS.data.evaluations || null, preds = view.state === 'off' ? null : MLS.data.predictions || null;
    const cohort = MLX.pickCohort(evals, MLS.cohort, status && status.training_cohort);
    const entry = cohort ? evals[cohort] : null;
    // Resumo de cada nível, sempre visível no seletor.
    const origin = S.conn && S.conn.origin, fresh = !!(S.live && S.live.age_ms !== null && S.live.age_ms < 1000);
    $('level-state-live').textContent = fresh ? (origin === 'DEMO' ? 'demonstração · ao vivo' : 'ESP32 · ao vivo') : 'sem sinal';
    $('level-state-live').dataset.on = String(fresh);
    $('level-state-models').textContent = !evals ? view.label.toLowerCase() : entry ? `${MLX.modelName(entry.selected_model)} · ${MLX.provOf(cohort).text.toLowerCase()}` : 'avaliações pendentes';
    const items = MLX.sortedPredictions(preds);
    $('level-state-inference').textContent = items.length ? `${items.length} sessões · última ${new Date(items[0].generated_at_iso).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'})}` : preds ? 'nenhuma sessão processada' : view.label.toLowerCase();
    const okIso = MLS.okAt.status ? new Date(MLS.okAt.status).toLocaleTimeString('pt-BR') : '';
    if (MLS.level === 'models') {
      const stale = staleStatus || mlStale('evaluations', ML_SLOW);
      MLX.renderNotice($('ml-notice-models'), view, stale, okIso);
      $('ml-models').dataset.stale = String(stale);
      MLX.renderPublished($('ml-published'), status, view);
      MLX.renderHeadline($('ml-headline'), entry, cohort, !!evals);
      MLX.renderCohorts($('ml-cohorts'), evals, cohort, c => { MLS.cohort = c; MLS.focus = null; renderMl(); });
      const published = status && status.status === 'ready' && entry && status.experiment_id === entry.experiment_id ? status.model_name : null;
      if (entry && entry.metrics) {
        if (!MLS.focus || !(MLS.focus in entry.metrics)) MLS.focus = published || entry.selected_model;
        MLX.renderCompare($('ml-compare'), entry, MLS.focus, published, name => { MLS.focus = name; renderMl(); });
        const sp = entry.split || {};
        $('ml-split').textContent = `Grupos por participante — treino ${(sp.train_groups || []).join(', ') || '—'} · validação ${(sp.validation_groups || []).join(', ') || '—'} · teste reservado ${(sp.test_groups || []).join(', ') || '—'}. A CV usa só o desenvolvimento; o teste reservado não escolhe modelo.`;
      } else {
        const pend = document.createElement('div'); pend.className = 'pending';
        pend.textContent = evals ? 'Nenhum experimento completo: a comparação aparece quando houver avaliação, sem valores estimados.' : view.state === 'ok' || view.state === 'idle' ? 'Aguardando a leitura das avaliações.' : view.detail;
        $('ml-compare').replaceChildren(pend); $('ml-split').textContent = '';
      }
      $('ml-focus').hidden = !(entry && entry.metrics);
      MLX.renderFocus($('ml-focus'), entry, MLS.focus, published);
      MLX.renderTuning($('ml-tuning'), entry && entry.tuning);
      MLX.renderPipeline($('ml-pipeline'), entry, status, view, $('ml-pipeline-title'), cohort);
    }
    if (MLS.level === 'inference') {
      const stale = staleStatus || mlStale('predictions', ML_FAST);
      MLX.renderNotice($('ml-notice-inference'), view, stale, okIso);
      $('ml-inference').dataset.stale = String(stale);
      MLX.renderInfLatest($('inf-latest'), preds, status, view);
      MLX.renderLedger($('inf-ledger'), preds);
      renderInfLive();
      MLX.renderQuery($('inf-query-result'), MLS.query);
    }
  }
  function renderInfLive() {
    const origin = S.conn && S.conn.origin, fresh = !!(S.live && S.live.age_ms !== null && S.live.age_ms < 1000);
    MLX.renderInfLive($('inf-live'), S.events, origin, fresh);
    const ready = !!(MLS.data.status && MLS.data.status.status === 'ready' && MLX.serviceView(MLS.res.status).state === 'ok');
    const inputOrigin = MLX.inferOrigin(origin), samples = fresh && inputOrigin ? MLX.samplesFromFrames(S.frames) : null;
    $('inf-query').disabled = !ready || !samples || !!(MLS.query && MLS.query.busy);
    const svc = MLX.serviceView(MLS.res.status).state;
    $('inf-query-note').textContent = !ready ? (svc === 'off' || svc === 'bad' ? 'requer o serviço ML' : 'requer modelo publicado') : !inputOrigin || !fresh ? 'requer sinal ao vivo' : !samples ? 'aguardando 10 amostras' : `${samples.length} amostras · entrada ${MLX.provOf(inputOrigin).text.toLowerCase()}`;
  }
  $('inf-query').addEventListener('click', async () => {
    const inputOrigin = MLX.inferOrigin(S.conn && S.conn.origin), samples = MLX.samplesFromFrames(S.frames);
    if (!inputOrigin || !samples) return;
    MLS.query = {busy: true}; renderMl();
    const res = await mlFetch('/api/ml/infer', {schema_version: 1, input_origin: inputOrigin, samples});
    const at = new Date().toLocaleTimeString('pt-BR');
    if (res.code === 200 && res.data && res.data.label) MLS.query = {result: res.data, samples: samples.length, at};
    else {
      const err = res.data && res.data.error, msg = res.data && res.data.message;
      MLS.query = {error: res.net ? 'Sem comunicação com o servidor local.' : res.code === 400 ? `Requisição recusada: ${String(msg || 'entrada inválida').replace(/\.$/, '')}.` : res.code === 413 ? 'Janela grande demais para o serviço (limite 64 KiB).'
        : res.code === 403 ? 'Chave local expirada: recarregue a página.' : err === 'model_pending' ? 'Modelo pendente: nenhuma classificação foi feita.' : err === 'ml_service_not_configured' ? 'Serviço ML não configurado neste painel.' : 'Serviço ML indisponível: nenhuma classificação foi feita.'};
    }
    renderMl();
  });
  setInterval(() => {
    mlPoll(false);
    if (S.view === 'intelligence') MLX.renderService($('ml-service'), MLX.serviceView(MLS.res.status), MLS.okAt.status ? Date.now() - MLS.okAt.status : null, mlStale('status', ML_FAST));
  }, 2000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) mlPoll(false); });
  let mlResizeRaf = 0, mlWidth = 0;
  if (typeof ResizeObserver === 'function') new ResizeObserver(entries => {
    const w = Math.round(entries[0].contentRect.width); if (w === mlWidth) return; mlWidth = w;
    cancelAnimationFrame(mlResizeRaf); mlResizeRaf = requestAnimationFrame(() => { if (S.view === 'intelligence' && MLS.level === 'models') renderMl(); });
  }).observe($('ml-compare'));

  // ================================================================== laço de animação
  let lastIntelDraw = 0, lastRecording = false;
  function frame(now) {
    drawStrip();
    if (S.view === 'home') drawHomeField(now);
    if (S.view === 'canvas' && canvasApp) {
      const input = currentInput('canvas'); canvasApp.setInput(input);
      $('canvas-empty').hidden = !(input.stale && !S.demo.canvas);
      if (now - (S._hudAt || 0) > 1000) { S._hudAt = now; renderCanvasHud(); }
    }
    if (S.view === 'music') { const m = ensureMusic(), input = currentInput('music'); m.input(input); drawPitch(input); drawLoopRing(); }
    if (S.view === 'intelligence' && MLS.level === 'live' && now - lastIntelDraw > 66) {
      lastIntelDraw = now;
      IL.drawChart($('intel-chart'), S.frames, S.events, S.lab && S.lab.store.settings);
      if (now - S.lastHistoryRender > 400) { S.lastHistoryRender = now; IL.renderHistory($('intel-history'), S.events); }
    }
    if (S.view === 'intelligence' && MLS.level === 'inference' && now - lastIntelDraw > 400) { lastIntelDraw = now; renderInfLive(); }
    const recording = !!(S.live && S.live.recording && S.live.recording.active);
    if (lastRecording && !recording && S.view === 'intelligence') labLoopOnce();
    lastRecording = recording;
    requestAnimationFrame(frame);
  }
  async function labLoopOnce() { try { applyLab(await api('/api/lab')); } catch (_) {} }
  document.addEventListener('visibilitychange', () => { if (!musicApp) return; document.hidden ? musicApp.pause() : musicApp.resume(); });

  // ================================================================== início
  api('/api/experience', {value: 'lab'}).catch(() => {});
  setView(location.hash.slice(1) || 'home');
  renderSlide();
  loadPorts(); liveLoop(); labLoop();
  requestAnimationFrame(frame);
})();
