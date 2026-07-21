from app.agent.errors import AgentExecutionError
from app.agent.runtime import AgentRuntime
from app.agent.state import AgentState
from app.agent.tools.pandas_analyze import PandasAnalyzeTool


class AnalyzeWithPandasNode:
    def __init__(self, runtime: AgentRuntime, tool: PandasAnalyzeTool) -> None:
        self.runtime = runtime
        self.tool = tool

    async def __call__(self, state: AgentState) -> AgentState:
        result = await self.runtime.run_tool(
            state,
            "analyze_with_pandas",
            "pandas_analyze",
            lambda context: self.tool.run(
                state.get("data_files", []),
                state["problem_definition"],
                context,
            ),
        )
        if not result.ok:
            raise AgentExecutionError(
                result.error_code or "PANDAS_ANALYSIS_FAILED",
                result.summary,
            )
        return {
            "metric_results": {**result.data, "output_files": result.files},
            "current_step": "analyze_with_pandas",
        }
