#include "sensors/sensors_driver.h"
#include <stddef.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <esp_timer.h>

static void esp32_configure_pins(const SensorPinConfig *cfg) {
    pinMode(cfg->pin_us_trig, OUTPUT);
    digitalWrite(cfg->pin_us_trig, LOW);
    pinMode(cfg->pin_us_echo, INPUT);

    if (cfg->ir_enabled) {
        pinMode(cfg->pin_ir_digital, INPUT);
    }
    analogReadResolution(12);
}

static uint32_t esp32_measure_echo_us(uint8_t pin_trig, uint8_t pin_echo, uint32_t timeout_us) {
    // Caso o pino ECHO esteja preso em HIGH (desconexão/falha), aguarda brevemente ou aborta sem travar
    if (digitalRead(pin_echo) == HIGH) {
        uint64_t guard_start = (uint64_t)esp_timer_get_time();
        while (digitalRead(pin_echo) == HIGH) {
            if (((uint64_t)esp_timer_get_time() - guard_start) > 2000ULL) {
                return 0UL;
            }
        }
    }

    // Pulso padrão de 10 µs no TRIG
    digitalWrite(pin_trig, LOW);
    delayMicroseconds(2);
    digitalWrite(pin_trig, HIGH);
    delayMicroseconds(10);
    digitalWrite(pin_trig, LOW);

    // Medição monotônica limitada por timeout_us (sem bloqueio indefinido)
    uint64_t t_wait_start = (uint64_t)esp_timer_get_time();
    while (digitalRead(pin_echo) == LOW) {
        if (((uint64_t)esp_timer_get_time() - t_wait_start) >= (uint64_t)timeout_us) {
            return 0UL;
        }
    }

    uint64_t t_pulse_start = (uint64_t)esp_timer_get_time();
    while (digitalRead(pin_echo) == HIGH) {
        uint64_t elapsed = (uint64_t)esp_timer_get_time() - t_pulse_start;
        if (elapsed >= (uint64_t)timeout_us) {
            return 0UL;
        }
    }
    uint64_t duration = (uint64_t)esp_timer_get_time() - t_pulse_start;
    return (uint32_t)duration;
}

static int esp32_read_digital(uint8_t pin) {
    return digitalRead(pin);
}

static uint16_t esp32_read_adc1_raw(uint8_t pin) {
    int val = analogRead(pin);
    if (val < 0) return 0U;
    if (val > 4095) return 4095U;
    return (uint16_t)val;
}

static uint64_t esp32_monotonic_us(void) {
    return (uint64_t)esp_timer_get_time();
}
#endif // ARDUINO

bool ultrasonic_echo_us_to_cm(uint32_t echo_us, float *out_distance_cm) {
    if (!out_distance_cm) {
        return false;
    }
    if (echo_us == 0UL) {
        *out_distance_cm = -1.0f;
        return false;
    }
    // d_cm = (echo_us * 0.0343f) / 2.0f = echo_us * 0.01715f
    float cm = (float)echo_us * 0.01715f;
    if (cm < ULTRASONIC_MIN_DISTANCE_CM || cm > ULTRASONIC_MAX_DISTANCE_CM) {
        *out_distance_cm = -1.0f;
        return false;
    }
    *out_distance_cm = cm;
    return true;
}

float adc1_raw_to_norm(uint16_t raw_value) {
    if (raw_value >= 4095U) {
        return 1.0f;
    }
    float norm = (float)raw_value / ADC_MAX_RAW_VALUE;
    if (norm < 0.0f) return 0.0f;
    if (norm > 1.0f) return 1.0f;
    return norm;
}

bool sensors_driver_init(
    SensorDriverContext *ctx,
    const SensorPinConfig *cfg,
    const SensorHalOps *custom_hal
) {
    if (!ctx || !cfg) {
        return false;
    }
    ctx->config = *cfg;
    ctx->timeout_us = ULTRASONIC_TIMEOUT_US;
    ctx->last_timestamp_ms = 0UL;
    ctx->initialized = false;

    if (custom_hal != NULL) {
        ctx->hal = *custom_hal;
    } else {
#ifdef ARDUINO
        ctx->hal.configure_pins = esp32_configure_pins;
        ctx->hal.measure_echo_us = esp32_measure_echo_us;
        ctx->hal.read_digital = esp32_read_digital;
        ctx->hal.read_adc1_raw = esp32_read_adc1_raw;
        ctx->hal.monotonic_us = esp32_monotonic_us;
#else
        return false;
#endif
    }

    if (ctx->hal.configure_pins) {
        ctx->hal.configure_pins(&ctx->config);
    }
    ctx->initialized = true;
    return true;
}

void sensors_driver_read(SensorDriverContext *ctx, SensorRawFrame *out_frame) {
    if (!ctx || !out_frame || !ctx->initialized) {
        return;
    }

    uint64_t t0_us = ctx->hal.monotonic_us ? ctx->hal.monotonic_us() : 0ULL;
    uint32_t ts_ms = (uint32_t)(t0_us / 1000ULL);
    if (ctx->last_timestamp_ms > 0UL && ts_ms <= ctx->last_timestamp_ms) {
        ts_ms = ctx->last_timestamp_ms + 1UL;
    }
    ctx->last_timestamp_ms = ts_ms;

    uint32_t echo_us = 0UL;
    if (ctx->hal.measure_echo_us) {
        echo_us = ctx->hal.measure_echo_us(
            ctx->config.pin_us_trig,
            ctx->config.pin_us_echo,
            ctx->timeout_us
        );
    }

    float dist_cm = -1.0f;
    bool valid_us = ultrasonic_echo_us_to_cm(echo_us, &dist_cm);

    bool ir_det = false;
    uint16_t ir_a_raw = 0U;
    float ir_a_norm = 0.0f;
    if (ctx->config.ir_enabled && ctx->hal.read_digital) {
        int raw_ir = ctx->hal.read_digital(ctx->config.pin_ir_digital);
        ir_det = ctx->config.ir_active_low ? (raw_ir == 0) : (raw_ir != 0);
        if (ctx->config.ir_analog_enabled && ctx->config.pin_ir_analog >= 0 && ctx->hal.read_adc1_raw) {
            ir_a_raw = ctx->hal.read_adc1_raw((uint8_t)ctx->config.pin_ir_analog);
            ir_a_norm = adc1_raw_to_norm(ir_a_raw);
        }
    }

    uint16_t pot_raw = 2048U;
    float pot_norm = 0.5f;
    if (ctx->config.pot_enabled && ctx->hal.read_adc1_raw) {
        pot_raw = ctx->hal.read_adc1_raw(ctx->config.pin_pot_adc);
        pot_norm = adc1_raw_to_norm(pot_raw);
    } else if (!ctx->config.pot_enabled) {
        pot_raw = 0U;
        pot_norm = 0.0f;
    }

    uint64_t t1_us = ctx->hal.monotonic_us ? ctx->hal.monotonic_us() : t0_us;

    out_frame->distance_cm = dist_cm;
    out_frame->valid_ultrasonic = valid_us;
    out_frame->ir_detected = ir_det;
    out_frame->pot_norm = pot_norm;
    out_frame->pot_raw = pot_raw;
    out_frame->timestamp_ms = ts_ms;
    out_frame->echo_duration_us = echo_us;
    out_frame->ir_analog_raw = ir_a_raw;
    out_frame->ir_analog_norm = ir_a_norm;
    out_frame->acquire_duration_us = (t1_us >= t0_us) ? (uint32_t)(t1_us - t0_us) : 0UL;
}
