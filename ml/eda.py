"""Cinco figuras exportáveis e interpretações descritivas, sem examinar o holdout."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from ml.schemas import CORE_GESTURE_CLASSES, FEATURE_NAMES


def generate_eda(records, windows, output_dir, cohort):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    figures = []

    def save(fig, name, interpretation):
        fig.suptitle(f"MotionLab — {cohort} — development only")
        fig.tight_layout()
        fig.savefig(out / f"{name}.svg", metadata={"Date": None})
        fig.savefig(out / f"{name}.png", dpi=120)
        plt.close(fig)
        figures.append({"path": f"eda/{name}.svg", "interpretation": interpretation})

    classes = Counter(w.label for w in windows)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(CORE_GESTURE_CLASSES, [classes[c] for c in CORE_GESTURE_CLASSES])
    ax.set_ylabel("Windows")
    save(fig, "01_classes", f"Janelas por classe: {dict(classes)}. Desbalanceamento exige F1-macro e suporte por classe.")

    participants = Counter(w.participant_id for w in windows)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(participants), list(participants.values()))
    ax.set_ylabel("Windows per participant")
    save(fig, "02_participants", f"{len(participants)} participantes no desenvolvimento; contagens {dict(participants)}. "
         "Janelas sobrepostas não são observações independentes; a unidade de generalização é o grupo.")

    session = records[0].session_id
    trace = [r for r in records if r.session_id == session]
    fig, ax = plt.subplots(figsize=(9, 4))
    for label in CORE_GESTURE_CLASSES:
        subset = [r for r in trace if r.label == label and r.distance_cm is not None]
        ax.scatter([r.ts_ms / 1000 for r in subset], [r.distance_cm for r in subset], s=10, label=label)
    ax.set(xlabel="Time (s)", ylabel="Distance (cm)")
    ax.legend()
    save(fig, "03_trace", f"Sessão ilustrativa {session}, {len(trace)} amostras. Rótulos vêm do cronograma solicitado; "
         "não comprovam que a pessoa executou o gesto corretamente. Inspecionar transições antes de interpretar erros.")

    counts = Counter(r.session_id for r in records)
    invalid = Counter(r.session_id for r in records if not r.valid_ultrasonic or r.distance_cm is None)
    rates = {s: invalid[s] / n for s, n in counts.items()}
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(list(rates), list(rates.values()))
    ax.tick_params(axis="x", labelrotation=75, labelsize=7)
    ax.set_ylabel("Invalid reading fraction")
    save(fig, "04_invalid", f"Fração inválida por sessão: { {s: round(v, 3) for s, v in rates.items()} }. "
         "Timeouts são tratados causalmente; alta perda pode mudar a distribuição e gerar falsos acionamentos.")

    X = np.asarray([w.features for w in windows])
    centered = X - X.mean(axis=0)
    norms = np.sqrt((centered ** 2).sum(axis=0))
    denominator = np.outer(norms, norms)
    corr = np.divide(centered.T @ centered, denominator, out=np.zeros_like(denominator), where=denominator > 0)
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(FEATURE_NAMES)), FEATURE_NAMES, rotation=75)
    ax.set_yticks(range(len(FEATURE_NAMES)), FEATURE_NAMES)
    fig.colorbar(im, ax=ax)
    pairs = [(abs(corr[i, j]), FEATURE_NAMES[i], FEATURE_NAMES[j]) for i in range(len(norms)) for j in range(i) if norms[i] and norms[j]]
    strongest = max(pairs) if pairs else (0, "nenhuma", "nenhuma")
    save(fig, "05_correlations", f"Maior correlação absoluta: {strongest[1]} × {strongest[2]} = {strongest[0]:.3f}. "
         "Redundância pode favorecer modelos compactos; correlação não estabelece causalidade. Features constantes aparecem como zero.")
    text = [f"# EDA — {cohort}", "Somente desenvolvimento; holdout reservado. Sintético/demo validam software, não desempenho físico."]
    for f in figures:
        text.extend([f"![{f['path']}]({Path(f['path']).name})", f["interpretation"]])
    (out / "interpretacao.md").write_text("\n\n".join(text) + "\n", encoding="utf-8")
    return {"scope": "development_only", "cohort": cohort, "figures": figures,
            "class_distribution": dict(classes), "participants": dict(participants), "invalid_ratio_by_session": rates}
