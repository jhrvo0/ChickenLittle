"""Validação cruzada só no desenvolvimento, preservando o holdout externo."""
from __future__ import annotations

import numpy as np
from sklearn.base import clone
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, StratifiedGroupKFold

from ml.training.models import TrainingConfig, build_candidate_models
from ml.training.splitter import windows_to_xy


def cross_validate_grouped(windows, config=None, *, group_attr="participant_id", leave_one_out=False, candidates=None):
    cfg = config or TrainingConfig()
    X, y = windows_to_xy(windows, cfg.class_names)
    if len(y) != len(windows):
        raise ValueError("CV aceita apenas as classes canônicas do experimento.")
    groups = np.asarray([getattr(w, group_attr) for w in windows])
    count = len(set(groups))
    if count < 2:
        return {"status": "pending", "reason": "Menos de dois grupos de desenvolvimento.", "models": {}}
    n_splits = min(5, count)
    if leave_one_out:
        splitter, method = LeaveOneGroupOut(), "LeaveOneGroupOut"
    elif _can_stratify(y, groups, n_splits):
        # k-fold estratificado que também respeita os grupos: cada participante fica inteiro em um
        # fold e a proporção das classes é equilibrada entre folds (NEUTRAL é majoritária).
        splitter, method = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=cfg.seed), "StratifiedGroupKFold"
    else:
        splitter, method = GroupKFold(n_splits=n_splits), "GroupKFold"
    folds = list(splitter.split(X, y, groups))
    results = {}
    for name, prototype in (candidates if candidates is not None else build_candidate_models(cfg)).items():
        scores = []
        for index, (train, val) in enumerate(folds):
            train_groups = sorted(set(groups[train]))
            val_groups = sorted(set(groups[val]))
            assert not set(train_groups) & set(val_groups)
            missing = sorted(set(range(len(cfg.class_names))) - set(y[train]))
            if missing:
                scores.append({"fold": index, "status": "pending", "train_groups": train_groups,
                               "validation_groups": val_groups, "missing_training_classes": missing})
                continue
            model = clone(prototype).fit(X[train], y[train])
            labels = list(range(len(cfg.class_names)))
            score = f1_score(y[val], model.predict(X[val]), labels=labels, average="macro", zero_division=0)
            # F1 no próprio treino do fold: a distância para a validação indica sobreajuste.
            train_score = f1_score(y[train], model.predict(X[train]), labels=labels, average="macro", zero_division=0)
            scores.append({"fold": index, "status": "evaluated", "train_groups": train_groups,
                           "validation_groups": val_groups, "f1_macro": float(score),
                           "train_f1_macro": float(train_score),
                           "missing_validation_classes": sorted(set(range(len(cfg.class_names))) - set(y[val]))})
        values = [s["f1_macro"] for s in scores if s["status"] == "evaluated"]
        train_values = [s["train_f1_macro"] for s in scores if s["status"] == "evaluated"]
        results[name] = {"folds": scores, "valid_folds": len(values),
                         "f1_macro_mean": float(np.mean(values)) if values else None,
                         "f1_macro_std": float(np.std(values)) if values else None,
                         "train_f1_macro_mean": float(np.mean(train_values)) if train_values else None,
                         "generalization_gap": float(np.mean(train_values) - np.mean(values)) if values else None,
                         "fit_diagnosis": _fit_diagnosis(train_values, values)}
    complete = all(r["valid_folds"] == len(folds) for r in results.values())
    return {"status": "evaluated" if complete else "incomplete", "group_attr": group_attr,
            "method": method, "n_splits": len(folds),
            "scope": "development_only", "models": results}


def _can_stratify(y, groups, n_splits):
    """Estratificar só faz sentido se cada classe aparece em pelo menos n_splits grupos."""
    if n_splits < 2:
        return False
    for label in np.unique(y):
        if len(set(groups[y == label])) < n_splits:
            return False
    return True


