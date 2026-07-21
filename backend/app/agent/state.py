from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator


class ProblemDefinition(BaseModel):
    metric: str | None = Field(default=None, description="Canonical metric name")
    subject: str | None = Field(default=None, description="Business object being analysed")
    time_range: str | None = Field(default=None, description="Requested analysis period")
    baseline: str | None = Field(default=None, description="Comparison baseline")
    analysis_goal: str = Field(description="The user's analysis objective")
    dimensions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    extraction_method: str = "rules"

    @model_validator(mode="after")
    def populate_missing_fields(self) -> "ProblemDefinition":
        required = {
            "metric": self.metric,
            "time_range": self.time_range,
            "baseline": self.baseline,
        }
        self.missing_fields = [name for name, value in required.items() if not value]
        return self


class ClarificationOutput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AnalysisPlanStep(BaseModel):
    step: Literal["query_data", "validate_data", "analyze_with_pandas"]
    goal: str = Field(min_length=1, max_length=500)
    dimensions: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class QuerySpec(BaseModel):
    objective: str = Field(min_length=1, max_length=1000)
    source_preference: Literal["auto", "attachment", "data_agent"] = "auto"
    required_fields: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_range: str
    baseline: str


class AnalysisPlanOutput(BaseModel):
    analysis_plan: list[AnalysisPlanStep] = Field(min_length=1, max_length=10)
    query_specs: list[QuerySpec] = Field(min_length=1, max_length=10)


class AgentState(TypedDict, total=False):
    task_id: str
    conversation_id: str
    user_id: str
    question: str
    attachment_ids: list[str]
    recent_messages: list[dict[str, Any]]
    context_summary: str | None
    problem_definition: dict[str, Any]
    analysis_plan: list[dict[str, Any]]
    query_specs: list[dict[str, Any]]
    data_files: list[dict[str, Any]]
    data_quality: dict[str, Any]
    metric_results: dict[str, Any]
    evidence_list: list[dict[str, Any]]
    attribution_candidates: list[dict[str, Any]]
    report_ir: dict[str, Any]
    report_valid: bool
    report_retry_count: int
    report_validation_errors: list[dict[str, Any]]
    generated_files: list[dict[str, Any]]
    current_step: str
    task_status: str
    retry_count: int
    cancellation_requested: bool
    clarification_question: str | None
    error: dict[str, Any] | None
