"""Falha real de DAG: configuração inválida não substitui modelo publicado."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

root = Path(os.environ.get("MOTIONLAB_DATA_ROOT", "/workspace/data"))
pointer = root / "pipeline/deployment.json"
before = hashlib.sha256(pointer.read_bytes()).hexdigest()
result = subprocess.run(["airflow", "dags", "test", "motionlab_experiment", "--conf", json.dumps({"cohort": "invalid"})], capture_output=True, text=True)
(root / "pipeline/airflow-invalid.log").write_text(result.stdout + result.stderr, encoding="utf-8")
connection = sqlite3.connect(Path(os.environ["AIRFLOW_HOME"]) / "airflow.db")
row = connection.execute("select run_id,state from dag_run where dag_id=? order by id desc limit 1", ("motionlab_experiment",)).fetchone()
tasks = connection.execute("select task_id,state from task_instance where dag_id=? and run_id=?", ("motionlab_experiment", row[0])).fetchall()
connection.close()
after = hashlib.sha256(pointer.read_bytes()).hexdigest()
passed = row[1] == "failed" and dict(tasks).get("configuration") == "failed" and before == after
evidence = {"status": "passed" if passed else "failed", "cli_exit_code": result.returncode,
            "dag_run_id": row[0], "dag_state": row[1], "tasks": dict(tasks), "deployment_unchanged": before == after}
(root / "pipeline/airflow-failure-drill.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
print(json.dumps(evidence))
sys.exit(0 if passed else 1)
