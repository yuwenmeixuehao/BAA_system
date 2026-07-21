from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.base import ToolContext, ToolResult
from app.agent.tools.tabular import dataframe_preview, file_format, read_dataframe
from app.core.config import Settings
from app.models.entities import Attachment


class FileReadTool:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.settings = settings

    async def run(self, attachment_id: str, context: ToolContext) -> ToolResult:
        async with self.sessions() as session:
            attachment = await session.scalar(
                select(Attachment).where(
                    Attachment.id == attachment_id,
                    Attachment.user_id == context.user_id,
                    Attachment.conversation_id == context.conversation_id,
                )
            )
            if attachment is None:
                return ToolResult(
                    ok=False,
                    summary="附件不存在或不属于当前会话",
                    error_code="ATTACHMENT_NOT_FOUND",
                )
            if attachment.file_size > self.settings.agent_max_file_bytes:
                return ToolResult(
                    ok=False,
                    summary="附件超过阶段四允许的大小限制",
                    error_code="FILE_TOO_LARGE",
                )
            storage_key = attachment.storage_key
            file_name = attachment.file_name

        storage = WorkspaceStorage(context.workspace_root)
        try:
            path = storage.resolve_key(storage_key)
            if not path.is_file():
                raise FileNotFoundError(path)
            format_name = file_format(file_name)
            frame = read_dataframe(path, file_name, self.settings.agent_max_rows)
        except Exception as exc:
            async with self.sessions() as session:
                failed = await session.get(Attachment, attachment_id)
                if failed:
                    failed.parse_status = "failed"
                    failed.parse_error = str(exc)[:1000]
                    await session.commit()
            return ToolResult(
                ok=False,
                summary="附件解析失败，请检查文件格式和内容",
                error_code="FILE_PARSE_FAILED",
            )

        async with self.sessions() as session:
            parsed = await session.get(Attachment, attachment_id)
            if parsed:
                parsed.parse_status = "parsed"
                parsed.parse_error = None
                await session.commit()

        file_ref = {
            "file_id": attachment_id,
            "source_type": "attachment",
            "storage_key": storage_key,
            "file_name": file_name,
            "format": format_name,
            "row_count": int(len(frame.index)),
            "columns": list(frame.columns),
        }
        return ToolResult(
            ok=True,
            summary=f"已读取附件 {file_name}，共 {len(frame.index)} 行、{len(frame.columns)} 列",
            files=[file_ref],
            data={
                "row_count": len(frame.index),
                "columns": list(frame.columns),
                "sample": dataframe_preview(frame, self.settings.agent_preview_rows),
            },
        )
