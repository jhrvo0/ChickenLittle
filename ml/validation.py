"""Validação cruzada só no desenvolvimento, preservando o holdout externo."""
from __future__ import annotations

import numpy as np
from sklearn.base import clone
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

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
    splitter = LeaveOneGroupOut() if leave_one_out else GroupKFold(n_splits=min(5, count))
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
            score = f1_score(y[val], model.predict(X[val]), labels=list(range(len(cfg.class_names))),
                             average="macro", zero_division=0)
            scores.append({"fold": index, "status": "evaluated", "train_groups": train_groups,
                           "validation_groups": val_groups, "f1_macro": float(score),
                           "missing_validation_classes": sorted(set(range(len(cfg.class_names))) - set(y[val]))})
        values = [s["f1_macro"] for s in scores if s["status"] == "evaluated"]
        results[name] = {"folds": scores, "valid_folds": len(values),
                         "f1_macro_mean": float(np.mean(values)) if values else None,
                         "f1_macro_std": float(np.std(values)) if values else None}
    complete = all(r["valid_folds"] == len(folds) for r in results.values())
    return {"status": "evaluated" if complete else "incomplete", "group_attr": group_attr,
            "method": "LeaveOneGroupOut" if leave_one_out else "GroupKFold", "n_splits": len(folds),
            "scope": "development_only", "models": results}


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
