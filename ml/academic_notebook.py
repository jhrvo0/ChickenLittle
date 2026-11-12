"""Notebook executável de EDA/preparação e análise dos artefatos de um run identificado."""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import platform
from pathlib import Path


def build_notebook(run_dir, destination):
    run = Path(run_dir).resolve()
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Notebook exige experimento completo.")
    cells, namespace = [], {"RUN": run}
    # Caminho relativo à raiz quando possível: o notebook versionado não carrega caminhos da máquina.
    try:
        shown_run = run.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        shown_run = str(run)

    def markdown(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": text})

    def code(source):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(source, "motionlab_bootstrap.ipynb", "exec"), namespace)
        cells.append({"cell_type": "code", "metadata": {}, "source": source,
                      "execution_count": sum(c["cell_type"] == "code" for c in cells) + 1,
                      "outputs": [{"output_type": "stream", "name": "stdout", "text": stream.getvalue()}]})

    markdown("# MotionLab: bootstrap, preparação e avaliação agrupada\n\n"
             "Corpus exclusivamente simulado nesta demonstração. As métricas caracterizam este corpus; "
             "desempenho físico permanece PENDING. O holdout é reservado antes da EDA. "
             "Este notebook foi executado pelo gerador `python -m ml.academic_notebook`; cada saída de código vem da execução da célula. "
             "Para repetir no Jupyter, execute a partir da raiz do projeto com as dependências do lock.")
    code("from pathlib import Path\nimport os, json\n"
         f"RUN = Path(os.environ.get('MOTIONLAB_RUN_DIR', {shown_run!r}))\n"
         "manifest = json.loads((RUN / 'manifest.json').read_text(encoding='utf-8'))\n"
         "print(json.dumps({k: manifest[k] for k in ('experiment_id','cohort','dataset_sha256','samples','windows','physical_validation')}, indent=2))")
    markdown("## Leitura do bootstrap e estatísticas de desenvolvimento\n\n"
             "A unidade de independência é participante/sessão. Janelas sobrepostas ficam no mesmo grupo. "
             "Distâncias inválidas mantêm suas flags e passam pelo filtro causal; não recebem rótulos inventados. "
             "O scaler do MLP é ajustado apenas no treino de cada fold. F1 macro com quatro classes é a métrica principal; "
             "acurácia, suporte, FAR e eventos complementam a análise.")
    code("import numpy as np\nfrom ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records\n"
         "from ml.training.splitter import split_windows_grouped\n"
         "rows = load_raw_records_from_path(RUN / 'corpus.jsonl')\n"
         "windows = preprocess_records(rows)\nsplit = split_windows_grouped(windows, seed=manifest['seed'])\n"
         "dev_sessions = {w.session_id for w in split.train + split.val}\n"
         "development_rows = [r for r in rows if r.session_id in dev_sessions]\n"
         "distances = np.array([r.distance_cm for r in development_rows if r.distance_cm is not None and r.valid_ultrasonic])\n"
         "print(json.dumps({'valid_distance_count': int(distances.size), 'mean_cm': float(distances.mean()), 'std_cm': float(distances.std()), 'min_cm': float(distances.min()), 'median_cm': float(np.median(distances)), 'max_cm': float(distances.max()), 'invalid_count': sum(not r.valid_ultrasonic or r.distance_cm is None for r in development_rows), 'split': manifest['split']}, indent=2))\n"
         "assert not set(manifest['split']['test_groups']) & set(manifest['split']['train_groups'] + manifest['split']['validation_groups'])")
    markdown("## Tratamento dos dados e justificativas\n\n"
             "**Valores ausentes.** Uma leitura do HC-SR04 fora de 2–400 cm ou sem eco chega com `valid_ultrasonic=false` e "
             "`distance_cm=-1`. Não imputamos média nem mediana do corpus: isso usaria informação de outras sessões e não é "
             "reproduzível na ESP32. O filtro causal repete o último valor válido por até `max_hold_steps` amostras (falhas curtas "
             "de eco) e, depois disso, satura em `saturation_cm` (mão fora do alcance). A fração de leituras inválidas na janela "
             "vira uma feature, para o modelo saber quando o sinal está degradado.\n\n"
             "**Limpeza e ruído.** Valores fora da faixa física são tratados como ausentes. Picos isolados são removidos por "
             "mediana móvel causal de 3 amostras e o sinal é suavizado por média exponencial (EMA). Tudo é causal: a mesma "
             "sequência roda no firmware. Sessões passam por validação de ordem, duplicatas e rótulos antes do experimento.\n\n"
             "**Rótulos ambíguos.** Janelas cuja classe dominante cobre menos que `min_label_purity` (transições entre gestos) "
             "são descartadas para não ensinar rótulos misturados.\n\n"
             "**Encoding.** O IR é booleano e entra como fração 0–1 de detecções na janela. As classes viram índices inteiros "
             "na ordem fixa de `class_names`; os classificadores tratam esses índices como categorias, sem ordem.\n\n"
             "**Normalização.** Árvore, floresta e AdaBoost não dependem de escala e usam as features cruas. KNN e MLP usam "
             "`StandardScaler` dentro de um `Pipeline`, ajustado só no treino de cada fold, para não vazar estatísticas da validação.")
    code("cfg = manifest['preprocessing']\n"
         "invalid = sum(not r.valid_ultrasonic or r.distance_cm is None for r in development_rows)\n"
         "saturated = int((distances >= cfg['saturation_cm']).sum())\n"
         "print(json.dumps({'leituras_desenvolvimento': len(development_rows), 'invalidas': invalid,\n"
         "                  'fracao_invalidas': round(invalid / max(1, len(development_rows)), 4),\n"
         "                  'validas_acima_da_saturacao': saturated, 'max_hold_steps': cfg['max_hold_steps'],\n"
         "                  'saturation_cm': cfg['saturation_cm'], 'median_kernel': cfg['median_kernel'],\n"
         "                  'ema_alpha': cfg['ema_alpha'], 'min_label_purity': cfg['min_label_purity'],\n"
         "                  'janelas_de_desenvolvimento': len(split.train) + len(split.val)}, indent=2, ensure_ascii=False))")
    markdown("## Cinco visualizações interpretadas\n\nAs cinco figuras abaixo usam somente desenvolvimento e foram produzidas pelo mesmo experimento identificado acima.")
    for index, figure in enumerate(manifest["eda"]["figures"], 1):
        filename = f"figure_{index}.png"
        content = base64.b64encode((run / figure["path"]).with_suffix(".png").read_bytes()).decode()
        cells.append({"cell_type": "markdown", "metadata": {},
                      "source": f"### Figura {index}\n\n![Figura {index}](attachment:{filename})\n\n{figure['interpretation']}",
                      "attachments": {filename: {"image/png": content}}})
    markdown("## Baselines, comparação, estabilidade e limites\n\n"
             "A árvore de profundidade 1 é um baseline aprendido simples e de baixa capacidade, separado dos modelos comparados "
             "(árvore, floresta, MLP e, quando habilitados, KNN e AdaBoost). "
             "As regras são uma referência de domínio adicional, sem treino estatístico. "
             "A grade 3/5/7 da árvore é pequena, explícita e compatível com o orçamento embarcado. "
             "GroupKFold e LOGO preservam os participantes; quando os números de folds coincidem são a mesma partição, não duas evidências independentes. "
             "A CV reutilizada no tuning é descritiva. O teste externo não escolhe hiperparâmetros. "
             "Diferenças entre treino, validação e teste abaixo ajudam a investigar sobreajuste; escores baixos em todos sugerem capacidade insuficiente ou dados difíceis, sem diagnóstico causal automático.")
    code("from sklearn.metrics import f1_score\nfrom ml.training.splitter import windows_to_xy\nfrom ml.training.trainer import load_trained_bundle\n"
         "report = json.loads((RUN / 'evaluation.json').read_text(encoding='utf-8'))\n"
         "X_train, y_train = windows_to_xy(split.train)\n"
         "for name, metrics in report['models'].items():\n"
         "    bundle = load_trained_bundle(RUN / 'models' / (name + '.joblib'))\n"
         "    train_f1 = float(f1_score(y_train, bundle.estimator.predict(X_train), labels=list(range(4)), average='macro', zero_division=0))\n"
         "    cv = manifest['validation']['group_kfold']['models'][name]\n"
         "    print(json.dumps({'model': name, 'train_f1': train_f1, 'validation_f1': metrics['val_f1_macro'], 'test_f1': metrics['test_f1_macro'], 'train_minus_validation': train_f1 - metrics['val_f1_macro'], 'cv_mean': cv['f1_macro_mean'], 'cv_std': cv['f1_macro_std'], 'valid_folds': cv['valid_folds'], 'far_status': metrics['false_activation_rate_neutral_status']}, ensure_ascii=False))\n"
         "print('Tuning:', json.dumps(manifest['tuning'], ensure_ascii=False))")
    search = manifest.get("hyperparameter_search", {})
    if search.get("status") == "evaluated":
        markdown("## Otimização de hiperparâmetros\n\n"
                 f"Estratégia: **{'Grid Search' if search['method'] == 'grid' else 'Random Search'}** por família de modelo, "
                 "com GroupKFold só nos grupos de desenvolvimento. Os espaços são pequenos de propósito: o pipeline roda dentro "
                 "do Airflow com 1 CPU, e o modelo escolhido precisa caber na ESP32. Grid Search avalia todas as combinações "
                 "desses espaços; Random Search sorteia um subconjunto quando o orçamento é menor. O critério é o F1-macro médio "
                 "da CV; em empate, vence a menor diferença treino-validação. O holdout externo não participa da escolha.")
        code("search = manifest['hyperparameter_search']\n"
             "for name, family in search['models'].items():\n"
             "    print(name, '| combinações:', family.get('evaluated_combinations'), '| melhor:', family.get('best_params'),\n"
             "          '| F1 CV:', None if family.get('best_cv_f1_macro') is None else round(family['best_cv_f1_macro'], 4))")
    cv_models = manifest["validation"]["group_kfold"].get("models", {})
    if any(m.get("train_f1_macro_mean") is not None for m in cv_models.values()):
        markdown("## Estabilidade, sobreajuste e subajuste\n\n"
                 "Para cada modelo, o gráfico compara o F1 no treino de cada fold com o F1 na validação do mesmo fold, e a barra "
                 "de erro mostra o desvio entre folds. Diferença treino-validação acima de 0,10 é marcada como sobreajuste; "
                 "treino e validação abaixo de 0,60 como subajuste. São limiares do projeto, não testes estatísticos. "
                 "O KNN com pesos por distância sempre acerta o próprio treino (cada ponto é vizinho de si mesmo), então a sua "
                 "diferença mede memorização e não deve ser lida como as das árvores.")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        names = [n for n, m in cv_models.items() if m.get("train_f1_macro_mean") is not None]
        train = [cv_models[n]["train_f1_macro_mean"] for n in names]
        val = [cv_models[n]["f1_macro_mean"] for n in names]
        err = [cv_models[n]["f1_macro_std"] for n in names]
        x = np.arange(len(names))
        fig, ax = plt.subplots(figsize=(max(6, 1.2 * len(names)), 4))
        ax.bar(x - 0.2, train, 0.4, label="Treino (fold)", color="#9db4d6")
        ax.bar(x + 0.2, val, 0.4, yerr=err, capsize=3, label="Validação (fold)", color="#2f5d9a")
        ax.set_xticks(x, names, rotation=30, ha="right", fontsize=8)
        ax.set(ylim=(0, 1.05), ylabel="F1-macro")
        ax.legend(fontsize=8)
        fig.tight_layout()
        gap_stream = io.BytesIO()
        fig.savefig(gap_stream, format="png", dpi=100)
        plt.close(fig)
        cells.append({"cell_type": "markdown", "metadata": {}, "source": "![Treino vs validação](attachment:fit_gap.png)",
                      "attachments": {"fit_gap.png": {"image/png": base64.b64encode(gap_stream.getvalue()).decode()}}})
        code("for name, model in manifest['validation']['group_kfold']['models'].items():\n"
             "    if model.get('train_f1_macro_mean') is not None:\n"
             "        print(f\"{name:24s} treino={model['train_f1_macro_mean']:.3f} validação={model['f1_macro_mean']:.3f}\"\n"
             "              f\" ±{model['f1_macro_std']:.3f} diferença={model['generalization_gap']:+.3f} → {model['fit_diagnosis']}\")")
    markdown("## Matrizes de confusão e comparação dos modelos\n\nLinhas são rótulos conhecidos no cenário simulado; colunas são previsões. Fora da diagonal estão os erros observados. As métricas de teste são descritivas desta execução reservada.")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    report = json.loads((run / "evaluation.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, len(report["models"]), figsize=(4 * len(report["models"]), 4))
    for ax, (name, metrics) in zip(axes, report["models"].items()):
        ax.imshow(metrics["confusion_matrix"], cmap="Blues")
        ax.set_title(name, fontsize=9)
        ax.set(xlabel="Previsto", ylabel="Rótulo do simulador")
        for i, row in enumerate(metrics["confusion_matrix"]):
            for j, value in enumerate(row):
                ax.text(j, i, str(value), ha="center", va="center", fontsize=8)
    fig.tight_layout()
    image_stream = io.BytesIO()
    fig.savefig(image_stream, format="png", dpi=100)
    plt.close(fig)
    cells.append({"cell_type": "markdown", "metadata": {}, "source": "![Matrizes](attachment:models.png)",
                  "attachments": {"models.png": {"image/png": base64.b64encode(image_stream.getvalue()).decode()}}})
    markdown("## Rastreabilidade e interpretação crítica\n\n"
             "Examinar a classe com menor recall e as confusões recorrentes, além de F1 agregado. "
             "A proximidade entre regras e modelos no simulador pode refletir o próprio gerador; não comprova vantagem de ML em pessoas reais. "
             "Desvio entre folds não é intervalo de confiança. A seleção usa validação e estimativas de memória; "
             "a latência é medida em Python no host do experimento. Não há benchmark físico. "
             "O run MLflow abaixo contém parâmetros, modelos e artefatos desta execução.")
    code("for name, metrics in report['models'].items():\n"
         "    weakest = min(metrics['per_class'].items(), key=lambda item: item[1]['recall'])\n"
         "    print(name, 'menor recall:', weakest[0], weakest[1])\n"
         "print(json.dumps(manifest['tracking'], indent=2))")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": platform.python_version()},
        "motionlab": {"experiment_id": manifest["experiment_id"], "dataset_sha256": manifest["dataset_sha256"], "cohort": manifest["cohort"],
                      "execution_engine": "python_exec", "experiment_python": manifest["environment"]["python"]}},
        "cells": [{"id": f"motionlab-{i}", **cell} for i, cell in enumerate(cells)]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--output", default="notebooks/motionlab_bootstrap.ipynb")
    args = parser.parse_args()
    print(build_notebook(args.run_dir, args.output))


if __name__ == "__main__":
    main()
