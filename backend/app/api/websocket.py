import asyncio
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import AppException, ErrorCode
from app.core.redis import get_redis
from app.schemas.websocket import (
    CancelTaskEvent,
    ClarificationResponseEvent,
    PingEvent,
    ResumeTaskEvent,
    UserMessageEvent,
    client_event_adapter,
)
from app.services.event_service import event_service
from app.services.task_service import task_service
from app.services.websocket_token_service import websocket_token_service

router = APIRouter(prefix="/chat/ws", tags=["websocket"])


async def _send_error(
    websocket: WebSocket,
    lock: asyncio.Lock,
    code: str,
    message: str,
    *,
    task_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    async with lock:
        await websocket.send_json(
            {
                "type": "error",
                "task_id": task_id,
                "conversation_id": conversation_id,
                "event_seq": 0,
                "payload": {"error_code": code, "message": message},
            }
        )


async def _forward_pubsub(
    websocket: WebSocket,
    redis: Redis,
    conversation_id: str,
    lock: asyncio.Lock,
    ready: asyncio.Event,
) -> None:
    try:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(event_service.channel(conversation_id))
            ready.set()
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message.get("type") == "message":
                    async with lock:
                        await websocket.send_text(str(message["data"]))
                await asyncio.sleep(0)
    except RedisError:
        ready.set()
        with suppress(RuntimeError, WebSocketDisconnect):
            await _send_error(
                websocket,
                lock,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "实时事件服务暂不可用",
                conversation_id=conversation_id,
            )
            await websocket.close(code=1011)


async def _send_replay(
    websocket: WebSocket,
    lock: asyncio.Lock,
    session: AsyncSession,
    task_id: str,
    user_id: str,
    conversation_id: str,
    after_seq: int,
) -> None:
    task = await task_service.require_owned(session, task_id, user_id)
    if task.conversation_id != conversation_id:
        raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
    replay = await event_service.list_owned(session, task, after_seq=after_seq)
    for item in replay.items:
        async with lock:
            await websocket.send_json(item.model_dump(mode="json"))


async def _handle_client_event(
    websocket: WebSocket,
    lock: asyncio.Lock,
    session: AsyncSession,
    redis: Redis,
    user_id: str,
    conversation_id: str,
    raw: dict[str, Any],
) -> None:
    event = client_event_adapter.validate_python(raw)
    if isinstance(event, PingEvent):
        async with lock:
            await websocket.send_json({"type": "pong"})
        return
    if isinstance(event, UserMessageEvent):
        if event.conversation_id != conversation_id:
            raise AppException(ErrorCode.FORBIDDEN, "消息会话与连接不匹配", status_code=403)
        outcome = await task_service.create_from_message(session, redis, user_id, event)
        if not outcome.created:
            for stored_event in outcome.events:
                async with lock:
                    await websocket.send_json(
                        event_service.to_item(stored_event).model_dump(mode="json")
                    )
        return
    if isinstance(event, ResumeTaskEvent):
        await _send_replay(
            websocket,
            lock,
            session,
            event.task_id,
            user_id,
            conversation_id,
            event.after_seq,
        )
        await session.rollback()
        return
    if isinstance(event, CancelTaskEvent):
        task = await task_service.require_owned(session, event.task_id, user_id)
        if task.conversation_id != conversation_id:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        await task_service.cancel(session, redis, event.task_id, user_id)
        return
    if isinstance(event, ClarificationResponseEvent):
        task = await task_service.require_owned(session, event.task_id, user_id)
        if task.conversation_id != conversation_id:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        await task_service.submit_clarification(
            session,
            redis,
            event.task_id,
            user_id,
            event.content,
        )


@router.websocket("/chat")
async def chat_websocket(
    websocket: WebSocket,
    websocket_token: str,
    conversation_id: str,
    redis: Annotated[Redis, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    try:
        user_id = await websocket_token_service.consume(
            session,
            redis,
            websocket_token,
            conversation_id,
        )
    except AppException as exc:
        await websocket.close(code=4401 if exc.status_code == 401 else 4403, reason=exc.message)
        return

    await websocket.accept()
    send_lock = asyncio.Lock()
    pubsub_ready = asyncio.Event()
    forwarder = asyncio.create_task(
        _forward_pubsub(websocket, redis, conversation_id, send_lock, pubsub_ready)
    )
    try:
        await pubsub_ready.wait()
        if forwarder.done():
            return
        latest = await task_service.tasks.get_latest_for_conversation(
            session,
            conversation_id,
            user_id,
        )
        if latest:
            await _send_replay(
                websocket,
                send_lock,
                session,
                latest.id,
                user_id,
                conversation_id,
                0,
            )
        await session.rollback()
        while True:
            try:
                raw = await websocket.receive_json()
                if not isinstance(raw, dict):
                    raise ValueError("event must be an object")
                await _handle_client_event(
                    websocket,
                    send_lock,
                    session,
                    redis,
                    user_id,
                    conversation_id,
                    raw,
                )
            except ValidationError:
                await session.rollback()
                await _send_error(
                    websocket,
                    send_lock,
                    ErrorCode.INVALID_ARGUMENT,
                    "WebSocket 消息格式无效",
                    conversation_id=conversation_id,
                )
            except ValueError:
                await _send_error(
                    websocket,
                    send_lock,
                    ErrorCode.INVALID_ARGUMENT,
                    "WebSocket 消息必须是 JSON 对象",
                    conversation_id=conversation_id,
                )
            except AppException as exc:
                await session.rollback()
                await _send_error(
                    websocket,
                    send_lock,
                    exc.code,
                    exc.message,
                    conversation_id=conversation_id,
                )
    except WebSocketDisconnect:
        pass
    except RedisError:
        with suppress(RuntimeError, WebSocketDisconnect):
            await _send_error(
                websocket,
                send_lock,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "实时事件服务暂不可用",
                conversation_id=conversation_id,
            )
            await websocket.close(code=1011)
    finally:
        forwarder.cancel()
        with suppress(asyncio.CancelledError):
            await forwarder
