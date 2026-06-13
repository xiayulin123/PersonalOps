"""files gcs storage columns (Plan B B3)

Revision ID: 20260613_0014
Revises: 20260613_0013
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0014"
down_revision: Union[str, Sequence[str], None] = "20260613_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("files")}

    if "storage_backend" not in cols:
        op.add_column(
            "files",
            sa.Column(
                "storage_backend",
                sa.String(length=16),
                nullable=False,
                server_default="local",
            ),
        )
    if "gcs_uri" not in cols:
        op.add_column("files", sa.Column("gcs_uri", sa.Text(), nullable=True))
    if "size_bytes" not in cols:
        op.add_column(
            "files",
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("files")}

    if "size_bytes" in cols:
        op.drop_column("files", "size_bytes")
    if "gcs_uri" in cols:
        op.drop_column("files", "gcs_uri")
    if "storage_backend" in cols:
        op.drop_column("files", "storage_backend")
