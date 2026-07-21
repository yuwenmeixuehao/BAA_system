import re
from pathlib import Path

from app.models import Base

SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "sql" / "init_insight_agent.sql"


def test_sql_snapshot_columns_match_orm_metadata() -> None:
    sql = SNAPSHOT_PATH.read_text(encoding="utf-8")
    table_blocks = {
        table_name: body
        for table_name, body in re.findall(
            r"CREATE TABLE `([a-z_]+)` \((.*?)\) ENGINE=InnoDB",
            sql,
            flags=re.DOTALL,
        )
    }

    assert set(Base.metadata.tables) == set(table_blocks) - {"alembic_version"}
    for table_name, table in Base.metadata.tables.items():
        snapshot_columns = set(
            re.findall(
                r"^    `([a-z0-9_]+)` ",
                table_blocks[table_name],
                flags=re.MULTILINE,
            )
        )
        assert set(table.c.keys()) == snapshot_columns


def test_sql_snapshot_contains_exact_mediumtext_columns_and_head_revision() -> None:
    sql = SNAPSHOT_PATH.read_text(encoding="utf-8")
    mediumtext_columns = set(re.findall(r"`([a-z_]+)` MEDIUMTEXT", sql))

    assert mediumtext_columns == {
        "content",
        "conclusion_text",
        "missing_data_text",
        "next_action_text",
        "result_markdown",
        "summary_text",
        "log_content",
    }
    assert "VALUES ('20260721_0002')" in sql
    assert "`actor_user_id` VARCHAR(36)" in sql
    assert "`config_json` JSON NOT NULL" in sql
    assert "`secret_ref` VARCHAR(255) NULL" in sql
    assert "`connection_info`" not in sql
