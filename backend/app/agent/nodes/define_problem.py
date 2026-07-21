from app.agent.model import ProblemDefinitionExtractor
from app.agent.state import AgentState


class DefineProblemNode:
    def __init__(self, extractor: ProblemDefinitionExtractor) -> None:
        self.extractor = extractor

    async def __call__(self, state: AgentState) -> AgentState:
        definition = await self.extractor.extract(
            state["question"],
            state.get("recent_messages", []),
        )
        return {
            "problem_definition": definition.model_dump(mode="json"),
            "current_step": "define_problem",
        }
