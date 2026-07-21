from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.entities import TaskLog
from app.services.event_service import event_service
from app.services.task_service import task_service


class AgentEventEmitter:
    """Persists events first; the existing event service publishes them afterwards."""

    def __init__(
        self,
        redis: Redis,
        sessions: async_sessionmaker[AsyncSession],
    ) -> None:
        self.redis = redis
        self.sessions = sessions

    async def node(
        self,
        task_id: str,
        node_name: str,
        node_status: str,
        *,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "task_status": "running",
            "current_step": node_name,
            "node_name": node_name,
            "node_status": node_status,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if error_code:
            payload["error_code"] = error_code
        await self._persist(task_id, "task_status", payload, duration_ms=duration_ms)

    async def tool(
        self,
        task_id: str,
        node_name: str,
        tool_name: str,
        tool_status: str,
        *,
        summary: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        event_type = "tool_start" if tool_status == "started" else "tool_finish"
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_status": tool_status,
            "current_step": node_name,
        }
        if summary:
            payload["summary"] = summary
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if error_code:
            payload["error_code"] = error_code
        await self._persist(task_id, event_type, payload, duration_ms=duration_ms)

    async def report_retry(self, task_id: str, report_retry_count: int) -> None:
        async with self.sessions() as session:
            task = await task_service.tasks.get_by_id(session, task_id, lock=True)
            if task is None:
                return
            task.retry_count += 1
            payload = {
                "task_status": "running",
                "current_step": "build_report_ir",
                "retry_scope": "report_ir_validation",
                "retry_count": task.retry_count,
                "report_retry_count": report_retry_count,
            }
            session.add(
                TaskLog(
                    task_id=task_id,
                    log_level="info",
                    log_type="retry",
                    log_content=(
                        "Report IR validation retry "
                        f"{report_retry_count}; task retry count {task.retry_count}"
                    ),
                    trace_id=f"task:{task_id}",
                )
            )
            event = await event_service.append(
                session,
                task,
                "task_status",
                payload,
                already_locked=True,
            )
            await session.commit()
        await event_service.publish(self.redis, [event])

    async def _persist(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        duration_ms: int | None,
    ) -> None:
        async with self.sessions() as session:
            task = await task_service.tasks.get_by_id(session, task_id, lock=True)
            if task is None:
                return
            if event_type == "task_status" and task.task_status == "running":
                task.current_step = str(payload["current_step"])
            session.add(
                TaskLog(
                    task_id=task_id,
                    log_level="error" if payload.get("error_code") else "info",
                    log_type=event_type,
                    log_content=str(payload.get("summary") or payload),
                    trace_id=f"task:{task_id}",
                    duration_ms=duration_ms,
                )
            )
            event = await event_service.append(
                session,
                task,
                event_type,
                payload,
                already_locked=True,
            )
            await session.commit()
        await event_service.publish(self.redis, [event])
