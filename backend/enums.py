"""Domain enum vocabulary (Schema.md §1).

Pure stdlib enums with **no** SQLAlchemy/DB dependency, so the domain vocabulary can be
imported by the pure logic engines (``progress.py``, ``rotation.py``) and unit-tested
without a database. ``models.py`` imports these and wires them to PG ENUM types.
"""

import enum


class MeasurementType(str, enum.Enum):
    selectorized = "selectorized"
    plate_loaded = "plate_loaded"
    smith = "smith"
    cardio = "cardio"
    circuit = "circuit"
    functional = "functional"
    bodyweight = "bodyweight"


class AutonomyMode(str, enum.Enum):
    guided = "guided"
    coached = "coached"
    self_directed = "self_directed"


class MembershipTier(str, enum.Enum):
    classic = "classic"
    black_card = "black_card"


class UserRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class RecordStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    disabled = "disabled"


class EquipmentCategory(str, enum.Enum):
    cardio = "cardio"
    strength = "strength"
    functional = "functional"
    circuit = "circuit"


class StackUnit(str, enum.Enum):
    pin_number = "pin_number"
    lb = "lb"
    kg = "kg"


class WeightUnit(str, enum.Enum):
    lb = "lb"
    kg = "kg"


class DistanceUnit(str, enum.Enum):
    mi = "mi"
    km = "km"
    m = "m"


class DifficultyLevel(str, enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class SessionType(str, enum.Enum):
    express_circuit = "express_circuit"
    standard = "standard"


class SessionStatus(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class SwapReason(str, enum.Enum):
    unavailable = "unavailable"
    occupied = "occupied"
    preference = "preference"
    other_club = "other_club"


class MetricKind(str, enum.Enum):
    est_1rm = "est_1rm"
    volume_load = "volume_load"
    distance = "distance"
    duration = "duration"
    none = "none"


class MicroLoadKind(str, enum.Enum):
    none = "none"
    magnet = "magnet"
    lever = "lever"
    dial = "dial"
