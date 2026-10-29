"""Suíte automatizada do Ciclo 3: Firmware C++ ESP32, paridade Python/C++ e preparação de bancada.

Compila os módulos reais em C++ de `firmware/` (`sensors_driver.cpp`, `jsonl_protocol.cpp`,
`gesture_classifier.cpp`, `pet_state.cpp`, `pet_persistence.cpp` e `lcd2004_driver.cpp`) em uma
biblioteca nativa de host (`cl.exe` freestanding DLL / `g++` shared lib) e valida via `ctypes`:

1. Driver físico de sensores simulado via HAL (HC-SR04, timeouts, TCRT5000 digital/ADC1, Pot ADC1).
2. Formação de `sensor_frame` e demais envelopes JSON Lines v1 + integração com `SerialSessionRecorder`.
3. Recuperação de falhas de comunicação serial (JSON truncado/corrompido, versão inválida, saltos de seq).
4. Processamento contínuo de janelas ML e paridade 1:1 entre `MLGestureClassifier` (Python) e C++ TinyML,
   além de troca intercambiável do header `tinyml_model.h` (`mlp_compact` <-> `decision_tree`).
5. Paridade 1:1 da máquina de estados do Pet entre `PetEngine` (Python) e `pet_state.cpp` (C++).
6. Persistência NVS antidesgaste (roundtrip, skip sem mudança, throttle de 30 s e recuperação de CRC32 corrompido).
7. Equivalência caractere-por-caractere do LCD 20x4 (`Lcd20x4Renderer` vs `lcd_format_pet_frame`) + protocolo
   de barramento paralelo de 4 bits HD44780 (init, CGRAM e atualização diferencial por dirty shadow buffer).
8. Auditoria estática de alocação zero-heap, segurança elétrica (`PROPOSED_PENDING_BENCH_INSPECTION`) e build Xtensa.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

from ml.classifiers import MLGestureClassifier
from ml.collection import generate_synthetic_session
from ml.collection.collector import SerialSessionRecorder
from ml.collection.validator import validate_session_records
from ml.export.cpp_exporter import export_model_to_cpp_header
from ml.export.parity import (
    _unload_shared_library,
    detect_esp32_xtensa_compiler,
    detect_native_cpp_compiler,
    verify_zero_dynamic_allocation,
)
from ml.preprocessing import preprocess_records
from ml.schemas import DataOrigin, PreprocessingConfig, StabilizerConfig
from ml.training import TrainingConfig, split_windows_grouped, train_candidate_models
from ml.training.trainer import TrainedBundle, load_trained_bundle
from terminal.communication.protocol import (
    AckPayload,
    CommandType,
    ErrorPayload,
    GestureEventPayload,
    GestureSource,
    GestureType,
    LcdFramePayload,
    MessageType,
    PetCommandPayload,
    ProtocolCodec,
    SensorFramePayload,
)
from terminal.communication.transport import create_virtual_serial_pair
from terminal.pet.engine import PetEngine
from terminal.pet.state import EvolutionStage, PetAnimation, PetMood, PetPersonality, PetState
from terminal.renderer.lcd20x4 import Lcd20x4Renderer

REPO_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_DIR = REPO_ROOT / "firmware"
MODELS_DIR = REPO_ROOT / "data" / "models"


def _build_freestanding_stddef_h() -> str:
    return """#ifndef MOTIONPET_FREESTANDING_STDDEF_H
#define MOTIONPET_FREESTANDING_STDDEF_H
#if defined(_WIN64) || defined(__aarch64__) || defined(__x86_64__)
typedef unsigned long long size_t;
typedef long long ptrdiff_t;
#else
typedef unsigned int size_t;
typedef int ptrdiff_t;
#endif
#ifndef NULL
#ifdef __cplusplus
#define NULL 0
#else
#define NULL ((void *)0)
#endif
#endif
#ifndef offsetof
#ifdef __cplusplus
#define offsetof(s, m) ((size_t)&reinterpret_cast<char const volatile &>((((s *)0)->m)))
#else
#define offsetof(s, m) ((size_t)&(((s *)0)->m))
#endif
#endif
#endif
"""


def _build_firmware_bridge_cpp() -> str:
    """Gera unidade de tradução C++ freestanding integrando todos os módulos reais do firmware."""
    return r"""
#define TINYML_FREESTANDING 1
#include <stddef.h>

#ifdef _MSC_VER
extern "C" {
int _fltused = 0;
void *memset(void *dst, int c, size_t n);
void *memcpy(void *dst, const void *src, size_t n);
#pragma function(memset, memcpy)
void *memset(void *dst, int c, size_t n) {
    unsigned char *p = (unsigned char *)dst;
    while (n--) { *p++ = (unsigned char)c; }
    return dst;
}
void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) { *d++ = *s++; }
    return dst;
}
}
#define FW_EXPORT extern "C" __declspec(dllexport)
#else
#define FW_EXPORT extern "C" __attribute__((visibility("default")))
#endif

#include "sensors/sensors_driver.cpp"
#include "communication/jsonl_protocol.cpp"
#include "gestures/gesture_classifier.cpp"
#include "pet/pet_state.cpp"
#include "pet/pet_persistence.cpp"
#include "display/lcd2004_driver.cpp"

// ============================================================================
// 1. Ponte determinística para `sensors_driver.cpp`
// ============================================================================
static SensorDriverContext g_test_sensor_ctx;
static uint32_t g_mock_echo_us = 0UL;
static int g_mock_ir_pin_level = 1;
static uint16_t g_mock_pot_raw = 0U;
static uint16_t g_mock_ir_ao_raw = 0U;
static uint64_t g_mock_clock_us = 1000ULL;
static uint32_t g_mock_echo_spend_us = 450UL;

static void mock_sensor_cfg_pins(const SensorPinConfig *cfg) {
    (void)cfg;
}

static uint32_t mock_sensor_measure_echo(uint8_t trig, uint8_t echo, uint32_t timeout_us) {
    (void)trig;
    (void)echo;
    g_mock_clock_us += g_mock_echo_spend_us;
    if (g_mock_echo_us > timeout_us) {
        return 0UL;
    }
    return g_mock_echo_us;
}

static int mock_sensor_read_digital(uint8_t pin) {
    (void)pin;
    return g_mock_ir_pin_level;
}

static uint16_t mock_sensor_read_adc1(uint8_t pin) {
    if (pin == 39U) {
        return g_mock_ir_ao_raw;
    }
    return g_mock_pot_raw;
}

static uint64_t mock_sensor_monotonic_us(void) {
    return g_mock_clock_us;
}

FW_EXPORT bool fw_sensor_echo_to_cm(uint32_t echo_us, float *out_cm) {
    return ultrasonic_echo_us_to_cm(echo_us, out_cm);
}

FW_EXPORT float fw_sensor_adc_norm(uint16_t raw_val) {
    return adc1_raw_to_norm(raw_val);
}

FW_EXPORT void fw_sensor_init(bool ir_enabled, bool ir_analog_en, bool ir_active_low, bool pot_enabled) {
    SensorPinConfig cfg{};
    cfg.pin_us_trig = 5U;
    cfg.pin_us_echo = 34U;
    cfg.pin_ir_digital = 35U;
    cfg.pin_pot_adc = 36U;
    cfg.pin_ir_analog = ir_analog_en ? 39 : -1;
    cfg.ir_enabled = ir_enabled;
    cfg.ir_analog_enabled = ir_analog_en;
    cfg.ir_active_low = ir_active_low;
    cfg.pot_enabled = pot_enabled;

    SensorHalOps hal{};
    hal.configure_pins = mock_sensor_cfg_pins;
    hal.measure_echo_us = mock_sensor_measure_echo;
    hal.read_digital = mock_sensor_read_digital;
    hal.read_adc1_raw = mock_sensor_read_adc1;
    hal.monotonic_us = mock_sensor_monotonic_us;

    g_mock_clock_us = 10000ULL;
    sensors_driver_init(&g_test_sensor_ctx, &cfg, &hal);
}

FW_EXPORT void fw_sensor_step(
    uint64_t clock_us,
    uint32_t echo_us,
    uint32_t spend_us,
    int ir_pin_level,
    uint16_t pot_raw,
    uint16_t ir_ao_raw,
    float *out_dist_cm,
    int32_t *out_valid_us,
    int32_t *out_ir_det,
    float *out_pot_norm,
    float *out_ir_ao_norm,
    uint32_t *out_ts_ms,
    uint32_t *out_acq_us
) {
    g_mock_clock_us = clock_us;
    g_mock_echo_us = echo_us;
    g_mock_echo_spend_us = spend_us;
    g_mock_ir_pin_level = ir_pin_level;
    g_mock_pot_raw = pot_raw;
    g_mock_ir_ao_raw = ir_ao_raw;

    SensorRawFrame f{};
    sensors_driver_read(&g_test_sensor_ctx, &f);
    *out_dist_cm = f.distance_cm;
    *out_valid_us = f.valid_ultrasonic ? 1 : 0;
    *out_ir_det = f.ir_detected ? 1 : 0;
    *out_pot_norm = f.pot_norm;
    *out_ir_ao_norm = f.ir_analog_norm;
    *out_ts_ms = f.timestamp_ms;
    *out_acq_us = f.acquire_duration_us;
}

