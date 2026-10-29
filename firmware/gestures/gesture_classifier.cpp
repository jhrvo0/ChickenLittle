#include "gestures/gesture_classifier.h"
#include "gestures/tinyml_model.h"
#include "common/fw_utils.h"

static GestureClassifierContext g_default_gesture_ctx;

const char* gesture_type_to_string(GestureType gesture) {
    switch (gesture) {
        case GESTURE_APPROACH: return "APPROACH";
        case GESTURE_RETREAT:  return "RETREAT";
        case GESTURE_HOLD:     return "HOLD";
        case GESTURE_IMPULSE:  return "IMPULSE";
        case GESTURE_DOUBLE:   return "DOUBLE";
        case GESTURE_NEUTRAL:
        default:               return "NEUTRAL";
    }
}

GestureType gesture_type_from_string(const char *str) {
    if (!str) return GESTURE_NEUTRAL;
    if (fw_strcmp(str, "APPROACH") == 0) return GESTURE_APPROACH;
    if (fw_strcmp(str, "RETREAT") == 0)  return GESTURE_RETREAT;
    if (fw_strcmp(str, "HOLD") == 0)     return GESTURE_HOLD;
    if (fw_strcmp(str, "IMPULSE") == 0)  return GESTURE_IMPULSE;
    if (fw_strcmp(str, "DOUBLE") == 0)   return GESTURE_DOUBLE;
    return GESTURE_NEUTRAL;
}

const char* gesture_rejection_to_string(GestureRejectionReason reason) {
    switch (reason) {
        case GESTURE_REJ_NONE:              return "none";
        case GESTURE_REJ_WINDOW_INCOMPLETE: return "window_incomplete";
        case GESTURE_REJ_LOW_CONFIDENCE:    return "low_confidence";
        case GESTURE_REJ_NEUTRAL:           return "neutral";
        case GESTURE_REJ_UNSTABLE_STATE:    return "unstable_state";
        case GESTURE_REJ_COOLDOWN_ACTIVE:   return "cooldown_active";
        default:                            return "unknown";
    }
}

const char* gesture_classifier_model_name(void) {
#ifdef TINYML_MODEL_NAME
    return TINYML_MODEL_NAME;
#else
    return "tinyml_static";
#endif
}

const char* gesture_classifier_experimental_status(void) {
#ifdef TINYML_EXPERIMENTAL_STATUS
    return TINYML_EXPERIMENTAL_STATUS;
#else
    return "AWAITING_REAL_DATA";
#endif
}

bool gesture_classifier_is_engineering_synthetic_model(void) {
#ifdef TINYML_IS_ENGINEERING_SYNTHETIC_MODEL
    return (TINYML_IS_ENGINEERING_SYNTHETIC_MODEL != 0);
#else
    return true;
#endif
}

void gesture_classifier_ctx_init(
    GestureClassifierContext *ctx,
    const GestureStabilizerConfig *custom_cfg
) {
    if (!ctx) return;

    ctx->flt_last_valid = 0.0f;
    ctx->flt_has_last_valid = false;
    ctx->flt_hold_count = 0;
    ctx->flt_hist[0] = 0.0f;
    ctx->flt_hist[1] = 0.0f;
    ctx->flt_hist[2] = 0.0f;
    ctx->flt_hist_len = 0;
    ctx->flt_ema = 0.0f;
    ctx->flt_has_ema = false;

    for (uint16_t i = 0U; i < GESTURE_WINDOW_MAX_SAMPLES; ++i) {
        ctx->ring_dists[i] = 0.0f;
        ctx->ring_ts[i] = 0UL;
        ctx->ring_ir[i] = 0U;
        ctx->ring_inv[i] = 0U;
    }
    ctx->ring_write_idx = 0U;
    ctx->ring_count = 0U;
    ctx->last_sample_ts_ms = 0UL;
    ctx->has_pending_sample = false;

    if (custom_cfg) {
        ctx->stab_cfg = *custom_cfg;
    } else {
        ctx->stab_cfg.min_confidence = 0.60f;
        ctx->stab_cfg.min_consecutive_windows = 2U;
        ctx->stab_cfg.cooldown_ms = 700UL;
        ctx->stab_cfg.require_neutral_reset = false;
    }

    ctx->last_emit_ts_ms = -10000000LL;
    ctx->consecutive_label = GESTURE_NEUTRAL;
    ctx->has_consecutive_label = false;
    ctx->consecutive_count = 0U;
    ctx->latched_label = GESTURE_NEUTRAL;
    ctx->has_latched_label = false;

    ctx->last_features = GestureFeatures{};
    ctx->last_raw_gesture = GESTURE_NEUTRAL;
    ctx->last_raw_confidence = 0.0f;
    ctx->last_rejection = GESTURE_REJ_NONE;
    ctx->total_windows_evaluated = 0UL;
    ctx->total_events_emitted = 0UL;
    ctx->total_windows_rejected = 0UL;
}

