"""Núcleo do MotionLab: sensores → reconhecimento → portão de segurança → ações dos módulos.

Fluxo por frame:
1. `SignalTracker` atualiza o canal contínuo (distância → posição 0..1).
2. `IrTracker` transforma bordas do IR em `IR_TAP` / `IR_HOLD`.
3. Os reconhecedores do host (regras e ML) recebem o frame; os eventos do TinyML chegam à parte.
4. Todo evento é registrado; só o da fonte escolhida (driver) e os do IR passam pelo portão.
5. O portão aplica: mapeamento, armado, confiança, zona ativa, cooldown, trava de repetição,
   chave de ações externas e limite de taxa. O desfecho fica no histórico com o motivo.

Os métodos são chamados com o lock da sessão web já tomado.
"""
from __future__ import annotations

from collections import deque
import time

from terminal.communication.protocol import GestureEventPayload, SensorFramePayload
from terminal.motionlab.actions import CATALOG, CONTEXTS, ExternalRateLimiter, KeySender, WindowsKeySender
from terminal.motionlab.dataset import GuidedRecorder
from terminal.motionlab.profiles import ProfileStore
from terminal.motionlab.recognizers import DEFAULT_MODEL_PATH, HostRecognizer, build_host_recognizers
from terminal.motionlab.signals import IrTracker, SignalTracker

GESTURES = ("APPROACH", "RETREAT", "HOLD")
MAX_FRAMES = 360
MAX_EVENTS = 300
STALE_MS = 1000          # sinal mais velho que isso não autoriza ação
ZONE_MEMORY_MS = 1200    # gesto vale se a mão esteve na zona ativa há pouco (o afastamento sai dela)
AGREEMENT_FRAMES = 10    # ~700 ms a 70 ms/frame para casar eventos de regras e ML


