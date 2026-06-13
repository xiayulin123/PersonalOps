"""life inbox/calendar provider column + google connections

Revision ID: 20260612_0009
Revises: 20260612_0008
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_0009"
down_revision: Union[str, Sequence[str], None] = "20260612_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "life_inbox_briefs" in tables:
        cols = {c["name"] for c in inspector.get_columns("life_inbox_briefs")}
        if "provider" not in cols:
            op.add_column(
                "life_inbox_briefs",
                sa.Column(
                    "provider",
                    sa.String(length=32),
                    nullable=False,
                    server_default="microsoft",
                ),
            )

    if "life_calendar_events" in tables:
        cols = {c["name"] for c in inspector.get_columns("life_calendar_events")}
        if "provider" not in cols:
            op.add_column(
                "life_calendar_events",
                sa.Column(
                    "provider",
                    sa.String(length=32),
                    nullable=False,
                    server_default="microsoft",
                ),
            )

    if "life_google_connections" not in tables:
        op.create_table(
            "life_google_connections",
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("account_email", sa.String(length=255), nullable=True),
            sa.Column("refresh_token", sa.Text(), nullable=True),
            sa.Column("access_token", sa.Text(), nullable=True),
            sa.Column("token_expires_at", sa.DateTime(), nullable=True),
            sa.Column("last_mail_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_calendar_sync_at", sa.DateTime(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("workspace_id"),
        )


def downgrade() -> None:
    op.drop_table("life_google_connections")
    op.drop_column("life_calendar_events", "provider")
    op.drop_column("life_inbox_briefs", "provider")
