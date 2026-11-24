#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/app"

exec "$project_root/.venv/bin/python" -m genmanip_client submit \
  scientific_experiments/task_01_pour_flask_to_cylinder/validation/mixed/mixed_1.yml \
  --host 127.0.0.1 --port 18087 --run_id wetop_task_01
