"""SQLAlchemy ORM models for PF Coach.

Source of truth for the data layer (Schema.md). Alembic migrations are written to match
these models. Conventions (Schema.md §0):
  - UUID primary keys, default ``gen_random_uuid()`` (Postgres 13+ core function).
  - ``timestamptz`` everywhere; ``created_at`` / ``updated_at`` default ``now()``.
  - Never hard-delete — soft-delete via ``status`` + ``deleted_at``; reversals are audited.
  - Units are explicit — never a bare "weight"; always a value column + a unit column.
  - Hot reads denormalize ``measurement_type`` and the computed ``session_metric`` onto
    session rows so progress/logging don't chase joins.

The PG ENUM types are created explicitly in the initial Alembic migration (``create_type``
is ``False`` here so SQLAlchemy never tries to create/drop them implicitly).
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database import Base

# The domain enum vocabulary lives in enums.py (pure stdlib, no DB dependency) so the
# logic engines can import it without pulling in SQLAlchemy. Re-exported here for callers
# that do `from models import MeasurementType`, etc.
from enums import (  # noqa: F401  (re-export)
    AutonomyMode,
    DifficultyLevel,
    DistanceUnit,
    EquipmentCategory,
    MeasurementType,
    MembershipTier,
    MetricKind,
    MicroLoadKind,
    RecordStatus,
    SessionStatus,
    SessionType,
    StackUnit,
    SwapReason,
    UserRole,
    WeightUnit,
)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _pk():
    """Fresh UUID primary-key column with a server-side default."""
    return Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _enum(enum_cls, name):
    """PG ENUM column type. ``create_type=False`` — the migration owns type creation."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda obj: [e.value for e in obj],
    )


def _created_at():
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at():
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ─── Identity & intake (Schema.md §3) ──────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = _pk()
    # Stored lowercased + a unique index on lower(email) gives citext-like behavior
    # without the citext extension (see Schema.md note / README deviation).
    email = Column(String(320), nullable=False)
    password_hash = Column(Text, nullable=False)  # bcrypt
    display_name = Column(Text)
    locale = Column(String(5), nullable=False, server_default="en")  # 'en' | 'es'
    role = Column(_enum(UserRole, "user_role"), nullable=False, server_default=UserRole.member.value)
    membership_tier = Column(
        _enum(MembershipTier, "membership_tier"),
        nullable=False,
        server_default=MembershipTier.classic.value,
    )
    home_club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id"))

    # Denormalized current intake snapshot (history lives in intake_responses).
    autonomy_mode = Column(
        _enum(AutonomyMode, "autonomy_mode"),
        nullable=False,
        server_default=AutonomyMode.guided.value,
    )
    goal = Column(Text)  # 'general_fitness' | 'weight_loss' | 'strength' | ...
    experience_level = Column(
        _enum(DifficultyLevel, "difficulty_level"),
        nullable=False,
        server_default=DifficultyLevel.beginner.value,
    )
    days_per_week = Column(SmallInteger)
    cardio_pct = Column(SmallInteger, CheckConstraint("cardio_pct BETWEEN 0 AND 100"))
    strength_pct = Column(SmallInteger, CheckConstraint("strength_pct BETWEEN 0 AND 100"))

    status = Column(
        _enum(RecordStatus, "record_status"),
        nullable=False,
        server_default=RecordStatus.active.value,
    )
    deleted_at = Column(DateTime(timezone=True))
    created_at = _created_at()
    updated_at = _updated_at()

    home_club = relationship("Club", foreign_keys=[home_club_id])
    intake_responses = relationship("IntakeResponse", back_populates="user")

    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        Index("ix_users_home_club", "home_club_id"),
    )


class IntakeResponse(Base):
    """Versioned intake so re-running the interview keeps history and is auditable."""

    __tablename__ = "intake_responses"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    answers = Column(JSONB, nullable=False)  # raw interview payload
    recommended_mode = Column(_enum(AutonomyMode, "autonomy_mode"), nullable=False)
    rationale = Column(Text)  # the "here's why" shown on the placement screen
    created_at = _created_at()

    user = relationship("User", back_populates="intake_responses")

    __table_args__ = (Index("ix_intake_responses_user", "user_id"),)


# ─── Clubs & equipment (Schema.md §4) ──────────────────────────────────────────

class Club(Base):
    __tablename__ = "clubs"

    id = _pk()
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    address = Column(Text)
    lat = Column(Numeric(9, 6))
    lng = Column(Numeric(9, 6))
    is_demo = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = _created_at()

    equipment = relationship("ClubEquipment", back_populates="club")


