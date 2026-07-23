import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from app.agent.executor import LangGraphTaskExecutor
from app.agent.model import AnalysisModelServices, RuleBasedProblemDefinitionExtractor
from app.agent.nodes.query_data import build_data_agent_objective
from app.agent.state import AnalysisPlanOutput
from app.agent.tools.base import ToolContext
from app.agent.tools.db_query import (
    DbQueryTool,
    HttpDataAgentClient,
    _data_agent_error_message,
    validate_read_only_sql,
)
from app.agent.tools.pandas_analyze import PandasAnalyzeTool
from app.core.config import Settings
from app.models.base import Base
from app.models.entities import (
    AnalysisResult,
    AnalysisTask,
    Attachment,
    Conversation,
    Message,
    ReportFile,
    TaskEvent,
    User,
)
from app.schemas.websocket import UserMessageEvent
from app.services.attachment_service import AttachmentService
from app.services.task_service import task_service
from app.workers.task_worker import TaskWorker


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.published: list[tuple[str, str]] = []

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    async def lpush(self, key: str, value: str) -> None:
        self.lists[key].insert(0, value)

    async def rpush(self, key: str, value: str) -> None:
        self.lists[key].append(value)

    async def brpoplpush(self, source: str, destination: str, **options: int) -> str | None:
        del options
        if not self.lists[source]:
            return None
        value = self.lists[source].pop()
        self.lists[destination].insert(0, value)
        return value

    async def lrem(self, key: str, count: int, value: str) -> int:
        del count
        try:
            self.lists[key].remove(value)
        except ValueError:
            return 0
        return 1


class EmptyDataAgentClient:
    async def query(
        self,
        objective: str,
        context: ToolContext,
        *,
        user_question: str | None = None,
    ) -> dict[str, object]:
        del objective, context, user_question
        return {
            "sql": "SELECT total_amount FROM biz_sales WHERE 1 = 0",
            "rows": [],
            "columns": ["total_amount"],
            "scanned_rows": 0,
            "truncated": False,
        }


class FakeClarificationGenerator:
    async def generate(
        self,
        question: str,
        problem_definition: dict[str, object],
        recent_messages: list[dict[str, object]],
    ) -> str:
        del question, recent_messages
        missing = problem_definition.get("missing_fields", [])
        return f"为了继续分析，请补充这些口径：{', '.join(str(item) for item in missing)}。"


class FakeAnalysisPlanner:
    async def build(
        self,
        question: str,
        problem_definition: dict[str, object],
        attachment_ids: list[str],
    ) -> AnalysisPlanOutput:
        metric = str(problem_definition["metric"])
        return AnalysisPlanOutput.model_validate(
            {
                "analysis_plan": [
                    {
                        "step": "query_data",
                        "goal": f"取得 {metric} 明细数据",
                        "dimensions": problem_definition.get("dimensions", []),
                        "methods": ["受控附件读取" if attachment_ids else "受控数据查询"],
                    },
                    {
                        "step": "validate_data",
                        "goal": "验证时间、指标字段和数据质量",
                        "methods": ["缺失值", "重复值", "时间范围"],
                    },
                    {
                        "step": "analyze_with_pandas",
                        "goal": "计算指标、趋势、基线差异和结构贡献",
                        "dimensions": problem_definition.get("dimensions", []),
                        "methods": ["趋势", "基线比较", "结构贡献"],
                    },
                ],
                "query_specs": [
                    {
                        "objective": question,
                        "source_preference": "attachment" if attachment_ids else "data_agent",
                        "required_fields": [metric, "date"],
                        "dimensions": problem_definition.get("dimensions", []),
                        "time_range": problem_definition["time_range"],
                        "baseline": problem_definition["baseline"],
                    }
                ],
            }
        )


def fake_model_services() -> AnalysisModelServices:
    return AnalysisModelServices(
        problem_extractor=RuleBasedProblemDefinitionExtractor(),
        clarification_generator=FakeClarificationGenerator(),
        analysis_planner=FakeAnalysisPlanner(),
    )


@dataclass
class AgentDatabase:
    sessions: async_sessionmaker[AsyncSession]
    user: User
    conversation: Conversation


@pytest.fixture
async def agent_database() -> AsyncIterator[AgentDatabase]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        user = User(
            external_user_id="agent-user",
            display_name="Agent 测试用户",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="阶段四测试")
        session.add(conversation)
        await session.commit()
        await session.refresh(user)
        await session.refresh(conversation)
    yield AgentDatabase(sessions, user, conversation)
    await engine.dispose()


