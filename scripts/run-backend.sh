#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="${SCRIPT_DIR}/../apps/api"
CONDA_ENV="${PERSONALOPS_CONDA_ENV:-py311}"

cd "${API_DIR}"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

echo "[PersonalOps] Backend: http://localhost:8000"
exec uvicorn main:app --reload --port 8000
