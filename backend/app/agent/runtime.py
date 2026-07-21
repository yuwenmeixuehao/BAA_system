import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from app.agent.errors import AgentExecutionError
from app.agent.events import AgentEventEmitter
from app.agent.state import AgentState
from app.agent.tools.base import ToolContext, ToolResult

NodeCallable = Callable[[AgentState], Awaitable[AgentState]]
T = TypeVar("T")


class AgentRuntime:
    def __init__(
        self,
        emitter: AgentEventEmitter,
        check_cancelled: Callable[[], Awaitable[None]],
        workspace_root: Path,
    ) -> None:
        self.emitter = emitter
        self.check_cancelled = check_cancelled
        self.workspace_root = workspace_root.expanduser().resolve()

    def wrap_node(self, node_name: str, node: NodeCallable) -> NodeCallable:
        async def wrapped(state: AgentState) -> AgentState:
            await self.check_cancelled()
            await self.emitter.node(state["task_id"], node_name, "started")
            started_at = time.perf_counter()
            try:
                update = await node(state)
                await self.check_cancelled()
            except AgentExecutionError as exc:
                duration = round((time.perf_counter() - started_at) * 1000)
                await self.emitter.node(
                    state["task_id"],
                    node_name,
                    "failed",
                    duration_ms=duration,
                    error_code=exc.error_code,
                )
                raise
            except Exception:
                duration = round((time.perf_counter() - started_at) * 1000)
                await self.emitter.node(
                    state["task_id"],
                    node_name,
                    "failed",
                    duration_ms=duration,
                    error_code="UNEXPECTED_NODE_ERROR",
                )
                raise
            duration = round((time.perf_counter() - started_at) * 1000)
            await self.emitter.node(
                state["task_id"],
                node_name,
                "finished",
                duration_ms=duration,
            )
            return update

        return wrapped

    async def run_tool(
        self,
        state: AgentState,
        node_name: str,
        tool_name: str,
        operation: Callable[[ToolContext], Awaitable[ToolResult]],
    ) -> ToolResult:
        await self.check_cancelled()
        await self.emitter.tool(state["task_id"], node_name, tool_name, "started")
        started_at = time.perf_counter()
        context = ToolContext(
            user_id=state["user_id"],
            conversation_id=state["conversation_id"],
            task_id=state["task_id"],
            workspace_root=self.workspace_root,
            trace_id=f"task:{state['task_id']}",
        )
        result = await operation(context)
        duration = round((time.perf_counter() - started_at) * 1000)
        await self.emitter.tool(
            state["task_id"],
            node_name,
            tool_name,
            "finished" if result.ok else "failed",
            summary=result.summary,
            duration_ms=duration,
            error_code=result.error_code,
        )
        await self.check_cancelled()
        return result
