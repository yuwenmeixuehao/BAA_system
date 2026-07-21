import json
from collections import defaultdict
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agent.errors import AgentExecutionError
from app.agent.events import AgentEventEmitter
from app.agent.nodes.build_evidence import BuildEvidenceNode
from app.agent.nodes.build_report_ir import BuildReportIRNode
from app.agent.nodes.determine_attribution import DetermineAttributionNode
from app.agent.nodes.validate_report import ValidateReportNode
from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.base import ToolContext
from app.agent.tools.pandas_analyze import PandasAnalyzeTool
from app.core.config import Settings
from app.core.exceptions import AppException
from app.dependencies.auth import require_admin
from app.models.base import Base
from app.models.entities import (
    AnalysisResult,
    AnalysisTask,
    AuditLog,
    Conversation,
    Message,
    ReportFile,
    TaskEvent,
    TaskLog,
    User,
)
from app.reporting.renderer import ReportRenderer
from app.schemas.report import ReportIR
from app.services.admin_log_service import admin_log_service
from app.services.analysis_result_service import AnalysisResultService
from app.services.context_summary_service import ContextSummaryService
from app.services.task_service import task_service


@dataclass
class StageFiveDatabase:
    sessions: async_sessionmaker[AsyncSession]
    user: User
    conversation: Conversation


@pytest.fixture
async def stage_five_database() -> AsyncIterator[StageFiveDatabase]:
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
            external_user_id="phase-five-user",
            display_name="阶段五测试用户",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="阶段五测试", status="active")
        session.add(conversation)
        await session.commit()
        await session.refresh(user)
        await session.refresh(conversation)
    yield StageFiveDatabase(sessions, user, conversation)
    await engine.dispose()


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.published: list[tuple[str, str]] = []

    async def set(self, key: str, value: str, **_: object) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def lrem(self, key: str, count: int, value: str) -> int:
        del count
        try:
            self.lists[key].remove(value)
        except ValueError:
            return 0
        return 1

    async def lpush(self, key: str, value: str) -> None:
        self.lists[key].insert(0, value)

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))


def valid_report_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "task_id": "task-phase-five",
        "problem_definition": {
            "question": "2026年7月销售额为何下降？",
            "scope": "2026年7月，环比2026年6月",
            "metric": "sales_amount",
            "baseline": "previous_period",
            "scenario": "market_performance",
            "assumptions": [],
        },
        "key_metrics": [
            {
                "metric_id": "m_001",
                "label": "销售额",
                "value": 800,
                "unit": "currency",
                "formula": "SUM(销售额)",
                "scope": "2026年7月",
                "baseline_value": 1000,
                "absolute_change": -200,
                "change_rate": -0.2,
            }
        ],
        "evidence_list": [
            {
                "evidence_id": "ev_001",
                "title": "销售额环比下降",
                "description": "销售额由1000下降至800。",
                "evidence_type": "baseline_comparison",
                "metric": "sales_amount",
                "current_value": 800,
                "baseline_value": 1000,
                "change_value": -200,
                "change_rate": -0.2,
                "scope": "2026年7月",
                "source_file_ids": ["file-001"],
                "formula": "current - baseline",
                "quality_status": "verified",
            }
        ],
        "attribution_conclusions": [
            {
                "conclusion_id": "c_001",
                "title": "销售额下降已确认",
                "description": "基线对比确认销售额下降20%。",
                "status": "confirmed",
                "impact_level": "high",
                "confidence": 0.95,
                "evidence_ids": ["ev_001"],
                "verification_needed": False,
            }
        ],
        "missing_data": [],
        "next_actions": [
            {
                "action_id": "a_001",
                "title": "复核渠道变化",
                "description": "检查主要渠道的流量与转化。",
                "priority": "high",
                "owner_hint": "经营负责人",
            }
        ],
        "visualizations": [
            {
                "chart_id": "chart_001",
                "title": "销售额趋势",
                "type": "line",
                "dimension": "period",
                "categories": ["2026-06", "2026-07"],
                "series": [{"name": "销售额", "data": [1000, 800]}],
            }
        ],
        "source_files": [
            {
                "file_id": "file-001",
                "file_name": "sales.csv",
                "source_type": "attachment",
                "row_count": 2,
            }
        ],
        "generated_files": [],
    }


