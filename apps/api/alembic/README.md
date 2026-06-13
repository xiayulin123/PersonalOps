# PersonalOps Database Migrations (Alembic)

Phase 3.1 replaces `Base.metadata.create_all()` with versioned schema migrations.

## On API startup

`main.py` calls `run_migrations()` which:

1. If `workspaces` exists but Alembic has **no revision** → `stamp head` (legacy Phase 0–2 DB)
2. Otherwise → `alembic upgrade head`

## Manual commands

Run from `personalops/apps/api` with `conda activate py311`:

```bash
# Apply all pending migrations
alembic upgrade head

# Show current revision
alembic current

# Create a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"
alembic upgrade head

# Mark existing DB as up-to-date without running SQL (legacy DB only)
alembic stamp head
```

## Adding a Phase 3+ table

1. Edit `models.py`
2. `alembic revision --autogenerate -m "add watch_folders"`
3. Review the generated file in `alembic/versions/`
4. `alembic upgrade head`
