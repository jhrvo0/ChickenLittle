/**
 * @file main.cpp
 * @brief Firmware Embarcado Completo MotionPet (ESP-WROOM-32 / FreeRTOS — Ciclo 3: Marcos A, B e C).
 *
 * Arquitetura multitarefa cooperativa/preemptiva com 5 tasks FreeRTOS em APP_CPU_NUM:
 *   1. TaskSensorAcquire (Prio 4, 3072 B): Aquisição periódica HC-SR04 + TCRT5000 + Potenciômetro ADC1.
 *   2. TaskGestureInfer  (Prio 3, 4096 B): Filtro causal, buffer circular, 11 features, TinyML e estabilizador.
 *   3. TaskPetDomain     (Prio 2, 4096 B): Motor autoritativo do Pet (1 Hz), comandos, gestos e persistência NVS.
 *   4. TaskSerialComm    (Prio 2, 4096 B): Único proprietário da UART0 (115200 baud), protocolo JSON Lines v1 puro.
 *   5. TaskLcdDisplay    (Prio 1, 3072 B): Atualização diferencial sem flicker (5 Hz) do LCD 2004A em modo 4 bits.
 *
 * NOTA CRÍTICA: Logs textuais soltos estão desativados (`CORE_DEBUG_LEVEL=0`) e proibidos na UART0
 * para garantir compatibilidade 100% pura com JSON Lines v1 (`SessionCollector` e `TerminalHostClient`).
 */

#include <Arduino.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

#include "common/fw_utils.h"
#include "main/pinout_config.h"
#include "main/telemetry_metrics.h"
#include "sensors/sensor_types.h"
#include "sensors/sensors_driver.h"
#include "gestures/gesture_classifier.h"
#include "pet/pet_state.h"
#include "pet/pet_persistence.h"
#include "display/lcd2004_driver.h"
#include "display/lcd2004_i2c_hal.h"
#include "display/lcd2004_anim.h"
#include "communication/jsonl_protocol.h"
#include "communication/iot_transport.h"
#include "communication/iot_core.h"

// Mensagens internas estáticas trocadas entre TaskSerialComm e TaskPetDomain (zero heap)
typedef struct {
    PetCommandType cmd;
    uint32_t seq;
    char mode_arg[20];
    LaunchCommand launch;
} PetCmdQueueItem;

typedef struct {
    uint32_t ack_seq;
    bool is_error;
    char code[24];
    char status[48];
} PetReplyQueueItem;

// Contextos estáticos dos subsistemas (zero alocação dinâmica em tempo real)
static SensorDriverContext g_sensor_drv;
static GestureClassifierContext g_gesture_ctx;
static PetPersistenceContext g_pet_nvs;
static LCDDriverContext g_lcd_drv;
static JsonlContext g_jsonl_ctx;
static FirmwareRuntimeMetrics g_metrics;

// Estado compartilhado protegido por g_state_mutex
static PetStateSnapshot g_shared_pet_state;
static LCDFrameBuffer g_shared_lcd_frame;
static LCDFrameBuffer g_host_lcd_frame;
static uint32_t g_host_lcd_received_ms = 0UL;
static bool g_has_host_lcd = false;
static SensorRawFrame g_latest_sensor_frame;
static bool g_has_latest_sensor = false;
static bool g_pet_state_tx_pending = false;
static char g_active_mode[20] = "MOTION_PET";

// Primitivas de sincronização FreeRTOS
static SemaphoreHandle_t g_state_mutex = NULL;
static QueueHandle_t g_q_sensor_infer = NULL;
static QueueHandle_t g_q_sensor_tx = NULL;
static QueueHandle_t g_q_gesture_pet = NULL;
static QueueHandle_t g_q_gesture_tx = NULL;
static QueueHandle_t g_q_cmd_pet = NULL;
static QueueHandle_t g_q_pet_reply_tx = NULL;

// Handles das 5 tasks FreeRTOS
static TaskHandle_t g_task_sensor_handle = NULL;
static TaskHandle_t g_task_gesture_handle = NULL;
static TaskHandle_t g_task_pet_handle = NULL;
static TaskHandle_t g_task_serial_handle = NULL;
static TaskHandle_t g_task_lcd_handle = NULL;

static uint32_t now_monotonic_ms(void) {
    return (uint32_t)((uint64_t)esp_timer_get_time() / 1000ULL);
}

static bool is_supported_mode_name(const char *mode_name) {
    if (!mode_name || !mode_name[0]) return false;
    return (
        fw_strcmp(mode_name, "MOTION_PET") == 0 ||
        fw_strcmp(mode_name, "PET_LAUNCH") == 0 ||
        fw_strcmp(mode_name, "AIR_MUSIC") == 0 ||
        fw_strcmp(mode_name, "AIR_SLIDES") == 0
    );
}

