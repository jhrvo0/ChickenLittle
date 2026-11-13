"""Definição dos modelos candidatos e hiperparâmetros de treinamento."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import AdaBoostClassifier, RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES


@dataclass(frozen=True)
class TrainingConfig:
    """Configuração versionada de hiperparâmetros e sementes de treinamento."""

    seed: int = 42
    class_names: tuple[str, ...] = CORE_GESTURE_CLASSES
    dt_max_depth: int = 5
    dt_min_samples_leaf: int = 3
    rf_n_estimators: int = 25
    rf_max_depth: int = 6
    rf_min_samples_leaf: int = 2
    mlp_hidden_layers: tuple[int, ...] = (16, 8)
    mlp_max_iter: int = 1200
    mlp_alpha: float = 1e-3
    include_learned_baseline: bool = False
    # KNN e AdaBoost: candidatos de comparação exigidos na disciplina de AM. Ficam fora da
    # seleção para o firmware (o exportador C++ cobre só árvore, floresta e MLP).
    include_extended_candidates: bool = False
    knn_n_neighbors: int = 7
    knn_weights: str = "distance"
    ada_n_estimators: int = 50
    ada_learning_rate: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["class_names"] = list(self.class_names)
        data["mlp_hidden_layers"] = list(self.mlp_hidden_layers)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingConfig:
        d = dict(data)
        if "class_names" in d:
            d["class_names"] = tuple(str(c) for c in d["class_names"])
        if "mlp_hidden_layers" in d:
            d["mlp_hidden_layers"] = tuple(int(x) for x in d["mlp_hidden_layers"])
        valid_keys = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid_keys)


class RuleBaselineModel(BaseEstimator, ClassifierMixin):
    """Classificador determinístico baseado em física e regras explícitas de domínio.

    Totalmente compatível com a interface do scikit-learn (`fit`, `predict`, `predict_proba`).
    Não requer treinamento estatístico e serve como baseline mínimo absoluto.
    """

    def __init__(self, class_names: Sequence[str] = CORE_GESTURE_CLASSES):
        self.class_names = tuple(class_names)
        self.classes_ = np.arange(len(self.class_names), dtype=np.int64)

    def fit(self, X: Any, y: Any = None) -> RuleBaselineModel:
        """Compatibilidade scikit-learn (sem aprendizado estatístico)."""
        _ = np.asarray(X)
        self.classes_ = np.arange(len(self.class_names), dtype=np.int64)
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        """Estima probabilidades para cada classe segundo as regras físicas."""
        arr = np.asarray(X, dtype=np.float64)
        n_samples = arr.shape[0]
        n_classes = len(self.class_names)
        if n_samples == 0:
            return np.zeros((0, n_classes), dtype=np.float64)

        probas = np.zeros((n_samples, n_classes), dtype=np.float64)
        c_map = {name: idx for idx, name in enumerate(self.class_names)}
        neutral_idx = c_map.get("NEUTRAL", 0)

        for i in range(n_samples):
            # Ordem de FEATURE_NAMES:
            # 0:d_min, 1:d_max, 2:d_mean, 3:d_std, 4:d_delta, 5:v_mean,
            # 6:v_peak, 7:trend_slope, 8:sign_inversions, 9:ir_active_ratio, 10:invalid_ratio
            d_min = arr[i, 0]
            d_max = arr[i, 1]
            d_mean = arr[i, 2]
            d_std = arr[i, 3]
            d_delta = arr[i, 4]
            v_mean = arr[i, 5]
            v_peak = arr[i, 6]
            trend_slope = arr[i, 7]
            sign_inversions = arr[i, 8]
            ir_active_ratio = arr[i, 9]
            invalid_ratio = arr[i, 10]

            chosen_label = "NEUTRAL"

            # 1. Condição de ausência de alvo ou leitura degradada
            if invalid_ratio > 0.6 or d_mean > 55.0:
                chosen_label = "NEUTRAL"
            # 2. Classes experimentais (se presentes no espaço de rótulos)
            elif "DOUBLE" in c_map and sign_inversions >= 2 and abs(v_peak) > 25.0:
                chosen_label = "DOUBLE"
            elif "IMPULSE" in c_map and abs(v_peak) > 40.0 and sign_inversions <= 1:
                chosen_label = "IMPULSE"
            # 3. Classes fundamentais
            elif d_delta <= -8.0 and trend_slope <= -12.0:
                chosen_label = "APPROACH"
            elif d_delta >= 8.0 and trend_slope >= 12.0:
                chosen_label = "RETREAT"
            elif 6.0 <= d_mean <= 32.0 and d_std <= 3.5 and abs(d_delta) < 6.0:
                chosen_label = "HOLD"
            else:
                chosen_label = "NEUTRAL"

            chosen_idx = c_map.get(chosen_label, neutral_idx)
            if n_classes == 1:
                probas[i, 0] = 1.0
            else:
                high_p = 0.85
                low_p = (1.0 - high_p) / (n_classes - 1)
                probas[i, :] = low_p
                probas[i, chosen_idx] = high_p
                # Normaliza para soma 1.0 exata
                row_sum = probas[i, :].sum()
                if row_sum > 0:
                    probas[i, :] /= row_sum

        return probas

    def predict(self, X: Any) -> np.ndarray:
        """Retorna o índice da classe prevista para cada amostra."""
        probas = self.predict_proba(X)
        if probas.shape[0] == 0:
            return np.zeros((0,), dtype=np.int64)
        return self.classes_[np.argmax(probas, axis=1)]


def build_candidate_models(config: TrainingConfig | None = None) -> dict[str, Any]:
    """Instancia os modelos candidatos: baseline de regras, árvore, floresta e MLP; opcionalmente KNN, AdaBoost e stump."""
    cfg = config or TrainingConfig()
    candidates = {
        "rule_baseline": RuleBaselineModel(class_names=cfg.class_names),
        "decision_tree": DecisionTreeClassifier(
            max_depth=cfg.dt_max_depth,
            min_samples_leaf=cfg.dt_min_samples_leaf,
            class_weight="balanced",
            random_state=cfg.seed,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=cfg.rf_n_estimators,
            max_depth=cfg.rf_max_depth,
            min_samples_leaf=cfg.rf_min_samples_leaf,
            class_weight="balanced",
            random_state=cfg.seed,
        ),
        "mlp_compact": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "mlp",
                    MLPClassifier(
                        hidden_layer_sizes=cfg.mlp_hidden_layers,
                        activation="relu",
                        alpha=cfg.mlp_alpha,
                        max_iter=cfg.mlp_max_iter,
                        random_state=cfg.seed,
                    ),
                ),
            ]
        ),
    }
    if cfg.include_extended_candidates:
        # KNN usa distância: sem padronização, features em cm dominariam as booleanas.
        candidates["knn"] = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("knn", KNeighborsClassifier(n_neighbors=cfg.knn_n_neighbors, weights=cfg.knn_weights)),
            ]
        )
        candidates["adaboost"] = AdaBoostClassifier(
            estimator=DecisionTreeClassifier(max_depth=1, class_weight="balanced", random_state=cfg.seed),
            n_estimators=cfg.ada_n_estimators,
            learning_rate=cfg.ada_learning_rate,
            random_state=cfg.seed,
        )
    if cfg.include_learned_baseline:
        candidates["decision_stump_baseline"] = DecisionTreeClassifier(
            max_depth=1, min_samples_leaf=cfg.dt_min_samples_leaf,
            class_weight="balanced", random_state=cfg.seed,
        )
    return candidates
