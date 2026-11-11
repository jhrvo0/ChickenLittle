"""Executa o HAL PCF8574 real com Wire simulado no host, sem a placa conectada."""
import ctypes
import os
from pathlib import Path
import subprocess

import pytest

from ml.export.parity import detect_native_cpp_compiler, _unload_shared_library


@pytest.fixture(scope="module")
def hal(tmp_path_factory):
    compiler = detect_native_cpp_compiler()
    if compiler is None:
        pytest.skip("Compilador C++ nativo indisponivel")
    work = tmp_path_factory.mktemp("i2c_hal")
    (work / "Arduino.h").write_text("#include <stdint.h>\ninline void delay(uint32_t) {}\ninline void delayMicroseconds(uint32_t) {}\n")
    (work / "Wire.h").write_text(r'''
#include <stdint.h>
struct FakeWire {
    int sda, scl, target, address, writes, wrong_address, bad_rw_bl;
    uint32_t hz;
    bool begin(int a, int b, uint32_t c) { sda=a; scl=b; hz=c; return true; }
    void beginTransmission(uint8_t a) { address=a; }
    void write(uint8_t b) { ++writes; if (address != target) ++wrong_address;
                          if ((b & 0x02U) || !(b & 0x08U)) ++bad_rw_bl; }
    uint8_t endTransmission() { return address == target ? 0 : 2; }
};
static FakeWire Wire;
''')
    src = work / "probe.cpp"
    src.write_text(r'''
#define ARDUINO 1
#include "display/lcd2004_i2c_hal.cpp"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
extern "C" EXPORT int probe(int address) {
    Wire.target=address; Wire.writes=0; Wire.wrong_address=0; Wire.bad_rw_bl=0;
    LCDPinConfig cfg;
    lcd_i2c_fill_pin_config(&cfg);
    g_lcd_i2c_hal_ops.configure_pins(&cfg);
    g_lcd_i2c_hal_ops.write_pin(cfg.pin_rs, 1);
    g_lcd_i2c_hal_ops.write_pin(cfg.pin_d4, 1);
    g_lcd_i2c_hal_ops.write_pin(cfg.pin_en, 1);
    g_lcd_i2c_hal_ops.write_pin(cfg.pin_en, 0);
    return (Wire.sda != 21 || Wire.scl != 22 || Wire.hz != 100000 ? 1 : 0)
         | (Wire.writes < 4 ? 2 : 0) | (Wire.wrong_address ? 4 : 0)
         | (Wire.bad_rw_bl ? 8 : 0);
}
''')
    kind, tool = compiler
    fw = Path(__file__).resolve().parents[1] / "firmware"
    lib_path = work / ("probe.dll" if os.name == "nt" else "probe.so")
    env = os.environ.copy()
    if kind == "msvc_freestanding_dll":
        cl = Path(tool)
        host_folder = cl.parent.parent
        native_bin = host_folder / host_folder.name.replace("Host", "").lower()
        env["PATH"] = os.pathsep.join([str(cl.parent), str(native_bin), env.get("PATH", "")])
        inc = host_folder.parent.parent / "include"
        command = [tool, "/nologo", "/std:c++17", "/O2", "/W3", "/GS-", "/Zl", "/EHs-c-", "/GR-", "/LD",
                   f"/I{inc}", f"/I{work}", f"/I{fw}", str(src), f"/Fe:{lib_path}", "/link", "/NOENTRY", "/NODEFAULTLIB"]
    else:
        command = [tool, "-std=c++17", "-O2", "-Wall", "-shared", "-fPIC", f"-I{work}", f"-I{fw}", str(src), "-o", str(lib_path)]
    result = subprocess.run(command, cwd=work, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    lib = ctypes.CDLL(str(lib_path))
    lib.probe.argtypes = [ctypes.c_int]
    lib.probe.restype = ctypes.c_int
    yield lib
    _unload_shared_library(lib)


@pytest.mark.parametrize("address", [0x27, 0x3F, 0x20, 0x3A])
def test_pcf_addresses_use_canonical_pins_and_keep_rw_low_backlight_on(hal, address):
    assert hal.probe(address) == 0