static void refresh_runtime_queue_and_heap_metrics_locked(void) {
    g_metrics.q_sensor_infer_used = g_q_sensor_infer ? (uint16_t)uxQueueMessagesWaiting(g_q_sensor_infer) : 0U;
    g_metrics.q_sensor_tx_used = g_q_sensor_tx ? (uint16_t)uxQueueMessagesWaiting(g_q_sensor_tx) : 0U;
    g_metrics.q_gesture_pet_used = g_q_gesture_pet ? (uint16_t)uxQueueMessagesWaiting(g_q_gesture_pet) : 0U;
    g_metrics.q_cmd_pet_used = g_q_cmd_pet ? (uint16_t)uxQueueMessagesWaiting(g_q_cmd_pet) : 0U;
    g_metrics.free_heap_bytes = (uint32_t)ESP.getFreeHeap();
    g_metrics.min_free_heap_bytes = (uint32_t)ESP.getMinFreeHeap();
}

static void format_diag_status(char *out_buf, size_t cap) {
    FirmwareRuntimeMetrics snap{};
    char mode_copy[20];
    if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        refresh_runtime_queue_and_heap_metrics_locked();
        snap = g_metrics;
        fw_strncpy(mode_copy, g_active_mode, sizeof(mode_copy));
        xSemaphoreGive(g_state_mutex);
    } else {
        fw_strncpy(mode_copy, "MOTION_PET", sizeof(mode_copy));
    }

    FwJsonWriter w;
    jw_init(&w, out_buf, cap);
    jw_puts(&w, "diag:fw=");
    jw_puts(&w, MOTIONPET_FW_VERSION);
    jw_puts(&w, ",origin=ESP32_HW,pins=");
    jw_puts(&w, MOTIONPET_PINOUT_STATUS);
    jw_puts(&w, ",acq=");
    jw_puts(&w, snap.collection_active ? "on" : "off");
    jw_puts(&w, ",per_ms=");
    jw_put_u32(&w, snap.sample_period_ms);
    jw_puts(&w, ",acq_us=");
    jw_put_u32(&w, snap.last_acquire_us);
    jw_puts(&w, ",max_acq_us=");
    jw_put_u32(&w, snap.max_acquire_us);
    jw_puts(&w, ",inf_us=");
    jw_put_u32(&w, snap.last_infer_us);
    jw_puts(&w, ",max_inf_us=");
    jw_put_u32(&w, snap.max_infer_us);
    jw_puts(&w, ",samp=");
    jw_put_u32(&w, snap.total_samples_acquired);
    jw_puts(&w, ",win=");
    jw_put_u32(&w, snap.total_windows_inferred);
    jw_puts(&w, ",gest=");
    jw_put_u32(&w, snap.total_gestures_emitted);
    jw_puts(&w, ",rej=");
    jw_put_u32(&w, snap.total_windows_rejected);
    jw_puts(&w, ",to_us=");
    jw_put_u32(&w, snap.ultrasonic_timeouts);
    jw_puts(&w, ",drop_si=");
    jw_put_u32(&w, snap.dropped_sensor_infer_queue);
    jw_puts(&w, ",drop_tx=");
    jw_put_u32(&w, snap.dropped_sensor_tx_queue);
    jw_puts(&w, ",drop_g=");
    jw_put_u32(&w, snap.dropped_gesture_queue);
    jw_puts(&w, ",q_si=");
    jw_put_u32(&w, (uint32_t)snap.q_sensor_infer_used);
    jw_puts(&w, ",q_tx=");
    jw_put_u32(&w, (uint32_t)snap.q_sensor_tx_used);
    jw_puts(&w, ",hwm_s=");
    jw_put_u32(&w, snap.hwm_sensor_bytes);
    jw_puts(&w, ",hwm_g=");
    jw_put_u32(&w, snap.hwm_gesture_bytes);
    jw_puts(&w, ",hwm_p=");
    jw_put_u32(&w, snap.hwm_pet_bytes);
    jw_puts(&w, ",hwm_c=");
    jw_put_u32(&w, snap.hwm_serial_bytes);
    jw_puts(&w, ",hwm_l=");
    jw_put_u32(&w, snap.hwm_lcd_bytes);
    jw_puts(&w, ",heap=");
    jw_put_u32(&w, snap.free_heap_bytes);
    jw_puts(&w, ",min_heap=");
    jw_put_u32(&w, snap.min_free_heap_bytes);
    jw_puts(&w, ",nvs_w=");
    jw_put_u32(&w, snap.nvs_save_count);
    jw_puts(&w, ",mdl=");
    jw_puts(&w, gesture_classifier_model_name());
    jw_puts(&w, ",exp=");
    jw_puts(&w, gesture_classifier_experimental_status());
    jw_puts(&w, ",mode=");
    jw_puts(&w, mode_copy);
}

