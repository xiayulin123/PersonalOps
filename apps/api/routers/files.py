import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal, get_db
from models import File, Workspace, User
from schema import FileOut
from services.chunker import chunk_text
from services.indexer import delete_file_chunks, index_file
from services.ocr import (
    OcrNotAvailableError,
    OcrProcessingError,
    is_ocr_available,
    ocr_pdf,
    ocr_unavailable_message,
)

logger = logging.getLogger(__name__)
from services.parser import parse_file

router = APIRouter(tags=["files"])

from services.auth.dependencies import get_current_user_for_request
from services.storage.file_storage import (
    cleanup_temp_cache,
    delete_stored_file,
    ensure_extracted_local_path,
    ensure_local_path,
    pages_to_extracted_text,
    save_extracted_text,
    save_uploaded_file,
)
from services.workspace_access import get_accessible_workspace


async def reset_stale_ocr_files() -> int:
    """Mark interrupted OCR jobs as needs_ocr (e.g. after server restart)."""
    async with SessionLocal() as db:
        result = await db.execute(
            update(File)
            .where(File.status == "ocr")
            .values(status="needs_ocr", chunk_count=0)
        )
        await db.commit()
        return result.rowcount or 0



async def _get_file_or_404(
    workspace_id: str, file_id: str, db: AsyncSession
) -> File:
    file_record = await db.get(File, file_id)
    if file_record is None or file_record.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="File not found")
    return file_record


def _is_pdf(filename: str) -> bool:
    return filename.rsplit(".", 1)[-1].lower() == "pdf"


def _status_for_no_extracted_text(filename: str) -> str:
    """PDF with no text layer is likely scanned; other types are simply empty."""
    return "needs_ocr" if _is_pdf(filename) else "empty"


def _apply_pages_to_index(file_record: File, pages: list[dict]) -> None:
    if not pages:
        file_record.status = _status_for_no_extracted_text(file_record.filename)
        file_record.chunk_count = 0
        return

    chunks = chunk_text(
        pages,
        workspace_id=file_record.workspace_id,
        file_id=file_record.id,
        filename=file_record.filename,
    )
    count = index_file(
        file_record.workspace_id,
        file_record.id,
        chunks,
    )
    if count > 0:
        file_record.status = "ready"
        file_record.chunk_count = count
    else:
        file_record.status = "empty"
        file_record.chunk_count = 0


async def run_indexing(file_id: str) -> None:
    async with SessionLocal() as db:
        file_record = await db.get(File, file_id)
        if file_record is None:
            return

        workspace = await db.get(Workspace, file_record.workspace_id)
        file_record.status = "indexing"
        await db.commit()

        try:
            from services.auth.openai_access import openai_context_for_workspace
            from services.openai_runtime import MissingOpenAIKeyError

            async with openai_context_for_workspace(db, workspace):
                extracted_path = ensure_extracted_local_path(file_record)
                if extracted_path:
                    pages = parse_file(extracted_path)
                else:
                    local_path = ensure_local_path(file_record)
                    pages = parse_file(local_path)
                _apply_pages_to_index(file_record, pages)
        except MissingOpenAIKeyError:
            file_record.status = "failed"
            file_record.chunk_count = 0
            logger.warning("Indexing skipped for %s: missing user OpenAI key", file_id)
        except Exception:
            file_record.status = "failed"
            file_record.chunk_count = 0

        await db.commit()
        if file_record.storage_backend == "gcs":
            cleanup_temp_cache(file_record)