class EquipmentType(Base):
    """Canonical catalog of machine/equipment kinds, club-independent.

    This is where the Smith-bar and pin-vs-pounds problems are resolved once, centrally.
    """

    __tablename__ = "equipment_types"

    id = _pk()
    name = Column(Text, nullable=False)  # 'Chest Press (selectorized)'
    category = Column(_enum(EquipmentCategory, "equipment_category"), nullable=False)
    measurement_type = Column(_enum(MeasurementType, "measurement_type"), nullable=False)
    bar_weight_lb = Column(Numeric(6, 2))     # Smith/plate: effective (often NOT 45)
    stack_unit = Column(_enum(StackUnit, "stack_unit"))  # selectorized labeling
    stack_map = Column(JSONB)                 # DEFERRED: optional pin_number -> lb mapping
    nominal_plate_lb = Column(Numeric(5, 2))  # ~lb per pin step; lets dial/lever increments
                                              # convert to a fractional pin step
    notes = Column(Text)
    created_at = _created_at()


class ClubEquipment(Base):
    """Availability: which equipment exists at which club. Drives rotation + swap filtering."""

    __tablename__ = "club_equipment"

    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id"), primary_key=True)
    equipment_type_id = Column(
        UUID(as_uuid=True), ForeignKey("equipment_types.id"), primary_key=True
    )
    quantity = Column(SmallInteger, nullable=False, server_default="1")
    is_available = Column(Boolean, nullable=False, server_default=text("true"))  # broken/OOS toggle

    club = relationship("Club", back_populates="equipment")
    equipment_type = relationship("EquipmentType")

    __table_args__ = (Index("ix_club_equipment_equipment", "equipment_type_id"),)


# ─── Exercise library & movement patterns (Schema.md §5) ───────────────────────

class MovementPattern(Base):
    __tablename__ = "movement_patterns"

    id = _pk()
    key = Column(Text, nullable=False, unique=True)  # 'horizontal_push', 'vertical_pull', ...
    name = Column(Text, nullable=False)
    display_order = Column(SmallInteger, nullable=False, server_default="0")


class Exercise(Base):
    __tablename__ = "exercises"

    id = _pk()
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    measurement_type = Column(
        _enum(MeasurementType, "measurement_type"), nullable=False
    )  # source of truth for logging UI
    equipment_type_id = Column(UUID(as_uuid=True), ForeignKey("equipment_types.id"))
    primary_pattern_id = Column(UUID(as_uuid=True), ForeignKey("movement_patterns.id"))
    secondary_pattern_id = Column(UUID(as_uuid=True), ForeignKey("movement_patterns.id"))
    muscle_groups = Column(JSONB)  # ['chest','triceps','front_delts']
    difficulty = Column(
        _enum(DifficultyLevel, "difficulty_level"),
        nullable=False,
        server_default=DifficultyLevel.beginner.value,
    )
    is_anchor = Column(Boolean, nullable=False, server_default=text("false"))  # core compound, no rotate
    video_url = Column(Text)  # LINKED (YouTube), never rehosted
    instructions = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = _created_at()
    updated_at = _updated_at()

    equipment_type = relationship("EquipmentType")
    primary_pattern = relationship("MovementPattern", foreign_keys=[primary_pattern_id])
    secondary_pattern = relationship("MovementPattern", foreign_keys=[secondary_pattern_id])

    __table_args__ = (
        Index("ix_exercises_pattern", "primary_pattern_id"),
        Index("ix_exercises_equipment", "equipment_type_id"),
    )


# ─── Programs & rotation (Schema.md §6) ─────────────────────────────────────────

class Program(Base):
    __tablename__ = "programs"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(Text)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id"))  # home club plan is generated against
    autonomy_mode_at_creation = Column(_enum(AutonomyMode, "autonomy_mode"), nullable=False)
    start_date = Column(Date)
    status = Column(
        _enum(RecordStatus, "record_status"),
        nullable=False,
        server_default=RecordStatus.active.value,
    )
    deleted_at = Column(DateTime(timezone=True))
    created_at = _created_at()

    user = relationship("User")
    club = relationship("Club")
    weeks = relationship("ProgramWeek", back_populates="program", order_by="ProgramWeek.week_number")

    __table_args__ = (Index("ix_programs_user", "user_id"),)


class ProgramWeek(Base):
    __tablename__ = "program_weeks"

    id = _pk()
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    week_number = Column(SmallInteger, nullable=False)
    start_date = Column(Date)
    is_current = Column(Boolean, nullable=False, server_default=text("false"))
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    program = relationship("Program", back_populates="weeks")
    slots = relationship("ProgramSlot", back_populates="week", order_by="ProgramSlot.slot_index")

    __table_args__ = (UniqueConstraint("program_id", "week_number", name="uq_program_week"),)


