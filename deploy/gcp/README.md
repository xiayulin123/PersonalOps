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
| `RESEND_API_KEY` | Email verification + password reset (Resend) |
| `EMAIL_FROM` | Sender address, e.g. `PersonalOps <noreply@personalops.live>` |

Per-user OpenAI keys are stored encrypted in Postgres (B2) — not in `.env`.

## Email auth (Resend) — register verify + forgot password

Cloud registration sends a **6-digit code** before creating the account. Sign-in includes **Forgot password?** with the same code flow.

### 1. Resend account

1. Sign up at [resend.com](https://resend.com) (free tier: ~100 emails/day).
2. Create an API key → set `RESEND_API_KEY` in `deploy/gcp/.env`.
3. Add and verify domain **`personalops.live`** in Resend → **Domains**.
4. Resend shows DNS records (SPF, DKIM). Add them in **GoDaddy DNS** (same panel as your A record).
5. Wait until Resend shows domain **Verified**.

### 2. Sender address

```env
EMAIL_FROM=PersonalOps <noreply@personalops.live>
```

Until the domain is verified, you can test with Resend's sandbox sender `onboarding@resend.dev` (only delivers to your Resend account email).

### 3. Deploy

```bash
cd deploy/gcp
# edit .env — RESEND_API_KEY, EMAIL_FROM
docker compose up -d --build api web
docker compose exec api alembic upgrade head
```

### 4. API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/register/start` | Send register code |
| POST | `/auth/register/verify` | Verify code → create user + JWT |
| POST | `/auth/register/resend` | Resend code (60s cooldown) |
| POST | `/auth/forgot-password` | Send reset code |
| POST | `/auth/reset-password` | Code + new password |

Legacy `POST /auth/register` (instant, no email) only works when `RESEND_API_KEY` is empty (local tests / desktop dev).

### 5. Security notes

- Never commit `RESEND_API_KEY` (`.env` is gitignored).
- Rotate the API key if it was exposed in chat or logs.
- Codes expire in 15 minutes; max 5 wrong guesses per code.
