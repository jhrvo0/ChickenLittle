"""Extração determinística O(W) de características temporais 1D para Python e TinyML C++."""

from __future__ import annotations

import math
from typing import Sequence

from ml.schemas import FEATURE_NAMES


def extract_window_features(
    distances_cm: Sequence[float],
    timestamps_ms: Sequence[int],
    ir_flags: Sequence[bool],
    invalid_flags: Sequence[bool],
    inversion_deadband_cm: float = 0.8,
) -> tuple[float, ...]:
    """Extrai as 11 características definidas em `FEATURE_NAMES` de uma janela causal.

    Implementada com aritmética elementar idêntica à rotina C++ exportada para o ESP32.
    """
    n = len(distances_cm)
    if n < 2:
        raise ValueError(f"Janela exige ao menos 2 amostras, recebeu {n}")
    if not (len(timestamps_ms) == n and len(ir_flags) == n and len(invalid_flags) == n):
        raise ValueError("Vetores da janela possuem comprimentos incompatíveis")

    d_min = float(distances_cm[0])
    d_max = float(distances_cm[0])
    d_sum = 0.0
    for d in distances_cm:
        fd = float(d)
        if fd < d_min:
            d_min = fd
        if fd > d_max:
            d_max = fd
        d_sum += fd

    d_mean = d_sum / n
    var_sum = 0.0
    for d in distances_cm:
        diff = float(d) - d_mean
        var_sum += diff * diff
    d_std = math.sqrt(var_sum / n)

    d_delta = float(distances_cm[-1]) - float(distances_cm[0])
    total_dt_s = max(1e-3, (int(timestamps_ms[-1]) - int(timestamps_ms[0])) / 1000.0)
    v_mean = d_delta / total_dt_s

    v_peak = 0.0
    inversions = 0
    prev_sign = 0
    for i in range(n - 1):
        step_d = float(distances_cm[i + 1]) - float(distances_cm[i])
        step_dt_s = max(1e-3, (int(timestamps_ms[i + 1]) - int(timestamps_ms[i])) / 1000.0)
        v_inst = step_d / step_dt_s
        if abs(v_inst) > abs(v_peak):
            v_peak = v_inst

        if abs(step_d) >= inversion_deadband_cm:
            sign = 1 if step_d > 0.0 else -1
            if prev_sign != 0 and sign != prev_sign:
                inversions += 1
            prev_sign = sign

    # Tendência linear por mínimos quadrados (cm/s)
    t0 = int(timestamps_ms[0])
    rel_t = [(int(ts) - t0) / 1000.0 for ts in timestamps_ms]
    t_mean = sum(rel_t) / n
    cov_td = 0.0
    var_t = 0.0
    for i in range(n):
        dt_c = rel_t[i] - t_mean
        cov_td += dt_c * (float(distances_cm[i]) - d_mean)
        var_t += dt_c * dt_c
    trend_slope = (cov_td / var_t) if var_t > 1e-9 else 0.0

    ir_active_ratio = sum(1.0 for f in ir_flags if f) / n
    invalid_ratio = sum(1.0 for f in invalid_flags if f) / n

    feats = (
        d_min,
        d_max,
        d_mean,
        d_std,
        d_delta,
        v_mean,
        v_peak,
        trend_slope,
        float(inversions),
        ir_active_ratio,
        invalid_ratio,
    )
    assert len(feats) == len(FEATURE_NAMES)
    return feats
