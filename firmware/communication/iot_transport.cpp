#include "communication/iot_transport.h"
#include "communication/iot_core.h"
#include "common/fw_utils.h"

#ifdef ARDUINO
#include <Arduino.h>
#include <WiFi.h>
#include <esp_log.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <mqtt_client.h>
#include <time.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#if defined(MOTIONLAB_IOT_USE_EXAMPLE) && MOTIONLAB_IOT_USE_EXAMPLE
#include "iot_config.example.h"
#elif __has_include("iot_config.local.h")
#include "iot_config.local.h"
#endif
#ifndef MOTIONLAB_WIFI_SSID
#define MOTIONLAB_WIFI_SSID ""
#endif
#ifndef MOTIONLAB_WIFI_PASSWORD
#define MOTIONLAB_WIFI_PASSWORD ""
#endif
#ifndef MOTIONLAB_MQTT_HOST
#define MOTIONLAB_MQTT_HOST ""
#endif
#ifndef MOTIONLAB_MQTT_PORT
#define MOTIONLAB_MQTT_PORT 1883
#endif
#ifndef MOTIONLAB_MQTT_USERNAME
#define MOTIONLAB_MQTT_USERNAME ""
#endif
#ifndef MOTIONLAB_MQTT_PASSWORD
#define MOTIONLAB_MQTT_PASSWORD ""
#endif
#ifndef MOTIONLAB_MQTT_CA_PEM
#define MOTIONLAB_MQTT_CA_PEM ""
#endif
#ifndef MOTIONLAB_SNTP_SERVER
#define MOTIONLAB_SNTP_SERVER "pool.ntp.org"
#endif
#ifndef MOTIONLAB_ALLOW_INSECURE_LAN
#define MOTIONLAB_ALLOW_INSECURE_LAN false
#endif

static IotSampleQueue g_queue;
static IotConnection g_connection;
static portMUX_TYPE g_lock = portMUX_INITIALIZER_UNLOCKED;
static StaticTask_t g_task;
// IDF task creation takes BYTES even though StackType_t itself is 32 bits here.
static StackType_t g_stack[4096 / sizeof(StackType_t)];
static esp_mqtt_client_handle_t g_client = NULL;
static bool g_configured = false;
static bool g_broker_up = false;
static bool g_broker_failed = false;
static int g_ack_mid = -1;
static IotConnectionState g_state = IOT_DISABLED;
static uint32_t g_reconnects = 0;
static uint32_t g_publish_errors = 0;
static uint32_t g_hwm = 0;
static char g_device[32];
static char g_session[64];
static char g_topic[96];
static char g_payload[IOT_PAYLOAD_CAPACITY];

static void append_hex(char *output, uint64_t value, unsigned digits) {
    const char alphabet[] = "0123456789abcdef";
    for (unsigned i = 0; i < digits; ++i) output[i] = alphabet[(value >> (4U * (digits - i - 1U))) & 15U];
    output[digits] = '\0';
}

static void mqtt_event(void *, esp_event_base_t, int32_t event_id, void *event_data) {
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    portENTER_CRITICAL(&g_lock);
    if (event_id == MQTT_EVENT_CONNECTED) g_broker_up = true;
    if (event_id == MQTT_EVENT_DISCONNECTED || event_id == MQTT_EVENT_ERROR) {
        g_broker_up = false;
        g_broker_failed = true;
    }
    // Store before publish() returns if necessary. Worker compares ID next iteration.
    if (event_id == MQTT_EVENT_PUBLISHED) g_ack_mid = event->msg_id;
    portEXIT_CRITICAL(&g_lock);
}

static void reset_mqtt(void) {
    // Worker only; never from callback or while holding queue lock.
    if (g_client) {
        esp_mqtt_client_stop(g_client);
        esp_mqtt_client_destroy(g_client); // drops the sole possible IDF outbox entry
        g_client = NULL;
    }
    portENTER_CRITICAL(&g_lock);
    g_broker_up = false;
    g_broker_failed = false;
    g_ack_mid = -1;
    portEXIT_CRITICAL(&g_lock);
}

