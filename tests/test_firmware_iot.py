"""Núcleo C++ real em DLL de host + falhas injetadas; nenhum acesso à ESP32/COM3."""
from __future__ import annotations

import ctypes
import json
import tempfile
from pathlib import Path

import pytest

from ml.export.parity import _unload_shared_library
from tests import test_firmware_cycle3 as bridge


CPP_BRIDGE = r'''
#include "communication/iot_core.cpp"
static IotSampleQueue test_queue;
static IotConnection test_connection;
FW_EXPORT void iot_test_reset(int configured) {
    iot_queue_init(&test_queue); iot_connection_init(&test_connection, configured != 0);
}
FW_EXPORT int iot_test_push(uint64_t ts, float distance, int valid, int ir) {
    SensorRawFrame frame{}; frame.timestamp_ms = (uint32_t)ts;
    frame.distance_cm = distance; frame.valid_ultrasonic = valid != 0; frame.ir_detected = ir != 0;
    return iot_queue_push(&test_queue, &frame, ts);
}
FW_EXPORT void iot_test_push_ir_disabled(uint64_t ts) {
    SensorRawFrame frame{}; frame.distance_cm = 20; frame.valid_ultrasonic = true;
    iot_queue_push(&test_queue, &frame, ts, false);
}
FW_EXPORT unsigned iot_test_sensor_timestamp(uint64_t clock_us, unsigned previous_ms) {
    fw_sensor_init(true, false, true, false);
    g_mock_clock_us = clock_us;
    g_test_sensor_ctx.last_timestamp_ms = previous_ms;
    SensorRawFrame frame{};
    sensors_driver_read(&g_test_sensor_ctx, &frame);
    return frame.timestamp_ms;
}
FW_EXPORT int iot_test_peek(char *output, unsigned capacity) {
    IotSample sample{};
    return iot_queue_peek(&test_queue, &sample) &&
        iot_serialize_sample(&sample, "esp32_112233aabbcc", "boot_001122", output, capacity);
}
FW_EXPORT void iot_test_ack() { iot_queue_ack(&test_queue); }
FW_EXPORT unsigned iot_test_used() { return test_queue.used; }
FW_EXPORT uint64_t iot_test_dropped() { return test_queue.dropped_total; }
FW_EXPORT uint64_t iot_test_next() { return test_queue.next_sequence; }
FW_EXPORT unsigned iot_test_size() { return sizeof(test_queue); }
FW_EXPORT int iot_test_step(uint64_t now, int wifi, int broker, int failed, int mid, int clock) {
    int action = iot_connection_step(&test_connection, now, wifi != 0, broker != 0,
        failed != 0, mid, test_queue.used != 0, clock != 0);
    if (action == IOT_ACK_SAMPLE) iot_queue_ack(&test_queue);
    return action;
}
FW_EXPORT void iot_test_published(uint64_t now, int mid) { iot_connection_published(&test_connection, now, mid); }
FW_EXPORT unsigned iot_test_state() { return test_connection.state; }
FW_EXPORT unsigned iot_test_backoff() { return test_connection.broker_backoff_ms; }
FW_EXPORT unsigned iot_test_poll_delay() { return iot_connection_poll_delay_ms(test_connection.state); }
FW_EXPORT uint64_t iot_test_deadline() { return test_connection.deadline_ms; }
FW_EXPORT uint64_t iot_test_extend(unsigned raw, uint64_t now) { return iot_extend_timestamp_ms(raw, now); }
'''


