#include "communication/iot_core.h"
#include "common/fw_utils.h"

static void put_u64(FwJsonWriter *writer, uint64_t value) {
    char digits[20];
    unsigned used = 0;
    do { digits[used++] = (char)('0' + value % 10U); value /= 10U; } while (value);
    while (used) jw_putc(writer, digits[--used]);
}

void iot_queue_init(IotSampleQueue *queue) { *queue = IotSampleQueue{}; }

uint64_t iot_extend_timestamp_ms(uint32_t raw_ms, uint64_t now_ms) {
    return now_ms - (uint32_t)((uint32_t)now_ms - raw_ms);
}

bool iot_queue_push(IotSampleQueue *queue, const SensorRawFrame *frame, uint64_t acquisition_ms, bool valid_ir) {
    // Drop newest: preserves the head and its immutable identity during PUBACK/retries.
    // Sequence advances on EVERY acquisition, including discarded samples.
    const uint64_t sequence = queue->next_sequence++;
    if (queue->used == IOT_QUEUE_CAPACITY) { ++queue->dropped_total; return false; }
    IotSample &sample = queue->samples[(queue->head + queue->used) % IOT_QUEUE_CAPACITY];
    sample = IotSample{};
    sample.sample_idx = sequence;
    sample.ts_ms = acquisition_ms;
    sample.dropped_total = queue->dropped_total;
    sample.valid_ultrasonic = frame->valid_ultrasonic && frame->distance_cm >= ULTRASONIC_MIN_DISTANCE_CM &&
        frame->distance_cm <= ULTRASONIC_MAX_DISTANCE_CM;
    sample.distance_cm = sample.valid_ultrasonic ? frame->distance_cm : -1.0f;
    sample.ir_detected = frame->ir_detected;
    sample.valid_ir = valid_ir;
    ++queue->used;
    return true;
}

bool iot_queue_peek(const IotSampleQueue *queue, IotSample *sample) {
    if (!queue->used) return false;
    *sample = queue->samples[queue->head];
    return true;
}

void iot_queue_ack(IotSampleQueue *queue) {
    if (!queue->used) return;
    queue->head = (queue->head + 1U) % IOT_QUEUE_CAPACITY;
    --queue->used;
    ++queue->acknowledged_total;
}

bool iot_serialize_sample(const IotSample *sample, const char *device_id, const char *session_id,
                          char *output, size_t capacity) {
    if (!sample || !device_id || !session_id || fw_strlen(device_id) > 32U || fw_strlen(session_id) > 64U) return false;
    FwJsonWriter writer;
    jw_init(&writer, output, capacity);
    jw_puts(&writer, "{\"schema_version\":1,\"kind\":\"sample\",\"device_id\":");
    jw_put_escaped_str(&writer, device_id);
    jw_puts(&writer, ",\"session_id\":"); jw_put_escaped_str(&writer, session_id);
    jw_puts(&writer, ",\"sample_idx\":"); put_u64(&writer, sample->sample_idx);
    jw_puts(&writer, ",\"ts_ms\":"); put_u64(&writer, sample->ts_ms);
    jw_puts(&writer, ",\"data_origin\":\"real_hardware\",\"distance_cm\":");
    jw_put_fixed(&writer, sample->valid_ultrasonic ? sample->distance_cm : -1.0f, 2U);
    jw_puts(&writer, ",\"valid_ultrasonic\":"); jw_put_bool(&writer, sample->valid_ultrasonic);
    jw_puts(&writer, ",\"ir_detected\":"); jw_put_bool(&writer, sample->ir_detected);
    jw_puts(&writer, ",\"valid_ir\":"); jw_put_bool(&writer, sample->valid_ir);
    jw_puts(&writer, ",\"captured_at_iso\":null,\"clock_source\":\"monotonic_boot\",\"physical_validation\":\"pending\",\"dropped_total\":");
    put_u64(&writer, sample->dropped_total); jw_putc(&writer, '}');
    return !writer.overflow;
}

void iot_connection_init(IotConnection *connection, bool configured) {
    *connection = IotConnection{};
    connection->state = configured ? IOT_WIFI_BACKOFF : IOT_DISABLED;
    connection->wifi_backoff_ms = IOT_RETRY_MIN_MS;
    connection->broker_backoff_ms = IOT_RETRY_MIN_MS;
    connection->pending_mid = -1;
}

static uint32_t advance_backoff(uint32_t value) {
    return value >= IOT_RETRY_MAX_MS / 2U ? IOT_RETRY_MAX_MS : value * 2U;
}

