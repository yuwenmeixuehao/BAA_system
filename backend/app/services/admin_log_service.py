from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import TaskLog
from app.schemas.admin import AdminTaskLogItem, AdminTaskLogList


class AdminLogService:
    async def list_logs(
        self,
        session: AsyncSession,
        *,
        task_id: str | None,
        trace_id: str | None,
        level: str | None,
        limit: int,
    ) -> AdminTaskLogList:
        query = select(TaskLog)
        if task_id:
            query = query.where(TaskLog.task_id == task_id)
        if trace_id:
            query = query.where(TaskLog.trace_id == trace_id)
        if level:
            query = query.where(TaskLog.log_level == level.lower())
        rows = list(
            await session.scalars(
                query.order_by(TaskLog.created_at.desc()).limit(limit)
            )
        )
        return AdminTaskLogList(
            items=[
                AdminTaskLogItem(
                    log_id=row.id,
                    task_id=row.task_id,
                    log_level=row.log_level,
                    log_type=row.log_type,
                    log_content=row.log_content[:4000],
                    trace_id=row.trace_id,
                    duration_ms=row.duration_ms,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        )


admin_log_service = AdminLogService()
