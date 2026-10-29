"""Particionamento agrupado anti-vazamento (Anti-Leakage) e conversão para tensores NumPy."""

from __future__ import annotations

import itertools
import random
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES, WindowSample


class DataLeakageError(ValueError):
    """Exceção levantada quando as condições mínimas de particionamento anti-vazamento não são satisfeitas."""


@dataclass(frozen=True)
class DatasetSplit:
    """Partição determinística de janelas divididas estritamente por grupos independentes."""

    train: list[WindowSample]
    val: list[WindowSample]
    test: list[WindowSample]
    strategy: str
    train_groups: tuple[str, ...]
    val_groups: tuple[str, ...]
    test_groups: tuple[str, ...]
    warnings: tuple[str, ...]


def _score_partition(
    assignment: dict[str, int],
    group_classes: dict[str, set[str]],
    group_counts: dict[str, int],
    all_classes: set[str],
    total_samples: int,
    val_ratio: float,
    test_ratio: float,
) -> float:
    """Calcula penalidade da partição: prioriza máxima cobertura de classes e mínima distorção de proporção."""
    train_classes: set[str] = set()
    val_classes: set[str] = set()
    test_classes: set[str] = set()

    n_train = 0
    n_val = 0
    n_test = 0

    for g, part in assignment.items():
        c_set = group_classes[g]
        cnt = group_counts[g]
        if part == 0:
            train_classes.update(c_set)
            n_train += cnt
        elif part == 1:
            val_classes.update(c_set)
            n_val += cnt
        else:
            test_classes.update(c_set)
            n_test += cnt

    # Penalidade severa para classes faltantes
    missing_classes = (
        len(all_classes - train_classes)
        + len(all_classes - val_classes)
        + len(all_classes - test_classes)
    )

    # Penalidade por desvio de proporção amostral
    train_ratio = max(0.1, 1.0 - val_ratio - test_ratio)
    err_train = abs((n_train / total_samples) - train_ratio)
    err_val = abs((n_val / total_samples) - val_ratio)
    err_test = abs((n_test / total_samples) - test_ratio)
    ratio_err = err_train + err_val + err_test

    return (missing_classes * 10000.0) + (ratio_err * 100.0)