class ProgramSlot(Base):
    """A stable pattern slot filled with the exercise chosen for that week.

    Anchor slots keep the same exercise across weeks; variety slots rotate (filled by the
    rotation engine from the pattern's pool, constrained to the program club's equipment).
    """

    __tablename__ = "program_slots"

    id = _pk()
    program_week_id = Column(UUID(as_uuid=True), ForeignKey("program_weeks.id"), nullable=False)
    slot_index = Column(SmallInteger, nullable=False)
    pattern_id = Column(UUID(as_uuid=True), ForeignKey("movement_patterns.id"), nullable=False)  # STABLE part
    exercise_id = Column(UUID(as_uuid=True), ForeignKey("exercises.id"), nullable=False)  # rotated-in choice
    is_anchor = Column(Boolean, nullable=False, server_default=text("false"))
    prescribed_sets = Column(SmallInteger)
    prescribed_reps = Column(SmallInteger)
    prescribed_target = Column(JSONB)  # cardio/circuit targets (duration, level, ...)
    notes = Column(Text)

    week = relationship("ProgramWeek", back_populates="slots")
    pattern = relationship("MovementPattern")
    exercise = relationship("Exercise")

    __table_args__ = (UniqueConstraint("program_week_id", "slot_index", name="uq_slot_index"),)


# ─── Sessions & logging — the measurement-type taxonomy (Schema.md §7) ──────────

class Session(Base):
    __tablename__ = "sessions"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    program_week_id = Column(UUID(as_uuid=True), ForeignKey("program_weeks.id"))  # null = ad-hoc
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=False)  # current_club (overridable)
    session_type = Column(
        _enum(SessionType, "session_type"),
        nullable=False,
        server_default=SessionType.standard.value,
    )
    status = Column(
        _enum(SessionStatus, "session_status"),
        nullable=False,
        server_default=SessionStatus.planned.value,
    )
    scheduled_date = Column(Date)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = _created_at()

    user = relationship("User")
    club = relationship("Club")
    exercises = relationship(
        "SessionExercise", back_populates="session", order_by="SessionExercise.order_index"
    )

    __table_args__ = (
        Index("ix_sessions_user", "user_id"),
        Index("ix_sessions_user_status", "user_id", "status"),
    )


class SessionExercise(Base):
    """One performed exercise in a session. Snapshots ``measurement_type`` and the computed
    ``session_metric`` (Schema.md §8) so progress queries don't chase joins. Swap tracking is
    folded in (no separate table for the demo)."""

    __tablename__ = "session_exercises"

    id = _pk()
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    exercise_id = Column(UUID(as_uuid=True), ForeignKey("exercises.id"), nullable=False)
    source_slot_id = Column(UUID(as_uuid=True), ForeignKey("program_slots.id"))  # which slot it came from
    order_index = Column(SmallInteger, nullable=False)
    measurement_type = Column(_enum(MeasurementType, "measurement_type"), nullable=False)  # snapshot
    prescribed = Column(JSONB)  # targets carried from the slot

    # Swap tracking.
    was_swapped = Column(Boolean, nullable=False, server_default=text("false"))
    swapped_from_exercise_id = Column(UUID(as_uuid=True), ForeignKey("exercises.id"))
    swap_reason = Column(_enum(SwapReason, "swap_reason"))

    # Denormalized progress metric (computed on completion, Schema.md §8).
    session_metric_kind = Column(
        _enum(MetricKind, "metric_kind"),
        nullable=False,
        server_default=MetricKind.none.value,
    )
    session_metric_value = Column(Numeric(10, 3))

    notes = Column(Text)
    created_at = _created_at()

    session = relationship("Session", back_populates="exercises")
    exercise = relationship("Exercise", foreign_keys=[exercise_id])
    swapped_from_exercise = relationship("Exercise", foreign_keys=[swapped_from_exercise_id])
    source_slot = relationship("ProgramSlot")
    set_entries = relationship(
        "SetEntry", back_populates="session_exercise", order_by="SetEntry.set_number"
    )

    __table_args__ = (
        Index("ix_sx_session", "session_id"),
        Index("ix_sx_exercise", "exercise_id"),
    )


