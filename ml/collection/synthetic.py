"""Gerador de corpus sintético multi-participante/multi-sessão EXCLUSIVO para teste do pipeline.

IMPORTANTE: Todos os registros gerados são carimbados com `data_origin="synthetic_simulator"`.
Eles servem unicamente para verificar integridade de código, reprodutibilidade, exportação C++ e
testes automatizados, NUNCA como evidência experimental de desempenho real do classificador.
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

from ml.collection.collector import save_session_csv, save_session_jsonl
from ml.schemas import DataOrigin, RawSampleRecord


def _synthesize_segment_distances(
    rng: random.Random,
    label: str,
    n_samples: int,
    participant_bias_cm: float,
    speed_scale: float,
) -> list[float]:
    """Gera perfil cinemático 1D com variabilidade entre participantes e tentativas."""
    if label == "APPROACH":
        start = rng.uniform(38.0, 50.0) + participant_bias_cm
        end = rng.uniform(8.0, 15.0) + 0.3 * participant_bias_cm
        vals: list[float] = []
        for i in range(n_samples):
            frac = min(1.0, (i / max(1, n_samples - 1)) * speed_scale)
            vals.append(start + (end - start) * frac)
        return vals

    if label == "RETREAT":
        start = rng.uniform(8.0, 15.0) + 0.3 * participant_bias_cm
        end = rng.uniform(38.0, 50.0) + participant_bias_cm
        vals = []
        for i in range(n_samples):
            frac = min(1.0, (i / max(1, n_samples - 1)) * speed_scale)
            vals.append(start + (end - start) * frac)
        return vals

    if label == "HOLD":
        hold_center = rng.uniform(12.0, 25.0) + 0.5 * participant_bias_cm
        drift = rng.uniform(-1.0, 1.0)
        return [
            hold_center + drift * (i / max(1, n_samples - 1)) + rng.gauss(0.0, 0.35)
            for i in range(n_samples)
        ]

    # NEUTRAL: inclui ausência de mão (> 70 cm) e movimentos distantes fora da zona ativa
    neutral_mode = rng.choice(("far_idle", "distant_wander"))
    if neutral_mode == "far_idle":
        base = rng.uniform(72.0, 130.0)
        return [base + rng.gauss(0.0, 1.2) for _ in range(n_samples)]
    base = rng.uniform(62.0, 90.0)
    amp = rng.uniform(-6.0, 6.0)
    return [base + amp * ((i % 5) / 4.0) for i in range(n_samples)]


def generate_synthetic_session(
    participant_id: str,
    session_id: str,
    seed: int,
    sample_period_ms: int = 75,
    participant_bias_cm: float = 0.0,
    speed_scale: float = 1.0,
) -> list[RawSampleRecord]:
    """Gera uma sessão contínua realista com NEUTRAL, gestos ativos e transições naturais."""
    rng = random.Random(seed)
    captured_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # Sequência contínua intercalando repouso NEUTRAL e episódios completos dos 3 gestos ativos
    active_order = ["APPROACH", "HOLD", "RETREAT", "APPROACH", "RETREAT", "HOLD"]
    rng.shuffle(active_order)

    plan: list[tuple[str, int]] = [("NEUTRAL", 14)]
    for gest in active_order:
        plan.append((gest, rng.randint(12, 15)))
        plan.append(("NEUTRAL", rng.randint(12, 16)))

    records: list[RawSampleRecord] = []
    ts_ms = 0
    sample_idx = 0

    for label, count in plan:
        clean_curve = _synthesize_segment_distances(
            rng=rng,
            label=label,
            n_samples=count,
            participant_bias_cm=participant_bias_cm,
            speed_scale=speed_scale,
        )
        for base_d in clean_curve:
            jitter_ms = rng.randint(-4, 4)
            ts_ms += max(25, sample_period_ms + jitter_ms)

            # Simula timeouts ocasionais (mais comuns em NEUTRAL distante)
            dropout_p = 0.08 if label == "NEUTRAL" else 0.02
            if rng.random() < dropout_p:
                dist: float | None = None
                valid = False
                ir_hit = False
            else:
                noisy = max(2.0, min(400.0, base_d + rng.gauss(0.0, 0.65)))
                dist = round(noisy, 2)
                valid = True
                ir_hit = dist <= 13.0

            records.append(
                RawSampleRecord(
                    participant_id=participant_id,
                    session_id=session_id,
                    sample_idx=sample_idx,
                    ts_ms=ts_ms,
                    label=label,
                    distance_cm=dist,
                    valid_ultrasonic=valid,
                    ir_detected=ir_hit,
                    pot_norm=0.5,
                    data_origin=DataOrigin.SYNTHETIC_SIMULATOR.value,
                    captured_at_iso=captured_iso,
                )
            )
            sample_idx += 1

    return records


def generate_synthetic_corpus(
    output_dir: str | Path,
    n_participants: int = 5,
    sessions_per_participant: int = 2,
    seed: int = 42,
    write_csv: bool = True,
) -> list[Path]:
    """Gera um conjunto de sessões sintéticas agrupadas por participante em `output_dir`."""
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    master_rng = random.Random(seed)
    created_files: list[Path] = []

    for p_idx in range(1, n_participants + 1):
        participant_id = f"sim_p{p_idx:02d}"
        p_bias = master_rng.uniform(-3.0, 3.0)
        p_speed = master_rng.uniform(0.88, 1.12)

        for s_idx in range(1, sessions_per_participant + 1):
            session_id = f"session_{participant_id}_s{s_idx:02d}"
            s_seed = master_rng.randint(1, 1_000_000)
            records = generate_synthetic_session(
                participant_id=participant_id,
                session_id=session_id,
                seed=s_seed,
                participant_bias_cm=p_bias,
                speed_scale=p_speed,
            )
            jsonl_path = save_session_jsonl(records, out_root / f"{session_id}.jsonl")
            created_files.append(jsonl_path)
            if write_csv:
                save_session_csv(records, out_root / f"{session_id}.csv")

    return created_files
