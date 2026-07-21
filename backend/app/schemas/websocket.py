from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator


class WebsocketTokenRequest(BaseModel):
    conversation_id: str


class WebsocketTokenResponse(BaseModel):
    websocket_token: str
    expires_in: int


class UserMessageEvent(BaseModel):
    type: Literal["user_message"]
    conversation_id: str
    client_msg_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value


class CancelTaskEvent(BaseModel):
    type: Literal["cancel_task"]
    task_id: str


class ResumeTaskEvent(BaseModel):
    type: Literal["resume_task"]
    task_id: str
    after_seq: int = Field(default=0, ge=0)


class ClarificationResponseEvent(BaseModel):
    type: Literal["clarification_response"]
    task_id: str
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value


class PingEvent(BaseModel):
    type: Literal["ping"]


ClientWebsocketEvent = Annotated[
    UserMessageEvent
    | CancelTaskEvent
    | ResumeTaskEvent
    | ClarificationResponseEvent
    | PingEvent,
    Field(discriminator="type"),
]

client_event_adapter = TypeAdapter(ClientWebsocketEvent)
