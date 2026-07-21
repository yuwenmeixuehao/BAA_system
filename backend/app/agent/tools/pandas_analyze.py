import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.agent.model import DIMENSION_ALIASES, METRIC_ALIASES
from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.base import ToolContext, ToolResult
from app.agent.tools.tabular import json_safe, read_dataframe
from app.core.config import Settings


class PandasAnalyzeTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(
        self,
        data_files: list[dict[str, Any]],
        problem_definition: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        storage = WorkspaceStorage(context.workspace_root)
        frames: list[tuple[dict[str, Any], pd.DataFrame]] = []
        try:
            for file_ref in data_files:
                storage_key = str(file_ref["storage_key"])
                file_name = str(file_ref["file_name"])
                frame = read_dataframe(
                    storage.resolve_key(storage_key),
                    file_name,
                    self.settings.agent_max_rows,
                )
                frames.append((file_ref, frame))
        except Exception as exc:
            return ToolResult(
                ok=False,
                summary=f"Pandas 读取分析数据失败：{str(exc)[:200]}",
                error_code="PANDAS_READ_FAILED",
            )
        if not frames:
            return ToolResult(
                ok=False,
                summary="没有可供 Pandas 分析的数据文件",
                error_code="NO_ANALYSIS_DATA",
            )

        requested_metric = str(problem_definition.get("metric") or "")
        results: dict[str, Any] = {
            "scenario": detect_scenario(problem_definition, frames),
            "metrics": [],
            "comparisons": [],
            "trends": [],
            "structures": [],
            "contributions": [],
            "dimension_changes": [],
            "anomalies": [],
            "scenario_metrics": [],
            "risk_items": [],
            "data_gaps": [],
        }
        metric_columns_found = False
        scope_empty = False
        for file_ref, frame in frames:
            metric_column = find_metric_column(frame, requested_metric)
            if metric_column is None:
                results["data_gaps"].append(
                    {
                        "file_id": file_ref["file_id"],
                        "message": f"未找到指标 {requested_metric} 对应的数值字段",
                    }
                )
                continue
            metric_columns_found = True
            scoped_frame, scope_status = apply_time_scope(
                frame,
                str(problem_definition.get("time_range") or ""),
            )
            if scope_status.startswith("unverified"):
                results["data_gaps"].append(
                    {
                        "file_id": file_ref["file_id"],
                        "message": f"时间范围未能验证：{scope_status}",
                    }
                )
            if scoped_frame.empty:
                scope_empty = True
                results["data_gaps"].append(
                    {
                        "file_id": file_ref["file_id"],
                        "message": "目标时间范围内没有数据",
                    }
                )
                continue
            values = pd.to_numeric(scoped_frame[metric_column], errors="coerce")
            valid = values.dropna()
            if valid.empty:
                results["data_gaps"].append(
                    {
                        "file_id": file_ref["file_id"],
                        "message": f"字段 {metric_column} 没有可计算的数值",
                    }
                )
                continue
            results["metrics"].append(
                {
                    "file_id": file_ref["file_id"],
                    "metric": requested_metric,
                    "field": metric_column,
                    "aggregation": "sum",
                    "value": float(valid.sum()),
                    "average": float(valid.mean()),
                    "minimum": float(valid.min()),
                    "maximum": float(valid.max()),
                    "valid_count": int(valid.count()),
                    "formula": f"SUM({metric_column})",
                    "scope": problem_definition.get("time_range"),
                    "scope_status": scope_status,
                }
            )
            full_values = pd.to_numeric(frame[metric_column], errors="coerce")
            trends = build_trend(frame, full_values, metric_column, file_ref)
            results["trends"].extend(trends)
            comparison = build_comparison(
                trends,
                str(problem_definition.get("baseline") or ""),
            )
            if comparison:
                results["comparisons"].append(comparison)
            structures, contributions = build_structures(
                scoped_frame,
                values,
                metric_column,
                requested_dimensions=list(problem_definition.get("dimensions") or []),
                file_ref=file_ref,
            )
            results["structures"].extend(structures)
            results["contributions"].extend(contributions)
            results["dimension_changes"].extend(
                build_dimension_changes(
                    frame,
                    metric_column,
                    list(problem_definition.get("dimensions") or []),
                    str(problem_definition.get("time_range") or ""),
                    str(problem_definition.get("baseline") or ""),
                    file_ref,
                )
            )
            results["anomalies"].extend(
                build_anomalies(scoped_frame, values, metric_column, file_ref)
            )
            scenario_output = analyze_scenario(
                str(results["scenario"]),
                scoped_frame,
                file_ref,
            )
            results["scenario_metrics"].extend(scenario_output["metrics"])
            results["risk_items"].extend(scenario_output["risk_items"])

        if not results["metrics"]:
            error_code = "METRIC_FIELD_NOT_FOUND"
            summary = "数据中没有与目标指标匹配的可计算数值字段"
            if metric_columns_found and scope_empty:
                error_code = "NO_DATA_IN_SCOPE"
                summary = "目标时间范围内没有可计算数据"
            return ToolResult(
                ok=False,
                summary=summary,
                data=json_safe(results),
                error_code=error_code,
            )

        results = json_safe(results)
        storage_key = f"tasks/{context.task_id}/analysis/pandas_analysis.json"
        storage.write_json(storage_key, results)
        output_ref = {
            "file_id": f"analysis:{context.task_id}",
            "source_type": "analysis",
            "storage_key": storage_key,
            "file_name": "pandas_analysis.json",
            "format": "json",
        }
        return ToolResult(
            ok=True,
            summary=(
                f"Pandas 已计算 {len(results['metrics'])} 组指标、"
                f"{len(results['comparisons'])} 组基线对比、"
                f"{len(results['contributions'])} 组贡献和 "
                f"{len(results['anomalies'])} 个异常点；"
                f"业务场景为 {results['scenario']}"
            ),
            files=[output_ref],
            data=results,
        )


def find_metric_column(frame: pd.DataFrame, metric: str) -> str | None:
    numeric_columns = [
        str(column)
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
        or pd.to_numeric(frame[column], errors="coerce").notna().any()
    ]
    aliases = (metric, *METRIC_ALIASES.get(metric, ()))
    normalized = {
        column.lower().replace(" ", "").replace("_", ""): column
        for column in numeric_columns
    }
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace("_", "")
        if key in normalized:
            return normalized[key]
    return None


def normalize_column(value: str) -> str:
    return value.lower().replace(" ", "").replace("_", "").replace("-", "")


def find_alias_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized = {normalize_column(str(column)): str(column) for column in frame.columns}
    for alias in aliases:
        key = normalize_column(alias)
        if key in normalized:
            return normalized[key]
    return None


def detect_scenario(
    problem_definition: dict[str, Any],
    frames: list[tuple[dict[str, Any], pd.DataFrame]],
) -> str:
    text = " ".join(
        str(problem_definition.get(key) or "")
        for key in ("analysis_goal", "metric", "subject")
    ).lower()
    columns = " ".join(
        str(column).lower() for _, frame in frames for column in frame.columns
    )
    inventory_tokens = ("库存", "存货", "缺货", "stock", "inventory")
    if any(token in f"{text} {columns}" for token in inventory_tokens):
        return "inventory_anomaly"
    if any(
        token in f"{text} {columns}"
        for token in ("销售", "营收", "订单", "渠道", "市场", "sales", "revenue", "campaign")
    ):
        return "market_performance"
    return "general"


def find_date_column(frame: pd.DataFrame) -> str | None:
    return next(
        (
            str(column)
            for column in frame.columns
            if any(
                token in str(column).lower()
                for token in ("date", "time", "日期", "时间", "月份")
            )
        ),
        None,
    )


def apply_time_scope(frame: pd.DataFrame, time_range: str) -> tuple[pd.DataFrame, str]:
    date_column = find_date_column(frame)
    if date_column is None:
        return frame, "unverified:no_date_field"
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    if not dates.notna().any():
        return frame, "unverified:invalid_date_field"
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    mask: pd.Series | None = None
    if time_range == "current_month":
        mask = (dates.dt.year == now.year) & (dates.dt.month == now.month)
    elif time_range == "previous_month":
        period = pd.Period(now, freq="M") - 1
        mask = (dates.dt.year == period.year) & (dates.dt.month == period.month)
    elif time_range == "current_quarter":
        mask = (dates.dt.year == now.year) & (dates.dt.quarter == ((now.month - 1) // 3 + 1))
    elif time_range == "current_year":
        mask = dates.dt.year == now.year
    else:
        month = re.fullmatch(r"(20\d{2})年(\d{1,2})月", time_range)
        quarter = re.fullmatch(r"(20\d{2})年(?:第)?([一二三四1234])季度", time_range)
        if month:
            mask = (dates.dt.year == int(month.group(1))) & (
                dates.dt.month == int(month.group(2))
            )
        elif quarter:
            quarter_number = "一二三四".find(quarter.group(2)) + 1
            if quarter_number == 0:
                quarter_number = int(quarter.group(2))
            mask = (dates.dt.year == int(quarter.group(1))) & (
                dates.dt.quarter == quarter_number
            )
        elif "至" in time_range:
            start_text, end_text = time_range.split("至", maxsplit=1)
            start = parse_chinese_date(start_text)
            end = parse_chinese_date(end_text, end_of_month=True)
            if start is not None and end is not None:
                mask = dates.between(start, end, inclusive="both")
    if mask is None:
        return frame, "unverified:unsupported_time_range"
    return frame.loc[mask.fillna(False)].copy(), "verified"


def parse_chinese_date(value: str, *, end_of_month: bool = False) -> pd.Timestamp | None:
    normalized = value.strip().replace("年", "-").replace("月", "-").replace("日", "")
    normalized = normalized.strip("-")
    try:
        timestamp = pd.Timestamp(normalized)
    except ValueError:
        return None
    if end_of_month and re.fullmatch(r"20\d{2}-\d{1,2}", normalized):
        timestamp = timestamp + pd.offsets.MonthEnd(0)
    return timestamp


def build_trend(
    frame: pd.DataFrame,
    values: pd.Series,
    metric_column: str,
    file_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    date_column = find_date_column(frame)
    if date_column is None:
        return []
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    valid = dates.notna() & values.notna()
    if not valid.any():
        return []
    grouped = (
        pd.DataFrame({"period": dates[valid].dt.to_period("M").astype(str), "value": values[valid]})
        .groupby("period", as_index=False)["value"]
        .sum()
        .tail(120)
    )
    return [
        {
            "file_id": file_ref["file_id"],
            "metric_field": metric_column,
            "grain": "month",
            "points": json_safe(grouped.to_dict(orient="records")),
        }
    ]


def build_comparison(trends: list[dict[str, Any]], baseline: str) -> dict[str, Any] | None:
    if not trends or baseline not in {"previous_period", "year_over_year"}:
        return None
    trend = trends[0]
    points = trend.get("points", [])
    if len(points) < 2:
        return None
    current = points[-1]
    baseline_point: dict[str, Any] | None = None
    if baseline == "previous_period":
        baseline_point = points[-2]
    else:
        target = str(pd.Period(str(current["period"]), freq="M") - 12)
        baseline_point = next(
            (point for point in points if str(point.get("period")) == target),
            None,
        )
    if baseline_point is None:
        return None
    current_value = float(current["value"])
    baseline_value = float(baseline_point["value"])
    absolute_change = current_value - baseline_value
    return {
        "file_id": trend["file_id"],
        "metric_field": trend["metric_field"],
        "baseline": baseline,
        "current_period": current["period"],
        "baseline_period": baseline_point["period"],
        "current_value": current_value,
        "baseline_value": baseline_value,
        "absolute_change": absolute_change,
        "change_rate": absolute_change / baseline_value if baseline_value else None,
        "formula": "(current_value - baseline_value) / baseline_value",
    }


def resolve_target_month(time_range: str) -> pd.Period | None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if time_range == "current_month":
        return pd.Period(now, freq="M")
    if time_range == "previous_month":
        return pd.Period(now, freq="M") - 1
    month = re.fullmatch(r"(20\d{2})年(\d{1,2})月", time_range)
    if month:
        return pd.Period(f"{month.group(1)}-{int(month.group(2)):02d}", freq="M")
    return None


def resolve_dimension_columns(
    frame: pd.DataFrame,
    requested_dimensions: list[str],
    metric_column: str,
) -> list[str]:
    dimensions: list[str] = []
    for canonical in requested_dimensions:
        aliases = (canonical, *DIMENSION_ALIASES.get(canonical, ()))
        match = find_alias_column(frame, aliases)
        if match and match != metric_column:
            dimensions.append(match)
    if not dimensions:
        date_column = find_date_column(frame)
        dimensions = [
            str(column)
            for column in frame.select_dtypes(exclude="number").columns
            if str(column) not in {metric_column, date_column}
        ][:3]
    return list(dict.fromkeys(dimensions))[:3]


def build_dimension_changes(
    frame: pd.DataFrame,
    metric_column: str,
    requested_dimensions: list[str],
    time_range: str,
    baseline: str,
    file_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    date_column = find_date_column(frame)
    target_month = resolve_target_month(time_range)
    if date_column is None or target_month is None:
        return []
    if baseline == "previous_period":
        baseline_month = target_month - 1
    elif baseline == "year_over_year":
        baseline_month = target_month - 12
    else:
        return []
    dates = pd.to_datetime(frame[date_column], errors="coerce").dt.to_period("M")
    values = pd.to_numeric(frame[metric_column], errors="coerce")
    dimensions = resolve_dimension_columns(frame, requested_dimensions, metric_column)
    outputs: list[dict[str, Any]] = []
    for dimension in dimensions:
        comparison_frame = pd.DataFrame(
            {
                "dimension": frame[dimension].astype(str),
                "period": dates,
                "value": values,
            }
        ).dropna(subset=["period", "value"])
        current = (
            comparison_frame.loc[comparison_frame["period"] == target_month]
            .groupby("dimension")["value"]
            .sum()
        )
        previous = (
            comparison_frame.loc[comparison_frame["period"] == baseline_month]
            .groupby("dimension")["value"]
            .sum()
        )
        if current.empty or previous.empty:
            continue
        joined = pd.concat(
            [current.rename("current_value"), previous.rename("baseline_value")],
            axis=1,
        ).fillna(0.0)
        joined["absolute_change"] = joined["current_value"] - joined["baseline_value"]
        total_change = float(joined["absolute_change"].sum())
        joined["change_rate"] = joined.apply(
            lambda row: (
                float(row["absolute_change"] / row["baseline_value"])
                if row["baseline_value"]
                else None
            ),
            axis=1,
        )
        joined["impact_share"] = (
            joined["absolute_change"] / total_change if total_change else 0.0
        )
        joined["absolute_sort"] = joined["absolute_change"].abs()
        joined = joined.sort_values("absolute_sort", ascending=False).head(20)
        items = []
        for name, row in joined.iterrows():
            items.append(
                {
                    "dimension_value": str(name),
                    "current_value": float(row["current_value"]),
                    "baseline_value": float(row["baseline_value"]),
                    "absolute_change": float(row["absolute_change"]),
                    "change_rate": row["change_rate"],
                    "impact_share": float(row["impact_share"]),
                }
            )
        outputs.append(
            {
                "file_id": file_ref["file_id"],
                "dimension": dimension,
                "metric_field": metric_column,
                "current_period": str(target_month),
                "baseline_period": str(baseline_month),
                "total_change": total_change,
                "items": items,
                "formula": "dimension_current - dimension_baseline",
            }
        )
    return outputs


def build_structures(
    frame: pd.DataFrame,
    values: pd.Series,
    metric_column: str,
    requested_dimensions: list[str],
    file_ref: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dimensions = resolve_dimension_columns(frame, requested_dimensions, metric_column)

    structures: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []
    for dimension in dimensions:
        grouped = (
            pd.DataFrame({"dimension": frame[dimension].astype(str), "value": values})
            .dropna(subset=["value"])
            .groupby("dimension", as_index=False)["value"]
            .sum()
            .sort_values("value", ascending=False)
            .head(20)
        )
        total = float(grouped["value"].sum())
        grouped["share"] = grouped["value"] / total if total else 0.0
        records = json_safe(grouped.to_dict(orient="records"))
        base = {
            "file_id": file_ref["file_id"],
            "dimension": dimension,
            "metric_field": metric_column,
            "items": records,
        }
        structures.append(base)
        contributions.append({**base, "formula": "dimension_value / selected_dimension_total"})
    return structures, contributions


def analyze_scenario(
    scenario: str,
    frame: pd.DataFrame,
    file_ref: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    if scenario == "inventory_anomaly":
        return analyze_inventory_scenario(frame, file_ref)
    if scenario == "market_performance":
        return analyze_market_scenario(frame, file_ref)
    return {"metrics": [], "risk_items": []}


def analyze_market_scenario(
    frame: pd.DataFrame,
    file_ref: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    sales_column = find_alias_column(
        frame,
        ("销售额", "销售收入", "营收", "成交额", "sales_amount", "revenue", "sales"),
    )
    orders_column = find_alias_column(
        frame,
        ("订单量", "订单数", "order_count", "orders"),
    )
    visits_column = find_alias_column(frame, ("访问量", "访客数", "visits", "sessions"))
    conversions_column = find_alias_column(
        frame,
        ("转化数", "成交用户数", "conversions"),
    )
    spend_column = find_alias_column(
        frame,
        ("投放费用", "广告费用", "营销费用", "ad_spend", "spend"),
    )
    metrics: list[dict[str, Any]] = []
    sales = numeric_sum(frame, sales_column)
    orders = numeric_sum(frame, orders_column)
    visits = numeric_sum(frame, visits_column)
    conversions = numeric_sum(frame, conversions_column)
    spend = numeric_sum(frame, spend_column)
    if orders is not None:
        metrics.append(scenario_metric(file_ref, "order_count", "订单量", orders, "SUM(orders)"))
    if sales is not None and orders:
        metrics.append(
            scenario_metric(
                file_ref,
                "average_order_value",
                "客单价",
                sales / orders,
                "sales_amount / order_count",
            )
        )
    if conversions is not None and visits:
        metrics.append(
            scenario_metric(
                file_ref,
                "conversion_rate",
                "转化率",
                conversions / visits,
                "conversions / visits",
                unit="ratio",
            )
        )
    if sales is not None and spend:
        metrics.append(
            scenario_metric(
                file_ref,
                "roas",
                "广告投入产出比",
                sales / spend,
                "sales_amount / ad_spend",
                unit="ratio",
            )
        )
    return {"metrics": metrics, "risk_items": []}


def analyze_inventory_scenario(
    frame: pd.DataFrame,
    file_ref: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    stock_column = find_alias_column(
        frame,
        ("库存量", "当前库存", "可用库存", "stock_quantity", "current_stock", "inventory"),
    )
    sales_column = find_alias_column(
        frame,
        ("销量", "销售数量", "出库量", "sales_quantity", "units_sold", "outbound"),
    )
    item_column = find_alias_column(
        frame,
        ("sku", "商品编码", "商品", "产品", "product_id", "item_id"),
    )
    reorder_column = find_alias_column(
        frame,
        ("补货点", "安全库存", "reorder_point", "safety_stock"),
    )
    if stock_column is None:
        return {"metrics": [], "risk_items": []}
    item_values = (
        frame[item_column].astype(str)
        if item_column
        else pd.Series(["全部商品"] * len(frame.index), index=frame.index)
    )
    work = pd.DataFrame(
        {
            "item": item_values,
            "stock": pd.to_numeric(frame[stock_column], errors="coerce").fillna(0.0),
            "sales": (
                pd.to_numeric(frame[sales_column], errors="coerce").fillna(0.0)
                if sales_column
                else 0.0
            ),
            "reorder": (
                pd.to_numeric(frame[reorder_column], errors="coerce").fillna(0.0)
                if reorder_column
                else 0.0
            ),
        }
    )
    grouped = work.groupby("item", as_index=False).agg(
        stock=("stock", "sum"),
        sales=("sales", "sum"),
        reorder=("reorder", "max"),
    )
    date_column = find_date_column(frame)
    active_days = 30
    if date_column:
        active_days = max(
            1,
            int(pd.to_datetime(frame[date_column], errors="coerce").dropna().dt.date.nunique()),
        )
    risk_items: list[dict[str, Any]] = []
    coverage_values: list[float] = []
    for _, row in grouped.iterrows():
        daily_sales = float(row["sales"]) / active_days
        coverage = float(row["stock"]) / daily_sales if daily_sales > 0 else None
        if coverage is not None:
            coverage_values.append(coverage)
        risk_type: str | None = None
        severity = "medium"
        if float(row["stock"]) <= float(row["reorder"]) or (
            coverage is not None and coverage < 7
        ):
            risk_type = "stockout"
            severity = "high"
        elif coverage is not None and coverage > 90:
            risk_type = "overstock"
            severity = "high" if coverage > 180 else "medium"
        elif float(row["sales"]) <= 0 and float(row["stock"]) > 0:
            risk_type = "slow_moving"
        if risk_type:
            risk_items.append(
                {
                    "file_id": file_ref["file_id"],
                    "item": str(row["item"]),
                    "risk_type": risk_type,
                    "severity": severity,
                    "stock": float(row["stock"]),
                    "sales": float(row["sales"]),
                    "coverage_days": coverage,
                    "formula": "stock / (period_sales / active_days)",
                }
            )
    metrics = [
        scenario_metric(
            file_ref,
            "total_inventory",
            "库存总量",
            float(grouped["stock"].sum()),
            f"SUM({stock_column})",
        ),
        scenario_metric(
            file_ref,
            "inventory_risk_items",
            "库存风险商品数",
            float(len(risk_items)),
            "COUNT(stockout OR overstock OR slow_moving)",
            unit="item",
        ),
    ]
    if coverage_values:
        metrics.append(
            scenario_metric(
                file_ref,
                "average_coverage_days",
                "平均库存覆盖天数",
                sum(coverage_values) / len(coverage_values),
                "AVG(stock / average_daily_sales)",
                unit="day",
            )
        )
    return {"metrics": metrics, "risk_items": risk_items[:100]}


def numeric_sum(frame: pd.DataFrame, column: str | None) -> float | None:
    if column is None:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.sum()) if not values.empty else None


def scenario_metric(
    file_ref: dict[str, Any],
    metric: str,
    label: str,
    value: float,
    formula: str,
    *,
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "file_id": file_ref["file_id"],
        "metric": metric,
        "label": label,
        "value": value,
        "unit": unit,
        "formula": formula,
    }


def build_anomalies(
    frame: pd.DataFrame,
    values: pd.Series,
    metric_column: str,
    file_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    standard_deviation = values.std()
    if pd.isna(standard_deviation) or float(standard_deviation) == 0:
        return []
    z_scores = (values - values.mean()) / standard_deviation
    indexes = z_scores[z_scores.abs() >= 3].index[:100]
    return [
        {
            "file_id": file_ref["file_id"],
            "row_index": int(index) if isinstance(index, int) else str(index),
            "metric_field": metric_column,
            "value": json_safe(values.loc[index]),
            "z_score": float(z_scores.loc[index]),
            "method": "absolute z-score >= 3",
        }
        for index in indexes
    ]
