/*
 * AUTO-GENERATED FILE — DO NOT EDIT MANUALLY
 * MotionPet TinyML Static Header (`tinyml_model.h`)
 * Model: mlp_compact
 * Experimental Data Status: AWAITING_REAL_DATA
 * WARNING: MODELO DE ENGENHARIA (TREINADO EM DADOS SINTETICOS) — AINDA NAO VALIDADO EXPERIMENTALMENTE.
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
static inline float tinyml_fabsf(float x) {
    return (x < 0.0f) ? -x : x;
}

static inline float tinyml_sqrtf(float x) {
    if (x <= 0.0f) return 0.0f;
    double norm = (double)x;
    double scale = 1.0;
    while (norm >= 4.0) { norm *= 0.25; scale *= 2.0; }
    while (norm < 0.25) { norm *= 4.0; scale *= 0.5; }
    double g = 1.0;
    for (int i = 0; i < 7; ++i) {
        g = 0.5 * (g + norm / g);
    }
    return (float)(g * scale);
}

static inline float tinyml_expf(float x) {
    if (x <= -88.0f) return 0.0f;
    if (x >= 88.0f) return 1.65163625e38f;
    const double inv_ln2 = 1.44269504088896340736;
    const double ln2 = 0.69314718055994530942;
    double xd = (double)x;
    int k = (int)(xd * inv_ln2 + (xd >= 0.0 ? 0.5 : -0.5));
    double r = xd - (double)k * ln2;
    double term = 1.0;
    double sum = 1.0;
    for (int n = 1; n <= 10; ++n) {
        term *= r / (double)n;
        sum += term;
    }
    if (k >= 0) {
        while (k >= 30) { sum *= (double)(1U << 30); k -= 30; }
        sum *= (double)(1U << k);
    } else {
        int nk = -k;
        while (nk >= 30) { sum /= (double)(1U << 30); nk -= 30; }
        sum /= (double)(1U << nk);
    }
    return (float)sum;
}
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define TINYML_MODEL_NAME                     "mlp_compact"
#define TINYML_EXPERIMENTAL_STATUS            "AWAITING_REAL_DATA"
#define TINYML_IS_ENGINEERING_SYNTHETIC_MODEL 1

#define TINYML_NUM_FEATURES 11
#define TINYML_NUM_CLASSES  4
#define TINYML_WINDOW_SIZE  10

static const char* const TINYML_CLASS_NAMES[TINYML_NUM_CLASSES] = { "NEUTRAL", "APPROACH", "RETREAT", "HOLD" };

/* Parametros causais identicos ao treinamento Python (`PreprocessingConfig`) */
#define TINYML_MIN_VALID_CM          2.00000000e+00f
#define TINYML_MAX_VALID_CM          4.00000000e+02f
#define TINYML_SATURATION_CM         1.00000000e+02f
#define TINYML_MAX_HOLD_STEPS        2
#define TINYML_EMA_ALPHA             6.50000000e-01f
#define TINYML_INVERSION_DEADBAND_CM 8.00000000e-01f

typedef struct {
    float last_valid;
    bool has_last_valid;
    int16_t hold_count;
    float hist[3];
    int16_t hist_len;
    float ema;
    bool has_ema;
} TinyMlCausalFilter;

static inline void tinyml_filter_reset(TinyMlCausalFilter *f) {
    f->last_valid = 0.0f;
    f->has_last_valid = false;
    f->hold_count = 0;
    f->hist[0] = 0.0f;
    f->hist[1] = 0.0f;
    f->hist[2] = 0.0f;
    f->hist_len = 0;
    f->ema = 0.0f;
    f->has_ema = false;
}

static inline float tinyml_median_up_to_3(const float *v, int16_t n) {
    if (n <= 1) return v[0];
    if (n == 2) return 0.5f * (v[0] + v[1]);
    float a = v[0], b = v[1], c = v[2], t;
    if (a > b) { t = a; a = b; b = t; }
    if (b > c) { t = b; b = c; c = t; }
    if (a > b) { t = a; a = b; b = t; }
    return b;
}

