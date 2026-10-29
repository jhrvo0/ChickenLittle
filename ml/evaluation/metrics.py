"""Cálculo de métricas estatísticas, latência, footprint para ESP32 e eventos contínuos."""

from __future__ import annotations

import io
import time
from collections import defaultdict
from typing import Any, Sequence

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from ml.evaluation.stabilizer import EventStabilizer
from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, StabilizerConfig, WindowSample


def estimate_esp32_memory(
    estimator: Any,
    class_names: Sequence[str] = CORE_GESTURE_CLASSES,
) -> dict[str, int]:
    """Estima o footprint de Flash e SRAM do modelo para execução no ESP32."""
    buf = io.BytesIO()
    joblib.dump(estimator, buf)
    serialized_bytes = len(buf.getvalue())

    model_type = type(estimator).__name__

    # 1. RuleBaselineModel
    if "RuleBaseline" in model_type:
        return {
            "serialized_bytes": serialized_bytes,
            "estimated_esp32_flash_bytes": 512,
            "estimated_esp32_sram_bytes": 64,
        }

    # 2. DecisionTreeClassifier
    if hasattr(estimator, "tree_"):
        node_count = int(estimator.tree_.node_count)
        # Cada nó em C++ requer ~24 bytes (arrays estáticos const em Flash)
        flash_bytes = node_count * 24
        sram_bytes = 128  # Pilha rasa e variáveis locais de percurso
        return {
            "serialized_bytes": serialized_bytes,
            "estimated_esp32_flash_bytes": flash_bytes,
            "estimated_esp32_sram_bytes": sram_bytes,
        }

    # 3. RandomForestClassifier
    if hasattr(estimator, "estimators_"):
        total_nodes = sum(int(t.tree_.node_count) for t in estimator.estimators_)
        flash_bytes = (total_nodes * 24) + 256
        sram_bytes = 256  # Votação acumulada dos estimadores
        return {
            "serialized_bytes": serialized_bytes,
            "estimated_esp32_flash_bytes": flash_bytes,
            "estimated_esp32_sram_bytes": sram_bytes,
        }

    # 4. Pipeline com MLPClassifier ou MLPClassifier direto
    mlp = None
    if hasattr(estimator, "named_steps") and "mlp" in estimator.named_steps:
        mlp = estimator.named_steps["mlp"]
    elif hasattr(estimator, "coefs_"):
        mlp = estimator

    if mlp is not None and hasattr(mlp, "coefs_"):
        n_features = len(FEATURE_NAMES)
        n_weights = sum(w.size for w in mlp.coefs_)
        n_biases = sum(b.size for b in mlp.intercepts_)
        # Pesos float32 (4 bytes cada) + parâmetros de normalização do scaler (mean e std: 2 * 11 * 4)
        flash_bytes = int((n_weights + n_biases + 2 * n_features) * 4)

        layer_widths = [n_features] + list(mlp.hidden_layer_sizes) + [len(class_names)]
        max_layer_width = max(layer_widths)
        # Buffers ping-pong float32 para ativações consecutivas + overhead
        sram_bytes = int((max_layer_width * 2) * 4 + 128)
        return {
            "serialized_bytes": serialized_bytes,
            "estimated_esp32_flash_bytes": flash_bytes,
            "estimated_esp32_sram_bytes": sram_bytes,
        }

    # Estimativa genérica de contingência
    return {
        "serialized_bytes": serialized_bytes,
        "estimated_esp32_flash_bytes": min(serialized_bytes, 16384),
        "estimated_esp32_sram_bytes": 512,
    }


def measure_inference_latency(
    estimator: Any,
    X: np.ndarray,
    n_warmup: int = 5,
) -> tuple[float, float]:
    """Mede a latência média e p95 da inferência janela a janela (single-window)."""
    n_samples = len(X)
    if n_samples == 0:
        return 0.0, 0.0

    # Aquecimento
    warmup_count = min(n_warmup, n_samples)
    for _ in range(warmup_count):
        _ = estimator.predict(X[0:1])

    latencies_ms: list[float] = []
    for i in range(n_samples):
        sample = X[i : i + 1]
        t0 = time.perf_counter()
        _ = estimator.predict(sample)
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    mean_lat = float(np.mean(latencies_ms))
    p95_lat = float(np.percentile(latencies_ms, 95))
    return round(mean_lat, 4), round(p95_lat, 4)


