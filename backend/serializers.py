"""ORM → plain-dict serializers for API responses.

Responses are plain dicts (not Pydantic response models) so enum-member and UUID handling
is explicit and predictable. Pydantic is used for request-body validation in the routers.
"""

from typing import Optional


def _v(x):
    """Enum member → its value; pass through plain values."""
    return x.value if hasattr(x, "value") else x


def _s(x) -> Optional[str]:
    return str(x) if x is not None else None


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _num(x):
    """Numeric/Decimal → float for JSON; None stays None."""
    return float(x) if x is not None else None


def serialize_user(u) -> dict:
    return {
        "id": _s(u.id),
        "email": u.email,
        "display_name": u.display_name,
        "locale": u.locale,
        "role": _v(u.role),
        "membership_tier": _v(u.membership_tier),
        "home_club_id": _s(u.home_club_id),
        "autonomy_mode": _v(u.autonomy_mode),
        "goal": u.goal,
        "experience_level": _v(u.experience_level),
        "days_per_week": u.days_per_week,
        "cardio_pct": u.cardio_pct,
        "strength_pct": u.strength_pct,
        "created_at": _iso(u.created_at),
    }


def serialize_club(c) -> dict:
    return {
        "id": _s(c.id),
        "name": c.name,
        "slug": c.slug,
        "address": c.address,
        "is_demo": c.is_demo,
    }


def serialize_equipment_type(e) -> dict:
    return {
        "id": _s(e.id),
        "name": e.name,
        "category": _v(e.category),
        "measurement_type": _v(e.measurement_type),
        "bar_weight_lb": _num(e.bar_weight_lb),
        "stack_unit": _v(e.stack_unit),
        "nominal_plate_lb": _num(e.nominal_plate_lb),
    }


def serialize_exercise(ex) -> dict:
    return {
        "id": _s(ex.id),
        "name": ex.name,
        "slug": ex.slug,
        "measurement_type": _v(ex.measurement_type),
        "equipment_type_id": _s(ex.equipment_type_id),
        "primary_pattern_id": _s(ex.primary_pattern_id),
        "secondary_pattern_id": _s(ex.secondary_pattern_id),
        "muscle_groups": ex.muscle_groups,
        "difficulty": _v(ex.difficulty),
        "is_anchor": ex.is_anchor,
        "video_url": ex.video_url,
        "instructions": ex.instructions,
    }


def serialize_pattern(p) -> dict:
    return {
        "id": _s(p.id),
        "key": p.key,
        "name": p.name,
        "display_order": p.display_order,
    }
