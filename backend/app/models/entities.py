from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin, TimestampMixin, utc_now
from app.models.types import MediumText


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    external_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_status_updated", "user_id", "status", "updated_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq_no", name="uq_messages_conversation_seq"),
        UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_messages_conversation_client_msg",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    client_msg_id: Mapped[str | None] = mapped_column(String(100))
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")
    tool_name: Mapped[str | None] = mapped_column(String(60))
    tool_status: Mapped[str | None] = mapped_column(String(30))
    content: Mapped[str | None] = mapped_column(MediumText())
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Attachment(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_conversation_created", "conversation_id", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    parse_error: Mapped[str | None] = mapped_column(String(1000))


class AnalysisTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "conversation_id",
            "client_msg_id",
            name="uq_tasks_user_conversation_client_msg",
        ),
        Index("ix_tasks_conversation_status", "conversation_id", "task_status"),
        Index("ix_tasks_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_msg_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    current_step: Mapped[str | None] = mapped_column(String(60))
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(1000))


class TaskEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "event_seq", name="uq_task_events_task_seq"),
        Index("ix_task_events_conversation_created", "conversation_id", "created_at"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AnalysisResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "analysis_results"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    problem_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    key_metrics_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_list_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    conclusion_text: Mapped[str] = mapped_column(MediumText(), nullable=False)
    missing_data_text: Mapped[str] = mapped_column(MediumText(), nullable=False)
    next_action_text: Mapped[str] = mapped_column(MediumText(), nullable=False)
    result_markdown: Mapped[str | None] = mapped_column(MediumText())
    result_file_path: Mapped[str | None] = mapped_column(String(500))
    report_ir_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")


class ReportFile(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "report_files"
    __table_args__ = (Index("ix_report_files_task_type", "task_id", "file_type"),)

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContextSummary(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "context_summaries"
    __table_args__ = (
        Index("ix_context_summaries_conversation_end", "conversation_id", "end_seq_no"),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    end_seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text: Mapped[str] = mapped_column(MediumText(), nullable=False)
    summary_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WebsocketToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "websocket_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemConfig(IdMixin, Base):
    __tablename__ = "system_configs"

    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config_group: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class TaskLog(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_logs"
    __table_args__ = (
        Index("ix_task_logs_task_created", "task_id", "created_at"),
        Index("ix_task_logs_trace_created", "trace_id", "created_at"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    log_level: Mapped[str] = mapped_column(String(20), nullable=False)
    log_type: Mapped[str] = mapped_column(String(30), nullable=False)
    log_content: Mapped[str] = mapped_column(MediumText(), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(100))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)


class AuditLog(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_trace_created", "trace_id", "created_at"),
    )

    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(100))


class DataSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")
