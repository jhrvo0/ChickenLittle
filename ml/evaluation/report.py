"""Geração de relatórios comparativos estruturados em JSON e Markdown."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Sequence

from ml.evaluation.metrics import (
    evaluate_classification_metrics,
    evaluate_event_level,
)
from ml.schemas import CORE_GESTURE_CLASSES, StabilizerConfig, WindowSample
from ml.training.splitter import windows_to_xy
from ml.training.trainer import TrainedBundle, select_best_embeddable_bundle


def generate_evaluation_report(
    bundles: dict[str, TrainedBundle],
    test_windows: Sequence[WindowSample],
    stabilizer_config: StabilizerConfig | None = None,
) -> dict[str, Any]:
    """Gera um dicionário completo de avaliação estatística, latência, footprint e eventos."""
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    if not bundles or not test_windows:
        raise ValueError("Avaliação requer modelos e janelas de teste; sem dados, o estado é pendente.")

    # Determinação rigorosa de integridade experimental
    all_origins = set()
    for w in test_windows:
        all_origins.add(w.data_origin)
    for b in bundles.values():
        all_origins.update(b.data_origins)

    has_synthetic = any(o != "real_hardware" for o in all_origins)
    exp_status = (
        "AWAITING_REAL_DATA" if has_synthetic else "EVALUATED_ON_REAL_DATA"
    )

    synthetic_disclaimer = (
        "AVISO DE DADOS SINTÉTICOS: O conjunto de dados contém amostras geradas por simulador "
        "('synthetic_simulator'). O status experimental é estritamente 'AWAITING_REAL_DATA'. "
        "Estes resultados validam unicamente a integridade funcional do pipeline, das regras causais "
        "e do código de inferência/estabilização, NÃO constituindo evidência de desempenho em hardware real."
        if has_synthetic
        else ""
    )

    first_bundle = next(iter(bundles.values())) if bundles else None
    split_strategy = first_bundle.split_strategy if first_bundle else "unknown"
    split_warnings = list(first_bundle.split_warnings) if first_bundle else []

    test_participants = sorted({w.participant_id for w in test_windows})
    test_sessions = sorted({w.session_id for w in test_windows})

    models_report: dict[str, Any] = {}

    for name, bundle in bundles.items():
        X_test, y_test = windows_to_xy(test_windows, class_names=bundle.class_names)
        cls_metrics = evaluate_classification_metrics(
            bundle.estimator,
            X_test,
            y_test,
            class_names=bundle.class_names,
        )
        evt_metrics = evaluate_event_level(
            bundle.estimator,
            test_windows,
            class_names=bundle.class_names,
            stabilizer_config=stabilizer_config,
        )

        models_report[name] = {
            "model_name": name,
            "val_f1_macro": round(float(bundle.val_f1_macro), 4),
            "test_f1_macro": cls_metrics["f1_macro"],
            "accuracy": cls_metrics["accuracy"],
            "false_activation_rate_neutral": cls_metrics["false_activation_rate_neutral"],
            "neutral_support": cls_metrics.get("neutral_support", 0),
            "false_activation_rate_neutral_status": cls_metrics.get("false_activation_rate_neutral_status", "pending"),
            "latency_mean_ms": cls_metrics["latency_mean_ms"],
            "latency_p95_ms": cls_metrics["latency_p95_ms"],
            "latency_scope": "notebook_python",
            "memory": cls_metrics["memory"],
            "memory_scope": "estimated_esp32",
            "per_class": cls_metrics["per_class"],
            "confusion_matrix": cls_metrics["confusion_matrix"],
            "event_level": evt_metrics,
        }

    best_bundle = select_best_embeddable_bundle(bundles) if bundles else None
    best_name = best_bundle.model_name if best_bundle else "none"

    recommendation_reason = (
        f"O modelo '{best_name}' foi selecionado pelas métricas de validação e estimativas de memória. "
        "O teste não determina a escolha. Custos embarcados são estimados; latência é medida no notebook. "
        "Generalização física e custo na ESP32 precisam de validação independente."
    )

    return {
        "generated_at_iso": now_iso,
        "experimental_status": exp_status,
        "is_synthetic": has_synthetic,
        "synthetic_disclaimer": synthetic_disclaimer,
        "dataset_summary": {
            "total_test_windows": len(test_windows),
            "test_participants_count": len(test_participants),
            "test_participants": test_participants,
            "test_sessions_count": len(test_sessions),
            "test_sessions": test_sessions,
            "split_strategy": split_strategy,
            "warnings": split_warnings,
        },
        "recommended_model": best_name,
        "recommendation_reason": recommendation_reason,
        "models": models_report,
    }


def format_evaluation_markdown(report: dict[str, Any]) -> str:
    """Formata os dados do relatório em documento Markdown de alta legibilidade."""
    lines: list[str] = []
    lines.append("# Relatório de Avaliação e Validação de Classificadores (MotionPet)\n")

    # Banner de status experimental
    if report.get("is_synthetic"):
        lines.append("> [!WARNING]")
        lines.append("> **STATUS EXPERIMENTAL: AWAITING_REAL_DATA**")
        lines.append(f"> {report.get('synthetic_disclaimer')}\n")
    else:
        lines.append("> [!NOTE]")
        lines.append("> **STATUS EXPERIMENTAL: EVALUATED_ON_REAL_DATA**")
        lines.append("> Avaliação executada integralmente sobre dados coletados em hardware real.\n")

    # Resumo do dataset e partição
    ds = report.get("dataset_summary", {})
    lines.append("## 1. Resumo do Particionamento e Integridade Anti-Vazamento\n")
    lines.append(f"- **Estratégia de Partição**: `{ds.get('split_strategy', 'N/A')}`")
    lines.append(f"- **Janelas de Teste**: `{ds.get('total_test_windows', 0)}`")
    lines.append(f"- **Participantes no Teste**: `{ds.get('test_participants_count', 0)}` ({', '.join(ds.get('test_participants', [])) or 'nenhum'})")
    lines.append(f"- **Sessões no Teste**: `{ds.get('test_sessions_count', 0)}`")

    warnings = ds.get("warnings", [])
    if warnings:
        lines.append("\n**Avisos e Limitações do Particionamento:**")
        for w in warnings:
            lines.append(f"- :warning: {w}")
    lines.append("")

    # Tabela comparativa dos 4 modelos
    lines.append("## 2. Comparativo Global de Modelos\n")
    lines.append("| Modelo | Val F1 | Test F1 | Acurácia | FAR Neutro | Latência Méd (ms) | Latência P95 (ms) | Flash ESP32 (B) | SRAM ESP32 (B) | Event F1 |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    models = report.get("models", {})
    def far_text(m):
        if m.get("false_activation_rate_neutral_status") == "pending_no_neutral_samples":
            return "não estimável (sem neutros)"
        return f"{m.get('false_activation_rate_neutral', 0.0):.4f}"

    for name, m in models.items():
        mem = m.get("memory", {})
        evt = m.get("event_level", {})
        lines.append(
            f"| `{name}` | {m.get('val_f1_macro', 0.0):.4f} | {m.get('test_f1_macro', 0.0):.4f} | "
            f"{m.get('accuracy', 0.0):.4f} | {far_text(m)} | "
            f"{m.get('latency_mean_ms', 0.0):.3f} | {m.get('latency_p95_ms', 0.0):.3f} | "
            f"{mem.get('estimated_esp32_flash_bytes', 0)} | {mem.get('estimated_esp32_sram_bytes', 0)} | "
            f"{evt.get('event_f1', 0.0):.4f} |"
        )
    lines.append("")

    # Recomendação para o ESP32
    rec_model = report.get("recommended_model", "N/A")
    lines.append("## 3. Modelo Recomendado para Embarque no ESP32\n")
    lines.append(f"> [!TIP]")
    lines.append(f"> **Modelo Selecionado**: `{rec_model}`\n>")
    lines.append(f"> {report.get('recommendation_reason', '')}\n")

    # Detalhamento de cada modelo
    lines.append("## 4. Análise Detalhada por Modelo\n")
    for name, m in models.items():
        lines.append(f"### Modelo: `{name}`\n")
        lines.append(f"- **F1-Macro (Teste)**: `{m.get('test_f1_macro', 0.0):.4f}` | **Acurácia**: `{m.get('accuracy', 0.0):.4f}`")
        lines.append(f"- **Taxa de Falsa Ativação (FAR Neutro)**: `{far_text(m)}`")
        lines.append(f"- **Latência**: Média `{m.get('latency_mean_ms', 0.0):.3f} ms` | P95 `{m.get('latency_p95_ms', 0.0):.3f} ms`\n")

        # Métricas por classe
        lines.append("#### Desempenho por Classe (Janelas)")
        lines.append("| Classe | Precisão | Revocação (Recall) | F1-Score | Suporte |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        per_class = m.get("per_class", {})
        for cname, p_data in per_class.items():
            lines.append(
                f"| `{cname}` | {p_data.get('precision', 0.0):.4f} | {p_data.get('recall', 0.0):.4f} | "
                f"{p_data.get('f1', 0.0):.4f} | {p_data.get('support', 0)} |"
            )
        lines.append("")

        # Matriz de Confusão
        lines.append("#### Matriz de Confusão (Linhas = Real, Colunas = Previsto)")
        cm = m.get("confusion_matrix", [])
        c_names = list(per_class.keys()) if per_class else list(CORE_GESTURE_CLASSES)
        header = "| Real \\ Prev | " + " | ".join(f"`{c}`" for c in c_names) + " |"
        sep = "| :--- | " + " | ".join([":---:"] * len(c_names)) + " |"
        lines.append(header)
        lines.append(sep)
        for idx, row in enumerate(cm):
            r_name = c_names[idx] if idx < len(c_names) else f"C{idx}"
            row_str = " | ".join(str(val) for val in row)
            lines.append(f"| `{r_name}` | {row_str} |")
        lines.append("")

        # Métricas de eventos contínuos
        evt = m.get("event_level", {})
        lines.append("#### Qualidade em Nível de Eventos Contínuos (com Estabilizador)")
        lines.append(f"- **Episódios Reais Ativos**: `{evt.get('true_episodes', 0)}`")
        lines.append(f"- **Episódios Corretamente Detectados**: `{evt.get('matched_episodes', 0)}`")
        lines.append(f"- **Ativações Duplicadas (Mesmo Gesto)**: `{evt.get('duplicate_activations', 0)}`")
        lines.append(f"- **Falsos Alarmes (Neutro/Gesto Invertido)**: `{evt.get('false_activations', 0)}`")
        lines.append(f"- **Janelas Rejeitadas pelo Estabilizador**: `{evt.get('rejected_windows', 0)}`")
        lines.append(f"- **Precisão de Evento**: `{evt.get('event_precision', 0.0):.4f}`")
        lines.append(f"- **Revocação de Evento (Recall)**: `{evt.get('event_recall', 0.0):.4f}`")
        lines.append(f"- **F1 de Evento**: `{evt.get('event_f1', 0.0):.4f}`\n")
        lines.append("---\n")

    return "\n".join(lines)


def save_evaluation_json(report: dict[str, Any], path: str | Path) -> Path:
    """Grava o relatório estruturado em formato JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def save_evaluation_markdown(
    report: dict[str, Any] | str,
    path: str | Path,
) -> Path:
    """Grava o relatório formatado em Markdown."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    md_content = report if isinstance(report, str) else format_evaluation_markdown(report)
    out.write_text(md_content, encoding="utf-8")
    return out
