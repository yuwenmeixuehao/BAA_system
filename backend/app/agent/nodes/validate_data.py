from typing import Any

import pandas as pd

from app.agent.errors import AgentExecutionError
from app.agent.state import AgentState
from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.pandas_analyze import find_date_column, find_metric_column
from app.agent.tools.tabular import read_dataframe
from app.core.config import Settings


class ValidateDataNode:
    def __init__(self, settings: Settings, workspace_root: Any) -> None:
        self.settings = settings
        self.storage = WorkspaceStorage(workspace_root)

    async def __call__(self, state: AgentState) -> AgentState:
        reports: list[dict[str, Any]] = []
        gaps: list[str] = []
        requested_metric = str(state["problem_definition"].get("metric") or "")
        metric_found = False
        for file_ref in state.get("data_files", []):
            try:
                frame = read_dataframe(
                    self.storage.resolve_key(str(file_ref["storage_key"])),
                    str(file_ref["file_name"]),
                    self.settings.agent_max_rows,
                )
            except Exception as exc:
                reports.append(
                    {
                        "file_id": file_ref.get("file_id"),
                        "usable": False,
                        "error": str(exc)[:200],
                    }
                )
                continue
            missing = {str(column): int(frame[column].isna().sum()) for column in frame.columns}
            duplicate_count = int(frame.duplicated().sum())
            current_metric = find_metric_column(frame, requested_metric)
            date_column = find_date_column(frame)
            valid_dates = (
                pd.to_datetime(frame[date_column], errors="coerce").dropna()
                if date_column
                else pd.Series(dtype="datetime64[ns]")
            )
            if date_column is None:
                gaps.append(f"文件 {file_ref.get('file_id')} 缺少可识别的时间字段")
            elif valid_dates.empty:
                gaps.append(f"文件 {file_ref.get('file_id')} 的时间字段无法解析")
            metric_found = metric_found or current_metric is not None
            reports.append(
                {
                    "file_id": file_ref.get("file_id"),
                    "usable": not frame.empty and bool(frame.columns.tolist()),
                    "row_count": int(len(frame.index)),
                    "column_count": int(len(frame.columns)),
                    "columns": list(frame.columns),
                    "missing_counts": missing,
                    "duplicate_count": duplicate_count,
                    "metric_field": current_metric,
                    "time_field": date_column,
                    "time_min": valid_dates.min().isoformat() if not valid_dates.empty else None,
                    "time_max": valid_dates.max().isoformat() if not valid_dates.empty else None,
                    "sample_size_warning": len(frame.index) < 2,
                }
            )
        usable = any(report.get("usable") for report in reports)
        if not usable:
            raise AgentExecutionError("DATA_QUALITY_FAILED", "所有数据文件均无法用于分析")
        if not metric_found:
            gaps.append(f"未找到指标 {requested_metric} 对应的数值字段")
            raise AgentExecutionError(
                "METRIC_FIELD_NOT_FOUND",
                f"数据中未找到指标 {requested_metric} 对应的数值字段",
            )
        return {
            "data_quality": {
                "usable": usable,
                "files": reports,
                "gaps": gaps,
            },
            "current_step": "validate_data",
        }
