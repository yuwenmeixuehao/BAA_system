import json
import logging
from collections.abc import Sequence
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import AnalysisTask, TaskEvent
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskEventItem, TaskEventList

logger = logging.getLogger(__name__)


class EventService:
    def __init__(self) -> None:
        self.tasks = TaskRepository()

    async def append(
        self,
        session: AsyncSession,
        task: AnalysisTask,
        event_type: str,
        payload: dict[str, Any],
        *,
        already_locked: bool = False,
    ) -> TaskEvent:
        return (
            await self.append_many(
                session,
                task,
                [(event_type, payload)],
                already_locked=already_locked,
            )
        )[0]

    async def append_many(
        self,
        session: AsyncSession,
        task: AnalysisTask,
        event_specs: Sequence[tuple[str, dict[str, Any]]],
        *,
        already_locked: bool = False,
    ) -> list[TaskEvent]:
        if not event_specs:
            return []
        if not already_locked:
            locked_task = await self.tasks.get_by_id(session, task.id, lock=True)
            if locked_task is None:
                raise RuntimeError(f"task not found while appending events: {task.id}")
        first_seq = await self.tasks.next_event_seq(session, task.id)
        events = [
            TaskEvent(
                task_id=task.id,
                conversation_id=task.conversation_id,
                event_seq=first_seq + offset,
                event_type=event_type,
                payload_json=payload,
            )
            for offset, (event_type, payload) in enumerate(event_specs)
        ]
        session.add_all(events)
        await session.flush()
        return events

    async def list_owned(
        self,
        session: AsyncSession,
        task: AnalysisTask,
        *,
        after_seq: int,
        limit: int | None = None,
    ) -> TaskEventList:
        rows = await self.tasks.list_events(
            session,
            task.id,
            after_seq=after_seq,
            limit=limit or settings.task_event_replay_limit,
        )
        items = [self.to_item(row) for row in rows]
        return TaskEventList(
            items=items,
            last_event_seq=items[-1].event_seq if items else after_seq,
        )

    async def publish(self, redis: Redis, events: list[TaskEvent]) -> None:
        for event in events:
            item = self.to_item(event)
            try:
                await redis.publish(
                    self.channel(event.conversation_id),
                    json.dumps(item.model_dump(mode="json"), ensure_ascii=False),
                )
            except RedisError:
                logger.exception(
                    "task event publish failed",
                    extra={"task_id": event.task_id, "event_seq": event.event_seq},
                )

    @staticmethod
    def to_item(event: TaskEvent) -> TaskEventItem:
        return TaskEventItem(
            type=event.event_type,
            task_id=event.task_id,
            conversation_id=event.conversation_id,
            event_seq=event.event_seq,
            occurred_at=event.created_at,
            payload=event.payload_json,
        )

    @staticmethod
    def channel(conversation_id: str) -> str:
        return f"{settings.task_event_channel_prefix}{conversation_id}"


event_service = EventService()
