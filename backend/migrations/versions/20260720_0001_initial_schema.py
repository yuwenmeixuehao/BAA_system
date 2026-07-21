"""create initial insight-agent schema

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(length=36)
CREATED_AT = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", ID, primary_key=True),
        sa.Column("external_user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100)),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )

    op.create_table(
        "conversations",
        sa.Column("id", ID, primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="新会话"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index(
        "ix_conversations_user_status_updated",
        "conversations",
        ["user_id", "status", "updated_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", ID),
        sa.Column("client_msg_id", sa.String(100)),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False, server_default="text"),
        sa.Column("tool_name", sa.String(60)),
        sa.Column("tool_status", sa.String(30)),
        sa.Column("content", sa.Text()),
        sa.Column("content_json", sa.JSON()),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("conversation_id", "seq_no", name="uq_messages_conversation_seq"),
        sa.UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_messages_conversation_client_msg",
        ),
    )
    op.create_index("ix_messages_task_id", "messages", ["task_id"])
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "attachments",
        sa.Column("id", ID, primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", ID, sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.String(1000)),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_attachments_conversation_created",
        "attachments",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "analysis_tasks",
        sa.Column("id", ID, primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            ID,
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_msg_id", sa.String(100), nullable=False),
        sa.Column("task_status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(60)),
        sa.Column("thread_id", sa.String(100), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_json", sa.JSON()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(60)),
        sa.Column("error_message", sa.String(1000)),
        *_timestamps(),
        sa.UniqueConstraint(
            "user_id",
            "conversation_id",
            "client_msg_id",
            name="uq_tasks_user_conversation_client_msg",
        ),
    )
    op.create_index(
        "ix_tasks_conversation_status",
        "analysis_tasks",
        ["conversation_id", "task_status"],
    )
    op.create_index("ix_tasks_user_created", "analysis_tasks", ["user_id", "created_at"])

    op.create_table(
        "task_events",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "task_id",
            ID,
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("task_id", "event_seq", name="uq_task_events_task_seq"),
    )
    op.create_index(
        "ix_task_events_conversation_created",
        "task_events",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "task_id",
            ID,
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("problem_definition", sa.JSON(), nullable=False),
        sa.Column("key_metrics_json", sa.JSON(), nullable=False),
        sa.Column("evidence_list_json", sa.JSON(), nullable=False),
        sa.Column("conclusion_text", sa.Text(), nullable=False),
        sa.Column("missing_data_text", sa.Text(), nullable=False),
        sa.Column("next_action_text", sa.Text(), nullable=False),
        sa.Column("result_markdown", sa.Text()),
        sa.Column("result_file_path", sa.String(500)),
        sa.Column("report_ir_json", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="pending"),
        *_timestamps(),
    )

    op.create_table(
        "report_files",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "task_id",
            ID,
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_report_files_task_type", "report_files", ["task_id", "file_type"])

    op.create_table(
        "context_summaries",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_seq_no", sa.Integer(), nullable=False),
        sa.Column("end_seq_no", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_context_summaries_conversation_end",
        "context_summaries",
        ["conversation_id", "end_seq_no"],
    )

    op.create_table(
        "websocket_tokens",
        sa.Column("id", ID, primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "conversation_id",
            ID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "system_configs",
        sa.Column("id", ID, primary_key=True),
        sa.Column("config_key", sa.String(100), nullable=False, unique=True),
        sa.Column("config_value", sa.JSON(), nullable=False),
        sa.Column("config_group", sa.String(50), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("updated_by", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "updated_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "task_logs",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "task_id",
            ID,
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("log_level", sa.String(20), nullable=False),
        sa.Column("log_type", sa.String(30), nullable=False),
        sa.Column("log_content", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(100)),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_task_logs_task_created", "task_logs", ["task_id", "created_at"])
    op.create_index("ix_task_logs_trace_created", "task_logs", ["trace_id", "created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", ID, primary_key=True),
        sa.Column("actor_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=False),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("detail_json", sa.JSON()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("trace_id", sa.String(100)),
        sa.Column(
            "created_at",
            CREATED_AT,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_logs_trace_created", "audit_logs", ["trace_id", "created_at"])

    op.create_table(
        "data_sources",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("secret_ref", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="disabled"),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("data_sources")
    op.drop_table("audit_logs")
    op.drop_table("task_logs")
    op.drop_table("system_configs")
    op.drop_table("websocket_tokens")
    op.drop_table("context_summaries")
    op.drop_table("report_files")
    op.drop_table("analysis_results")
    op.drop_table("task_events")
    op.drop_table("analysis_tasks")
    op.drop_table("attachments")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
