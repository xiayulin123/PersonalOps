"""files extracted_gcs_uri column (Plan B B3 OCR sidecar)

Revision ID: 20260613_0016
Revises: 20260613_0015
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0016"
down_revision: Union[str, Sequence[str], None] = "20260613_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("files")}
    if "extracted_gcs_uri" not in cols:
        op.add_column("files", sa.Column("extracted_gcs_uri", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("files")}
    if "extracted_gcs_uri" in cols:
        op.drop_column("files", "extracted_gcs_uri")
