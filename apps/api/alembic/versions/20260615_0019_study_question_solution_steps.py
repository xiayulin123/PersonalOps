"""Add solution_steps_json to study_questions for calculation items

Revision ID: 20260615_0019
Revises: 20260614_0018
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260615_0019"
down_revision: Union[str, Sequence[str], None] = "20260614_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("study_questions")}
    if "solution_steps_json" not in columns:
        op.add_column(
            "study_questions",
            sa.Column("solution_steps_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("study_questions")}
    if "solution_steps_json" in columns:
        op.drop_column("study_questions", "solution_steps_json")
