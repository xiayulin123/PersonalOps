"""users + user_api_credentials + workspaces.user_id (Plan B B1)

Revision ID: 20260613_0013
Revises: 20260612_0012
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0013"
down_revision: Union[str, Sequence[str], None] = "20260612_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "user_api_credentials" not in tables:
        op.create_table(
            "user_api_credentials",
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("provider", sa.String(length=32), primary_key=True),
            sa.Column("encrypted_secret", sa.Text(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
        )

    cols = {c["name"] for c in inspector.get_columns("workspaces")}
    if "user_id" not in cols:
        op.add_column(
            "workspaces",
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workspaces")}
    if "user_id" in cols:
        op.drop_index("ix_workspaces_user_id", table_name="workspaces")
        op.drop_column("workspaces", "user_id")
    if "user_api_credentials" in inspector.get_table_names():
        op.drop_table("user_api_credentials")
    if "users" in inspector.get_table_names():
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
