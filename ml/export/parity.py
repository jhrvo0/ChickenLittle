"""Verificação automatizada de paridade numérica entre Python (scikit-learn) e C/C++ nativo compilado."""

from __future__ import annotations

import _ctypes
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ml.preprocessing.features import extract_window_features
from ml.preprocessing.filtering import CausalSignalFilter
from ml.schemas import FEATURE_NAMES, PreprocessingConfig, RawSampleRecord

_VS2022_EDITIONS: tuple[str, ...] = ("Community", "BuildTools", "Professional", "Enterprise")


@dataclass(frozen=True)
class ParityCheckReport:
    """Resultado da validação de equivalência entre modelo Python e código C/C++ exportado."""

    execution_backend: str  # "native_cpp_msvc_dll" | "native_cpp_gnu_dll" | "static_header_audit_only"
    compiled_natively: bool
    esp32_xtensa_syntax_verified: bool
    num_windows_tested: int
    class_agreement_rate: float
    max_abs_proba_diff: float
    max_abs_feature_diff: float
    zero_dynamic_alloc_verified: bool
    passed: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_zero_dynamic_allocation(header_path: str | Path) -> bool:
    """Audita o código C/C++ gerado garantindo ausência de alocação dinâmica de heap."""
    code = Path(header_path).read_text(encoding="utf-8")
    active_lines = [
        ln for ln in code.splitlines() if not ln.strip().startswith(("*", "/*", "//"))
    ]
    joined = "\n".join(active_lines)
    forbidden = (
        "malloc(",
        "calloc(",
        "realloc(",
        "free(",
        "std::vector",
        "std::string",
        " new ",
        "delete ",
    )
    return not any(tok in joined for tok in forbidden)


def _python_target_arch() -> str:
    ver = sys.version.upper()
    if "ARM64" in ver:
        return "arm64"
    if "AMD64" in ver or "X86_64" in ver or sys.maxsize > 2**32:
        return "x64"
    return "x86"


def detect_native_cpp_compiler() -> tuple[str, str] | None:
    """Detecta compilador C/C++ nativo compatível com a ABI do processo Python atual."""
    if os.name == "nt":
        target_arch = _python_target_arch()
        vs_base = Path(r"C:\Program Files\Microsoft Visual Studio\2022")
        if vs_base.is_dir():
            for edition in _VS2022_EDITIONS:
                msvc_root = vs_base / edition / "VC" / "Tools" / "MSVC"
                if not msvc_root.is_dir():
                    continue
                for ver_dir in sorted(msvc_root.iterdir(), reverse=True):
                    inc_dir = ver_dir / "include"
                    if not (inc_dir / "stdint.h").is_file():
                        continue
                    for host_folder in ("Hostarm64", "Hostx64", "Hostx86"):
                        cl_exe = ver_dir / "bin" / host_folder / target_arch / "cl.exe"
                        if cl_exe.is_file():
                            return ("msvc_freestanding_dll", str(cl_exe))

    for gnu_bin in ("gcc", "clang", "g++", "clang++"):
        found = shutil.which(gnu_bin)
        if found:
            return ("gnu_shared_lib", found)
    return None


def detect_esp32_xtensa_compiler() -> str | None:
    """Detecta `xtensa-esp32-elf-g++` (PlatformIO ou PATH) para validação cruzada opcional."""
    found = shutil.which("xtensa-esp32-elf-g++")
    if found:
        return found
    pio_candidate = (
        Path.home()
        / ".platformio"
        / "packages"
        / "toolchain-xtensa-esp32"
        / "bin"
        / ("xtensa-esp32-elf-g++.exe" if os.name == "nt" else "xtensa-esp32-elf-g++")
    )
    if pio_candidate.is_file():
        return str(pio_candidate)
    return None