def test_report_ir_enforces_evidence_references_and_chart_shape() -> None:
    assert ReportIR.model_validate(valid_report_payload()).schema_version == "1.0"

    missing_evidence = deepcopy(valid_report_payload())
    missing_evidence["attribution_conclusions"][0]["evidence_ids"] = []
    with pytest.raises(ValidationError, match="confirmed conclusion requires evidence"):
        ReportIR.model_validate(missing_evidence)

    invalid_chart = deepcopy(valid_report_payload())
    invalid_chart["visualizations"][0]["series"][0]["data"] = [1000]
    with pytest.raises(ValidationError, match="category and series lengths"):
        ReportIR.model_validate(invalid_chart)

    limited_evidence = deepcopy(valid_report_payload())
    limited_evidence["evidence_list"][0]["quality_status"] = "limited"
    with pytest.raises(ValidationError, match="requires verified evidence"):
        ReportIR.model_validate(limited_evidence)


@pytest.mark.asyncio
async def test_report_validation_repairs_safe_errors_and_fails_once_if_unrepairable() -> None:
    invalid = valid_report_payload()
    invalid["attribution_conclusions"][0]["evidence_ids"] = []
    validator = ValidateReportNode()
    builder = BuildReportIRNode()

    first = await validator(  # type: ignore[arg-type]
        {"report_ir": invalid, "report_retry_count": 0}
    )
    assert first["report_valid"] is False
    assert first["report_retry_count"] == 1
    repaired = await builder(  # type: ignore[arg-type]
        {
            "report_ir": invalid,
            "report_retry_count": first["report_retry_count"],
            "report_validation_errors": first["report_validation_errors"],
        }
    )
    validated = await validator(  # type: ignore[arg-type]
        {
            "report_ir": repaired["report_ir"],
            "report_retry_count": 1,
        }
    )
    assert validated["report_valid"] is True
    assert validated["report_ir"]["attribution_conclusions"][0]["status"] == "to_verify"

    unrepairable = valid_report_payload()
    unrepairable["key_metrics"] = []
    first_failure = await validator(  # type: ignore[arg-type]
        {"report_ir": unrepairable, "report_retry_count": 0}
    )
    repaired_failure = await builder(  # type: ignore[arg-type]
        {
            "report_ir": unrepairable,
            "report_retry_count": 1,
            "report_validation_errors": first_failure["report_validation_errors"],
        }
    )
    with pytest.raises(AgentExecutionError) as error:
        await validator(  # type: ignore[arg-type]
            {"report_ir": repaired_failure["report_ir"], "report_retry_count": 1}
        )
    assert error.value.error_code == "REPORT_INVALID"


@pytest.mark.asyncio
async def test_limited_data_quality_produces_probable_attribution() -> None:
    state: dict[str, Any] = {
        "problem_definition": {"time_range": "2026年7月"},
        "metric_results": {
            "comparisons": [
                {
                    "file_id": "file-001",
                    "metric_field": "销售额",
                    "current_period": "2026-07",
                    "current_value": 800,
                    "baseline_period": "2026-06",
                    "baseline_value": 1000,
                    "absolute_change": -200,
                    "change_rate": -0.2,
                    "formula": "current - baseline",
                }
            ]
        },
        "data_quality": {
            "usable": True,
            "files": [
                {
                    "file_id": "file-001",
                    "usable": True,
                    "metric_field": "销售额",
                    "time_field": "日期",
                    "time_min": "2026-06-01T00:00:00",
                    "time_max": "2026-07-31T00:00:00",
                    "missing_counts": {"销售额": 1},
                    "duplicate_count": 0,
                    "sample_size_warning": False,
                }
            ],
            "gaps": [],
        },
    }
    evidence_update = await BuildEvidenceNode()(state)  # type: ignore[arg-type]
    conclusion_update = await DetermineAttributionNode()(
        {**state, **evidence_update}  # type: ignore[arg-type]
    )

    assert evidence_update["evidence_list"][0]["quality_status"] == "limited"
    conclusion = conclusion_update["attribution_candidates"][0]
    assert conclusion["status"] == "probable"
    assert conclusion["verification_needed"] is True
    assert conclusion["confidence"] <= 0.7