static IotAction reset_broker(IotConnection *connection, uint64_t now_ms, bool wifi_up) {
    connection->pending_mid = -1;
    ++connection->reconnects;
    if (wifi_up) {
        connection->state = IOT_BROKER_BACKOFF;
        connection->deadline_ms = now_ms + connection->broker_backoff_ms;
        connection->broker_backoff_ms = advance_backoff(connection->broker_backoff_ms);
    } else {
        connection->state = IOT_WIFI_BACKOFF;
        connection->deadline_ms = now_ms + connection->wifi_backoff_ms;
        connection->wifi_backoff_ms = advance_backoff(connection->wifi_backoff_ms);
    }
    return IOT_RESET_BROKER;
}

IotAction iot_connection_step(IotConnection *connection, uint64_t now_ms, bool wifi_up,
                              bool broker_up, bool broker_failed, int ack_mid, bool has_sample,
                              bool clock_ready) {
    if (connection->state == IOT_DISABLED) return IOT_IDLE;
    // PUBACK remains meaningful if disconnection follows it before the next poll.
    if (connection->pending_mid >= 0 && ack_mid == connection->pending_mid) {
        connection->pending_mid = -1;
        connection->broker_backoff_ms = IOT_RETRY_MIN_MS;
        return IOT_ACK_SAMPLE;
    }
    if (!wifi_up) {
        if (connection->state >= IOT_CLOCK_WAIT) return reset_broker(connection, now_ms, false);
        if (connection->state == IOT_WIFI_CONNECTING && now_ms >= connection->deadline_ms) {
            connection->state = IOT_WIFI_BACKOFF;
            connection->deadline_ms = now_ms + connection->wifi_backoff_ms;
            connection->wifi_backoff_ms = advance_backoff(connection->wifi_backoff_ms);
            ++connection->reconnects;
        }
        if (connection->state == IOT_WIFI_BACKOFF && now_ms >= connection->deadline_ms) {
            connection->state = IOT_WIFI_CONNECTING;
            connection->deadline_ms = now_ms + IOT_CONNECT_TIMEOUT_MS;
            return IOT_CONNECT_WIFI;
        }
        return IOT_IDLE;
    }
    connection->wifi_backoff_ms = IOT_RETRY_MIN_MS;
    if (!clock_ready) {
        const bool had_client = connection->state == IOT_BROKER_CONNECTING || connection->state == IOT_ONLINE;
        connection->state = IOT_CLOCK_WAIT;
        connection->pending_mid = -1;
        if (had_client) { ++connection->reconnects; return IOT_RESET_BROKER; }
        return IOT_IDLE;
    }
    if (connection->state == IOT_WIFI_CONNECTING || connection->state == IOT_WIFI_BACKOFF || connection->state == IOT_CLOCK_WAIT) {
        connection->state = IOT_BROKER_BACKOFF;
        connection->deadline_ms = now_ms;
    }
    if (connection->state == IOT_BROKER_BACKOFF) {
        if (now_ms < connection->deadline_ms) return IOT_IDLE;
        connection->state = IOT_BROKER_CONNECTING;
        connection->deadline_ms = now_ms + IOT_CONNECT_TIMEOUT_MS;
        return IOT_CONNECT_BROKER;
    }
    if (connection->state == IOT_BROKER_CONNECTING) {
        if (broker_failed || now_ms >= connection->deadline_ms) return reset_broker(connection, now_ms, true);
        if (!broker_up) return IOT_IDLE;
        connection->state = IOT_ONLINE;
    }
    if (connection->state == IOT_ONLINE) {
        if (!broker_up || broker_failed || (connection->pending_mid >= 0 &&
                now_ms - connection->pending_since_ms >= IOT_ACK_TIMEOUT_MS)) {
            return reset_broker(connection, now_ms, true);
        }
        if (connection->pending_mid < 0 && has_sample) return IOT_PUBLISH_SAMPLE;
    }
    return IOT_IDLE;
}

void iot_connection_published(IotConnection *connection, uint64_t now_ms, int mid) {
    connection->pending_mid = mid;
    connection->pending_since_ms = now_ms;
    // A failing publish can have entered the IDF outbox. Force destroy before retry.
    if (mid < 0) connection->deadline_ms = 0U;
}

uint32_t iot_connection_poll_delay_ms(IotConnectionState state) {
    // Online, check PUBACK and the next queue head quickly; disconnected retry
    // and clock states retain the slower polling cadence.
    return state == IOT_ONLINE ? 1U : 20U;
}

const char *iot_connection_state_name(IotConnectionState state) {
    switch (state) {
        case IOT_DISABLED: return "disabled";
        case IOT_WIFI_BACKOFF: return "wifi_backoff";
        case IOT_WIFI_CONNECTING: return "wifi_connecting";
        case IOT_CLOCK_WAIT: return "clock_wait";
        case IOT_BROKER_BACKOFF: return "broker_backoff";
        case IOT_BROKER_CONNECTING: return "broker_connecting";
        case IOT_ONLINE: return "online";
        default: return "unknown";
    }
}