void gesture_classifier_ctx_push_sample(
    GestureClassifierContext *ctx,
    float distance_cm,
    bool valid_ultrasonic,
    bool ir_detected,
    uint32_t ts_ms
) {
    if (!ctx) return;

    // Garante monotonicidade estrita idêntica a MLGestureClassifier.push_frame
    uint32_t cur_ts = ts_ms;
    if (ctx->ring_count > 0U && cur_ts <= ctx->last_sample_ts_ms) {
        cur_ts = ctx->last_sample_ts_ms + 1UL;
    }
    ctx->last_sample_ts_ms = cur_ts;

    // Reconstrói struct TinyMlCausalFilter local a partir do estado do contexto
    TinyMlCausalFilter flt;
    flt.last_valid = ctx->flt_last_valid;
    flt.has_last_valid = ctx->flt_has_last_valid;
    flt.hold_count = ctx->flt_hold_count;
    flt.hist[0] = ctx->flt_hist[0];
    flt.hist[1] = ctx->flt_hist[1];
    flt.hist[2] = ctx->flt_hist[2];
    flt.hist_len = ctx->flt_hist_len;
    flt.ema = ctx->flt_ema;
    flt.has_ema = ctx->flt_has_ema;

    bool was_inv = false;
    float filtered_d = tinyml_filter_step(&flt, distance_cm, valid_ultrasonic, &was_inv);

    ctx->flt_last_valid = flt.last_valid;
    ctx->flt_has_last_valid = flt.has_last_valid;
    ctx->flt_hold_count = flt.hold_count;
    ctx->flt_hist[0] = flt.hist[0];
    ctx->flt_hist[1] = flt.hist[1];
    ctx->flt_hist[2] = flt.hist[2];
    ctx->flt_hist_len = flt.hist_len;
    ctx->flt_ema = flt.ema;
    ctx->flt_has_ema = flt.has_ema;

    // Grava no buffer circular estático O(1)
    uint16_t slot = ctx->ring_write_idx;
    ctx->ring_dists[slot] = filtered_d;
    ctx->ring_ts[slot] = cur_ts;
    ctx->ring_ir[slot] = ir_detected ? 1U : 0U;
    ctx->ring_inv[slot] = was_inv ? 1U : 0U;

    ctx->ring_write_idx = (uint16_t)((slot + 1U) % GESTURE_WINDOW_MAX_SAMPLES);
    if (ctx->ring_count < TINYML_WINDOW_SIZE) {
        ctx->ring_count++;
    }
    ctx->has_pending_sample = true;
}

static bool stabilizer_step(
    GestureClassifierContext *ctx,
    GestureType raw_gesture,
    float confidence,
    uint32_t ts_ms
) {
    const GestureStabilizerConfig *cfg = &ctx->stab_cfg;

    // 1. Rejeição por baixa confiança
    if (confidence < cfg->min_confidence) {
        ctx->consecutive_count = 0U;
        ctx->has_consecutive_label = false;
        if (raw_gesture == GESTURE_NEUTRAL) {
            ctx->last_rejection = GESTURE_REJ_NEUTRAL;
        } else {
            ctx->last_rejection = GESTURE_REJ_LOW_CONFIDENCE;
            ctx->total_windows_rejected++;
        }
        return false;
    }

    // 2. Supressão de NEUTRAL (libera trava de gesto sustentado)
    if (raw_gesture == GESTURE_NEUTRAL) {
        ctx->consecutive_count = 0U;
        ctx->has_consecutive_label = false;
        ctx->has_latched_label = false;
        ctx->last_rejection = GESTURE_REJ_NEUTRAL;
        return false;
    }

    // 3. Histerese temporal (mínimo de janelas consecutivas congruentes)
    if (ctx->has_consecutive_label && raw_gesture == ctx->consecutive_label) {
        ctx->consecutive_count++;
    } else {
        ctx->consecutive_label = raw_gesture;
        ctx->has_consecutive_label = true;
        ctx->consecutive_count = 1U;
    }

    if (ctx->consecutive_count < cfg->min_consecutive_windows) {
        ctx->last_rejection = GESTURE_REJ_UNSTABLE_STATE;
        ctx->total_windows_rejected++;
        return false;
    }

    // 4. Anti-repetição (cooldown + trava de mesmo gesto contínuo)
    int64_t dt = (int64_t)ts_ms - ctx->last_emit_ts_ms;
    if (dt < (int64_t)cfg->cooldown_ms) {
        ctx->last_rejection = GESTURE_REJ_COOLDOWN_ACTIVE;
        ctx->total_windows_rejected++;
        return false;
    }

    if (ctx->has_latched_label && ctx->latched_label == raw_gesture) {
        if (cfg->require_neutral_reset || (dt < (int64_t)(2UL * cfg->cooldown_ms))) {
            ctx->last_rejection = GESTURE_REJ_COOLDOWN_ACTIVE;
            ctx->total_windows_rejected++;
            return false;
        }
    }

    // 5. Aprovação e emissão
    ctx->last_emit_ts_ms = (int64_t)ts_ms;
    ctx->latched_label = raw_gesture;
    ctx->has_latched_label = true;
    ctx->last_rejection = GESTURE_REJ_NONE;
    ctx->total_events_emitted++;
    return true;
}

