from collections.abc import AsyncIterator
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agent.nodes.query_data import build_data_agent_objective
from app.core.config import Settings
from app.data_agent.main import create_data_agent_app
from app.data_agent.schemas import QueryRequest
from app.data_agent.service import (
    DataAgentService,
    _controlled_query_text,
    _sales_channel_comparison_sql,
)


class StaticSqlGenerator:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.schema = ""
        self.dialect = ""

    async def generate(self, objective: str, schema: str, dialect: str) -> str:
        del objective
        self.schema = schema
        self.dialect = dialect
        return self.sql


class SequenceSqlGenerator:
    def __init__(self, *sql: str) -> None:
        self.sql = list(sql)
        self.objectives: list[str] = []

    async def generate(self, objective: str, schema: str, dialect: str) -> str:
        del schema, dialect
        self.objectives.append(objective)
        return self.sql.pop(0)


@pytest.fixture
async def business_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE inventory (sku TEXT PRIMARY KEY, stock INTEGER NOT NULL)")
        )
        await connection.execute(
            text("INSERT INTO inventory (sku, stock) VALUES ('A', 3), ('B', 8), ('C', 13)")
        )
    yield engine
    await engine.dispose()


def data_agent_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "DATA_AGENT_API_KEY": "service-secret",
        "DATA_AGENT_DATABASE_URL": "",
        "DATA_AGENT_ALLOWED_TABLES": "inventory",
        "DATA_AGENT_TIMEOUT_SECONDS": 10,
        "DATA_AGENT_MAX_SCANNED_ROWS": 1000,
        "AGENT_MAX_ROWS": 100,
    }
    values.update(overrides)
    return Settings(**values)


def query_payload(*, max_rows: int = 100) -> dict[str, object]:
    return {
        "objective": "检查库存",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "task_id": "task-1",
        "trace_id": "trace-data-agent-1",
        "limits": {
            "max_returned_rows": max_rows,
            "max_scanned_rows": 1000,
            "timeout_seconds": 10,
        },
    }


