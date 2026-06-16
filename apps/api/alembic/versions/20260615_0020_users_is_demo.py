"""Add users.is_demo for read-only example account."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260615_0020"
down_revision = "20260615_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_demo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_demo")
