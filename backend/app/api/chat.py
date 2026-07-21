from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.redis import get_redis
from app.dependencies.auth import CurrentUserDep
from app.schemas.common import ApiResponse, success
from app.schemas.conversation import (
    ConversationItem,
    ConversationList,
    CreateConversationRequest,
    DeleteConversationsRequest,
    DeleteConversationsResult,
    MessageList,
    UpdateConversationRequest,
)
from app.schemas.websocket import WebsocketTokenRequest, WebsocketTokenResponse
from app.services.conversation_service import conversation_service
from app.services.websocket_token_service import websocket_token_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ws-token", response_model=ApiResponse[WebsocketTokenResponse])
async def create_websocket_token(
    body: WebsocketTokenRequest,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ApiResponse[WebsocketTokenResponse]:
    return success(
        await websocket_token_service.issue(
            session,
            redis,
            user.id,
            body.conversation_id,
        )
    )


@router.post("/create", response_model=ApiResponse[ConversationItem])
async def create_conversation(
    body: CreateConversationRequest,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[ConversationItem]:
    return success(await conversation_service.create(session, user.id, body.title))


@router.post("/delete", response_model=ApiResponse[DeleteConversationsResult])
async def delete_conversations(
    body: DeleteConversationsRequest,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[DeleteConversationsResult]:
    result = await conversation_service.delete_many(
        session,
        user.id,
        body.conversation_ids,
    )
    return success(result)


@router.post("/update", response_model=ApiResponse[ConversationItem])
async def update_conversation(
    body: UpdateConversationRequest,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[ConversationItem]:
    return success(await conversation_service.update(session, user.id, body))


@router.get("/ls", response_model=ApiResponse[ConversationList])
async def list_conversations(
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["draft", "active", "archived", "deleted"] | None = None,
) -> ApiResponse[ConversationList]:
    return success(
        await conversation_service.list_conversations(
            session,
            user.id,
            status=status,
            cursor=cursor,
            limit=limit,
        )
    )


@router.get("/ls/{conversation_id}", response_model=ApiResponse[MessageList])
async def list_messages(
    conversation_id: str,
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApiResponse[MessageList]:
    return success(
        await conversation_service.list_messages(
            session,
            user.id,
            conversation_id,
            cursor=cursor,
            limit=limit,
        )
    )