def test_report_renderer_outputs_six_sections_and_three_files(tmp_path: Path) -> None:
    report = ReportIR.model_validate(valid_report_payload())
    rendered = ReportRenderer(WorkspaceStorage(tmp_path)).render(report)

    assert {item["file_type"] for item in rendered.generated_files} == {"html", "md", "json"}
    assert all(
        WorkspaceStorage(tmp_path).resolve_key(str(item["storage_key"])).is_file()
        for item in rendered.generated_files
    )
    assert "## 6. 下一步建议" in rendered.markdown
    assert "echarts@6.1.0" in rendered.html
    assert "ev_001" in rendered.html


@pytest.mark.asyncio
async def test_market_and_inventory_scenarios_compute_business_metrics(tmp_path: Path) -> None:
    market_path = tmp_path / "raw" / "market.csv"
    market_path.parent.mkdir(parents=True)
    market_path.write_text(
        "日期,渠道,销售额,订单量,访问量,转化数,投放费用\n"
        "2026-07-01,线上,1000,20,200,20,100\n"
        "2026-07-02,门店,500,10,100,10,50\n",
        encoding="utf-8-sig",
    )
    inventory_path = tmp_path / "raw" / "inventory.csv"
    inventory_path.write_text(
        "日期,SKU,库存量,销量,安全库存\n"
        "2026-07-01,A,2,30,5\n"
        "2026-07-01,B,500,1,10\n"
        "2026-07-01,C,100,0,5\n",
        encoding="utf-8-sig",
    )
    tool = PandasAnalyzeTool(Settings(_env_file=None, AGENT_MAX_ROWS=1000))
    context = ToolContext("user", "conversation", "task", tmp_path, "trace")

    market = await tool.run(
        [file_reference("market", "raw/market.csv")],
        problem_definition("sales_amount", "分析市场销售表现"),
        context,
    )
    inventory = await tool.run(
        [file_reference("inventory", "raw/inventory.csv")],
        problem_definition("inventory", "识别库存异常"),
        context,
    )

    assert market.ok and market.data["scenario"] == "market_performance"
    assert {item["metric"] for item in market.data["scenario_metrics"]} >= {
        "order_count",
        "average_order_value",
        "conversion_rate",
        "roas",
    }
    assert inventory.ok and inventory.data["scenario"] == "inventory_anomaly"
    assert {item["risk_type"] for item in inventory.data["risk_items"]} == {
        "stockout",
        "overstock",
        "slow_moving",
    }


@pytest.mark.asyncio
async def test_context_compression_retains_recent_messages(
    stage_five_database: StageFiveDatabase,
) -> None:
    async with stage_five_database.sessions() as session:
        session.add_all(
            [
                Message(
                    conversation_id=stage_five_database.conversation.id,
                    seq_no=index,
                    role="user" if index % 2 else "assistant",
                    message_type="text",
                    content=f"第{index}条经营分析上下文",
                )
                for index in range(1, 6)
            ]
        )
        await session.commit()
    service = ContextSummaryService(
        stage_five_database.sessions,
        Settings(
            _env_file=None,
            CONTEXT_SUMMARY_MESSAGE_THRESHOLD=5,
            CONTEXT_SUMMARY_CHAR_THRESHOLD=10000,
            CONTEXT_SUMMARY_RETAIN_MESSAGES=2,
        ),
    )

    summary = await service.compress_if_needed(stage_five_database.conversation.id)

    assert summary is not None
    assert (summary.start_seq_no, summary.end_seq_no) == (1, 3)
    assert "第1条经营分析上下文" in summary.summary_text


