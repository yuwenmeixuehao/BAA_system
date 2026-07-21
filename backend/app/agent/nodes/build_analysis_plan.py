from app.agent.model import AnalysisPlanner
from app.agent.state import AgentState


class BuildAnalysisPlanNode:
    def __init__(self, planner: AnalysisPlanner) -> None:
        self.planner = planner

    async def __call__(self, state: AgentState) -> AgentState:
        plan = await self.planner.build(
            state["question"],
            state["problem_definition"],
            state.get("attachment_ids", []),
        )
        return {
            "analysis_plan": [item.model_dump(mode="json") for item in plan.analysis_plan],
            "query_specs": [item.model_dump(mode="json") for item in plan.query_specs],
            "current_step": "build_analysis_plan",
        }
