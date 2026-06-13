"""life workspace outlook plugins

Revision ID: 20260611_0007
Revises: 20260610_0006
Create Date: 2026-06-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260611_0007"
down_revision: Union[str, Sequence[str], None] = "20260610_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "life_outlook_connections",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_mail_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_calendar_sync_at", sa.DateTime(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_table(
        "life_inbox_briefs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("graph_message_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("from_address", sa.String(length=255), nullable=False),
        sa.Column("from_name", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("body_preview", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("summary_engine", sa.String(length=32), nullable=False),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "graph_message_id", name="uq_life_inbox_graph_msg"),
    )
    op.create_table(
        "life_calendar_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("graph_event_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("organizer", sa.String(length=255), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "graph_event_id", name="uq_life_calendar_graph_evt"),
    )


def downgrade() -> None:
    op.drop_table("life_calendar_events")
    op.drop_table("life_inbox_briefs")
    op.drop_table("life_outlook_connections")
