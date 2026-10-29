#ifndef MOTIONPET_GESTURE_CLASSIFIER_H
#define MOTIONPET_GESTURE_CLASSIFIER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Classes de gestos reconhecidas pelo sistema (ordem canônica alinhada com ml/schemas.py).
 */
typedef enum {
    GESTURE_NEUTRAL = 0,    ///< Repouso, ausência de movimento ou sem detecção
    GESTURE_APPROACH = 1,   ///< Mão se aproximando do sensor
    GESTURE_RETREAT = 2,    ///< Mão se afastando do sensor
    GESTURE_HOLD = 3,       ///< Mão parada na faixa de interesse
    GESTURE_IMPULSE = 4,    ///< Movimento rápido de vai-e-vem (experimental)
    GESTURE_DOUBLE = 5      ///< Duplo movimento consecutivo (experimental)
} GestureType;

/**
 * @brief Origem da classificação gestual.
 */
typedef enum {
    GESTURE_SOURCE_SIM_KEYBOARD = 0,
    GESTURE_SOURCE_SIM_SENSOR = 1,
    GESTURE_SOURCE_RULE_BASELINE = 2,
    GESTURE_SOURCE_TINYML = 3
} GestureSource;

/**
 * @brief Razões explícitas de rejeição ou supressão do estabilizador temporal.
 */
typedef enum {
    GESTURE_REJ_NONE = 0,
    GESTURE_REJ_WINDOW_INCOMPLETE,
    GESTURE_REJ_LOW_CONFIDENCE,
    GESTURE_REJ_NEUTRAL,
    GESTURE_REJ_UNSTABLE_STATE,
    GESTURE_REJ_COOLDOWN_ACTIVE
} GestureRejectionReason;

/**
 * @brief Evento gestual classificado e emitido para a máquina de estados do pet.
 */
typedef struct {
    GestureType gesture;        ///< Gesto classificado
    float confidence;           ///< Confiança da predição [0.0f .. 1.0f]
    GestureSource source;       ///< Motor responsável pela inferência
    uint16_t window_ms;         ///< Janela temporal considerada (em ms)
    uint32_t timestamp_ms;      ///< Timestamp da classificação
} GestureEvent;

// Parâmetros canônicos de janelamento e extração de características (Ciclos 2 e 3)
#define GESTURE_WINDOW_MAX_SAMPLES  16
#define GESTURE_FEATURE_COUNT       11

/**
 * @brief Vetor das 11 características causais extraídas de uma janela temporal 1D.
 * Ordem idêntica a `FEATURE_NAMES` em `ml/schemas.py`.
 */
typedef struct {
    float d_min;
    float d_max;
    float d_mean;
    float d_std;
    float d_delta;
    float v_mean;
    float v_peak;
    float trend_slope;
    float sign_inversions;
    float ir_active_ratio;
    float invalid_ratio;
} GestureFeatures;

/**
 * @brief Configuração do estabilizador causal de eventos (paridade 1:1 com Python `StabilizerConfig`).
 */
typedef struct {
    float min_confidence;
    uint16_t min_consecutive_windows;
    uint32_t cooldown_ms;
    bool require_neutral_reset;
} GestureStabilizerConfig;

/**
 * @brief Contexto completo e estático (zero-heap) do pipeline TinyML embarcado.
 */
typedef struct {
    // Filtro causal de sinal (idêntico a TinyMlCausalFilter / CausalSignalFilter)
    float flt_last_valid;
    bool flt_has_last_valid;
    int16_t flt_hold_count;
    float flt_hist[3];
    int16_t flt_hist_len;
    float flt_ema;
    bool flt_has_ema;

    // Buffer circular de amostras filtradas
    float ring_dists[GESTURE_WINDOW_MAX_SAMPLES];
    uint32_t ring_ts[GESTURE_WINDOW_MAX_SAMPLES];
    uint8_t ring_ir[GESTURE_WINDOW_MAX_SAMPLES];
    uint8_t ring_inv[GESTURE_WINDOW_MAX_SAMPLES];
    uint16_t ring_write_idx;
    uint16_t ring_count;
    uint32_t last_sample_ts_ms;
    bool has_pending_sample;

    // Estabilizador temporal de eventos
    GestureStabilizerConfig stab_cfg;
    int64_t last_emit_ts_ms;
    GestureType consecutive_label;
    bool has_consecutive_label;
    uint16_t consecutive_count;
    GestureType latched_label;
    bool has_latched_label;

    // Telemetria e inspeção da última janela processada
    GestureFeatures last_features;
    GestureType last_raw_gesture;
    float last_raw_confidence;
    GestureRejectionReason last_rejection;
    uint32_t total_windows_evaluated;
    uint32_t total_events_emitted;
    uint32_t total_windows_rejected;
} GestureClassifierContext;

// API orientada a contexto explícito (recomendada para multitarefa FreeRTOS e testes de paridade)
void gesture_classifier_ctx_init(
    GestureClassifierContext *ctx,
    const GestureStabilizerConfig *custom_cfg
);

void gesture_classifier_ctx_push_sample(
    GestureClassifierContext *ctx,
    float distance_cm,
    bool valid_ultrasonic,
    bool ir_detected,
    uint32_t ts_ms
);

bool gesture_classifier_ctx_infer(
    GestureClassifierContext *ctx,
    GestureEvent *out_event
);

// Metadados do modelo TinyML compilado no firmware
const char* gesture_classifier_model_name(void);
const char* gesture_classifier_experimental_status(void);
bool gesture_classifier_is_engineering_synthetic_model(void);

// API global de compatibilidade (opera sobre instância estática padrão)
void gesture_classifier_init(void);
void gesture_classifier_push_sample(float distance_cm, bool valid_ultrasonic, bool ir_detected, uint32_t ts_ms);
bool gesture_classifier_infer(GestureEvent *out_event);
const char* gesture_type_to_string(GestureType gesture);
GestureType gesture_type_from_string(const char *str);
const char* gesture_rejection_to_string(GestureRejectionReason reason);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_GESTURE_CLASSIFIER_H