def evaluate_classification_metrics(
    estimator: Any,
    X: np.ndarray,
    y: np.ndarray,
    class_names: Sequence[str] = CORE_GESTURE_CLASSES,
) -> dict[str, Any]:
    """Calcula métricas estáticas de classificação por janela: F1, matriz de confusão e FAR neutro."""
    if len(y) == 0:
        return {
            "accuracy": 0.0,
            "f1_macro": 0.0,
            "confusion_matrix": [],
            "per_class": {},
            "false_activation_rate_neutral": 0.0,
            "latency_mean_ms": 0.0,
            "latency_p95_ms": 0.0,
            "memory": estimate_esp32_memory(estimator, class_names),
        }

    y_pred = estimator.predict(X)
    acc = float(accuracy_score(y, y_pred))
    f1_mac = float(f1_score(y, y_pred, average="macro", zero_division=0))

    labels_idx = list(range(len(class_names)))
    cm = confusion_matrix(y, y_pred, labels=labels_idx).tolist()

    per_class: dict[str, dict[str, Any]] = {}
    for idx, name in enumerate(class_names):
        tp = int(np.sum((y == idx) & (y_pred == idx)))
        fp = int(np.sum((y != idx) & (y_pred == idx)))
        fn = int(np.sum((y == idx) & (y_pred != idx)))
        support = int(np.sum(y == idx))

        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        per_class[name] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    # Taxa de falsa ativação em janelas de repouso (NEUTRAL classificado como gesto ativo)
    neutral_idx = list(class_names).index("NEUTRAL") if "NEUTRAL" in class_names else 0
    neutral_mask = y == neutral_idx
    n_neutral = int(np.sum(neutral_mask))
    if n_neutral > 0:
        false_activations = int(np.sum(y_pred[neutral_mask] != neutral_idx))
        far_neutral = float(false_activations / n_neutral)
    else:
        far_neutral = 0.0

    latency_mean, latency_p95 = measure_inference_latency(estimator, X)
    mem = estimate_esp32_memory(estimator, class_names)

    return {
        "accuracy": round(acc, 4),
        "f1_macro": round(f1_mac, 4),
        "confusion_matrix": cm,
        "per_class": per_class,
        "false_activation_rate_neutral": round(far_neutral, 4),
        "latency_mean_ms": latency_mean,
        "latency_p95_ms": latency_p95,
        "memory": mem,
    }


