"""Apply Alembic migrations programmatically (used on API startup)."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from config import settings


def _current_revision(engine) -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def run_migrations() -> None:
    api_dir = Path(__file__).resolve().parent
    os.chdir(api_dir)

    alembic_cfg = Config(str(api_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_dir / "alembic"))

    engine = create_engine(settings.sync_database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        current_rev = _current_revision(engine)
    finally:
        engine.dispose()

    # Phase 0–2 DBs were created with Base.metadata.create_all().
    # If app tables exist but Alembic has no revision recorded, stamp baseline.
    if "workspaces" in tables and current_rev is None:
        command.stamp(alembic_cfg, "head")
        return

    command.upgrade(alembic_cfg, "head")
