"""initial schema — enums + core tables

Creates the PG ENUM types first (Schema.md §14), then all core tables in dependency order.
The optional ``exercise_progress_points`` materialization table is deferred to 0002 so
compute-on-read ships first (Schema.md §8.3).

Revision ID: 0001
Revises:
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# ─── Enum definitions (name -> values) ──────────────────────────────────────────
ENUMS = {
    "measurement_type": (
        "selectorized", "plate_loaded", "smith", "cardio", "circuit", "functional", "bodyweight",
    ),
    "autonomy_mode": ("guided", "coached", "self_directed"),
    "membership_tier": ("classic", "black_card"),
    "user_role": ("member", "admin"),
    "record_status": ("active", "archived", "disabled"),
    "equipment_category": ("cardio", "strength", "functional", "circuit"),
    "stack_unit": ("pin_number", "lb", "kg"),
    "weight_unit": ("lb", "kg"),
    "distance_unit": ("mi", "km", "m"),
    "difficulty_level": ("beginner", "intermediate", "advanced"),
    "session_type": ("express_circuit", "standard"),
    "session_status": ("planned", "in_progress", "completed", "skipped"),
    "swap_reason": ("unavailable", "occupied", "preference", "other_club"),
    "metric_kind": ("est_1rm", "volume_load", "distance", "duration", "none"),
    "micro_load_kind": ("none", "magnet", "lever", "dial"),
}


def _enum(name):
    """Reference an already-created PG ENUM type in a column (does not manage the type)."""
    return postgresql.ENUM(name=name, create_type=False)


def _uuid_pk():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False,
    )


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enum types ──────────────────────────────────────────────────────────────
    for name, values in ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({vals})")

    # ── clubs ─────────────────────────────────────────────────────────────────
    op.create_table(
        "clubs",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_clubs_slug"),
    )

    # ── equipment_types ─────────────────────────────────────────────────────────
    op.create_table(
        "equipment_types",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", _enum("equipment_category"), nullable=False),
        sa.Column("measurement_type", _enum("measurement_type"), nullable=False),
        sa.Column("bar_weight_lb", sa.Numeric(6, 2)),
        sa.Column("stack_unit", _enum("stack_unit")),
        sa.Column("stack_map", postgresql.JSONB()),
        sa.Column("nominal_plate_lb", sa.Numeric(5, 2)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── movement_patterns ─────────────────────────────────────────────────────
    op.create_table(
        "movement_patterns",
        _uuid_pk(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("key", name="uq_movement_patterns_key"),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("locale", sa.String(5), nullable=False, server_default="en"),
        sa.Column("role", _enum("user_role"), nullable=False, server_default=sa.text("'member'")),
        sa.Column("membership_tier", _enum("membership_tier"), nullable=False, server_default=sa.text("'classic'")),
        sa.Column("home_club_id", postgresql.UUID(as_uuid=True)),
        sa.Column("autonomy_mode", _enum("autonomy_mode"), nullable=False, server_default=sa.text("'guided'")),
        sa.Column("goal", sa.Text()),
        sa.Column("experience_level", _enum("difficulty_level"), nullable=False, server_default=sa.text("'beginner'")),
        sa.Column("days_per_week", sa.SmallInteger()),
        sa.Column("cardio_pct", sa.SmallInteger()),
        sa.Column("strength_pct", sa.SmallInteger()),
        sa.Column("status", _enum("record_status"), nullable=False, server_default=sa.text("'active'")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["home_club_id"], ["clubs.id"], name="fk_users_home_club"),
        sa.CheckConstraint("cardio_pct BETWEEN 0 AND 100", name="ck_users_cardio_pct"),
        sa.CheckConstraint("strength_pct BETWEEN 0 AND 100", name="ck_users_strength_pct"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("ix_users_home_club", "users", ["home_club_id"])

    # ── intake_responses ─────────────────────────────────────────────────────
    op.create_table(
        "intake_responses",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_mode", _enum("autonomy_mode"), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_intake_user"),
    )
    op.create_index("ix_intake_responses_user", "intake_responses", ["user_id"])

    # ── club_equipment ─────────────────────────────────────────────────────────
    op.create_table(
        "club_equipment",
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], name="fk_club_equipment_club"),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"], name="fk_club_equipment_equipment"),
        sa.PrimaryKeyConstraint("club_id", "equipment_type_id"),
    )
    op.create_index("ix_club_equipment_equipment", "club_equipment", ["equipment_type_id"])

    # ── exercises ─────────────────────────────────────────────────────────────
    op.create_table(
        "exercises",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("measurement_type", _enum("measurement_type"), nullable=False),
        sa.Column("equipment_type_id", postgresql.UUID(as_uuid=True)),
        sa.Column("primary_pattern_id", postgresql.UUID(as_uuid=True)),
        sa.Column("secondary_pattern_id", postgresql.UUID(as_uuid=True)),
        sa.Column("muscle_groups", postgresql.JSONB()),
        sa.Column("difficulty", _enum("difficulty_level"), nullable=False, server_default=sa.text("'beginner'")),
        sa.Column("is_anchor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("video_url", sa.Text()),
        sa.Column("instructions", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"], name="fk_exercises_equipment"),
        sa.ForeignKeyConstraint(["primary_pattern_id"], ["movement_patterns.id"], name="fk_exercises_primary_pattern"),
        sa.ForeignKeyConstraint(["secondary_pattern_id"], ["movement_patterns.id"], name="fk_exercises_secondary_pattern"),
        sa.UniqueConstraint("slug", name="uq_exercises_slug"),
    )
    op.create_index("ix_exercises_pattern", "exercises", ["primary_pattern_id"])
    op.create_index("ix_exercises_equipment", "exercises", ["equipment_type_id"])

    # ── programs ────────────────────────────────────────────────────────────────
    op.create_table(
        "programs",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("club_id", postgresql.UUID(as_uuid=True)),
        sa.Column("autonomy_mode_at_creation", _enum("autonomy_mode"), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("status", _enum("record_status"), nullable=False, server_default=sa.text("'active'")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_programs_user"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], name="fk_programs_club"),
    )
    op.create_index("ix_programs_user", "programs", ["user_id"])

    # ── program_weeks ─────────────────────────────────────────────────────────
    op.create_table(
        "program_weeks",
        _uuid_pk(),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_number", sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], name="fk_program_weeks_program"),
        sa.UniqueConstraint("program_id", "week_number", name="uq_program_week"),
    )

    # ── program_slots ─────────────────────────────────────────────────────────
    op.create_table(
        "program_slots",
        _uuid_pk(),
        sa.Column("program_week_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_index", sa.SmallInteger(), nullable=False),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_anchor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prescribed_sets", sa.SmallInteger()),
        sa.Column("prescribed_reps", sa.SmallInteger()),
        sa.Column("prescribed_target", postgresql.JSONB()),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["program_week_id"], ["program_weeks.id"], name="fk_program_slots_week"),
        sa.ForeignKeyConstraint(["pattern_id"], ["movement_patterns.id"], name="fk_program_slots_pattern"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], name="fk_program_slots_exercise"),
        sa.UniqueConstraint("program_week_id", "slot_index", name="uq_slot_index"),
    )

    # ── sessions ────────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_week_id", postgresql.UUID(as_uuid=True)),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", _enum("session_type"), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("status", _enum("session_status"), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("scheduled_date", sa.Date()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user"),
        sa.ForeignKeyConstraint(["program_week_id"], ["program_weeks.id"], name="fk_sessions_week"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], name="fk_sessions_club"),
    )
    op.create_index("ix_sessions_user", "sessions", ["user_id"])
    op.create_index("ix_sessions_user_status", "sessions", ["user_id", "status"])

    # ── session_exercises ─────────────────────────────────────────────────────
    op.create_table(
        "session_exercises",
        _uuid_pk(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_slot_id", postgresql.UUID(as_uuid=True)),
        sa.Column("order_index", sa.SmallInteger(), nullable=False),
        sa.Column("measurement_type", _enum("measurement_type"), nullable=False),
        sa.Column("prescribed", postgresql.JSONB()),
        sa.Column("was_swapped", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("swapped_from_exercise_id", postgresql.UUID(as_uuid=True)),
        sa.Column("swap_reason", _enum("swap_reason")),
        sa.Column("session_metric_kind", _enum("metric_kind"), nullable=False, server_default=sa.text("'none'")),
        sa.Column("session_metric_value", sa.Numeric(10, 3)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_sx_session"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], name="fk_sx_exercise"),
        sa.ForeignKeyConstraint(["swapped_from_exercise_id"], ["exercises.id"], name="fk_sx_swapped_from"),
        sa.ForeignKeyConstraint(["source_slot_id"], ["program_slots.id"], name="fk_sx_source_slot"),
    )
    op.create_index("ix_sx_session", "session_exercises", ["session_id"])
    op.create_index("ix_sx_exercise", "session_exercises", ["exercise_id"])

    # ── set_entries (sparse-wide) ─────────────────────────────────────────────
    op.create_table(
        "set_entries",
        _uuid_pk(),
        sa.Column("session_exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("set_number", sa.SmallInteger(), nullable=False),
        sa.Column("reps", sa.SmallInteger()),
        sa.Column("weight_value", sa.Numeric(7, 2)),
        sa.Column("weight_unit", _enum("weight_unit")),
        sa.Column("pin_position", sa.SmallInteger()),
        sa.Column("micro_load_kind", _enum("micro_load_kind"), nullable=False, server_default=sa.text("'none'")),
        sa.Column("added_load_lb", sa.Numeric(6, 2)),
        sa.Column("micro_load_notches", sa.SmallInteger()),
        sa.Column("distance_value", sa.Numeric(8, 3)),
        sa.Column("distance_unit", _enum("distance_unit")),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("level", sa.SmallInteger()),
        sa.Column("incline", sa.Numeric(4, 1)),
        sa.Column("speed", sa.Numeric(5, 2)),
        sa.Column("avg_hr", sa.SmallInteger()),
        sa.Column("calories", sa.Integer()),
        sa.Column("tut_seconds", sa.Integer()),
        sa.Column("rpe", sa.Numeric(3, 1)),
        sa.Column("extra", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_exercise_id"], ["session_exercises.id"], name="fk_set_entries_sx"),
    )
    op.create_index("ix_set_entries_parent", "set_entries", ["session_exercise_id"])

    # ── body_metrics ──────────────────────────────────────────────────────────
    op.create_table(
        "body_metrics",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("weight_value", sa.Numeric(6, 2)),
        sa.Column("weight_unit", _enum("weight_unit")),
        sa.Column("body_fat_pct", sa.Numeric(4, 1)),
        sa.Column("measurements", postgresql.JSONB()),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_body_metrics_user"),
    )
    op.create_index("ix_body_metrics_user", "body_metrics", ["user_id", "recorded_at"])

    # ── nutrition_partners ─────────────────────────────────────────────────────
    op.create_table(
        "nutrition_partners",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text()),
        sa.Column("affiliate_url", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # ── meal_suggestions ─────────────────────────────────────────────────────
    op.create_table(
        "meal_suggestions",
        _uuid_pk(),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("day_of_week", sa.SmallInteger()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("link_url", sa.Text()),
        sa.Column("tags", postgresql.JSONB()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["partner_id"], ["nutrition_partners.id"], name="fk_meal_partner"),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_meal_day_of_week"),
    )

    # ── supplements ─────────────────────────────────────────────────────────────
    op.create_table(
        "supplements",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("link_url", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # ── autonomy_events ─────────────────────────────────────────────────────────
    op.create_table(
        "autonomy_events",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_mode", _enum("autonomy_mode")),
        sa.Column("to_mode", _enum("autonomy_mode"), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_autonomy_events_user"),
    )
    op.create_index("ix_autonomy_events_user", "autonomy_events", ["user_id"])

    # ── admin_transactions ─────────────────────────────────────────────────────
    op.create_table(
        "admin_transactions",
        _uuid_pk(),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_table", sa.Text(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB()),
        sa.Column("after_state", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], name="fk_admin_tx_admin"),
    )


def downgrade() -> None:
    op.drop_table("admin_transactions")
    op.drop_index("ix_autonomy_events_user", table_name="autonomy_events")
    op.drop_table("autonomy_events")
    op.drop_table("supplements")
    op.drop_table("meal_suggestions")
    op.drop_table("nutrition_partners")
    op.drop_index("ix_body_metrics_user", table_name="body_metrics")
    op.drop_table("body_metrics")
    op.drop_index("ix_set_entries_parent", table_name="set_entries")
    op.drop_table("set_entries")
    op.drop_index("ix_sx_exercise", table_name="session_exercises")
    op.drop_index("ix_sx_session", table_name="session_exercises")
    op.drop_table("session_exercises")
    op.drop_index("ix_sessions_user_status", table_name="sessions")
    op.drop_index("ix_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("program_slots")
    op.drop_table("program_weeks")
    op.drop_index("ix_programs_user", table_name="programs")
    op.drop_table("programs")
    op.drop_index("ix_exercises_equipment", table_name="exercises")
    op.drop_index("ix_exercises_pattern", table_name="exercises")
    op.drop_table("exercises")
    op.drop_index("ix_club_equipment_equipment", table_name="club_equipment")
    op.drop_table("club_equipment")
    op.drop_index("ix_intake_responses_user", table_name="intake_responses")
    op.drop_table("intake_responses")
    op.drop_index("ix_users_home_club", table_name="users")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("movement_patterns")
    op.drop_table("equipment_types")
    op.drop_table("clubs")

    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
