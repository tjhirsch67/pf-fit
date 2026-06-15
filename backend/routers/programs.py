"""Programs & rotation — generate a rotating multi-week plan, read the current week, swap.

The week generator is the rotation engine (rotation.py) applied over slot specs derived from
the movement patterns: each pattern contributes a fixed *anchor* slot (its compound, when one
exists) and a rotating *variety* slot. Anchors hold week to week so per-exercise progression
is continuous; variety slots rotate (LRU) so the member sees new machines — and the
pattern-trend (progress.py) stays continuous across the rotation.
"""

import uuid
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auth
import models
import rotation
from database import get_db
from enums import MeasurementType, RecordStatus
from serializers import serialize_exercise

router = APIRouter(prefix="/programs", tags=["programs"])

DEFAULT_WEEKS = 8


class GenerateRequest(BaseModel):
    club_id: Optional[uuid.UUID] = None
    weeks: int = Field(default=DEFAULT_WEEKS, ge=1, le=26)
    name: Optional[str] = None


def _prescribe(measurement_type: str):
    """Default prescription per measurement type → (sets, reps, target_json)."""
    if measurement_type == MeasurementType.cardio.value:
        return 1, None, {"duration_min": 20}
    if measurement_type == MeasurementType.circuit.value:
        return 1, None, {"work_sec": 60, "rest_sec": 30}
    if measurement_type == MeasurementType.bodyweight.value:
        return 3, 12, None
    return 3, 10, None  # selectorized / plate_loaded / smith / functional


def _resolve_club(db: Session, user: models.User, club_id: Optional[uuid.UUID]) -> models.Club:
    cid = club_id or user.home_club_id
    if cid is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No club specified and you have no home club set",
        )
    club = db.query(models.Club).filter(models.Club.id == cid).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    return club


def _build_specs_and_pools(db: Session, club_id: uuid.UUID):
    """Slot specs (anchor + variety per pattern) + the per-pattern exercise pools + the
    club's available equipment ids."""
    available_ids = {
        ce.equipment_type_id
        for ce in db.query(models.ClubEquipment)
        .filter(models.ClubEquipment.club_id == club_id, models.ClubEquipment.is_available.is_(True))
        .all()
    }
    patterns = db.query(models.MovementPattern).order_by(models.MovementPattern.display_order).all()

    specs: List[dict] = []
    pools: Dict = {}
    idx = 0
    for p in patterns:
        pool = (
            db.query(models.Exercise)
            .filter(
                models.Exercise.primary_pattern_id == p.id,
                models.Exercise.is_active.is_(True),
            )
            .all()
        )
        pools[p.id] = pool
        anchors = [e for e in pool if e.is_anchor and rotation.exercise_available(e, available_ids)]
        variety = [e for e in pool if not e.is_anchor and rotation.exercise_available(e, available_ids)]
        if anchors:
            specs.append({"slot_index": idx, "pattern_id": p.id, "is_anchor": True,
                          "anchor_exercise_id": anchors[0].id})
            idx += 1
        if variety:
            specs.append({"slot_index": idx, "pattern_id": p.id, "is_anchor": False})
            idx += 1
    return specs, pools, available_ids