// ============================================================================
// 2. Ponte para `jsonl_protocol.cpp`
// ============================================================================
static JsonlContext g_test_jsonl;

FW_EXPORT void fw_jsonl_reset(void) {
    jsonl_init(&g_test_jsonl);
}

FW_EXPORT void fw_jsonl_stats(uint32_t *out_seq_tx, uint32_t *out_dropped, uint32_t *out_parse_err) {
    *out_seq_tx = g_test_jsonl.seq_tx;
    *out_dropped = g_test_jsonl.dropped_frames;
    *out_parse_err = g_test_jsonl.parse_errors;
}

FW_EXPORT bool fw_jsonl_make_sensor_frame(
    uint32_t ts_ms,
    float dist_cm,
    bool valid_us,
    bool ir_det,
    float pot_norm,
    char *out_buf,
    uint32_t cap
) {
    SensorRawFrame f{};
    f.distance_cm = dist_cm;
    f.valid_ultrasonic = valid_us;
    f.ir_detected = ir_det;
    f.pot_norm = pot_norm;
    f.timestamp_ms = ts_ms;
    return jsonl_serialize_sensor_frame(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, &f);
}

FW_EXPORT bool fw_jsonl_make_gesture_event(
    uint32_t ts_ms,
    int32_t gesture_id,
    float conf,
    int32_t source_id,
    uint16_t win_ms,
    char *out_buf,
    uint32_t cap
) {
    GestureEvent ev{};
    ev.gesture = (GestureType)gesture_id;
    ev.confidence = conf;
    ev.source = (GestureSource)source_id;
    ev.window_ms = win_ms;
    ev.timestamp_ms = ts_ms;
    return jsonl_serialize_gesture_event(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, &ev);
}

FW_EXPORT bool fw_jsonl_make_ack(uint32_t ts_ms, uint32_t ack_seq, const char *status, char *out_buf, uint32_t cap) {
    return jsonl_serialize_ack(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, ack_seq, status);
}

FW_EXPORT bool fw_jsonl_make_error(
    uint32_t ts_ms,
    const char *code,
    const char *msg,
    int64_t ref_seq,
    char *out_buf,
    uint32_t cap
) {
    return jsonl_serialize_error_ex(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, code, msg, ref_seq);
}

FW_EXPORT bool fw_jsonl_parse_line(
    const char *line,
    int32_t *out_kind,
    uint32_t *out_seq,
    int32_t *out_pet_cmd,
    uint32_t *out_param_u32,
    int32_t *out_param_bool,
    char *out_mode_arg,
    uint32_t mode_cap,
    char *out_err_code,
    uint32_t err_cap
) {
    JsonlRxParsed p{};
    bool ok = jsonl_parse_incoming_line(&g_test_jsonl, line, &p);
    *out_kind = (int32_t)p.kind;
    *out_seq = p.seq;
    *out_pet_cmd = (int32_t)p.pet_cmd;
    *out_param_u32 = p.param_u32;
    *out_param_bool = p.param_bool ? 1 : 0;
    fw_strncpy(out_mode_arg, p.mode_arg, (size_t)mode_cap);
    fw_strncpy(out_err_code, p.error_code, (size_t)err_cap);
    return ok;
}

// ============================================================================
// 3. Ponte para `gesture_classifier.cpp` + `tinyml_model.h`
// ============================================================================
static GestureClassifierContext g_test_gctx;

FW_EXPORT const char* fw_gesture_model_name(void) {
    return gesture_classifier_model_name();
}

FW_EXPORT const char* fw_gesture_exp_status(void) {
    return gesture_classifier_experimental_status();
}

FW_EXPORT bool fw_gesture_is_synthetic(void) {
    return gesture_classifier_is_engineering_synthetic_model();
}

FW_EXPORT void fw_gesture_init(
    float min_conf,
    uint16_t min_consec,
    uint32_t cooldown_ms,
    bool req_neutral
) {
    GestureStabilizerConfig cfg{};
    cfg.min_confidence = min_conf;
    cfg.min_consecutive_windows = min_consec;
    cfg.cooldown_ms = cooldown_ms;
    cfg.require_neutral_reset = req_neutral;
    gesture_classifier_ctx_init(&g_test_gctx, &cfg);
}

FW_EXPORT bool fw_gesture_step(
    float dist_cm,
    bool valid_us,
    bool ir_det,
    uint32_t ts_ms,
    float *out_features_11,
    int32_t *out_raw_cls,
    float *out_raw_conf,
    int32_t *out_rej_reason,
    int32_t *out_emitted_cls,
    float *out_emitted_conf,
    uint16_t *out_win_ms
) {
    gesture_classifier_ctx_push_sample(&g_test_gctx, dist_cm, valid_us, ir_det, ts_ms);
    GestureEvent ev{};
    bool emitted = gesture_classifier_ctx_infer(&g_test_gctx, &ev);

    out_features_11[0]  = g_test_gctx.last_features.d_min;
    out_features_11[1]  = g_test_gctx.last_features.d_max;
    out_features_11[2]  = g_test_gctx.last_features.d_mean;
    out_features_11[3]  = g_test_gctx.last_features.d_std;
    out_features_11[4]  = g_test_gctx.last_features.d_delta;
    out_features_11[5]  = g_test_gctx.last_features.v_mean;
    out_features_11[6]  = g_test_gctx.last_features.v_peak;
    out_features_11[7]  = g_test_gctx.last_features.trend_slope;
    out_features_11[8]  = g_test_gctx.last_features.sign_inversions;
    out_features_11[9]  = g_test_gctx.ir_active_ratio_unused_pad ? 0.0f : g_test_gctx.last_features.ir_active_ratio;
    out_features_11[10] = g_test_gctx.last_features.invalid_ratio;

    *out_raw_cls = (int32_t)g_test_gctx.last_raw_gesture;
    *out_raw_conf = g_test_gctx.last_raw_confidence;
    *out_rej_reason = (int32_t)g_test_gctx.last_rejection;
    if (emitted) {
        *out_emitted_cls = (int32_t)ev.gesture;
        *out_emitted_conf = ev.confidence;
        *out_win_ms = ev.window_ms;
    } else {
        *out_emitted_cls = 0;
        *out_emitted_conf = 0.0f;
        *out_win_ms = 0U;
    }
    return emitted;
}

// ============================================================================
// 4. Ponte para `pet_state.cpp` + `jsonl_serialize_pet_state` + `lcd_format_pet_frame`
// ============================================================================
static PetStateSnapshot g_test_pet;

FW_EXPORT void fw_pet_init(const char *name, int32_t personality_id) {
    pet_init(&g_test_pet, name, (PetPersonality)personality_id);
}

FW_EXPORT void fw_pet_tick(void) {
    pet_tick(&g_test_pet);
}

FW_EXPORT bool fw_pet_command(const char *cmd_name) {
    PetCommandType cmd = pet_command_from_string(cmd_name);
    return pet_apply_command(&g_test_pet, cmd);
}

FW_EXPORT bool fw_pet_gesture_event(const char *gesture_name, float conf, float min_conf) {
    GestureEvent ev{};
    ev.gesture = gesture_type_from_string(gesture_name);
    ev.confidence = conf;
    ev.source = GESTURE_SOURCE_TINYML;
    ev.window_ms = 630U;
    ev.timestamp_ms = 1000UL;
    return pet_apply_gesture_event(&g_test_pet, &ev, min_conf);
}

FW_EXPORT bool fw_pet_to_jsonl(uint32_t ts_ms, char *out_buf, uint32_t cap) {
    return jsonl_serialize_pet_state(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, &g_test_pet);
}

FW_EXPORT bool fw_pet_to_lcd_jsonl(
    uint32_t ts_ms,
    uint32_t frame_idx,
    bool has_sensor,
    float dist_cm,
    bool valid_us,
    char *out_buf,
    uint32_t cap
) {
    SensorRawFrame sf{};
    sf.distance_cm = dist_cm;
    sf.valid_ultrasonic = valid_us;
    LCDFrameBuffer lcd{};
    lcd_format_pet_frame(&g_test_pet, frame_idx, has_sensor ? &sf : NULL, &lcd);
    return jsonl_serialize_lcd_frame(&g_test_jsonl, out_buf, (size_t)cap, ts_ms, &lcd);
}

// ============================================================================
// 5. Ponte para `pet_persistence.cpp` (NVS em memória com injeção de corrupção)
// ============================================================================
static PetPersistenceContext g_test_nvs;
static uint8_t g_mock_nvs_storage[512];
static size_t g_mock_nvs_len = 0U;

static bool mock_nvs_read(void *out_data, size_t expected_len) {
    if (g_mock_nvs_len != expected_len) {
        return false;
    }
    uint8_t *dst = (uint8_t *)out_data;
    for (size_t i = 0U; i < expected_len; ++i) {
        dst[i] = g_mock_nvs_storage[i];
    }
    return true;
}

