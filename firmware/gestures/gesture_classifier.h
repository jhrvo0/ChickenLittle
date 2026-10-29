#ifndef MOTIONPET_GESTURE_CLASSIFIER_H
#define MOTIONPET_GESTURE_CLASSIFIER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Classes de gestos reconhecidas pelo sistema.
 */
typedef enum {
    GESTURE_NEUTRAL = 0,    ///< Repouso, ausência de movimento ou sem detecção
    GESTURE_APPROACH,       ///< Mão se aproximando rapidamente do sensor
    GESTURE_RETREAT,        ///< Mão se afastando do sensor
    GESTURE_HOLD,           ///< Mão parada na faixa de interesse (10 a 25 cm)
    GESTURE_IMPULSE,        ///< Movimento balístico rápido de vai-e-vem
    GESTURE_DOUBLE          ///< Duplo toque aéreo em intervalo curto
} GestureType;

/**
 * @brief Origem da classificação gestual.
 */
typedef enum {
    GESTURE_SOURCE_SIM_KEYBOARD = 0,
    GESTURE_SOURCE_SIM_SENSOR,
    GESTURE_SOURCE_RULE_BASELINE,
    GESTURE_SOURCE_TINYML
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

// Parâmetros de janelamento e extração de características (Ciclo 2/3)
#define GESTURE_WINDOW_MAX_SAMPLES  16
#define GESTURE_FEATURE_COUNT       8

/**
 * @brief Vetor de características extraídas de uma janela temporal.
 */
typedef struct {
    float d_min;
    float d_max;
    float d_delta;
    float d_mean;
    float d_std;
    float v_mean;
    float v_peak;
    uint8_t sign_inversions;
} GestureFeatures;

/**
 * @brief Inicializa o classificador de gestos.
 */
void gesture_classifier_init(void);

/**
 * @brief Insere uma nova amostra de distância no buffer circular de janelamento.
 * @param distance_cm Distância em cm (ou < 0 se medição inválida/timeout)
 * @param ts_ms Timestamp da leitura em milissegundos
 */
void gesture_classifier_push_sample(float distance_cm, uint32_t ts_ms);

/**
 * @brief Executa inferência sobre a janela temporal corrente.
 * @param out_event Ponteiro para gravação do evento gerado
 * @return true se um novo gesto com confiança suficiente foi detectado
 */
bool gesture_classifier_infer(GestureEvent *out_event);

/**
 * @brief Converte GestureType para string literal conforme especificação do protocolo JSONL.
 */
const char* gesture_type_to_string(GestureType gesture);

/**
 * @brief Converte string do protocolo JSONL para GestureType.
 */
GestureType gesture_type_from_string(const char *str);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_GESTURE_CLASSIFIER_H
