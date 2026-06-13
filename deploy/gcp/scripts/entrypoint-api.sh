#!/bin/sh
set -eu

echo "PersonalOps API entrypoint — waiting for database..."

if [ -n "${DATABASE_URL:-}" ]; then
  python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

from config import settings

url = settings.sync_database_url
if not url.startswith("postgresql"):
    sys.exit(0)

engine = create_engine(url, pool_pre_ping=True)
for attempt in range(1, 31):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready.")
        sys.exit(0)
    except Exception as exc:
        print(f"DB not ready (attempt {attempt}/30): {exc}")
        time.sleep(2)
print("Database did not become ready in time.", file=sys.stderr)
sys.exit(1)
PY
fi

exec "$@"