static bool mock_nvs_write(const void *data, size_t len) {
    if (len > sizeof(g_mock_nvs_storage)) {
        return false;
    }
    const uint8_t *src = (const uint8_t *)data;
    for (size_t i = 0U; i < len; ++i) {
        g_mock_nvs_storage[i] = src[i];
    }
    g_mock_nvs_len = len;
    return true;
}

FW_EXPORT void fw_nvs_reset(uint32_t min_auto_interval_ms) {
    g_mock_nvs_len = 0U;
    for (size_t i = 0U; i < sizeof(g_mock_nvs_storage); ++i) {
        g_mock_nvs_storage[i] = 0U;
    }
    PetNvsBackendOps ops{};
    ops.read_blob = mock_nvs_read;
    ops.write_blob = mock_nvs_write;
    pet_persistence_init(&g_test_nvs, &ops, min_auto_interval_ms);
}

FW_EXPORT int32_t fw_nvs_save_current_pet(uint32_t now_ms, bool force_manual) {
    return (int32_t)pet_persistence_save(&g_test_nvs, &g_test_pet, now_ms, force_manual);
}

FW_EXPORT int32_t fw_nvs_load_into_current_pet(void) {
    PetStateSnapshot loaded{};
    PetNvsStatus st = pet_persistence_load(&g_test_nvs, &loaded);
    if (st == PET_NVS_OK) {
        g_test_pet = loaded;
    }
    return (int32_t)st;
}

FW_EXPORT void fw_nvs_corrupt_byte(uint32_t byte_offset, uint8_t xor_mask) {
    if (byte_offset < g_mock_nvs_len) {
        g_mock_nvs_storage[byte_offset] ^= xor_mask;
    }
}

FW_EXPORT void fw_nvs_stats(
    uint32_t *out_writes,
    uint32_t *out_skipped,
    uint32_t *out_throttled,
    uint32_t *out_corrupt_recov,
    uint32_t *out_blob_size
) {
    *out_writes = g_test_nvs.total_writes;
    *out_skipped = g_test_nvs.skipped_unchanged;
    *out_throttled = g_test_nvs.throttled_writes;
    *out_corrupt_recov = g_test_nvs.corruption_recoveries;
    *out_blob_size = (uint32_t)g_mock_nvs_len;
}

// ============================================================================
// 6. Ponte para `lcd2004_driver.cpp` (Decodificador de barramento 4 bits HD44780)
// ============================================================================
static LCDDriverContext g_test_lcd_drv;
static uint8_t g_pin_levels[40];
static uint8_t g_bus_rs_log[4096];
static uint8_t g_bus_nibble_log[4096];
static uint32_t g_bus_nibble_count = 0UL;

static void mock_lcd_cfg_pins(const LCDPinConfig *cfg) {
    (void)cfg;
    for (int i = 0; i < 40; ++i) g_pin_levels[i] = 0U;
    g_bus_nibble_count = 0UL;
}

static void mock_lcd_write_pin(uint8_t pin, uint8_t level) {
    if (pin >= 40U) return;
    uint8_t prev = g_pin_levels[pin];
    g_pin_levels[pin] = level ? 1U : 0U;

    // Borda de descida do pino EN captura o nibble D7..D4 e estado de RS (HD44780 timing)
    if (pin == g_test_lcd_drv.pins.pin_en && prev == 1U && g_pin_levels[pin] == 0U) {
        if (g_bus_nibble_count < 4096UL) {
            uint8_t nib = 0U;
            if (g_pin_levels[g_test_lcd_drv.pins.pin_d4]) nib |= 0x01U;
            if (g_pin_levels[g_test_lcd_drv.pins.pin_d5]) nib |= 0x02U;
            if (g_pin_levels[g_test_lcd_drv.pins.pin_d6]) nib |= 0x04U;
            if (g_pin_levels[g_test_lcd_drv.pins.pin_d7]) nib |= 0x08U;
            g_bus_rs_log[g_bus_nibble_count] = g_pin_levels[g_test_lcd_drv.pins.pin_rs];
            g_bus_nibble_log[g_bus_nibble_count] = nib;
            g_bus_nibble_count++;
        }
    }
}

static void mock_lcd_delay_us(uint32_t us) {
    (void)us;
}

FW_EXPORT bool fw_lcd_hw_init_and_glyphs(void) {
    LCDPinConfig cfg{};
    cfg.pin_rs = 19U;
    cfg.pin_en = 18U;
    cfg.pin_d4 = 21U;
    cfg.pin_d5 = 22U;
    cfg.pin_d6 = 23U;
    cfg.pin_d7 = 27U;

    LCDHalOps hal{};
    hal.configure_pins = mock_lcd_cfg_pins;
    hal.write_pin = mock_lcd_write_pin;
    hal.delay_us = mock_lcd_delay_us;

    if (!lcd_ctx_init(&g_test_lcd_drv, &cfg, &hal)) {
        return false;
    }
    lcd_ctx_load_default_glyphs(&g_test_lcd_drv);
    return true;
}

FW_EXPORT void fw_lcd_hw_render_pet(
    uint32_t frame_idx,
    bool has_sensor,
    float dist_cm,
    bool valid_us,
    uint32_t *out_chars_written,
    uint32_t *out_total_bus_bytes
) {
    SensorRawFrame sf{};
    sf.distance_cm = dist_cm;
    sf.valid_ultrasonic = valid_us;
    LCDFrameBuffer fb{};
    lcd_format_pet_frame(&g_test_pet, frame_idx, has_sensor ? &sf : NULL, &fb);
    lcd_ctx_render_frame(&g_test_lcd_drv, &fb);
    *out_chars_written = g_test_lcd_drv.chars_written_last_frame;
    *out_total_bus_bytes = g_test_lcd_drv.total_bus_bytes_sent;
}

