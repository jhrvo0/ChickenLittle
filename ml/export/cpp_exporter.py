"""Exportador estático C/C++ (zero heap, compatível com FPU float32 do ESP-WROOM-32) para TinyML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml.schemas import FEATURE_NAMES, PreprocessingConfig


@dataclass(frozen=True)
class ExportMetadata:
    """Resumo técnico do cabeçalho C/C++ exportado para o ESP32."""

    header_path: str
    model_type: str
    num_features: int
    num_classes: int
    class_names: tuple[str, ...]
    estimated_flash_bytes: int
    estimated_stack_sram_bytes: int
    experimental_status: str
    hardware_validation_status: str = "NOT_VALIDATED_ON_ESP32_HARDWARE"


def _format_float_c(val: float) -> str:
    return f"{float(val):.8e}f"


def _extract_single_tree_arrays(
    tree_estimator: DecisionTreeClassifier,
    num_classes: int,
) -> list[tuple[int, int, int, float, list[float]]]:
    """Extrai `(feature, left, right, threshold, norm_probs)` de uma árvore scikit-learn."""
    tree = tree_estimator.tree_
    nodes: list[tuple[int, int, int, float, list[float]]] = []
    for node_id in range(tree.node_count):
        left = int(tree.children_left[node_id])
        right = int(tree.children_right[node_id])
        if left == right:  # Nó folha (-1 == -1)
            feat = -1
            thresh = 0.0
            counts = np.asarray(tree.value[node_id][0], dtype=np.float64)
            total = float(np.sum(counts))
            if total > 0.0:
                probs = [float(c / total) for c in counts]
            else:
                probs = [1.0 / num_classes] * num_classes
        else:
            feat = int(tree.feature[node_id])
            thresh = float(tree.threshold[node_id])
            probs = [0.0] * num_classes

        # Garante comprimento exato `num_classes` caso alguma classe rara não tenha caído na árvore
        if len(probs) < num_classes:
            mapped = [0.0] * num_classes
            classes_arr = getattr(tree_estimator, "classes_", np.arange(len(probs)))
            for idx_p, cls_idx in enumerate(classes_arr):
                if 0 <= int(cls_idx) < num_classes:
                    mapped[int(cls_idx)] = probs[idx_p]
            probs = mapped

        nodes.append((feat, left, right, thresh, probs[:num_classes]))
    return nodes


def _build_common_c_preamble(
    class_names: Sequence[str],
    preproc_cfg: PreprocessingConfig,
    experimental_status: str,
    model_name: str,
) -> str:
    num_classes = len(class_names)
    num_features = len(FEATURE_NAMES)
    class_strs = ", ".join(f'"{c}"' for c in class_names)

    return f"""/*
 * AUTO-GENERATED FILE — DO NOT EDIT MANUALLY
 * MotionPet Cycle 2 TinyML Static Header (`tinyml_model.h`)
 * Model: {model_name}
 * Experimental Data Status: {experimental_status}
 * Hardware Status: NOT_VALIDATED_ON_ESP32_HARDWARE (Host C++ Parity Verified Only)
 *
 * Restricoes embarcadas atendidas:
 * - Zero alocacao dinamica (sem malloc/new/std::vector/std::string)
 * - Constantes imutaveis posicionadas em Flash/ROM (`static const`)
 * - Aritmetica `float` (IEEE-754 32-bit) nativa para a FPU do ESP-WROOM-32
 */

#ifndef MOTIONPET_TINYML_MODEL_H
#define MOTIONPET_TINYML_MODEL_H

#include <stdint.h>
#include <stdbool.h>

#ifndef TINYML_FREESTANDING
#include <math.h>
#define tinyml_fabsf(x) fabsf(x)
#define tinyml_sqrtf(x) sqrtf(x)
#define tinyml_expf(x)  expf(x)
#else
static inline float tinyml_fabsf(float x) {{
    return (x < 0.0f) ? -x : x;
}}

static inline float tinyml_sqrtf(float x) {{
    if (x <= 0.0f) return 0.0f;
    double norm = (double)x;
    double scale = 1.0;
    while (norm >= 4.0) {{ norm *= 0.25; scale *= 2.0; }}
    while (norm < 0.25) {{ norm *= 4.0; scale *= 0.5; }}
    double g = 1.0;
    for (int i = 0; i < 7; ++i) {{
        g = 0.5 * (g + norm / g);
    }}
    return (float)(g * scale);
}}

