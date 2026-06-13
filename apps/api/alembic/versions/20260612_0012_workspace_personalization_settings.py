"""workspace personalization_settings_json for P2

Revision ID: 20260612_0012
Revises: 20260612_0011
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_0012"
down_revision: Union[str, Sequence[str], None] = "20260612_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workspaces")}
    if "personalization_settings_json" not in cols:
        op.add_column(
            "workspaces",
            sa.Column(
                "personalization_settings_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    op.drop_column("workspaces", "personalization_settings_json")
