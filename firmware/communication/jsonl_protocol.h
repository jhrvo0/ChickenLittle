#ifndef MOTIONPET_JSONL_PROTOCOL_H
#define MOTIONPET_JSONL_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include "sensors/sensor_types.h"
#include "gestures/gesture_classifier.h"
#include "display/lcd2004_driver.h"
#include "pet/pet_state.h"

#ifdef __cplusplus
extern "C" {
#endif

#define JSONL_PROTOCOL_VERSION  1
#define JSONL_LINE_BUFFER_SIZE  384   ///< Tamanho estático máximo seguro por linha (sem heap)

/**
 * @brief Estado interno e estatísticas do motor de protocolo JSON Lines.
 */
typedef struct {
    uint32_t seq_tx;            ///< Contador de sequência de transmissão incremental
    uint32_t seq_rx_last;       ///< Último número de sequência recebido com sucesso
    uint32_t dropped_frames;    ///< Contador de saltos detectados no sequenciamento
    uint32_t parse_errors;      ///< Total de linhas inválidas descartadas
} JsonlContext;

/**
 * @brief Inicializa o contexto de comunicação do protocolo.
 */
void jsonl_init(JsonlContext *ctx);

/**
 * @brief Serializa um quadro de leituras de sensores para uma string JSON Lines.
 */
bool jsonl_serialize_sensor_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const SensorRawFrame *frame
);

/**
 * @brief Serializa um evento de gesto classificado.
 */
bool jsonl_serialize_gesture_event(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const GestureEvent *event
);

/**
 * @brief Serializa o snapshot completo de estado do pet.
 */
bool jsonl_serialize_pet_state(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const PetStateSnapshot *state
);

/**
 * @brief Serializa o quadro do display LCD para espelhamento no terminal host.
 */
bool jsonl_serialize_lcd_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const LCDFrameBuffer *lcd
);

/**
 * @brief Serializa uma mensagem de confirmação (ACK).
 */
bool jsonl_serialize_ack(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    uint32_t ref_seq,
    const char *status
);

/**
 * @brief Serializa uma notificação de erro ou diagnóstico.
 */
bool jsonl_serialize_error(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const char *err_code,
    const char *err_message
);

/**
 * @brief Decodifica uma linha recebida pela serial buscando por um comando pet_command.
 * @param line Linha JSON crua (terminada com ou sem \n)
 * @param out_cmd Comando identificado
 * @param out_seq Número de seq da mensagem recebida
 * @return true se o comando foi decodificado com sucesso
 */
bool jsonl_parse_pet_command(
    JsonlContext *ctx,
    const char *line,
    PetCommandType *out_cmd,
    uint32_t *out_seq
);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_JSONL_PROTOCOL_H
