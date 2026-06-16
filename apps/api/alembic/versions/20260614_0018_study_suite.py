"""Study workspace tables (S1): concepts, question sets, questions, attempts

Revision ID: 20260614_0018
Revises: 20260613_0017
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_0018"
down_revision: Union[str, Sequence[str], None] = "20260613_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "study_concepts" not in tables:
        op.create_table(
            "study_concepts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=512), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("key_points_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("example", sa.Text(), nullable=True),
            sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("mastery", sa.String(length=32), nullable=False, server_default="learning"),
            sa.Column(
                "source_file_ids_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_study_concepts_workspace_id",
            "study_concepts",
            ["workspace_id"],
        )

    if "study_question_sets" not in tables:
        op.create_table(
            "study_question_sets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_study_question_sets_workspace_id",
            "study_question_sets",
            ["workspace_id"],
        )

    if "study_questions" not in tables:
        op.create_table(
            "study_questions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "set_id",
                sa.String(length=36),
                sa.ForeignKey("study_question_sets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("question_type", sa.String(length=32), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("options_json", sa.Text(), nullable=True),
            sa.Column("correct_answer", sa.Text(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
            sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("topic", sa.String(length=255), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_study_questions_set_id", "study_questions", ["set_id"])
        op.create_index(
            "ix_study_questions_workspace_id",
            "study_questions",
            ["workspace_id"],
        )

    if "study_test_attempts" not in tables:
        op.create_table(
            "study_test_attempts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "set_id",
                sa.String(length=36),
                sa.ForeignKey("study_question_sets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("answers_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("score_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "started_at",
                sa.DateTime(),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_study_test_attempts_set_id",
            "study_test_attempts",
            ["set_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "study_test_attempts" in tables:
        op.drop_index("ix_study_test_attempts_set_id", table_name="study_test_attempts")
        op.drop_table("study_test_attempts")

    if "study_questions" in tables:
        op.drop_index("ix_study_questions_workspace_id", table_name="study_questions")
        op.drop_index("ix_study_questions_set_id", table_name="study_questions")
        op.drop_table("study_questions")

    if "study_question_sets" in tables:
        op.drop_index(
            "ix_study_question_sets_workspace_id",
            table_name="study_question_sets",
        )
        op.drop_table("study_question_sets")

    if "study_concepts" in tables:
        op.drop_index("ix_study_concepts_workspace_id", table_name="study_concepts")
        op.drop_table("study_concepts")
