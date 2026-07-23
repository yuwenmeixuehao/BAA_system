from app.agent.model import ProblemDefinitionExtractor, canonical_metric
from app.agent.state import AgentState


class DefineProblemNode:
    def __init__(self, extractor: ProblemDefinitionExtractor) -> None:
        self.extractor = extractor

    async def __call__(self, state: AgentState) -> AgentState:
        definition = await self.extractor.extract(
            state["question"],
            state.get("recent_messages", []),
        )
        definition.metric = canonical_metric(definition.metric)
        definition.missing_fields = [
            field
            for field in ("metric", "time_range", "baseline")
            if not getattr(definition, field)
        ]
        return {
            "problem_definition": definition.model_dump(mode="json"),
            "current_step": "define_problem",
        }
