import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from schema import HealthOut

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
    force=True,
)
logging.getLogger("personalops.agent").setLevel(logging.INFO)
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — register ORM tables with Base.metadata
from db_migrate import run_migrations
from routers import (
    auth,
    chat,
    files,
    github,
    life_plugins,
    me,
    memory,
    metrics,
    oauth_pages,
    personalization,
    study,
    templates,
    tools,
    watcher,
    workspaces,
)
from config import settings
from services.deployment import is_cloud_deployment
from services import folder_watcher
from routers.files import reset_stale_ocr_files
from services.cursor_agent.bridge import start_cursor_bridge, stop_cursor_bridge
from services.life.life_poller import start_life_poller, stop_life_poller
from services.personalization.scheduler import start_personalization_scheduler

logger = logging.getLogger(__name__)


async def _maybe_seed_demo_account() -> None:
    from database import SessionLocal
    from services.demo.bootstrap_demo import bootstrap_demo

    try:
        async with SessionLocal() as db:
            result = await bootstrap_demo(db, force=False, index_files=False)
        if result.warnings:
            logger.info("Demo auto-seed: %s", "; ".join(result.warnings))
        else:
            logger.info("Demo account ready: %s", result.email)
    except Exception as exc:
        logger.warning("Demo auto-seed skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    if settings.demo_auto_seed:
        await _maybe_seed_demo_account()
    # Watch-folder full scans can index many files — never block HTTP startup.
    asyncio.create_task(folder_watcher.start_all_from_db())
    if not is_cloud_deployment():
        asyncio.create_task(start_cursor_bridge())
    else:
        logger.info("Cloud deployment — Cursor Agent bridge skipped (LangGraph only)")
    start_life_poller()
    start_personalization_scheduler()
    logger.info("PersonalOps API startup complete — accepting requests")
    yield
    stop_life_poller()
    if not is_cloud_deployment():
        await stop_cursor_bridge()
    folder_watcher.stop_all_watchers()


app = FastAPI(title="PersonalOps API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(workspaces.router)
app.include_router(files.router)
app.include_router(memory.router)
app.include_router(tools.router)
app.include_router(templates.router)
app.include_router(chat.router)
app.include_router(github.router)
app.include_router(watcher.router)
app.include_router(metrics.router)
app.include_router(life_plugins.router)
app.include_router(personalization.router)
app.include_router(study.router)
app.include_router(oauth_pages.router)


@app.get("/health", response_model=HealthOut)
def health():
    from services.health_check import build_health_payload

    return build_health_payload()