def evaluate_event_level(
    estimator: Any,
    test_windows: Sequence[WindowSample],
    class_names: Sequence[str] = CORE_GESTURE_CLASSES,
    stabilizer_config: StabilizerConfig | None = None,
) -> dict[str, Any]:
    """Avalia o classificador em fluxo contínuo com histerese e supressão de repetecos."""
    if not test_windows:
        return {
            "true_episodes": 0,
            "matched_episodes": 0,
            "duplicate_activations": 0,
            "false_activations": 0,
            "rejected_windows": 0,
            "event_precision": 0.0,
            "event_recall": 0.0,
            "event_f1": 0.0,
        }

    # Agrupa por sessão mantendo ordenação temporal causal estrita
    sessions_map: dict[str, list[WindowSample]] = defaultdict(list)
    for w in test_windows:
        sessions_map[w.session_id].append(w)

    true_episodes_total = 0
    matched_episodes_total = 0
    duplicate_activations_total = 0
    false_activations_total = 0
    rejected_windows_total = 0

    stabilizer = EventStabilizer(stabilizer_config)

    for session_id in sorted(sessions_map.keys()):
        ordered = sorted(sessions_map[session_id], key=lambda x: (x.end_ts_ms, x.start_ts_ms))
        if not ordered:
            continue

        # 1. Extração dos episódios de referência contínuos da sessão
        episodes: list[dict[str, Any]] = []
        cur_label: str | None = None
        cur_windows: list[WindowSample] = []

        for w in ordered:
            if w.label == cur_label:
                cur_windows.append(w)
            else:
                if cur_label is not None and cur_label != "NEUTRAL":
                    dt_win = (
                        (cur_windows[-1].end_ts_ms - cur_windows[-2].end_ts_ms)
                        if len(cur_windows) > 1
                        else max(50, cur_windows[0].end_ts_ms - cur_windows[0].start_ts_ms)
                    )
                    episodes.append(
                        {
                            "label": cur_label,
                            "start_ts_ms": cur_windows[0].start_ts_ms,
                            "end_ts_ms": cur_windows[-1].end_ts_ms,
                            "extended_end_ts_ms": cur_windows[-1].end_ts_ms + dt_win,
                        }
                    )
                cur_label = w.label
                cur_windows = [w]

        if cur_label is not None and cur_label != "NEUTRAL":
            dt_win = (
                (cur_windows[-1].end_ts_ms - cur_windows[-2].end_ts_ms)
                if len(cur_windows) > 1
                else max(50, cur_windows[0].end_ts_ms - cur_windows[0].start_ts_ms)
            )
            episodes.append(
                {
                    "label": cur_label,
                    "start_ts_ms": cur_windows[0].start_ts_ms,
                    "end_ts_ms": cur_windows[-1].end_ts_ms,
                    "extended_end_ts_ms": cur_windows[-1].end_ts_ms + dt_win,
                }
            )

        # 2. Execução causal do classificador + estabilizador na sessão
        stabilizer.reset()
        emissions: list[dict[str, Any]] = []

        for w in ordered:
            x_arr = np.asarray(w.features, dtype=np.float64).reshape(1, -1)
            if hasattr(estimator, "predict_proba"):
                probas = estimator.predict_proba(x_arr)[0]
                c_idx = int(np.argmax(probas))
                conf = float(probas[c_idx])
            else:
                c_idx = int(estimator.predict(x_arr)[0])
                conf = 1.0

            raw_label = class_names[c_idx] if c_idx < len(class_names) else "NEUTRAL"
            dec = stabilizer.step(raw_label=raw_label, confidence=conf, ts_ms=w.end_ts_ms)

            if not dec.accepted:
                rejected_windows_total += 1
            else:
                emissions.append(
                    {
                        "label": dec.emitted_label,
                        "ts_ms": w.end_ts_ms,
                        "matched": False,
                    }
                )

        # 3. Casamento temporal dos eventos emitidos com os episódios reais
        for ep in episodes:
            true_episodes_total += 1
            matches = [
                e
                for e in emissions
                if (ep["start_ts_ms"] <= e["ts_ms"] <= ep["extended_end_ts_ms"])
                and (e["label"] == ep["label"])
                and not e["matched"]
            ]
            if matches:
                matched_episodes_total += 1
                matches[0]["matched"] = True
                if len(matches) > 1:
                    duplicate_activations_total += len(matches) - 1
                    for extra in matches[1:]:
                        extra["matched"] = True

        # Emissões não casadas (em NEUTRAL ou com classe invertida/errônea)
        unmatched = [e for e in emissions if not e["matched"]]
        false_activations_total += len(unmatched)

    # Cálculo final das métricas de evento
    total_emitted = (
        matched_episodes_total + duplicate_activations_total + false_activations_total
    )

    recall = (
        float(matched_episodes_total / true_episodes_total)
        if true_episodes_total > 0
        else 1.0
    )
    precision = (
        float(matched_episodes_total / total_emitted) if total_emitted > 0 else 0.0
    )
    f1 = (
        float(2 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "true_episodes": true_episodes_total,
        "matched_episodes": matched_episodes_total,
        "duplicate_activations": duplicate_activations_total,
        "false_activations": false_activations_total,
        "rejected_windows": rejected_windows_total,
        "event_precision": round(precision, 4),
        "event_recall": round(recall, 4),
        "event_f1": round(f1, 4),
    }