@pytest.mark.asyncio
async def test_rule_extractor_keeps_unknown_scope_missing() -> None:
    extractor = RuleBasedProblemDefinitionExtractor()
    complete = await extractor.extract("分析本月各渠道销售额，对比上月", [])
    incomplete = await extractor.extract("分析利润下降原因", [])

    assert complete.metric == "sales_amount"
    assert complete.time_range == "current_month"
    assert complete.baseline == "previous_period"
    assert complete.dimensions == ["channel"]
    assert complete.missing_fields == []
    assert set(incomplete.missing_fields) == {"time_range", "baseline"}


def test_analysis_model_config_uses_shared_defaults_and_dedicated_overrides() -> None:
    settings = Settings(
        _env_file=None,
        MODEL_PROVIDER="openai_compatible",
        MODEL_NAME="shared-model",
        API_KEY="shared-key",
        BASE_URL="https://llm.example/v1",
        ANALYSIS_AGENT_MODEL_NAME="analysis-model",
        ANALYSIS_AGENT_API_KEY="analysis-key",
    )

    assert settings.analysis_model_provider == "openai_compatible"
    assert settings.analysis_model_name == "analysis-model"
    assert settings.analysis_model_api_key == "analysis-key"
    assert settings.analysis_model_base_url == "https://llm.example/v1"


def test_db_query_sql_guard_accepts_select_and_rejects_unsafe_sql() -> None:
    validate_read_only_sql("WITH recent AS (SELECT * FROM sales) SELECT * FROM recent")
    validate_read_only_sql(
        "WITH recent AS (SELECT * FROM sales) SELECT * FROM recent",
        allowed_tables={"sales"},
    )

    for sql in (
        "UPDATE sales SET amount = 0",
        "SELECT 1; SELECT 2",
        "SELECT * FROM information_schema.tables",
        "SELECT SLEEP(10)",
    ):
        with pytest.raises(ValueError):
            validate_read_only_sql(sql)
    with pytest.raises(ValueError):
        validate_read_only_sql("SELECT * FROM secret_table", allowed_tables={"sales"})


def test_data_agent_error_message_uses_remote_classified_error() -> None:
    response = httpx.Response(
        422,
        json={
            "error": {
                "code": "DATA_AGENT_SQL_REJECTED",
                "message": "候选 SQL 未通过只读安全校验",
            }
        },
    )

    assert _data_agent_error_message(response) == (
        "DATA_AGENT_SQL_REJECTED: 候选 SQL 未通过只读安全校验"
    )


@pytest.mark.asyncio
async def test_data_agent_client_does_not_use_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            captured["request_json"] = kwargs.get("json")
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "sql": "SELECT total_amount FROM biz_sales",
                    "rows": [{"total_amount": 1}],
                    "columns": ["total_amount"],
                    "scanned_rows": 1,
                    "truncated": False,
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = HttpDataAgentClient(
        Settings(
            _env_file=None,
            DATA_AGENT_BASE_URL="http://127.0.0.1:8002",
            DATA_AGENT_API_KEY="service-secret",
        )
    )

    payload = await client.query(
        "sales",
        ToolContext(
            user_id="user-1",
            conversation_id="conversation-1",
            task_id="task-1",
            workspace_root=tmp_path,
            trace_id="trace-1",
        ),
        user_question="分析 6 月销售额",
    )

    assert captured["trust_env"] is False
    assert captured["request_json"]["user_question"] == "分析 6 月销售额"
    assert payload["rows"] == [{"total_amount": 1}]


def test_data_agent_objective_preserves_structured_query_intent() -> None:
    objective = build_data_agent_objective(
        {
            "question": "分析 6 月各渠道销售表现，对比上月",
            "problem_definition": {
                "metric": "sales_amount",
                "time_range": "2026-06",
                "baseline": "previous_month",
                "dimensions": ["channel"],
            },
            "query_specs": [
                {
                    "objective": "按渠道返回销售额和对比期间",
                    "source_preference": "data_agent",
                    "required_fields": ["total_amount", "sale_date", "channel_id"],
                    "dimensions": ["channel"],
                    "time_range": "2026-06",
                    "baseline": "previous_month",
                }
            ],
        }
    )

    payload = json.loads(objective.split("\n", 1)[1])
    assert payload["query_spec"]["required_fields"] == [
        "total_amount",
        "sale_date",
        "channel_id",
    ]
    assert payload["problem_definition"]["dimensions"] == ["channel"]
    assert payload["user_question"] == "分析 6 月各渠道销售表现，对比上月"


