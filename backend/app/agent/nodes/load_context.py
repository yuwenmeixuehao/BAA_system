from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.errors import AgentExecutionError
from app.agent.state import AgentState
from app.core.config import Settings
from app.models.entities import AnalysisTask, ContextSummary, Message


class LoadContextNode:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.settings = settings

    async def __call__(self, state: AgentState) -> AgentState:
        task_id = state["task_id"]
        async with self.sessions() as session:
            task = await session.get(AnalysisTask, task_id)
            if task is None:
                raise AgentExecutionError("TASK_NOT_FOUND", "待分析任务不存在")

            summary = await session.scalar(
                select(ContextSummary)
                .where(ContextSummary.conversation_id == task.conversation_id)
                .order_by(ContextSummary.end_seq_no.desc())
                .limit(1)
            )
            message_query = select(Message).where(
                Message.conversation_id == task.conversation_id
            )
            if summary:
                message_query = message_query.where(Message.seq_no > summary.end_seq_no)
            message_result = await session.scalars(
                message_query.order_by(Message.seq_no.desc()).limit(
                    self.settings.agent_context_message_limit
                )
            )
            messages = list(reversed(list(message_result)))

        input_json = dict(task.input_json or {})
        clarifications_by_id = {
            item.get("message_id"): item
            for item in input_json.get("clarifications", [])
            if isinstance(item, dict)
        }
        recent_messages: list[dict[str, object]] = []
        for message in messages:
            clarification = clarifications_by_id.get(message.id)
            recent_messages.append(
                {
                    "message_id": message.id,
                    "seq_no": message.seq_no,
                    "role": message.role,
                    "content": (message.content or "")[:4000],
                    "clarification_for_task": bool(clarification),
                }
            )

        return {
            "task_id": task.id,
            "conversation_id": task.conversation_id,
            "user_id": task.user_id,
            "question": task.input_text,
            "attachment_ids": list(input_json.get("attachment_ids", [])),
            "recent_messages": recent_messages,
            "context_summary": summary.summary_text if summary else None,
            "retry_count": task.retry_count,
            "cancellation_requested": task.cancel_requested,
            "current_step": "load_context",
            "task_status": task.task_status,
            "error": None,
        }
