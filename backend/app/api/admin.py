from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.auth import AdminUserDep
from app.schemas.admin import AdminTaskLogList
from app.schemas.common import ApiResponse, success
from app.services.admin_log_service import admin_log_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/logs", response_model=ApiResponse[AdminTaskLogList])
async def list_admin_logs(
    _: AdminUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    task_id: str | None = None,
    trace_id: str | None = None,
    level: Literal["info", "warning", "error"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ApiResponse[AdminTaskLogList]:
    return success(
        await admin_log_service.list_logs(
            session,
            task_id=task_id,
            trace_id=trace_id,
            level=level,
            limit=limit,
        )
    )