static inline float tinyml_filter_step(
    TinyMlCausalFilter *f,
    float distance_cm,
    bool valid_ultrasonic,
    bool *out_was_invalid
) {
    bool ok = valid_ultrasonic && (distance_cm >= TINYML_MIN_VALID_CM) && (distance_cm <= TINYML_MAX_VALID_CM);
    float raw_val;
    if (ok) {
        raw_val = distance_cm;
        f->last_valid = raw_val;
        f->has_last_valid = true;
        f->hold_count = 0;
        if (out_was_invalid) *out_was_invalid = false;
    } else {
        if (out_was_invalid) *out_was_invalid = true;
        if (f->has_last_valid && f->hold_count < TINYML_MAX_HOLD_STEPS) {
            f->hold_count += 1;
            raw_val = f->last_valid;
        } else {
            raw_val = TINYML_SATURATION_CM;
        }
    }

    if (raw_val < TINYML_MIN_VALID_CM) raw_val = TINYML_MIN_VALID_CM;
    if (raw_val > TINYML_SATURATION_CM) raw_val = TINYML_SATURATION_CM;

    if (f->hist_len < 3) {
        f->hist[f->hist_len++] = raw_val;
    } else {
        f->hist[0] = f->hist[1];
        f->hist[1] = f->hist[2];
        f->hist[2] = raw_val;
    }

    float med = tinyml_median_up_to_3(f->hist, f->hist_len);
    if (!f->has_ema) {
        f->ema = med;
        f->has_ema = true;
    } else {
        f->ema = TINYML_EMA_ALPHA * med + (1.0f - TINYML_EMA_ALPHA) * f->ema;
    }
    return f->ema;
}

static inline void tinyml_extract_features(
    const float *distances_cm,
    const uint32_t *timestamps_ms,
    const uint8_t *ir_flags,
    const uint8_t *invalid_flags,
    uint16_t n,
    float out_features[TINYML_NUM_FEATURES]
) {
    if (n == 0) {
        for (uint16_t k = 0; k < TINYML_NUM_FEATURES; ++k) {
            out_features[k] = 0.0f;
        }
        return;
    }
    float d_min = distances_cm[0];
    float d_max = distances_cm[0];
    float d_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {
        float d = distances_cm[i];
        if (d < d_min) d_min = d;
        if (d > d_max) d_max = d;
        d_sum += d;
    }
    float d_mean = d_sum / (float)n;

    float var_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {
        float diff = distances_cm[i] - d_mean;
        var_sum += diff * diff;
    }
    float d_std = tinyml_sqrtf(var_sum / (float)n);

    float d_delta = distances_cm[n - 1] - distances_cm[0];
    float total_dt_s = ((float)(timestamps_ms[n - 1] - timestamps_ms[0])) / 1000.0f;
    if (total_dt_s < 1e-3f) total_dt_s = 1e-3f;
    float v_mean = d_delta / total_dt_s;

    float v_peak = 0.0f;
    int16_t inversions = 0;
    int8_t prev_sign = 0;
    for (uint16_t i = 0; i + 1 < n; ++i) {
        float step_d = distances_cm[i + 1] - distances_cm[i];
        float step_dt_s = ((float)(timestamps_ms[i + 1] - timestamps_ms[i])) / 1000.0f;
        if (step_dt_s < 1e-3f) step_dt_s = 1e-3f;
        float v_inst = step_d / step_dt_s;
        if (tinyml_fabsf(v_inst) > tinyml_fabsf(v_peak)) {
            v_peak = v_inst;
        }
        if (tinyml_fabsf(step_d) >= TINYML_INVERSION_DEADBAND_CM) {
            int8_t sign = (step_d > 0.0f) ? 1 : -1;
            if (prev_sign != 0 && sign != prev_sign) {
                inversions += 1;
            }
            prev_sign = sign;
        }
    }

    uint32_t t0 = timestamps_ms[0];
    float t_sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {
        t_sum += ((float)(timestamps_ms[i] - t0)) / 1000.0f;
    }
    float t_mean = t_sum / (float)n;
    float cov_td = 0.0f;
    float var_t = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {
        float rt = ((float)(timestamps_ms[i] - t0)) / 1000.0f;
        float dt_c = rt - t_mean;
        cov_td += dt_c * (distances_cm[i] - d_mean);
        var_t += dt_c * dt_c;
    }
    float trend_slope = (var_t > 1e-9f) ? (cov_td / var_t) : 0.0f;

    uint16_t ir_cnt = 0;
    uint16_t inv_cnt = 0;
    for (uint16_t i = 0; i < n; ++i) {
        if (ir_flags[i]) ir_cnt += 1;
        if (invalid_flags[i]) inv_cnt += 1;
    }

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
}