// ============================================================================
// 1. TaskSensorAcquire: Aquisição determinística HC-SR04 + TCRT5000 + Pot ADC1
// ============================================================================
static void TaskSensorAcquire(void *param) {
    (void)param;
    TickType_t last_wake = xTaskGetTickCount();
    // Acquisition owns its mutable driver/timestamp; serial updates only the desired
    // IR configuration in g_sensor_drv. Apply it once per cycle for coherent validity.
    SensorDriverContext sensor_driver = g_sensor_drv;

    for (;;) {
        bool stream_tx_active = true;
        uint32_t period_ms = DEFAULT_SENSOR_PERIOD_MS;

        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            stream_tx_active = g_metrics.collection_active;
            period_ms = g_metrics.sample_period_ms;
            sensor_driver.config.ir_enabled = g_sensor_drv.config.ir_enabled;
            xSemaphoreGive(g_state_mutex);
        }

        SensorRawFrame frame;
        sensors_driver_read(&sensor_driver, &frame);

        // Same acquisition as USB/TinyML. Extend the existing 32-bit timestamp using
        // the ESP timer (64-bit); preserves exact acquisition time across millis rollover.
        const uint64_t now_ms64 = (uint64_t)esp_timer_get_time() / 1000ULL;
        const uint64_t acquisition_ms = iot_extend_timestamp_ms(frame.timestamp_ms, now_ms64);
        iot_transport_acquire(&frame, acquisition_ms,
            sensor_driver.config.ir_enabled && sensor_driver.hal.read_digital != NULL);

        // Alimenta sempre o pipeline local TinyML para autonomia embarcada
        bool dropped_infer = (xQueueSend(g_q_sensor_infer, &frame, 0) != pdTRUE);
        bool dropped_tx = false;
        if (stream_tx_active) {
            dropped_tx = (xQueueSend(g_q_sensor_tx, &frame, 0) != pdTRUE);
        }

        uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_latest_sensor_frame = frame;
            g_has_latest_sensor = true;
            g_metrics.total_samples_acquired++;
            g_metrics.last_acquire_us = frame.acquire_duration_us;
            if (frame.acquire_duration_us > g_metrics.max_acquire_us) {
                g_metrics.max_acquire_us = frame.acquire_duration_us;
            }
            if (!frame.valid_ultrasonic) {
                g_metrics.ultrasonic_timeouts++;
            }
            if (dropped_infer) {
                g_metrics.dropped_sensor_infer_queue++;
            }
            if (dropped_tx) {
                g_metrics.dropped_sensor_tx_queue++;
            }
            g_metrics.hwm_sensor_bytes = hwm;
            xSemaphoreGive(g_state_mutex);
        }

        TickType_t wait_ticks = pdMS_TO_TICKS(period_ms);
        if (wait_ticks < 1) wait_ticks = 1;
        vTaskDelayUntil(&last_wake, wait_ticks);
    }
}

// ============================================================================
// 2. TaskGestureInfer: Pré-processamento causal, 11 features e inferência TinyML
// ============================================================================
static void TaskGestureInfer(void *param) {
    (void)param;
    SensorRawFrame frame;

    for (;;) {
        // Bloqueia na fila sem polling ativo
        if (xQueueReceive(g_q_sensor_infer, &frame, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        uint64_t t0_us = (uint64_t)esp_timer_get_time();
        gesture_classifier_ctx_push_sample(
            &g_gesture_ctx,
            frame.distance_cm,
            frame.valid_ultrasonic,
            frame.ir_detected,
            frame.timestamp_ms
        );

        GestureEvent ev{};
        bool emitted = gesture_classifier_ctx_infer(&g_gesture_ctx, &ev);
        uint32_t elapsed_us = (uint32_t)((uint64_t)esp_timer_get_time() - t0_us);

        bool dropped_gesture = false;
        if (emitted) {
            if (xQueueSend(g_q_gesture_pet, &ev, 0) != pdTRUE) {
                dropped_gesture = true;
            }
            if (xQueueSend(g_q_gesture_tx, &ev, 0) != pdTRUE) {
                dropped_gesture = true;
            }
        }

        uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_metrics.last_infer_us = elapsed_us;
            if (elapsed_us > g_metrics.max_infer_us) {
                g_metrics.max_infer_us = elapsed_us;
            }
            g_metrics.total_windows_inferred = g_gesture_ctx.total_windows_evaluated;
            g_metrics.total_gestures_emitted = g_gesture_ctx.total_events_emitted;
            g_metrics.total_windows_rejected = g_gesture_ctx.total_windows_rejected;
            if (dropped_gesture) {
                g_metrics.dropped_gesture_queue++;
            }
            g_metrics.hwm_gesture_bytes = hwm;
            xSemaphoreGive(g_state_mutex);
        }
    }
}

// ============================================================================
// 3. TaskPetDomain: Motor autoritativo do Pet (1 Hz) + Persistência NVS CRC32
// ============================================================================
static void publish_pet_snapshot(const PetStateSnapshot *pet, bool notify_serial_tx) {
    uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
    if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        g_shared_pet_state = *pet;
        if (notify_serial_tx) {
            g_pet_state_tx_pending = true;
        }
        g_metrics.nvs_save_count = g_pet_nvs.total_writes;
        g_metrics.nvs_load_errors = g_pet_nvs.corruption_recoveries;
        g_metrics.hwm_pet_bytes = hwm;
        xSemaphoreGive(g_state_mutex);
    }
}

