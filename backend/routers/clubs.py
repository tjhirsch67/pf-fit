"""Clubs & equipment — what's available where (drives rotation + swap)."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from serializers import serialize_club, serialize_equipment_type, serialize_exercise

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("")
def list_clubs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    clubs = db.query(models.Club).order_by(models.Club.name).all()
    return [serialize_club(c) for c in clubs]


def _require_club(db: Session, club_id: uuid.UUID) -> models.Club:
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    return club


@router.get("/{club_id}/equipment")
def club_equipment(
    club_id: uuid.UUID,
    available_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_club(db, club_id)
    q = (
        db.query(models.EquipmentType, models.ClubEquipment)
        .join(models.ClubEquipment, models.ClubEquipment.equipment_type_id == models.EquipmentType.id)
        .filter(models.ClubEquipment.club_id == club_id)
    )
    if available_only:
        q = q.filter(models.ClubEquipment.is_available.is_(True))

    out = []
    for eq, ce in q.all():
        row = serialize_equipment_type(eq)
        row["quantity"] = ce.quantity
        row["is_available"] = ce.is_available
        out.append(row)
    return out


@router.get("/{club_id}/exercises")
def club_exercises(
    club_id: uuid.UUID,
    pattern_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Exercises doable at this club: equipment is available, or the exercise needs none
    (bodyweight). Optionally scoped to one movement pattern."""
    _require_club(db, club_id)

    available_ids = {
        ce.equipment_type_id
        for ce in db.query(models.ClubEquipment)
        .filter(
            models.ClubEquipment.club_id == club_id,
            models.ClubEquipment.is_available.is_(True),
        )
        .all()
    }

    q = db.query(models.Exercise).filter(models.Exercise.is_active.is_(True))
    if pattern_id is not None:
        q = q.filter(models.Exercise.primary_pattern_id == pattern_id)

    out = []
    for ex in q.order_by(models.Exercise.name).all():
        if ex.equipment_type_id is None or ex.equipment_type_id in available_ids:
            out.append(serialize_exercise(ex))
    return out