@pytest.mark.asyncio
async def test_data_agent_query_executes_allowlisted_read_only_sql(
    business_engine: AsyncEngine,
) -> None:
    generator = StaticSqlGenerator("SELECT sku, stock FROM inventory ORDER BY sku")
    config = data_agent_settings(AGENT_MAX_ROWS=2)
    service = DataAgentService(config, generator=generator, engine=business_engine)
    app = create_data_agent_app(config, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://data-agent",
    ) as client:
        response = await client.post(
            "/query",
            headers={"Authorization": "Bearer service-secret"},
            json=query_payload(max_rows=2),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sql"] == "SELECT sku, stock FROM inventory ORDER BY sku"
    assert payload["rows"] == [{"sku": "A", "stock": 3}, {"sku": "B", "stock": 8}]
    assert payload["columns"] == ["sku", "stock"]
    assert payload["truncated"] is True
    assert "inventory" in generator.schema
    assert generator.dialect == "sqlite"


@pytest.mark.asyncio
async def test_data_agent_regenerates_after_database_rejects_candidate_sql(
    business_engine: AsyncEngine,
) -> None:
    generator = SequenceSqlGenerator(
        "SELECT missing_column FROM inventory",
        "SELECT sku, stock FROM inventory ORDER BY sku",
    )
    config = data_agent_settings()
    service = DataAgentService(config, generator=generator, engine=business_engine)
    response = await service.query(
        QueryRequest(
            objective="check inventory",
            user_id="user-1",
            conversation_id="conversation-1",
            task_id="task-retry",
            trace_id="trace-retry",
            limits={
                "max_returned_rows": 2,
                "max_scanned_rows": 1000,
                "timeout_seconds": 10,
            },
        )
    )

    assert response.sql == "SELECT sku, stock FROM inventory ORDER BY sku"
    assert response.rows == [{"sku": "A", "stock": 3}, {"sku": "B", "stock": 8}]
    assert len(generator.objectives) == 2
    assert "Regenerate the SQL" in generator.objectives[1]


def test_sales_channel_comparison_fallback_uses_explicit_periods() -> None:
    objective = (
        "\u5e2e\u6211\u5206\u6790\u4e00\u4e0b\u672c\u6708\uff086\u6708\uff09"
        "\u5404\u6e20\u9053\u7684\u9500\u552e\u8868\u73b0\uff0c\u5bf9\u6bd4\u4e0a\u6708\u6570\u636e"
    )
    sql = _sales_channel_comparison_sql(
        objective,
        "mysql",
        {"biz_sales", "biz_channels"},
    )

    assert sql is not None
    assert "FROM biz_sales AS s" in sql
    assert "biz_channels AS c" in sql
    assert f"{date.today().year}-06-01" in sql
    assert f"{date.today().year}-05-01" in sql
    assert "GROUP BY c.id, c.channel_name" in sql


def test_sales_channel_comparison_fallback_matches_structured_agent_objective() -> None:
    objective = build_data_agent_objective(
        {
            "question": (
                "\u5e2e\u6211\u5206\u6790\u4e00\u4e0b\u672c\u6708\uff086\u6708\uff09"
                "\u5404\u6e20\u9053\u7684\u9500\u552e\u8868\u73b0\uff0c\u5bf9\u6bd4\u4e0a\u6708\u6570\u636e"
            ),
            "problem_definition": {
                "metric": "sales_amount",
                "time_range": "2026-06",
                "baseline": "previous_month",
                "dimensions": ["channel"],
            },
            "query_specs": [
                {
                    "objective": "sales by channel month comparison",
                    "source_preference": "data_agent",
                    "required_fields": ["total_amount", "sale_date", "channel_id"],
                    "dimensions": ["channel"],
                    "time_range": "2026-06",
                    "baseline": "previous_month",
                }
            ],
        }
    )

    sql = _sales_channel_comparison_sql(
        objective,
        "mysql",
        {"biz_sales", "biz_channels"},
    )
    assert sql is not None
    assert "current_sales_amount" in sql
    assert "previous_sales_amount" in sql


def test_controlled_query_text_preserves_original_user_question() -> None:
    request = QueryRequest(
        objective="Analyze current_month data with a generated plan",
        user_question=(
            "\u5e2e\u6211\u5206\u6790 6 \u6708\u5404\u6e20\u9053"
            "\u9500\u552e\u8868\u73b0\uff0c\u5bf9\u6bd4\u4e0a\u6708"
        ),
        user_id="user-1",
        conversation_id="conversation-1",
        task_id="task-1",
        trace_id="trace-1",
    )

    sql = _sales_channel_comparison_sql(
        _controlled_query_text(request),
        "mysql",
        {"biz_sales", "biz_channels"},
    )

    assert sql is not None
    assert f"{date.today().year}-06-01" in sql
    assert f"{date.today().year}-05-01" in sql


def test_controlled_query_ignores_hallucinated_structured_year() -> None:
    request = QueryRequest(
        objective=(
            'Use this structured request: {"time_range":"2024-06",'
            '"baseline":"previous_month"}'
        ),
        user_question=(
            "帮我分析一下本月（6月）各渠道的销售表现，对比上月数据，看看哪些渠道有问题"
        ),
        user_id="user-1",
        conversation_id="conversation-1",
        task_id="task-year-guard",
        trace_id="trace-year-guard",
    )

    sql = _sales_channel_comparison_sql(
        request.user_question or request.objective,
        "mysql",
        {"biz_sales", "biz_channels"},
    )

    assert sql is not None
    assert f"{date.today().year}-06-01" in sql
    assert "2024-06-01" not in sql


@pytest.mark.asyncio
async def test_data_agent_query_requires_bearer_secret(
    business_engine: AsyncEngine,
) -> None:
    config = data_agent_settings()
    service = DataAgentService(
        config,
        generator=StaticSqlGenerator("SELECT sku FROM inventory"),
        engine=business_engine,
    )
    app = create_data_agent_app(config, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://data-agent",
    ) as client:
        response = await client.post("/query", json=query_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "DATA_AGENT_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_data_agent_rejects_generated_write_sql(
    business_engine: AsyncEngine,
) -> None:
    config = data_agent_settings()
    service = DataAgentService(
        config,
        generator=StaticSqlGenerator("DELETE FROM inventory"),
        engine=business_engine,
    )
    app = create_data_agent_app(config, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://data-agent",
    ) as client:
        response = await client.post(
            "/query",
            headers={"Authorization": "Bearer service-secret"},
            json=query_payload(),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DATA_AGENT_SQL_REJECTED"


@pytest.mark.asyncio
async def test_data_agent_ready_checks_database_and_configuration(
    business_engine: AsyncEngine,
) -> None:
    config = data_agent_settings()
    service = DataAgentService(
        config,
        generator=StaticSqlGenerator("SELECT sku FROM inventory"),
        engine=business_engine,
    )
    app = create_data_agent_app(config, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://data-agent",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {"configured": True, "database": True, "model": True},
    }
