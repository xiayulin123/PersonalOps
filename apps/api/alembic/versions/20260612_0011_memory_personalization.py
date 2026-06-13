"""extend memory table for agent personalization P1

Revision ID: 20260612_0011
Revises: 20260612_0010
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_0011"
down_revision: Union[str, Sequence[str], None] = "20260612_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("memory")}

    if "source" not in cols:
        op.add_column(
            "memory",
            sa.Column(
                "source",
                sa.String(length=16),
                nullable=False,
                server_default="manual",
            ),
        )
    if "kind" not in cols:
        op.add_column(
            "memory",
            sa.Column(
                "kind",
                sa.String(length=16),
                nullable=False,
                server_default="memory",
            ),
        )
    if "status" not in cols:
        op.add_column(
            "memory",
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            ),
        )
    if "confidence" not in cols:
        op.add_column(
            "memory",
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="1.0",
            ),
        )
    if "period_start" not in cols:
        op.add_column("memory", sa.Column("period_start", sa.Date(), nullable=True))
    if "updated_at" not in cols:
        # SQLite cannot ADD COLUMN with CURRENT_TIMESTAMP default — add nullable, backfill.
        op.add_column("memory", sa.Column("updated_at", sa.DateTime(), nullable=True))
        op.execute(sa.text("UPDATE memory SET updated_at = CURRENT_TIMESTAMP"))


def downgrade() -> None:
    for col in ("updated_at", "period_start", "confidence", "status", "kind", "source"):
        op.drop_column("memory", col)
