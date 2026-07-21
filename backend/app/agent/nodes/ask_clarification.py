from app.agent.model import ClarificationGenerator
from app.agent.state import AgentState


class AskClarificationNode:
    def __init__(self, generator: ClarificationGenerator) -> None:
        self.generator = generator

    async def __call__(self, state: AgentState) -> AgentState:
        question = await self.generator.generate(
            state["question"],
            state["problem_definition"],
            state.get("recent_messages", []),
        )
        return {
            "clarification_question": question,
            "current_step": "ask_clarification",
        }