static void enqueue_pet_reply(uint32_t seq, bool is_err, const char *code, const char *status) {
    PetReplyQueueItem rep{};
    rep.ack_seq = seq;
    rep.is_error = is_err;
    fw_strncpy(rep.code, code ? code : "", sizeof(rep.code));
    fw_strncpy(rep.status, status ? status : "ok", sizeof(rep.status));
    (void)xQueueSend(g_q_pet_reply_tx, &rep, 0);
}

static void TaskPetDomain(void *param) {
    (void)param;
    PetStateSnapshot local_pet{};
    pet_init(&local_pet, "Bitinho", PERSONALITY_CURIOUS);

    // Tentativa segura de restauração do estado salvo na NVS
    PetStateSnapshot restored_pet{};
    PetNvsStatus load_st = pet_persistence_load(&g_pet_nvs, &restored_pet);
    if (load_st == PET_NVS_OK) {
        local_pet = restored_pet;
    }

    publish_pet_snapshot(&local_pet, true);
    uint32_t next_bio_tick_ms = now_monotonic_ms() + PET_TICK_PERIOD_MS;
    bool launch_active = false;

    for (;;) {
        uint32_t now_ms = now_monotonic_ms();
        uint32_t wait_ms = 50UL;
        if (now_ms < next_bio_tick_ms) {
            uint32_t rem = next_bio_tick_ms - now_ms;
            if (rem < wait_ms) wait_ms = rem;
        } else {
            wait_ms = 0UL;
        }

        bool state_changed = false;
        bool should_notify_serial = false;

        // 1. Aguarda comando administrativo/cuidado sem busy-wait
        PetCmdQueueItem cmd_item{};
        if (xQueueReceive(g_q_cmd_pet, &cmd_item, pdMS_TO_TICKS(wait_ms)) == pdTRUE) {
            uint32_t cmd_ts = now_monotonic_ms();
            if (cmd_item.cmd == CMD_SAVE) {
                PetNvsStatus sv = pet_persistence_save(&g_pet_nvs, &local_pet, cmd_ts, true);
                if (sv == PET_NVS_OK || sv == PET_NVS_ERR_UNCHANGED) {
                    fw_strncpy(local_pet.last_action, "SAVED", sizeof(local_pet.last_action));
                    state_changed = true;
                    should_notify_serial = true;
                    enqueue_pet_reply(cmd_item.seq, false, "", sv == PET_NVS_OK ? "saved_nvs" : "saved_unchanged");
                } else {
                    enqueue_pet_reply(cmd_item.seq, true, "NVS_SAVE_FAIL", "Failed to save state to NVS");
                }
            } else if (cmd_item.cmd == CMD_LOAD) {
                PetStateSnapshot loaded{};
                PetNvsStatus ld = pet_persistence_load(&g_pet_nvs, &loaded);
                if (ld == PET_NVS_OK) {
                    local_pet = loaded;
                    fw_strncpy(local_pet.last_action, "LOADED", sizeof(local_pet.last_action));
                    state_changed = true;
                    should_notify_serial = true;
                    enqueue_pet_reply(cmd_item.seq, false, "", "loaded_nvs");
                } else if (ld == PET_NVS_ERR_NOT_FOUND) {
                    enqueue_pet_reply(cmd_item.seq, false, "", "no_save_found");
                } else {
                    enqueue_pet_reply(cmd_item.seq, true, "NVS_CORRUPT_RECOVERED", "Corrupt NVS blob ignored safely");
                }
            } else if (cmd_item.cmd == CMD_SWITCH_MODE) {
                const char *target_mode = cmd_item.mode_arg[0] ? cmd_item.mode_arg : "MOTION_PET";
                if (is_supported_mode_name(target_mode)) {
                    if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                        fw_strncpy(g_active_mode, target_mode, sizeof(g_active_mode));
                        if (fw_strcmp(target_mode, "PET_LAUNCH") != 0) g_has_host_lcd = false;
                        launch_active = fw_strcmp(target_mode, "PET_LAUNCH") == 0;
                        xSemaphoreGive(g_state_mutex);
                        state_changed = true;
                        should_notify_serial = true;
                        enqueue_pet_reply(cmd_item.seq, false, "", "mode_switched");
                    } else {
                        enqueue_pet_reply(cmd_item.seq, true, "EXEC_ERR", "Mode update busy");
                    }
                } else {
                    enqueue_pet_reply(cmd_item.seq, true, "INVALID_MODE", "Unsupported system mode");
                }
            } else if (cmd_item.launch.action != LAUNCH_NONE) {
                bool applied = false;
                if (cmd_item.launch.action == LAUNCH_MATCH_RESULT) {
                    applied = pet_apply_launch_match(&local_pet, cmd_item.launch.distance_m,
                        cmd_item.launch.score, cmd_item.launch.coins_earned, cmd_item.launch.xp_earned);
                } else if (cmd_item.launch.action == LAUNCH_UNLOCK_UPGRADE) {
                    applied = pet_unlock_launch_upgrade(&local_pet, cmd_item.launch.upgrade_id, cmd_item.launch.cost);
                }
                if (applied) {
                    state_changed = true;
                    should_notify_serial = true;
                    enqueue_pet_reply(cmd_item.seq, false, "", "applied");
                } else {
                    enqueue_pet_reply(cmd_item.seq, true, "EXEC_ERR", "Pet Launch command rejected");
                }
            } else {
                (void)pet_apply_command(&local_pet, cmd_item.cmd);
                state_changed = true;
                should_notify_serial = true;
                enqueue_pet_reply(cmd_item.seq, false, "", "applied");
            }
        }

        // 2. Drena eventos gestuais classificados pelo TinyML ou injetados
        GestureEvent gev{};
        while (xQueueReceive(g_q_gesture_pet, &gev, 0) == pdTRUE) {
            if (!launch_active && pet_apply_gesture_event(&local_pet, &gev, 0.55f)) {
                state_changed = true;
                should_notify_serial = true;
            }
        }

        // 3. Ciclo biológico determinístico de 1 Hz + auto-save antidesgaste (30 s)
        now_ms = now_monotonic_ms();
        if (now_ms >= next_bio_tick_ms) {
            if (!launch_active) pet_tick(&local_pet);
            state_changed = true;
            should_notify_serial = true;
            next_bio_tick_ms = now_ms + PET_TICK_PERIOD_MS;

            // Gravação automática limitada a intervalos >= 30 s e apenas quando houve mudança real
            (void)pet_persistence_save(&g_pet_nvs, &local_pet, now_ms, false);
        }

        if (state_changed) {
            publish_pet_snapshot(&local_pet, should_notify_serial);
        }
    }
}

