"""Progress & reporting — the hero metric and its drill-downs.

Reads the denormalized per-session metrics off completed ``session_exercises`` and runs them
through the progress engine: pattern-trend (container) → per-exercise (drill-down) → single
exercise history (deepest). Cardio gets its own dashboard; PRs/pin-badges are surfaced
separately. user_basic-style read access is fine — all endpoints are per-user.
"""

import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
import progress
from database import get_db
from enums import MeasurementType, MetricKind
from serializers import serialize_pattern

router = APIRouter(prefix="/progress", tags=["progress"])

# Metric kinds that belong to the strength pattern-trend (cardio/circuit live elsewhere).
_STRENGTH_KINDS = {MetricKind.est_1rm.value, MetricKind.volume_load.value}


def _collect(db: Session, user: models.User):
    """Gather completed-session metric points, indexed by exercise, with pattern + pin info."""
    rows = (
        db.query(
            models.SessionExercise.id.label("sx_id"),
            models.SessionExercise.exercise_id,
            models.SessionExercise.session_metric_kind,
            models.SessionExercise.session_metric_value,
            models.Session.completed_at,
            models.Exercise.primary_pattern_id,
            models.Exercise.measurement_type,
            models.Exercise.name,
        )
        .join(models.Session, models.Session.id == models.SessionExercise.session_id)
        .join(models.Exercise, models.Exercise.id == models.SessionExercise.exercise_id)
        .filter(
            models.Session.user_id == user.id,
            models.Session.status == models.SessionStatus.completed.value,
            models.Session.completed_at.isnot(None),
            models.SessionExercise.session_metric_value.isnot(None),
        )
        .all()
    )

    # Max pin per session_exercise (for pin-badge milestones).
    pin_rows = (
        db.query(models.SetEntry.session_exercise_id, func.max(models.SetEntry.pin_position))
        .group_by(models.SetEntry.session_exercise_id)
        .all()
    )
    pins = {sx_id: pin for sx_id, pin in pin_rows}

    points_by_exercise: Dict[str, List[progress.MetricPoint]] = {}
    exercise_meta: Dict[str, dict] = {}
    pattern_to_exercises: Dict[str, set] = {}

    for r in rows:
        ex_id = str(r.exercise_id)
        kind = r.session_metric_kind.value if hasattr(r.session_metric_kind, "value") else r.session_metric_kind
        mt = r.measurement_type.value if hasattr(r.measurement_type, "value") else r.measurement_type
        points_by_exercise.setdefault(ex_id, []).append(
            progress.MetricPoint(
                recorded_at=r.completed_at,
                value=float(r.session_metric_value),
                exercise_id=ex_id,
                pin_position=pins.get(r.sx_id),
            )
        )
        exercise_meta[ex_id] = {
            "exercise_id": ex_id,
            "name": r.name,
            "measurement_type": mt,
            "metric_kind": kind,
            "pattern_id": str(r.primary_pattern_id) if r.primary_pattern_id else None,
        }
        if r.primary_pattern_id is not None:
            pattern_to_exercises.setdefault(str(r.primary_pattern_id), set()).add(ex_id)

    return points_by_exercise, exercise_meta, pattern_to_exercises


def _series_dicts(series):
    return [{"date": pt["recorded_at"].isoformat(), "value": pt["value"]} for pt in series]


@router.get("/patterns")
def patterns_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """The hero view: one pattern-trend line per movement pattern (strength only)."""
    points_by_exercise, meta, pattern_to_exercises = _collect(db, current_user)
    patterns = db.query(models.MovementPattern).order_by(models.MovementPattern.display_order).all()

    out = []
    for p in patterns:
        pid = str(p.id)
        ex_ids = [e for e in pattern_to_exercises.get(pid, set()) if meta[e]["metric_kind"] in _STRENGTH_KINDS]
        pts = {e: points_by_exercise[e] for e in ex_ids}
        series = progress.pattern_trend_series(pts) if pts else []
        out.append({
            "pattern": serialize_pattern(p),
            "exercise_count": len(ex_ids),
            "current_index": series[-1]["value"] if series else None,
            "series": _series_dicts(series),
        })
    return out


@router.get("/patterns/{pattern_id}")
def pattern_detail(
    pattern_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Drill-down: the pattern-trend plus each contributing exercise's indexed series."""
    pattern = db.query(models.MovementPattern).filter(models.MovementPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")

    points_by_exercise, meta, pattern_to_exercises = _collect(db, current_user)
    pid = str(pattern_id)
    ex_ids = [e for e in pattern_to_exercises.get(pid, set()) if meta[e]["metric_kind"] in _STRENGTH_KINDS]
    pts = {e: points_by_exercise[e] for e in ex_ids}
    trend = progress.pattern_trend_series(pts) if pts else []

    exercises = []
    for ex_id in ex_ids:
        indexed = progress.index_points(points_by_exercise[ex_id])
        badges = progress.detect_pin_badges(points_by_exercise[ex_id])
        exercises.append({
            **meta[ex_id],
            "series": [{"date": ip.recorded_at.isoformat(), "value": ip.value, "indexed": ip.indexed} for ip in indexed],
            "pin_badges": [{"date": b.recorded_at.isoformat(), "from_pin": b.from_pin, "to_pin": b.to_pin} for b in badges],
        })

    return {
        "pattern": serialize_pattern(pattern),
        "trend": _series_dicts(trend),
        "current_index": trend[-1]["value"] if trend else None,
        "exercises": exercises,
    }


@router.get("/exercises/{exercise_id}")
def exercise_detail(
    exercise_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Deepest level: one exercise's metric + indexed history and its pin-badge milestones."""
    points_by_exercise, meta, _ = _collect(db, current_user)
    ex_id = str(exercise_id)
    if ex_id not in points_by_exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No completed data for this exercise")

    indexed = progress.index_points(points_by_exercise[ex_id])
    badges = progress.detect_pin_badges(points_by_exercise[ex_id])
    return {
        **meta[ex_id],
        "series": [{"date": ip.recorded_at.isoformat(), "value": ip.value, "indexed": ip.indexed} for ip in indexed],
        "pin_badges": [{"date": b.recorded_at.isoformat(), "from_pin": b.from_pin, "to_pin": b.to_pin} for b in badges],
    }


@router.get("/cardio")
def cardio_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Cardio's own dashboard — distance/duration over time, excluded from the strength trend."""
    points_by_exercise, meta, _ = _collect(db, current_user)
    out = []
    for ex_id, pts in points_by_exercise.items():
        if meta[ex_id]["measurement_type"] != MeasurementType.cardio.value:
            continue
        ordered = sorted(pts, key=lambda p: p.recorded_at)
        out.append({
            **meta[ex_id],
            "series": [{"date": p.recorded_at.isoformat(), "value": p.value} for p in ordered],
        })
    return out


@router.get("/prs")
def personal_records(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Best metric per exercise + all pin-badge milestones — the celebration surface."""
    points_by_exercise, meta, _ = _collect(db, current_user)
    out = []
    for ex_id, pts in points_by_exercise.items():
        best = max(pts, key=lambda p: p.value)
        badges = progress.detect_pin_badges(pts)
        out.append({
            **meta[ex_id],
            "best_value": best.value,
            "best_date": best.recorded_at.isoformat(),
            "pin_badges": [{"date": b.recorded_at.isoformat(), "from_pin": b.from_pin, "to_pin": b.to_pin} for b in badges],
        })
    return out