class MotionEngine:
    def __init__(self, *, store: ProfileStore | None = None, key_sender: KeySender | None = None,
                 model_path=DEFAULT_MODEL_PATH, recognizers: dict[str, HostRecognizer] | None = None,
                 data_root=None, clock=time.monotonic) -> None:
        self._clock = clock
        self._t0 = clock()
        self.store = store or ProfileStore()
        self.key_sender = key_sender or WindowsKeySender()
        self.recognizers = recognizers if recognizers is not None else build_host_recognizers(model_path)
        self.signal = SignalTracker()
        self.ir = IrTracker()
        self.recorder = GuidedRecorder(data_root=data_root)
        self.rate = ExternalRateLimiter(clock)
        self.module = "home"
        self.armed = False
        self.external_enabled = False
        self.origin = "NONE"
        self.frames: deque = deque(maxlen=MAX_FRAMES)
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self._frame_seq = 0
        self._event_seq = 0
        self._device_count = 0
        self._device_last_raw: dict | None = None
        self._last_frame_host: float | None = None
        self._last_present_host: float | None = None
        self._last_exec_host: float | None = None
        self._last_exec_trigger: str | None = None
        self._intervals: deque = deque(maxlen=200)
        self._last_ts: int | None = None
        self._apply_settings()

    # ------------------------------------------------------------------ ciclo de vida
    def _apply_settings(self) -> None:
        s = self.store.settings
        self.signal.configure(s["near_cm"], s["far_cm"])
        self.ir.hold_ms = int(s["ir_hold_ms"])

    def reset(self, origin: str = "NONE") -> None:
        """Nova conexão (ou desconexão): limpa histórico de sinal e DESARMA por segurança."""
        self.origin = origin
        self.armed = False
        self.external_enabled = False
        self.signal.reset()
        self.ir.reset()
        for rec in self.recognizers.values():
            rec.reset()
        self.frames.clear()
        self._device_count = 0
        self._device_last_raw = None
        self._last_frame_host = None
        self._last_present_host = None
        self._last_exec_host = None
        self._last_exec_trigger = None
        self._intervals.clear()
        self._last_ts = None
        if self.recorder.active:
            self.recorder.abort("A conexão mudou durante a gravação.")

    def _now_ms(self) -> int:
        return int((self._clock() - self._t0) * 1000)

    # ------------------------------------------------------------------ entrada
    def on_frame(self, frame: SensorFramePayload, ts_ms: int) -> None:
        now = self._clock()
        if self._last_ts is not None and ts_ms > self._last_ts:
            self._intervals.append(ts_ms - self._last_ts)
        self._last_ts = ts_ms
        self._last_frame_host = now
        self._frame_seq += 1
        snap = self.signal.push(frame.distance_cm, frame.valid_ultrasonic, ts_ms)
        if snap.present:
            self._last_present_host = now
        self.frames.append({
            "seq": self._frame_seq, "ts": ts_ms, "d": None if frame.distance_cm is None else round(frame.distance_cm, 2),
            "f": None if snap.filtered_cm is None else round(snap.filtered_cm, 2),
            "p": None if snap.position is None else round(snap.position, 4),
            "v": snap.valid, "ir": bool(frame.ir_detected),
        })
        if self.recorder.active:
            self.recorder.on_frame(frame, ts_ms)
        for trigger in self.ir.push(frame.ir_detected, ts_ms):
            if trigger in ("IR_TAP", "IR_HOLD"):
                self._route("ir", trigger, None, kind="sensor")
            else:
                self._record({"source": "ir", "gesture": trigger, "confidence": None, "status": "observed"})
        for source, rec in self.recognizers.items():
            event = rec.push(frame, ts_ms)
            if event is not None:
                self._route(source, event.gesture.value, event.confidence, kind=rec.kind)

    def on_device_gesture(self, event: GestureEventPayload, ts_ms: int) -> None:
        """Evento do firmware (TinyML embarcado, `source=tinyml`, ou outra origem informada)."""
        self._device_count += 1
        self._device_last_raw = {"label": event.gesture.value, "confidence": round(event.confidence, 4),
                                 "ts_ms": ts_ms, "wire_source": event.source.value}
        if event.gesture.value not in GESTURES:
            self._record({"source": "device", "gesture": event.gesture.value, "confidence": event.confidence,
                          "status": "observed", "reason": "not_core_gesture"})
            return
        self._route("device", event.gesture.value, event.confidence, kind="ml")

    # ------------------------------------------------------------------ portão
    def _record(self, entry: dict) -> dict:
        self._event_seq += 1
        entry = {"id": self._event_seq, "t": self._now_ms(), "frame_seq": self._frame_seq,
                 "action": None, "context": None, "reason": None, **entry}
        self.events.append(entry)
        return entry

    def _context(self) -> str | None:
        return self.module if self.module in CONTEXTS else None

    def _route(self, source: str, trigger: str, confidence: float | None, *, kind: str) -> dict:
        driver = self.store.settings["driver"]
        base = {"source": source, "gesture": trigger,
                "confidence": None if confidence is None else round(float(confidence), 4),
                "confidence_kind": "rule" if kind == "rules" else "softmax" if kind == "ml" else None}
        if source != "ir" and source != driver:
            return self._record({**base, "status": "observed"})
        context = self._context()
        if context is None:
            return self._record({**base, "status": "rejected", "reason": "no_module"})
        action = self.store.active_profile(context)["bindings"].get(trigger)
        if action is None:
            return self._record({**base, "status": "rejected", "reason": "unmapped", "context": context})
        reason = self._gate(trigger, action, confidence, kind)
        if reason is not None:
            return self._record({**base, "status": "rejected", "reason": reason, "action": action, "context": context})
        return self._execute(action, context, base, trigger)

    def _gate(self, trigger: str, action: str, confidence: float | None, kind: str) -> str | None:
        s = self.store.settings
        now = self._clock()
        if action != "lab.toggle_armed" and not self.armed:
            return "disarmed"
        if self._last_frame_host is None or (now - self._last_frame_host) * 1000 > STALE_MS:
            return "stale_signal"
        if kind == "ml" and confidence is not None and confidence < s["min_confidence"]:
            return "low_confidence"
        if trigger in GESTURES and (self._last_present_host is None or (now - self._last_present_host) * 1000 > ZONE_MEMORY_MS):
            return "out_of_zone"
        if self._last_exec_host is not None:
            elapsed = (now - self._last_exec_host) * 1000
            if elapsed < s["cooldown_ms"]:
                return "cooldown"
            if s["repeat_lock"] and trigger == self._last_exec_trigger and trigger in GESTURES and elapsed < 2 * s["cooldown_ms"]:
                return "repeat_lock"
        spec = CATALOG[action]
        if spec.kind == "external":
            if not self.external_enabled:
                return "external_disabled"
            if not self.key_sender.available:
                return "external_unavailable"
        return None

    def _execute(self, action: str, context: str, base: dict, trigger: str | None) -> dict:
        spec = CATALOG[action]
        if spec.kind == "external":
            if not self.rate.allow():
                return self._record({**base, "status": "rejected", "reason": "rate_limited", "action": action, "context": context})
            try:
                self.key_sender.send(spec.vk, spec.extended)
            except Exception as exc:
                return self._record({**base, "status": "rejected", "reason": f"send_failed: {exc}", "action": action, "context": context})
            status = "executed"
        elif spec.kind == "system":
            self.armed = not self.armed
            status = "executed"
        else:
            status = "dispatched"  # a interface do módulo executa ao ler o evento
        if trigger is not None:
            self._last_exec_host = self._clock()
            self._last_exec_trigger = trigger
        entry = self._record({**base, "status": status, "action": action, "context": context})
        if spec.kind == "system":
            entry["detail"] = "armed" if self.armed else "disarmed"
        return entry

    # ------------------------------------------------------------------ comandos da interface
    def set_module(self, module: str) -> None:
        if module not in CONTEXTS + ("home", "intelligence"):
            raise ValueError("Módulo desconhecido.")
        self.module = module

    def set_armed(self, value: bool) -> None:
        self.armed = bool(value)
        self._record({"source": "ui", "gesture": None, "confidence": None, "status": "executed",
                      "action": "lab.toggle_armed", "detail": "armed" if self.armed else "disarmed"})

    def set_external(self, value: bool) -> None:
        if value and not self.key_sender.available:
            raise ValueError(f"Ações no sistema indisponíveis: {self.key_sender.reason}")
        self.external_enabled = bool(value)

    def update_settings(self, changes: dict) -> None:
        self.store.update_settings(changes)
        self._apply_settings()

    def test_action(self, action: str) -> dict:
        """Disparo manual pela interface (botão "testar"). Sem gesto, sem cooldown; mesma allowlist."""
        spec = CATALOG.get(action)
        if spec is None:
            raise ValueError("Ação fora da lista permitida.")
        context = self._context() or (spec.contexts[0] if spec.contexts else "control")
        base = {"source": "ui", "gesture": None, "confidence": None, "confidence_kind": None}
        if spec.kind == "external":
            if not self.external_enabled:
                raise ValueError("Ligue \"Ações no sistema\" para testar teclas externas.")
            if not self.key_sender.available:
                raise ValueError(f"Ações no sistema indisponíveis: {self.key_sender.reason}")
        entry = self._execute(action, context, base, None)
        if entry["status"] == "rejected":
            raise ValueError("Ação recusada: " + str(entry["reason"]))
        return entry

    # ------------------------------------------------------------------ leitura
    def live(self, since_frame: int = 0, since_event: int = 0) -> dict:
        frames = [f for f in self.frames if f["seq"] > since_frame]
        events = [e for e in self.events if e["id"] > since_event]
        now = self._clock()
        return {
            "frame_seq": self._frame_seq, "event_seq": self._event_seq, "frames": frames[-120:], "events": events[-60:],
            "signal": self.signal.snapshot.to_dict(),
            "ir": {"active": self.ir.active, "held_ms": self.ir.held_ms(self._last_ts or 0)},
            "age_ms": None if self._last_frame_host is None else round((now - self._last_frame_host) * 1000),
            "armed": self.armed, "external_enabled": self.external_enabled, "module": self.module,
            "origin": self.origin, "recording": self.recorder.status(),
            "cooldown_left_ms": self._cooldown_left(now),
        }

    def _cooldown_left(self, now: float) -> int:
        if self._last_exec_host is None:
            return 0
        return max(0, int(self.store.settings["cooldown_ms"] - (now - self._last_exec_host) * 1000))

    def agreement(self) -> dict:
        """Concordância entre regras e ML no fluxo ao vivo (sem rótulo: não é acurácia)."""
        by_source: dict[str, list] = {"rules": [], "ml": [], "device": []}
        for e in self.events:
            if e["source"] in by_source and e["gesture"] in GESTURES:
                by_source[e["source"]].append(e)

        def pair(a: list, b: list) -> dict:
            used: set[int] = set()
            matched = 0
            for ea in a:
                for eb in b:
                    if eb["id"] not in used and eb["gesture"] == ea["gesture"] and abs(eb["frame_seq"] - ea["frame_seq"]) <= AGREEMENT_FRAMES:
                        used.add(eb["id"])
                        matched += 1
                        break
            total = len(a) + len(b) - matched
            return {"matched": matched, "only_a": len(a) - matched, "only_b": len(b) - matched,
                    "rate": None if total == 0 else round(matched / total, 3)}

        return {"rules_vs_ml": pair(by_source["rules"], by_source["ml"]),
                "rules_vs_device": pair(by_source["rules"], by_source["device"]),
                "window_frames": AGREEMENT_FRAMES}

    def snapshot(self) -> dict:
        intervals = list(self._intervals)
        period = None
        if intervals:
            ordered = sorted(intervals)
            period = {"mean_ms": round(sum(ordered) / len(ordered), 1), "max_ms": ordered[-1],
                      "p95_ms": ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]}
        counts: dict[str, dict[str, int]] = {}
        for e in self.events:
            bucket = counts.setdefault(e["source"], {})
            key = e["status"] if e["status"] != "rejected" else "rejected:" + str(e["reason"])
            bucket[key] = bucket.get(key, 0) + 1
        demo = self.origin == "DEMO"
        device = {"source": "device", "label": "Detector do simulador" if demo else "TinyML na ESP32", "kind": "ml",
                  "available": self.origin == "ESP32_HW" or self._device_count > 0,
                  "origin": "simulator" if demo else "synthetic", "events": self._device_count,
                  "last_raw": self._device_last_raw,
                  "confidence_meaning": "heurística do simulador" if demo else "softmax não calibrado (firmware)",
                  "note": ("Na demonstração, esta faixa recebe o detector heurístico do simulador, não o TinyML."
                           if demo else "Modelo embarcado treinado com dados sintéticos (AWAITING_REAL_DATA).")}
        return {
            "module": self.module, "armed": self.armed, "external_enabled": self.external_enabled,
            "external_available": self.key_sender.available, "external_reason": self.key_sender.reason,
            "origin": self.origin, "store": self.store.to_dict(),
            "catalog": [spec.to_dict() for spec in CATALOG.values()],
            "recognizers": [r.describe() for r in self.recognizers.values()] + [device],
            "sample_period": period, "counts": counts, "agreement": self.agreement(),
            "recording": self.recorder.status(),
        }
