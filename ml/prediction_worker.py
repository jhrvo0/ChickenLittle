"""Novas sessões persistidas → inferência automática, preservando origem e hash."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from ml.experiment import dataset_digest, validate_corpus
from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records
from ml.schemas import FEATURE_NAMES


class PredictionWorker:
    def __init__(self, service, raw_root, output, interval=2, *, iot_db=None):
        self.service, self.raw_root, self.output = service, Path(raw_root) if raw_root else None, Path(output)
        self.iot_db = Path(iot_db) if iot_db else None
        self.interval, self.stop = interval, Event()
        self.thread = Thread(target=self._run, name="motionlab-inference", daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=10)

    def tick(self):
        with self.service.lock:
            status = self.service.status()
            if status["status"] != "ready":
                return
            previous = self.service.predictions()
            cached = {(p["input_origin"], p["session_id"], p["dataset_sha256"]): p for p in previous["items"] if p.get("processing_version") == 1}
            items, errors = [], []
            for cohort in ("real", "synthetic", "demo"):
                for path in sorted((self.raw_root / cohort).glob("*.jsonl")) if self.raw_root else ():
                    try:
                        rows = load_raw_records_from_path(path)
                        validate_corpus(rows, cohort)
                        if len({r.session_id for r in rows}) != 1:
                            raise ValueError("Arquivo exige uma única sessão.")
                        digest = dataset_digest(rows)
                        key = (cohort, rows[0].session_id, digest)
                        if key in cached:
                            items.append(cached[key])
                            continue
                        windows = preprocess_records(rows, self.service.bundle.preprocessing_config, keep_ambiguous_transitions=True)
                        if not windows:
                            raise ValueError("Sessão sem janela válida.")
                        prediction = self.service.infer({"schema_version": 1, "input_origin": cohort,
                                                         "features": list(windows[-1].features),
                                                         "feature_names": list(FEATURE_NAMES)})
                        items.append({**prediction, "session_id": rows[0].session_id, "dataset_sha256": digest,
                                      "processing_version": 1, "window_end_ts_ms": windows[-1].end_ts_ms,
                                      "samples": len(rows), "windows": len(windows), "scope": "last_window_of_session",
                                      "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat()})
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        errors.append({"cohort": cohort, "file": path.name, "error": type(exc).__name__})
            if self.iot_db and self.iot_db.is_file():
                from ml.iot_ingestion import IotStore, predict_iot_windows
                try:
                    items.extend(predict_iot_windows(IotStore(self.iot_db), self.service))
                except (sqlite3.Error, OSError, ValueError, TypeError, KeyError) as exc:
                    errors.append({"cohort": "iot", "file": self.iot_db.name, "error": type(exc).__name__})
            result = {"schema_version": 1, "status": "ready" if items else "pending", "items": items,
                      "errors": errors, "physical_validation": "pending"}
            self.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.output.with_name(f".{self.output.name}-{uuid4().hex}.tmp")
            try:
                temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
                temporary.replace(self.output)
            finally:
                temporary.unlink(missing_ok=True)

    def _run(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                print(json.dumps({"status": "prediction_worker_error", "error": type(exc).__name__}), flush=True)
            self.stop.wait(self.interval)
