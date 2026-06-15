"""Sessions & logging — create a session, log sets (sparse-wide), swap, complete.

On completion, each performed exercise's per-session metric is computed by the progress
engine (Epley est-1RM / volume-load proxy / cardio / circuit) and denormalized onto the
``session_exercises`` row, so progress queries never recompute from raw sets.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import models
import progress
import rotation
from database import get_db
from enums import SessionStatus, SessionType, SwapReason
from serializers import serialize_exercise

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ─── request models ─────────────────────────────────────────────────────────

class CreateSession(BaseModel):
    program_week_id: Optional[uuid.UUID] = None
    club_id: Optional[uuid.UUID] = None
    session_type: str = SessionType.standard.value


class SetLog(BaseModel):
    set_number: Optional[int] = None
    reps: Optional[int] = None
    weight_value: Optional[float] = None
    weight_unit: Optional[str] = None
    pin_position: Optional[int] = None
    micro_load_kind: Optional[str] = None
    added_load_lb: Optional[float] = None
    micro_load_notches: Optional[int] = None
    distance_value: Optional[float] = None
    distance_unit: Optional[str] = None
    duration_seconds: Optional[int] = None
    level: Optional[int] = None
    incline: Optional[float] = None
    speed: Optional[float] = None
    avg_hr: Optional[int] = None
    calories: Optional[int] = None
    tut_seconds: Optional[int] = None
    rpe: Optional[float] = None


class SwapRequest(BaseModel):
    to_exercise_id: uuid.UUID
    reason: str = SwapReason.unavailable.value


# ─── helpers ─────────────────────────────────────────────────────────────────

def _mt(x) -> str:
    return x.value if hasattr(x, "value") else x


def _resolve_club_id(db: Session, user: models.User, club_id: Optional[uuid.UUID]) -> uuid.UUID:
    cid = club_id or user.home_club_id
    if cid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No club specified")
    if not db.query(models.Club).filter(models.Club.id == cid).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    return cid


def _owned_session(db: Session, session_id: uuid.UUID, user: models.User) -> models.Session:
    s = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return s


def _serialize_set(se: models.SetEntry) -> dict:
    return {
        "id": str(se.id),
        "set_number": se.set_number,
        "reps": se.reps,
        "weight_value": progress._f(se.weight_value) if se.weight_value is not None else None,
        "weight_unit": _mt(se.weight_unit) if se.weight_unit else None,
        "pin_position": se.pin_position,
        "micro_load_kind": _mt(se.micro_load_kind) if se.micro_load_kind else None,
        "added_load_lb": progress._f(se.added_load_lb) if se.added_load_lb is not None else None,
        "micro_load_notches": se.micro_load_notches,
        "distance_value": progress._f(se.distance_value) if se.distance_value is not None else None,
        "distance_unit": _mt(se.distance_unit) if se.distance_unit else None,
        "duration_seconds": se.duration_seconds,
        "level": se.level,
        "incline": progress._f(se.incline) if se.incline is not None else None,
        "speed": progress._f(se.speed) if se.speed is not None else None,
        "avg_hr": se.avg_hr,
        "calories": se.calories,
        "tut_seconds": se.tut_seconds,
        "rpe": progress._f(se.rpe) if se.rpe is not None else None,
    }


def _serialize_session_exercise(sx: models.SessionExercise) -> dict:
    return {
        "id": str(sx.id),
        "order_index": sx.order_index,
        "measurement_type": _mt(sx.measurement_type),
        "prescribed": sx.prescribed,
        "was_swapped": sx.was_swapped,
        "swap_reason": _mt(sx.swap_reason) if sx.swap_reason else None,
        "session_metric_kind": _mt(sx.session_metric_kind),
        "session_metric_value": progress._f(sx.session_metric_value) if sx.session_metric_value is not None else None,
        "exercise": serialize_exercise(sx.exercise) if sx.exercise else None,
        "sets": [_serialize_set(s) for s in sx.set_entries],
    }


def _serialize_session(s: models.Session) -> dict:
    return {
        "id": str(s.id),
        "club_id": str(s.club_id),
        "program_week_id": str(s.program_week_id) if s.program_week_id else None,
        "session_type": _mt(s.session_type),
        "status": _mt(s.status),
        "scheduled_date": s.scheduled_date.isoformat() if s.scheduled_date else None,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "exercises": [_serialize_session_exercise(sx) for sx in s.exercises],
    }


# ─── endpoints ─────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(
    req: CreateSession,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    club_id = _resolve_club_id(db, current_user, req.club_id)
    session = models.Session(
        user_id=current_user.id,
        club_id=club_id,
        program_week_id=req.program_week_id,
        session_type=req.session_type,
        status=SessionStatus.planned.value,
    )
    db.add(session)
    db.flush()

    order = 0
    if req.program_week_id is not None:
        week = db.query(models.ProgramWeek).filter(models.ProgramWeek.id == req.program_week_id).first()
        if not week:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program week not found")
        for slot in week.slots:
            ex = slot.exercise
            if not ex:
                continue
            db.add(models.SessionExercise(
                session_id=session.id,
                exercise_id=ex.id,
                source_slot_id=slot.id,
                order_index=order,
                measurement_type=_mt(ex.measurement_type),
                prescribed={"sets": slot.prescribed_sets, "reps": slot.prescribed_reps,
                            "target": slot.prescribed_target},
            ))
            order += 1
    elif req.session_type == SessionType.express_circuit.value:
        # The Guided beginner on-ramp: the Express Circuit stations.
        stations = (
            db.query(models.Exercise)
            .filter(
                models.Exercise.measurement_type == models.MeasurementType.circuit.value,
                models.Exercise.is_active.is_(True),
            )
            .order_by(models.Exercise.name)
            .all()
        )
        for ex in stations:
            db.add(models.SessionExercise(
                session_id=session.id,
                exercise_id=ex.id,
                order_index=order,
                measurement_type=_mt(ex.measurement_type),
                prescribed={"work_sec": 60, "rest_sec": 30},
            ))
            order += 1

    db.commit()
    db.refresh(session)
    return _serialize_session(session)


@router.get("")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    sessions = (
        db.query(models.Session)
        .filter(models.Session.user_id == current_user.id)
        .order_by(models.Session.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": str(s.id),
            "session_type": _mt(s.session_type),
            "status": _mt(s.status),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "exercise_count": len(s.exercises),
        }
        for s in sessions
    ]


@router.get("/{session_id}")
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return _serialize_session(_owned_session(db, session_id, current_user))


@router.post("/{session_id}/start")
def start_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    s = _owned_session(db, session_id, current_user)
    if s.status == SessionStatus.planned.value:
        s.status = SessionStatus.in_progress.value
        s.started_at = datetime.now(timezone.utc)
        db.commit()
    return _serialize_session(s)


@router.post("/{session_id}/exercises/{sx_id}/sets", status_code=status.HTTP_201_CREATED)
def log_set(
    session_id: uuid.UUID,
    sx_id: uuid.UUID,
    req: SetLog,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    s = _owned_session(db, session_id, current_user)
    sx = db.query(models.SessionExercise).filter(
        models.SessionExercise.id == sx_id, models.SessionExercise.session_id == s.id
    ).first()
    if not sx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session exercise not found")

    set_number = req.set_number
    if set_number is None:
        set_number = len(sx.set_entries) + 1

    entry = models.SetEntry(
        session_exercise_id=sx.id,
        set_number=set_number,
        reps=req.reps,
        weight_value=req.weight_value,
        weight_unit=req.weight_unit,
        pin_position=req.pin_position,
        micro_load_kind=req.micro_load_kind or models.MicroLoadKind.none.value,
        added_load_lb=req.added_load_lb,
        micro_load_notches=req.micro_load_notches,
        distance_value=req.distance_value,
        distance_unit=req.distance_unit,
        duration_seconds=req.duration_seconds,
        level=req.level,
        incline=req.incline,
        speed=req.speed,
        avg_hr=req.avg_hr,
        calories=req.calories,
        tut_seconds=req.tut_seconds,
        rpe=req.rpe,
    )
    db.add(entry)
    if s.status == SessionStatus.planned.value:
        s.status = SessionStatus.in_progress.value
        s.started_at = s.started_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(sx)
    return _serialize_session_exercise(sx)


@router.post("/{session_id}/exercises/{sx_id}/swap")
def swap_exercise(
    session_id: uuid.UUID,
    sx_id: uuid.UUID,
    req: SwapRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Swap a prescribed exercise for a same-pattern, club-available alternative — so a
    broken/occupied machine (or a different club) never punches a hole in the pattern-trend."""
    s = _owned_session(db, session_id, current_user)
    sx = db.query(models.SessionExercise).filter(
        models.SessionExercise.id == sx_id, models.SessionExercise.session_id == s.id
    ).first()
    if not sx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session exercise not found")

    target = db.query(models.Exercise).filter(models.Exercise.id == req.to_exercise_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target exercise not found")

    current_ex = sx.exercise
    if current_ex and target.primary_pattern_id != current_ex.primary_pattern_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Swap must stay within the same movement pattern",
        )

    sx.swapped_from_exercise_id = sx.exercise_id
    sx.exercise_id = target.id
    sx.measurement_type = _mt(target.measurement_type)
    sx.was_swapped = True
    sx.swap_reason = req.reason
    db.commit()
    db.refresh(sx)
    return _serialize_session_exercise(sx)


