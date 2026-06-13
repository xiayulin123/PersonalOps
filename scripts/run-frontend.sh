#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="${SCRIPT_DIR}/../apps/desktop"

cd "${DESKTOP_DIR}"

echo "[PersonalOps] Desktop: Tauri dev"
exec npm run tauri dev