def _fit_diagnosis(train_values, val_values, *, gap_limit=0.10, low_limit=0.60):
    """Rótulo descritivo; os limiares são convenções do projeto, não testes estatísticos."""
    if not val_values:
        return "pending"
    train, val = float(np.mean(train_values)), float(np.mean(val_values))
    if train - val > gap_limit:
        return "overfitting"
    if train < low_limit and val < low_limit:
        return "underfitting"
    return "balanced"


def tune_tree_depth(windows, config, group_attr):
    """Busca pequena e explícita; nenhum trial recebe o holdout externo."""
    from dataclasses import replace
    trials = []
    for depth in (3, 5, 7):
        cfg = replace(config, dt_max_depth=depth)
        candidate = build_candidate_models(cfg)["decision_tree"]
        cv = cross_validate_grouped(windows, cfg, group_attr=group_attr, candidates={"decision_tree": candidate})
        model = cv.get("models", {}).get("decision_tree", {})
        trials.append({"dt_max_depth": depth, "status": cv["status"],
                       "cv_f1_macro": model.get("f1_macro_mean"), "cv": cv})
    complete = [t for t in trials if t["status"] == "evaluated" and t["cv_f1_macro"] is not None]
    if not complete:
        return config, {"status": "pending", "trials": trials}
    best = max(complete, key=lambda t: (t["cv_f1_macro"], -t["dt_max_depth"]))
    return replace(config, dt_max_depth=best["dt_max_depth"]), {
        "status": "selected_on_development_cv", "selected_dt_max_depth": best["dt_max_depth"], "trials": trials,
        "caveat": "CV após tuning é descritiva; o holdout externo é a estimativa final reservada."}


# Espaços de busca pequenos de propósito: rodam dentro do Airflow com 1 CPU e 1,4 GB.
# Chaves "<modelo>__<campo do TrainingConfig>" para aplicar o vencedor sem mapeamento manual.
SEARCH_SPACES = {
    "decision_tree": {"dt_max_depth": [3, 5, 7, 9], "dt_min_samples_leaf": [1, 3, 5]},
    "random_forest": {"rf_n_estimators": [25, 50, 100], "rf_max_depth": [4, 6, 8], "rf_min_samples_leaf": [1, 2, 4]},
    "mlp_compact": {"mlp_hidden_layers": [(16, 8), (32, 16), (16,)], "mlp_alpha": [1e-4, 1e-3, 1e-2]},
    "knn": {"knn_n_neighbors": [3, 5, 7, 11, 15], "knn_weights": ["uniform", "distance"]},
    "adaboost": {"ada_n_estimators": [25, 50, 100], "ada_learning_rate": [0.1, 0.5, 1.0]},
}


def search_hyperparameters(windows, config, group_attr, *, method="grid", n_iter=6, models=None):
    """Grid Search ou Random Search por modelo, com GroupKFold só nos grupos de desenvolvimento.

    Cada combinação é avaliada por F1-macro médio nos folds agrupados, com o F1 de treino ao lado
    para expor sobreajuste. O holdout externo não participa. O vencedor de cada família é
    aplicado ao TrainingConfig devolvido.
    """
    from dataclasses import replace
    from itertools import product
    import random

    if method not in ("grid", "random"):
        raise ValueError("Método de busca: grid ou random.")
    names = [m for m in (models or SEARCH_SPACES) if m in SEARCH_SPACES]
    if not config.include_extended_candidates:
        names = [m for m in names if m not in ("knn", "adaboost")]
    rng = random.Random(config.seed)
    families, best_config = {}, config
    for name in names:
        space = SEARCH_SPACES[name]
        keys = list(space)
        combos = [dict(zip(keys, values)) for values in product(*(space[k] for k in keys))]
        if method == "random" and len(combos) > n_iter:
            combos = rng.sample(combos, n_iter)
        trials = []
        for params in combos:
            cfg = replace(config, **params)
            candidate = build_candidate_models(cfg)[name]
            cv = cross_validate_grouped(windows, cfg, group_attr=group_attr, candidates={name: candidate})
            model = cv.get("models", {}).get(name, {})
            trials.append({"params": {k: list(v) if isinstance(v, tuple) else v for k, v in params.items()},
                           "status": cv["status"], "cv_f1_macro": model.get("f1_macro_mean"),
                           "cv_f1_macro_std": model.get("f1_macro_std"),
                           "train_f1_macro": model.get("train_f1_macro_mean"),
                           "generalization_gap": model.get("generalization_gap")})
        complete = [t for t in trials if t["status"] == "evaluated" and t["cv_f1_macro"] is not None]
        if not complete:
            families[name] = {"status": "pending", "trials": trials}
            continue
        # Empate: menor diferença treino-validação (modelo mais estável).
        best = max(complete, key=lambda t: (t["cv_f1_macro"], -(t["generalization_gap"] or 0.0)))
        applied = {k: tuple(v) if isinstance(v, list) else v for k, v in best["params"].items()}
        best_config = replace(best_config, **applied)
        families[name] = {"status": "selected_on_development_cv", "best_params": best["params"],
                          "best_cv_f1_macro": best["cv_f1_macro"], "evaluated_combinations": len(trials),
                          "trials": trials}
    return best_config, {"status": "evaluated" if families else "not_applicable", "method": method,
                         "cv": "StratifiedGroupKFold/GroupKFold (ver validation)", "group_attr": group_attr, "scope": "development_only",
                         "selection_metric": "f1_macro", "models": families,
                         "caveat": "Seleção feita na CV de desenvolvimento; o holdout externo é a estimativa final."}