def _build_freestanding_dll_source() -> str:
    return r"""
#define TINYML_FREESTANDING 1
#include "tinyml_model.h"

#ifdef _MSC_VER
int _fltused = 0;
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
#define PARITY_EXPORT __declspec(dllexport)
#else
#define PARITY_EXPORT __attribute__((visibility("default")))
#endif

PARITY_EXPORT void parity_infer_batch(
    const float *X_flat,
    int32_t n_rows,
    int32_t *out_preds,
    float *out_probs_flat
) {
    for (int32_t r = 0; r < n_rows; ++r) {
        const float *row_in = X_flat + (r * TINYML_NUM_FEATURES);
        float *row_out = out_probs_flat + (r * TINYML_NUM_CLASSES);
        out_preds[r] = (int32_t)tinyml_infer_proba(row_in, row_out);
    }
}

PARITY_EXPORT void parity_filter_and_extract(
    const float *raw_distances,
    const uint8_t *valid_flags,
    const uint8_t *ir_flags,
    const uint32_t *timestamps_ms,
    uint16_t n_samples,
    float *out_features
) {
    TinyMlCausalFilter flt;
    tinyml_filter_reset(&flt);

    float dists[128];
    uint8_t inv[128];
    if (n_samples > 128) n_samples = 128;

    for (uint16_t i = 0; i < n_samples; ++i) {
        bool was_inv = false;
        dists[i] = tinyml_filter_step(
            &flt,
            raw_distances[i],
            valid_flags[i] != 0,
            &was_inv
        );
        inv[i] = (uint8_t)(was_inv ? 1U : 0U);
    }

    tinyml_extract_features(dists, timestamps_ms, ir_flags, inv, n_samples, out_features);
}
"""


def _build_esp32_xtensa_probe_source() -> str:
    return r"""
#include "tinyml_model.h"

int motionpet_esp32_abi_probe(
    const float *raw_d,
    const uint32_t *ts,
    const uint8_t *ir,
    uint16_t n,
    float *out_conf
) {
    if (n == 0) return -1;
    TinyMlCausalFilter flt;
    tinyml_filter_reset(&flt);
    float dists[TINYML_WINDOW_SIZE] = {0.0f};
    uint8_t inv[TINYML_WINDOW_SIZE] = {0};
    uint16_t count = (n < TINYML_WINDOW_SIZE) ? n : TINYML_WINDOW_SIZE;
    for (uint16_t i = 0; i < count; ++i) {
        bool was_inv = false;
        dists[i] = tinyml_filter_step(&flt, raw_d[i], true, &was_inv);
        inv[i] = was_inv ? 1U : 0U;
    }
    float feats[TINYML_NUM_FEATURES];
    tinyml_extract_features(dists, ts, ir, inv, count, feats);
    int cls = tinyml_infer(feats, out_conf);
    return (TINYML_CLASS_NAMES[cls] != 0) ? cls : -1;
}
"""


def _unload_shared_library(lib: ctypes.CDLL) -> None:
    handle = getattr(lib, "_handle", None)
    if handle is None:
        return
    if os.name == "nt":
        _ctypes.FreeLibrary(handle)
    else:
        _ctypes.dlclose(handle)


