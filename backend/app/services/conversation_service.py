from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ErrorCode
from app.core.pagination import decode_cursor, encode_cursor
from app.models.entities import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.conversation import (
    AttachmentSummary,
    ConversationItem,
    ConversationList,
    DeleteConversationsResult,
    MessageItem,
    MessageList,
    UpdateConversationRequest,
)


class ConversationService:
    def __init__(self) -> None:
        self.repository = ConversationRepository()

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        title: str | None,
    ) -> ConversationItem:
        normalized_title = (title or "").strip() or "新会话"
        conversation = Conversation(
            user_id=user_id,
            title=normalized_title,
            status="draft",
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return self._item(conversation)

    async def update(
        self,
        session: AsyncSession,
        user_id: str,
        request: UpdateConversationRequest,
    ) -> ConversationItem:
        conversation = await self._require_owned(session, request.conversation_id, user_id)
        if request.title is not None:
            conversation.title = request.title.strip()
        if request.status is not None:
            conversation.status = request.status
        await session.commit()
        await session.refresh(conversation)
        return self._item(conversation)

    async def delete_many(
        self,
        session: AsyncSession,
        user_id: str,
        conversation_ids: list[str],
    ) -> DeleteConversationsResult:
        unique_ids = list(dict.fromkeys(conversation_ids))
        conversations = []
        for conversation_id in unique_ids:
            conversations.append(await self._require_owned(session, conversation_id, user_id))
        for conversation in conversations:
            conversation.status = "deleted"
        await session.commit()
        return DeleteConversationsResult(deleted_count=len(conversations))

    async def list_conversations(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> ConversationList:
        cursor_time: datetime | None = None
        cursor_id: str | None = None
        if cursor:
            payload = decode_cursor(cursor)
            try:
                cursor_time = datetime.fromisoformat(str(payload["updated_at"]))
                cursor_id = str(payload["id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AppException(
                    ErrorCode.INVALID_ARGUMENT,
                    "会话分页游标无效",
                    status_code=400,
                ) from exc
        rows = await self.repository.list_owned(
            session,
            user_id,
            status=status,
            cursor_time=cursor_time,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(
                {"updated_at": last.updated_at.isoformat(), "id": last.id}
            )
        return ConversationList(
            items=[self._item(item) for item in page],
            next_cursor=next_cursor,
        )

    async def list_messages(
        self,
        session: AsyncSession,
        user_id: str,
        conversation_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> MessageList:
        await self._require_owned(session, conversation_id, user_id)
        before_seq: int | None = None
        if cursor:
            payload = decode_cursor(cursor)
            try:
                before_seq = int(payload["before_seq"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AppException(
                    ErrorCode.INVALID_ARGUMENT,
                    "消息分页游标无效",
                    status_code=400,
                ) from exc
        rows = await self.repository.list_messages(
            session,
            conversation_id,
            before_seq=before_seq,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page_desc = rows[:limit]
        attachments = await self.repository.list_attachments_by_messages(
            session,
            [message.id for message in page_desc],
        )
        by_message: dict[str, list[AttachmentSummary]] = {}
        for attachment in attachments:
            if attachment.message_id:
                by_message.setdefault(attachment.message_id, []).append(
                    AttachmentSummary(
                        attachment_id=attachment.id,
                        file_name=attachment.file_name,
                        file_type=attachment.mime_type,
                        file_size=attachment.file_size,
                        parse_status=attachment.parse_status,
                    )
                )
        next_cursor = None
        if has_more and page_desc:
            next_cursor = encode_cursor({"before_seq": page_desc[-1].seq_no})
        items = [
            MessageItem(
                message_id=message.id,
                task_id=message.task_id,
                client_msg_id=message.client_msg_id,
                seq_no=message.seq_no,
                role=message.role,
                message_type=message.message_type,
                content=message.content,
                attachments=by_message.get(message.id, []),
                created_at=message.created_at,
            )
            for message in reversed(page_desc)
        ]
        return MessageList(
            conversation_id=conversation_id,
            items=items,
            next_cursor=next_cursor,
        )

    async def _require_owned(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        conversation = await self.repository.get_owned(session, conversation_id, user_id)
        if conversation is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "会话不存在",
                status_code=404,
            )
        return conversation

    @staticmethod
    def _item(conversation: Conversation) -> ConversationItem:
        return ConversationItem(
            conversation_id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            last_message_at=conversation.last_message_at,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


conversation_service = ConversationService()
