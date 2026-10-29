"""Validação de integridade, ordenação temporal e qualidade das sessões coletadas."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from ml.schemas import ALL_GESTURE_CLASSES, RawSampleRecord


@dataclass(frozen=True)
class SessionQualityReport:
    """Diagnóstico completo de integridade e qualidade de uma sessão de sensores."""

    session_id: str
    valid: bool
    total_samples: int
    invalid_ultrasonic_count: int
    invalid_ratio: float
    min_dt_ms: int | None
    max_dt_ms: int | None
    mean_dt_ms: float | None
    labels_distribution: dict[str, int]
    data_origins: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_session_records(
    records: Sequence[RawSampleRecord],
    min_samples: int = 10,
    max_invalid_ratio: float = 0.50,
    expected_min_dt_ms: int = 20,
    expected_max_dt_ms: int = 250,
) -> SessionQualityReport:
    """Verifica schema, monotonicidade estrita de timestamps, taxas de falha e rótulos."""
    errors: list[str] = []
    warnings: list[str] = []

    if not records:
        return SessionQualityReport(
            session_id="EMPTY",
            valid=False,
            total_samples=0,
            invalid_ultrasonic_count=0,
            invalid_ratio=1.0,
            min_dt_ms=None,
            max_dt_ms=None,
            mean_dt_ms=None,
            labels_distribution={},
            data_origins=(),
            errors=("Sessão vazia (0 amostras).",),
            warnings=(),
        )

    session_ids = {r.session_id for r in records}
    session_label = next(iter(session_ids)) if len(session_ids) == 1 else "MULTIPLE_SESSIONS"
    if len(session_ids) > 1:
        errors.append(f"Múltiplos session_id misturados no mesmo bloco: {sorted(session_ids)}")

    participants = {r.participant_id for r in records}
    if len(participants) > 1:
        errors.append(f"Múltiplos participant_id na mesma sessão: {sorted(participants)}")
    if any(not r.participant_id for r in records):
        errors.append("participant_id vazio detectado.")

    n = len(records)
    if n < min_samples:
        errors.append(f"Quantidade insuficiente de amostras: {n} (mínimo exigido: {min_samples}).")

    dts: list[int] = []
    invalid_count = 0
    unknown_labels: set[str] = set()

    for idx, rec in enumerate(records):
        if rec.label not in ALL_GESTURE_CLASSES:
            unknown_labels.add(rec.label)

        if not (0.0 <= rec.pot_norm <= 1.0):
            errors.append(f"Amostra {idx}: pot_norm fora de [0, 1] ({rec.pot_norm}).")

        if not rec.valid_ultrasonic or rec.distance_cm is None:
            invalid_count += 1
        elif not (2.0 <= rec.distance_cm <= 400.0):
            warnings.append(
                f"Amostra {idx}: distance_cm fora da faixa nominal do HC-SR04 ({rec.distance_cm} cm)."
            )

        if idx > 0:
            prev = records[idx - 1]
            dt = rec.ts_ms - prev.ts_ms
            dts.append(dt)
            if dt <= 0:
                errors.append(
                    f"Violação de ordenação temporal estrita entre índices {idx - 1} e {idx}: "
                    f"ts_ms {prev.ts_ms} -> {rec.ts_ms} (dt={dt} ms)."
                )
            if rec.sample_idx <= prev.sample_idx:
                errors.append(
                    f"Violação de ordenação de sample_idx entre {prev.sample_idx} e {rec.sample_idx}."
                )

    if unknown_labels:
        errors.append(f"Rótulos desconhecidos encontrados: {sorted(unknown_labels)}")

    inv_ratio = invalid_count / n
    if inv_ratio > max_invalid_ratio:
        # Nota: se a sessão for puramente NEUTRAL sem obstáculos, timeouts podem ser altos;
        # porém acima do limiar configurado alertamos/reprovamos conforme contexto.
        only_neutral = {r.label for r in records} == {"NEUTRAL"}
        if only_neutral:
            warnings.append(
                f"Sessão NEUTRAL com alta taxa de timeouts ultrassônicos ({inv_ratio:.1%}), "
                "esperado quando não há fundo reflexivo próximo."
            )
        else:
            errors.append(
                f"Taxa de leituras inválidas/timeouts ({inv_ratio:.1%}) excede o limite ({max_invalid_ratio:.1%})."
            )
    elif inv_ratio > 0.20:
        warnings.append(f"Taxa moderada de timeouts ultrassônicos: {inv_ratio:.1%}.")

    min_dt = min(dts) if dts else None
    max_dt = max(dts) if dts else None
    mean_dt = round(statistics.fmean(dts), 2) if dts else None

    if min_dt is not None and min_dt < expected_min_dt_ms:
        warnings.append(
            f"Intervalo mínimo entre amostras ({min_dt} ms) abaixo de {expected_min_dt_ms} ms "
            "(risco de eco residual no HC-SR04)."
        )
    if max_dt is not None and max_dt > expected_max_dt_ms:
        warnings.append(
            f"Jitter/lacuna temporal elevada detectada: max_dt={max_dt} ms (limite nominal {expected_max_dt_ms} ms)."
        )

    dist_labels = dict(Counter(r.label for r in records))
    origins = tuple(sorted({r.data_origin for r in records}))

    return SessionQualityReport(
        session_id=session_label,
        valid=(len(errors) == 0),
        total_samples=n,
        invalid_ultrasonic_count=invalid_count,
        invalid_ratio=round(inv_ratio, 4),
        min_dt_ms=min_dt,
        max_dt_ms=max_dt,
        mean_dt_ms=mean_dt,
        labels_distribution=dist_labels,
        data_origins=origins,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