FW_EXPORT uint32_t fw_lcd_hw_get_nibble_log(uint8_t *out_rs, uint8_t *out_nibbles, uint32_t max_items) {
    uint32_t n = (g_bus_nibble_count < max_items) ? g_bus_nibble_count : max_items;
    for (uint32_t i = 0UL; i < n; ++i) {
        out_rs[i] = g_bus_rs_log[i];
        out_nibbles[i] = g_bus_nibble_log[i];
    }
    return n;
}
"""


def _compile_firmware_bridge_dll(
    work_dir: Path,
    override_tinyml_header: Path | None = None,
) -> ctypes.CDLL:
    """Compila os fontes C++ do firmware em DLL nativa freestanding para execução em pytest."""
    compiler = detect_native_cpp_compiler()
    if compiler is None:
        pytest.skip("Compilador C++ nativo não detectado no host.")

    # Copia árvore `firmware/` para diretório isolado permitindo testar troca de `tinyml_model.h`
    fw_copy = work_dir / "fw"
    shutil.copytree(
        FIRMWARE_DIR,
        fw_copy,
        ignore=shutil.ignore_patterns(".pio", "*.parity.json"),
    )
    if override_tinyml_header is not None:
        shutil.copy2(override_tinyml_header, fw_copy / "gestures" / "tinyml_model.h")

    src_cpp = work_dir / "fw_host_bridge.cpp"
    cpp_code = _build_firmware_bridge_cpp().replace(
        "g_test_gctx.ir_active_ratio_unused_pad ? 0.0f : g_test_gctx.last_features.ir_active_ratio",
        "g_test_gctx.last_features.ir_active_ratio",
    )
    src_cpp.write_text(cpp_code, encoding="utf-8")

    dll_ext = ".dll" if os.name == "nt" else ".so"
    dll_path = work_dir / f"fw_bridge_{uuid.uuid4().hex[:10]}{dll_ext}"

    kind, tool_path = compiler
    if kind == "msvc_freestanding_dll":
        (work_dir / "stddef.h").write_text(_build_freestanding_stddef_h(), encoding="utf-8")
        cl_path = Path(tool_path)
        host_folder = cl_path.parent.parent
        host_arch = host_folder.name.replace("Host", "").lower()
        host_native_bin = host_folder / host_arch
        inc_dir = host_folder.parent.parent / "include"

        env = os.environ.copy()
        extra_paths = [str(cl_path.parent)]
        if host_native_bin.is_dir():
            extra_paths.append(str(host_native_bin))
        env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])

        res = subprocess.run(
            [
                str(cl_path),
                "/nologo",
                "/std:c++17",
                "/O2",
                "/W3",
                "/GS-",
                "/Zl",
                "/EHs-c-",
                "/GR-",
                "/LD",
                f"/I{inc_dir}",
                f"/I{work_dir}",
                f"/I{fw_copy}",
                str(src_cpp),
                f"/Fe:{dll_path}",
                "/link",
                "/NOENTRY",
                "/NODEFAULTLIB",
            ],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    else:
        res = subprocess.run(
            [
                tool_path,
                "-std=gnu++17",
                "-O2",
                "-Wall",
                "-shared",
                "-fPIC",
                f"-I{fw_copy}",
                str(src_cpp),
                "-o",
                str(dll_path),
            ],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

    if res.returncode != 0 or not dll_path.is_file():
        raise RuntimeError(
            f"Falha ao compilar módulos C++ do firmware para testes de host:\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    lib = ctypes.CDLL(str(dll_path))
    _configure_bridge_signatures(lib)
    return lib


def _configure_bridge_signatures(lib: ctypes.CDLL) -> None:
    lib.fw_sensor_echo_to_cm.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
    lib.fw_sensor_echo_to_cm.restype = ctypes.c_bool

    lib.fw_sensor_adc_norm.argtypes = [ctypes.c_uint16]
    lib.fw_sensor_adc_norm.restype = ctypes.c_float

    lib.fw_sensor_init.argtypes = [ctypes.c_bool, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool]
    lib.fw_sensor_init.restype = None

    lib.fw_sensor_step.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.fw_sensor_step.restype = None

    lib.fw_jsonl_reset.argtypes = []
    lib.fw_jsonl_reset.restype = None

    lib.fw_jsonl_stats.argtypes = [
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.fw_jsonl_stats.restype = None

    lib.fw_jsonl_make_sensor_frame.argtypes = [
        ctypes.c_uint32,
        ctypes.c_float,
        ctypes.c_bool,
        ctypes.c_bool,
        ctypes.c_float,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_jsonl_make_sensor_frame.restype = ctypes.c_bool

    lib.fw_jsonl_make_gesture_event.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_float,
        ctypes.c_int32,
        ctypes.c_uint16,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_jsonl_make_gesture_event.restype = ctypes.c_bool

    lib.fw_jsonl_make_ack.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_jsonl_make_ack.restype = ctypes.c_bool

    lib.fw_jsonl_make_error.argtypes = [
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int64,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_jsonl_make_error.restype = ctypes.c_bool

    lib.fw_jsonl_parse_line.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_jsonl_parse_line.restype = ctypes.c_bool

    lib.fw_gesture_model_name.argtypes = []
    lib.fw_gesture_model_name.restype = ctypes.c_char_p

    lib.fw_gesture_exp_status.argtypes = []
    lib.fw_gesture_exp_status.restype = ctypes.c_char_p

    lib.fw_gesture_is_synthetic.argtypes = []
    lib.fw_gesture_is_synthetic.restype = ctypes.c_bool

    lib.fw_gesture_init.argtypes = [
        ctypes.c_float,
        ctypes.c_uint16,
        ctypes.c_uint32,
        ctypes.c_bool,
    ]
    lib.fw_gesture_init.restype = None

    lib.fw_gesture_step.argtypes = [
        ctypes.c_float,
        ctypes.c_bool,
        ctypes.c_bool,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint16),
    ]
    lib.fw_gesture_step.restype = ctypes.c_bool

    lib.fw_pet_init.argtypes = [ctypes.c_char_p, ctypes.c_int32]
    lib.fw_pet_init.restype = None

    lib.fw_pet_tick.argtypes = []
    lib.fw_pet_tick.restype = None

    lib.fw_pet_command.argtypes = [ctypes.c_char_p]
    lib.fw_pet_command.restype = ctypes.c_bool

    lib.fw_pet_gesture_event.argtypes = [ctypes.c_char_p, ctypes.c_float, ctypes.c_float]
    lib.fw_pet_gesture_event.restype = ctypes.c_bool

    lib.fw_pet_to_jsonl.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32]
    lib.fw_pet_to_jsonl.restype = ctypes.c_bool

    lib.fw_pet_to_lcd_jsonl.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_bool,
        ctypes.c_float,
        ctypes.c_bool,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    lib.fw_pet_to_lcd_jsonl.restype = ctypes.c_bool

    lib.fw_nvs_reset.argtypes = [ctypes.c_uint32]
    lib.fw_nvs_reset.restype = None

    lib.fw_nvs_save_current_pet.argtypes = [ctypes.c_uint32, ctypes.c_bool]
    lib.fw_nvs_save_current_pet.restype = ctypes.c_int32

    lib.fw_nvs_load_into_current_pet.argtypes = []
    lib.fw_nvs_load_into_current_pet.restype = ctypes.c_int32

    lib.fw_nvs_corrupt_byte.argtypes = [ctypes.c_uint32, ctypes.c_uint8]
    lib.fw_nvs_corrupt_byte.restype = None

    lib.fw_nvs_stats.argtypes = [
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.fw_nvs_stats.restype = None

    lib.fw_lcd_hw_init_and_glyphs.argtypes = []
    lib.fw_lcd_hw_init_and_glyphs.restype = ctypes.c_bool

    lib.fw_lcd_hw_render_pet.argtypes = [
        ctypes.c_uint32,
        ctypes.c_bool,
        ctypes.c_float,
        ctypes.c_bool,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.fw_lcd_hw_render_pet.restype = None

    lib.fw_lcd_hw_get_nibble_log.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_uint32,
    ]
    lib.fw_lcd_hw_get_nibble_log.restype = ctypes.c_uint32


@pytest.fixture(scope="module")
def fw_lib() -> Iterator[ctypes.CDLL]:
    with tempfile.TemporaryDirectory(
        prefix="motionpet_fw_cycle3_",
        ignore_cleanup_errors=True,
    ) as tmp_dir:
        lib = _compile_firmware_bridge_dll(Path(tmp_dir))
        try:
            yield lib
        finally:
            _unload_shared_library(lib)


def _cpp_pet_snapshot_as_payload(lib: ctypes.CDLL, codec: ProtocolCodec) -> PetState:
    buf = ctypes.create_string_buffer(512)
    assert lib.fw_pet_to_jsonl(1000, buf, 512)
    env = codec.decode(buf.value.decode("utf-8"))
    assert env.type == MessageType.PET_STATE
    return PetState.from_dict(env.data)


# ============================================================================
# 1. Testes do Driver Físico de Sensores Simulado via HAL (`sensors_driver.cpp`)
# ============================================================================
def test_sensors_driver_echo_conversion_and_bounds(fw_lib: ctypes.CDLL) -> None:
    dist = ctypes.c_float(0.0)

    # Timeout (0 us) -> inválido (-1.0 cm)
    assert not fw_lib.fw_sensor_echo_to_cm(0, ctypes.byref(dist))
    assert dist.value == pytest.approx(-1.0)

    # Ruído espúrio curto (< 115 us / < 2.0 cm) -> rejeitado
    assert not fw_lib.fw_sensor_echo_to_cm(80, ctypes.byref(dist))
    assert dist.value == pytest.approx(-1.0)

    # Eco válido (~1166 us -> ~20.0 cm a 343 m/s)
    assert fw_lib.fw_sensor_echo_to_cm(1166, ctypes.byref(dist))
    assert 19.8 <= dist.value <= 20.2

    # Acima de 400 cm (> 23324 us) -> rejeitado
    assert not fw_lib.fw_sensor_echo_to_cm(24500, ctypes.byref(dist))
    assert dist.value == pytest.approx(-1.0)

    # Normalização ADC1 12 bits [0..4095] -> [0.0..1.0]
    assert fw_lib.fw_sensor_adc_norm(0) == pytest.approx(0.0)
    assert fw_lib.fw_sensor_adc_norm(4095) == pytest.approx(1.0)
    assert fw_lib.fw_sensor_adc_norm(5000) == pytest.approx(1.0)
    assert 0.49 <= fw_lib.fw_sensor_adc_norm(2048) <= 0.51


def test_sensors_driver_hal_monotonic_timestamps_ir_and_adc1(fw_lib: ctypes.CDLL) -> None:
    fw_lib.fw_sensor_init(True, True, True, True)

    dist = ctypes.c_float()
    valid = ctypes.c_int32()
    ir_det = ctypes.c_int32()
    pot_norm = ctypes.c_float()
    ir_ao_norm = ctypes.c_float()
    ts_ms = ctypes.c_uint32()
    acq_us = ctypes.c_uint32()

    # Leitura 1: 70 ms, eco de ~15 cm (875 us), TCRT5000 active-low = LOW (detectado), pot = 50%
    fw_lib.fw_sensor_step(
        70_000,
        875,
        900,
        0,
        2048,
        1024,
        ctypes.byref(dist),
        ctypes.byref(valid),
        ctypes.byref(ir_det),
        ctypes.byref(pot_norm),
        ctypes.byref(ir_ao_norm),
        ctypes.byref(ts_ms),
        ctypes.byref(acq_us),
    )
    assert valid.value == 1
    assert 14.8 <= dist.value <= 15.2
    assert ir_det.value == 1
    assert pot_norm.value == pytest.approx(2048 / 4095.0, abs=1e-4)
    assert ir_ao_norm.value == pytest.approx(1024 / 4095.0, abs=1e-4)
    assert ts_ms.value == 70
    assert acq_us.value == 900

    # Leitura 2: relógio estagnado/regressivo + timeout (> 25000 us) -> timestamp continua monotônico!
    fw_lib.fw_sensor_step(
        65_000,
        30_000,
        25_000,
        1,
        4095,
        0,
        ctypes.byref(dist),
        ctypes.byref(valid),
        ctypes.byref(ir_det),
        ctypes.byref(pot_norm),
        ctypes.byref(ir_ao_norm),
        ctypes.byref(ts_ms),
        ctypes.byref(acq_us),
    )
    assert valid.value == 0
    assert dist.value == pytest.approx(-1.0)
    assert ir_det.value == 0
    assert pot_norm.value == pytest.approx(1.0)
    assert ts_ms.value == 71  # estritamente monotônico (> 70)
    assert acq_us.value == 25_000


# ============================================================================
# 2. Formação de `sensor_frame` / JSON Lines v1 e Integração com `SerialSessionRecorder`
# ============================================================================
def test_jsonl_envelopes_decode_cleanly_in_python_protocol_codec(fw_lib: ctypes.CDLL) -> None:
    fw_lib.fw_jsonl_reset()
    codec = ProtocolCodec()
    buf = ctypes.create_string_buffer(512)

    # 1. sensor_frame válido
    assert fw_lib.fw_jsonl_make_sensor_frame(70, 23.456, True, True, 0.75, buf, 512)
    raw_line = buf.value.decode("utf-8")
    assert raw_line.endswith("\n")
    env1 = codec.decode(raw_line)
    assert env1.v == 1 and env1.seq == 1 and env1.ts_ms == 70
    assert env1.type == MessageType.SENSOR_FRAME
    sf1 = SensorFramePayload.from_dict(env1.data)
    assert sf1.distance_cm == pytest.approx(23.46, abs=0.01)
    assert sf1.valid_ultrasonic is True
    assert sf1.ir_detected is True
    assert sf1.pot_norm == pytest.approx(0.75, abs=0.001)

    # 2. sensor_frame em timeout (`distance_cm: null`, `valid_ultrasonic: false`)
    assert fw_lib.fw_jsonl_make_sensor_frame(140, -1.0, False, False, 0.0, buf, 512)
    env2 = codec.decode(buf.value.decode("utf-8"))
    sf2 = SensorFramePayload.from_dict(env2.data)
    assert sf2.distance_cm is None
    assert sf2.valid_ultrasonic is False

    # 3. gesture_event (`GESTURE_APPROACH = 1`, `GESTURE_SOURCE_TINYML = 3`)
    assert fw_lib.fw_jsonl_make_gesture_event(630, 1, 0.9123, 3, 630, buf, 512)
    env3 = codec.decode(buf.value.decode("utf-8"))
    assert env3.type == MessageType.GESTURE_EVENT
    ge = GestureEventPayload.from_dict(env3.data)
    assert ge.gesture == GestureType.APPROACH
    assert ge.source == GestureSource.TINYML
    assert ge.confidence == pytest.approx(0.9123, abs=1e-4)
    assert ge.window_ms == 630

    # 4. ack (`ack_seq` + `status`)
    assert fw_lib.fw_jsonl_make_ack(700, 12, b"diag:acq=on,per_ms=70", buf, 512)
    env4 = codec.decode(buf.value.decode("utf-8"))
    assert env4.type == MessageType.ACK
    ack = AckPayload.from_dict(env4.data)
    assert ack.ack_seq == 12
    assert ack.status == "diag:acq=on,per_ms=70"

    # 5. error (`code` + `message` + `ref_seq`)
    assert fw_lib.fw_jsonl_make_error(710, b"BAD_JSON", b"Malformed frame", 13, buf, 512)
    env5 = codec.decode(buf.value.decode("utf-8"))
    assert env5.type == MessageType.ERROR
    err = ErrorPayload.from_dict(env5.data)
    assert err.code == "BAD_JSON"
    assert err.ref_seq == 13


def test_cpp_sensor_frames_feed_directly_into_serial_session_recorder(fw_lib: ctypes.CDLL) -> None:
    """Valida P0: quadros `sensor_frame` gerados pelo C++ embarcado alimentam `SerialSessionRecorder`."""
    fw_lib.fw_jsonl_reset()
    fw_lib.fw_pet_init(b"Bitinho", 0)
    host_ep, fw_ep, _ = create_virtual_serial_pair()

    step_idx = 0
    buf = ctypes.create_string_buffer(512)

    def pump_firmware_tx() -> None:
        nonlocal step_idx
        step_idx += 1
        ts_ms = step_idx * 70
        # Intercala `pet_state` e `ack` como ocorre nas 5 tasks FreeRTOS para garantir filtragem limpa
        if step_idx % 7 == 0:
            assert fw_lib.fw_pet_to_jsonl(ts_ms, buf, 512)
            fw_ep.write_line(buf.value.decode("utf-8").strip())
        if step_idx % 9 == 0:
            assert fw_lib.fw_jsonl_make_ack(ts_ms, 0, b"collection_started", buf, 512)
            fw_ep.write_line(buf.value.decode("utf-8").strip())

        is_timeout = (step_idx == 11)
        dist = -1.0 if is_timeout else (32.0 - 0.6 * (step_idx % 10))
        ir = dist > 0 and dist < 12.0
        assert fw_lib.fw_jsonl_make_sensor_frame(ts_ms, dist, not is_timeout, ir, 0.25, buf, 512)
        fw_ep.write_line(buf.value.decode("utf-8").strip())

    recorder = SerialSessionRecorder(
        endpoint=host_ep,
        data_origin=DataOrigin.REAL_HARDWARE,
        step_callback=pump_firmware_tx,
    )
    records = recorder.record_schedule(
        participant_id="p_bench_01",
        session_id="sess_fw_p0_smoke",
        schedule=[("NEUTRAL", 10), ("APPROACH", 10), ("HOLD", 5)],
        timeout_sec=5.0,
    )

    assert len(records) == 25
    assert records[10].valid_ultrasonic is False
    assert records[10].distance_cm is None
    report = validate_session_records(records)
    assert report.valid, f"Falha na validação do dataset vindo do firmware C++: {report.errors}"


# ============================================================================
# 3. Recuperação de Falhas de Comunicação (`jsonl_protocol.cpp`)
# ============================================================================
def test_serial_protocol_fault_recovery_and_bench_commands(fw_lib: ctypes.CDLL) -> None:
    fw_lib.fw_jsonl_reset()
    codec = ProtocolCodec()

    kind = ctypes.c_int32()
    seq = ctypes.c_uint32()
    pet_cmd = ctypes.c_int32()
    param_u32 = ctypes.c_uint32()
    param_bool = ctypes.c_int32()
    mode_arg = ctypes.create_string_buffer(24)
    err_code = ctypes.create_string_buffer(24)

    def parse(line: str) -> bool:
        return bool(
            fw_lib.fw_jsonl_parse_line(
                line.encode("utf-8"),
                ctypes.byref(kind),
                ctypes.byref(seq),
                ctypes.byref(pet_cmd),
                ctypes.byref(param_u32),
                ctypes.byref(param_bool),
                mode_arg,
                24,
                err_code,
                24,
            )
        )

    # 1. JSON truncado/corrompido -> falha controlada sem travar
    assert not parse('{"v":1,"seq":1,"type":"pet_command"')
    assert err_code.value.decode("utf-8") != ""

    # 2. Versão incompatível v=2 -> rejeitado com código explícito
    assert not parse('{"v":2,"seq":2,"type":"pet_command","ts_ms":10,"data":{"command":"FEED"}}')
    assert "VERSION" in err_code.value.decode("utf-8")

    # 3. Comando desconhecido -> rejeitado
    assert not parse('{"v":1,"seq":3,"type":"pet_command","ts_ms":20,"data":{"command":"EXPLODE"}}')

    # 4. Recuperação imediata no próximo `pet_command` válido do host Python (seq=1)
    valid_feed = codec.encode(
        MessageType.PET_COMMAND,
        PetCommandPayload(command=CommandType.FEED).to_dict(),
        ts_ms=100,
    )
    assert parse(valid_feed)
    assert kind.value == 1  # RX_MSG_PET_COMMAND
    assert seq.value == 1
    assert pet_cmd.value == 0  # CMD_FEED

    # 5. Salto de sequência (seq=1 -> seq=5, 3 quadros perdidos) contabilizado sem travar
    for _ in range(3):
        codec.encode(MessageType.ACK, {"ack_seq": 0, "status": "skip"}, ts_ms=150)
    valid_switch = codec.encode(
        MessageType.PET_COMMAND,
        PetCommandPayload(command=CommandType.SWITCH_MODE, payload={"mode": "AIR_MUSIC"}).to_dict(),
        ts_ms=200,
    )
    assert parse(valid_switch)
    assert seq.value == 5
    assert mode_arg.value.decode("utf-8") == "AIR_MUSIC"

    seq_tx = ctypes.c_uint32()
    dropped = ctypes.c_uint32()
    parse_err = ctypes.c_uint32()
    fw_lib.fw_jsonl_stats(ctypes.byref(seq_tx), ctypes.byref(dropped), ctypes.byref(parse_err))
    assert dropped.value == 3
    assert parse_err.value == 3

    # 6. Comandos simples de bancada (`STOP`, `START`, `PERIOD 75`, `IR ON`, `DIAG`)
    assert parse("STOP\n") and kind.value == 4      # RX_MSG_ACQ_STOP
    assert parse("START\n") and kind.value == 3     # RX_MSG_ACQ_START
    assert parse("PERIOD 75") and kind.value == 5 and param_u32.value == 75
    assert parse("IR OFF") and kind.value == 6 and param_bool.value == 0
    assert parse("DIAG") and kind.value == 7       # RX_MSG_DIAG_REQUEST

    # 7. Buffer pequeno demais não corrompe `seq_tx`
    tiny_buf = ctypes.create_string_buffer(16)
    before_seq = seq_tx.value
    assert not fw_lib.fw_jsonl_make_sensor_frame(300, 20.0, True, False, 0.5, tiny_buf, 16)
    fw_lib.fw_jsonl_stats(ctypes.byref(seq_tx), ctypes.byref(dropped), ctypes.byref(parse_err))
    assert seq_tx.value == before_seq


# ============================================================================
# 4. Processamento Contínuo de Janelas TinyML + Paridade Python vs C++
# ============================================================================
def _generate_continuous_gesture_stream() -> list[tuple[int, float | None, bool, bool]]:
    """Gera série temporal contínua realista (96 amostras a 70 ms) com múltiplos gestos e timeouts."""
    stream: list[tuple[int, float | None, bool, bool]] = []
    ts = 0

    def push(dist: float | None, valid: bool = True, ir: bool = False) -> None:
        nonlocal ts
        ts += 70
        stream.append((ts, dist, valid, ir))

    # Segmento 1: NEUTRAL longe (~62 cm, 14 amostras, com 1 timeout isolado)
    for i in range(14):
        if i == 5:
            push(None, valid=False, ir=False)
        else:
            push(62.0 + 0.3 * ((i % 3) - 1), valid=True, ir=False)

    # Segmento 2: APPROACH (44 cm -> 9 cm em 12 amostras, ativando IR no final)
    for d in np.linspace(44.0, 9.0, 12):
        push(float(d), valid=True, ir=(d < 13.0))

    # Segmento 3: NEUTRAL de reset (65 cm, 14 amostras)
    for i in range(14):
        push(65.0 + 0.2 * (i % 2), valid=True, ir=False)

    # Segmento 4: HOLD estável na zona próxima (~14.5 cm, 15 amostras)
    for i in range(15):
        push(14.5 + 0.15 * ((i % 3) - 1), valid=True, ir=True)

    # Segmento 5: NEUTRAL de reset (64 cm, 14 amostras)
    for i in range(14):
        push(64.0 - 0.2 * (i % 2), valid=True, ir=False)

    # Segmento 6: RETREAT (10 cm -> 48 cm em 12 amostras)
    for d in np.linspace(10.0, 48.0, 12):
        push(float(d), valid=True, ir=(d < 13.0))

    # Segmento 7: NEUTRAL final (63 cm, 15 amostras)
    for _ in range(15):
        push(63.0, valid=True, ir=False)

    return stream


def _load_or_build_engineering_bundles() -> tuple[dict[str, TrainedBundle], bool]:
    """Carrega bundles de `data/models/` se presentes, ou treina corpus sintético em clone limpo."""
    mlp_path = MODELS_DIR / "mlp_compact.joblib"
    dt_path = MODELS_DIR / "decision_tree.joblib"
    if mlp_path.is_file() and dt_path.is_file():
        return (
            {
                "mlp_compact": load_trained_bundle(mlp_path),
                "decision_tree": load_trained_bundle(dt_path),
            },
            True,
        )

    records = []
    for p_idx in range(1, 7):
        records.extend(
            generate_synthetic_session(
                participant_id=f"p{p_idx:02d}",
                session_id=f"s_p{p_idx:02d}",
                seed=100 + p_idx,
            )
        )
    pre_cfg = PreprocessingConfig()
    windows = preprocess_records(records, config=pre_cfg)
    split = split_windows_grouped(windows, seed=42)
    bundles = train_candidate_models(split, pre_cfg, TrainingConfig(seed=42))
    return (bundles, False)


def test_tinyml_continuous_stream_parity_python_vs_cpp(fw_lib: ctypes.CDLL) -> None:
    """Alimenta sequência contínua de 96 leituras em Python e C++ verificando paridade 1:1."""
    assert fw_lib.fw_gesture_model_name().decode("utf-8") == "mlp_compact"
    assert fw_lib.fw_gesture_exp_status().decode("utf-8") == "AWAITING_REAL_DATA"
    assert fw_lib.fw_gesture_is_synthetic() is True

    bundles, from_disk = _load_or_build_engineering_bundles()
    mlp_bundle = bundles["mlp_compact"]

    stab_cfg = StabilizerConfig(
        min_confidence=0.55,
        min_consecutive_windows=2,
        cooldown_ms=450,
        require_neutral_reset=True,
    )
    py_clf = MLGestureClassifier(
        bundle=mlp_bundle,
        stabilizer_config=stab_cfg,
    )
    assert py_clf.is_loaded

    extra_tmp: tempfile.TemporaryDirectory[str] | None = None
    target_lib = fw_lib
    if not from_disk:
        extra_tmp = tempfile.TemporaryDirectory(
            prefix="motionpet_fw_fresh_mlp_",
            ignore_cleanup_errors=True,
        )
        tmp_p = Path(extra_tmp.name)
        fresh_hdr = tmp_p / "tinyml_model.h"
        export_model_to_cpp_header(
            estimator=mlp_bundle.estimator,
            class_names=mlp_bundle.class_names,
            output_path=fresh_hdr,
            preprocessing_config=mlp_bundle.preprocessing_config,
            experimental_status=mlp_bundle.experimental_status,
            model_name=mlp_bundle.model_name,
        )
        target_lib = _compile_firmware_bridge_dll(tmp_p, override_tinyml_header=fresh_hdr)

    try:
        target_lib.fw_gesture_init(
            stab_cfg.min_confidence,
            stab_cfg.min_consecutive_windows,
            stab_cfg.cooldown_ms,
            stab_cfg.require_neutral_reset,
        )

        cpp_id_to_name = {
            0: "NEUTRAL",
            1: "APPROACH",
            2: "RETREAT",
            3: "HOLD",
            4: "IMPULSE",
            5: "DOUBLE",
        }

        py_events: list[tuple[int, str, float, int]] = []
        cpp_events: list[tuple[int, str, float, int]] = []

        feats_buf = (ctypes.c_float * 11)()
        raw_cls = ctypes.c_int32()
        raw_conf = ctypes.c_float()
        rej_reason = ctypes.c_int32()
        emit_cls = ctypes.c_int32()
        emit_conf = ctypes.c_float()
        win_ms = ctypes.c_uint16()

        stream = _generate_continuous_gesture_stream()
        for idx, (ts_ms, dist_cm, valid_us, ir_det) in enumerate(stream):
            py_ev = py_clf.push_frame(
                SensorFramePayload(
                    distance_cm=dist_cm,
                    ir_detected=ir_det,
                    pot_norm=0.0,
                    valid_ultrasonic=valid_us,
                ),
                ts_ms=ts_ms,
            )

            cpp_emitted = target_lib.fw_gesture_step(
                float(dist_cm if (valid_us and dist_cm is not None) else -1.0),
                valid_us,
                ir_det,
                ts_ms,
                feats_buf,
                ctypes.byref(raw_cls),
                ctypes.byref(raw_conf),
                ctypes.byref(rej_reason),
                ctypes.byref(emit_cls),
                ctypes.byref(emit_conf),
                ctypes.byref(win_ms),
            )

            # Nas primeiras 9 amostras (W < 10), janela deve ser reportada como incompleta
            if idx < 9:
                assert py_ev is None
                assert not cpp_emitted
                assert rej_reason.value == 1  # GESTURE_REJ_WINDOW_INCOMPLETE
                continue

            # A partir da 10ª amostra, classe bruta e confiança devem coincidir entre Python e C++!
            diag = py_clf.get_diagnostics()
            assert cpp_id_to_name[raw_cls.value] == diag.last_class
            assert abs(raw_conf.value - float(py_clf._last_conf)) < 1e-3

            if py_ev is not None:
                py_events.append((ts_ms, py_ev.gesture.value, py_ev.confidence, py_ev.window_ms))
            if cpp_emitted:
                cpp_events.append(
                    (ts_ms, cpp_id_to_name[emit_cls.value], round(float(emit_conf.value), 4), int(win_ms.value))
                )

        assert len(py_events) >= 3, f"Esperava ao menos APPROACH, HOLD e RETREAT, obteve {py_events}"
        assert [e[1] for e in cpp_events] == [e[1] for e in py_events]
        assert [e[0] for e in cpp_events] == [e[0] for e in py_events]
        assert [e[3] for e in cpp_events] == [e[3] for e in py_events]
        for (_, _, py_c, _), (_, _, cpp_c, _) in zip(py_events, cpp_events):
            assert abs(py_c - cpp_c) < 1e-3
    finally:
        if not from_disk and target_lib is not fw_lib:
            _unload_shared_library(target_lib)
        if extra_tmp is not None:
            extra_tmp.cleanup()


def test_tinyml_header_is_drop_in_replaceable_without_breaking_contracts() -> None:
    """Exporta `decision_tree` para um `tinyml_model.h` substituto e recompila o firmware C++."""
    bundles, _ = _load_or_build_engineering_bundles()
    dt_bundle = bundles["decision_tree"]
    with tempfile.TemporaryDirectory(
        prefix="motionpet_fw_swap_dt_",
        ignore_cleanup_errors=True,
    ) as tmp_dir:
        tmp = Path(tmp_dir)
        alt_hdr = tmp / "tinyml_model.h"
        export_model_to_cpp_header(
            estimator=dt_bundle.estimator,
            class_names=dt_bundle.class_names,
            output_path=alt_hdr,
            preprocessing_config=dt_bundle.preprocessing_config,
            experimental_status=dt_bundle.experimental_status,
            model_name=dt_bundle.model_name,
        )
        alt_lib = _compile_firmware_bridge_dll(tmp, override_tinyml_header=alt_hdr)
        try:
            assert alt_lib.fw_gesture_model_name().decode("utf-8") == "decision_tree"
            assert alt_lib.fw_gesture_exp_status().decode("utf-8") == "AWAITING_REAL_DATA"
            alt_lib.fw_gesture_init(0.55, 2, 450, True)

            feats_buf = (ctypes.c_float * 11)()
            raw_cls = ctypes.c_int32()
            raw_conf = ctypes.c_float()
            rej = ctypes.c_int32()
            em_cls = ctypes.c_int32()
            em_conf = ctypes.c_float()
            win_ms = ctypes.c_uint16()

            emitted_names: list[str] = []
            id_map = {0: "NEUTRAL", 1: "APPROACH", 2: "RETREAT", 3: "HOLD", 4: "IMPULSE", 5: "DOUBLE"}
            for ts_ms, dist_cm, valid_us, ir_det in _generate_continuous_gesture_stream():
                if alt_lib.fw_gesture_step(
                    float(dist_cm if (valid_us and dist_cm is not None) else -1.0),
                    valid_us,
                    ir_det,
                    ts_ms,
                    feats_buf,
                    ctypes.byref(raw_cls),
                    ctypes.byref(raw_conf),
                    ctypes.byref(rej),
                    ctypes.byref(em_cls),
                    ctypes.byref(em_conf),
                    ctypes.byref(win_ms),
                ):
                    emitted_names.append(id_map[em_cls.value])

            assert len(emitted_names) >= 2
        finally:
            _unload_shared_library(alt_lib)


# ============================================================================
# 5. Paridade 1:1 do Motor do Pet: Python `PetEngine` vs C++ `pet_state.cpp`
# ============================================================================
def test_pet_engine_shared_sequence_parity_python_vs_cpp(fw_lib: ctypes.CDLL) -> None:
    """Executa 65 transições compartilhadas em Python e C++ comparando todos os 16 campos de estado."""
    codec = ProtocolCodec()
    py_engine = PetEngine(state=PetState(name="Bitinho", personality=PetPersonality.CURIOUS))
    fw_lib.fw_jsonl_reset()
    fw_lib.fw_pet_init(b"Bitinho", 0)

    def assert_states_match(context: str) -> None:
        py_s = py_engine.state
        cpp_s = _cpp_pet_snapshot_as_payload(fw_lib, codec)
        assert cpp_s.name == py_s.name, context
        assert cpp_s.hunger == pytest.approx(py_s.hunger, abs=0.02), context
        assert cpp_s.happiness == pytest.approx(py_s.happiness, abs=0.02), context
        assert cpp_s.energy == pytest.approx(py_s.energy, abs=0.02), context
        assert cpp_s.health == pytest.approx(py_s.health, abs=0.02), context
        assert cpp_s.xp == py_s.xp, context
        assert cpp_s.level == py_s.level, context
        assert cpp_s.stage == py_s.stage, context
        assert cpp_s.mood == py_s.mood, context
        assert cpp_s.personality == py_s.personality, context
        assert cpp_s.animation == py_s.animation, context
        assert cpp_s.animation_ttl_ticks == py_s.animation_ttl_ticks, context
        assert cpp_s.is_sleeping == py_s.is_sleeping, context
        assert cpp_s.age_ticks == py_s.age_ticks, context
        assert cpp_s.last_action == py_s.last_action, context
        assert cpp_s.care_counters == py_s.care_counters, context

    assert_states_match("initial")

    script: list[tuple[str, str, float]] = [
        ("CMD", "FEED", 0.0),
        ("CMD", "PLAY", 0.0),
        ("TICK", "", 0.0),
        ("TICK", "", 0.0),
        ("GEST", "HOLD", 0.88),
        ("GEST", "APPROACH", 0.40),  # confiança < 0.55 -> ignorado em ambos
        ("GEST", "APPROACH", 0.91),
        ("TICK", "", 0.0),
        ("GEST", "IMPULSE", 0.85),
        ("GEST", "DOUBLE", 0.79),
        ("CMD", "INTERACT", 0.0),
        ("GEST", "RETREAT", 0.92),  # entra em sono
        ("CMD", "PLAY", 0.0),       # bloqueado durante sono ("ZZZ_LOCKED")
    ]
    # Avança 12 ticks dormindo (testa recuperação de energia e despertar automático em 100%)
    script.extend([("TICK", "", 0.0)] * 12)
    # Evolui até CHICK e CYBER_ROOSTER acumulando XP e exercitando contadores de personalidade
    for _ in range(10):
        script.extend([
            ("CMD", "FEED", 0.0),
            ("CMD", "PLAY", 0.0),
            ("CMD", "INTERACT", 0.0),
            ("TICK", "", 0.0),
        ])
    script.extend([
        ("CMD", "HEAL", 0.0),
        ("TICK", "", 0.0),
        ("CMD", "RESET", 0.0),
    ])

    for step_i, (op, arg, conf) in enumerate(script):
        if op == "TICK":
            py_engine.tick()
            fw_lib.fw_pet_tick()
        elif op == "CMD":
            py_engine.apply_command(CommandType(arg))
            fw_lib.fw_pet_command(arg.encode("utf-8"))
        elif op == "GEST":
            ev = GestureEventPayload(
                gesture=GestureType(arg),
                confidence=conf,
                source=GestureSource.TINYML,
                window_ms=630,
            )
            py_engine.apply_gesture(ev)
            fw_lib.fw_pet_gesture_event(arg.encode("utf-8"), conf, 0.55)
        assert_states_match(f"step_{step_i}_{op}_{arg}")


# ============================================================================
# 6. Persistência NVS Antidesgaste + Recuperação de Corrupção (`pet_persistence.cpp`)
# ============================================================================
def test_nvs_persistence_roundtrip_wear_protection_and_corruption_recovery(fw_lib: ctypes.CDLL) -> None:
    codec = ProtocolCodec()
    fw_lib.fw_jsonl_reset()
    fw_lib.fw_nvs_reset(30_000)

    # Sem estado salvo -> PET_NVS_ERR_NOT_FOUND (1)
    fw_lib.fw_pet_init(b"Bitinho", 0)
    assert fw_lib.fw_nvs_load_into_current_pet() == 1

    # Evolui um pouco o pet e grava manualmente (`force_manual=True`) -> PET_NVS_OK (0)
    fw_lib.fw_pet_command(b"FEED")
    fw_lib.fw_pet_command(b"PLAY")
    fw_lib.fw_pet_tick()
    saved_expected = _cpp_pet_snapshot_as_payload(fw_lib, codec)

    assert fw_lib.fw_nvs_save_current_pet(1_000, True) == 0

    writes = ctypes.c_uint32()
    skipped = ctypes.c_uint32()
    throttled = ctypes.c_uint32()
    corrupt_rec = ctypes.c_uint32()
    blob_sz = ctypes.c_uint32()
    fw_lib.fw_nvs_stats(
        ctypes.byref(writes),
        ctypes.byref(skipped),
        ctypes.byref(throttled),
        ctypes.byref(corrupt_rec),
        ctypes.byref(blob_sz),
    )
    assert writes.value == 1
    assert blob_sz.value > 64

    # Proteção Flash 1: tentar salvar estado idêntico -> PET_NVS_ERR_UNCHANGED (5), zero escritas novas
    assert fw_lib.fw_nvs_save_current_pet(2_000, True) == 5
    fw_lib.fw_nvs_stats(
        ctypes.byref(writes),
        ctypes.byref(skipped),
        ctypes.byref(throttled),
        ctypes.byref(corrupt_rec),
        ctypes.byref(blob_sz),
    )
    assert writes.value == 1
    assert skipped.value == 1

    # Proteção Flash 2: auto-save (`force_manual=False`) antes de 30 s -> PET_NVS_ERR_THROTTLED (4)
    fw_lib.fw_pet_tick()
    assert fw_lib.fw_nvs_save_current_pet(15_000, False) == 4
    # Após 31 s (>= 30_000 ms), auto-save grava normalmente -> PET_NVS_OK (0)
    assert fw_lib.fw_nvs_save_current_pet(32_000, False) == 0
    saved_expected = _cpp_pet_snapshot_as_payload(fw_lib, codec)

    # Reinicia o pet em memória e restaura da NVS -> roundtrip 100% fiel
    fw_lib.fw_pet_init(b"Outro", 2)
    assert fw_lib.fw_nvs_load_into_current_pet() == 0
    restored = _cpp_pet_snapshot_as_payload(fw_lib, codec)
    assert restored == saved_expected

    # Injeção de corrupção binária no payload salvo -> CRC32 detecta e recupera com segurança!
    fw_lib.fw_nvs_corrupt_byte(20, 0x5A)
    fw_lib.fw_pet_init(b"SafeFallback", 0)
    assert fw_lib.fw_nvs_load_into_current_pet() == 2  # PET_NVS_ERR_CORRUPT_CRC
    fallback_after = _cpp_pet_snapshot_as_payload(fw_lib, codec)
    assert fallback_after.name == "SafeFallback"

    fw_lib.fw_nvs_stats(
        ctypes.byref(writes),
        ctypes.byref(skipped),
        ctypes.byref(throttled),
        ctypes.byref(corrupt_rec),
        ctypes.byref(blob_sz),
    )
    assert writes.value == 2
    assert throttled.value == 1
    assert corrupt_rec.value == 1


# ============================================================================
# 7. Equivalência 20x4 do LCD + Barramento 4 bits HD44780 (`lcd2004_driver.cpp`)
# ============================================================================
def test_lcd2004_character_parity_python_vs_cpp_and_4bit_hd44780_bus(fw_lib: ctypes.CDLL) -> None:
    codec = ProtocolCodec()
    py_renderer = Lcd20x4Renderer()
    py_engine = PetEngine(state=PetState(name="Bitinho", personality=PetPersonality.CURIOUS))
    fw_lib.fw_jsonl_reset()
    fw_lib.fw_pet_init(b"Bitinho", 0)

    buf = ctypes.create_string_buffer(512)

    # Verifica equivalência caractere-por-caractere nas 4 linhas x 20 colunas em múltiplos estados e paridades
    scenarios: list[tuple[CommandType | None, int, float | None, bool]] = [
        (None, 0, None, False),
        (None, 1, 18.4, True),
        (CommandType.FEED, 0, 12.1, True),
        (CommandType.FEED, 1, 12.1, True),
        (CommandType.PLAY, 0, 29.7, True),
        (CommandType.INTERACT, 1, None, False),
        (CommandType.REST, 0, 55.0, True),
        (CommandType.HEAL, 1, 8.9, True),
    ]
    for cmd, frame_idx, dist, valid in scenarios:
        if cmd is not None:
            py_engine.apply_command(cmd)
            fw_lib.fw_pet_command(cmd.value.encode("utf-8"))
        else:
            py_engine.tick()
            fw_lib.fw_pet_tick()

        sensor_py = (
            SensorFramePayload(distance_cm=dist, ir_detected=False, pot_norm=0.0, valid_ultrasonic=valid)
            if dist is not None
            else None
        )
        py_lcd = py_renderer.render(py_engine.state, frame_idx=frame_idx, sensor=sensor_py)

        assert fw_lib.fw_pet_to_lcd_jsonl(
            1000,
            frame_idx,
            dist is not None,
            float(dist if dist is not None else -1.0),
            valid,
            buf,
            512,
        )
        env = codec.decode(buf.value.decode("utf-8"))
        cpp_lcd = LcdFramePayload.from_dict(env.data)
        assert cpp_lcd.lines == py_lcd.lines

    # Verifica protocolo elétrico de 4 bits do HD44780 e atualização diferencial (dirty shadow buffer)
    assert fw_lib.fw_lcd_hw_init_and_glyphs()

    rs_arr = (ctypes.c_uint8 * 512)()
    nib_arr = (ctypes.c_uint8 * 512)()
    n_nibbles = fw_lib.fw_lcd_hw_get_nibble_log(rs_arr, nib_arr, 512)

    # Os 4 primeiros nibbles de init com RS=0 seguem o handshake padrão HD44780: 0x03, 0x03, 0x03, 0x02
    assert n_nibbles >= 140  # init + 8 glifos CGRAM (8 * (1 cmd + 8 bytes dados) * 2 nibbles)
    assert [nib_arr[i] for i in range(4)] == [0x03, 0x03, 0x03, 0x02]
    assert all(rs_arr[i] == 0 for i in range(4))

    # Reconstrói os bytes enviados após os 4 nibbles iniciais de sincronismo
    cmd_bytes: list[int] = []
    data_bytes: list[int] = []
    for i in range(4, n_nibbles - 1, 2):
        byte_val = ((int(nib_arr[i]) & 0x0F) << 4) | (int(nib_arr[i + 1]) & 0x0F)
        if rs_arr[i] == 0:
            cmd_bytes.append(byte_val)
        else:
            data_bytes.append(byte_val)

    # Comandos obrigatórios HD44780: 0x28 (4-bit, 2 linhas), 0x0C (display ON), 0x06 (entry mode), 0x01 (clear)
    for expected_cmd in (0x28, 0x0C, 0x06, 0x01, 0x40):  # 0x40 = CGRAM glyph 0
        assert expected_cmd in cmd_bytes
    assert len(data_bytes) >= 64  # 8 glifos CGRAM * 8 linhas = 64 bytes gravados

    # Renderização 1: quadro inicial escreve os caracteres modificados em relação ao display limpo
    chars_written = ctypes.c_uint32()
    bus_bytes_1 = ctypes.c_uint32()
    fw_lib.fw_lcd_hw_render_pet(0, True, 20.0, True, ctypes.byref(chars_written), ctypes.byref(bus_bytes_1))
    assert 1 <= chars_written.value <= 80

    # Renderização 2 com quadro IDÊNTICO -> shadow buffer suprime 100% das escritas no barramento!
    bus_bytes_2 = ctypes.c_uint32()
    fw_lib.fw_lcd_hw_render_pet(0, True, 20.0, True, ctypes.byref(chars_written), ctypes.byref(bus_bytes_2))
    assert chars_written.value == 0
    assert bus_bytes_2.value == bus_bytes_1.value

    # Renderização 3 mudando apenas a distância `020cm` -> `025cm` -> escreve apenas 1 caractere sujo!
    bus_bytes_3 = ctypes.c_uint32()
    fw_lib.fw_lcd_hw_render_pet(0, True, 25.0, True, ctypes.byref(chars_written), ctypes.byref(bus_bytes_3))
    assert chars_written.value == 1
    assert bus_bytes_3.value > bus_bytes_2.value


# ============================================================================
# 8. Auditoria Estática de Tempo Real, Segurança Elétrica e Compilador Xtensa ESP32
# ============================================================================
def test_firmware_zero_heap_safety_status_and_xtensa_cross_compile() -> None:
    rt_files = [
        FIRMWARE_DIR / "common" / "fw_utils.h",
        FIRMWARE_DIR / "sensors" / "sensors_driver.cpp",
        FIRMWARE_DIR / "communication" / "jsonl_protocol.cpp",
        FIRMWARE_DIR / "gestures" / "gesture_classifier.cpp",
        FIRMWARE_DIR / "gestures" / "tinyml_model.h",
        FIRMWARE_DIR / "pet" / "pet_state.cpp",
        FIRMWARE_DIR / "pet" / "pet_persistence.cpp",
        FIRMWARE_DIR / "display" / "lcd2004_driver.cpp",
        FIRMWARE_DIR / "main" / "main.cpp",
    ]
    for path in rt_files:
        assert path.is_file(), f"Arquivo ausente: {path}"
        assert verify_zero_dynamic_allocation(path), f"Alocação dinâmica proibida detectada em {path}"

    pinout_hdr = (FIRMWARE_DIR / "main" / "pinout_config.h").read_text(encoding="utf-8")
    assert 'MOTIONPET_PINOUT_STATUS "PROPOSED_PENDING_BENCH_INSPECTION"' in pinout_hdr

    # Verifica compilação cruzada real com `xtensa-esp32-elf-g++` nos módulos independentes de Arduino
    xtensa_gpp = detect_esp32_xtensa_compiler()
    if xtensa_gpp is not None:
        with tempfile.TemporaryDirectory(
            prefix="motionpet_xtensa_fw_",
            ignore_cleanup_errors=True,
        ) as tmp_dir:
            tmp = Path(tmp_dir)
            for rel in (
                "sensors/sensors_driver.cpp",
                "communication/jsonl_protocol.cpp",
                "gestures/gesture_classifier.cpp",
                "pet/pet_state.cpp",
                "pet/pet_persistence.cpp",
                "display/lcd2004_driver.cpp",
            ):
                src = FIRMWARE_DIR / rel
                obj = tmp / (Path(rel).stem + ".o")
                res = subprocess.run(
                    [
                        xtensa_gpp,
                        "-std=gnu++17",
                        "-O2",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-mlongcalls",
                        f"-I{FIRMWARE_DIR}",
                        "-c",
                        str(src),
                        "-o",
                        str(obj),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert res.returncode == 0, (
                    f"Falha Xtensa ESP32 (-Werror) em {rel}:\n{res.stdout}\n{res.stderr}"
                )
