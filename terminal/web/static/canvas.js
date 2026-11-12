'use strict';
/* Motion Canvas — arte generativa controlada pela distância (canal contínuo) e pelo IR.
   Canvas 2D com composição aditiva: sem dependências, compatível com a CSP do app, e com
   contagem de partículas ajustada ao FPS medido. O sinal chega a ~14 Hz; uma mola criticamente
   amortecida interpola a posição a 60 fps. */
(() => {
  const PALETTES = [
    {name: 'Aurora', colors: [[124, 201, 192], [122, 160, 222], [169, 156, 240], [220, 143, 176]]},
    {name: 'Brasa', colors: [[236, 205, 140], [226, 161, 92], [214, 110, 88], [150, 70, 92]]},
    {name: 'Grafite', colors: [[236, 235, 230], [190, 188, 180], [124, 201, 192], [110, 108, 102]]},
    {name: 'Líquen', colors: [[200, 214, 150], [143, 207, 157], [124, 201, 192], [226, 161, 92]]},
  ];
  const STYLES = [
    {id: 'field', name: 'Campo'}, {id: 'waves', name: 'Ondas'}, {id: 'flow', name: 'Fluxo'}, {id: 'pulse', name: 'Pulso'},
  ];
  const MAX_PARTICLES = 4200, MIN_PARTICLES = 400;

  /** Mola criticamente amortecida: segue o alvo sem overshoot (pura, testável). */
  function spring(value, velocity, target, omega, dt) {
    const x = omega * dt, exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
    const change = value - target, temp = (velocity + omega * change) * dt;
    return [target + (change + temp) * exp, (velocity - omega * temp) * exp];
  }

  function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }

  class MotionCanvas {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d', {alpha: false});
      this.styleIndex = 0; this.paletteIndex = 0;
      this.frozen = false; this.running = false;
      this.count = 1800;
      this.px = new Float32Array(MAX_PARTICLES); this.py = new Float32Array(MAX_PARTICLES);
      this.vx = new Float32Array(MAX_PARTICLES); this.vy = new Float32Array(MAX_PARTICLES);
      this.seed = new Float32Array(MAX_PARTICLES); this.life = new Float32Array(MAX_PARTICLES);
      for (let i = 0; i < MAX_PARTICLES; i++) { this.seed[i] = Math.random(); this.life[i] = Math.random() * 400; }
      this.input = {position: null, velocity: 0, ir: false};
      this.pos = 0.5; this.posVel = 0; this.presence = 0; this.irGlow = 0;
      this.rings = []; this.pulseClock = 0; this.t = 0;
      this.frameMs = 16; this.fps = 60; this._fpsAcc = 0; this._fpsN = 0; this._fpsT = 0;
      this.onStats = null;
      this._loop = this._loop.bind(this);
      this.resize();
      this.scatter();
    }
    get style() { return STYLES[this.styleIndex]; }
    get palette() { return PALETTES[this.paletteIndex]; }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = Math.max(320, Math.round(rect.width * dpr)), h = Math.max(240, Math.round(rect.height * dpr));
      if (w !== this.canvas.width || h !== this.canvas.height) {
        this.canvas.width = w; this.canvas.height = h; this.dpr = dpr;
        this.ctx.fillStyle = '#08080a'; this.ctx.fillRect(0, 0, w, h);
        this.scatter();
      }
    }
    scatter() {
      const w = this.canvas.width, h = this.canvas.height;
      for (let i = 0; i < MAX_PARTICLES; i++) {
        this.px[i] = Math.random() * w; this.py[i] = Math.random() * h; this.vx[i] = 0; this.vy[i] = 0;
      }
    }
    setInput(input) { this.input = input; }
    setStyle(id) {
      const idx = STYLES.findIndex(s => s.id === id);
      if (idx >= 0 && idx !== this.styleIndex) { this.styleIndex = idx; this._clear(); this.scatter(); }
    }
    action(name) {
      if (name === 'canvas.next_style') { this.styleIndex = (this.styleIndex + 1) % STYLES.length; this._clear(); this.scatter(); }
      else if (name === 'canvas.next_palette') this.paletteIndex = (this.paletteIndex + 1) % PALETTES.length;
      else if (name === 'canvas.freeze') this.frozen = !this.frozen;
      else if (name === 'canvas.burst') this.burst();
      else if (name === 'canvas.reset') { this.rings = []; this._clear(); this.scatter(); this.frozen = false; }
      else return false;
      return true;
    }
    burst() {
      const w = this.canvas.width, h = this.canvas.height, cx = w / 2, cy = h / 2;
      for (let i = 0; i < this.count; i++) {
        const dx = this.px[i] - cx, dy = this.py[i] - cy, d = Math.hypot(dx, dy) + 1, k = 9 * this.dpr * (0.6 + this.seed[i]);
        this.vx[i] += dx / d * k; this.vy[i] += dy / d * k;
      }
      this.rings.push({r: 10, speed: 9 * this.dpr, width: 6 * this.dpr, alpha: 1, color: 3});
    }
    _clear() { this.ctx.globalCompositeOperation = 'source-over'; this.ctx.fillStyle = '#08080a'; this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height); }
    start() { if (!this.running) { this.running = true; this._last = performance.now(); requestAnimationFrame(this._loop); } }
    stop() { this.running = false; }

    _loop(now) {
      if (!this.running) return;
      const dtMs = Math.min(50, now - this._last); this._last = now;
      this._measure(dtMs, now);
      if (!this.frozen) { this._update(dtMs / 1000); this._draw(); }
      requestAnimationFrame(this._loop);
    }
    _measure(dtMs, now) {
      this.frameMs += 0.08 * (dtMs - this.frameMs);
      this._fpsAcc += dtMs; this._fpsN++;
      if (now - this._fpsT > 1000) {
        this.fps = Math.round(1000 / (this._fpsAcc / this._fpsN)); this._fpsAcc = 0; this._fpsN = 0; this._fpsT = now;
        const particleStyle = this.style.id === 'field' || this.style.id === 'flow';
        if (particleStyle && this.frameMs > 21 && this.count > MIN_PARTICLES) this.count = Math.max(MIN_PARTICLES, Math.round(this.count * 0.85));
        else if (particleStyle && this.frameMs < 15 && this.count < MAX_PARTICLES) this.count = Math.min(MAX_PARTICLES, Math.round(this.count * 1.08));
        if (this.onStats) this.onStats({fps: this.fps, count: particleStyle ? this.count : null});
      }
    }
    _update(dt) {
      const inp = this.input, present = inp.position !== null && inp.position !== undefined;
      this.presence += ((present ? 1 : 0) - this.presence) * Math.min(1, dt * 3);
      if (present) [this.pos, this.posVel] = spring(this.pos, this.posVel, inp.position, 9, dt);
      this.irGlow += ((inp.ir ? 1 : 0) - this.irGlow) * Math.min(1, dt * 8);
      this.t += dt; this._dt = dt;
      const speed = Math.min(1, Math.abs(inp.velocity || 0) / 80);
      this.energy = this.presence * (0.25 + 0.75 * (1 - this.pos)) + 0.6 * speed * this.presence;
      for (const ring of this.rings) { ring.r += ring.speed * dt * 60; ring.alpha -= dt * 0.55; }
      this.rings = this.rings.filter(r => r.alpha > 0);
    }

    _draw() {
      const ctx = this.ctx, w = this.canvas.width, h = this.canvas.height, id = this.style.id;
      ctx.globalCompositeOperation = 'source-over';
      const trail = id === 'waves' ? 0.32 : id === 'pulse' ? 0.18 : 0.10 + 0.08 * (1 - this.energy);
      ctx.fillStyle = `rgba(8,8,10,${trail})`; ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = 'lighter';
      if (id === 'field') this._field(ctx, w, h);
      else if (id === 'flow') this._flow(ctx, w, h);
      else if (id === 'waves') this._waves(ctx, w, h);
      else this._pulse(ctx, w, h);
      this._rings(ctx, w, h);
    }
    _particles(ctx, binOf) {
      const cols = this.palette.colors, size = 1.6 * this.dpr, alpha = 0.55 + 0.35 * this.presence;
      for (let b = 0; b < 4; b++) {
        ctx.fillStyle = rgba(cols[b], alpha);
        for (let i = 0; i < this.count; i++) if (binOf(i) === b) ctx.fillRect(this.px[i], this.py[i], size, size);
      }
    }
    _field(ctx, w, h) {
      const cx = w / 2, cy = h / 2, m = Math.min(w, h);
      const radius = m * (0.10 + 0.34 * (this.presence > 0.05 ? this.pos : 0.55));
      const swirl = (0.006 + 0.03 * this.energy) * (this.irGlow > 0.5 ? -1 : 1);
      const pull = 0.0009 + 0.0035 * this.energy;
      const jitter = 0.25 * this.dpr * (0.3 + this.energy);
      for (let i = 0; i < this.count; i++) {
        const dx = this.px[i] - cx, dy = this.py[i] - cy, d = Math.hypot(dx, dy) + 0.001;
        const target = radius * (0.75 + 0.5 * this.seed[i]);
        const radial = (target - d) * pull * (this.irGlow > 0.5 ? -0.6 : 1);
        this.vx[i] = this.vx[i] * 0.94 + (dx / d) * radial * 30 - dy * swirl + (Math.random() - 0.5) * jitter;
        this.vy[i] = this.vy[i] * 0.94 + (dy / d) * radial * 30 + dx * swirl + (Math.random() - 0.5) * jitter;
        this.px[i] += this.vx[i]; this.py[i] += this.vy[i];
        if (this.px[i] < -50 || this.px[i] > w + 50 || this.py[i] < -50 || this.py[i] > h + 50) { this.px[i] = cx + (Math.random() - .5) * m * .2; this.py[i] = cy + (Math.random() - .5) * m * .2; this.vx[i] = this.vy[i] = 0; }
      }
      this._particles(ctx, i => { const s = Math.abs(this.vx[i]) + Math.abs(this.vy[i]); return s > 6 ? 3 : s > 3 ? 2 : s > 1.2 ? 1 : 0; });
    }
    _flow(ctx, w, h) {
      const scale = (0.0012 + 0.004 * (1 - this.pos)) / this.dpr, t = this.t * (0.25 + this.energy);
      const speed = this.dpr * (0.6 + 3.2 * this.energy), turb = this.irGlow > 0.5 ? 2.2 : 1;
      for (let i = 0; i < this.count; i++) {
        const x = this.px[i] * scale, y = this.py[i] * scale;
        const a = (Math.sin(x * 1.7 + t) * Math.cos(y * 1.3 - t * 0.7) + Math.sin((x + y) * 0.9 + t * 0.5)) * Math.PI * turb;
        this.vx[i] = this.vx[i] * 0.86 + Math.cos(a) * speed * 0.14 * 6;
        this.vy[i] = this.vy[i] * 0.86 + Math.sin(a) * speed * 0.14 * 6;
        this.px[i] += this.vx[i] * 0.4; this.py[i] += this.vy[i] * 0.4;
        this.life[i] -= 1;
        if (this.life[i] < 0 || this.px[i] < 0 || this.px[i] > w || this.py[i] < 0 || this.py[i] > h) {
          this.px[i] = Math.random() * w; this.py[i] = Math.random() * h; this.life[i] = 120 + Math.random() * 300;
        }
      }
      this._particles(ctx, i => (this.seed[i] * 4) | 0);
    }
    _waves(ctx, w, h) {
      const lines = 26, cols = this.palette.colors, step = 6 * this.dpr;
      const amp = h * (0.02 + 0.2 * this.energy), freq = (0.002 + 0.012 * (1 - this.pos)) / this.dpr, t = this.t * (0.8 + 2.4 * this.energy);
      ctx.lineWidth = 1.3 * this.dpr;
      for (let k = 0; k < lines; k++) {
        const f = k / (lines - 1), base = h * (0.18 + 0.64 * f), c = cols[Math.min(3, (f * 4) | 0)];
        ctx.strokeStyle = rgba(c, 0.25 + 0.55 * this.presence * (1 - Math.abs(f - 0.5)) + 0.25 * this.irGlow);
        ctx.beginPath();
        for (let x = 0; x <= w; x += step) {
          const env = Math.sin(Math.PI * x / w);
          const y = base + env * amp * (Math.sin(x * freq + t + k * 0.35) + 0.45 * Math.sin(x * freq * 2.3 - t * 1.3 + k * 0.6) * (this.irGlow > 0.5 ? -1 : 1));
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    }
    _pulse(ctx, w, h) {
      const cx = w / 2, cy = h / 2, m = Math.min(w, h), cols = this.palette.colors;
      this.pulseClock += this._dt || 1 / 60;
      const interval = 1.4 - 1.1 * this.energy;
      if (this.presence > 0.1 && this.pulseClock > interval) {
        this.pulseClock = 0;
        this.rings.push({r: m * 0.04, speed: (1.5 + 5 * this.energy) * this.dpr, width: (1.5 + 3 * this.energy) * this.dpr, alpha: 0.9, color: (this.rings.length % 3)});
      }
      const core = m * (0.03 + 0.1 * this.presence * (1 - this.pos));
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, core * 3);
      g.addColorStop(0, rgba(cols[this.irGlow > 0.5 ? 3 : 0], 0.9)); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, core * 3, 0, Math.PI * 2); ctx.fill();
    }
    _rings(ctx, w, h) {
      const cx = w / 2, cy = h / 2, cols = this.palette.colors;
      for (const ring of this.rings) {
        ctx.strokeStyle = rgba(cols[ring.color], Math.max(0, ring.alpha));
        ctx.lineWidth = ring.width; ctx.beginPath(); ctx.arc(cx, cy, ring.r, 0, Math.PI * 2); ctx.stroke();
      }
    }
  }

  /** Sinal sintético da demonstração: mouse (se mexeu há pouco) ou um movimento automático. */
  class DemoSignal {
    constructor() { this.pointer = null; this.pointerAt = 0; this.ir = false; this.t0 = performance.now(); }
    point(fraction) { this.pointer = Math.min(1, Math.max(0, fraction)); this.pointerAt = performance.now(); }
    sample() {
      const now = performance.now();
      if (this.pointer !== null && now - this.pointerAt < 4000) return {position: this.pointer, velocity: 0, ir: this.ir};
      const t = (now - this.t0) / 1000;
      const p = 0.5 + 0.38 * Math.sin(t * 0.55) + 0.08 * Math.sin(t * 2.1);
      return {position: Math.min(1, Math.max(0, p)), velocity: 60 * Math.cos(t * 0.55), ir: this.ir};
    }
  }

  globalThis.MotionCanvasLib = {MotionCanvas, DemoSignal, PALETTES, STYLES, spring};
})();
