"""change long content columns to MySQL MEDIUMTEXT

Revision ID: 20260721_0002
Revises: 20260720_0001
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEDIUMTEXT_COLUMNS = (
    ("messages", "content", True),
    ("analysis_results", "conclusion_text", False),
    ("analysis_results", "missing_data_text", False),
    ("analysis_results", "next_action_text", False),
    ("analysis_results", "result_markdown", True),
    ("context_summaries", "summary_text", False),
    ("task_logs", "log_content", False),
)


def upgrade() -> None:
    for table_name, column_name, nullable in MEDIUMTEXT_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.Text(),
            type_=mysql.MEDIUMTEXT(),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    for table_name, column_name, nullable in reversed(MEDIUMTEXT_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=mysql.MEDIUMTEXT(),
            type_=sa.Text(),
            existing_nullable=nullable,
        )
