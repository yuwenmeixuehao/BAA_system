from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AnalysisResult,
    AnalysisTask,
    Attachment,
    Conversation,
    Message,
    ReportFile,
    TaskEvent,
)


class TaskRepository:
    async def lock_conversation_owned(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_id: str,
    ) -> Conversation | None:
        return await session.scalar(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.status != "deleted",
            )
            .with_for_update()
        )

    async def get_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
        *,
        lock: bool = False,
    ) -> AnalysisTask | None:
        query = select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return await session.scalar(query)

    async def get_by_id(
        self,
        session: AsyncSession,
        task_id: str,
        *,
        lock: bool = False,
    ) -> AnalysisTask | None:
        query = select(AnalysisTask).where(AnalysisTask.id == task_id)
        if lock:
            query = query.with_for_update()
        return await session.scalar(query)

    async def get_idempotent(
        self,
        session: AsyncSession,
        user_id: str,
        conversation_id: str,
        client_msg_id: str,
    ) -> AnalysisTask | None:
        return await session.scalar(
            select(AnalysisTask).where(
                AnalysisTask.user_id == user_id,
                AnalysisTask.conversation_id == conversation_id,
                AnalysisTask.client_msg_id == client_msg_id,
            )
        )

    async def get_active_for_conversation(
        self,
        session: AsyncSession,
        conversation_id: str,
    ) -> AnalysisTask | None:
        return await session.scalar(
            select(AnalysisTask)
            .where(
                AnalysisTask.conversation_id == conversation_id,
                AnalysisTask.task_status.in_(("queued", "running")),
            )
            .order_by(AnalysisTask.created_at.desc())
            .limit(1)
        )

    async def get_latest_for_conversation(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_id: str,
    ) -> AnalysisTask | None:
        return await session.scalar(
            select(AnalysisTask)
            .where(
                AnalysisTask.conversation_id == conversation_id,
                AnalysisTask.user_id == user_id,
            )
            .order_by(AnalysisTask.created_at.desc())
            .limit(1)
        )

    async def list_queued(self, session: AsyncSession, *, limit: int) -> list[AnalysisTask]:
        result = await session.scalars(
            select(AnalysisTask)
            .where(AnalysisTask.task_status == "queued")
            .order_by(AnalysisTask.created_at.asc())
            .limit(limit)
        )
        return list(result)

    async def list_expired_waiting(
        self,
        session: AsyncSession,
        *,
        updated_before: datetime,
        limit: int,
    ) -> list[AnalysisTask]:
        result = await session.scalars(
            select(AnalysisTask)
            .where(
                AnalysisTask.task_status == "waiting_input",
                AnalysisTask.updated_at < updated_before,
            )
            .order_by(AnalysisTask.updated_at.asc())
            .limit(limit)
        )
        return list(result)

    async def next_message_seq(self, session: AsyncSession, conversation_id: str) -> int:
        current = await session.scalar(
            select(func.max(Message.seq_no)).where(Message.conversation_id == conversation_id)
        )
        return int(current or 0) + 1

    async def owned_attachments(
        self,
        session: AsyncSession,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
    ) -> list[Attachment]:
        if not attachment_ids:
            return []
        result = await session.scalars(
            select(Attachment).where(
                Attachment.id.in_(attachment_ids),
                Attachment.user_id == user_id,
                Attachment.conversation_id == conversation_id,
            )
        )
        return list(result)

    async def next_event_seq(self, session: AsyncSession, task_id: str) -> int:
        current = await session.scalar(
            select(func.max(TaskEvent.event_seq)).where(TaskEvent.task_id == task_id)
        )
        return int(current or 0) + 1

    async def list_events(
        self,
        session: AsyncSession,
        task_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> list[TaskEvent]:
        result = await session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id, TaskEvent.event_seq > after_seq)
            .order_by(TaskEvent.event_seq.asc())
            .limit(limit)
        )
        return list(result)

    async def has_complete_result(self, session: AsyncSession, task_id: str) -> bool:
        result_id = await session.scalar(
            select(AnalysisResult.id).where(AnalysisResult.task_id == task_id)
        )
        file_id = await session.scalar(select(ReportFile.id).where(ReportFile.task_id == task_id))
        return result_id is not None and file_id is not None