def create_program_for_user(
    db: Session,
    user: models.User,
    club_id: Optional[uuid.UUID] = None,
    weeks: int = DEFAULT_WEEKS,
    name: Optional[str] = None,
) -> models.Program:
    """Generate and persist a rotating multi-week program. Shared by the /generate endpoint
    and the intake flow. Commits and returns the new Program."""
    club = _resolve_club(db, user, club_id)
    specs, pools, available_ids = _build_specs_and_pools(db, club.id)
    if not specs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No exercises available at this club — seed the exercise library first",
        )

    # Archive any existing active program (never hard-delete).
    db.query(models.Program).filter(
        models.Program.user_id == user.id,
        models.Program.status == RecordStatus.active.value,
    ).update({"status": RecordStatus.archived.value, "deleted_at": models.func.now()})

    program = models.Program(
        user_id=user.id,
        name=name or "PF Coach Program",
        club_id=club.id,
        autonomy_mode_at_creation=user.autonomy_mode,
        start_date=date.today(),
    )
    db.add(program)
    db.flush()

    ex_by_id = {e.id: e for pool in pools.values() for e in pool}
    history_by_pattern: Dict = {}

    for wk in range(1, weeks + 1):
        resolved = rotation.build_program_week(specs, pools, available_ids, history_by_pattern)
        week = models.ProgramWeek(program_id=program.id, week_number=wk, is_current=(wk == 1))
        db.add(week)
        db.flush()
        for r in resolved:
            ex_id = r["exercise_id"]
            if not ex_id:
                continue
            ex = ex_by_id.get(ex_id)
            mt = ex.measurement_type.value if hasattr(ex.measurement_type, "value") else ex.measurement_type
            sets, reps, target = _prescribe(mt)
            db.add(models.ProgramSlot(
                program_week_id=week.id,
                slot_index=r["slot_index"],
                pattern_id=r["pattern_id"],
                exercise_id=ex_id,
                is_anchor=r["is_anchor"],
                prescribed_sets=sets,
                prescribed_reps=reps,
                prescribed_target=target,
            ))
            # Variety choices feed the rotation history so next week prefers something else.
            if not r["is_anchor"]:
                history_by_pattern.setdefault(r["pattern_id"], []).insert(0, ex_id)

    db.commit()
    db.refresh(program)
    return program


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate_program(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    program = create_program_for_user(db, current_user, req.club_id, req.weeks, req.name)
    return _serialize_program(db, program, current_week_only=True)


def _serialize_slot(db: Session, slot: models.ProgramSlot) -> dict:
    ex = slot.exercise
    return {
        "id": str(slot.id),
        "slot_index": slot.slot_index,
        "pattern_id": str(slot.pattern_id),
        "is_anchor": slot.is_anchor,
        "prescribed_sets": slot.prescribed_sets,
        "prescribed_reps": slot.prescribed_reps,
        "prescribed_target": slot.prescribed_target,
        "exercise": serialize_exercise(ex) if ex else None,
    }


def _serialize_week(db: Session, week: models.ProgramWeek) -> dict:
    return {
        "id": str(week.id),
        "week_number": week.week_number,
        "is_current": week.is_current,
        "slots": [_serialize_slot(db, s) for s in week.slots],
    }


def _serialize_program(db: Session, program: models.Program, current_week_only: bool = False) -> dict:
    weeks = program.weeks
    if current_week_only:
        weeks = [w for w in weeks if w.is_current] or weeks[:1]
    return {
        "id": str(program.id),
        "name": program.name,
        "club_id": str(program.club_id) if program.club_id else None,
        "status": program.status.value if hasattr(program.status, "value") else program.status,
        "start_date": program.start_date.isoformat() if program.start_date else None,
        "week_count": len(program.weeks),
        "weeks": [_serialize_week(db, w) for w in weeks],
    }


def _active_program(db: Session, user: models.User) -> models.Program:
    program = (
        db.query(models.Program)
        .filter(models.Program.user_id == user.id, models.Program.status == RecordStatus.active.value)
        .order_by(models.Program.created_at.desc())
        .first()
    )
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active program")
    return program


@router.get("/active")
def get_active(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    program = _active_program(db, current_user)
    return _serialize_program(db, program, current_week_only=True)


@router.get("/active/full")
def get_active_full(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    program = _active_program(db, current_user)
    return _serialize_program(db, program, current_week_only=False)


@router.post("/advance-week")
def advance_week(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Move the 'current' marker to the next week (wraps to week 1 after the last)."""
    program = _active_program(db, current_user)
    weeks = sorted(program.weeks, key=lambda w: w.week_number)
    if not weeks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Program has no weeks")
    current_idx = next((i for i, w in enumerate(weeks) if w.is_current), 0)
    next_idx = (current_idx + 1) % len(weeks)
    for i, w in enumerate(weeks):
        w.is_current = (i == next_idx)
    db.commit()
    return _serialize_week(db, weeks[next_idx])
