"""Coleta guiada de dados reais pela interface e avaliação legítima dos reconhecedores.

- A gravação usa o cronograma e o formato (`RawSampleRecord`) de `ml.collection`, então os
  arquivos entram direto em `ml.preprocessing` e em `ml.real_pipeline`.
- Só a origem `ESP32_HW` grava em `data/raw/real/`. A demonstração grava em `data/raw/demo/`
  com `data_origin=synthetic_simulator`: dado sintético nunca vira evidência de desempenho.
- A avaliação reproduz as sessões reais gravadas, por janela (mesma pureza de rótulo do
  pipeline), e calcula F1-macro e matriz de confusão para regras e ML.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re

from ml.schemas import CORE_GESTURE_CLASSES, DataOrigin, RawSampleRecord

DEFAULT_SCHEDULE = "NEUTRAL:20,APPROACH:16,NEUTRAL:16,RETREAT:16,NEUTRAL:16,HOLD:18,NEUTRAL:20"
_PARTICIPANT = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
PROMPTS = {
    "NEUTRAL": "Mão fora do sensor (repouso)",
    "APPROACH": "Aproxime a mão do sensor",
    "RETREAT": "Afaste a mão do sensor",
    "HOLD": "Segure a mão parada a ~15 cm",
}


def parse_schedule(spec: str, repeats: int) -> list[tuple[str, int]]:
    from ml.collection.collector import parse_gesture_schedule

    base = parse_gesture_schedule(spec)
    if not 1 <= repeats <= 5:
        raise ValueError("Repetições entre 1 e 5.")
    for label, count in base:
        if label not in CORE_GESTURE_CLASSES or not 4 <= count <= 200:
            raise ValueError("Cronograma inválido.")
    return base * repeats


class GuidedRecorder:
    def __init__(self, data_root=None) -> None:
        self.data_root = Path(data_root) if data_root is not None else Path("data/raw")
        self.active = False
        self.last_result: dict | None = None
        self._clear()

    def _clear(self) -> None:
        self.active = False
        self._plan: list[str] = []
        self._segments: list[tuple[str, int]] = []
        self._records: list[RawSampleRecord] = []
        self._participant = ""
        self._session_id = ""
        self._origin = ""
        self._started_iso = ""

    def start(self, participant: str, origin: str, *, repeats: int = 3, schedule: str = DEFAULT_SCHEDULE) -> None:
        if self.active:
            raise ValueError("Já existe uma gravação em andamento.")
        if not isinstance(participant, str) or not _PARTICIPANT.match(participant):
            raise ValueError("Identificador do participante: 1 a 24 caracteres (letras, números, - e _).")
        if origin not in ("ESP32_HW", "DEMO"):
            raise ValueError("Conecte a ESP32 (ou a demonstração) antes de gravar.")
        if isinstance(repeats, bool) or not isinstance(repeats, int):
            raise ValueError("Repetições inválidas.")
        segments = parse_schedule(schedule, repeats)
        self._clear()
        self._segments = segments
        self._plan = [label for label, count in segments for _ in range(count)]
        self._participant = participant
        self._origin = origin
        now = dt.datetime.now(dt.timezone.utc)
        self._started_iso = now.isoformat()
        self._session_id = f"session_{participant}_{now.strftime('%Y%m%dT%H%M%S')}"
        self.active = True
        self.last_result = None

    def abort(self, reason: str = "Gravação cancelada.") -> None:
        if self.active:
            self.last_result = {"ok": False, "message": reason, "session_id": self._session_id}
        self._clear()

    def on_frame(self, frame, ts_ms: int) -> None:
        if not self.active:
            return
        idx = len(self._records)
        if self._records and ts_ms <= self._records[-1].ts_ms:
            ts_ms = self._records[-1].ts_ms + 1  # monotonicidade estrita exigida pelo validador
        origin = DataOrigin.REAL_HARDWARE.value if self._origin == "ESP32_HW" else DataOrigin.SYNTHETIC_SIMULATOR.value
        self._records.append(RawSampleRecord(
            participant_id=self._participant, session_id=self._session_id, sample_idx=idx, ts_ms=int(ts_ms),
            label=self._plan[idx], distance_cm=frame.distance_cm, valid_ultrasonic=bool(frame.valid_ultrasonic),
            ir_detected=bool(frame.ir_detected), pot_norm=0.5, data_origin=origin, captured_at_iso=self._started_iso,
        ))
        if len(self._records) >= len(self._plan):
            self._finish()

    def _finish(self) -> None:
        from ml.collection.validator import validate_session_records

        report = validate_session_records(self._records)
        folder = self.data_root / ("real" if self._origin == "ESP32_HW" else "demo")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self._session_id}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for rec in self._records:
                fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        self.last_result = {
            "ok": report.valid, "session_id": self._session_id, "path": path.as_posix(), "samples": len(self._records),
            "origin": "real" if self._origin == "ESP32_HW" else "demo",
            "errors": list(report.errors), "warnings": list(report.warnings),
            "message": "Sessão real gravada." if self._origin == "ESP32_HW" else "Sessão de demonstração gravada (sintética, fora da avaliação).",
        }
        self._clear()

    def status(self) -> dict:
        if not self.active:
            return {"active": False, "last_result": self.last_result}
        idx = len(self._records)
        label = self._plan[idx]
        # posição dentro do segmento atual
        consumed = 0
        seg_index = 0
        for seg_index, (seg_label, count) in enumerate(self._segments):
            if idx < consumed + count:
                break
            consumed += count
        seg_label, seg_count = self._segments[seg_index]
        next_label = self._segments[seg_index + 1][0] if seg_index + 1 < len(self._segments) else None
        return {
            "active": True, "participant": self._participant, "session_id": self._session_id,
            "origin": "real" if self._origin == "ESP32_HW" else "demo",
            "label": label, "prompt": PROMPTS.get(label, label), "sample": idx, "total": len(self._plan),
            "segment": seg_index + 1, "segments": len(self._segments),
            "segment_left": consumed + seg_count - idx, "segment_size": seg_count,
            "next_label": next_label, "last_result": self.last_result,
        }


def list_sessions(data_root=None) -> dict:
    root = Path(data_root) if data_root is not None else Path("data/raw")
    out = {}
    for kind in ("real", "demo"):
        folder = root / kind
        files = sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
        out[kind] = [{"name": f.stem, "bytes": f.stat().st_size} for f in files][-50:]
    return out


def evaluate_real_sessions(recognizers: dict, data_root=None) -> dict:
    """Avalia regras e ML por janela nas sessões REAIS gravadas. Sem sessões: status pendente."""
    import numpy as np

    from ml.evaluation.metrics import evaluate_classification_metrics
    from ml.preprocessing.windowing import load_raw_records_from_path, segment_session_windows
    from ml.training.splitter import windows_to_xy

    folder = (Path(data_root) if data_root is not None else Path("data/raw")) / "real"
    if not folder.is_dir() or not any(folder.glob("*.jsonl")):
        return {"status": "pending", "message": "Nenhuma sessão real gravada ainda. Use a coleta guiada com a ESP32 conectada."}
    records = load_raw_records_from_path(folder)
    if not records:
        return {"status": "pending", "message": "Nenhuma amostra real disponível."}
    if any(r.data_origin != DataOrigin.REAL_HARDWARE.value for r in records):
        return {"status": "invalid_data", "message": "A pasta real contém dados de outra origem; avaliação bloqueada."}
    sessions: dict[str, list] = {}
    for r in records:
        sessions.setdefault(r.session_id, []).append(r)
    participants = sorted({r.participant_id for r in records})
    results = {}
    for source, rec in recognizers.items():
        if not rec.available:
            results[source] = {"available": False, "error": rec.error}
            continue
        cfg = rec.bundle.preprocessing_config
        windows = []
        for sess in sessions.values():
            windows.extend(segment_session_windows(sess, cfg))
        X, y = windows_to_xy(windows, rec.bundle.class_names)
        if len(y) == 0:
            results[source] = {"available": True, "windows": 0}
            continue
        metrics = evaluate_classification_metrics(rec.bundle.estimator, X, y, rec.bundle.class_names)
        metrics.pop("memory", None)
        from ml.provenance import preview_provenance
        results[source] = {"available": True, "windows": int(len(y)), "class_names": list(rec.bundle.class_names),
                           "model_name": rec.bundle.model_name, "trained_on": list(rec.bundle.data_origins),
                           "provenance": preview_provenance(rec.bundle, records), **metrics}
    supports = {name: int(np.sum([1 for s in sessions.values() for r in s if r.label == name])) for name in CORE_GESTURE_CLASSES}
    small = len(participants) < 3 or len(sessions) < 3
    return {
        "status": "evaluated_on_real_data", "sessions": len(sessions), "participants": participants,
        "evaluation_scope": "exploratory_replay", "physical_validation": "pending",
        "samples_per_label": supports, "results": results,
        "caveat": ("Amostra pequena: poucos participantes/sessões; trate como indicativo, não conclusivo." if small else None),
    }


def load_synthetic_report(path=Path("data/reports/evaluation_report.json")) -> dict | None:
    """Resumo do relatório do pipeline sintético, sempre acompanhado do aviso de que é sintético."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        models = {
            name: {k: m.get(k) for k in ("test_f1_macro", "accuracy", "false_activation_rate_neutral")}
            for name, m in (data.get("models") or {}).items()
        }
        return {"is_synthetic": bool(data.get("is_synthetic", True)), "status": data.get("experimental_status"),
                "disclaimer": data.get("synthetic_disclaimer") or "Relatório gerado com dados sintéticos.",
                "generated_at": data.get("generated_at_iso"), "models": models}
    except (OSError, ValueError, AttributeError):
        return None
