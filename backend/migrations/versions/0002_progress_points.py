"""exercise_progress_points — optional progress materialization

Deferred from 0001 per Schema.md §8.3: compute-on-read ships first; this table lets
pattern-trend queries be precomputed later if they get heavy. Nothing writes to it until
materialization is turned on, so applying it is harmless.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercise_progress_points",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_kind", postgresql.ENUM(name="metric_kind", create_type=False), nullable=False),
        sa.Column("metric_value", sa.Numeric(10, 3), nullable=False),
        sa.Column("indexed_value", sa.Numeric(7, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_epp_user"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], name="fk_epp_exercise"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_epp_session"),
        sa.UniqueConstraint("user_id", "exercise_id", "session_id", name="uq_epp_user_ex_session"),
    )
    op.create_index(
        "ix_epp_user_exercise", "exercise_progress_points", ["user_id", "exercise_id", "recorded_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_epp_user_exercise", table_name="exercise_progress_points")
    op.drop_table("exercise_progress_points")
