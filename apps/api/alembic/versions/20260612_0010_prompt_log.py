"""prompt log and period stats for agent personalization P0

Revision ID: 20260612_0010
Revises: 20260612_0009
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_0010"
down_revision: Union[str, Sequence[str], None] = "20260612_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_redacted", sa.Text(), nullable=True),
        sa.Column("chat_mode", sa.String(length=32), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_log_workspace_created",
        "prompt_log",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "prompt_period_stats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("prompt_count", sa.Integer(), nullable=False),
        sa.Column("distillation_status", sa.String(length=32), nullable=False),
        sa.Column("distilled_at", sa.DateTime(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "period_type",
            "period_start",
            name="uq_prompt_period_stats_workspace_period",
        ),
    )


def downgrade() -> None:
    op.drop_table("prompt_period_stats")
    op.drop_index("ix_prompt_log_workspace_created", table_name="prompt_log")
    op.drop_table("prompt_log")