@pytest.fixture(scope="module")
def iot_lib():
    original = bridge._build_firmware_bridge_cpp
    with tempfile.TemporaryDirectory(prefix="motionlab_iot_host_", ignore_cleanup_errors=True) as folder:
        try:
            bridge._build_firmware_bridge_cpp = lambda: original() + CPP_BRIDGE
            lib = bridge._compile_firmware_bridge_dll(Path(folder))
        finally:
            bridge._build_firmware_bridge_cpp = original
        signatures = {
            "reset": ([ctypes.c_int], None),
            "push": ([ctypes.c_uint64, ctypes.c_float, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "peek": ([ctypes.c_char_p, ctypes.c_uint], ctypes.c_int),
            "ack": ([], None), "used": ([], ctypes.c_uint),
            "dropped": ([], ctypes.c_uint64), "next": ([], ctypes.c_uint64),
            "size": ([], ctypes.c_uint), "state": ([], ctypes.c_uint),
            "step": ([ctypes.c_uint64] + [ctypes.c_int] * 5, ctypes.c_int),
            "published": ([ctypes.c_uint64, ctypes.c_int], None),
            "backoff": ([], ctypes.c_uint), "deadline": ([], ctypes.c_uint64),
            "poll_delay": ([], ctypes.c_uint),
            "extend": ([ctypes.c_uint, ctypes.c_uint64], ctypes.c_uint64),
            "push_ir_disabled": ([ctypes.c_uint64], None),
            "sensor_timestamp": ([ctypes.c_uint64, ctypes.c_uint], ctypes.c_uint),
        }
        for name, (args, result) in signatures.items():
            func = getattr(lib, "iot_test_" + name)
            func.argtypes, func.restype = args, result
        try:
            yield lib
        finally:
            _unload_shared_library(lib)


def peek(lib):
    buffer = ctypes.create_string_buffer(1024)
    assert lib.iot_test_peek(buffer, len(buffer))
    return json.loads(buffer.value)


def online(lib, now=0):
    lib.iot_test_reset(1)
    assert lib.iot_test_step(now, 0, 0, 0, -1, 1) == 1
    assert lib.iot_test_step(now + 1, 1, 0, 0, -1, 1) == 2
    assert lib.iot_test_step(now + 2, 1, 1, 0, -1, 1) == 0
    assert lib.iot_test_state() == 6


def test_disabled_transport_and_offline_acquisition_are_independent(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(0)
    assert lib.iot_test_step(10**12, 0, 0, 1, -1, 0) == 0
    assert lib.iot_test_state() == 0
    # Adapter avoids enqueue entirely when disabled; portable queue itself has no I/O.
    assert lib.iot_test_push(123, 12, 1, 1)
    assert peek(lib)["ts_ms"] == 123


def test_cpp_payload_contract_and_usb_same_sensor_values(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    assert lib.iot_test_push(123456, 37.25, 1, 1)
    mqtt = peek(lib)
    assert mqtt == {
        "schema_version": 1, "kind": "sample", "device_id": "esp32_112233aabbcc",
        "session_id": "boot_001122", "sample_idx": 0, "ts_ms": 123456,
        "data_origin": "real_hardware", "distance_cm": 37.25, "valid_ultrasonic": True,
        "ir_detected": True, "valid_ir": True, "captured_at_iso": None, "clock_source": "monotonic_boot",
        "physical_validation": "pending", "dropped_total": 0,
    }
    lib.fw_jsonl_reset()
    output = ctypes.create_string_buffer(1024)
    assert lib.fw_jsonl_make_sensor_frame(123456, 37.25, True, True, 0, output, len(output))
    usb = json.loads(output.value)
    assert usb["v"] == 1 and usb["type"] == "sensor_frame"
    assert usb["ts_ms"] == mqtt["ts_ms"]
    for field in ("distance_cm", "valid_ultrasonic", "ir_detected"):
        assert usb["data"][field] == mqtt[field]
    small = ctypes.create_string_buffer(80)
    assert not lib.iot_test_peek(small, len(small))


@pytest.mark.parametrize("distance,valid", [(float("nan"), 1), (float("inf"), 1), (-1, 0), (1.99, 1), (400.01, 1), (20, 0)])
def test_invalid_ultrasonic_is_finite_minus_one(iot_lib, distance, valid):
    lib = iot_lib
    lib.iot_test_reset(1)
    assert lib.iot_test_push(10, distance, valid, 0)
    sample = peek(lib)
    assert sample["distance_cm"] == -1 and sample["valid_ultrasonic"] is False


def test_bounded_queue_drop_new_sequence_gaps_and_immutable_retry(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    size = lib.iot_test_size()
    for index in range(10000):
        assert bool(lib.iot_test_push(index * 70, 10, 1, 0)) == (index < 32)
    assert lib.iot_test_used() == 32
    assert lib.iot_test_dropped() == 9968
    assert lib.iot_test_next() == 10000 and lib.iot_test_size() == size
    assert size <= 2048
    first = peek(lib)
    assert first["sample_idx"] == 0 and first["dropped_total"] == 0
    for _ in range(32):
        lib.iot_test_ack()
    assert lib.iot_test_used() == 0
    assert lib.iot_test_push(700000, 10, 1, 0)
    following = peek(lib)
    assert following["sample_idx"] == 10000 and following["dropped_total"] == 9968


def test_disabled_ir_is_explicitly_invalid_and_differs_from_no_detection(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    lib.iot_test_push_ir_disabled(10)
    assert peek(lib)["valid_ir"] is False and peek(lib)["ir_detected"] is False
    lib.iot_test_ack()
    assert lib.iot_test_push(80, 20, 1, 0)
    assert peek(lib)["valid_ir"] is True and peek(lib)["ir_detected"] is False


def test_wifi_connection_timeout_and_bounded_backoff(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    assert lib.iot_test_step(0, 0, 0, 0, -1, 1) == 1
    assert lib.iot_test_step(9999, 0, 0, 0, -1, 1) == 0
    assert lib.iot_test_step(10000, 0, 0, 0, -1, 1) == 0
    assert lib.iot_test_deadline() == 11000
    assert lib.iot_test_step(10999, 0, 0, 0, -1, 1) == 0
    assert lib.iot_test_step(11000, 0, 0, 0, -1, 1) == 1


def test_broker_refusal_backoff_is_capped_and_recovers(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    now = 0
    assert lib.iot_test_step(now, 1, 0, 0, -1, 1) == 2
    delays = []
    for _ in range(10):
        now += 1
        assert lib.iot_test_step(now, 1, 0, 1, -1, 1) == 3
        deadline = lib.iot_test_deadline()
        delays.append(deadline - now)
        assert lib.iot_test_step(deadline - 1, 1, 0, 0, -1, 1) == 0
        assert lib.iot_test_step(deadline, 1, 0, 0, -1, 1) == 2
        now = deadline
    assert delays[:3] == [1000, 2000, 4000] and max(delays) == 60000
    assert lib.iot_test_step(now + 1, 1, 1, 0, -1, 1) == 0
    assert lib.iot_test_state() == 6


def test_tls_waits_for_clock_and_wifi_failure_still_reconnects(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    assert lib.iot_test_step(1, 1, 0, 0, -1, 0) == 0
    assert lib.iot_test_state() == 3
    assert lib.iot_test_step(10**8, 1, 0, 0, -1, 0) == 0
    assert lib.iot_test_step(10**8 + 1, 0, 0, 0, -1, 0) == 3
    assert lib.iot_test_step(10**8 + 1001, 0, 0, 0, -1, 0) == 1
    assert lib.iot_test_step(10**8 + 1002, 1, 0, 0, -1, 1) == 2


def test_clock_loss_resets_existing_client_before_clock_wait(iot_lib):
    lib = iot_lib
    online(lib)
    assert lib.iot_test_push(10, 30, 1, 0)
    assert lib.iot_test_step(10, 1, 1, 0, -1, 1) == 4
    lib.iot_test_published(10, 9)
    assert lib.iot_test_step(11, 1, 1, 0, -1, 0) == 3
    assert lib.iot_test_state() == 3 and lib.iot_test_used() == 1
    assert lib.iot_test_step(12, 1, 0, 0, -1, 0) == 0
    assert lib.iot_test_step(13, 1, 0, 0, -1, 1) == 2


def test_qos1_one_inflight_puback_and_duplicate_ack(iot_lib):
    lib = iot_lib
    online(lib)
    assert lib.iot_test_push(10, 20, 1, 0)
    assert lib.iot_test_push(80, 21, 1, 1)
    original = peek(lib)
    assert lib.iot_test_step(10, 1, 1, 0, -1, 1) == 4
    lib.iot_test_published(10, 7)
    assert lib.iot_test_step(11, 1, 1, 0, -1, 1) == 0
    assert lib.iot_test_used() == 2 and peek(lib) == original
    assert lib.iot_test_step(12, 1, 1, 0, 6, 1) == 0
    assert lib.iot_test_step(13, 1, 1, 0, 7, 1) == 5
    assert lib.iot_test_used() == 1
    assert lib.iot_test_step(14, 1, 1, 0, 7, 1) == 4
    assert lib.iot_test_used() == 1  # duplicate PUBACK never removes next sample


def test_online_polling_preserves_single_inflight_and_bounds_loss(iot_lib):
    lib = iot_lib
    lib.iot_test_reset(1)
    assert lib.iot_test_poll_delay() == 20
    online(lib)
    assert lib.iot_test_poll_delay() == 1

    def simulate(ack_latency_ms):
        online(lib)
        outstanding = None
        next_mid = 1
        published = []
        acknowledged = []
        for now in range(3, 14004, lib.iot_test_poll_delay()):
            if (now - 3) % 70 == 0:
                lib.iot_test_push(now, 20, 1, 0)
            ack = outstanding[0] if outstanding and now == outstanding[1] else -1
            action = lib.iot_test_step(now, 1, 1, 0, ack, 1)
            if action == 4:
                assert outstanding is None  # no second publication before matching PUBACK
                published.append(peek(lib)["sample_idx"])
                lib.iot_test_published(now, next_mid)
                outstanding = (next_mid, now + ack_latency_ms)
                next_mid += 1
            elif action == 5:
                assert outstanding is not None and ack == outstanding[0]
                acknowledged.append(published[-1])
                outstanding = None
        assert acknowledged == sorted(set(acknowledged))
        return lib.iot_test_dropped()

    assert simulate(40) == 0  # one millisecond polling can keep up in this model
    assert simulate(100) > 0  # a slower broker can still fill the finite queue


@pytest.mark.parametrize("failure", ["wifi", "broker", "timeout", "publish"])
def test_transport_failure_preserves_sample_until_retry_ack(iot_lib, failure):
    lib = iot_lib
    online(lib)
    assert lib.iot_test_push(123, 30, 1, 1)
    sample = peek(lib)
    assert lib.iot_test_step(10, 1, 1, 0, -1, 1) == 4
    lib.iot_test_published(10, -1 if failure == "publish" else 99)
    now = 10010 if failure == "timeout" else 11
    assert lib.iot_test_step(now, failure != "wifi", failure != "broker", failure == "publish", -1, 1) == 3
    assert peek(lib) == sample and lib.iot_test_used() == 1
    deadline = lib.iot_test_deadline()
    assert lib.iot_test_step(deadline, 1, 0, 0, -1, 1) == 2
    assert lib.iot_test_step(deadline + 1, 1, 1, 0, -1, 1) == 4
    lib.iot_test_published(deadline + 1, 2)
    assert lib.iot_test_step(deadline + 2, 1, 1, 0, 2, 1) == 5
    assert lib.iot_test_used() == 0


def test_monotonic_acquisition_timestamp_extends_32bit_rollover(iot_lib):
    lib = iot_lib
    assert lib.iot_test_extend(0xFFFFFFF0, 0x100000010) == 0xFFFFFFF0
    assert lib.iot_test_extend(0x20, 0x100000030) == 0x100000020
    assert lib.iot_test_extend(0xFFFFFFFF, 0x200000010) == 0x1FFFFFFFF
    lib.iot_test_reset(1)
    assert lib.iot_test_push(2**40 + 123, 20, 1, 0)
    assert peek(lib)["ts_ms"] == 2**40 + 123
    assert lib.iot_test_sensor_timestamp(0x100000020 * 1000, 0xFFFFFFF0) == 0x20
    assert lib.iot_test_sensor_timestamp(12345 * 1000, 12345) == 12346


def test_iot_diag_uses_existing_usb_ack_command_kind(iot_lib):
    from tests.test_firmware_strict_parser import _parse
    ok, parsed = _parse(iot_lib, "IOT_DIAG")
    assert ok and parsed.kind.value == 7 and parsed.pbool.value == 1
    ok, parsed = _parse(iot_lib, '{"v":1,"seq":9,"ts_ms":1,"type":"pet_command","data":{"command":"IOT_DIAG"}}')
    assert ok and parsed.kind.value == 7 and parsed.pbool.value == 1 and parsed.seq.value == 9