@pytest.mark.asyncio
async def test_pandas_tool_calculates_metrics_contribution_and_artifact(tmp_path: Path) -> None:
    source = tmp_path / "tasks" / "task-1" / "raw" / "sales.csv"
    source.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "日期": ["2026-06-01", "2026-07-01", "2026-07-02", "2026-07-03"],
            "渠道": ["线上", "线上", "线下", "线上"],
            "销售额": [80.0, 100.0, 150.0, 200.0],
        }
    ).to_csv(source, index=False, encoding="utf-8-sig")
    settings = Settings(AGENT_DATA_ROOT=str(tmp_path), AGENT_MAX_ROWS=1000)
    tool = PandasAnalyzeTool(settings)
    result = await tool.run(
        [
            {
                "file_id": "file-1",
                "storage_key": "tasks/task-1/raw/sales.csv",
                "file_name": "sales.csv",
            }
        ],
        {
            "metric": "sales_amount",
            "time_range": "2026年7月",
            "baseline": "previous_period",
            "dimensions": ["channel"],
        },
        ToolContext(
            user_id="user-1",
            conversation_id="conversation-1",
            task_id="task-1",
            workspace_root=tmp_path,
            trace_id="trace-1",
        ),
    )

    assert result.ok is True
    assert result.data["metrics"][0]["value"] == 450.0
    assert result.data["comparisons"][0]["baseline_value"] == 80.0
    assert result.data["contributions"][0]["dimension"] == "渠道"
    assert (tmp_path / "tasks" / "task-1" / "analysis" / "pandas_analysis.json").is_file()


@pytest.mark.asyncio
async def test_unconfigured_db_query_returns_classified_gap(tmp_path: Path) -> None:
    settings = Settings(AGENT_DATA_ROOT=str(tmp_path), DATA_AGENT_BASE_URL="")
    result = await DbQueryTool(settings).run(
        "分析本月销售额",
        ToolContext(
            user_id="user-1",
            conversation_id="conversation-1",
            task_id="task-1",
            workspace_root=tmp_path,
            trace_id="trace-1",
        ),
    )

    assert result.ok is False
    assert result.error_code == "DATA_AGENT_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_empty_db_query_returns_classified_gap(tmp_path: Path) -> None:
    settings = Settings(
        AGENT_DATA_ROOT=str(tmp_path),
        DATA_AGENT_BASE_URL="http://data-agent",
    )
    result = await DbQueryTool(settings, EmptyDataAgentClient()).run(
        "分析本月销售额",
        ToolContext(
            user_id="user-1",
            conversation_id="conversation-1",
            task_id="task-1",
            workspace_root=tmp_path,
            trace_id="trace-1",
        ),
    )

    assert result.ok is False
    assert result.error_code == "DATA_QUERY_FAILED"
    assert "未返回任何数据" in result.summary


def test_sales_metric_alias_matches_aggregated_amount_column() -> None:
    frame = pd.DataFrame({"channel_id": [1, 2], "cur_amount": [100.0, 200.0]})

    from app.agent.tools.pandas_analyze import find_metric_column

    assert find_metric_column(frame, "sales") == "cur_amount"


def test_sales_metric_alias_matches_current_sales_amount_column() -> None:
    frame = pd.DataFrame(
        {"channel_id": [1, 2], "current_sales_amount": [100.0, 200.0]}
    )

    from app.agent.tools.pandas_analyze import find_metric_column

    assert find_metric_column(frame, "sales_amount") == "current_sales_amount"


@pytest.mark.asyncio
async def test_attachment_upload_uses_controlled_storage_key(
    agent_database: AgentDatabase,
    tmp_path: Path,
) -> None:
    service = AttachmentService(
        Settings(AGENT_DATA_ROOT=str(tmp_path), AGENT_MAX_FILE_BYTES=1024)
    )
    upload = UploadFile(
        BytesIO(b"sales,channel\n100,online\n"),
        filename="../sales.csv",
        headers=Headers({"content-type": "text/csv"}),
    )
    async with agent_database.sessions() as session:
        item = await service.upload(
            session,
            agent_database.user.id,
            agent_database.conversation.id,
            upload,
        )

    assert item.file_name == "sales.csv"
    assert item.file_path == f"attachment:{item.attachment_id}"
    async with agent_database.sessions() as session:
        attachment, path = await service.get_owned(
            session,
            agent_database.user.id,
            item.attachment_id,
        )
        assert attachment.storage_key.startswith("attachments/")
        assert path.is_relative_to(tmp_path)
        assert path.read_text(encoding="utf-8") == "sales,channel\n100,online\n"


