from app.agent.errors import AgentExecutionError
from app.agent.state import AgentState
from app.reporting.renderer import ReportRenderer
from app.schemas.report import ReportIR


class RenderReportNode:
    def __init__(self, renderer: ReportRenderer) -> None:
        self.renderer = renderer

    async def __call__(self, state: AgentState) -> AgentState:
        if not state.get("report_valid"):
            raise AgentExecutionError("REPORT_INVALID", "报告未经校验，禁止渲染")
        report = ReportIR.model_validate(state["report_ir"])
        rendered = self.renderer.render(report)
        return {
            "report_ir": rendered.report_ir,
            "generated_files": rendered.generated_files,
            "current_step": "render_report",
        }
