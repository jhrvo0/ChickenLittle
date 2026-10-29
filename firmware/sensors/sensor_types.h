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
#define ULTRASONIC_MIN_ECHO_US        115UL     // ~2.0 cm (pulsos menores indicam ruído/curto)
#define ULTRASONIC_MAX_ECHO_US        23324UL   // ~400.0 cm a 343 m/s
#define ULTRASONIC_SAMPLE_INTERVAL_MS 70UL      // Período padrão seguro (faixa 60..80 ms)

// Resolução do Conversor Analógico-Digital do ESP32 (ADC1: 12 bits)
#define ADC_MAX_RAW_VALUE             4095.0f

/**
 * @brief Estrutura unificada com as leituras físicas do ciclo de sensoriamento.
 */
typedef struct {
    float distance_cm;              ///< Distância estimada em cm (ou -1.0f se inválido/timeout)
    bool valid_ultrasonic;          ///< Verdadeiro se eco foi captado dentro da janela física
    bool ir_detected;               ///< Verdadeiro se TCRT5000 detectou reflexão próxima
    float pot_norm;                 ///< Leitura normalizada do potenciômetro [0.0f .. 1.0f]
    uint16_t pot_raw;               ///< Leitura bruta de 12 bits do ADC1 [0 .. 4095]
    uint32_t timestamp_ms;          ///< Timestamp monotônico em milissegundos da aquisição
    uint32_t echo_duration_us;      ///< Largura bruta do pulso ECHO em microssegundos (0 se timeout)
    uint16_t ir_analog_raw;         ///< Leitura analógica opcional AO do TCRT5000 [0 .. 4095]
    float ir_analog_norm;           ///< Leitura analógica normalizada do TCRT5000 [0.0f .. 1.0f]
    uint32_t acquire_duration_us;   ///< Tempo total gasto na leitura dos sensores (µs)
} SensorRawFrame;

/**
 * @brief Configuração de pinos e opções elétricas para os sensores.
 */
typedef struct {
    uint8_t pin_us_trig;            ///< GPIO de saída para pulso de disparo TRIG (3.3 V)
    uint8_t pin_us_echo;            ///< GPIO de entrada (GPI) com divisor resistivo para ECHO
    uint8_t pin_ir_digital;         ///< GPIO de entrada digital para saída DO do TCRT5000 (3.3 V)
    uint8_t pin_pot_adc;            ///< GPIO de entrada analógica no bloco ADC1
    int8_t pin_ir_analog;           ///< GPIO ADC1 opcional para AO do TCRT5000 (-1 se desabilitado)
    bool ir_enabled;                ///< Habilita leitura do TCRT5000
    bool ir_analog_enabled;         ///< Habilita leitura analógica AO do TCRT5000 no ADC1
    bool ir_active_low;             ///< true se DO vai a LOW ao detectar obstáculo (padrão LM393)
    bool pot_enabled;               ///< Habilita leitura analógica do potenciômetro no ADC1
} SensorPinConfig;

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_SENSOR_TYPES_H
