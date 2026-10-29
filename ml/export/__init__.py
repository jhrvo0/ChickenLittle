"""Subpacote de exportação estática C/C++ TinyML e verificação de paridade."""

from ml.export.cpp_exporter import ExportMetadata, export_model_to_cpp_header
from ml.export.parity import (
    ParityCheckReport,
    detect_native_cpp_compiler,
    run_cpp_parity_verification,
    verify_zero_dynamic_allocation,
)

__all__ = [
    "ExportMetadata",
    "ParityCheckReport",
    "detect_native_cpp_compiler",
    "export_model_to_cpp_header",
    "run_cpp_parity_verification",
    "verify_zero_dynamic_allocation",
]
