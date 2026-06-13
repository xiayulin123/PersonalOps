from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Workspace, User
from schema import TemplateOut
from services.templates import get_templates

router = APIRouter(tags=["templates"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



@router.get(
    "/workspaces/{workspace_id}/templates",
    response_model=list[TemplateOut],
)
async def list_templates(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    return [
        TemplateOut(
            id=template["id"],
            label=template["label"],
            description=template["description"],
        )
        for template in get_templates(workspace.type)
    ]
