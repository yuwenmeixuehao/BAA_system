from app.agent.errors import AgentExecutionError
from app.agent.runtime import AgentRuntime
from app.agent.state import AgentState
from app.agent.tools.db_query import DbQueryTool
from app.agent.tools.file_read import FileReadTool


class QueryDataNode:
    def __init__(
        self,
        runtime: AgentRuntime,
        file_read: FileReadTool,
        db_query: DbQueryTool,
    ) -> None:
        self.runtime = runtime
        self.file_read = file_read
        self.db_query = db_query

    async def __call__(self, state: AgentState) -> AgentState:
        data_files: list[dict[str, object]] = []
        query_specs: list[dict[str, object]] = list(state.get("query_specs", []))
        attachment_ids = state.get("attachment_ids", [])
        if attachment_ids:
            for attachment_id in attachment_ids:
                result = await self.runtime.run_tool(
                    state,
                    "query_data",
                    "file_read",
                    lambda context, current_id=attachment_id: self.file_read.run(
                        current_id,
                        context,
                    ),
                )
                if not result.ok:
                    raise AgentExecutionError(
                        result.error_code or "FILE_READ_FAILED",
                        result.summary,
                    )
                data_files.extend(result.files)
                query_specs.append(
                    {
                        "execution": "file_read",
                        "source_type": "attachment",
                        "attachment_id": attachment_id,
                    }
                )
        else:
            objective = state["question"]
            result = await self.runtime.run_tool(
                state,
                "query_data",
                "db_query",
                lambda context: self.db_query.run(objective, context),
            )
            if not result.ok:
                raise AgentExecutionError(
                    result.error_code or "DATA_QUERY_FAILED",
                    result.summary,
                )
            data_files.extend(result.files)
            query_specs.append(
                {
                    "execution": "db_query",
                    "source_type": "data_agent",
                    "objective": objective,
                    "read_only": True,
                }
            )
        if not data_files:
            raise AgentExecutionError("NO_ANALYSIS_DATA", "没有取得可供分析的数据")
        return {
            "query_specs": query_specs,
            "data_files": data_files,
            "current_step": "query_data",
        }
