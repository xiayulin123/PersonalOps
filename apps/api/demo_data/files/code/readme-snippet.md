# PersonalOps API

FastAPI backend for workspaces, file indexing, chat, and study tools.

## Local development

```bash
cd personalops/apps/api
uvicorn main:app --reload --port 8000
```

## Key modules

- `routers/` — HTTP endpoints
- `services/indexer.py` — Chroma embeddings
- `services/study/` — S1 study workspace features

## Deployment

Cloud edition uses Postgres + GCS + LangGraph chat only.
