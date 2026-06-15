"""Indexed-progress engine — the hero metric (Schema.md §8).

This is PF Coach's load-bearing differentiator over MARLON. PF's floor is heterogeneous
(a leg press logs pin 12; a hack squat logs 135 lb), and the weekly rotation engine
intentionally swaps exercises in and out. You cannot average those raw numbers, and a naive
per-exercise line breaks every time rotation changes the exercise.

The fix, in three moves:

1. Compute one ``session_metric`` per performed exercise, gated by ``measurement_type``
   (est-1RM for plate/smith; a volume-load proxy for selectorized that folds in the pin and
   any micro-load adders; volume-load for functional/bodyweight; cardio/circuit on their own
   track).
2. **Index** every metric to that exercise's own first session = 100, so units cancel.
3. Roll indexed values up to a **pattern-trend** — a recency-weighted average across all
   exercises sharing a movement pattern — which stays continuous across rotation.

Everything here is intentionally pure (no DB, no ORM imports beyond the enum vocabulary) so
it is trivially testable and portable. Routers gather the raw points from the DB and hand
them to these functions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple, Union

from config import settings
from enums import MeasurementType, MetricKind

# Unit conversions (we normalize to lb / meters internally; indexing cancels the unit, but
# consistent internal units keep cross-set sums honest).
KG_TO_LB = 2.2046226218
DISTANCE_TO_M = {"mi": 1609.344, "km": 1000.0, "m": 1.0}


# ─── Coercion helpers ───────────────────────────────────────────────────────────

def _f(value, default: float = 0.0) -> float:
    """Coerce a possibly-None Decimal/int/str to float."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _enum_value(x) -> Optional[str]:
    """Normalize an enum member or raw string to its value string."""
    if x is None:
        return None
    return x.value if hasattr(x, "value") else str(x)


def _unit(x) -> Optional[str]:
    return _enum_value(x)


def to_lb(weight_value, weight_unit) -> float:
    """Resolve a logged weight to pounds (kg → lb if needed)."""
    v = _f(weight_value)
    if v == 0.0:
        return 0.0
    return v * KG_TO_LB if _unit(weight_unit) == "kg" else v


def to_meters(distance_value, distance_unit) -> float:
    v = _f(distance_value)
    if v == 0.0:
        return 0.0
    return v * DISTANCE_TO_M.get(_unit(distance_unit) or "m", 1.0)


# ─── effective_step (Schema.md §8.1) ────────────────────────────────────────────

def effective_step(set_entry, equipment_type=None) -> float:
    """Fold incremental adders into the pin position so progress made *without* moving the
    pin still registers::

        effective_step = pin_position
                       + added_load_lb / nominal_plate_lb     (labeled +5/+10 dial)
                       + micro_load_notches * NOTCH_FRACTION   (unlabeled lever/magnet)

    Accepts any object exposing the ``set_entries`` columns (ORM row or a stand-in).
    """
    step = _f(getattr(set_entry, "pin_position", None))

    nominal = _f(getattr(equipment_type, "nominal_plate_lb", None)) if equipment_type else 0.0
    if nominal <= 0:
        nominal = settings.default_nominal_plate_lb

    added = _f(getattr(set_entry, "added_load_lb", None))
    if added and nominal:
        step += added / nominal

    notches = _f(getattr(set_entry, "micro_load_notches", None))
    if notches:
        step += notches * settings.notch_fraction

    return step


def epley_1rm(load_lb: float, reps: float) -> float:
    """Epley estimated 1RM: ``load * (1 + reps/30)``."""
    if load_lb <= 0 or reps <= 0:
        return 0.0
    return load_lb * (1.0 + reps / 30.0)


# ─── Per-session metric (Schema.md §8.1) ────────────────────────────────────────