@pytest.mark.asyncio
async def test_context_compression_budget_keeps_every_covered_message(
    stage_five_database: StageFiveDatabase,
) -> None:
    async with stage_five_database.sessions() as session:
        session.add_all(
            [
                Message(
                    conversation_id=stage_five_database.conversation.id,
                    seq_no=index,
                    role="user" if index % 2 else "assistant",
                    message_type="text",
                    content=(
                        f"消息{index}开头-"
                        + ("经营分析上下文" * 250)
                        + f"-消息{index}结尾"
                    ),
                )
                for index in range(1, 23)
            ]
        )
        await session.commit()
    service = ContextSummaryService(
        stage_five_database.sessions,
        Settings(
            _env_file=None,
            CONTEXT_SUMMARY_MESSAGE_THRESHOLD=5,
            CONTEXT_SUMMARY_CHAR_THRESHOLD=1000,
            CONTEXT_SUMMARY_RETAIN_MESSAGES=2,
        ),
    )

    summary = await service.compress_if_needed(stage_five_database.conversation.id)

    assert summary is not None and summary.end_seq_no == 20
    assert len(summary.summary_text) <= 12_000
    for index in range(1, 21):
        assert f"[{index}]：" in summary.summary_text
        assert f"消息{index}开头" in summary.summary_text
        assert f"消息{index}结尾" in summary.summary_text


@pytest.mark.asyncio
async def test_report_retry_updates_task_event_and_log(
    stage_five_database: StageFiveDatabase,
) -> None:
    async with stage_five_database.sessions() as session:
        message = Message(
            conversation_id=stage_five_database.conversation.id,
            seq_no=1,
            role="user",
            message_type="text",
            content="生成归因报告",
        )
        session.add(message)
        await session.flush()
        task = AnalysisTask(
            user_id=stage_five_database.user.id,
            conversation_id=stage_five_database.conversation.id,
            message_id=message.id,
            client_msg_id="report-retry-phase-five",
            task_status="running",
            current_step="validate_report",
            thread_id="thread-report-retry",
            input_text="生成归因报告",
            retry_count=0,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    redis = FakeRedis()
    emitter = AgentEventEmitter(
        redis,  # type: ignore[arg-type]
        stage_five_database.sessions,
    )
    await emitter.report_retry(task_id, 1)

    async with stage_five_database.sessions() as session:
        task = await session.get(AnalysisTask, task_id)
        event = await session.scalar(
            select(TaskEvent).where(TaskEvent.task_id == task_id)
        )
        log = await session.scalar(
            select(TaskLog).where(
                TaskLog.task_id == task_id,
                TaskLog.log_type == "retry",
            )
        )

    assert task is not None and task.retry_count == 1
    assert event is not None and event.payload_json["report_retry_count"] == 1
    assert log is not None and "Report IR validation retry" in log.log_content


@pytest.mark.asyncio
async def test_failed_task_can_be_requeued_and_admin_logs_can_be_filtered(
    stage_five_database: StageFiveDatabase,
) -> None:
    async with stage_five_database.sessions() as session:
        message = Message(
            conversation_id=stage_five_database.conversation.id,
            seq_no=1,
            role="user",
            message_type="text",
            content="重试分析",
        )
        session.add(message)
        await session.flush()
        task = AnalysisTask(
            user_id=stage_five_database.user.id,
            conversation_id=stage_five_database.conversation.id,
            message_id=message.id,
            client_msg_id="retry-phase-five",
            task_status="failed",
            current_step="render_report",
            thread_id="thread-phase-five",
            input_text="重试分析",
            retry_count=0,
            error_code="REPORT_INVALID",
            error_message="报告校验失败",
        )
        session.add(task)
        await session.flush()
        session.add(
            TaskLog(
                task_id=task.id,
                log_level="error",
                log_type="error",
                log_content="报告校验失败，未记录敏感业务数据",
                trace_id="trace-phase-five",
                duration_ms=12,
            )
        )
        await session.commit()
        task_id = task.id

    redis = FakeRedis()
    async with stage_five_database.sessions() as session:
        summary = await task_service.retry(
            session,
            redis,  # type: ignore[arg-type]
            task_id,
            stage_five_database.user.id,
        )
        logs = await admin_log_service.list_logs(
            session,
            task_id=task_id,
            trace_id="trace-phase-five",
            level="error",
            limit=10,
        )
        events = list(
            await session.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id))
        )

    assert summary.task_status == "queued" and summary.retry_count == 1
    assert any(task_id in items for items in redis.lists.values())
    assert len(events) == 1 and events[0].payload_json["retry_count"] == 1
    assert len(logs.items) == 1 and logs.items[0].trace_id == "trace-phase-five"


