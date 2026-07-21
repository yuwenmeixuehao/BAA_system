from typing import Any

from app.agent.state import AgentState


class BuildEvidenceNode:
    async def __call__(self, state: AgentState) -> AgentState:
        results = state.get("metric_results", {})
        scope = str(state.get("problem_definition", {}).get("time_range") or "未指定")
        evidence: list[dict[str, Any]] = []

        def append(item: dict[str, Any]) -> None:
            item["evidence_id"] = f"ev_{len(evidence) + 1:03d}"
            evidence.append(item)

        for comparison in results.get("comparisons", []):
            change_rate = comparison.get("change_rate")
            file_id = str(comparison.get("file_id"))
            append(
                {
                    "title": f"{comparison.get('metric_field')} 基线对比",
                    "description": (
                        f"{comparison.get('current_period')} 为 {comparison.get('current_value')}，"
                        f"基线 {comparison.get('baseline_period')} 为 "
                        f"{comparison.get('baseline_value')}。"
                    ),
                    "evidence_type": "baseline_comparison",
                    "metric": str(comparison.get("metric_field")),
                    "current_value": comparison.get("current_value"),
                    "baseline_value": comparison.get("baseline_value"),
                    "change_value": comparison.get("absolute_change"),
                    "change_rate": change_rate,
                    "scope": scope,
                    "source_file_ids": [file_id],
                    "formula": str(comparison.get("formula")),
                    "quality_status": evidence_quality(state, file_id),
                    "kind": "comparison",
                }
            )

        for change_group in results.get("dimension_changes", []):
            file_id = str(change_group.get("file_id"))
            for item in change_group.get("items", [])[:5]:
                append(
                    {
                        "title": (
                            f"{change_group.get('dimension')}={item.get('dimension_value')} "
                            "的变化贡献"
                        ),
                        "description": (
                            f"当前值 {item.get('current_value')}，基线值 "
                            f"{item.get('baseline_value')}，变化 {item.get('absolute_change')}。"
                        ),
                        "evidence_type": "dimension_change",
                        "metric": str(change_group.get("metric_field")),
                        "current_value": item.get("current_value"),
                        "baseline_value": item.get("baseline_value"),
                        "change_value": item.get("absolute_change"),
                        "change_rate": item.get("change_rate"),
                        "scope": scope,
                        "source_file_ids": [file_id],
                        "formula": str(change_group.get("formula")),
                        "quality_status": evidence_quality(state, file_id),
                        "kind": "dimension_change",
                        "dimension": change_group.get("dimension"),
                        "dimension_value": item.get("dimension_value"),
                        "impact_share": item.get("impact_share"),
                    }
                )

        for risk in results.get("risk_items", [])[:20]:
            file_id = str(risk.get("file_id"))
            append(
                {
                    "title": f"{risk.get('item')}：{risk_label(str(risk.get('risk_type')))}",
                    "description": (
                        f"库存 {risk.get('stock')}，期间销量 {risk.get('sales')}，"
                        f"覆盖天数 {risk.get('coverage_days')}。"
                    ),
                    "evidence_type": "inventory_risk",
                    "metric": "inventory_coverage",
                    "current_value": risk.get("coverage_days") or risk.get("stock"),
                    "scope": scope,
                    "source_file_ids": [file_id],
                    "formula": str(risk.get("formula")),
                    "quality_status": evidence_quality(state, file_id),
                    "kind": "inventory_risk",
                    "risk_type": risk.get("risk_type"),
                    "item": risk.get("item"),
                    "severity": risk.get("severity"),
                }
            )

        if not evidence:
            for metric in results.get("metrics", [])[:5]:
                file_id = str(metric.get("file_id"))
                append(
                    {
                        "title": f"{metric.get('field')} 指标计算结果",
                        "description": (
                            f"在 {metric.get('scope')} 范围内计算值为 {metric.get('value')}。"
                        ),
                        "evidence_type": "metric_calculation",
                        "metric": str(metric.get("metric")),
                        "current_value": metric.get("value"),
                        "scope": scope,
                        "source_file_ids": [file_id],
                        "formula": str(metric.get("formula")),
                        "quality_status": evidence_quality(
                            state,
                            file_id,
                            scope_status=str(metric.get("scope_status") or ""),
                        ),
                        "kind": "metric",
                    }
                )

        return {
            "evidence_list": evidence,
            "current_step": "build_evidence",
        }


def evidence_quality(
    state: AgentState,
    file_id: str,
    *,
    scope_status: str | None = None,
) -> str:
    if scope_status is not None and scope_status != "verified":
        return "limited"
    quality = state.get("data_quality", {})
    reports = quality.get("files", []) if isinstance(quality, dict) else []
    report = next(
        (item for item in reports if str(item.get("file_id")) == file_id),
        None,
    )
    if not report or not report.get("usable"):
        return "limited"
    metric_field = report.get("metric_field")
    missing_counts = report.get("missing_counts") or {}
    metric_missing = (
        int(missing_counts.get(str(metric_field), 0)) if metric_field else 0
    )
    if (
        metric_missing > 0
        or int(report.get("duplicate_count") or 0) > 0
        or bool(report.get("sample_size_warning"))
        or not report.get("time_field")
        or not report.get("time_min")
        or not report.get("time_max")
    ):
        return "limited"
    return "verified"


def risk_label(risk_type: str) -> str:
    return {
        "stockout": "缺货风险",
        "overstock": "积压风险",
        "slow_moving": "滞销风险",
    }.get(risk_type, "库存异常")