@router.get("/{session_id}/exercises/{sx_id}/swap-options")
def swap_options(
    session_id: uuid.UUID,
    sx_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    s = _owned_session(db, session_id, current_user)
    sx = db.query(models.SessionExercise).filter(
        models.SessionExercise.id == sx_id, models.SessionExercise.session_id == s.id
    ).first()
    if not sx or not sx.exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session exercise not found")

    pattern_id = sx.exercise.primary_pattern_id
    pool = db.query(models.Exercise).filter(
        models.Exercise.primary_pattern_id == pattern_id,
        models.Exercise.is_active.is_(True),
    ).all()
    available_ids = {
        ce.equipment_type_id
        for ce in db.query(models.ClubEquipment)
        .filter(models.ClubEquipment.club_id == s.club_id, models.ClubEquipment.is_available.is_(True))
        .all()
    }
    alts = rotation.same_pattern_alternatives(sx.exercise_id, pool, available_ids)
    return [serialize_exercise(e) for e in alts]


@router.post("/{session_id}/complete")
def complete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Finalize a session: compute and store each performed exercise's per-session metric."""
    s = _owned_session(db, session_id, current_user)

    for sx in s.exercises:
        eq = sx.exercise.equipment_type if sx.exercise else None
        kind, value = progress.compute_session_metric(sx.measurement_type, sx.set_entries, eq)
        sx.session_metric_kind = kind.value
        sx.session_metric_value = value

    s.status = SessionStatus.completed.value
    s.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return _serialize_session(s)