class SetEntry(Base):
    """Sparse-wide log: every logged dimension is a nullable column. Which ones are required
    is enforced per ``measurement_type`` in Pydantic (Schema.md §7.1), not the DB."""

    __tablename__ = "set_entries"

    id = _pk()
    session_exercise_id = Column(
        UUID(as_uuid=True), ForeignKey("session_exercises.id"), nullable=False
    )
    set_number = Column(SmallInteger, nullable=False)

    # Strength dimensions.
    reps = Column(SmallInteger)
    weight_value = Column(Numeric(7, 2))
    weight_unit = Column(_enum(WeightUnit, "weight_unit"))
    pin_position = Column(SmallInteger)  # selectorized: track the pin, not fake lbs

    # Incremental adders between pins (magnet / push-in lever / +5/+10 dial).
    micro_load_kind = Column(
        _enum(MicroLoadKind, "micro_load_kind"),
        nullable=False,
        server_default=MicroLoadKind.none.value,
    )
    added_load_lb = Column(Numeric(6, 2))   # when the adder is labeled in lb
    micro_load_notches = Column(SmallInteger)  # unlabeled stepped adder (lever/magnet count)

    # Cardio dimensions.
    distance_value = Column(Numeric(8, 3))
    distance_unit = Column(_enum(DistanceUnit, "distance_unit"))
    duration_seconds = Column(Integer)
    level = Column(SmallInteger)
    incline = Column(Numeric(4, 1))
    speed = Column(Numeric(5, 2))
    avg_hr = Column(SmallInteger)
    calories = Column(Integer)

    # Circuit / time-under-tension.
    tut_seconds = Column(Integer)

    # Shared.
    rpe = Column(Numeric(3, 1))
    extra = Column(JSONB)  # overflow for anything not columnized
    created_at = _created_at()

    session_exercise = relationship("SessionExercise", back_populates="set_entries")

    __table_args__ = (Index("ix_set_entries_parent", "session_exercise_id"),)


# ─── Progress materialization (Schema.md §8.3 — optional, deferred) ─────────────

class ExerciseProgressPoint(Base):
    """Optional precomputed progress points. Compute-on-read is the default (Schema.md §8.3);
    this table exists for materialization if pattern-trend queries get heavy. Created in a
    later migration so compute-on-read can ship first."""

    __tablename__ = "exercise_progress_points"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    exercise_id = Column(UUID(as_uuid=True), ForeignKey("exercises.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    metric_kind = Column(_enum(MetricKind, "metric_kind"), nullable=False)
    metric_value = Column(Numeric(10, 3), nullable=False)
    indexed_value = Column(Numeric(7, 2), nullable=False)  # vs this user+exercise first value
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "exercise_id", "session_id", name="uq_epp_user_ex_session"),
        Index("ix_epp_user_exercise", "user_id", "exercise_id", "recorded_at"),
    )


# ─── Body metrics (Schema.md §9) ────────────────────────────────────────────────

class BodyMetric(Base):
    __tablename__ = "body_metrics"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    weight_value = Column(Numeric(6, 2))
    weight_unit = Column(_enum(WeightUnit, "weight_unit"))
    body_fat_pct = Column(Numeric(4, 1))
    measurements = Column(JSONB)  # {'waist_in': 34, 'chest_in': 42, ...}
    notes = Column(Text)

    __table_args__ = (Index("ix_body_metrics_user", "user_id", "recorded_at"),)


# ─── Nutrition & supplements — marketing surfaces, placeholders (Schema.md §10) ──

class NutritionPartner(Base):
    __tablename__ = "nutrition_partners"

    id = _pk()
    name = Column(Text, nullable=False)
    image_url = Column(Text)
    affiliate_url = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))


class MealSuggestion(Base):
    __tablename__ = "meal_suggestions"

    id = _pk()
    partner_id = Column(UUID(as_uuid=True), ForeignKey("nutrition_partners.id"))
    day_of_week = Column(SmallInteger, CheckConstraint("day_of_week BETWEEN 0 AND 6"))  # ~1/day
    title = Column(Text, nullable=False)
    description = Column(Text)
    image_url = Column(Text)
    link_url = Column(Text)
    tags = Column(JSONB)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    partner = relationship("NutritionPartner")


class Supplement(Base):
    __tablename__ = "supplements"

    id = _pk()
    name = Column(Text, nullable=False)
    category = Column(Text)
    description = Column(Text)
    image_url = Column(Text)
    link_url = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))


# ─── Autonomy events & consistency (Schema.md §11) ──────────────────────────────

class AutonomyEvent(Base):
    """Records each invitation/transition for the autonomy-gradient nudge mechanic."""

    __tablename__ = "autonomy_events"

    id = _pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    from_mode = Column(_enum(AutonomyMode, "autonomy_mode"))
    to_mode = Column(_enum(AutonomyMode, "autonomy_mode"), nullable=False)
    trigger = Column(Text, nullable=False)  # 'nudge_consistency' | 'self_declared' | 'admin'
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("ix_autonomy_events_user", "user_id"),)


# ─── Admin reversal audit (Schema.md §12 — house principle: never hard-delete) ──

class AdminTransaction(Base):
    __tablename__ = "admin_transactions"

    id = _pk()
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(Text, nullable=False)  # 'archive_session', 'restore_program', ...
    target_table = Column(Text, nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    before_state = Column(JSONB)
    after_state = Column(JSONB)
    created_at = _created_at()
