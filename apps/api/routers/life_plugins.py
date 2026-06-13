from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import (
    LifeCalendarEvent,
    LifeGoogleConnection,
    LifeInboxBrief,
    LifeOutlookConnection,
    User,
    Workspace,
)
from schema import (
    CalendarEventOut,
    DeviceCodePollIn,
    DeviceCodeStartOut,
    InboxBriefOut,
    InboxListOut,
    LifeCalendarOut,
    LifeConnectionProviderOut,
    LifeConnectionsOut,
    LifeOutlookStatusOut,
    LifeSyncOut,
    OAuthCallbackIn,
    OAuthStartOut,
)
from services.life.calendar_sync import sync_workspace_calendar
from services.life.gmail_inbox_sync import sync_workspace_gmail
from services.life.google_calendar_sync import sync_workspace_google_calendar
from services.life.google_client import fetch_google_profile_email
from services.life.google_oauth import (
    complete_authorization_code_flow as complete_google_authorization_code_flow,
    is_google_configured,
    start_authorization_code_flow as start_google_authorization_code_flow,
)
from services.life.inbox_list import build_inbox_lists
from services.life.inbox_sync import sync_workspace_mail
from services.life.outlook_graph import fetch_profile_email
from services.life.outlook_oauth import (
    complete_authorization_code_flow,
    is_outlook_configured,
    poll_device_code_flow,
    start_authorization_code_flow,
    start_device_code_flow,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/life", tags=["life"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace


async def _require_life_workspace(
    workspace_id: str,
    db: AsyncSession,
    current_user: User | None,
) -> Workspace:
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    if workspace.type != "life":
        raise HTTPException(
            status_code=400,
            detail="Life plugins are only available for life workspaces",
        )
    return workspace


def _outlook_status_from_connection(
    connection: LifeOutlookConnection | None,
) -> LifeOutlookStatusOut:
    return LifeOutlookStatusOut(
        configured=is_outlook_configured(),
        connected=bool(connection and connection.refresh_token),
        account_email=connection.account_email if connection else None,
        last_mail_sync_at=connection.last_mail_sync_at if connection else None,
        last_calendar_sync_at=connection.last_calendar_sync_at if connection else None,
    )


async def _save_outlook_connection(
    db: AsyncSession,
    workspace_id: str,
    result: dict,
    email: str,
) -> LifeOutlookConnection:
    connection = await db.get(LifeOutlookConnection, workspace_id)
    expires = result["expires_at"]
    if connection is None:
        connection = LifeOutlookConnection(workspace_id=workspace_id)
        db.add(connection)
    connection.account_email = email
    connection.refresh_token = result["refresh_token"]
    connection.access_token = result["access_token"]
    connection.token_expires_at = (
        expires.replace(tzinfo=None) if expires.tzinfo else expires
    )
    connection.enabled = True
    await db.commit()
    await db.refresh(connection)
    return connection


async def _save_google_connection(
    db: AsyncSession,
    workspace_id: str,
    result: dict,
    email: str,
) -> LifeGoogleConnection:
    connection = await db.get(LifeGoogleConnection, workspace_id)
    expires = result["expires_at"]
    if connection is None:
        connection = LifeGoogleConnection(workspace_id=workspace_id)
        db.add(connection)
    connection.account_email = email
    connection.refresh_token = result["refresh_token"]
    connection.access_token = result["access_token"]
    connection.token_expires_at = (
        expires.replace(tzinfo=None) if expires.tzinfo else expires
    )
    connection.enabled = True
    await db.commit()
    await db.refresh(connection)
    return connection


logger = logging.getLogger(__name__)


async def _sync_all_plugins(workspace_id: str) -> LifeSyncOut:
    mail_new = await sync_workspace_mail(workspace_id)
    mail_new += await sync_workspace_gmail(workspace_id)
    calendar_count = await sync_workspace_calendar(workspace_id)
    calendar_count += await sync_workspace_google_calendar(workspace_id)
    return LifeSyncOut(new_mail_briefs=mail_new, calendar_events=calendar_count)


async def _sync_all_plugins_background(workspace_id: str) -> None:
    try:
        await _sync_all_plugins(workspace_id)
    except Exception:
        logger.exception(
            "Background life plugin sync failed for workspace %s", workspace_id
        )


def _is_mail_connected(
    outlook: LifeOutlookConnection | None, google: LifeGoogleConnection | None
) -> bool:
    return bool(
        (outlook and outlook.refresh_token) or (google and google.refresh_token)
    )


@router.get("/connections", response_model=LifeConnectionsOut)
async def list_connections(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    outlook = await db.get(LifeOutlookConnection, workspace_id)
    google = await db.get(LifeGoogleConnection, workspace_id)
    providers = [
        LifeConnectionProviderOut(
            id="microsoft",
            label="Microsoft 365",
            configured=is_outlook_configured(),
            connected=bool(outlook and outlook.refresh_token),
            account_email=outlook.account_email if outlook else None,
            features=["inbox", "calendar"],
            last_mail_sync_at=outlook.last_mail_sync_at if outlook else None,
            last_calendar_sync_at=outlook.last_calendar_sync_at if outlook else None,
        ),
        LifeConnectionProviderOut(
            id="google",
            label="Google",
            configured=is_google_configured(),
            connected=bool(google and google.refresh_token),
            account_email=google.account_email if google else None,
            features=["inbox", "calendar"],
            last_mail_sync_at=google.last_mail_sync_at if google else None,
            last_calendar_sync_at=google.last_calendar_sync_at if google else None,
        ),
    ]
    return LifeConnectionsOut(providers=providers)


@router.get("/outlook/status", response_model=LifeOutlookStatusOut)
async def outlook_status(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    connection = await db.get(LifeOutlookConnection, workspace_id)
    return _outlook_status_from_connection(connection)


@router.get("/outlook/oauth/start", response_model=OAuthStartOut)
async def outlook_oauth_start(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    if not is_outlook_configured():
        raise HTTPException(
            status_code=503,
            detail="Set MS_GRAPH_CLIENT_ID in .env",
        )
    try:
        payload = await start_authorization_code_flow(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OAuthStartOut(**payload)


@router.post("/outlook/oauth/callback", response_model=LifeOutlookStatusOut)
async def outlook_oauth_callback(
    workspace_id: str,
    body: OAuthCallbackIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    try:
        result = await complete_authorization_code_flow(
            workspace_id, body.code, body.state
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    email = await fetch_profile_email(result["access_token"])
    connection = await _save_outlook_connection(db, workspace_id, result, email)
    background_tasks.add_task(_sync_all_plugins_background, workspace_id)
    return _outlook_status_from_connection(connection)


@router.get("/google/oauth/start", response_model=OAuthStartOut)
async def google_oauth_start(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    if not is_google_configured():
        raise HTTPException(
            status_code=503,
            detail="Set GOOGLE_CLIENT_ID in .env",
        )
    try:
        payload = await start_google_authorization_code_flow(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OAuthStartOut(**payload)


@router.post("/google/oauth/callback", response_model=LifeOutlookStatusOut)
async def google_oauth_callback(
    workspace_id: str,
    body: OAuthCallbackIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    try:
        result = await complete_google_authorization_code_flow(
            workspace_id, body.code, body.state
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    email = await fetch_google_profile_email(result["access_token"]) or "google"
    connection = await _save_google_connection(db, workspace_id, result, email)
    background_tasks.add_task(_sync_all_plugins_background, workspace_id)
    return LifeOutlookStatusOut(
        configured=True,
        connected=True,
        account_email=connection.account_email,
        last_mail_sync_at=connection.last_mail_sync_at,
        last_calendar_sync_at=connection.last_calendar_sync_at,
    )


@router.delete("/google", status_code=204)
async def google_disconnect(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    connection = await db.get(LifeGoogleConnection, workspace_id)
    if connection:
        await db.delete(connection)
        await db.commit()


@router.post("/outlook/device-code/start", response_model=DeviceCodeStartOut)
async def outlook_device_code_start(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await _require_life_workspace(workspace_id, db, current_user)
    if not is_outlook_configured():
        raise HTTPException(
            status_code=503,
            detail="Set MS_GRAPH_CLIENT_ID in .env",
        )
    try:
        payload = await start_device_code_flow(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeviceCodeStartOut(**payload)


@router.post("/outlook/device-code/poll", response_model=LifeOutlookStatusOut)
async def outlook_device_code_poll(
    workspace_id: str,
    body: DeviceCodePollIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    try:
        result = await poll_device_code_flow(workspace_id, body.device_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.get("status") == "pending":
        raise HTTPException(status_code=202, detail="Authorization pending")

    email = await fetch_profile_email(result["access_token"])
    connection = await _save_outlook_connection(db, workspace_id, result, email)
    return _outlook_status_from_connection(connection)


@router.delete("/outlook", status_code=204)
async def outlook_disconnect(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    connection = await db.get(LifeOutlookConnection, workspace_id)
    if connection:
        await db.delete(connection)
        await db.commit()


@router.get("/inbox", response_model=InboxListOut)
async def list_inbox(
    workspace_id: str,
    page_size: int = 5,
    page: int = 0,
    summary_limit: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    outlook = await db.get(LifeOutlookConnection, workspace_id)
    google = await db.get(LifeGoogleConnection, workspace_id)
    effective_page_size = summary_limit if summary_limit is not None else page_size
    page_items, viewed, total_unread, total_pages = await build_inbox_lists(
        db, workspace_id, effective_page_size, page
    )
    viewed_out = [InboxBriefOut.model_validate(item) for item in viewed]
    return InboxListOut(
        connected=_is_mail_connected(outlook, google),
        items=[InboxBriefOut.model_validate(item) for item in page_items],
        unread=[],
        viewed=viewed_out,
        historical=viewed_out,
        total_unread=total_unread,
        page=page,
        page_size=effective_page_size,
        total_pages=total_pages,
    )


@router.post("/inbox/dismiss-all", status_code=204)
async def dismiss_all_inbox_briefs(
    workspace_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await _require_life_workspace(workspace_id, db, current_user)
    result = await db.execute(
        select(LifeInboxBrief).where(
            LifeInboxBrief.workspace_id == workspace_id,
            LifeInboxBrief.dismissed.is_(False),
            LifeInboxBrief.summary_engine != "raw",
        )
    )
    for brief in result.scalars().all():
        brief.dismissed = True
    await db.commit()


@router.post("/inbox/{brief_id}/dismiss", status_code=204)
async def dismiss_inbox_brief(
    workspace_id: str, brief_id: str, db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request)
):
    await _require_life_workspace(workspace_id, db, current_user)
    brief = await db.get(LifeInboxBrief, brief_id)
    if brief is None or brief.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Brief not found")
    brief.dismissed = True
    await db.commit()


@router.get("/calendar", response_model=LifeCalendarOut)
async def list_calendar(
    workspace_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    outlook = await db.get(LifeOutlookConnection, workspace_id)
    google = await db.get(LifeGoogleConnection, workspace_id)
    cutoff = datetime.utcnow() - timedelta(days=1)
    result = await db.execute(
        select(LifeCalendarEvent)
        .where(
            LifeCalendarEvent.workspace_id == workspace_id,
            LifeCalendarEvent.end_at >= cutoff,
        )
        .order_by(LifeCalendarEvent.start_at.asc())
    )
    events = list(result.scalars().all())
    return LifeCalendarOut(
        connected=_is_mail_connected(outlook, google),
        events=[CalendarEventOut.model_validate(event) for event in events],
    )


@router.post("/sync", response_model=LifeSyncOut)
async def sync_life_plugins(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await _require_life_workspace(workspace_id, db, current_user)
    return await _sync_all_plugins(workspace_id)
