#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/app"

export CUDA_HOME=/opt/wetop/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export PYTHONEXE="$project_root/.venv/bin/python"
export LD_LIBRARY_PATH="/opt/wetop/native:$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES PRIVACY_CONSENT=N RAY_ADDRESS=local
export PYTHONUNBUFFERED=1

printf "Starting GenManip on http://127.0.0.1:18087 (initial startup may take about a minute)...\n"
exec /isaac-sim/python.sh ray_eval_server.py --host 127.0.0.1 --port 18087 "$@"
