"""auth_email_challenges + users.email_verified (Plan B email auth)

Revision ID: 20260613_0017
Revises: 20260613_0016
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0017"
down_revision: Union[str, Sequence[str], None] = "20260613_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "email_verified" not in cols:
            op.add_column(
                "users",
                sa.Column(
                    "email_verified",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )

    if "auth_email_challenges" not in tables:
        op.create_table(
            "auth_email_challenges",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_auth_email_challenges_email",
            "auth_email_challenges",
            ["email"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "auth_email_challenges" in tables:
        op.drop_index("ix_auth_email_challenges_email", table_name="auth_email_challenges")
        op.drop_table("auth_email_challenges")

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "email_verified" in cols:
            op.drop_column("users", "email_verified")