static bool start_mqtt(void) {
    esp_mqtt_client_config_t config{}; // IDF 4.4 flat configuration, not IDF 5 API
    config.host = MOTIONLAB_MQTT_HOST;
    config.port = MOTIONLAB_MQTT_PORT;
    config.client_id = g_device;
    config.username = MOTIONLAB_MQTT_USERNAME[0] ? MOTIONLAB_MQTT_USERNAME : g_device;
    config.password = MOTIONLAB_MQTT_PASSWORD;
    config.disable_auto_reconnect = true;
    config.keepalive = 20;
    config.network_timeout_ms = 2000;
    config.task_stack = 6144;
    config.task_prio = 1;
    config.buffer_size = IOT_PAYLOAD_CAPACITY;
    config.out_buffer_size = IOT_PAYLOAD_CAPACITY;
    // Local plain TCP is supported only for a restricted trusted LAN.
    if (MOTIONLAB_MQTT_CA_PEM[0]) {
        config.transport = MQTT_TRANSPORT_OVER_SSL;
        config.cert_pem = MOTIONLAB_MQTT_CA_PEM;
    } else config.transport = MQTT_TRANSPORT_OVER_TCP;
    g_client = esp_mqtt_client_init(&config);
    if (!g_client) return false;
    return esp_mqtt_client_register_event(g_client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqtt_event, NULL) == ESP_OK &&
        esp_mqtt_client_start(g_client) == ESP_OK;
}

static void network_task(void *) {
    WiFi.persistent(false);
    WiFi.setAutoReconnect(false);
    WiFi.mode(WIFI_STA);
    // MQTT QoS 1 waits for PUBACK; modem sleep can delay incoming packets.
    WiFi.setSleep(false);
    if (MOTIONLAB_MQTT_CA_PEM[0]) configTime(0, 0, MOTIONLAB_SNTP_SERVER);
    for (;;) {
        bool broker_up, broker_failed, has_sample;
        int ack_mid;
        IotSample sample{};
        portENTER_CRITICAL(&g_lock);
        broker_up = g_broker_up;
        broker_failed = g_broker_failed;
        ack_mid = g_ack_mid;
        g_ack_mid = -1;
        has_sample = iot_queue_peek(&g_queue, &sample);
        portEXIT_CRITICAL(&g_lock);
        const uint64_t now_ms = (uint64_t)esp_timer_get_time() / 1000ULL;
        IotAction action = iot_connection_step(&g_connection, now_ms, WiFi.status() == WL_CONNECTED,
                                              broker_up, broker_failed, ack_mid, has_sample,
                                              !MOTIONLAB_MQTT_CA_PEM[0] || time(NULL) >= 1735689600);
        switch (action) {
            case IOT_CONNECT_WIFI:
                WiFi.disconnect(false, false);
                WiFi.begin(MOTIONLAB_WIFI_SSID, MOTIONLAB_WIFI_PASSWORD);
                break;
            case IOT_CONNECT_BROKER:
                if (!start_mqtt()) {
                    portENTER_CRITICAL(&g_lock); g_broker_failed = true; portEXIT_CRITICAL(&g_lock);
                }
                break;
            case IOT_RESET_BROKER: reset_mqtt(); break;
            case IOT_ACK_SAMPLE:
                portENTER_CRITICAL(&g_lock); iot_queue_ack(&g_queue); portEXIT_CRITICAL(&g_lock);
                break;
            case IOT_PUBLISH_SAMPLE: {
                // Exactly one QoS1 publication is outstanding; queue head stays until PUBACK.
                const bool serialized = iot_serialize_sample(&sample, g_device, g_session, g_payload, sizeof(g_payload));
                const int mid = serialized ? esp_mqtt_client_publish(g_client, g_topic, g_payload, 0, 1, 0) : -1;
                iot_connection_published(&g_connection, now_ms, mid);
                if (mid < 0) {
                    portENTER_CRITICAL(&g_lock); g_broker_failed = true; ++g_publish_errors; portEXIT_CRITICAL(&g_lock);
                }
                break;
            }
            default: break;
        }
        const uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        portENTER_CRITICAL(&g_lock);
        g_state = g_connection.state;
        g_reconnects = g_connection.reconnects;
        g_hwm = hwm;
        portEXIT_CRITICAL(&g_lock);
        // Even at low tick rates yield at least one tick. At the current 1 kHz
        // tick rate, online polling waits 1 ms rather than 20 ms per action.
        const TickType_t delay_ticks = pdMS_TO_TICKS(iot_connection_poll_delay_ms(g_connection.state));
        vTaskDelay(delay_ticks ? delay_ticks : 1);
    }
}