def compute_session_metric(
    measurement_type,
    set_entries: Sequence,
    equipment_type=None,
) -> Tuple[MetricKind, Optional[float]]:
    """Compute one ``(metric_kind, value)`` for a performed exercise from its logged sets.

    - plate_loaded / smith → est-1RM of the best working set (load includes ``bar_weight_lb``)
    - selectorized         → Σ ``effective_step × reps`` (volume-load proxy)
    - functional/bodyweight→ Σ ``(load or 1) × reps`` (volume-load)
    - cardio               → total distance (else total duration) — own dashboard
    - circuit              → total time-under-tension (else duration) — consistency-oriented
    """
    mt = _enum_value(measurement_type)
    sets = list(set_entries or [])
    if not sets:
        return MetricKind.none, None

    if mt in (MeasurementType.plate_loaded.value, MeasurementType.smith.value):
        bar = _f(getattr(equipment_type, "bar_weight_lb", None)) if equipment_type else 0.0
        best = 0.0
        for s in sets:
            reps = _f(getattr(s, "reps", None))
            if reps <= 0 or getattr(s, "weight_value", None) is None:
                continue
            load = to_lb(s.weight_value, getattr(s, "weight_unit", None)) + bar
            best = max(best, epley_1rm(load, reps))
        return (MetricKind.est_1rm, round(best, 3)) if best > 0 else (MetricKind.none, None)

    if mt == MeasurementType.selectorized.value:
        total = 0.0
        for s in sets:
            reps = _f(getattr(s, "reps", None))
            if reps <= 0:
                continue
            total += effective_step(s, equipment_type) * reps
        return (MetricKind.volume_load, round(total, 3)) if total > 0 else (MetricKind.none, None)

    if mt in (MeasurementType.functional.value, MeasurementType.bodyweight.value):
        total = 0.0
        for s in sets:
            reps = _f(getattr(s, "reps", None))
            if reps <= 0:
                continue
            load = to_lb(getattr(s, "weight_value", None), getattr(s, "weight_unit", None)) or 1.0
            total += load * reps
        return (MetricKind.volume_load, round(total, 3)) if total > 0 else (MetricKind.none, None)

    if mt == MeasurementType.cardio.value:
        dist = sum(
            to_meters(getattr(s, "distance_value", None), getattr(s, "distance_unit", None))
            for s in sets
        )
        if dist > 0:
            return MetricKind.distance, round(dist, 3)
        dur = sum(_f(getattr(s, "duration_seconds", None)) for s in sets)
        if dur > 0:
            return MetricKind.duration, round(dur, 3)
        return MetricKind.none, None

    if mt == MeasurementType.circuit.value:
        tut = sum(_f(getattr(s, "tut_seconds", None)) for s in sets)
        if tut > 0:
            return MetricKind.duration, round(tut, 3)
        dur = sum(_f(getattr(s, "duration_seconds", None)) for s in sets)
        if dur > 0:
            return MetricKind.duration, round(dur, 3)
        return MetricKind.none, None

    return MetricKind.none, None


# ─── Indexing & roll-up (Schema.md §8.2) ────────────────────────────────────────

@dataclass
class MetricPoint:
    """One per-session metric for one exercise. ``pin_position`` (if any) drives pin badges."""

    recorded_at: datetime
    value: float
    exercise_id: Optional[str] = None
    pin_position: Optional[int] = None


@dataclass
class IndexedPoint:
    recorded_at: datetime
    value: float
    indexed: float


def index_points(points: Sequence[MetricPoint]) -> List[IndexedPoint]:
    """Index a single exercise's metric series to its own first (positive) value = 100."""
    pts = sorted([p for p in points if p and p.value and p.value > 0], key=lambda p: p.recorded_at)
    if not pts:
        return []
    baseline = pts[0].value
    return [
        IndexedPoint(recorded_at=p.recorded_at, value=p.value, indexed=round(p.value / baseline * 100.0, 2))
        for p in pts
    ]


def _recency_weight(age_days: float, halflife_days: float) -> float:
    """Exponential recency weight: 1.0 at age 0, 0.5 at one half-life."""
    if halflife_days <= 0:
        return 1.0
    return 0.5 ** (age_days / halflife_days)


def pattern_trend_series(
    points_by_exercise: Dict[str, Sequence[MetricPoint]],
    halflife_days: Optional[int] = None,
) -> List[Dict[str, Union[datetime, float]]]:
    """The hero metric: a recency-weighted average of indexed values across all exercises in
    a pattern, sampled at every date any of them was performed.

    At each date ``d``, each exercise contributes its most recent indexed value as of ``d``,
    weighted by how recently it was observed (a stale exercise fades, it doesn't vanish), so
    the line stays continuous when rotation swaps exercises in and out.
    """
    halflife = halflife_days or settings.pattern_trend_halflife_days
    indexed_by_ex = {ex: index_points(pts) for ex, pts in points_by_exercise.items()}
    indexed_by_ex = {ex: series for ex, series in indexed_by_ex.items() if series}
    if not indexed_by_ex:
        return []

    all_dates = sorted({pt.recorded_at for series in indexed_by_ex.values() for pt in series})
    out: List[Dict[str, Union[datetime, float]]] = []
    for d in all_dates:
        num = den = 0.0
        for series in indexed_by_ex.values():
            prior = [pt for pt in series if pt.recorded_at <= d]
            if not prior:
                continue
            last = prior[-1]
            age = (d - last.recorded_at).total_seconds() / 86400.0
            w = _recency_weight(age, halflife)
            num += w * last.indexed
            den += w
        if den > 0:
            out.append({"recorded_at": d, "value": round(num / den, 2)})
    return out


@dataclass
class PinBadge:
    recorded_at: datetime
    from_pin: int
    to_pin: int
    exercise_id: Optional[str] = None


def detect_pin_badges(points: Sequence[MetricPoint]) -> List[PinBadge]:
    """Surface each *new high* pin as a celebrated milestone, so the proxy's post-jump dip
    (more pin, fewer reps) reads as a win instead of a confusing regression (Schema.md §8.1)."""
    pts = sorted(
        [p for p in points if p and p.pin_position], key=lambda p: p.recorded_at
    )
    badges: List[PinBadge] = []
    running_max: Optional[int] = None
    for p in pts:
        pin = int(p.pin_position)
        if running_max is not None and pin > running_max:
            badges.append(
                PinBadge(recorded_at=p.recorded_at, from_pin=running_max, to_pin=pin, exercise_id=p.exercise_id)
            )
        running_max = pin if running_max is None else max(running_max, pin)
    return badges