@pytest.mark.asyncio
async def test_langgraph_worker_completes_attachment_analysis(
    agent_database: AgentDatabase,
    tmp_path: Path,
) -> None:
    upload = tmp_path / "uploads" / "sales.csv"
    upload.parent.mkdir(parents=True)
    upload.write_text(
        "日期,渠道,销售额\n2026-07-01,线上,100\n2026-07-02,线下,150\n",
        encoding="utf-8-sig",
    )
    async with agent_database.sessions() as session:
        attachment = Attachment(
            user_id=agent_database.user.id,
            conversation_id=agent_database.conversation.id,
            file_name="sales.csv",
            storage_key="uploads/sales.csv",
            mime_type="text/csv",
            file_size=upload.stat().st_size,
            parse_status="pending",
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)

    redis = FakeRedis()
    async with agent_database.sessions() as session:
        created = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            agent_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=agent_database.conversation.id,
                client_msg_id="agent-success-1",
                content="分析2026年7月各渠道销售额，环比",
                attachment_ids=[attachment.id],
            ),
        )

    settings = Settings(
        AGENT_DATA_ROOT=str(tmp_path),
        AGENT_MODEL_PROVIDER="",
        AGENT_MAX_ROWS=1000,
    )
    executor = LangGraphTaskExecutor(
        redis,  # type: ignore[arg-type]
        agent_database.sessions,
        settings,
        model_services=fake_model_services(),
    )
    worker = TaskWorker(redis, agent_database.sessions)  # type: ignore[arg-type]
    assert await worker.process_once(executor, block_seconds=1) is True

    async with agent_database.sessions() as session:
        task = await session.get(AnalysisTask, created.task.id)
        result = await session.scalar(
            select(AnalysisResult).where(AnalysisResult.task_id == created.task.id)
        )
        report_files = list(
            await session.scalars(
                select(ReportFile).where(ReportFile.task_id == created.task.id)
            )
        )
        assistant = await session.scalar(
            select(Message).where(
                Message.task_id == created.task.id,
                Message.role == "assistant",
            )
        )
        events = list(
            await session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == created.task.id)
                .order_by(TaskEvent.event_seq)
            )
        )

    assert task is not None and task.task_status == "success"
    assert result is not None and result.key_metrics_json[0]["value"] == 250.0
    assert result.evidence_list_json[0]["evidence_id"] == "ev_001"
    assert result.report_ir_json["schema_version"] == "1.0"
    assert result.report_ir_json["attribution_conclusions"][0]["status"] == "to_verify"
    assert {item.file_type for item in report_files} == {"html", "md", "json"}
    assert assistant is not None and "Report IR" in (assistant.content or "")
    event_types = [event.event_type for event in events]
    assert "tool_start" in event_types
    assert "tool_finish" in event_types
    assert "result_ready" in event_types
    assert any(
        event.payload_json.get("current_step") == "build_analysis_plan"
        for event in events
    )
    assert event_types[-1] == "done"


@pytest.mark.asyncio
async def test_langgraph_stops_for_clarification_before_querying_data(
    agent_database: AgentDatabase,
    tmp_path: Path,
) -> None:
    redis = FakeRedis()
    async with agent_database.sessions() as session:
        created = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            agent_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=agent_database.conversation.id,
                client_msg_id="agent-clarify-1",
                content="分析利润下降原因",
                attachment_ids=[],
            ),
        )
    executor = LangGraphTaskExecutor(
        redis,  # type: ignore[arg-type]
        agent_database.sessions,
        Settings(AGENT_DATA_ROOT=str(tmp_path), AGENT_MODEL_PROVIDER=""),
        model_services=fake_model_services(),
    )
    worker = TaskWorker(redis, agent_database.sessions)  # type: ignore[arg-type]
    assert await worker.process_once(executor, block_seconds=1) is True

    async with agent_database.sessions() as session:
        task = await session.get(AnalysisTask, created.task.id)
        events = list(
            await session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == created.task.id)
                .order_by(TaskEvent.event_seq)
            )
        )

    assert task is not None and task.task_status == "waiting_input"
    assert task.current_step == "ask_clarification"
    assert any(event.event_type == "clarification_required" for event in events)
    assert not any(
        event.event_type == "tool_start"
        and event.payload_json.get("tool_name") == "db_query"
        for event in events
    )
