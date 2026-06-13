"""github links table

Revision ID: 20260608_0002
Revises: 20260607_0001
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260608_0002"
down_revision: Union[str, Sequence[str], None] = "20260607_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_links",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(length=128), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=True),
        sa.Column("repo_description", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("github_links")
