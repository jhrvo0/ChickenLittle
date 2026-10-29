#ifndef MOTIONPET_SENSOR_TYPES_H
#define MOTIONPET_SENSOR_TYPES_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Limiares físicos e temporizações do sensor HC-SR04
#define ULTRASONIC_MIN_DISTANCE_CM    2.0f
#define ULTRASONIC_MAX_DISTANCE_CM    400.0f
#define ULTRASONIC_TIMEOUT_US         25000UL   // 25 ms (~4.3 metros)
#define ULTRASONIC_SAMPLE_INTERVAL_MS 50UL      // 20 Hz de amostragem máxima recomendada

// Resolução do Conversor Analógico-Digital do ESP32 (ADC1)
#define ADC_MAX_RAW_VALUE             4095.0f

/**
 * @brief Estrutura unificada com as leituras físicas do ciclo de sensoriamento.
 */
typedef struct {
    float distance_cm;          ///< Distância estimada em cm (ou < 0 se inválido)
    bool valid_ultrasonic;      ///< Verdadeiro se eco foi captado sem timeout
    bool ir_detected;           ///< Verdadeiro se TCRT5000 detectou reflexão próxima
    float pot_norm;             ///< Leitura normalizada do potenciômetro [0.0f .. 1.0f]
    uint16_t pot_raw;           ///< Leitura bruta de 12 bits do ADC1 [0 .. 4095]
    uint32_t timestamp_ms;      ///< Timestamp em milissegundos da aquisição
} SensorRawFrame;

/**
 * @brief Configuração de pinos de hardware para os sensores.
 */
typedef struct {
    uint8_t pin_us_trig;        ///< GPIO de saída para pulso de disparo TRIG
    uint8_t pin_us_echo;        ///< GPIO de entrada (GPI) com divisor resistivo para ECHO
    uint8_t pin_ir_digital;     ///< GPIO de entrada digital para saída DO do TCRT5000
    uint8_t pin_pot_adc;        ///< GPIO de entrada analógica no bloco ADC1
} SensorPinConfig;

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_SENSOR_TYPES_H