def split_windows_grouped(
    windows: Sequence[WindowSample],
    seed: int = 42,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
) -> DatasetSplit:
    """Particiona janelas em Treino / Validação / Teste sem vazamento temporal ou de sujeito.

    Regras:
    1. Se houver >= 3 participantes distintos, particiona estritamente por `participant_id`.
    2. Caso contrário, se houver >= 3 sessões independentes, particiona por `session_id`
       com aviso explícito de que generalização inter-sujeito não está testada.
    3. Se houver < 3 sessões, levanta DataLeakageError.
    4. O particionamento maximiza deterministamente a presença de todas as classes em cada split.
    """
    if not windows:
        raise ValueError("A sequência de janelas está vazia.")

    participants = sorted({w.participant_id for w in windows})
    sessions = sorted({w.session_id for w in windows})
    warnings: list[str] = []

    if len(participants) >= 3:
        strategy = "by_participant"
        group_attr = "participant_id"
        groups = participants
    elif len(sessions) >= 3:
        strategy = "by_session_fallback"
        group_attr = "session_id"
        groups = sessions
        warnings.append(
            "Generalização entre diferentes participantes ainda não está validada "
            "(particionamento agrupado por sessão independente)."
        )
    else:
        raise DataLeakageError(
            f"Menos de 3 sessões independentes disponíveis para particionamento agrupado "
            f"(participantes={len(participants)}, sessões={len(sessions)}). "
            f"Risco crítico de vazamento de dados decorrente de janelas temporais sobrepostas."
        )

    # Metadados de cada grupo
    group_classes: dict[str, set[str]] = {}
    group_counts: dict[str, int] = {}
    all_classes = {w.label for w in windows}

    for g in groups:
        g_windows = [w for w in windows if getattr(w, group_attr) == g]
        group_classes[g] = {w.label for w in g_windows}
        group_counts[g] = len(g_windows)

    total_samples = len(windows)
    k = len(groups)

    best_score = float("inf")
    best_assignment: dict[str, int] = {}

    rng = random.Random(seed)

    # Para k pequeno (<= 8), podemos avaliar exaustivamente todas as 3^k partições válidas
    if k <= 8:
        for p_tuple in itertools.product((0, 1, 2), repeat=k):
            # Garante ao menos 1 grupo em cada partição
            if len(set(p_tuple)) < 3:
                continue
            cand_assignment = {groups[i]: p_tuple[i] for i in range(k)}
            score = _score_partition(
                cand_assignment,
                group_classes,
                group_counts,
                all_classes,
                total_samples,
                val_ratio,
                test_ratio,
            )
            if score < best_score:
                best_score = score
                best_assignment = cand_assignment
    else:
        # Busca determinística com seed sobre partições e permutações
        # 1. Candidato heurístico guloso ordenado por diversidade de classes
        sorted_groups = sorted(
            groups,
            key=lambda g: (len(group_classes[g]), group_counts[g]),
            reverse=True,
        )
        heuristic_assign: dict[str, int] = {}
        for idx, g in enumerate(sorted_groups):
            # Garante primeiros 3 em partições distintas
            if idx == 0:
                heuristic_assign[g] = 0  # train
            elif idx == 1:
                heuristic_assign[g] = 1  # val
            elif idx == 2:
                heuristic_assign[g] = 2  # test
            else:
                heuristic_assign[g] = 0

        score = _score_partition(
            heuristic_assign,
            group_classes,
            group_counts,
            all_classes,
            total_samples,
            val_ratio,
            test_ratio,
        )
        best_score = score
        best_assignment = heuristic_assign

        # 2. Amostragem determinística de partições candidatas
        for _ in range(2500):
            # Garante que cada partição receba ao menos 1 grupo
            shuffled = list(groups)
            rng.shuffle(shuffled)
            cand_assign = {
                shuffled[0]: 0,
                shuffled[1]: 1,
                shuffled[2]: 2,
            }
            # Atribuição ponderada pelas proporções alvo
            for g in shuffled[3:]:
                r = rng.random()
                if r < val_ratio:
                    cand_assign[g] = 1
                elif r < (val_ratio + test_ratio):
                    cand_assign[g] = 2
                else:
                    cand_assign[g] = 0

            cand_score = _score_partition(
                cand_assign,
                group_classes,
                group_counts,
                all_classes,
                total_samples,
                val_ratio,
                test_ratio,
            )
            if cand_score < best_score:
                best_score = cand_score
                best_assignment = cand_assign

    train_groups = tuple(sorted(g for g, p in best_assignment.items() if p == 0))
    val_groups = tuple(sorted(g for g, p in best_assignment.items() if p == 1))
    test_groups = tuple(sorted(g for g, p in best_assignment.items() if p == 2))

    train_windows = [w for w in windows if getattr(w, group_attr) in train_groups]
    val_windows = [w for w in windows if getattr(w, group_attr) in val_groups]
    test_windows = [w for w in windows if getattr(w, group_attr) in test_groups]

    # Verifica cobertura final de classes para registrar alertas se necessário
    train_c = {w.label for w in train_windows}
    val_c = {w.label for w in val_windows}
    test_c = {w.label for w in test_windows}

    for c in sorted(all_classes):
        if c not in train_c:
            warnings.append(f"Classe '{c}' ausente no subconjunto de treino devido a restrições de grupos.")
        if c not in val_c:
            warnings.append(f"Classe '{c}' ausente no subconjunto de validação devido a restrições de grupos.")
        if c not in test_c:
            warnings.append(f"Classe '{c}' ausente no subconjunto de teste devido a restrições de grupos.")

    return DatasetSplit(
        train=train_windows,
        val=val_windows,
        test=test_windows,
        strategy=strategy,
        train_groups=train_groups,
        val_groups=val_groups,
        test_groups=test_groups,
        warnings=tuple(warnings),
    )


def windows_to_xy(
    windows: Sequence[WindowSample],
    class_names: Sequence[str] = CORE_GESTURE_CLASSES,
) -> tuple[np.ndarray, np.ndarray]:
    """Filtra janelas pelas classes canônicas e projeta para vetores de features `X` e rótulos `y`."""
    class_to_idx = {name: idx for idx, name in enumerate(class_names)}
    filtered = [w for w in windows if w.label in class_to_idx]

    if not filtered:
        return (
            np.zeros((0, len(FEATURE_NAMES)), dtype=np.float64),
            np.zeros((0,), dtype=np.int64),
        )

    X = np.array([w.features for w in filtered], dtype=np.float64)
    y = np.array([class_to_idx[w.label] for w in filtered], dtype=np.int64)
    return X, y
