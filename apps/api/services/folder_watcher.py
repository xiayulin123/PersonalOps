from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import settings
from database import SessionLocal
from models import File, WatchFolder

logger = logging.getLogger(__name__)

WATCHED_DIR_NAME = "_watched"
_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "dist", "target"}
_BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".ico",
    ".mp3",
    ".mp4",
    ".wav",
}

_observers: dict[str, Observer] = {}
_handlers: dict[str, "DebouncedWatchHandler"] = {}
_start_lock = threading.Lock()


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _file_hash(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_ingest(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.startswith("."):
        return False
    ext = path.suffix.lower()
    if ext in _BINARY_EXTENSIONS:
        return False
    return True


def _watched_dest_path(workspace_id: str, watch_root: Path, src_path: Path) -> Path:
    rel = src_path.resolve().relative_to(watch_root.resolve())
    return Path(settings.uploads_dir) / workspace_id / WATCHED_DIR_NAME / rel


def _watched_filename(watch_root: Path, src_path: Path) -> str:
    rel = src_path.resolve().relative_to(watch_root.resolve())
    return f"{WATCHED_DIR_NAME}/{rel.as_posix()}"


class DebouncedWatchHandler(FileSystemEventHandler):
    def __init__(self, workspace_id: str, watch_path: str) -> None:
        self.workspace_id = workspace_id
        self.watch_root = Path(watch_path).resolve()
        self.debounce_sec = settings.watcher_debounce_sec
        self._pending: dict[str, threading.Timer] = {}
        self._hashes: dict[str, str] = {}
        self._lock = threading.Lock()

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        self._schedule(event.dest_path)

    def _schedule(self, src_path: str) -> None:
        src = Path(src_path)
        if not _should_ingest(src):
            return
        try:
            src.resolve().relative_to(self.watch_root)
        except ValueError:
            return

        with self._lock:
            existing = self._pending.get(src_path)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                self.debounce_sec,
                self._process,
                args=[src_path],
            )
            self._pending[src_path] = timer
            timer.daemon = True
            timer.start()

    def _process(self, src_path: str) -> None:
        with self._lock:
            self._pending.pop(src_path, None)

        try:
            asyncio.run(
                ingest_watched_file(
                    self.workspace_id,
                    str(self.watch_root),
                    src_path,
                    content_hashes=self._hashes,
                )
            )
        except Exception:
            logger.exception(
                "Failed to ingest watched file %s for workspace %s",
                src_path,
                self.workspace_id,
            )


async def ingest_watched_file(
    workspace_id: str,
    watch_root: str,
    src_path: str,
    *,
    content_hashes: dict[str, str] | None = None,
) -> File | None:
    watch_root_path = Path(watch_root).resolve()
    source_path = Path(src_path).resolve()

    if not _should_ingest(source_path):
        return None

    try:
        source_path.relative_to(watch_root_path)
    except ValueError:
        return None

    if not source_path.is_file():
        return None

    file_hash = _file_hash(source_path)
    hash_key = str(source_path)
    if content_hashes is not None and content_hashes.get(hash_key) == file_hash:
        return None
    if content_hashes is not None:
        content_hashes[hash_key] = file_hash

    dest_path = _watched_dest_path(workspace_id, watch_root_path, source_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, dest_path)

    filename = _watched_filename(watch_root_path, source_path)
    dest_str = str(dest_path)

    async with SessionLocal() as db:
        result = await db.execute(
            select(File).where(
                File.workspace_id == workspace_id,
                File.path == dest_str,
            )
        )
        file_record = result.scalar_one_or_none()
        if file_record is None:
            file_record = File(
                workspace_id=workspace_id,
                filename=filename,
                path=dest_str,
                status="pending",
                chunk_count=0,
            )
            db.add(file_record)
        else:
            file_record.filename = filename
            file_record.status = "pending"
            file_record.chunk_count = 0

        watch_result = await db.execute(
            select(WatchFolder).where(WatchFolder.workspace_id == workspace_id)
        )
        watch_record = watch_result.scalar_one_or_none()
        if watch_record is not None:
            watch_record.last_scan_at = _utcnow_naive()

        await db.commit()
        await db.refresh(file_record)
        file_id = file_record.id

    from routers.files import run_indexing

    await run_indexing(file_id)

    async with SessionLocal() as db:
        refreshed = await db.get(File, file_id)
        return refreshed


async def scan_watch_folder(workspace_id: str, watch_path: str) -> int:
    watch_root = Path(watch_path).resolve()
    if not watch_root.is_dir():
        return 0

    handler = _handlers.get(workspace_id)
    content_hashes = handler._hashes if handler is not None else {}

    ingested = 0
    for root, dirnames, filenames in os.walk(watch_root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _SKIP_DIR_NAMES and not name.startswith(".")
        ]
        for filename in filenames:
            src = Path(root) / filename
            record = await ingest_watched_file(
                workspace_id,
                str(watch_root),
                str(src),
                content_hashes=content_hashes,
            )
            if record is not None:
                ingested += 1

    async with SessionLocal() as db:
        result = await db.execute(
            select(WatchFolder).where(WatchFolder.workspace_id == workspace_id)
        )
        watch_record = result.scalar_one_or_none()
        if watch_record is not None:
            watch_record.last_scan_at = _utcnow_naive()
            await db.commit()

    return ingested


def stop_watcher(workspace_id: str) -> None:
    with _start_lock:
        observer = _observers.pop(workspace_id, None)
        _handlers.pop(workspace_id, None)
    if observer is not None:
        observer.stop()
        observer.join(timeout=5)


def start_watcher(workspace_id: str, watch_path: str) -> None:
    watch_root = Path(watch_path).resolve()
    if not watch_root.is_dir():
        raise ValueError(f"Watch path is not a directory: {watch_path}")

    stop_watcher(workspace_id)

    handler = DebouncedWatchHandler(workspace_id, str(watch_root))
    observer = Observer()
    observer.schedule(handler, str(watch_root), recursive=True)
    observer.start()

    with _start_lock:
        _observers[workspace_id] = observer
        _handlers[workspace_id] = handler

    logger.info("Started folder watcher for workspace %s at %s", workspace_id, watch_root)


def stop_all_watchers() -> None:
    for workspace_id in list(_observers.keys()):
        stop_watcher(workspace_id)


async def start_all_from_db() -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(WatchFolder).where(WatchFolder.enabled.is_(True))
        )
        records = result.scalars().all()

    for record in records:
        if not Path(record.path).is_dir():
            logger.warning(
                "Skipping watcher for workspace %s — path missing: %s",
                record.workspace_id,
                record.path,
            )
            continue
        try:
            start_watcher(record.workspace_id, record.path)
            await scan_watch_folder(record.workspace_id, record.path)
        except Exception:
            logger.exception(
                "Failed to start watcher for workspace %s",
                record.workspace_id,
            )
