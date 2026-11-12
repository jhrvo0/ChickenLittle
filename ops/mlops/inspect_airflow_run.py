"""Consulta somente leitura de um run identificado no banco persistente do Airflow."""
import json
import os
from pathlib import Path
import sqlite3
import sys

database = (Path(os.environ["AIRFLOW_HOME"]) / "airflow.db").as_posix()
connection = sqlite3.connect("file:" + database + "?mode=ro", uri=True)
row = connection.execute("select state from dag_run where dag_id=? and run_id=?", ("motionlab_experiment", sys.argv[1])).fetchone()
tasks = connection.execute("select task_id,state from task_instance where dag_id=? and run_id=?", ("motionlab_experiment", sys.argv[1])).fetchall()
print(json.dumps({"run_id": sys.argv[1], "state": row[0] if row else None, "tasks": dict(tasks)}))
connection.close()
