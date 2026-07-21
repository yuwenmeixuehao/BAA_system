import hashlib
import logging
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.tabular import file_format
from app.core.config import Settings
from app.core.exceptions import AppException, ErrorCode
from app.models.entities import Attachment
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.attachment import AttachmentItem, DeleteAttachmentResult

logger = logging.getLogger(__name__)


class AttachmentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.conversations = ConversationRepository()
        self.storage = WorkspaceStorage(settings.agent_data_root)

    async def upload(
        self,
        session: AsyncSession,
        user_id: str,
        conversation_id: str,
        file: UploadFile,
    ) -> AttachmentItem:
        conversation = await self.conversations.get_owned(
            session,
            conversation_id,
            user_id,
        )
        if conversation is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "会话不存在",
                status_code=404,
            )
        original_name = Path(file.filename or "").name
        if not original_name:
            raise AppException(ErrorCode.INVALID_ARGUMENT, "文件名不能为空")
        try:
            file_format(original_name)
        except ValueError as exc:
            raise AppException(
                ErrorCode.INVALID_ARGUMENT,
                "仅支持 CSV、JSON、Parquet、Excel 和文本数据文件",
            ) from exc
        safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", original_name)[:200]
        attachment_id = str(uuid4())
        storage_key = PurePosixPath(
            "attachments",
            user_id,
            conversation_id,
            attachment_id,
            safe_name,
        ).as_posix()
        target = self.storage.resolve_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        digest = hashlib.sha256()
        try:
            with target.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.agent_max_file_bytes:
                        raise AppException(
                            ErrorCode.INVALID_ARGUMENT,
                            "文件超过允许的大小限制",
                            status_code=413,
                        )
                    digest.update(chunk)
                    output.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

        if size == 0:
            target.unlink(missing_ok=True)
            raise AppException(ErrorCode.INVALID_ARGUMENT, "不能上传空文件")

        attachment = Attachment(
            id=attachment_id,
            user_id=user_id,
            conversation_id=conversation_id,
            file_name=original_name,
            storage_key=storage_key,
            mime_type=file.content_type or "application/octet-stream",
            file_size=size,
            sha256=digest.hexdigest(),
            parse_status="pending",
        )
        session.add(attachment)
        try:
            await session.commit()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return self.to_item(attachment)

    async def get_owned(
        self,
        session: AsyncSession,
        user_id: str,
        attachment_id: str,
    ) -> tuple[Attachment, Path]:
        attachment = await session.scalar(
            select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.user_id == user_id,
            )
        )
        if attachment is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "附件不存在",
                status_code=404,
            )
        path = self.storage.resolve_key(attachment.storage_key)
        if not path.is_file():
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "附件文件不存在",
                status_code=404,
            )
        return attachment, path

    async def delete(
        self,
        session: AsyncSession,
        user_id: str,
        attachment_id: str,
    ) -> DeleteAttachmentResult:
        attachment = await session.scalar(
            select(Attachment)
            .where(
                Attachment.id == attachment_id,
                Attachment.user_id == user_id,
            )
            .with_for_update()
        )
        if attachment is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "附件不存在",
                status_code=404,
            )
        if attachment.message_id:
            raise AppException(
                ErrorCode.INVALID_ARGUMENT,
                "已提交到任务的附件不能删除",
                status_code=409,
            )
        path = self.storage.resolve_key(attachment.storage_key)
        await session.delete(attachment)
        await session.commit()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "orphan attachment cleanup failed",
                extra={"attachment_id": attachment_id},
            )
        return DeleteAttachmentResult(attachment_id=attachment_id, deleted=True)

    @staticmethod
    def to_item(attachment: Attachment) -> AttachmentItem:
        return AttachmentItem(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            file_path=f"attachment:{attachment.id}",
            mime_type=attachment.mime_type,
            file_size=attachment.file_size,
            parse_status=attachment.parse_status,
        )


def build_attachment_service(settings: Settings) -> AttachmentService:
    return AttachmentService(settings)
