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
 * @brief Evento gestual classificado e emitido para a máquina de estados do pet.
 */
typedef struct {
    GestureType gesture;        ///< Gesto classificado
    float confidence;           ///< Confiança da predição [0.0f .. 1.0f]
    GestureSource source;       ///< Motor responsável pela inferência
    uint16_t window_ms;         ///< Janela temporal considerada (em ms)
    uint32_t timestamp_ms;      ///< Timestamp da classificação
} GestureEvent;

// Parâmetros canônicos de janelamento e extração de características (Ciclo 2/3)
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

void gesture_classifier_init(void);
void gesture_classifier_push_sample(float distance_cm, bool valid_ultrasonic, bool ir_detected, uint32_t ts_ms);
bool gesture_classifier_infer(GestureEvent *out_event);
const char* gesture_type_to_string(GestureType gesture);
GestureType gesture_type_from_string(const char *str);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_GESTURE_CLASSIFIER_H
