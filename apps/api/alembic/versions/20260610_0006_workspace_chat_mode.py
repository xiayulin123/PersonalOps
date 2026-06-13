"""workspace chat_mode for dual pipeline

Revision ID: 20260610_0006
Revises: 20260610_0005
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260610_0006"
down_revision: Union[str, Sequence[str], None] = "20260610_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "chat_mode",
                sa.String(length=32),
                nullable=False,
                server_default="langgraph",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.drop_column("chat_mode")