void iot_transport_start(void) {
    iot_queue_init(&g_queue);
    g_configured = MOTIONLAB_WIFI_SSID[0] && MOTIONLAB_MQTT_HOST[0] && MOTIONLAB_MQTT_PASSWORD[0] &&
        MOTIONLAB_MQTT_PORT > 0 && MOTIONLAB_MQTT_PORT <= 65535 &&
        (MOTIONLAB_MQTT_CA_PEM[0] || MOTIONLAB_ALLOW_INSECURE_LAN);
    iot_connection_init(&g_connection, g_configured);
    g_state = g_connection.state;
    // Arduino/IDF logs must never corrupt the UART0 JSONL protocol.
    esp_log_level_set("*", ESP_LOG_NONE);
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    fw_strncpy(g_device, "esp32_", sizeof(g_device));
    for (unsigned i = 0; i < 6; ++i) append_hex(g_device + 6 + i * 2, mac[i], 2);
    fw_strncpy(g_session, "boot_", sizeof(g_session));
    // Bootloader-seeded RNG, for identity uniqueness, never used as a security token.
    for (unsigned i = 0; i < 4; ++i) append_hex(g_session + 5 + i * 8, esp_random(), 8);
    FwJsonWriter writer;
    jw_init(&writer, g_topic, sizeof(g_topic));
    jw_puts(&writer, "motionlab/v1/devices/"); jw_puts(&writer, g_device); jw_puts(&writer, "/samples");
    if (!g_configured) return; // USB/inference do not depend on Wi-Fi initialization.
    // PRO_CPU (core 0) hosts the Wi-Fi/lwIP stack. The acquisition task on APP_CPU busy-waits
    // up to 25 ms per HC-SR04 echo at the highest priority; keeping the network worker off that
    // core lets PUBACK handling and publishing proceed during the echo wait. g_lock is a
    // portMUX spinlock, so the queue shared with the acquisition task stays SMP-safe.
    if (!xTaskCreateStaticPinnedToCore(network_task, "MotionIoT", sizeof(g_stack), NULL, 1,
                                      g_stack, &g_task, PRO_CPU_NUM)) {
        g_configured = false;
        g_state = IOT_DISABLED;
    }
}

void iot_transport_acquire(const SensorRawFrame *frame, uint64_t acquisition_ms, bool valid_ir) {
    if (!g_configured) return;
    // One bounded struct copy and arithmetic; no waits, String, heap or network.
    portENTER_CRITICAL(&g_lock);
    iot_queue_push(&g_queue, frame, acquisition_ms, valid_ir);
    portEXIT_CRITICAL(&g_lock);
}

void iot_transport_diag(char *output, size_t capacity) {
    uint16_t used;
    uint64_t dropped, acknowledged;
    uint32_t reconnects, errors, hwm;
    IotConnectionState state;
    portENTER_CRITICAL(&g_lock);
    used = g_queue.used; dropped = g_queue.dropped_total; acknowledged = g_queue.acknowledged_total;
    reconnects = g_reconnects; errors = g_publish_errors; hwm = g_hwm; state = g_state;
    portEXIT_CRITICAL(&g_lock);
    FwJsonWriter writer;
    jw_init(&writer, output, capacity);
    jw_puts(&writer, "iot:state="); jw_puts(&writer, iot_connection_state_name(state));
    jw_puts(&writer, ",device="); jw_puts(&writer, g_device);
    jw_puts(&writer, ",session="); jw_puts(&writer, g_session);
    jw_puts(&writer, ",q="); jw_put_u32(&writer, used);
    jw_puts(&writer, "/32,drop="); jw_put_u32(&writer, (uint32_t)dropped);
    jw_puts(&writer, ",ack="); jw_put_u32(&writer, (uint32_t)acknowledged);
    jw_puts(&writer, ",retry="); jw_put_u32(&writer, reconnects);
    jw_puts(&writer, ",puberr="); jw_put_u32(&writer, errors);
    jw_puts(&writer, ",hwm="); jw_put_u32(&writer, hwm);
}
#else
void iot_transport_start(void) {}
void iot_transport_acquire(const SensorRawFrame *, uint64_t, bool) {}
void iot_transport_diag(char *output, size_t capacity) { fw_strncpy(output, "iot:state=host_stub", capacity); }
#endif