def compare_models_statistically(cv_result, *, alpha=0.05):
    """Compara os modelos nos mesmos folds: teste de Friedman e Wilcoxon pareado contra o melhor.

    Os folds são os mesmos para todos os modelos, então as amostras são pareadas. Com poucos folds o
    poder é baixo: um p-valor alto significa "sem evidência de diferença", não "modelos iguais".
    p-valores do Wilcoxon são corrigidos por Holm para as comparações múltiplas.
    """
    from scipy.stats import friedmanchisquare, rankdata, wilcoxon

    models = {name: m for name, m in cv_result.get("models", {}).items()
              if m.get("valid_folds") and m["valid_folds"] == cv_result.get("n_splits")}
    if len(models) < 3 or cv_result.get("n_splits", 0) < 3:
        return {"status": "pending", "reason": "Exige 3+ modelos avaliados em todos os 3+ folds."}
    names = list(models)
    scores = np.array([[f["f1_macro"] for f in models[n]["folds"]] for n in names])  # modelos x folds
    ranks = np.mean([rankdata(-scores[:, j]) for j in range(scores.shape[1])], axis=0)
    friedman = friedmanchisquare(*scores)
    best = names[int(np.argmax(scores.mean(axis=1)))]
    raw = []
    for i, name in enumerate(names):
        if name == best:
            continue
        diff = scores[names.index(best)] - scores[i]
        p = 1.0 if np.allclose(diff, 0) else float(wilcoxon(scores[names.index(best)], scores[i]).pvalue)
        raw.append((name, p, float(diff.mean())))
    # Holm: ordena p crescente e multiplica pelo número de hipóteses restantes, mantendo monotonia.
    adjusted, running = {}, 0.0
    for k, (name, p, _) in enumerate(sorted(raw, key=lambda r: r[1])):
        running = max(running, min(1.0, p * (len(raw) - k)))
        adjusted[name] = running
    pairwise = [{"model": name, "mean_f1_difference": diff, "p_value": p, "p_value_holm": adjusted[name],
                 "significant": adjusted[name] < alpha} for name, p, diff in raw]
    return {"status": "evaluated", "cv_method": cv_result.get("method"), "n_folds": int(scores.shape[1]),
            "alpha": alpha, "mean_rank": {n: float(r) for n, r in zip(names, ranks)},
            "friedman": {"statistic": float(friedman.statistic), "p_value": float(friedman.pvalue)},
            "best_model": best, "pairwise_vs_best": sorted(pairwise, key=lambda r: r["mean_f1_difference"]),
            "caveat": "Folds de CV compartilham dados de treino; os testes indicam tendência, não independência estrita."}
