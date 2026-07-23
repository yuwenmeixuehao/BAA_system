import asyncio
from typing import Any, Protocol

import httpx
import pandas as pd
import sqlglot
from sqlglot import expressions as exp

from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.base import ToolContext, ToolResult
from app.core.config import Settings


class DataAgentClient(Protocol):
    async def query(
        self,
        objective: str,
        context: ToolContext,
        *,
        user_question: str | None = None,
    ) -> dict[str, Any]: ...


class HttpDataAgentClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.data_agent_base_url.rstrip("/")
        self.api_key = settings.data_agent_api_key
        self.timeout = settings.data_agent_timeout_seconds

    async def query(
        self,
        objective: str,
        context: ToolContext,
        *,
        user_question: str | None = None,
    ) -> dict[str, Any]:
        headers = {self.settings.trace_id_header: context.trace_id}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(
            timeout=self.timeout,
            trust_env=False,
        ) as client:
            response: httpx.Response | None = None
            for attempt in range(3):
                try:
                    response = await client.post(
                        f"{self.base_url}/query",
                        headers=headers,
                        json={
                            "objective": objective,
                            "user_question": user_question,
                            "user_id": context.user_id,
                            "conversation_id": context.conversation_id,
                            "task_id": context.task_id,
                            "trace_id": context.trace_id,
                            "limits": {
                                "max_returned_rows": self.settings.agent_max_rows,
                                "max_scanned_rows": self.settings.data_agent_max_scanned_rows,
                                "timeout_seconds": self.settings.data_agent_timeout_seconds,
                            },
                        },
                    )
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500 or attempt >= 2:
                        raise ValueError(_data_agent_error_message(exc.response)) from exc
                except httpx.RequestError as exc:
                    if attempt >= 2:
                        raise ValueError(
                            "DATA_AGENT_UNAVAILABLE: "
                            f"无法连接本地 Data Agent（{self.base_url}）"
                        ) from exc
                await asyncio.sleep(0.25 * (2**attempt))
            if response is None:
                raise httpx.RequestError("Data Agent request did not start")
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid Data Agent response")
        return payload


def _data_agent_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "DATA_AGENT_ERROR")
            message = str(error.get("message") or "Data Agent request failed")
            return f"{code}: {message}"
    return f"Data Agent HTTP {response.status_code}"


class DbQueryTool:
    def __init__(
        self,
        settings: Settings,
        client: DataAgentClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or (
            HttpDataAgentClient(settings) if settings.data_agent_base_url else None
        )

    async def run(
        self,
        objective: str,
        context: ToolContext,
        *,
        user_question: str | None = None,
    ) -> ToolResult:
        if self.client is None:
            return ToolResult(
                ok=False,
                summary="尚未配置受控 Data Agent，无法查询业务数据库",
                error_code="DATA_AGENT_NOT_CONFIGURED",
            )
        try:
            response = await self.client.query(
                objective,
                context,
                user_question=user_question,
            )
            sql = str(response.get("sql") or "")
            validate_read_only_sql(
                sql,
                allowed_tables=self.settings.data_agent_allowed_table_list,
            )
            scanned_rows = response.get("scanned_rows")
            if (
                scanned_rows is not None
                and int(scanned_rows) > self.settings.data_agent_max_scanned_rows
            ):
                raise ValueError("Data Agent scan limit exceeded")
            rows = response.get("rows")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Data Agent rows must be a list of objects")
            if len(rows) > self.settings.agent_max_rows:
                raise ValueError("Data Agent row limit exceeded")
            columns = response.get("columns")
            if not isinstance(columns, list) or any(
                not isinstance(column, str) for column in columns
            ):
                raise ValueError("Data Agent columns must be a list of strings")
            if not rows:
                raise ValueError("Data Agent 查询未返回任何数据")
            frame = pd.DataFrame(rows, columns=columns)
            storage_key = f"tasks/{context.task_id}/raw/data_agent_query.csv"
            storage = WorkspaceStorage(context.workspace_root)
            path = storage.resolve_key(storage_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False, encoding="utf-8-sig")
        except (httpx.HTTPError, ValueError, sqlglot.errors.SqlglotError) as exc:
            return ToolResult(
                ok=False,
                summary=f"受控数据查询失败：{str(exc)[:200]}",
                error_code="DATA_QUERY_FAILED",
            )

        file_ref = {
            "file_id": f"data-agent:{context.task_id}",
            "source_type": "data_agent",
            "storage_key": storage_key,
            "file_name": "data_agent_query.csv",
            "format": "csv",
            "row_count": len(frame.index),
            "columns": list(frame.columns),
        }
        return ToolResult(
            ok=True,
            summary=f"Data Agent 已返回 {len(frame.index)} 行、{len(frame.columns)} 列",
            files=[file_ref],
            data={"row_count": len(frame.index), "columns": list(frame.columns)},
        )


def validate_read_only_sql(sql: str, *, allowed_tables: set[str] | None = None) -> None:
    if not sql.strip():
        raise ValueError("Data Agent did not return SQL")
    statements = sqlglot.parse(sql, dialect="mysql")
    if len(statements) != 1:
        raise ValueError("only one read-only statement is allowed")
    statement = statements[0]
    allowed_roots = (exp.Select, exp.Union, exp.Subquery)
    if not isinstance(statement, allowed_roots):
        raise ValueError("only SELECT queries are allowed")
    forbidden_names = (
        "Insert",
        "Update",
        "Delete",
        "Create",
        "Drop",
        "Alter",
        "Command",
        "Merge",
        "Grant",
        "Revoke",
        "TruncateTable",
    )
    for name in forbidden_names:
        expression_type = getattr(exp, name, None)
        if expression_type is not None and statement.find(expression_type):
            raise ValueError("write or administrative SQL is forbidden")
    forbidden_catalogs = {"information_schema", "mysql", "performance_schema", "sys"}
    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    for table in statement.find_all(exp.Table):
        catalog = (table.catalog or "").lower()
        database = (table.db or "").lower()
        if not catalog and not database and table.name.lower() in cte_names:
            continue
        if catalog in forbidden_catalogs or database in forbidden_catalogs:
            raise ValueError("system schemas are forbidden")
        table_name = table.name.lower()
        qualified_name = f"{database}.{table_name}" if database else table_name
        if allowed_tables and not {table_name, qualified_name}.intersection(allowed_tables):
            raise ValueError(f"table is not in the allowlist: {qualified_name}")
    forbidden_functions = {"benchmark", "get_lock", "load_file", "release_lock", "sleep"}
    for function in statement.find_all(exp.Func):
        function_name = function.sql_name().lower()
        if function_name == "anonymous":
            function_name = str(function.this).lower()
        if function_name in forbidden_functions:
            raise ValueError("unsafe SQL function is forbidden")
