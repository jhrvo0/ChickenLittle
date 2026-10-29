#ifndef MOTIONPET_SENSORS_DRIVER_H
#define MOTIONPET_SENSORS_DRIVER_H

#include <stdint.h>
#include <stdbool.h>
#include "sensors/sensor_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Interface de abstração de hardware (HAL) para permitir testes determinísticos em host
 *        sem alterar uma linha da lógica embarcada de aquisição e conversão física.
 */
typedef struct {
    void (*configure_pins)(const SensorPinConfig *cfg);
    uint32_t (*measure_echo_us)(uint8_t pin_trig, uint8_t pin_echo, uint32_t timeout_us);
    int (*read_digital)(uint8_t pin);
    uint16_t (*read_adc1_raw)(uint8_t pin);
    uint64_t (*monotonic_us)(void);
} SensorHalOps;

/**
 * @brief Contexto de operação do driver de aquisição de sensores.
 */
typedef struct {
    SensorPinConfig config;
    SensorHalOps hal;
    uint32_t timeout_us;
    uint32_t last_timestamp_ms;
    bool initialized;
} SensorDriverContext;

/**
 * @brief Converte duração do pulso ECHO (µs) em distância (cm) validando limites físicos [2..400 cm].
 */
bool ultrasonic_echo_us_to_cm(uint32_t echo_us, float *out_distance_cm);

/**
 * @brief Normaliza leitura bruta de 12 bits [0..4095] para [0.0f..1.0f] com saturação segura.
 */
float adc1_raw_to_norm(uint16_t raw_value);

/**
 * @brief Inicializa o driver de sensores (usa HAL nativa ESP32 quando `custom_hal == NULL`).
 */
bool sensors_driver_init(
    SensorDriverContext *ctx,
    const SensorPinConfig *cfg,
    const SensorHalOps *custom_hal
);

/**
 * @brief Executa uma leitura completa e não-travante do HC-SR04, TCRT5000 e potenciômetro ADC1.
 */
void sensors_driver_read(SensorDriverContext *ctx, SensorRawFrame *out_frame);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_SENSORS_DRIVER_H
