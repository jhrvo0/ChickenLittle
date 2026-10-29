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
#define JSONL_LINE_BUFFER_SIZE  512   ///< Tamanho estático máximo seguro por linha (zero heap)

/**
 * @brief Estado interno e estatísticas do motor de protocolo JSON Lines v1.
 */
typedef struct {
    uint32_t seq_tx;            ///< Contador de sequência de transmissão incremental (inicia em 1)
    uint32_t seq_rx_last;       ///< Último número de sequência recebido com sucesso
    uint32_t dropped_frames;    ///< Contador de saltos detectados no sequenciamento
    uint32_t parse_errors;      ///< Total de linhas inválidas descartadas
    bool has_rx_seq;            ///< Indica se já recebeu ao menos um quadro numerado
} JsonlContext;

/**
 * @brief Tipos de mensagem ou controle recebidos pela porta serial (Host -> ESP32).
 */
typedef enum {
    RX_MSG_INVALID = 0,
    RX_MSG_PET_COMMAND,         ///< Envelope JSONL `pet_command` padrão
    RX_MSG_GESTURE_INJECT,      ///< Envelope JSONL `gesture_event` injetado
    RX_MSG_ACQ_START,           ///< Iniciar transmissão de `sensor_frame`
    RX_MSG_ACQ_STOP,            ///< Pausar transmissão de `sensor_frame`
    RX_MSG_ACQ_SET_PERIOD,      ///< Ajustar período de amostragem em ms (ex: 60..80 ms)
    RX_MSG_ACQ_SET_IR,          ///< Habilitar/desabilitar leitura do TCRT5000
    RX_MSG_DIAG_REQUEST         ///< Solicitar resumo de telemetria FreeRTOS em envelope `ack`
} JsonlRxKind;

/**
 * @brief Resultado estruturado da decodificação não-bloqueante de uma linha recebida.
 */
typedef struct {
    JsonlRxKind kind;
    uint32_t seq;
    PetCommandType pet_cmd;
    char mode_arg[20];
    GestureEvent injected_gesture;
    uint32_t param_u32;
    bool param_bool;
    char error_code[24];
    char error_msg[64];
} JsonlRxParsed;

void jsonl_init(JsonlContext *ctx);

bool jsonl_serialize_sensor_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const SensorRawFrame *frame
);

bool jsonl_serialize_gesture_event(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const GestureEvent *event
);

bool jsonl_serialize_pet_state(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const PetStateSnapshot *state
);

bool jsonl_serialize_lcd_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const LCDFrameBuffer *lcd
);

bool jsonl_serialize_ack(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    uint32_t ack_seq,
    const char *status
);

bool jsonl_serialize_error_ex(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const char *err_code,
    const char *err_message,
    int64_t ref_seq
);

bool jsonl_serialize_error(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const char *err_code,
    const char *err_message
);

bool jsonl_parse_pet_command(
    JsonlContext *ctx,
    const char *line,
    PetCommandType *out_cmd,
    uint32_t *out_seq
);

bool jsonl_parse_incoming_line(
    JsonlContext *ctx,
    const char *line,
    JsonlRxParsed *out_parsed
);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_JSONL_PROTOCOL_H