static inline float tinyml_expf(float x) {{
    if (x <= -88.0f) return 0.0f;
    if (x >= 88.0f) return 1.65163625e38f;
    const double inv_ln2 = 1.44269504088896340736;
    const double ln2 = 0.69314718055994530942;
    double xd = (double)x;
    int k = (int)(xd * inv_ln2 + (xd >= 0.0 ? 0.5 : -0.5));
    double r = xd - (double)k * ln2;
    double term = 1.0;
    double sum = 1.0;
    for (int n = 1; n <= 10; ++n) {{
        term *= r / (double)n;
        sum += term;
    }}
    if (k >= 0) {{
        while (k >= 30) {{ sum *= (double)(1U << 30); k -= 30; }}
        sum *= (double)(1U << k);
    }} else {{
        int nk = -k;
        while (nk >= 30) {{ sum /= (double)(1U << 30); nk -= 30; }}
        sum /= (double)(1U << nk);
    }}
    return (float)sum;
}}
#endif

#ifdef __cplusplus
extern "C" {{
#endif

#define TINYML_NUM_FEATURES {num_features}
#define TINYML_NUM_CLASSES  {num_classes}
#define TINYML_WINDOW_SIZE  {preproc_cfg.window_size}

static const char* const TINYML_CLASS_NAMES[TINYML_NUM_CLASSES] = {{ {class_strs} }};

/* Parametros causais identicos ao treinamento Python (`PreprocessingConfig`) */
#define TINYML_MIN_VALID_CM          {_format_float_c(preproc_cfg.min_valid_cm)}
#define TINYML_MAX_VALID_CM          {_format_float_c(preproc_cfg.max_valid_cm)}
#define TINYML_SATURATION_CM         {_format_float_c(preproc_cfg.saturation_cm)}
#define TINYML_MAX_HOLD_STEPS        {int(preproc_cfg.max_hold_steps)}
#define TINYML_EMA_ALPHA             {_format_float_c(preproc_cfg.ema_alpha)}
#define TINYML_INVERSION_DEADBAND_CM {_format_float_c(preproc_cfg.inversion_deadband_cm)}

typedef struct {{
    float last_valid;
    bool has_last_valid;
    int16_t hold_count;
    float hist[3];
    int16_t hist_len;
    float ema;
    bool has_ema;
}} TinyMlCausalFilter;

static inline void tinyml_filter_reset(TinyMlCausalFilter *f) {{
    f->last_valid = 0.0f;
    f->has_last_valid = false;
    f->hold_count = 0;
    f->hist[0] = 0.0f;
    f->hist[1] = 0.0f;
    f->hist[2] = 0.0f;
    f->hist_len = 0;
    f->ema = 0.0f;
    f->has_ema = false;
}}

static inline float tinyml_median_up_to_3(const float *v, int16_t n) {{
    if (n <= 1) return v[0];
    if (n == 2) return 0.5f * (v[0] + v[1]);
    float a = v[0], b = v[1], c = v[2], t;
    if (a > b) {{ t = a; a = b; b = t; }}
    if (b > c) {{ t = b; b = c; c = t; }}
    if (a > b) {{ t = a; a = b; b = t; }}
    return b;
}}

static inline float tinyml_filter_step(
    TinyMlCausalFilter *f,
    float distance_cm,
    bool valid_ultrasonic,
    bool *out_was_invalid
) {{
    bool ok = valid_ultrasonic && (distance_cm >= TINYML_MIN_VALID_CM) && (distance_cm <= TINYML_MAX_VALID_CM);
    float raw_val;
    if (ok) {{
        raw_val = distance_cm;
        f->last_valid = raw_val;
        f->has_last_valid = true;
        f->hold_count = 0;
        if (out_was_invalid) *out_was_invalid = false;
    }} else {{
        if (out_was_invalid) *out_was_invalid = true;
        if (f->has_last_valid && f->hold_count < TINYML_MAX_HOLD_STEPS) {{
            f->hold_count += 1;
            raw_val = f->last_valid;
        }} else {{
            raw_val = TINYML_SATURATION_CM;
        }}
    }}

    if (raw_val < TINYML_MIN_VALID_CM) raw_val = TINYML_MIN_VALID_CM;
    if (raw_val > TINYML_SATURATION_CM) raw_val = TINYML_SATURATION_CM;

    if (f->hist_len < 3) {{
        f->hist[f->hist_len++] = raw_val;
    }} else {{
        f->hist[0] = f->hist[1];
        f->hist[1] = f->hist[2];
        f->hist[2] = raw_val;
    }}

    float med = tinyml_median_up_to_3(f->hist, f->hist_len);
    if (!f->has_ema) {{
        f->ema = med;
        f->has_ema = true;
    }} else {{
        f->ema = TINYML_EMA_ALPHA * med + (1.0f - TINYML_EMA_ALPHA) * f->ema;
    }}
    return f->ema;
}}

static inline void tinyml_extract_features(
    const float *distances_cm,
    const uint32_t *timestamps_ms,
    const uint8_t *ir_flags,
    const uint8_t *invalid_flags,
    uint16_t n,
    float out_features[TINYML_NUM_FEATURES]
) {{
    if (n == 0) {{
        for (uint16_t k = 0; k < TINYML_NUM_FEATURES; ++k) {{
            out_features[k] = 0.0f;
        }}
        return;
    }}
    float d_min = distances_cm[0];
    float d_max = distances_cm[0];
    float d_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {{
        float d = distances_cm[i];
        if (d < d_min) d_min = d;
        if (d > d_max) d_max = d;
        d_sum += d;
    }}
    float d_mean = d_sum / (float)n;

    float var_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {{
        float diff = distances_cm[i] - d_mean;
        var_sum += diff * diff;
    }}
    float d_std = tinyml_sqrtf(var_sum / (float)n);

    float d_delta = distances_cm[n - 1] - distances_cm[0];
    float total_dt_s = ((float)(timestamps_ms[n - 1] - timestamps_ms[0])) / 1000.0f;
    if (total_dt_s < 1e-3f) total_dt_s = 1e-3f;
    float v_mean = d_delta / total_dt_s;

    float v_peak = 0.0f;
    int16_t inversions = 0;
    int8_t prev_sign = 0;
    for (uint16_t i = 0; i + 1 < n; ++i) {{
        float step_d = distances_cm[i + 1] - distances_cm[i];
        float step_dt_s = ((float)(timestamps_ms[i + 1] - timestamps_ms[i])) / 1000.0f;
        if (step_dt_s < 1e-3f) step_dt_s = 1e-3f;
        float v_inst = step_d / step_dt_s;
        if (tinyml_fabsf(v_inst) > tinyml_fabsf(v_peak)) {{
            v_peak = v_inst;
        }}
        if (tinyml_fabsf(step_d) >= TINYML_INVERSION_DEADBAND_CM) {{
            int8_t sign = (step_d > 0.0f) ? 1 : -1;
            if (prev_sign != 0 && sign != prev_sign) {{
                inversions += 1;
            }}
            prev_sign = sign;
        }}
    }}

    uint32_t t0 = timestamps_ms[0];
    float t_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {{
        t_sum += ((float)(timestamps_ms[i] - t0)) / 1000.0f;
    }}
    float t_mean = t_sum / (float)n;
    float cov_td = 0.0f;
    float var_t = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {{
        float rt = ((float)(timestamps_ms[i] - t0)) / 1000.0f;
        float dt_c = rt - t_mean;
        cov_td += dt_c * (distances_cm[i] - d_mean);
        var_t += dt_c * dt_c;
    }}
    float trend_slope = (var_t > 1e-9f) ? (cov_td / var_t) : 0.0f;

    uint16_t ir_cnt = 0;
    uint16_t inv_cnt = 0;
    for (uint16_t i = 0; i < n; ++i) {{
        if (ir_flags[i]) ir_cnt += 1;
        if (invalid_flags[i]) inv_cnt += 1;
    }}

    out_features[0]  = d_min;
    out_features[1]  = d_max;
    out_features[2]  = d_mean;
    out_features[3]  = d_std;
    out_features[4]  = d_delta;
    out_features[5]  = v_mean;
    out_features[6]  = v_peak;
    out_features[7]  = trend_slope;
    out_features[8]  = (float)inversions;
    out_features[9]  = ((float)ir_cnt) / (float)n;
    out_features[10] = ((float)inv_cnt) / (float)n;
}}
"""


def _export_tree_ensemble_c(
    trees: Sequence[DecisionTreeClassifier],
    num_classes: int,
) -> tuple[str, int, int]:
    all_nodes: list[tuple[int, int, int, float, list[float]]] = []
    tree_offsets: list[int] = []
    for t in trees:
        tree_offsets.append(len(all_nodes))
        t_nodes = _extract_single_tree_arrays(t, num_classes)
        offset = tree_offsets[-1]
        for feat, left, right, thresh, probs in t_nodes:
            adj_left = (left + offset) if left >= 0 else -1
            adj_right = (right + offset) if right >= 0 else -1
            all_nodes.append((feat, adj_left, adj_right, thresh, probs))

    total_nodes = len(all_nodes)
    num_trees = len(trees)
    offsets_str = ", ".join(str(o) for o in tree_offsets)

    node_lines: list[str] = []
    for feat, left, right, thresh, probs in all_nodes:
        probs_c = ", ".join(_format_float_c(p) for p in probs)
        # Limiar em double/float: usamos double na constante de corte ou float consistente
        node_lines.append(
            f"    {{ {feat}, {left}, {right}, {thresh:.12e}, {{ {probs_c} }} }}"
        )
    nodes_block = ",\n".join(node_lines)

    body = f"""
#define TINYML_NUM_TREES  {num_trees}
#define TINYML_TOTAL_NODES {total_nodes}

typedef struct {{
    int16_t feature;
    int16_t left;
    int16_t right;
    double threshold;
    float probs[TINYML_NUM_CLASSES];
}} TinyMlTreeNode;

static const int16_t TINYML_TREE_ROOTS[TINYML_NUM_TREES] = {{ {offsets_str} }};

static const TinyMlTreeNode TINYML_NODES[TINYML_TOTAL_NODES] = {{
{nodes_block}
}};

static inline int tinyml_infer_proba(
    const float features[TINYML_NUM_FEATURES],
    float out_probs[TINYML_NUM_CLASSES]
) {{
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {{
        out_probs[c] = 0.0f;
    }}

    for (int t = 0; t < TINYML_NUM_TREES; ++t) {{
        int idx = TINYML_TREE_ROOTS[t];
        while (TINYML_NODES[idx].left >= 0) {{
            int f_idx = TINYML_NODES[idx].feature;
            /* scikit-learn converte features para float32 antes de comparar com threshold float64 */
            double f_val = (double)((float)features[f_idx]);
            if (f_val <= TINYML_NODES[idx].threshold) {{
                idx = TINYML_NODES[idx].left;
            }} else {{
                idx = TINYML_NODES[idx].right;
            }}
        }}
        for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {{
            out_probs[c] += TINYML_NODES[idx].probs[c];
        }}
    }}

    int best_cls = 0;
    float inv_trees = 1.0f / (float)TINYML_NUM_TREES;
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {{
        out_probs[c] *= inv_trees;
        if (out_probs[c] > out_probs[best_cls]) {{
            best_cls = c;
        }}
    }}
    return best_cls;
}}
"""
    flash_bytes = total_nodes * (2 + 2 + 2 + 8 + 4 * num_classes) + num_trees * 2 + 256
    sram_bytes = 64 + 4 * num_classes
    return body, flash_bytes, sram_bytes


def _export_mlp_pipeline_c(
    scaler: StandardScaler | None,
    mlp: MLPClassifier,
    num_features: int,
    num_classes: int,
) -> tuple[str, int, int]:
    means = (
        [float(x) for x in scaler.mean_]
        if scaler is not None and hasattr(scaler, "mean_")
        else [0.0] * num_features
    )
    scales = (
        [float(x) if float(x) != 0.0 else 1.0 for x in scaler.scale_]
        if scaler is not None and hasattr(scaler, "scale_")
        else [1.0] * num_features
    )

    n_layers = len(mlp.coefs_)
    widths = [w.shape[0] for w in mlp.coefs_] + [mlp.coefs_[-1].shape[1]]
    max_width = max(widths)

    arrays_code: list[str] = [
        f"#define TINYML_MLP_LAYERS {n_layers}",
        f"#define TINYML_MLP_MAX_WIDTH {max_width}",
        "static const float TINYML_SCALER_MEAN[TINYML_NUM_FEATURES] = { "
        + ", ".join(_format_float_c(m) for m in means)
        + " };",
        "static const float TINYML_SCALER_SCALE[TINYML_NUM_FEATURES] = { "
        + ", ".join(_format_float_c(s) for s in scales)
        + " };",
    ]

    total_floats = 2 * num_features
    step_code: list[str] = []

    for idx, (w_mat, b_vec) in enumerate(zip(mlp.coefs_, mlp.intercepts_)):
        in_dim, out_dim = w_mat.shape
        flat_w = ", ".join(_format_float_c(v) for v in w_mat.reshape(-1))
        flat_b = ", ".join(_format_float_c(v) for v in b_vec.reshape(-1))
        arrays_code.append(
            f"static const float TINYML_W{idx}[{in_dim * out_dim}] = {{ {flat_w} }};"
        )
        arrays_code.append(f"static const float TINYML_B{idx}[{out_dim}] = {{ {flat_b} }};")
        total_floats += in_dim * out_dim + out_dim

        is_last = idx == (n_layers - 1)
        relu_stmt = "" if is_last else "if (acc < 0.0f) acc = 0.0f;"
        step_code.append(
            f"""
    for (int o = 0; o < {out_dim}; ++o) {{
        float acc = TINYML_B{idx}[o];
        for (int i = 0; i < {in_dim}; ++i) {{
            acc += cur[i] * TINYML_W{idx}[i * {out_dim} + o];
        }}
        {relu_stmt}
        nxt[o] = acc;
    }}
    for (int o = 0; o < {out_dim}; ++o) {{ cur[o] = nxt[o]; }}"""
        )

    arrays_joined = "\n".join(arrays_code)
    steps_joined = "\n".join(step_code)

    body = f"""
{arrays_joined}

static inline int tinyml_infer_proba(
    const float features[TINYML_NUM_FEATURES],
    float out_probs[TINYML_NUM_CLASSES]
) {{
    float cur[TINYML_MLP_MAX_WIDTH];
    float nxt[TINYML_MLP_MAX_WIDTH];

    for (int i = 0; i < TINYML_NUM_FEATURES; ++i) {{
        cur[i] = (features[i] - TINYML_SCALER_MEAN[i]) / TINYML_SCALER_SCALE[i];
    }}
{steps_joined}

    float max_logit = cur[0];
    for (int c = 1; c < TINYML_NUM_CLASSES; ++c) {{
        if (cur[c] > max_logit) max_logit = cur[c];
    }}
    float sum_exp = 0.0f;
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {{
        out_probs[c] = tinyml_expf(cur[c] - max_logit);
        sum_exp += out_probs[c];
    }}
    int best_cls = 0;
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {{
        out_probs[c] /= sum_exp;
        if (out_probs[c] > out_probs[best_cls]) {{
            best_cls = c;
        }}
    }}
    return best_cls;
}}
"""
    flash_bytes = total_floats * 4 + 256
    sram_bytes = max_width * 2 * 4 + 96
    return body, flash_bytes, sram_bytes


def export_model_to_cpp_header(
    estimator: Any,
    class_names: Sequence[str],
    output_path: str | Path = "firmware/gestures/tinyml_model.h",
    preprocessing_config: PreprocessingConfig | None = None,
    experimental_status: str = "AWAITING_REAL_DATA",
    model_name: str | None = None,
) -> ExportMetadata:
    """Transpila `DecisionTreeClassifier`, `RandomForestClassifier` ou `MLP` para `tinyml_model.h`."""
    pre_cfg = preprocessing_config or PreprocessingConfig()
    num_classes = len(class_names)
    num_features = len(FEATURE_NAMES)

    scaler: StandardScaler | None = None
    core_est = estimator
    if isinstance(estimator, Pipeline):
        if "scaler" in estimator.named_steps:
            scaler = estimator.named_steps["scaler"]
        core_est = estimator.steps[-1][1]

    resolved_name = model_name or type(core_est).__name__
    preamble = _build_common_c_preamble(
        class_names=class_names,
        preproc_cfg=pre_cfg,
        experimental_status=experimental_status,
        model_name=resolved_name,
    )

    if isinstance(core_est, DecisionTreeClassifier):
        if scaler is not None:
            raise ValueError("DecisionTree export espera features diretas sem StandardScaler externo.")
        body, flash_b, sram_b = _export_tree_ensemble_c([core_est], num_classes)
        m_type = "decision_tree"
    elif isinstance(core_est, RandomForestClassifier):
        if scaler is not None:
            raise ValueError("RandomForest export espera features diretas sem StandardScaler externo.")
        body, flash_b, sram_b = _export_tree_ensemble_c(list(core_est.estimators_), num_classes)
        m_type = "random_forest"
    elif isinstance(core_est, MLPClassifier):
        body, flash_b, sram_b = _export_mlp_pipeline_c(scaler, core_est, num_features, num_classes)
        m_type = "mlp_compact"
    else:
        raise TypeError(
            f"Tipo de modelo não suportado para exportação C++ estática: {type(core_est).__name__}"
        )

    footer = """
static inline int tinyml_infer(
    const float features[TINYML_NUM_FEATURES],
    float *out_confidence
) {
    float probs[TINYML_NUM_CLASSES];
    int best = tinyml_infer_proba(features, probs);
    if (out_confidence) {
        *out_confidence = probs[best];
    }
    return best;
}

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_TINYML_MODEL_H
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(preamble + body + footer, encoding="utf-8")

    return ExportMetadata(
        header_path=str(out),
        model_type=m_type,
        num_features=num_features,
        num_classes=num_classes,
        class_names=tuple(class_names),
        estimated_flash_bytes=flash_b,
        estimated_stack_sram_bytes=sram_b,
        experimental_status=experimental_status,
    )