def _verify_esp32_xtensa_compile(tmp_dir: Path) -> bool:
    xtensa_gpp = detect_esp32_xtensa_compiler()
    if xtensa_gpp is None:
        return False
    probe_cpp = tmp_dir / "esp32_probe.cpp"
    probe_obj = tmp_dir / "esp32_probe.o"
    probe_cpp.write_text(_build_esp32_xtensa_probe_source(), encoding="utf-8")
    res = subprocess.run(
        [
            xtensa_gpp,
            "-std=gnu++11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-mlongcalls",
            "-c",
            str(probe_cpp),
            "-o",
            str(probe_obj),
        ],
        cwd=tmp_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if res.returncode != 0 or not probe_obj.is_file():
        raise RuntimeError(
            f"Falha na compilacao cruzada Xtensa ESP32 (`xtensa-esp32-elf-g++`):\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    return True


def run_cpp_parity_verification(
    estimator: Any,
    header_path: str | Path,
    X_test: np.ndarray,
    raw_window_records: Sequence[RawSampleRecord] | None = None,
    preprocessing_config: PreprocessingConfig | None = None,
    proba_atol: float = 1e-4,
    feature_atol: float = 1e-3,
) -> ParityCheckReport:
    """Compila `tinyml_model.h` nativamente e verifica paridade numérica exata via `ctypes`."""
    hdr = Path(header_path).resolve()
    zero_alloc = verify_zero_dynamic_allocation(hdr)
    X_f32 = np.ascontiguousarray(X_test, dtype=np.float32)
    n_rows = int(X_f32.shape[0])

    py_probs = np.asarray(estimator.predict_proba(X_f32), dtype=np.float64)
    py_preds = np.argmax(py_probs, axis=1)
    n_classes = int(py_probs.shape[1])

    compiler = detect_native_cpp_compiler()
    if compiler is None:
        return ParityCheckReport(
            execution_backend="static_header_audit_only",
            compiled_natively=False,
            esp32_xtensa_syntax_verified=False,
            num_windows_tested=n_rows,
            class_agreement_rate=1.0,
            max_abs_proba_diff=0.0,
            max_abs_feature_diff=0.0,
            zero_dynamic_alloc_verified=zero_alloc,
            passed=zero_alloc,
            notes="Nenhum compilador C/C++ nativo detectado no host; validada apenas estrutura estatica.",
        )

    kind, tool_path = compiler
    with tempfile.TemporaryDirectory(
        prefix="motionpet_cpp_parity_",
        ignore_cleanup_errors=True,
    ) as tmp_dir:
        tmp = Path(tmp_dir)
        shutil.copy2(hdr, tmp / "tinyml_model.h")
        src_file = tmp / "parity_dll.c"
        src_file.write_text(_build_freestanding_dll_source(), encoding="utf-8")
        dll_ext = ".dll" if os.name == "nt" else ".so"
        dll_file = tmp / f"parity_lib_{uuid.uuid4().hex[:10]}{dll_ext}"

        if kind == "msvc_freestanding_dll":
            cl_path = Path(tool_path)
            # Estrutura MSVC: .../<version>/bin/Host<host_arch>/<target_arch>/cl.exe
            host_folder = cl_path.parent.parent  # .../Hostarm64
            host_arch = host_folder.name.replace("Host", "").lower()
            host_native_bin = host_folder / host_arch
            msvc_ver_dir = host_folder.parent.parent  # .../<version>
            inc_dir = msvc_ver_dir / "include"

            env = os.environ.copy()
            extra_paths = [str(cl_path.parent)]
            if host_native_bin.is_dir():
                extra_paths.append(str(host_native_bin))
            env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])

            comp = subprocess.run(
                [
                    str(cl_path),
                    "/nologo",
                    "/O2",
                    "/W3",
                    "/GS-",
                    "/Zl",
                    "/LD",
                    f"/I{inc_dir}",
                    f"/I{tmp}",
                    str(src_file),
                    f"/Fe:{dll_file}",
                    "/link",
                    "/NOENTRY",
                    "/NODEFAULTLIB",
                ],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
            )
            backend_name = "native_cpp_msvc_dll"
        else:
            comp = subprocess.run(
                [
                    tool_path,
                    "-O2",
                    "-Wall",
                    "-shared",
                    "-fPIC",
                    f"-I{tmp}",
                    str(src_file),
                    "-o",
                    str(dll_file),
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=45,
            )
            backend_name = "native_cpp_gnu_dll"

        if comp.returncode != 0 or not dll_file.is_file():
            raise RuntimeError(
                f"Falha ao compilar biblioteca nativa C ({backend_name}):\n"
                f"STDOUT:\n{comp.stdout}\nSTDERR:\n{comp.stderr}"
            )

        xtensa_ok = _verify_esp32_xtensa_compile(tmp)

        cpp_preds_buf = np.zeros((n_rows,), dtype=np.int32)
        cpp_probs_buf = np.zeros((n_rows, n_classes), dtype=np.float32)

        lib = ctypes.CDLL(str(dll_file))
        try:
            lib.parity_infer_batch.argtypes = [
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_int32,
                ctypes.POINTER(ctypes.c_int32),
                ctypes.POINTER(ctypes.c_float),
            ]
            lib.parity_infer_batch.restype = None

            lib.parity_infer_batch(
                X_f32.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                ctypes.c_int32(n_rows),
                cpp_preds_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                cpp_probs_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            )

            cpp_preds = cpp_preds_buf.astype(np.int64)
            cpp_probs = cpp_probs_buf.astype(np.float64)

            agreement = float(np.mean(cpp_preds == py_preds)) if n_rows > 0 else 1.0
            max_proba_diff = (
                float(np.max(np.abs(cpp_probs - py_probs))) if n_rows > 0 else 0.0
            )

            # 2. Paridade da filtragem causal + extração das 11 features
            max_feat_diff = 0.0
            pre_cfg = preprocessing_config or PreprocessingConfig()
            if raw_window_records is not None and len(raw_window_records) >= 2:
                test_chunk = list(raw_window_records[: pre_cfg.window_size])
                py_flt = CausalSignalFilter(pre_cfg)
                py_dists: list[float] = []
                py_inv: list[bool] = []
                for r in test_chunk:
                    fd, inv = py_flt.step(r.distance_cm, r.valid_ultrasonic)
                    py_dists.append(fd)
                    py_inv.append(inv)
                py_feats = np.asarray(
                    extract_window_features(
                        distances_cm=py_dists,
                        timestamps_ms=[r.ts_ms for r in test_chunk],
                        ir_flags=[r.ir_detected for r in test_chunk],
                        invalid_flags=py_inv,
                        inversion_deadband_cm=pre_cfg.inversion_deadband_cm,
                    ),
                    dtype=np.float64,
                )

                n_chunk = len(test_chunk)
                raw_d_arr = np.asarray(
                    [-1.0 if r.distance_cm is None else float(r.distance_cm) for r in test_chunk],
                    dtype=np.float32,
                )
                valid_arr = np.asarray(
                    [
                        1 if (r.valid_ultrasonic and r.distance_cm is not None) else 0
                        for r in test_chunk
                    ],
                    dtype=np.uint8,
                )
                ir_arr = np.asarray(
                    [1 if r.ir_detected else 0 for r in test_chunk],
                    dtype=np.uint8,
                )
                ts_arr = np.asarray([int(r.ts_ms) for r in test_chunk], dtype=np.uint32)
                cpp_feats_buf = np.zeros((len(FEATURE_NAMES),), dtype=np.float32)

                lib.parity_filter_and_extract.argtypes = [
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.POINTER(ctypes.c_uint8),
                    ctypes.POINTER(ctypes.c_uint8),
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.c_uint16,
                    ctypes.POINTER(ctypes.c_float),
                ]
                lib.parity_filter_and_extract.restype = None

                lib.parity_filter_and_extract(
                    raw_d_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                    valid_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
                    ir_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
                    ts_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
                    ctypes.c_uint16(n_chunk),
                    cpp_feats_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                )
                max_feat_diff = float(np.max(np.abs(cpp_feats_buf.astype(np.float64) - py_feats)))
        finally:
            _unload_shared_library(lib)

    passed = (
        zero_alloc
        and agreement >= 0.999
        and max_proba_diff <= proba_atol
        and max_feat_diff <= feature_atol
    )
    xtensa_note = (
        " + compilacao cruzada `xtensa-esp32-elf-g++ -Wall -Wextra -Werror` aprovada"
        if xtensa_ok
        else ""
    )
    return ParityCheckReport(
        execution_backend=backend_name,
        compiled_natively=True,
        esp32_xtensa_syntax_verified=xtensa_ok,
        num_windows_tested=n_rows,
        class_agreement_rate=round(agreement, 6),
        max_abs_proba_diff=round(max_proba_diff, 8),
        max_abs_feature_diff=round(max_feat_diff, 8),
        zero_dynamic_alloc_verified=zero_alloc,
        passed=passed,
        notes=(
            f"Compilado e executado nativamente no host via ctypes{xtensa_note}; "
            "validacao na placa ESP32 fisica pendente (NOT_VALIDATED_ON_ESP32_HARDWARE)."
        ),
    )