@pytest.mark.asyncio
async def test_admin_dependency_rejects_non_admin() -> None:
    user = User(
        external_user_id="ordinary-user",
        display_name="普通用户",
        role="user",
        status="active",
    )
    with pytest.raises(AppException) as error:
        await require_admin(user)  # type: ignore[arg-type]
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_result_service_enforces_ownership_and_exports_file(
    stage_five_database: StageFiveDatabase,
    tmp_path: Path,
) -> None:
    payload = valid_report_payload()
    storage = WorkspaceStorage(tmp_path)
    storage_key = "tasks/result-service/reports/report.html"
    file_size, sha256 = storage.write_text(storage_key, "<h1>经营归因分析报告</h1>")
    async with stage_five_database.sessions() as session:
        message = Message(
            conversation_id=stage_five_database.conversation.id,
            seq_no=1,
            role="user",
            message_type="text",
            content="查询正式报告",
        )
        session.add(message)
        await session.flush()
        task = AnalysisTask(
            user_id=stage_five_database.user.id,
            conversation_id=stage_five_database.conversation.id,
            message_id=message.id,
            client_msg_id="result-service-phase-five",
            task_status="success",
            current_step="report_ready",
            thread_id="thread-result-service",
            input_text="查询正式报告",
        )
        session.add(task)
        await session.flush()
        result = AnalysisResult(
            task_id=task.id,
            conversation_id=stage_five_database.conversation.id,
            schema_version="1.0",
            problem_definition=payload["problem_definition"],
            key_metrics_json=payload["key_metrics"],
            evidence_list_json=payload["evidence_list"],
            conclusion_text="销售额下降已确认",
            missing_data_text="无已识别的数据缺口",
            next_action_text=json.dumps(payload["next_actions"], ensure_ascii=False),
            result_markdown="# 报告",
            result_file_path=storage_key,
            report_ir_json={
                **payload,
                "generated_files": [
                    {
                        "file_type": "html",
                        "file_name": "report.html",
                        "storage_key": storage_key,
                        "file_size": file_size,
                        "sha256": sha256,
                    }
                ],
            },
            validation_status="valid",
        )
        session.add(result)
        session.add(
            ReportFile(
                task_id=task.id,
                conversation_id=stage_five_database.conversation.id,
                file_type="html",
                file_name="report.html",
                storage_key=storage_key,
                file_size=file_size,
                sha256=sha256,
            )
        )
        await session.commit()
        task_id = task.id

    service = AnalysisResultService(Settings(_env_file=None, AGENT_DATA_ROOT=str(tmp_path)))
    async with stage_five_database.sessions() as session:
        response = await service.get_owned(
            session,
            task_id,
            stage_five_database.user.id,
        )
        _, exported_path = await service.export_owned(
            session,
            task_id,
            stage_five_database.user.id,
            "html",
        )
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.resource_id == task_id)
        )
        with pytest.raises(AppException):
            await service.get_owned(session, task_id, "another-user")

    assert response.validation_status == "valid"
    assert response.generated_files[0].download_url.endswith("format=html")
    assert "storage_key" not in response.report_ir["generated_files"][0]
    assert exported_path.read_text(encoding="utf-8").startswith("<h1>")
    assert audit is not None and audit.action == "report.export"


def file_reference(file_id: str, storage_key: str) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "source_type": "attachment",
        "storage_key": storage_key,
        "file_name": Path(storage_key).name,
        "format": "csv",
    }


def problem_definition(metric: str, goal: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "subject": "经营数据",
        "time_range": "2026年7月",
        "baseline": "previous_period",
        "analysis_goal": goal,
        "dimensions": ["channel"] if metric == "sales_amount" else ["product"],
    }
