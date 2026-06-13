# PersonalOps Plan B — GCP / Docker Deploy (B5)

Run the **cloud edition** on a VM with **Postgres + FastAPI + nginx + GCS**.

## Architecture

```
Browser → nginx (web:8080) → static React (VITE_EDITION=cloud)
                          → proxy /auth, /workspaces, … → api:8000
                          → Postgres (db)
                          → GCS bucket (files + conversation backups)
                          → /data volume (Chroma cache + temp uploads)
```

Chat history and workspaces live in **Postgres**. GCS is for file blobs and conversation JSONL backups (B3/B4).

## Quick start (local Docker test)

```bash
cd personalops/deploy/gcp
cp env.example .env
# Edit .env — set POSTGRES_PASSWORD, JWT_SECRET, GCS_SA_FILE path

mkdir -p secrets
# Copy your GCS service account JSON:
# cp /path/to/gcs-archive-sa.json secrets/gcs-archive-sa.json

docker compose up -d --build
docker compose logs -f api
```

Open **http://localhost** (or `HTTP_PORT` from `.env`).

### Bootstrap admin (first time)

```bash
docker compose exec api python -m personalops_cli admin bootstrap
```

Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`, add your OpenAI key in **Settings**, then upload a file and chat.

### Smoke test

```bash
chmod +x scripts/smoke-test.sh
./scripts/smoke-test.sh
```

## GCP VM (production outline)

1. **Create VM** — e2-medium (4 GB), Ubuntu 22.04, allow HTTP/HTTPS.
2. **Install Docker** — `docker compose` plugin.
3. **Clone repo** and configure `deploy/gcp/.env`.
4. **GCS** — bucket `personalops-personal`; attach SA with `roles/storage.objectAdmin`.
5. **Copy SA JSON** to `deploy/gcp/secrets/gcs-archive-sa.json`.
6. **Start stack** — `docker compose up -d --build`.
7. **HTTPS** — point DNS to VM; use Caddy or certbot + nginx (see below).
8. **OAuth** — add `https://app.yourdomain.com/oauth/*/callback` in Google/Microsoft consoles; set env vars in `.env`.

## HTTPS (certbot outline)

For production, terminate TLS in front of the `web` container:

- Option A: **Caddy** reverse proxy on host → `localhost:80`
- Option B: Mount Let's Encrypt certs into a custom nginx config on port 443

Update Life OAuth redirect URIs to `https://your-domain/oauth/...`.

## Useful commands

```bash
# Logs
docker compose logs -f api web db

# Migrations (also run automatically on API startup)
docker compose exec api alembic upgrade head

# Backfill conversation exports to GCS
docker compose exec api python -m personalops_cli admin export-conversations

# Restore conversations from GCS
docker compose exec api python -m personalops_cli admin restore-conversations --dry-run
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `postgres-data` | Users, workspaces, messages, credentials |
| `app-data` | Chroma vector cache, temp local upload paths |

VM disk loss: Postgres volume backup + GCS files/conversations; Chroma can be rebuilt by re-indexing from GCS.

## Environment reference

See `env.example`. Critical vars:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_PASSWORD` | DB password |
| `JWT_SECRET` | Auth tokens |
| `GCS_APP_BUCKET` | Object storage bucket |
| `GCS_SA_FILE` | Host path to SA JSON (mounted read-only) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First admin bootstrap |

Per-user OpenAI keys are stored encrypted in Postgres (B2) — not in `.env`.
