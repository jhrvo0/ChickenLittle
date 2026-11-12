#!/usr/bin/env bash
set -euo pipefail
airflow db migrate
# Tasks reais no runtime Airflow, sem manter scheduler/UI na RAM.
airflow dags test motionlab_experiment --conf '{"cohort":"demo"}'
