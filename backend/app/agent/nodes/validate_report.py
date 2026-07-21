from pydantic import ValidationError

from app.agent.errors import AgentExecutionError
from app.agent.state import AgentState
from app.services.report_validator import report_validator


class ValidateReportNode:
    async def __call__(self, state: AgentState) -> AgentState:
        retry_count = int(state.get("report_retry_count", 0))
        try:
            report = report_validator.validate(state["report_ir"])
        except ValidationError as exc:
            errors = report_validator.safe_errors(exc)
            if retry_count >= 1:
                raise AgentExecutionError(
                    "REPORT_INVALID",
                    "报告结构校验失败，未生成不可验证的正式报告",
                    details={"validation_errors": errors},
                ) from exc
            return {
                "report_valid": False,
                "report_retry_count": retry_count + 1,
                "report_validation_errors": errors,
                "current_step": "validate_report",
            }
        return {
            "report_ir": report.model_dump(mode="json"),
            "report_valid": True,
            "report_validation_errors": [],
            "current_step": "validate_report",
        }
