import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ErrorCode
from app.models.entities import AnalysisTask, Message, TaskEvent
from app.repositories.task_repository import TaskRepository
from app.schemas.task import CancelTaskResult, TaskEventList, TaskSummary
from app.schemas.websocket import UserMessageEvent
from app.services.event_service import event_service
from app.workers.cancellation import cancellation_service
from app.workers.task_queue import TaskQueue

logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = {"queued", "running"}
TERMINAL_TASK_STATUSES = {"success", "failed", "cancelled"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"waiting_input", "success", "failed", "cancelled"},
    "waiting_input": {"queued", "cancelled"},
    "failed": {"queued"},
    "success": set(),
    "cancelled": set(),
}


@dataclass
class TaskCreationOutcome:
    task: AnalysisTask
    message: Message
    events: list[TaskEvent]
    created: bool


class TaskService:
    def __init__(self) -> None:
        self.tasks = TaskRepository()

    async def create_from_message(
        self,
        session: AsyncSession,
        redis: Redis,
        user_id: str,
        request: UserMessageEvent,
    ) -> TaskCreationOutcome:
        conversation = await self.tasks.lock_conversation_owned(
            session,
            request.conversation_id,
            user_id,
        )
        if conversation is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "会话不存在",
                status_code=404,
            )
        conversation_id = conversation.id
        existing = await self.tasks.get_idempotent(
            session,
            user_id,
            conversation_id,
            request.client_msg_id,
        )
        if existing:
            message = await session.get(Message, existing.message_id)
            if message is None:
                raise AppException(ErrorCode.INTERNAL_ERROR, "任务消息不存在", status_code=500)
            events = await self.tasks.list_events(
                session,
                existing.id,
                after_seq=0,
                limit=10,
            )
            if existing.task_status == "queued":
                await self._enqueue_safely(redis, existing.id)
            return TaskCreationOutcome(existing, message, events, False)

        active = await self.tasks.get_active_for_conversation(session, conversation_id)
        if active:
            raise AppException(
                ErrorCode.TASK_ALREADY_RUNNING,
                "当前会话已有进行中的任务",
                status_code=409,
                data={"task_id": active.id, "task_status": active.task_status},
            )

        attachment_ids = list(dict.fromkeys(request.attachment_ids))
        attachments = await self.tasks.owned_attachments(
            session,
            attachment_ids,
            user_id,
            conversation_id,
        )
        if len(attachments) != len(attachment_ids):
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "附件不存在或不属于当前会话",
                status_code=404,
            )

        now = datetime.now(UTC)
        message = Message(
            conversation_id=conversation_id,
            client_msg_id=request.client_msg_id,
            seq_no=await self.tasks.next_message_seq(session, conversation_id),
            role="user",
            message_type="text",
            content=request.content,
        )
        session.add(message)
        await session.flush()
        task = AnalysisTask(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message.id,
            client_msg_id=request.client_msg_id,
            task_status="queued",
            current_step="queued",
            thread_id=str(uuid4()),
            input_text=request.content,
            input_json={"attachment_ids": attachment_ids},
        )
        session.add(task)
        await session.flush()
        message.task_id = task.id
        for attachment in attachments:
            attachment.message_id = message.id
        conversation.status = "active"
        conversation.last_message_at = now
        events = await event_service.append_many(
            session,
            task,
            [
                (
                    "message_start",
                    {
                        "message_id": message.id,
                        "task_id": task.id,
                        "client_msg_id": request.client_msg_id,
                        "role": "user",
                        "seq_no": message.seq_no,
                    },
                ),
                (
                    "task_status",
                    {"task_status": "queued", "current_step": "queued"},
                ),
            ],
            already_locked=True,
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await self.tasks.get_idempotent(
                session,
                user_id,
                conversation_id,
                request.client_msg_id,
            )
            if existing is None:
                raise
            existing_message = await session.get(Message, existing.message_id)
            if existing_message is None:
                raise
            existing_events = await self.tasks.list_events(
                session,
                existing.id,
                after_seq=0,
                limit=10,
            )
            return TaskCreationOutcome(existing, existing_message, existing_events, False)

        await self._enqueue_safely(redis, task.id)
        await event_service.publish(redis, events)
        return TaskCreationOutcome(task, message, events, True)

    async def get_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
    ) -> TaskSummary:
        return self.to_summary(await self.require_owned(session, task_id, user_id))

    async def list_events_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
        *,
        after_seq: int,
    ) -> TaskEventList:
        task = await self.require_owned(session, task_id, user_id)
        return await event_service.list_owned(session, task, after_seq=after_seq)

    async def cancel(
        self,
        session: AsyncSession,
        redis: Redis,
        task_id: str,
        user_id: str,
    ) -> CancelTaskResult:
        task = await self.tasks.get_owned(session, task_id, user_id, lock=True)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        if task.task_status not in {"queued", "running", "waiting_input"}:
            raise AppException(
                ErrorCode.TASK_NOT_CANCELLABLE,
                "当前任务状态不可取消",
                status_code=409,
            )
        task.cancel_requested = True
        events: list[TaskEvent] = []
        if task.task_status in {"queued", "waiting_input"}:
            task.task_status = "cancelled"
            task.current_step = None
            task.finished_at = datetime.now(UTC)
            events.extend(await self._terminal_events(session, task, "cancelled"))
        else:
            events.append(
                await event_service.append(
                    session,
                    task,
                    "task_status",
                    {
                        "task_status": "running",
                        "current_step": task.current_step,
                        "cancel_requested": True,
                    },
                    already_locked=True,
                )
            )
        await session.commit()
        try:
            await cancellation_service.request(redis, task.id)
        except RedisError:
            logger.exception("task cancellation marker write failed", extra={"task_id": task.id})
        await event_service.publish(redis, events)
        return CancelTaskResult(
            task_id=task.id,
            task_status=task.task_status,
            cancel_requested=True,
            accepted=True,
        )

    async def submit_clarification(
        self,
        session: AsyncSession,
        redis: Redis,
        task_id: str,
        user_id: str,
        content: str,
    ) -> list[TaskEvent]:
        task = await self.tasks.get_owned(session, task_id, user_id, lock=True)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        if task.task_status != "waiting_input":
            raise AppException(
                ErrorCode.TASK_NOT_RETRYABLE,
                "任务当前不等待补充信息",
                status_code=409,
            )
        conversation = await self.tasks.lock_conversation_owned(
            session,
            task.conversation_id,
            user_id,
        )
        if conversation is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "会话不存在", status_code=404)
        message = Message(
            conversation_id=task.conversation_id,
            task_id=task.id,
            seq_no=await self.tasks.next_message_seq(session, task.conversation_id),
            role="user",
            message_type="text",
            content=content,
            content_json={"clarification_for_task": task.id},
        )
        session.add(message)
        await session.flush()
        input_json: dict[str, Any] = dict(task.input_json or {})
        clarifications = list(input_json.get("clarifications", []))
        clarifications.append({"content": content, "message_id": message.id})
        input_json["clarifications"] = clarifications
        task.input_json = input_json
        task.task_status = "queued"
        task.current_step = "resume"
        task.cancel_requested = False
        task.finished_at = None
        conversation.last_message_at = datetime.now(UTC)
        event = await event_service.append(
            session,
            task,
            "task_status",
            {"task_status": "queued", "current_step": "resume"},
            already_locked=True,
        )
        await session.commit()
        try:
            await cancellation_service.clear(redis, task.id)
        except RedisError:
            logger.exception("task cancellation marker clear failed", extra={"task_id": task.id})
        await self._enqueue_safely(redis, task.id)
        await event_service.publish(redis, [event])
        return [event]

    async def retry(
        self,
        session: AsyncSession,
        redis: Redis,
        task_id: str,
        user_id: str,
    ) -> TaskSummary:
        task = await self.tasks.get_owned(session, task_id, user_id, lock=True)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        if task.task_status != "failed":
            raise AppException(
                ErrorCode.TASK_NOT_RETRYABLE,
                "只有失败任务可以重试",
                status_code=409,
            )
        task.task_status = "queued"
        task.current_step = "retry"
        task.retry_count += 1
        task.cancel_requested = False
        task.finished_at = None
        task.error_code = None
        task.error_message = None
        event = await event_service.append(
            session,
            task,
            "task_status",
            {
                "task_status": "queued",
                "current_step": "retry",
                "retry_count": task.retry_count,
            },
            already_locked=True,
        )
        await session.commit()
        try:
            await cancellation_service.clear(redis, task.id)
        except RedisError:
            logger.exception(
                "task retry cancellation marker clear failed",
                extra={"task_id": task.id},
            )
        await self._enqueue_safely(redis, task.id)
        await event_service.publish(redis, [event])
        return self.to_summary(task)

    async def transition(
        self,
        session: AsyncSession,
        redis: Redis,
        task_id: str,
        target_status: str,
        *,
        current_step: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        clarification_question: str | None = None,
    ) -> AnalysisTask | None:
        task = await self.tasks.get_by_id(session, task_id, lock=True)
        if task is None:
            return None
        source_status = task.task_status
        if target_status not in ALLOWED_TRANSITIONS.get(source_status, set()):
            return None
        if target_status == "success" and not await self.tasks.has_complete_result(
            session,
            task.id,
        ):
            raise AppException(
                ErrorCode.INTERNAL_ERROR,
                "任务缺少完整结果，不能标记成功",
                status_code=500,
            )
        now = datetime.now(UTC)
        task.task_status = target_status
        task.current_step = current_step
        if target_status == "queued":
            task.finished_at = None
            task.cancel_requested = False
            task.error_code = None
            task.error_message = None
            if source_status == "failed":
                task.retry_count += 1
        if target_status == "running" and task.started_at is None:
            task.started_at = now
        if target_status in TERMINAL_TASK_STATUSES:
            task.finished_at = now
        if target_status == "failed" or error_code:
            task.error_code = error_code or "INTERNAL_ERROR"
            task.error_message = error_message or "任务执行失败"
        event_specs: list[tuple[str, dict[str, Any]]] = [
            ("task_status", {"task_status": target_status, "current_step": current_step})
        ]
        if task.error_code and target_status in TERMINAL_TASK_STATUSES:
            event_specs.append(
                (
                    "error",
                    {"error_code": task.error_code, "message": task.error_message},
                )
            )
        if target_status == "waiting_input" and clarification_question:
            event_specs.append(
                (
                    "clarification_required",
                    {"question": clarification_question},
                )
            )
        if target_status in TERMINAL_TASK_STATUSES:
            event_specs.append(
                (
                    "done",
                    {"task_status": target_status, "finished_at": now.isoformat()},
                )
            )
        events = await event_service.append_many(
            session,
            task,
            event_specs,
            already_locked=True,
        )
        await session.commit()
        await event_service.publish(redis, events)
        return task

    async def require_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
    ) -> AnalysisTask:
        task = await self.tasks.get_owned(session, task_id, user_id)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        return task

    async def _terminal_events(
        self,
        session: AsyncSession,
        task: AnalysisTask,
        status: str,
    ) -> list[TaskEvent]:
        now = task.finished_at or datetime.now(UTC)
        return await event_service.append_many(
            session,
            task,
            [
                ("task_status", {"task_status": status, "current_step": None}),
                ("done", {"task_status": status, "finished_at": now.isoformat()}),
            ],
            already_locked=True,
        )

    @staticmethod
    def to_summary(task: AnalysisTask) -> TaskSummary:
        return TaskSummary(
            task_id=task.id,
            conversation_id=task.conversation_id,
            message_id=task.message_id,
            client_msg_id=task.client_msg_id,
            task_status=task.task_status,  # type: ignore[arg-type]
            current_step=task.current_step,
            cancel_requested=task.cancel_requested,
            retry_count=task.retry_count,
            started_at=task.started_at,
            finished_at=task.finished_at,
            error_code=task.error_code,
            error_message=task.error_message,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    async def _enqueue_safely(redis: Redis, task_id: str) -> None:
        try:
            await TaskQueue(redis).enqueue(task_id)
        except RedisError:
            logger.exception("task enqueue failed", extra={"task_id": task_id})


task_service = TaskService()
