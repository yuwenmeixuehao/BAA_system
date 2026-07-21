from typing import Any

from app.agent.state import AgentState
from app.services.report_validator import report_validator

METRIC_LABELS = {
    "sales_amount": "销售额",
    "profit": "利润",
    "order_count": "订单量",
    "conversion_rate": "转化率",
    "inventory": "库存量",
    "customer_count": "客户数",
}


class BuildReportIRNode:
    async def __call__(self, state: AgentState) -> AgentState:
        if (
            int(state.get("report_retry_count", 0)) > 0
            and state.get("report_ir")
            and state.get("report_validation_errors")
        ):
            return {
                "report_ir": report_validator.repair(
                    state["report_ir"],
                    state["report_validation_errors"],
                ),
                "report_valid": False,
                "current_step": "build_report_ir",
            }
        definition = state["problem_definition"]
        results = state.get("metric_results", {})
        scenario = str(results.get("scenario") or "general")
        report = {
            "schema_version": "1.0",
            "task_id": state["task_id"],
            "problem_definition": {
                "question": state["question"],
                "scope": build_scope(definition),
                "metric": str(definition.get("metric")),
                "baseline": str(definition.get("baseline")),
                "scenario": scenario,
                "assumptions": build_assumptions(state),
            },
            "key_metrics": build_key_metrics(results),
            "evidence_list": state.get("evidence_list", []),
            "attribution_conclusions": state.get("attribution_candidates", []),
            "missing_data": build_missing_data(state),
            "next_actions": build_next_actions(state, scenario),
            "visualizations": build_visualizations(results, state.get("evidence_list", [])),
            "source_files": build_source_files(state.get("data_files", [])),
            "generated_files": [],
        }
        return {
            "report_ir": report,
            "report_valid": False,
            "current_step": "build_report_ir",
        }


def build_scope(definition: dict[str, Any]) -> str:
    dimensions = list(definition.get("dimensions") or [])
    dimension_text = f"，按 {', '.join(dimensions)} 拆解" if dimensions else ""
    return f"{definition.get('time_range')}，基线 {definition.get('baseline')}{dimension_text}"


def build_assumptions(state: AgentState) -> list[str]:
    assumptions: list[str] = []
    for metric in state.get("metric_results", {}).get("metrics", []):
        if metric.get("scope_status") != "verified":
            assumptions.append("数据缺少可验证时间字段，指标范围按文件内容解释")
    return list(dict.fromkeys(assumptions))


