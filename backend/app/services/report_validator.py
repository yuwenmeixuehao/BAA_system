from typing import Any

from pydantic import ValidationError

from app.schemas.report import ReportIR


class ReportValidator:
    def validate(self, payload: dict[str, Any]) -> ReportIR:
        return ReportIR.model_validate(payload)

    @staticmethod
    def safe_errors(error: ValidationError) -> list[dict[str, Any]]:
        return [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors(include_url=False, include_input=False)
        ]


report_validator = ReportValidator()
