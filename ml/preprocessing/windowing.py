"""Segmentação de séries temporais em janelas causais e persistência CSV/JSONL."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from ml.preprocessing.features import extract_window_features
from ml.preprocessing.filtering import CausalSignalFilter
from ml.schemas import (
    FEATURE_NAMES,
    PreprocessingConfig,
    RawSampleRecord,
    WindowSample,
)


def segment_session_windows(
    records: Sequence[RawSampleRecord],
    config: PreprocessingConfig | None = None,
    keep_ambiguous_transitions: bool = False,
) -> list[WindowSample]:
    """Processa causalmente uma única sessão ordenada no tempo e extrai janelas."""
    cfg = config or PreprocessingConfig()
    if len(records) < cfg.window_size:
        return []

    ordered = sorted(records, key=lambda r: (r.ts_ms, r.sample_idx))
    sig_filter = CausalSignalFilter(cfg)

    filtered_dists: list[float] = []
    was_invalid: list[bool] = []
    for rec in ordered:
        f_dist, inv = sig_filter.step(rec.distance_cm, rec.valid_ultrasonic)
        filtered_dists.append(f_dist)
        was_invalid.append(inv)

    windows: list[WindowSample] = []
    w = cfg.window_size
    stride = max(1, cfg.stride)

    for start in range(0, len(ordered) - w + 1, stride):
        end = start + w
        chunk = ordered[start:end]
        labels = [r.label for r in chunk]
        counts = Counter(labels)
        dominant_label, dom_count = counts.most_common(1)[0]
        purity = dom_count / w

        if not keep_ambiguous_transitions and purity < cfg.min_label_purity:
            continue

        chosen_label = dominant_label if purity >= cfg.min_label_purity else chunk[-1].label
        feats = extract_window_features(
            distances_cm=filtered_dists[start:end],
            timestamps_ms=[r.ts_ms for r in chunk],
            ir_flags=[r.ir_detected for r in chunk],
            invalid_flags=was_invalid[start:end],
            inversion_deadband_cm=cfg.inversion_deadband_cm,
        )

        # Se qualquer amostra da janela vier de simulador, marca como sintética
        origins = {r.data_origin for r in chunk}
        origin = (
            "synthetic_simulator"
            if "synthetic_simulator" in origins
            else chunk[-1].data_origin
        )

        windows.append(
            WindowSample(
                participant_id=chunk[-1].participant_id,
                session_id=chunk[-1].session_id,
                start_ts_ms=chunk[0].ts_ms,
                end_ts_ms=chunk[-1].ts_ms,
                label=chosen_label,
                features=feats,
                data_origin=origin,
            )
        )

    return windows


def preprocess_records(
    records: Iterable[RawSampleRecord],
    config: PreprocessingConfig | None = None,
    keep_ambiguous_transitions: bool = False,
) -> list[WindowSample]:
    """Agrupa registros por `session_id` (isolando estado do filtro) e extrai janelas."""
    grouped: dict[str, list[RawSampleRecord]] = defaultdict(list)
    for rec in records:
        grouped[rec.session_id].append(rec)

    all_windows: list[WindowSample] = []
    for session_id in sorted(grouped.keys()):
        all_windows.extend(
            segment_session_windows(
                grouped[session_id],
                config=config,
                keep_ambiguous_transitions=keep_ambiguous_transitions,
            )
        )
    return all_windows


def load_raw_records_from_path(path: str | Path) -> list[RawSampleRecord]:
    """Carrega registros brutos de um arquivo `.jsonl`/`.csv` ou diretório contendo sessões."""
    target = Path(path)
    if target.is_dir():
        files = sorted(
            p
            for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in (".jsonl", ".csv")
        )
        # Evita duplicar a mesma sessão caso existam .jsonl e .csv com o mesmo stem
        seen_stems: set[str] = set()
        selected: list[Path] = []
        for f in sorted(files, key=lambda p: (0 if p.suffix.lower() == ".jsonl" else 1, p.name)):
            if f.stem not in seen_stems:
                seen_stems.add(f.stem)
                selected.append(f)
        out: list[RawSampleRecord] = []
        for f in selected:
            out.extend(load_raw_records_from_path(f))
        return out

    if not target.is_file():
        raise FileNotFoundError(f"Caminho de dados brutos não encontrado: '{target}'")

    records: list[RawSampleRecord] = []
    suffix = target.suffix.lower()
    if suffix == ".jsonl":
        for line in target.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            obj = json.loads(stripped)
            if obj.get("_record_type") == "session_header":
                continue
            records.append(RawSampleRecord.from_dict(obj))
        return records

    if suffix == ".csv":
        with target.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                records.append(RawSampleRecord.from_dict(row))
        return records

    raise ValueError(f"Formato não suportado '{suffix}' em '{target}'")


def save_windows_csv(windows: Sequence[WindowSample], output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "participant_id",
        "session_id",
        "start_ts_ms",
        "end_ts_ms",
        "label",
        "data_origin",
        *FEATURE_NAMES,
    ]
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for win in windows:
            writer.writerow(win.to_dict())
    return out


def load_windows_csv(input_path: str | Path) -> list[WindowSample]:
    inp = Path(input_path)
    if not inp.is_file():
        raise FileNotFoundError(f"Arquivo de janelas processadas não encontrado: '{inp}'")
    windows: list[WindowSample] = []
    with inp.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            windows.append(WindowSample.from_dict(row))
    return windows
