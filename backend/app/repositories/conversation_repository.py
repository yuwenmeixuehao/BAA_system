from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Attachment, Conversation, Message


class ConversationRepository:
    async def get_owned(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_id: str,
        *,
        include_deleted: bool = False,
    ) -> Conversation | None:
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        if not include_deleted:
            query = query.where(Conversation.status != "deleted")
        return await session.scalar(query)

    async def list_owned(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        status: str | None,
        cursor_time: datetime | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[Conversation]:
        query = select(Conversation).where(Conversation.user_id == user_id)
        if status:
            query = query.where(Conversation.status == status)
        else:
            query = query.where(Conversation.status != "deleted")
        if cursor_time and cursor_id:
            query = query.where(
                or_(
                    Conversation.updated_at < cursor_time,
                    and_(
                        Conversation.updated_at == cursor_time,
                        Conversation.id < cursor_id,
                    ),
                )
            )
        result = await session.scalars(
            query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit)
        )
        return list(result)

    async def list_messages(
        self,
        session: AsyncSession,
        conversation_id: str,
        *,
        before_seq: int | None,
        limit: int,
    ) -> list[Message]:
        query = select(Message).where(Message.conversation_id == conversation_id)
        if before_seq is not None:
            query = query.where(Message.seq_no < before_seq)
        result = await session.scalars(query.order_by(Message.seq_no.desc()).limit(limit))
        return list(result)

    async def list_attachments_by_messages(
        self,
        session: AsyncSession,
        message_ids: list[str],
    ) -> list[Attachment]:
        if not message_ids:
            return []
        result = await session.scalars(
            select(Attachment)
            .where(Attachment.message_id.in_(message_ids))
            .order_by(Attachment.created_at.asc())
        )
        return list(result)
