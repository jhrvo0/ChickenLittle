#ifndef MOTIONLAB_IOT_CORE_H
#define MOTIONLAB_IOT_CORE_H

#include <stdint.h>
#include <stddef.h>
#include "sensors/sensor_types.h"

// Portable, bounded transport state. Caller serializes queue access, never network I/O.
#define IOT_QUEUE_CAPACITY 32U
#define IOT_PAYLOAD_CAPACITY 1024U
#define IOT_RETRY_MIN_MS 1000U
#define IOT_RETRY_MAX_MS 60000U
#define IOT_CONNECT_TIMEOUT_MS 10000U
#define IOT_ACK_TIMEOUT_MS 10000U

struct IotSample {
    uint64_t sample_idx;
    uint64_t ts_ms;
    uint64_t dropped_total;
    float distance_cm;
    bool valid_ultrasonic;
    bool ir_detected;
    bool valid_ir;
};

struct IotSampleQueue {
    IotSample samples[IOT_QUEUE_CAPACITY];
    uint64_t next_sequence;
    uint64_t dropped_total;
    uint64_t acknowledged_total;
    uint16_t head;
    uint16_t used;
};

enum IotConnectionState {
    IOT_DISABLED = 0, IOT_WIFI_BACKOFF, IOT_WIFI_CONNECTING, IOT_CLOCK_WAIT,
    IOT_BROKER_BACKOFF, IOT_BROKER_CONNECTING, IOT_ONLINE
};
enum IotAction {
    IOT_IDLE = 0, IOT_CONNECT_WIFI, IOT_CONNECT_BROKER, IOT_RESET_BROKER,
    IOT_PUBLISH_SAMPLE, IOT_ACK_SAMPLE
};

struct IotConnection {
    IotConnectionState state;
    uint64_t deadline_ms;
    uint64_t pending_since_ms;
    uint32_t wifi_backoff_ms;
    uint32_t broker_backoff_ms;
    uint32_t reconnects;
    int pending_mid;
};

void iot_queue_init(IotSampleQueue *queue);
uint64_t iot_extend_timestamp_ms(uint32_t raw_ms, uint64_t now_ms);
bool iot_queue_push(IotSampleQueue *queue, const SensorRawFrame *frame, uint64_t acquisition_ms, bool valid_ir = true);
bool iot_queue_peek(const IotSampleQueue *queue, IotSample *sample);
void iot_queue_ack(IotSampleQueue *queue);
bool iot_serialize_sample(const IotSample *sample, const char *device_id, const char *session_id,
                          char *output, size_t capacity);
void iot_connection_init(IotConnection *connection, bool configured);
IotAction iot_connection_step(IotConnection *connection, uint64_t now_ms, bool wifi_up,
                              bool broker_up, bool broker_failed, int ack_mid, bool has_sample,
                              bool clock_ready = true);
void iot_connection_published(IotConnection *connection, uint64_t now_ms, int mid);
uint32_t iot_connection_poll_delay_ms(IotConnectionState state);
const char *iot_connection_state_name(IotConnectionState state);

#endif
