"""conversations gcs export metadata (Plan B B4)

Revision ID: 20260613_0015
Revises: 20260613_0014
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0015"
down_revision: Union[str, Sequence[str], None] = "20260613_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("conversations")}

    if "gcs_export_uri" not in cols:
        op.add_column("conversations", sa.Column("gcs_export_uri", sa.Text(), nullable=True))
    if "gcs_exported_at" not in cols:
        op.add_column("conversations", sa.Column("gcs_exported_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("conversations")}

    if "gcs_exported_at" in cols:
        op.drop_column("conversations", "gcs_exported_at")
    if "gcs_export_uri" in cols:
        op.drop_column("conversations", "gcs_export_uri")
