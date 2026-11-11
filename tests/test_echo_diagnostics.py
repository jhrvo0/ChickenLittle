"""Serialização real C++ dos tempos de diagnóstico do ultrassom."""

import ctypes

import pytest

from ml.export.parity import _unload_shared_library
from terminal.communication.protocol import MessageType, ProtocolCodec, SensorFramePayload
from tests import test_firmware_cycle3 as firmware_tests


@pytest.fixture(scope="module")
def diagnostics_lib(tmp_path_factory):
    original = firmware_tests._build_firmware_bridge_cpp
    extra = r"""
FW_EXPORT bool fw_test_echo_frame(uint32_t echo_us, uint32_t acquire_us,
                                  bool valid, char *out, uint32_t cap) {
    SensorRawFrame frame{};
    frame.distance_cm = valid ? 30.0f : -1.0f;
    frame.valid_ultrasonic = valid;
    frame.echo_duration_us = echo_us;
    frame.acquire_duration_us = acquire_us;
    return jsonl_serialize_sensor_frame(&g_test_jsonl, out, cap, 1000, &frame);
}
"""
    firmware_tests._build_firmware_bridge_cpp = lambda: original() + extra
    try:
        lib = firmware_tests._compile_firmware_bridge_dll(tmp_path_factory.mktemp("echo_diagnostics"))
    finally:
        firmware_tests._build_firmware_bridge_cpp = original
    lib.fw_test_echo_frame.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool,
                                      ctypes.c_char_p, ctypes.c_uint32]
    lib.fw_test_echo_frame.restype = ctypes.c_bool
    try:
        yield lib
    finally:
        _unload_shared_library(lib)


@pytest.mark.parametrize("echo_us,acquire_us,valid", [(1749, 1900, True), (0, 25000, False), (50, 200, False)])
def test_echo_diagnostics_serialized_without_changing_python_payload(diagnostics_lib, echo_us, acquire_us, valid):
    out = ctypes.create_string_buffer(512)
    assert diagnostics_lib.fw_test_echo_frame(echo_us, acquire_us, valid, out, len(out))
    env = ProtocolCodec().decode(out.value.decode("utf-8"))
    assert env.type == MessageType.SENSOR_FRAME
    assert env.data["echo_duration_us"] == echo_us
    assert env.data["acquire_duration_us"] == acquire_us
    frame = SensorFramePayload.from_dict(env.data)
    assert frame.valid_ultrasonic is valid
    assert frame.distance_cm == (30.0 if valid else None)


def test_legacy_sensor_frame_without_diagnostics_remains_valid():
    frame = SensorFramePayload.from_dict({"distance_cm": None, "ir_detected": False,
                                         "pot_norm": 0.0, "valid_ultrasonic": False})
    assert frame.distance_cm is None and frame.valid_ultrasonic is False
