"""Airflow real: snapshot validado → preparação/treino/MLflow → publicação explícita."""
from datetime import datetime, timezone

from airflow.sdk import dag, task, get_current_context


PYTHON = "/opt/airflow/motionlab-venv/bin/python"


@dag(schedule="@daily", start_date=datetime(2026, 11, 10, tzinfo=timezone.utc), catchup=False,
     max_active_runs=1, tags=["motionlab", "academic"])
def motionlab_experiment():
    @task
    def configuration():
        import os
        conf = get_current_context()["dag_run"].conf or {}
        cohort = conf.get("cohort", "demo")
        if cohort not in ("real", "synthetic", "demo"):
            raise ValueError("cohort inválida")
        return {"cohort": cohort, "data_root": os.environ.get("MOTIONLAB_DATA_ROOT", "/workspace/data"),
                "airflow_run_id": get_current_context()["dag_run"].run_id}

    @task.external_python(python=PYTHON, expect_airflow=False)
    def prepare(spec):
        import json
        import shutil
        from pathlib import Path
        from uuid import uuid4
        from ml.experiment import validate_corpus, dataset_digest
        from ml.preprocessing.windowing import load_raw_records_from_path, preprocess_records, save_windows_csv
        root = Path(spec["data_root"])
        source = root / "raw" / spec["cohort"]
        snapshot = root / "pipeline/snapshots" / uuid4().hex
        snapshot.mkdir(parents=True)
        for path in sorted(source.glob("*.jsonl")):
            shutil.copyfile(path, snapshot / path.name)
        rows = load_raw_records_from_path(snapshot)
        quality = validate_corpus(rows, spec["cohort"])
        if len({r.participant_id for r in rows}) < 5:
            raise ValueError("Demonstração acadêmica exige ao menos cinco grupos independentes.")
        windows = preprocess_records(rows)
        save_windows_csv(windows, snapshot.parent / (snapshot.name + "-windows.csv"))
        (snapshot / "preparation.json").write_text(json.dumps({"dataset_sha256": dataset_digest(rows),
            "samples": len(rows), "windows": len(windows), "sessions": quality}), encoding="utf-8")
        return {**spec, "raw_dir": str(snapshot)}

    @task.external_python(python=PYTHON, expect_airflow=False)
    def experiment(spec):
        import os
        from ml.experiment import run_experiment
        from ml.training.models import TrainingConfig
        from pathlib import Path
        run = run_experiment(spec["raw_dir"], cohort=spec["cohort"],
                             output_root=str(Path(spec["data_root"]) / "experiments"),
                             leave_one_out=True, tune=True,
                             training_config=TrainingConfig(include_learned_baseline=True),
                             orchestration={"engine": "apache_airflow", "dag_id": "motionlab_experiment", "run_id": spec["airflow_run_id"]},
                             tracking_uri=os.environ.get("MLFLOW_TRACKING_URI"))
        return {**spec, "run_dir": str(run)}

    @task.external_python(python=PYTHON, expect_airflow=False)
    def publish(spec):
        from pathlib import Path
        from ml.deployment import publish_experiment
        root = Path(spec["data_root"])
        if spec["cohort"] != "demo":
            return {"status": "promotion_requires_operator", "run_dir": spec["run_dir"]}
        return publish_experiment(spec["run_dir"], root / "pipeline/deployment.json", root / "experiments")

    publish(experiment(prepare(configuration())))


motionlab_experiment()
