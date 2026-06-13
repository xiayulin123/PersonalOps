#!/usr/bin/env bash
# Open PersonalOps backend + desktop in separate Terminal windows (macOS).
#
# Usage:
#   ./scripts/dev.sh
#   PERSONALOPS_CONDA_ENV=py311 ./scripts/dev.sh
#
# Requires: macOS Terminal.app, conda env with API deps, npm deps in desktop/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_DIR="${ROOT}/apps/api"
DESKTOP_DIR="${ROOT}/apps/desktop"
CONDA_ENV="${PERSONALOPS_CONDA_ENV:-py311}"

BACKEND_LAUNCHER="${SCRIPT_DIR}/run-backend.sh"
FRONTEND_LAUNCHER="${SCRIPT_DIR}/run-frontend.sh"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "dev.sh currently supports macOS only (uses Terminal.app)."
  echo "Run manually:"
  echo "  Backend:  ${BACKEND_LAUNCHER}"
  echo "  Frontend: ${FRONTEND_LAUNCHER}"
  exit 1
fi

if [[ ! -d "${API_DIR}" || ! -d "${DESKTOP_DIR}" ]]; then
  echo "Could not find apps/api or apps/desktop under ${ROOT}"
  exit 1
fi

chmod +x "${BACKEND_LAUNCHER}" "${FRONTEND_LAUNCHER}"

# Use small launcher scripts so AppleScript does not need fragile quote escaping.
osascript \
  -e 'tell application "Terminal" to activate' \
  -e "tell application \"Terminal\" to do script \"export PERSONALOPS_CONDA_ENV='${CONDA_ENV}'; bash '${BACKEND_LAUNCHER}'\"" \
  -e 'delay 0.4' \
  -e "tell application \"Terminal\" to do script \"bash '${FRONTEND_LAUNCHER}'\""

echo "Started backend and desktop in separate Terminal windows."