#define TINYML_MLP_LAYERS 3
#define TINYML_MLP_MAX_WIDTH 16
static const float TINYML_SCALER_MEAN[TINYML_NUM_FEATURES] = { 3.40503178e+01f, 7.38759048e+01f, 5.45830395e+01f, 1.47702126e+01f, -4.62879411e-01f, -6.86306800e-01f, -3.81034489e-01f, -4.56103760e-01f, 4.98956159e-01f, 4.98956159e-02f, 5.21920668e-02f };
static const float TINYML_SCALER_SCALE[TINYML_NUM_FEATURES] = { 2.45498686e+01f, 2.12258538e+01f, 2.33097552e+01f, 1.08105424e+01f, 4.59385820e+01f, 6.79419526e+01f, 4.13450534e+02f, 7.12113195e+01f, 7.66944263e-01f, 1.17360451e-01f, 6.92217147e-02f };
static const float TINYML_W0[176] = { 2.40552661e-02f, 2.99324526e-01f, 2.14392601e-01f, -1.63981479e-01f, 1.39485925e-01f, -3.54867368e-01f, -4.80839146e-01f, 3.69951906e-01f, -3.39402528e-01f, 2.97219874e-01f, -4.94177260e-01f, 3.11921195e-01f, 1.22620329e-01f, -7.94902959e-02f, -4.98155853e-01f, -6.61082996e-01f, -8.48665570e-02f, -3.13476148e-01f, -4.14495723e-01f, -3.57539001e-01f, -1.16870604e-01f, -1.16341180e-01f, -2.92173772e-01f, 1.11905840e-01f, 5.75009682e-02f, -7.15895606e-02f, -2.78474013e-01f, -4.44173588e-01f, 2.22218865e-02f, -4.75207180e-01f, -2.07910835e-01f, -2.14181311e-01f, -9.61119615e-01f, 3.03333897e-01f, 8.05498283e-01f, 7.84532920e-01f, 1.30102033e-01f, -3.66132773e-01f, 2.82703347e-01f, -4.99467734e-01f, -9.74071070e-01f, 1.86216785e-01f, -1.01513679e+00f, 6.63032531e-01f, -5.29882235e-01f, -1.01327345e-01f, 1.46570887e-01f, 5.69035914e-01f, 2.07122056e-01f, -5.56798412e-01f, 2.28225130e-01f, 1.43996738e-01f, -1.93511469e-01f, 8.17884944e-01f, 2.01790983e-01f, 4.57456804e-01f, -5.47560107e-01f, -5.52261847e-01f, -9.11952852e-02f, -2.35914841e-01f, 1.78821439e-01f, -1.68388305e-01f, 3.92629097e-01f, -1.45060472e-01f, -1.20680801e-01f, 4.26886436e-01f, -1.59107398e-01f, 3.32696482e-01f, -8.12605037e-01f, 4.11899517e-01f, 2.35037119e-01f, -8.84348263e-02f, -4.87150166e-01f, 4.18501721e-01f, 3.71413424e-01f, -2.45404136e-02f, 2.39954511e-01f, -4.72637739e-01f, -9.23801264e-02f, -3.25140747e-01f, 4.31601041e-01f, 5.04227845e-01f, 1.83271390e-02f, -3.65963376e-01f, -5.95136124e-01f, -2.03514015e-01f, 1.92322145e-01f, 3.25503628e-01f, 3.50855531e-01f, 8.73203318e-02f, -1.74592759e-01f, -2.87026516e-02f, 2.14875619e-01f, 1.93973156e-03f, 2.93543292e-01f, 2.95809121e-02f, -2.13761807e-01f, -1.85005907e-01f, -2.21785754e-01f, -5.49276169e-01f, -1.74145826e-01f, -1.39375933e-01f, -2.47840667e-01f, -4.71083188e-01f, 8.86266049e-01f, -4.94511677e-01f, -7.62123989e-01f, -2.71371791e-01f, -7.81926890e-01f, -5.33061507e-01f, -1.16731058e-01f, -1.84654053e-01f, 4.13521998e-01f, 6.49851672e-01f, 5.70106718e-01f, 6.51021703e-01f, -1.10763117e-02f, -1.42084088e-01f, 4.21812649e-01f, -1.93531358e-01f, -5.74229147e-02f, 7.35892878e-01f, -2.99757490e-01f, -1.58992654e-01f, -3.66896089e-01f, -1.35849492e-01f, 4.35260069e-01f, 5.71827996e-01f, -7.63074630e-01f, -5.69320189e-01f, 2.36234244e-01f, -7.69364401e-01f, -1.00288692e+00f, -6.29212640e-01f, 4.86632847e-01f, -3.22488758e-01f, -2.74628674e-02f, 1.97626688e-03f, -3.00382628e-01f, 9.20953227e-01f, 5.75555861e-01f, -4.29746375e-01f, 2.62298891e-01f, -5.79388349e-02f, -1.21661031e-01f, -3.52826658e-01f, 1.69483992e-01f, 8.22693754e-03f, -6.97787475e-01f, 1.12539388e-01f, 5.55011003e-01f, -3.42273041e-01f, -2.25311933e-01f, -1.82876155e-01f, 4.60272379e-01f, 1.19905739e-01f, 7.20159187e-02f, 2.64934046e-01f, -1.52648838e-01f, 1.96032256e-01f, 3.72897418e-03f, -1.45806798e-01f, 4.41193264e-02f, 3.25527589e-01f, -1.61586328e-02f, -7.05598075e-02f, 4.84914927e-02f, -8.24971002e-03f, -3.83647859e-01f, 3.23241609e-02f, 3.39066822e-01f, -5.35213421e-01f, -1.85008226e-01f, -1.09949987e-01f, 2.41488153e-02f, -3.57864834e-01f };
static const float TINYML_B0[16] = { 1.14892980e-01f, -1.69803568e-01f, 6.73227595e-01f, 1.64250711e-01f, 3.27673071e-02f, -6.37926312e-01f, 5.48725843e-01f, 4.13799355e-01f, 1.93533980e-01f, 4.34578841e-01f, 3.84459732e-01f, 1.43321313e-01f, -1.67762932e-01f, -5.87108945e-01f, -2.65350936e-01f, 8.45514993e-01f };
static const float TINYML_W1[128] = { 5.88398730e-01f, 2.31622374e-01f, -3.82008577e-01f, -4.68102546e-01f, 6.08957058e-02f, 5.84682747e-01f, 3.99842583e-01f, 5.57344788e-01f, 7.68441591e-01f, 4.69467301e-01f, -2.78334937e-01f, 5.34416246e-01f, -1.51276889e-01f, -1.34351091e+00f, -1.40892434e-01f, 1.45895798e-01f, -3.25636214e-01f, -4.70886513e-01f, 3.62456128e-01f, 6.39558689e-01f, 1.58867160e-01f, -5.98266768e-01f, 5.51865198e-01f, -4.61815355e-01f, -2.97310767e-01f, 1.18978525e+00f, 6.99368100e-01f, 8.89511993e-01f, 9.30873481e-01f, -1.04547835e+00f, -5.72383387e-02f, -4.41498425e-01f, -3.07330953e-01f, -9.96366970e-01f, 5.42632588e-01f, 1.48104990e-01f, 2.22633774e-01f, 8.07900401e-01f, 3.66369720e-01f, 2.73107161e-02f, 7.43201850e-01f, -4.10346703e-02f, -6.08054982e-01f, 9.94469870e-02f, -7.39844818e-01f, -2.02948685e-01f, 6.68971648e-01f, -1.17363165e-01f, 4.21299309e-01f, 5.87714146e-01f, 6.54995366e-01f, 4.73569226e-01f, -2.13711503e-01f, 3.43520192e-01f, 2.34407345e-01f, 3.92878347e-01f, 4.69975645e-01f, 7.24734181e-01f, -4.60191505e-01f, -3.12899570e-01f, 1.81717998e-01f, 2.36641395e-01f, -5.75292456e-01f, 3.84542498e-01f, 1.09461831e-01f, -1.31785825e-01f, 2.00997860e-01f, -7.24434683e-01f, 2.46452300e-01f, 1.19390217e+00f, -6.05885826e-01f, 9.97402158e-02f, 8.56293272e-01f, 1.12470960e+00f, 3.28866536e-01f, 4.08682823e-01f, -7.20966718e-03f, -7.34427480e-01f, 5.81124797e-01f, 3.15628924e-01f, 5.29976501e-01f, 5.55158727e-01f, -1.82557701e-01f, -2.11082294e-01f, 1.93646107e-01f, 4.71275717e-01f, 1.76829369e-01f, 6.11332897e-01f, 7.50644621e-01f, -6.44634023e-01f, 1.06459060e-01f, 1.30375540e-02f, -6.38103170e-02f, -7.07670077e-01f, 2.52113539e-01f, -5.21401276e-02f, 3.14243204e-01f, 7.98849772e-01f, -8.68215746e-01f, -4.50888343e-01f, 3.90074523e-01f, -9.03530913e-01f, -6.26410826e-01f, 2.50869587e-01f, 4.03324504e-01f, -4.98142203e-01f, 1.50284310e-01f, -2.23019402e-02f, -6.04239050e-01f, 3.78327707e-01f, 3.34160149e-01f, 5.95850178e-02f, 4.35986590e-02f, -6.50014419e-04f, 2.22330553e-01f, 1.27636676e-01f, 4.24210533e-01f, -2.93002013e-02f, 1.89202881e-01f, -5.74571512e-01f, -6.68684981e-01f, 9.29001344e-01f, 7.67080098e-01f, 8.62046726e-01f, 2.31327839e-01f, -8.59659287e-01f, -6.81191599e-02f, -3.64872367e-01f };
static const float TINYML_B1[8] = { -2.92709125e-01f, 2.43315667e-01f, 4.81928925e-01f, 1.17940446e-02f, 7.61154848e-01f, 5.43920853e-01f, 6.55578184e-02f, 1.01113844e-01f };
static const float TINYML_W2[32] = { -1.19918344e-01f, -7.41168896e-01f, -1.37872088e-01f, 5.84799520e-01f, -6.59658094e-01f, -1.02927348e+00f, -3.73860295e-02f, -8.75566293e-01f, 9.39558992e-01f, 4.35804605e-01f, -5.23106071e-01f, -1.23674616e+00f, 4.67393924e-01f, -4.86637885e-01f, -9.95361527e-01f, -5.52204395e-01f, -1.21592171e-01f, 2.76802460e-01f, 1.58817321e-01f, -9.06162293e-01f, -7.24993133e-01f, 8.44234272e-01f, -5.66344624e-01f, 7.20913711e-01f, 6.76070268e-01f, -8.86754176e-01f, -1.09192777e+00f, 4.63019266e-01f, -8.69868820e-01f, -1.84577930e-02f, 7.79831332e-01f, 3.39072738e-01f };
static const float TINYML_B2[4] = { -7.80311992e-02f, 2.81612477e-01f, -2.17434990e-01f, -1.41020770e-01f };

