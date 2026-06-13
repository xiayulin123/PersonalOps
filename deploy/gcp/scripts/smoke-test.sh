#!/usr/bin/env bash
# Smoke test for PersonalOps Plan B Docker stack.
# Usage (from deploy/gcp):
#   ./scripts/smoke-test.sh
#   BASE_URL=http://203.0.113.10 ./scripts/smoke-test.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
EMAIL="${SMOKE_EMAIL:-smoke-$(date +%s)@example.com}"
PASSWORD="${SMOKE_PASSWORD:-smoke-test-password-123}"

echo "==> Health"
health="$(curl -fsS "${BASE_URL}/health")"
echo "$health" | grep -q '"deployment_mode":"cloud"' || {
  echo "Expected deployment_mode=cloud in /health"
  exit 1
}

echo "==> Register"
reg="$(curl -fsS -X POST "${BASE_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
token="$(echo "$reg" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

echo "==> Storage status"
curl -fsS "${BASE_URL}/me/storage/status" \
  -H "Authorization: Bearer ${token}" | python3 -m json.tool

echo "==> Workspaces list"
curl -fsS "${BASE_URL}/workspaces" \
  -H "Authorization: Bearer ${token}" | python3 -m json.tool

echo ""
echo "Smoke test passed for ${BASE_URL}"