// ============================================================================
// 4. TaskSerialComm: Protocolo JSON Lines v1 puro sobre UART0 (115200 baud)
// ============================================================================
static void handle_serial_rx_line(const char *rx_line, char *tx_buf, size_t tx_cap) {
    JsonlRxParsed parsed;
    uint32_t ts = now_monotonic_ms();

    if (!jsonl_parse_incoming_line(&g_jsonl_ctx, rx_line, &parsed)) {
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_metrics.serial_rx_parse_errors = g_jsonl_ctx.parse_errors;
            xSemaphoreGive(g_state_mutex);
        }
        int64_t ref_seq = (parsed.seq > 0U) ? (int64_t)parsed.seq : -1;
        if (jsonl_serialize_error_ex(
                &g_jsonl_ctx, tx_buf, tx_cap, ts,
                parsed.error_code[0] ? parsed.error_code : "BAD_FRAME",
                parsed.error_msg[0] ? parsed.error_msg : "Parse failure",
                ref_seq)) {
            Serial.print(tx_buf);
        }
        return;
    }

    if (parsed.kind == RX_MSG_PET_COMMAND) {
        PetCmdQueueItem item{};
        item.cmd = parsed.pet_cmd;
        item.seq = parsed.seq;
        fw_strncpy(item.mode_arg, parsed.mode_arg, sizeof(item.mode_arg));
        item.launch = parsed.launch;
        if (xQueueSend(g_q_cmd_pet, &item, pdMS_TO_TICKS(10)) != pdTRUE) {
            if (jsonl_serialize_error_ex(
                    &g_jsonl_ctx, tx_buf, tx_cap, ts,
                    "CMD_QUEUE_FULL", "Pet command queue busy", (int64_t)parsed.seq)) {
                Serial.print(tx_buf);
            }
        }
        return;
    }

    if (parsed.kind == RX_MSG_GESTURE_INJECT) {
        (void)xQueueSend(g_q_gesture_pet, &parsed.injected_gesture, 0);
        if (jsonl_serialize_ack(&g_jsonl_ctx, tx_buf, tx_cap, ts, parsed.seq, "gesture_accepted")) {
            Serial.print(tx_buf);
        }
        return;
    }

    if (parsed.kind == RX_MSG_LCD_FRAME) {
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            // SWITCH_MODE segue por outra fila: o quadro pode chegar primeiro.
            g_host_lcd_frame = parsed.lcd_frame;
            g_host_lcd_received_ms = ts;
            g_has_host_lcd = true;
            xSemaphoreGive(g_state_mutex);
        }
        return;
    }

    const char *ack_msg = "ok";
    char status_buf[384];

    if (parsed.kind == RX_MSG_ACQ_START) {
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            g_metrics.collection_active = true;
            if (parsed.param_u32 >= MIN_SENSOR_PERIOD_MS && parsed.param_u32 <= MAX_SENSOR_PERIOD_MS) {
                g_metrics.sample_period_ms = parsed.param_u32;
            }
            xSemaphoreGive(g_state_mutex);
        }
        ack_msg = "collection_started";
    } else if (parsed.kind == RX_MSG_ACQ_STOP) {
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            g_metrics.collection_active = false;
            xSemaphoreGive(g_state_mutex);
        }
        ack_msg = "collection_stopped";
    } else if (parsed.kind == RX_MSG_ACQ_SET_PERIOD) {
        uint32_t clamped = parsed.param_u32;
        if (clamped < MIN_SENSOR_PERIOD_MS) clamped = MIN_SENSOR_PERIOD_MS;
        if (clamped > MAX_SENSOR_PERIOD_MS) clamped = MAX_SENSOR_PERIOD_MS;
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            g_metrics.sample_period_ms = clamped;
            xSemaphoreGive(g_state_mutex);
        }
        ack_msg = "period_updated";
    } else if (parsed.kind == RX_MSG_ACQ_SET_IR) {
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            g_sensor_drv.config.ir_enabled = parsed.param_bool;
            xSemaphoreGive(g_state_mutex);
        }
        ack_msg = parsed.param_bool ? "ir_enabled" : "ir_disabled";
    } else if (parsed.kind == RX_MSG_DIAG_REQUEST) {
        if (parsed.param_bool) iot_transport_diag(status_buf, sizeof(status_buf));
        else format_diag_status(status_buf, sizeof(status_buf));
        ack_msg = status_buf;
    }

    if (jsonl_serialize_ack(&g_jsonl_ctx, tx_buf, tx_cap, ts, parsed.seq, ack_msg)) {
        Serial.print(tx_buf);
    }
}

