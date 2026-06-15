"""Current-user profile, autonomy-gradient transitions, and consistency."""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from enums import AutonomyMode, DifficultyLevel, MembershipTier
from serializers import serialize_user

router = APIRouter(prefix="/me", tags=["me"])


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    locale: Optional[str] = None
    goal: Optional[str] = None
    experience_level: Optional[str] = None
    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    cardio_pct: Optional[int] = Field(default=None, ge=0, le=100)
    strength_pct: Optional[int] = Field(default=None, ge=0, le=100)
    home_club_id: Optional[uuid.UUID] = None
    membership_tier: Optional[str] = None


class AutonomyChange(BaseModel):
    mode: str
    trigger: str = "self_declared"  # 'self_declared' | 'nudge_consistency' | 'admin'


def _valid_enum(value: str, enum_cls, field: str):
    valid = {e.value for e in enum_cls}
    if value not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: must be one of {sorted(valid)}",
        )


@router.get("")
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return serialize_user(current_user)


@router.patch("")
def update_me(
    req: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if req.experience_level is not None:
        _valid_enum(req.experience_level, DifficultyLevel, "experience_level")
        current_user.experience_level = req.experience_level
    if req.membership_tier is not None:
        _valid_enum(req.membership_tier, MembershipTier, "membership_tier")
        current_user.membership_tier = req.membership_tier
    if req.home_club_id is not None:
        club = db.query(models.Club).filter(models.Club.id == req.home_club_id).first()
        if not club:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown home club")
        current_user.home_club_id = req.home_club_id

    for field in ("display_name", "locale", "goal", "days_per_week", "cardio_pct", "strength_pct"):
        value = getattr(req, field)
        if value is not None:
            setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return serialize_user(current_user)


@router.post("/autonomy")
def change_autonomy(
    req: AutonomyChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Move along the autonomy gradient. By invitation, never gated — any member can
    self-promote (or stay guided) at any time (CLAUDE.md §4)."""
    _valid_enum(req.mode, AutonomyMode, "mode")
    from_mode = current_user.autonomy_mode

    if req.mode != from_mode:
        current_user.autonomy_mode = req.mode
        db.add(
            models.AutonomyEvent(
                user_id=current_user.id,
                from_mode=from_mode,
                to_mode=req.mode,
                trigger=req.trigger or "self_declared",
            )
        )
        db.commit()
        db.refresh(current_user)
    return serialize_user(current_user)


@router.get("/consistency")
def consistency(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Streak + completed-session counts. Consistency (not raw count) is what triggers the
    nudge to advance along the gradient (CLAUDE.md §4)."""
    completed = (
        db.query(models.Session)
        .filter(
            models.Session.user_id == current_user.id,
            models.Session.status == models.SessionStatus.completed.value,
        )
        .all()
    )
    total = len(completed)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = sum(1 for s in completed if s.completed_at and s.completed_at >= month_start)

    # Current streak: consecutive calendar days (ending today or yesterday) with a session.
    done_days = {s.completed_at.date() for s in completed if s.completed_at}
    streak = 0
    cursor = date.today()
    if cursor not in done_days and (cursor - timedelta(days=1)) in done_days:
        cursor = cursor - timedelta(days=1)  # today not done yet, but yesterday was
    while cursor in done_days:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "completed_total": total,
        "completed_this_month": this_month,
        "current_streak_days": streak,
    }
