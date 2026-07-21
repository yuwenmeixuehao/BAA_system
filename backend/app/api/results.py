from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.dependencies.auth import CurrentUserDep
from app.schemas.common import ApiResponse, success
from app.schemas.report import AnalysisResultResponse
from app.services.analysis_result_service import get_analysis_result_service

router = APIRouter(prefix="/results", tags=["results"])
result_service = get_analysis_result_service(settings)


@router.get("/{task_id}", response_model=ApiResponse[AnalysisResultResponse])
async def get_result(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[AnalysisResultResponse]:
    return success(await result_service.get_owned(session, task_id, user.id))


@router.get("/{task_id}/export", response_class=FileResponse)
async def export_result(
    task_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    format: Annotated[Literal["html", "md", "json"], Query()] = "html",
) -> FileResponse:
    report_file, path = await result_service.export_owned(
        session,
        task_id,
        user.id,
        format,
    )
    media_types = {
        "html": "text/html; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
        "json": "application/json",
    }
    return FileResponse(path, filename=report_file.file_name, media_type=media_types[format])
