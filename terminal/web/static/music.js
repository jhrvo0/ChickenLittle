'use strict';
/* Air Music Pro — instrumento por distância com Web Audio nativo.
   A distância escolhe a nota (leitura direta, sem ML); a presença da mão abre o som; o IR
   (pelo perfil "Música") grava/para camadas do looper. O looper guarda eventos de nota, não
   áudio: cada camada é tocada por uma voz própria, sincronizada ao relógio do AudioContext. */
(() => {
  const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const SCALES = {
    pent_major: {name: 'Pentatônica maior', steps: [0, 2, 4, 7, 9]},
    pent_minor: {name: 'Pentatônica menor', steps: [0, 3, 5, 7, 10]},
    major: {name: 'Maior', steps: [0, 2, 4, 5, 7, 9, 11]},
    dorian: {name: 'Dórica', steps: [0, 2, 3, 5, 7, 9, 10]},
    chromatic: {name: 'Cromática', steps: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]},
  };
  const TIMBRES = [
    {id: 'glass', name: 'Vidro'}, {id: 'pad', name: 'Pad'}, {id: 'pluck', name: 'Pluck'}, {id: 'theremin', name: 'Teremim'},
  ];
  const MAX_LAYERS = 4;

  // ------------------------------------------------------------ funções puras (testadas no Node)
  function scaleNotes(root, scaleId, octaves) {
    const steps = (SCALES[scaleId] || SCALES.pent_major).steps, out = [];
    for (let o = 0; o < octaves; o++) for (const s of steps) out.push(root + 12 * o + s);
    out.push(root + 12 * octaves);
    return out;
  }
  /** Posição 0 (mão perto) → nota mais aguda, como num teremim. */
  function pickNote(position, notes) {
    if (position === null || position === undefined || !notes.length) return null;
    const p = Math.min(1, Math.max(0, position));
    return notes[Math.round((1 - p) * (notes.length - 1))];
  }
  const midiToFreq = m => 440 * Math.pow(2, (m - 69) / 12);
  const noteName = m => m === null ? '—' : NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1);
  /** Valor de uma camada no instante `t` (eventos em degrau, cíclicos no loop). */
  function valueAt(events, t) {
    if (!events.length) return null;
    let lo = 0, hi = events.length - 1, idx = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (events[mid].t <= t) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
    return idx < 0 ? events[events.length - 1].midi : events[idx].midi;
  }
  function loopSeconds(bpm, bars) { return bars * 4 * 60 / bpm; }

  // ------------------------------------------------------------ voz
  class Voice {
    constructor(ctx, out, timbre) {
      this.ctx = ctx; this.timbre = timbre; this.midi = null; this.on = false;
      this.filter = ctx.createBiquadFilter(); this.filter.type = 'lowpass'; this.filter.Q.value = 0.8;
      this.amp = ctx.createGain(); this.amp.gain.value = 0;
      this.filter.connect(this.amp); this.amp.connect(out);
      const types = {glass: ['sine', 'triangle'], pad: ['sawtooth', 'sawtooth'], pluck: ['square', 'triangle'], theremin: ['sine', 'sine']}[timbre];
      this.oscs = types.map((type, i) => {
        const o = ctx.createOscillator(); o.type = type;
        if (timbre === 'pad') o.detune.value = i ? 7 : -7;
        const g = ctx.createGain(); g.gain.value = timbre === 'glass' && i ? 0.25 : timbre === 'theremin' && i ? 0 : 0.5;
        o.connect(g); g.connect(this.filter); o.start(); return {o, ratio: timbre === 'glass' && i ? 2 : 1};
      });
      this.brightness = 0.6; this.level = 0.7;
    }
    set(midi, level) {
      const ctx = this.ctx, now = ctx.currentTime;
      const glide = this.timbre === 'theremin' ? 0.09 : this.timbre === 'pad' ? 0.05 : 0.012;
      const cutoff = 300 + 6000 * this.brightness * this.brightness;
      this.filter.frequency.setTargetAtTime(cutoff * (this.timbre === 'pluck' ? 0.7 : 1), now, 0.05);
      if (midi === null) {
        if (this.on) { this.amp.gain.cancelScheduledValues(now); this.amp.gain.setTargetAtTime(0, now, this.timbre === 'pad' ? 0.25 : 0.08); }
        this.on = false; this.midi = null; return;
      }
      const freq = midiToFreq(midi), changed = midi !== this.midi;
      for (const {o, ratio} of this.oscs) o.frequency.setTargetAtTime(freq * ratio, now, glide);
      const peak = 0.22 * level;
      if (!this.on || (changed && (this.timbre === 'pluck' || this.timbre === 'glass'))) {
        const g = this.amp.gain; g.cancelScheduledValues(now); g.setValueAtTime(Math.max(0.0001, g.value), now);
        if (this.timbre === 'pluck') { g.linearRampToValueAtTime(peak, now + 0.004); g.setTargetAtTime(0.0001, now + 0.01, 0.12); }
        else if (this.timbre === 'glass') { g.linearRampToValueAtTime(peak, now + 0.006); g.setTargetAtTime(peak * 0.3, now + 0.02, 0.25); }
        else g.setTargetAtTime(peak, now, this.timbre === 'pad' ? 0.18 : 0.03);
      } else if (this.timbre === 'theremin' || this.timbre === 'pad') this.amp.gain.setTargetAtTime(peak, now, 0.05);
      this.on = true; this.midi = midi;
    }
    dispose() {
      const now = this.ctx.currentTime;
      this.amp.gain.setTargetAtTime(0, now, 0.05);
      setTimeout(() => { for (const {o} of this.oscs) { try { o.stop(); } catch (_) {} } this.amp.disconnect(); }, 400);
    }
  }

  function impulse(ctx, seconds) {
    const len = Math.round(ctx.sampleRate * seconds), buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let ch = 0; ch < 2; ch++) { const d = buf.getChannelData(ch); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6); }
    return buf;
  }

  // ------------------------------------------------------------ instrumento + looper
  class AirMusic {
    constructor() {
      this.ctx = null; this.enabled = false;
      this.timbreIndex = 0; this.scale = 'pent_major'; this.root = 57; this.octaves = 2;
      this.volume = 0.7; this.brightness = 0.6; this.echo = 0.25; this.space = 0.3; this.muted = false;
      this.bpm = 90; this.bars = 2;
      this.layers = []; this.playing = false; this.recording = null; this.loopStart = 0;
      this.current = null; this.live = null; this.onChange = null;
    }
    get timbre() { return TIMBRES[this.timbreIndex].id; }
    get notes() { return scaleNotes(this.root, this.scale, this.octaves); }
    get loopLength() { return this.layers.length ? this.layers[0].length : loopSeconds(this.bpm, this.bars); }

    async enable() {
      if (!this.ctx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) throw new Error('Este navegador não oferece Web Audio.');
        const ctx = this.ctx = new Ctx();
        this.master = ctx.createGain();
        const comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 3;
        this.bus = ctx.createGain();
        this.delay = ctx.createDelay(2); this.feedback = ctx.createGain(); this.echoWet = ctx.createGain();
        this.reverb = ctx.createConvolver(); this.reverb.buffer = impulse(ctx, 2.6); this.spaceWet = ctx.createGain();
        this.bus.connect(this.master);
        this.bus.connect(this.delay); this.delay.connect(this.feedback); this.feedback.connect(this.delay); this.delay.connect(this.echoWet); this.echoWet.connect(this.master);
        this.bus.connect(this.reverb); this.reverb.connect(this.spaceWet); this.spaceWet.connect(this.master);
        this.master.connect(comp); comp.connect(ctx.destination);
        this._timer = setInterval(() => this._tick(), 20);
      }
      await this.ctx.resume();
      this.enabled = true; this.applyMix(); this._newLiveVoice(); this._changed();
    }
    disable() {
      this.enabled = false;
      if (this.live) { this.live.dispose(); this.live = null; }
      for (const l of this.layers) if (l.voice) l.voice.set(null, 0);
      if (this.ctx) this.ctx.suspend();
      this._changed();
    }
    applyMix() {
      if (!this.ctx) return;
      const now = this.ctx.currentTime, beat = 60 / this.bpm;
      this.master.gain.setTargetAtTime(this.volume, now, 0.05);
      this.delay.delayTime.setTargetAtTime(beat * 0.75, now, 0.05);
      this.feedback.gain.setTargetAtTime(0.25 + 0.45 * this.echo, now, 0.05);
      this.echoWet.gain.setTargetAtTime(this.echo, now, 0.05);
      this.spaceWet.gain.setTargetAtTime(this.space * 0.8, now, 0.05);
      for (const v of [this.live, ...this.layers.map(l => l.voice)]) if (v) v.brightness = this.brightness;
    }
    _newLiveVoice() {
      if (!this.ctx) return;
      if (this.live) this.live.dispose();
      this.live = new Voice(this.ctx, this.bus, this.timbre); this.live.brightness = this.brightness;
    }
    nextTimbre() { this.timbreIndex = (this.timbreIndex + 1) % TIMBRES.length; this._newLiveVoice(); this._changed(); }
    setTimbre(id) { const i = TIMBRES.findIndex(t => t.id === id); if (i >= 0) { this.timbreIndex = i; this._newLiveVoice(); this._changed(); } }

    /** Entrada contínua a cada quadro (somente com o módulo de música aberto). */
    input({position, velocity}) {
      const midi = this.muted ? null : pickNote(position, this.notes);
      const level = 0.75 + 0.25 * Math.min(1, Math.abs(velocity || 0) / 60);
      if (this.live && this.enabled) this.live.set(midi, level);
      if (midi !== this.current) {
        this.current = midi;
        if (this.recording) this._capture(midi);
        this._changed();
      }
    }
    silenceLive() { if (this.live) this.live.set(null, 0); this.current = null; if (this.recording) this._capture(null); }

    action(name) {
      if (name === 'music.toggle_record') this.recording ? this.stopRecording() : this.startRecording();
      else if (name === 'music.toggle_play') this.togglePlay();
      else if (name === 'music.next_timbre') this.nextTimbre();
      else if (name === 'music.clear_layer') this.undo();
      else if (name === 'music.toggle_mute') { this.muted = !this.muted; this._changed(); }
      else return false;
      return true;
    }
    _pos() { return this.ctx ? ((this.ctx.currentTime - this.loopStart) % this.loopLength + this.loopLength) % this.loopLength : 0; }
    startRecording() {
      if (!this.enabled) throw new Error('Ative o áudio antes de gravar.');
      if (this.layers.length >= MAX_LAYERS) throw new Error('Limite de 4 camadas. Apague uma para gravar outra.');
      const first = this.layers.length === 0;
      if (first) { this.loopStart = this.ctx.currentTime; this.playing = true; }
      const length = first ? loopSeconds(this.bpm, this.bars) : this.loopLength;
      this.recording = {events: [], startedAt: this.ctx.currentTime, length, timbre: this.timbre};
      this._capture(this.current);
      this._changed();
    }
    _capture(midi) {
      const r = this.recording; if (!r) return;
      const t = this.layers.length ? this._pos() : this.ctx.currentTime - this.loopStart;
      r.events.push({t: Math.max(0, Math.min(r.length - 1e-3, t)), midi});
    }
    stopRecording() {
      const r = this.recording; if (!r) return;
      this.recording = null;
      const events = r.events.slice().sort((a, b) => a.t - b.t);
      if (events.some(e => e.midi !== null)) {
        const voice = new Voice(this.ctx, this.bus, r.timbre); voice.brightness = this.brightness;
        this.layers.push({events, length: r.length, timbre: r.timbre, voice, muted: false});
      } else if (!this.layers.length) this.playing = false;
      this._changed();
    }
    togglePlay() {
      if (!this.layers.length) return;
      this.playing = !this.playing;
      if (this.playing && this.ctx) this.loopStart = this.ctx.currentTime;
      if (!this.playing) for (const l of this.layers) l.voice.set(null, 0);
      this._changed();
    }
    undo() {
      if (this.recording) { this.recording = null; if (!this.layers.length) this.playing = false; this._changed(); return; }
      const l = this.layers.pop(); if (l) l.voice.dispose();
      if (!this.layers.length) this.playing = false;
      this._changed();
    }
    toggleLayer(i) { const l = this.layers[i]; if (l) { l.muted = !l.muted; if (l.muted) l.voice.set(null, 0); this._changed(); } }
    _tick() {
      if (!this.ctx || !this.enabled) return;
      if (this.recording && this.ctx.currentTime - this.recording.startedAt >= this.recording.length) this.stopRecording();
      if (!this.playing) return;
      const pos = this._pos();
      for (const l of this.layers) if (!l.muted) l.voice.set(valueAt(l.events, pos), 0.8);
    }
    pause() { if (this.ctx && this.enabled) { this.silenceLive(); for (const l of this.layers) l.voice.set(null, 0); this.ctx.suspend(); } }
    resume() { if (this.ctx && this.enabled) this.ctx.resume(); }
    position() { return this.playing || this.recording ? this._pos() / this.loopLength : null; }
    _changed() { if (this.onChange) this.onChange(); }
  }

  globalThis.AirMusicLib = {AirMusic, SCALES, TIMBRES, NAMES, scaleNotes, pickNote, midiToFreq, noteName, valueAt, loopSeconds};
})();