async def run_ocr_and_index(file_id: str) -> None:
    async with SessionLocal() as db:
        file_record = await db.get(File, file_id)
        if file_record is None:
            return

        file_path = ensure_local_path(file_record)
        file_record.status = "ocr"
        await db.commit()

    logger.info("OCR started for file %s (%s)", file_id, file_path)

    try:
        pages = await asyncio.to_thread(ocr_pdf, file_path)
    except OcrNotAvailableError as exc:
        logger.warning("OCR unavailable for file %s: %s", file_id, exc)
        pages = None
        error_status = "needs_ocr"
    except OcrProcessingError as exc:
        logger.error("OCR failed for file %s: %s", file_id, exc)
        pages = None
        error_status = "failed"
    except Exception:
        logger.exception("Unexpected OCR failure for file %s", file_id)
        pages = None
        error_status = "failed"
    else:
        error_status = None

    async with SessionLocal() as db:
        file_record = await db.get(File, file_id)
        if file_record is None:
            return

        if error_status is not None:
            file_record.status = error_status
            file_record.chunk_count = 0
        else:
            workspace = await db.get(Workspace, file_record.workspace_id)
            user_id = workspace.user_id if workspace else None
            extracted_text = pages_to_extracted_text(pages or [])
            if extracted_text.strip():
                extracted_uri = save_extracted_text(
                    file_record=file_record,
                    user_id=user_id,
                    text=extracted_text,
                )
                if extracted_uri:
                    file_record.extracted_gcs_uri = extracted_uri

            from services.auth.openai_access import openai_context_for_workspace
            from services.openai_runtime import MissingOpenAIKeyError

            try:
                async with openai_context_for_workspace(db, workspace):
                    _apply_pages_to_index(file_record, pages)
            except MissingOpenAIKeyError:
                file_record.status = "failed"
                file_record.chunk_count = 0
                logger.warning(
                    "OCR indexing skipped for %s: missing user OpenAI key", file_id
                )
            logger.info(
                "OCR finished for file %s: status=%s chunks=%s",
                file_id,
                file_record.status,
                file_record.chunk_count,
            )

        await db.commit()
        if file_record.storage_backend == "gcs":
            cleanup_temp_cache(file_record)


@router.post(
    "/workspaces/{workspace_id}/files",
    response_model=FileOut,
    status_code=201,
)
async def upload_file(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)

    filename = os.path.basename(file.filename or "upload")
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()
    file_id, storage_backend, dest_path, gcs_uri, size_bytes = save_uploaded_file(
        workspace_id=workspace_id,
        user_id=current_user.id if current_user else None,
        filename=filename,
        content=content,
    )

    file_record = File(
        id=file_id,
        workspace_id=workspace_id,
        filename=filename,
        path=dest_path,
        storage_backend=storage_backend,
        gcs_uri=gcs_uri,
        size_bytes=size_bytes,
        status="pending",
        chunk_count=0,
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)

    background_tasks.add_task(run_indexing, file_record.id)
    return file_record


@router.post(
    "/workspaces/{workspace_id}/files/{file_id}/ocr",
    response_model=FileOut,
)
async def ocr_file(
    workspace_id: str,
    file_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    file_record = await _get_file_or_404(workspace_id, file_id, db)

    if not _is_pdf(file_record.filename):
        raise HTTPException(status_code=400, detail="OCR is only supported for PDF files")

    if file_record.status not in ("needs_ocr", "failed", "ocr"):
        raise HTTPException(
            status_code=400,
            detail="OCR can only be run on PDF files marked as needs_ocr, failed, or ocr",
        )

    if not is_ocr_available():
        raise HTTPException(status_code=503, detail=ocr_unavailable_message())

    file_record.status = "ocr"
    await db.commit()
    await db.refresh(file_record)

    background_tasks.add_task(run_ocr_and_index, file_record.id)
    return file_record


@router.get("/workspaces/{workspace_id}/files", response_model=list[FileOut])
async def list_files(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)

    result = await db.execute(
        select(File)
        .where(File.workspace_id == workspace_id)
        .order_by(File.filename)
    )
    return result.scalars().all()


@router.delete("/workspaces/{workspace_id}/files/{file_id}", status_code=204)
async def delete_file(
    workspace_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    file_record = await _get_file_or_404(workspace_id, file_id, db)

    delete_stored_file(file_record)

    delete_file_chunks(workspace_id, file_id)

    await db.delete(file_record)
    await db.commit()