static inline int tinyml_infer_proba(
    const float features[TINYML_NUM_FEATURES],
    float out_probs[TINYML_NUM_CLASSES]
) {
    float cur[TINYML_MLP_MAX_WIDTH];
    float nxt[TINYML_MLP_MAX_WIDTH];

    for (int i = 0; i < TINYML_NUM_FEATURES; ++i) {
        cur[i] = (features[i] - TINYML_SCALER_MEAN[i]) / TINYML_SCALER_SCALE[i];
    }

    for (int o = 0; o < 16; ++o) {
        float acc = TINYML_B0[o];
        for (int i = 0; i < 11; ++i) {
            acc += cur[i] * TINYML_W0[i * 16 + o];
        }
        if (acc < 0.0f) acc = 0.0f;
        nxt[o] = acc;
    }
    for (int o = 0; o < 16; ++o) { cur[o] = nxt[o]; }

    for (int o = 0; o < 8; ++o) {
        float acc = TINYML_B1[o];
        for (int i = 0; i < 16; ++i) {
            acc += cur[i] * TINYML_W1[i * 8 + o];
        }
        if (acc < 0.0f) acc = 0.0f;
        nxt[o] = acc;
    }
    for (int o = 0; o < 8; ++o) { cur[o] = nxt[o]; }

    for (int o = 0; o < 4; ++o) {
        float acc = TINYML_B2[o];
        for (int i = 0; i < 8; ++i) {
            acc += cur[i] * TINYML_W2[i * 4 + o];
        }
        
        nxt[o] = acc;
    }
    for (int o = 0; o < 4; ++o) { cur[o] = nxt[o]; }

    float max_logit = cur[0];
    for (int c = 1; c < TINYML_NUM_CLASSES; ++c) {
        if (cur[c] > max_logit) max_logit = cur[c];
    }
    float sum_exp = 0.0f;
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {
        out_probs[c] = tinyml_expf(cur[c] - max_logit);
        sum_exp += out_probs[c];
    }
    int best_cls = 0;
    for (int c = 0; c < TINYML_NUM_CLASSES; ++c) {
        out_probs[c] /= sum_exp;
        if (out_probs[c] > out_probs[best_cls]) {
            best_cls = c;
        }
    }
    return best_cls;
}

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
