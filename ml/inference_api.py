"""API local de ML, independente da API visual e sem acesso à serial."""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import pickle
from pathlib import Path
import re
from threading import RLock

import numpy as np

from ml.experiment import COHORT_ORIGIN
from ml.preprocessing.windowing import preprocess_records
from ml.schemas import FEATURE_NAMES, ML_SCHEMA_VERSION, RawSampleRecord
from ml.training.trainer import load_trained_bundle
from ml.deployment import resolve_deployment


def evaluation_summary(root):
    result = {"schema_version": 1, "physical_validation": "pending"}
    for cohort in COHORT_ORIGIN:
        item = {"status": "pending", "cohort": cohort, "metrics": None,
                "message": "Nenhum experimento completo para esta origem."}
        try:
            folder = Path(root) / cohort
            latest = json.loads((folder / "latest.json").read_text(encoding="utf-8"))
            run_id = latest["experiment_id"]
            if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
                raise ValueError("Identificador inválido.")
            manifest = json.loads((folder / run_id / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((folder / run_id / "evaluation.json").read_text(encoding="utf-8"))
            if manifest["status"] != "complete" or manifest["cohort"] != cohort or report["cohort"] != cohort:
                raise ValueError("Manifesto incompatível.")
            if manifest["data_origin"] != COHORT_ORIGIN[cohort] or report["is_synthetic"] != (cohort != "real"):
                raise ValueError("Origem do relatório incompatível.")
            if manifest["dataset_sha256"] != report["dataset_sha256"] or report["experiment_id"] != run_id:
                raise ValueError("Relatório não corresponde ao manifesto.")
            item = {"status": "evaluated", "cohort": cohort, "experiment_id": run_id,
                    "dataset_sha256": manifest["dataset_sha256"], "evaluation_scope": "grouped_holdout",
                    "selected_model": manifest["selected_model"], "metrics": {
                        name: {**metrics, "far_neutral": {
                            "status": metrics.get("false_activation_rate_neutral_status", "pending"),
                            "value": metrics["false_activation_rate_neutral"] if metrics.get("false_activation_rate_neutral_status") == "evaluated" else None,
                            "support": metrics.get("neutral_support")}}
                        for name, metrics in report["models"].items()},
                    "software_only": cohort != "real", "generated_at_iso": manifest["generated_at_iso"],
                    "split": manifest["split"], "validation": manifest["validation"],
                    "eda": manifest.get("eda"), "tuning": manifest.get("tuning"),
                    "tracking": manifest.get("tracking"),
                    "orchestration": manifest.get("orchestration"),
                    "message": "Desempenho físico não validado." if cohort != "real" else "Avaliação offline sobre corpus declarado real; benchmark na placa pendente."}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            item.update(status="invalid", message="Artefatos inconsistentes; execute novamente o experimento.")
        result[cohort] = item
    return result


class InferenceService:
    def __init__(self, model_path=None, experiments_root="data/experiments", ui_origins=None, *, deployment=None, predictions=None):
        if model_path and deployment:
            raise ValueError("Escolha --model ou --deployment.")
        self.experiments_root = Path(experiments_root)
        self.bundle = load_trained_bundle(model_path) if model_path is not None else None
        if self.bundle and (tuple(self.bundle.feature_names) != FEATURE_NAMES or self.bundle.preprocessing_config.schema_version != ML_SCHEMA_VERSION):
            raise ValueError("Bundle incompatível com o contrato de features v1.")
        self.model_sha256 = hashlib.sha256(Path(model_path).read_bytes()).hexdigest() if model_path else None
        self.lock = RLock()
        self.deployment = Path(deployment) if deployment else None
        self.deployment_state = "fixed" if model_path else "pending"
        self.training_cohort = None
        self.predictions_path = Path(predictions) if predictions else None
        self.ui_origins = tuple(ui_origins) if ui_origins is not None else ("http://127.0.0.1:8767", "http://localhost:8767")

    def status(self):
        with self.lock:
            self._refresh()
            return self._status()

    def _refresh(self):
        if self.deployment is None:
            return
        try:
            model, spec = resolve_deployment(self.deployment, self.experiments_root)
            if spec["model_sha256"] != self.model_sha256:
                bundle = load_trained_bundle(model)
                if (tuple(bundle.feature_names) != FEATURE_NAMES or
                        bundle.preprocessing_config.schema_version != ML_SCHEMA_VERSION or
                        bundle.experiment_id != spec["experiment_id"] or
                        bundle.dataset_sha256 != spec["dataset_sha256"] or
                        set(bundle.data_origins) != {COHORT_ORIGIN[spec["cohort"]]}):
                    raise ValueError("Bundle incompatível com a publicação.")
                self.bundle = bundle
                self.model_sha256 = spec["model_sha256"]
            self.deployment_state = "published"
            self.training_cohort = spec["cohort"]
        except (OSError, ValueError, KeyError, TypeError, EOFError, pickle.UnpicklingError, ImportError, AttributeError, IndexError):
            self.bundle = None
            self.model_sha256 = None
            self.training_cohort = None
            self.deployment_state = "pending" if not self.deployment.exists() else "invalid"

    def _status(self):
        bundle = self.bundle
        return {"schema_version": 1, "status": "ready" if bundle else "pending", "source": "ml_host",
                "model_name": bundle.model_name if bundle else None, "model_sha256": self.model_sha256,
                "trained_on": list(bundle.data_origins) if bundle else [],
                "experiment_id": getattr(bundle, "experiment_id", None),
                "experimental_status": bundle.experimental_status if bundle else "AWAITING_REAL_DATA",
                "feature_names": list(FEATURE_NAMES), "physical_validation": "pending",
                "deployment_status": self.deployment_state, "training_cohort": self.training_cohort}

    def predictions(self):
        status = self.status()
        pending = {"schema_version": 1, "status": "pending", "items": [], "physical_validation": "pending"}
        if self.predictions_path is None or status["status"] != "ready":
            return pending
        try:
            data = json.loads(self.predictions_path.read_text(encoding="utf-8"))
            # Nunca exibir previsões de outro modelo como se fossem atuais.
            data["items"] = [p for p in data["items"] if p["model_sha256"] == status["model_sha256"]]
            data["status"] = "ready" if data["items"] else "pending"
            return data
        except FileNotFoundError:
            return pending
        except (OSError, ValueError, KeyError, TypeError):
            return {**pending, "status": "invalid"}

    def infer(self, payload):
        with self.lock:
            self._refresh()
            return self._infer(payload)

    def _infer(self, payload):
        if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != ML_SCHEMA_VERSION:
            raise ValueError("schema_version=1 obrigatório.")
        origin = payload.get("input_origin")
        if origin not in COHORT_ORIGIN:
            raise ValueError("input_origin obrigatório: real, synthetic ou demo.")
        if self.bundle is None:
            raise RuntimeError("Modelo pendente; configure --model com um bundle local confiável.")
        if ("features" in payload) == ("samples" in payload):
            raise ValueError("Informe exatamente um campo: features ou samples.")
        if "features" in payload:
            if payload.get("feature_names") != list(FEATURE_NAMES):
                raise ValueError("feature_names deve conter as 11 features na ordem canônica.")
            features = payload["features"]
            if not isinstance(features, list) or len(features) != len(FEATURE_NAMES):
                raise ValueError("Esperado um vetor com 11 features.")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in features):
                raise ValueError("Features devem ser números finitos.")
        else:
            samples = payload["samples"]
            if not isinstance(samples, list) or not self.bundle.preprocessing_config.window_size <= len(samples) <= 512:
                raise ValueError("samples precisa ter de window_size a 512 amostras ordenadas de uma sessão.")
            rows = []
            previous = -1
            for index, sample in enumerate(samples):
                if not isinstance(sample, dict):
                    raise ValueError("Cada amostra deve ser um objeto.")
                ts = sample.get("ts_ms")
                distance = sample.get("distance_cm")
                if isinstance(ts, bool) or not isinstance(ts, int) or ts <= previous:
                    raise ValueError("ts_ms deve ser inteiro não negativo e estritamente crescente.")
                if distance is not None and (isinstance(distance, bool) or not isinstance(distance, (float, int)) or not math.isfinite(distance)):
                    raise ValueError("distance_cm deve ser finita ou null.")
                if not isinstance(sample.get("valid_ultrasonic"), bool) or not isinstance(sample.get("ir_detected"), bool):
                    raise ValueError("valid_ultrasonic e ir_detected devem ser booleanos.")
                rows.append(RawSampleRecord("api", "api", index, ts, "NEUTRAL", distance,
                                            sample["valid_ultrasonic"], sample["ir_detected"], data_origin=COHORT_ORIGIN[origin]))
                previous = ts
            windows = preprocess_records(rows, self.bundle.preprocessing_config)
            features = list(windows[-1].features)
        with self.lock:
            probabilities = self.bundle.estimator.predict_proba(np.asarray([features], dtype=float))[0]
        cls = int(np.argmax(probabilities))
        label_index = int(self.bundle.estimator.classes_[cls])
        return {**self._status(), "input_origin": origin, "label": self.bundle.class_names[label_index],
                "confidence": float(probabilities[cls]),
                "probabilities": {self.bundle.class_names[int(k)]: float(v) for k, v in zip(self.bundle.estimator.classes_, probabilities)},
                "scope": "single_window", "event_gate_applied": False,
                "message": "Inferência de janela; não envia ações nem equivale a avaliação de desempenho."}


def create_server(service, host="127.0.0.1", port=8768):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(6)

        def log_message(self, *_args):
            pass

        def reply(self, code, body):
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            origin = self.headers.get("Origin")
            if origin in service.ui_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            origin = self.headers.get("Origin")
            if origin not in service.ui_origins:
                self.reply(403, {"error": "origin_not_allowed"})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path in ("/health", "/v1/status"):
                self.reply(200, service.status())
            elif self.path == "/v1/evaluations":
                self.reply(200, evaluation_summary(service.experiments_root))
            elif self.path == "/v1/predictions":
                self.reply(200, service.predictions())
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/v1/infer":
                self.reply(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    self.reply(413, {"error": "payload_size", "max_bytes": 65536})
                    return
                payload = json.loads(self.rfile.read(size))
                self.reply(200, service.infer(payload))
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {"error": "invalid_request", "message": str(exc)})
            except RuntimeError as exc:
                self.reply(503, {"error": "model_pending", "message": str(exc)})
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Bundle joblib local confiável; não aceita upload pela API.")
    parser.add_argument("--deployment", help="Publicação local explícita; recarrega após troca atômica.")
    parser.add_argument("--watch-raw-root", help="Classifica automaticamente novas sessões persistidas, sem treinar.")
    parser.add_argument("--watch-iot-db", help="SQLite IoT isolado: inferência sem rótulos, sem treino/avaliação.")
    parser.add_argument("--predictions", help="JSON local das previsões automáticas.")
    parser.add_argument("--experiments-root", default="data/experiments")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--ui-origin", action="append", help="Origem adicional permitida para o frontend local.")
    args = parser.parse_args(argv)
    origins = ["http://127.0.0.1:8767", "http://localhost:8767", *(args.ui_origin or [])]
    if (args.watch_raw_root or args.watch_iot_db) and not args.predictions:
        parser.error("--watch-raw-root/--watch-iot-db exige --predictions")
    service = InferenceService(args.model, args.experiments_root, origins, deployment=args.deployment, predictions=args.predictions)
    server = create_server(service, args.host, args.port)
    worker = None
    if args.watch_raw_root or args.watch_iot_db:
        from ml.prediction_worker import PredictionWorker
        worker = PredictionWorker(service, args.watch_raw_root, args.predictions, iot_db=args.watch_iot_db)
        worker.start()
    print(f"MotionLab ML API: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if worker:
            worker.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
