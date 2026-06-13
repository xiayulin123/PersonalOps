import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DEFAULT_TOOL_SETTINGS_JSON, Workspace, User
from schema import ToolSettingsOut, ToolSettingsUpdate

router = APIRouter(tags=["tools"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace

AVAILABLE_TOOLS = ["file_search", "web_search", "memory", "github_read", "code_search"]



def _parse_tool_settings(raw: str | None) -> dict[str, bool]:
    defaults = json.loads(DEFAULT_TOOL_SETTINGS_JSON)
    if not raw:
        return defaults
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return defaults

    return {
        "file_search": bool(data.get("file_search", defaults["file_search"])),
        "web_search": bool(data.get("web_search", defaults["web_search"])),
        "memory": bool(data.get("memory", defaults["memory"])),
        "github_read": bool(data.get("github_read", defaults["github_read"])),
        "code_search": bool(data.get("code_search", defaults["code_search"])),
    }


def _to_tool_settings_out(settings: dict[str, bool]) -> ToolSettingsOut:
    return ToolSettingsOut(
        file_search=settings["file_search"],
        web_search=settings["web_search"],
        memory=settings["memory"],
        github_read=settings["github_read"],
        code_search=settings["code_search"],
        available=AVAILABLE_TOOLS,
    )


@router.get("/workspaces/{workspace_id}/tools", response_model=ToolSettingsOut)
async def get_tool_settings(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    settings = _parse_tool_settings(workspace.tool_settings_json)
    return _to_tool_settings_out(settings)


@router.patch("/workspaces/{workspace_id}/tools", response_model=ToolSettingsOut)
async def update_tool_settings(
    workspace_id: str,
    body: ToolSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    settings = _parse_tool_settings(workspace.tool_settings_json)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No tool settings provided")

    for key, value in updates.items():
        if key not in AVAILABLE_TOOLS:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {key}")
        settings[key] = value

    workspace.tool_settings_json = json.dumps(settings)
    await db.commit()
    await db.refresh(workspace)
    return _to_tool_settings_out(settings)
