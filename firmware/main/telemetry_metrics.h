#ifndef MOTIONPET_TELEMETRY_METRICS_H
#define MOTIONPET_TELEMETRY_METRICS_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Telemetria interna de desempenho, filas, pilhas e saude de tempo real (FreeRTOS).
 *
 * Nota: Nunca impressa como texto solto na serial; exposta apenas sob comando de diagnostico
 * encapsulado em envelope JSON Lines v1 valido (`ack`), preservando pureza do stream JSONL.
 */
typedef struct {
    // Tempos de aquisicao (em microssegundos)
    uint32_t last_acquire_us;
    uint32_t max_acquire_us;
    uint32_t total_samples_acquired;
    uint32_t ultrasonic_timeouts;

    // Tempos de inferencia TinyML (em microssegundos)
    uint32_t last_infer_us;
    uint32_t max_infer_us;
    uint32_t total_windows_inferred;
    uint32_t total_gestures_emitted;
    uint32_t total_windows_rejected;

    // Contadores de perda de amostras e falhas de fila/comunicacao
    uint32_t dropped_sensor_infer_queue;
    uint32_t dropped_sensor_tx_queue;
    uint32_t dropped_gesture_queue;
    uint32_t serial_rx_parse_errors;
    uint32_t serial_rx_overflows;
    uint32_t nvs_save_count;
    uint32_t nvs_load_errors;

    // Ocupacao instantanea das filas
    uint16_t q_sensor_infer_used;
    uint16_t q_sensor_tx_used;
    uint16_t q_gesture_pet_used;
    uint16_t q_cmd_pet_used;

    // Stack high-water mark (bytes livres minimos observados em cada tarefa ESP-IDF)
    uint32_t hwm_sensor_bytes;
    uint32_t hwm_gesture_bytes;
    uint32_t hwm_pet_bytes;
    uint32_t hwm_serial_bytes;
    uint32_t hwm_lcd_bytes;

    // Memoria Heap do sistema
    uint32_t free_heap_bytes;
    uint32_t min_free_heap_bytes;

    // Estado da coleta
    bool collection_active;
    uint32_t sample_period_ms;
} FirmwareRuntimeMetrics;

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_TELEMETRY_METRICS_H
