from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas.report import (
    AttributionConclusion,
    EvidenceItem,
    GeneratedFile,
    KeyMetric,
    MissingDataItem,
    NextAction,
    ReportIR,
    SourceFile,
    Visualization,
)


class ReportValidator:
    def validate(self, payload: dict[str, Any]) -> ReportIR:
        return ReportIR.model_validate(payload)

    def repair(
        self,
        payload: dict[str, Any],
        validation_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        repaired = deepcopy(payload)
        repaired["key_metrics"] = validated_items(KeyMetric, repaired.get("key_metrics"))
        evidence = unique_validated_items(
            EvidenceItem,
            repaired.get("evidence_list"),
            "evidence_id",
        )
        repaired["evidence_list"] = evidence
        evidence_quality = {
            item["evidence_id"]: item["quality_status"] for item in evidence
        }
        repaired["attribution_conclusions"] = repair_conclusions(
            repaired.get("attribution_conclusions"),
            evidence_quality,
        )
        repaired["missing_data"] = validated_items(
            MissingDataItem,
            repaired.get("missing_data"),
        )
        repaired["next_actions"] = validated_items(
            NextAction,
            repaired.get("next_actions"),
        )
        repaired["visualizations"] = unique_validated_items(
            Visualization,
            repaired.get("visualizations"),
            "chart_id",
        )
        repaired["source_files"] = unique_validated_items(
            SourceFile,
            repaired.get("source_files"),
            "file_id",
        )
        repaired["generated_files"] = validated_items(
            GeneratedFile,
            repaired.get("generated_files"),
        )
        repaired["repair_context"] = {
            "validation_errors": validation_errors,
            "strategy": "deterministic_safe_repair",
        }
        return repaired

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


def validated_items(
    model: type[BaseModel],
    values: object,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for value in values if isinstance(values, list) else []:
        try:
            output.append(model.model_validate(value).model_dump(mode="json"))
        except ValidationError:
            continue
    return output


def unique_validated_items(
    model: type[BaseModel],
    values: object,
    identity_field: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in validated_items(model, values):
        identity = str(item.get(identity_field) or "")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        output.append(item)
    return output


def repair_conclusions(
    values: object,
    evidence_quality: dict[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        conclusion_id = str(item.get("conclusion_id") or "")
        if not conclusion_id or conclusion_id in seen:
            continue
        seen.add(conclusion_id)
        raw_evidence_ids = item.get("evidence_ids")
        evidence_ids = [
            str(evidence_id)
            for evidence_id in (
                raw_evidence_ids if isinstance(raw_evidence_ids, list) else []
            )
            if str(evidence_id) in evidence_quality
        ]
        item["evidence_ids"] = list(dict.fromkeys(evidence_ids))
        has_limited_evidence = any(
            evidence_quality[evidence_id] != "verified"
            for evidence_id in item["evidence_ids"]
        )
        if not item["evidence_ids"]:
            item["status"] = "to_verify"
            item["verification_needed"] = True
            item["confidence"] = min(safe_confidence(item.get("confidence")), 0.49)
        elif item.get("status") == "confirmed" and (
            has_limited_evidence or item.get("verification_needed")
        ):
            item["status"] = "probable"
            item["verification_needed"] = True
            item["confidence"] = min(safe_confidence(item.get("confidence")), 0.7)
        try:
            output.append(
                AttributionConclusion.model_validate(item).model_dump(mode="json")
            )
        except ValidationError:
            continue
    return output


def safe_confidence(value: object) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(confidence, 1.0))