def build_key_metrics(results: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = {
        (str(item.get("file_id")), str(item.get("metric_field"))): item
        for item in results.get("comparisons", [])
    }
    output: list[dict[str, Any]] = []
    for metric in results.get("metrics", []):
        comparison = comparisons.get((str(metric.get("file_id")), str(metric.get("field"))))
        canonical = str(metric.get("metric"))
        output.append(
            {
                "metric_id": f"m_{len(output) + 1:03d}",
                "label": METRIC_LABELS.get(canonical, str(metric.get("field"))),
                "value": metric.get("value"),
                "unit": metric_unit(canonical),
                "formula": str(metric.get("formula")),
                "scope": str(metric.get("scope")),
                "baseline_value": comparison.get("baseline_value") if comparison else None,
                "absolute_change": comparison.get("absolute_change") if comparison else None,
                "change_rate": comparison.get("change_rate") if comparison else None,
            }
        )
    for metric in results.get("scenario_metrics", []):
        output.append(
            {
                "metric_id": f"m_{len(output) + 1:03d}",
                "label": str(metric.get("label") or metric.get("metric")),
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "formula": str(metric.get("formula")),
                "scope": "当前分析范围",
            }
        )
    return output


def metric_unit(metric: str) -> str | None:
    return {
        "sales_amount": "currency",
        "profit": "currency",
        "order_count": "count",
        "conversion_rate": "ratio",
        "inventory": "count",
        "customer_count": "count",
    }.get(metric)


def build_missing_data(state: AgentState) -> list[dict[str, str]]:
    messages: list[str] = []
    messages.extend(str(item) for item in state.get("data_quality", {}).get("gaps", []))
    messages.extend(
        str(item.get("message"))
        for item in state.get("metric_results", {}).get("data_gaps", [])
        if item.get("message")
    )
    definition = state.get("problem_definition", {})
    if definition.get("baseline") and not state.get("metric_results", {}).get("comparisons"):
        messages.append("缺少可计算的基线期间数据，不能形成完整变化率")
    return [
        {
            "field": f"gap_{index:03d}",
            "reason": message,
            "impact": "相关结论的置信度或可解释范围受限",
            "required_action": "补充对应字段或期间数据后重新执行任务",
        }
        for index, message in enumerate(dict.fromkeys(messages), start=1)
    ]


def build_next_actions(state: AgentState, scenario: str) -> list[dict[str, Any]]:
    conclusions = state.get("attribution_candidates", [])
    primary = conclusions[0].get("title") if conclusions else "主要异常项"
    if scenario == "inventory_anomaly":
        actions = [
            (
                "核查高风险商品",
                f"优先核查报告中的缺货、积压和滞销商品：{primary}",
                "high",
                "库存/采购负责人",
            ),
            (
                "复核补货参数",
                "结合交付周期和近期销量复核安全库存与补货点",
                "high",
                "供应链负责人",
            ),
            (
                "建立风险复测",
                "补充入库、出库和在途数据后再次计算覆盖天数",
                "medium",
                "数据分析人员",
            ),
        ]
    elif scenario == "market_performance":
        actions = [
            (
                "复核主要变化维度",
                f"围绕 {primary} 检查活动、价格和流量变化",
                "high",
                "经营负责人",
            ),
            (
                "补齐驱动数据",
                "关联投放费用、访问量、转化数和退款数据验证深层原因",
                "high",
                "市场/数据团队",
            ),
            (
                "设置跟踪指标",
                "按报告维度持续跟踪销售额、订单量、客单价和转化率",
                "medium",
                "运营负责人",
            ),
        ]
    else:
        actions = [
            ("复核关键证据", f"优先复核 {primary} 的业务口径和源数据", "high", "业务负责人"),
            ("补充验证数据", "针对待验证结论补充基线和驱动字段", "medium", "数据分析人员"),
        ]
    return [
        {
            "action_id": f"a_{index:03d}",
            "title": title,
            "description": description,
            "priority": priority,
            "owner_hint": owner,
        }
        for index, (title, description, priority, owner) in enumerate(actions, start=1)
    ]


def build_visualizations(
    results: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    visualizations: list[dict[str, Any]] = []
    for trend in results.get("trends", [])[:2]:
        points = trend.get("points", [])
        if points:
            visualizations.append(
                {
                    "chart_id": f"chart_{len(visualizations) + 1:03d}",
                    "title": f"{trend.get('metric_field')} 月度趋势",
                    "type": "line",
                    "dimension": "period",
                    "categories": [str(item.get("period")) for item in points],
                    "series": [
                        {
                            "name": str(trend.get("metric_field")),
                            "data": [float(item.get("value") or 0.0) for item in points],
                        }
                    ],
                }
            )
    for change in results.get("dimension_changes", [])[:2]:
        items = change.get("items", [])[:12]
        if items:
            visualizations.append(
                {
                    "chart_id": f"chart_{len(visualizations) + 1:03d}",
                    "title": f"按{change.get('dimension')}的基线对比",
                    "type": "bar",
                    "dimension": str(change.get("dimension")),
                    "categories": [str(item.get("dimension_value")) for item in items],
                    "series": [
                        {
                            "name": str(change.get("current_period")),
                            "data": [float(item.get("current_value") or 0.0) for item in items],
                        },
                        {
                            "name": str(change.get("baseline_period")),
                            "data": [float(item.get("baseline_value") or 0.0) for item in items],
                        },
                    ],
                }
            )
    risks = results.get("risk_items", [])[:50]
    if risks:
        visualizations.append(
            {
                "chart_id": f"chart_{len(visualizations) + 1:03d}",
                "title": "库存风险明细",
                "type": "table",
                "columns": ["item", "risk_type", "severity", "stock", "sales", "coverage_days"],
                "rows": risks,
            }
        )
    if not visualizations:
        visualizations.append(
            {
                "chart_id": "chart_001",
                "title": "证据明细",
                "type": "table",
                "columns": ["evidence_id", "title", "description", "quality_status"],
                "rows": evidence[:100],
            }
        )
    return visualizations


def build_source_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "file_id": str(item.get("file_id")),
            "file_name": str(item.get("file_name")),
            "source_type": str(item.get("source_type")),
            "row_count": item.get("row_count"),
        }
        for item in files
        if item.get("source_type") != "analysis"
    ]
