from sqlalchemy.dialects import mysql, sqlite

from app.models import Base

EXPECTED_TABLES = {
    "analysis_results",
    "analysis_tasks",
    "attachments",
    "audit_logs",
    "context_summaries",
    "conversations",
    "data_sources",
    "messages",
    "report_files",
    "system_configs",
    "task_events",
    "task_logs",
    "users",
    "websocket_tokens",
}


def test_initial_schema_contains_all_base_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_review_required_columns_are_present() -> None:
    users = Base.metadata.tables["users"]
    messages = Base.metadata.tables["messages"]
    results = Base.metadata.tables["analysis_results"]

    assert "username" in users.c
    assert {"tool_name", "tool_status"}.issubset(messages.c.keys())
    assert {
        "problem_definition",
        "key_metrics_json",
        "evidence_list_json",
        "conclusion_text",
        "missing_data_text",
        "next_action_text",
        "result_markdown",
        "result_file_path",
    }.issubset(results.c.keys())


def test_long_content_uses_mediumtext_only_on_mysql() -> None:
    mediumtext_columns = (
        ("messages", "content"),
        ("analysis_results", "conclusion_text"),
        ("analysis_results", "missing_data_text"),
        ("analysis_results", "next_action_text"),
        ("analysis_results", "result_markdown"),
        ("context_summaries", "summary_text"),
        ("task_logs", "log_content"),
    )

    for table_name, column_name in mediumtext_columns:
        column_type = Base.metadata.tables[table_name].c[column_name].type
        assert column_type.compile(dialect=mysql.dialect()) == "MEDIUMTEXT"
        assert column_type.compile(dialect=sqlite.dialect()) == "TEXT"

    input_text_type = Base.metadata.tables["analysis_tasks"].c.input_text.type
    assert input_text_type.compile(dialect=mysql.dialect()) == "TEXT"