static void TaskSerialComm(void *param) {
    (void)param;
    static char rx_buf[JSONL_LINE_BUFFER_SIZE];
    // O snapshot com progresso do jogo é maior que os comandos recebidos.
    static char tx_buf[1024];
    size_t rx_pos = 0U;
    bool rx_overflowing = false;

    for (;;) {
        // 1. Leitura não-bloqueante da porta Serial USB
        while (Serial.available() > 0) {
            int ch = Serial.read();
            if (ch < 0) break;
            if (ch == '\r') continue;
            if (ch == '\n') {
                if (rx_overflowing) {
                    rx_overflowing = false;
                    rx_pos = 0U;
                    if (jsonl_serialize_error(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), now_monotonic_ms(),
                                              "ERR_LINE_OVERFLOW", "Serial Rx line exceeded buffer")) {
                        Serial.print(tx_buf);
                    }
                } else if (rx_pos > 0U) {
                    rx_buf[rx_pos] = '\0';
                    handle_serial_rx_line(rx_buf, tx_buf, sizeof(tx_buf));
                    rx_pos = 0U;
                }
            } else if (!rx_overflowing) {
                if (rx_pos + 1U < sizeof(rx_buf)) {
                    rx_buf[rx_pos++] = (char)ch;
                } else {
                    rx_overflowing = true;
                    if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(2)) == pdTRUE) {
                        g_metrics.serial_rx_overflows++;
                        xSemaphoreGive(g_state_mutex);
                    }
                }
            }
        }

        // 2. Respostas `ack` / `error` originadas por comandos do Pet
        PetReplyQueueItem rep{};
        while (xQueueReceive(g_q_pet_reply_tx, &rep, 0) == pdTRUE) {
            uint32_t ts = now_monotonic_ms();
            if (rep.is_error) {
                if (jsonl_serialize_error_ex(
                        &g_jsonl_ctx, tx_buf, sizeof(tx_buf), ts,
                        rep.code, rep.status, (int64_t)rep.ack_seq)) {
                    Serial.print(tx_buf);
                }
            } else {
                if (jsonl_serialize_ack(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), ts, rep.ack_seq, rep.status)) {
                    Serial.print(tx_buf);
                }
            }
        }

        // 3. Eventos gestuais classificados pelo TinyML (`gesture_event`)
        GestureEvent gev{};
        while (xQueueReceive(g_q_gesture_tx, &gev, 0) == pdTRUE) {
            if (jsonl_serialize_gesture_event(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), gev.timestamp_ms, &gev)) {
                Serial.print(tx_buf);
            }
        }

        // 4. Sincronização de `pet_state` e `lcd_frame` após comandos ou gestos aceitos
        bool send_pet_sync = false;
        PetStateSnapshot pet_snap{};
        LCDFrameBuffer lcd_snap{};
        uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            if (g_pet_state_tx_pending) {
                g_pet_state_tx_pending = false;
                pet_snap = g_shared_pet_state;
                lcd_snap = g_shared_lcd_frame;
                send_pet_sync = true;
            }
            g_metrics.hwm_serial_bytes = hwm;
            xSemaphoreGive(g_state_mutex);
        }

        if (send_pet_sync) {
            uint32_t ts = now_monotonic_ms();
            if (jsonl_serialize_pet_state(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), ts, &pet_snap)) {
                Serial.print(tx_buf);
            }
            if (jsonl_serialize_lcd_frame(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), ts, &lcd_snap)) {
                Serial.print(tx_buf);
            }
        }

        // 5. Drena quadros `sensor_frame` prontos para envio (P0 aquisição contínua)
        SensorRawFrame sframe;
        while (xQueueReceive(g_q_sensor_tx, &sframe, 0) == pdTRUE) {
            if (jsonl_serialize_sensor_frame(&g_jsonl_ctx, tx_buf, sizeof(tx_buf), sframe.timestamp_ms, &sframe)) {
                Serial.print(tx_buf);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

// ============================================================================
// 5. TaskLcdDisplay: Atualização diferencial sem flicker do LCD 2004A (5 Hz)
// ============================================================================
static void TaskLcdDisplay(void *param) {
    (void)param;
    TickType_t last_wake = xTaskGetTickCount();
    uint32_t anim_phase = 0UL;

    for (;;) {
        PetStateSnapshot pet_snap{};
        SensorRawFrame sensor_snap{};
        bool has_sensor = false;
        bool show_host_frame = false;
        LCDFrameBuffer host_frame{};

        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            pet_snap = g_shared_pet_state;
            sensor_snap = g_latest_sensor_frame;
            has_sensor = g_has_latest_sensor;
            show_host_frame = g_has_host_lcd && fw_strcmp(g_active_mode, "PET_LAUNCH") == 0 &&
                (uint32_t)(now_monotonic_ms() - g_host_lcd_received_ms) < 2000UL;
            if (show_host_frame) host_frame = g_host_lcd_frame;
            xSemaphoreGive(g_state_mutex);
        }

        // Animação não-bloqueante de 2 quadros alternada a cada ~600 ms (3 ciclos de 200 ms)
        uint32_t visual_frame_idx = anim_phase / 3UL;
        anim_phase++;

        LCDFrameBuffer frame_buf{};
        if (show_host_frame) frame_buf = host_frame;
        else lcd_format_pet_frame(&pet_snap, visual_frame_idx, has_sensor ? &sensor_snap : NULL, &frame_buf);
        lcd_ctx_render_frame(&g_lcd_drv, &frame_buf);

        uint32_t hwm = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        if (xSemaphoreTake(g_state_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_shared_lcd_frame = frame_buf;
            g_metrics.hwm_lcd_bytes = hwm;
            xSemaphoreGive(g_state_mutex);
        }

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(LCD_REFRESH_PERIOD_MS));
    }
}

// ============================================================================
// Inicialização geral do ESP32 (setup / loop)
// ============================================================================
void setup(void) {
    Serial.begin(MOTIONPET_SERIAL_BAUD);
    jsonl_init(&g_jsonl_ctx);

    g_metrics = FirmwareRuntimeMetrics{};
    g_metrics.collection_active = true;
    g_metrics.sample_period_ms = DEFAULT_SENSOR_PERIOD_MS;

    // 1. Inicializa driver físico de sensores
    SensorPinConfig pin_cfg{};
    pin_cfg.pin_us_trig = PIN_HCSR04_TRIG;
    pin_cfg.pin_us_echo = PIN_HCSR04_ECHO;
    pin_cfg.pin_ir_digital = PIN_TCRT5000_DO;
    pin_cfg.pin_pot_adc = PIN_POT_ADC1;
    pin_cfg.pin_ir_analog = DEFAULT_IR_ANALOG_EN ? PIN_TCRT5000_AO : -1;
    pin_cfg.ir_enabled = DEFAULT_IR_ENABLED;
    pin_cfg.ir_analog_enabled = DEFAULT_IR_ANALOG_EN;
    pin_cfg.ir_active_low = DEFAULT_IR_ACTIVE_LOW;
    pin_cfg.pot_enabled = DEFAULT_POT_ENABLED;
    sensors_driver_init(&g_sensor_drv, &pin_cfg, NULL);

    // 2. Inicializa pipeline TinyML embarcado e persistência NVS antidesgaste
    gesture_classifier_ctx_init(&g_gesture_ctx, NULL);
    pet_persistence_init(&g_pet_nvs, NULL, PET_NVS_MIN_AUTO_INTERVAL_MS);

    // 3. Inicializa driver do LCD 2004A pelo adaptador I2C PCF8574 (SDA=GPIO21, SCL=GPIO22)
    LCDPinConfig lcd_cfg{};
    lcd_i2c_fill_pin_config(&lcd_cfg);
    lcd_ctx_init(&g_lcd_drv, &lcd_cfg, &g_lcd_i2c_hal_ops);
    lcd_ctx_load_default_glyphs(&g_lcd_drv);
    lcd_play_boot_animation(&g_lcd_drv);

    // 4. Inicializa estado inicial compartilhado antes da partida das tasks
    pet_init(&g_shared_pet_state, "Bitinho", PERSONALITY_CURIOUS);
    lcd_format_pet_frame(&g_shared_pet_state, 0UL, NULL, &g_shared_lcd_frame);

    // 5. Cria mutex e filas estáticas FreeRTOS
    g_state_mutex = xSemaphoreCreateMutex();
    g_q_sensor_infer = xQueueCreate(QUEUE_LEN_SENSOR_INFER, sizeof(SensorRawFrame));
    g_q_sensor_tx = xQueueCreate(QUEUE_LEN_SENSOR_TX, sizeof(SensorRawFrame));
    g_q_gesture_pet = xQueueCreate(QUEUE_LEN_GESTURE_PET, sizeof(GestureEvent));
    g_q_gesture_tx = xQueueCreate(QUEUE_LEN_GESTURE_TX, sizeof(GestureEvent));
    g_q_cmd_pet = xQueueCreate(QUEUE_LEN_CMD_PET, sizeof(PetCmdQueueItem));
    g_q_pet_reply_tx = xQueueCreate(QUEUE_LEN_CMD_PET, sizeof(PetReplyQueueItem));

    // Disabled without private local configuration. No serial ownership in this module.
    iot_transport_start();

    // 6. Cria as 5 tasks FreeRTOS em APP_CPU_NUM (evitando complexidade multicore desnecessária)
    xTaskCreatePinnedToCore(
        TaskSensorAcquire,
        "SensorAcq",
        TASK_STACK_SENSOR_BYTES,
        NULL,
        TASK_PRIO_SENSOR_ACQUIRE,
        &g_task_sensor_handle,
        APP_CPU_NUM
    );

    xTaskCreatePinnedToCore(
        TaskGestureInfer,
        "GestureInf",
        TASK_STACK_GESTURE_BYTES,
        NULL,
        TASK_PRIO_GESTURE_INFER,
        &g_task_gesture_handle,
        APP_CPU_NUM
    );

    xTaskCreatePinnedToCore(
        TaskPetDomain,
        "PetDomain",
        TASK_STACK_PET_BYTES,
        NULL,
        TASK_PRIO_PET_DOMAIN,
        &g_task_pet_handle,
        APP_CPU_NUM
    );

    xTaskCreatePinnedToCore(
        TaskSerialComm,
        "SerialComm",
        TASK_STACK_SERIAL_BYTES,
        NULL,
        TASK_PRIO_SERIAL_COMM,
        &g_task_serial_handle,
        APP_CPU_NUM
    );

    xTaskCreatePinnedToCore(
        TaskLcdDisplay,
        "LcdDisplay",
        TASK_STACK_LCD_BYTES,
        NULL,
        TASK_PRIO_LCD_DISPLAY,
        &g_task_lcd_handle,
        APP_CPU_NUM
    );
}

void loop(void) {
    // Libera a task padrão do Arduino para não consumir ciclos de CPU
    vTaskDelay(pdMS_TO_TICKS(1000));
}