bool gesture_classifier_ctx_infer(
    GestureClassifierContext *ctx,
    GestureEvent *out_event
) {
    if (!ctx) return false;

    if (!ctx->has_pending_sample) {
        return false;
    }
    ctx->has_pending_sample = false;

    const uint16_t W = (uint16_t)TINYML_WINDOW_SIZE;
    if (ctx->ring_count < W || W > GESTURE_WINDOW_MAX_SAMPLES) {
        ctx->last_rejection = GESTURE_REJ_WINDOW_INCOMPLETE;
        return false;
    }

    // Desenrola as W amostras mais recentes em ordem cronológica estrita [0 .. W-1]
    float ordered_d[GESTURE_WINDOW_MAX_SAMPLES];
    uint32_t ordered_ts[GESTURE_WINDOW_MAX_SAMPLES];
    uint8_t ordered_ir[GESTURE_WINDOW_MAX_SAMPLES];
    uint8_t ordered_inv[GESTURE_WINDOW_MAX_SAMPLES];

    uint16_t start = (uint16_t)((ctx->ring_write_idx + GESTURE_WINDOW_MAX_SAMPLES - W) % GESTURE_WINDOW_MAX_SAMPLES);
    for (uint16_t i = 0U; i < W; ++i) {
        uint16_t idx = (uint16_t)((start + i) % GESTURE_WINDOW_MAX_SAMPLES);
        ordered_d[i] = ctx->ring_dists[idx];
        ordered_ts[i] = ctx->ring_ts[idx];
        ordered_ir[i] = ctx->ring_ir[idx];
        ordered_inv[i] = ctx->ring_inv[idx];
    }

    float feat_vec[TINYML_NUM_FEATURES];
    tinyml_extract_features(ordered_d, ordered_ts, ordered_ir, ordered_inv, W, feat_vec);

    ctx->last_features.d_min           = feat_vec[0];
    ctx->last_features.d_max           = feat_vec[1];
    ctx->last_features.d_mean          = feat_vec[2];
    ctx->last_features.d_std           = feat_vec[3];
    ctx->last_features.d_delta         = feat_vec[4];
    ctx->last_features.v_mean          = feat_vec[5];
    ctx->last_features.v_peak          = feat_vec[6];
    ctx->last_features.trend_slope     = feat_vec[7];
    ctx->last_features.sign_inversions = feat_vec[8];
    ctx->last_features.ir_active_ratio = feat_vec[9];
    ctx->last_features.invalid_ratio   = feat_vec[10];

    float probs[TINYML_NUM_CLASSES];
    int best_cls = tinyml_infer_proba(feat_vec, probs);
    if (best_cls < 0 || best_cls >= TINYML_NUM_CLASSES) {
        best_cls = 0;
    }

    GestureType raw_g = gesture_type_from_string(TINYML_CLASS_NAMES[best_cls]);
    float conf = probs[best_cls];
    if (conf < 0.0f) conf = 0.0f;
    if (conf > 1.0f) conf = 1.0f;

    ctx->last_raw_gesture = raw_g;
    ctx->last_raw_confidence = conf;
    ctx->total_windows_evaluated++;

    uint32_t end_ts = ordered_ts[W - 1U];
    uint32_t start_ts = ordered_ts[0U];
    uint32_t win_span = (end_ts > start_ts) ? (end_ts - start_ts) : 1UL;
    if (win_span > 65535UL) win_span = 65535UL;

    if (!stabilizer_step(ctx, raw_g, conf, end_ts)) {
        return false;
    }

    if (out_event) {
        out_event->gesture = raw_g;
        out_event->confidence = conf;
        out_event->source = GESTURE_SOURCE_TINYML;
        out_event->window_ms = (uint16_t)win_span;
        out_event->timestamp_ms = end_ts;
    }
    return true;
}

void gesture_classifier_init(void) {
    gesture_classifier_ctx_init(&g_default_gesture_ctx, NULL);
}

void gesture_classifier_push_sample(float distance_cm, bool valid_ultrasonic, bool ir_detected, uint32_t ts_ms) {
    gesture_classifier_ctx_push_sample(&g_default_gesture_ctx, distance_cm, valid_ultrasonic, ir_detected, ts_ms);
}

bool gesture_classifier_infer(GestureEvent *out_event) {
    return gesture_classifier_ctx_infer(&g_default_gesture_ctx, out_event);
}
