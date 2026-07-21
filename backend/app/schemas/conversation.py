from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ConversationStatus = Literal["draft", "active", "archived", "deleted"]


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class DeleteConversationsRequest(BaseModel):
    conversation_ids: list[str] = Field(min_length=1, max_length=100)


class UpdateConversationRequest(BaseModel):
    conversation_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateConversationRequest":
        if self.title is not None:
            self.title = self.title.strip()
        if self.title is None and self.status is None:
            raise ValueError("title 和 status 至少提供一个")
        if self.title == "":
            raise ValueError("title 不能为空")
        return self


class ConversationItem(BaseModel):
    conversation_id: str
    title: str
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationItem]
    next_cursor: str | None


class DeleteConversationsResult(BaseModel):
    deleted_count: int


class AttachmentSummary(BaseModel):
    attachment_id: str
    file_name: str
    file_type: str
    file_size: int
    parse_status: str


class MessageItem(BaseModel):
    message_id: str
    task_id: str | None
    client_msg_id: str | None
    seq_no: int
    role: str
    message_type: str
    content: str | None
    attachments: list[AttachmentSummary]
    created_at: datetime


class MessageList(BaseModel):
    conversation_id: str
    items: list[MessageItem]
    next_cursor: str | None
