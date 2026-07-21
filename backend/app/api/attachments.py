from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.dependencies.auth import CurrentUserDep
from app.schemas.attachment import (
    AttachmentItem,
    DeleteAttachmentRequest,
    DeleteAttachmentResult,
)
from app.schemas.common import ApiResponse, success
from app.services.attachment_service import build_attachment_service

router = APIRouter(prefix="/attachment", tags=["attachment"])
attachment_service = build_attachment_service(settings)


@router.post("/upload", response_model=ApiResponse[AttachmentItem])
async def upload_attachment(
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    conversation_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> ApiResponse[AttachmentItem]:
    return success(
        await attachment_service.upload(
            session,
            user.id,
            conversation_id,
            file,
        )
    )


@router.post("/delete", response_model=ApiResponse[DeleteAttachmentResult])
async def delete_attachment(
    body: DeleteAttachmentRequest,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[DeleteAttachmentResult]:
    return success(await attachment_service.delete(session, user.id, body.attachment_id))


@router.get("/get", response_class=FileResponse)
async def get_attachment(
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    attachment_id: Annotated[str, Query()],
) -> FileResponse:
    attachment, path = await attachment_service.get_owned(session, user.id, attachment_id)
    return FileResponse(path, filename=attachment.file_name, media_type=attachment.mime_type)
