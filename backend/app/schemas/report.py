import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ReportProblemDefinition(BaseModel):
    question: str
    scope: str
    metric: str
    baseline: str
    scenario: Literal["market_performance", "inventory_anomaly", "general"]
    assumptions: list[str] = Field(default_factory=list)


class KeyMetric(BaseModel):
    metric_id: str
    label: str
    value: float
    unit: str | None = None
    formula: str
    scope: str
    baseline_value: float | None = None
    absolute_change: float | None = None
    change_rate: float | None = None

    @field_validator("value", "baseline_value", "absolute_change", "change_rate")
    @classmethod
    def finite_numbers(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("report metric values must be finite")
        return value


class EvidenceItem(BaseModel):
    evidence_id: str
    title: str
    description: str
    evidence_type: str
    metric: str | None = None
    current_value: float | None = None
    baseline_value: float | None = None
    change_value: float | None = None
    change_rate: float | None = None
    scope: str
    source_file_ids: list[str] = Field(min_length=1)
    formula: str
    quality_status: Literal["verified", "limited"]

    @field_validator("current_value", "baseline_value", "change_value", "change_rate")
    @classmethod
    def finite_evidence_numbers(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("evidence values must be finite")
        return value


class AttributionConclusion(BaseModel):
    conclusion_id: str
    title: str
    description: str
    status: Literal["confirmed", "probable", "to_verify"]
    impact_level: Literal["high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    verification_needed: bool


class MissingDataItem(BaseModel):
    field: str
    reason: str
    impact: str
    required_action: str


class NextAction(BaseModel):
    action_id: str
    title: str
    description: str
    priority: Literal["high", "medium", "low"]
    owner_hint: str | None = None


class ChartSeries(BaseModel):
    name: str
    data: list[float]

    @field_validator("data")
    @classmethod
    def finite_series(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("chart series must contain finite numbers")
        return values


class Visualization(BaseModel):
    chart_id: str
    title: str
    type: Literal["line", "bar", "stackedBar", "pie", "table"]
    dimension: str | None = None
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "Visualization":
        if self.type == "table":
            if not self.columns:
                raise ValueError("table visualization requires columns")
            if len(self.rows) > 500:
                raise ValueError("table visualization exceeds row limit")
            return self
        if not self.categories or not self.series:
            raise ValueError("chart visualization requires categories and series")
        if len(self.categories) > 500:
            raise ValueError("chart visualization exceeds point limit")
        if any(len(series.data) != len(self.categories) for series in self.series):
            raise ValueError("chart category and series lengths must match")
        return self


class SourceFile(BaseModel):
    file_id: str
    file_name: str
    source_type: str
    row_count: int | None = Field(default=None, ge=0)


class GeneratedFile(BaseModel):
    file_type: Literal["html", "md", "json"]
    file_name: str
    storage_key: str
    file_size: int = Field(ge=0)
    sha256: str


class ReportIR(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    task_id: str
    problem_definition: ReportProblemDefinition
    key_metrics: list[KeyMetric] = Field(min_length=1)
    evidence_list: list[EvidenceItem] = Field(min_length=1)
    attribution_conclusions: list[AttributionConclusion] = Field(min_length=1)
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(min_length=1)
    visualizations: list[Visualization] = Field(default_factory=list)
    source_files: list[SourceFile] = Field(min_length=1)
    generated_files: list[GeneratedFile] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ReportIR":
        evidence_ids = [item.evidence_id for item in self.evidence_list]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id must be unique")
        conclusion_ids = [item.conclusion_id for item in self.attribution_conclusions]
        if len(conclusion_ids) != len(set(conclusion_ids)):
            raise ValueError("conclusion_id must be unique")
        known_evidence = set(evidence_ids)
        evidence_by_id = {item.evidence_id: item for item in self.evidence_list}
        for conclusion in self.attribution_conclusions:
            if not set(conclusion.evidence_ids).issubset(known_evidence):
                raise ValueError("conclusion references unknown evidence")
            if conclusion.status == "confirmed" and not conclusion.evidence_ids:
                raise ValueError("confirmed conclusion requires evidence")
            if conclusion.status == "confirmed" and conclusion.verification_needed:
                raise ValueError("confirmed conclusion cannot require verification")
            if conclusion.status == "confirmed" and any(
                evidence_by_id[evidence_id].quality_status != "verified"
                for evidence_id in conclusion.evidence_ids
            ):
                raise ValueError("confirmed conclusion requires verified evidence")
        return self


class GeneratedFileItem(BaseModel):
    file_id: str
    file_type: str
    file_name: str
    file_size: int
    download_url: str


class AnalysisResultResponse(BaseModel):
    task_id: str
    result_id: str
    schema_version: str
    problem_definition: dict[str, Any]
    key_metrics: list[dict[str, Any]]
    evidence_list: list[dict[str, Any]]
    attribution_conclusions: list[dict[str, Any]]
    conclusion_text: str
    missing_data_text: str
    next_actions: list[dict[str, Any]]
    result_markdown: str
    result_file_path: str | None
    report_ir: dict[str, Any]
    generated_files: list[GeneratedFileItem]
    validation_status: str
