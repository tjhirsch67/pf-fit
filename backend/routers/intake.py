"""Intake — the digitized PE@PF interview that places the member on the autonomy gradient.

Two surfaces:
  - ``/intake/chat`` — a warm, conversational trainer turn (free-form, Sonnet).
  - ``/intake/submit`` — structured placement: the model reads the answers and returns a
    recommended autonomy mode + a plain-language rationale (the "here's why" screen), which
    we persist, apply to the profile, and (optionally) use to generate the first program.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import ai
import auth
import models
from database import get_db
from routers.programs import _serialize_program, create_program_for_user

router = APIRouter(prefix="/intake", tags=["intake"])

INTERVIEW_SYSTEM = (
    "You are PF Coach — a warm, encouraging, plainspoken personal trainer for a brand-new "
    "Planet Fitness member who may feel intimidated. Speak TO the beginner, never down to "
    "them. Sentence case, friendly, short sentences, real verbs. Never gate or shame; the "
    "gym is a judgement-free space. Ask ONE thing at a time: their goal, how much experience "
    "they have, how many days a week they can train, any injuries or concerns, and how "
    "confident they feel walking onto the floor. Keep replies brief — this is read on a "
    "phone. When you have enough to place them, tell them they're all set and to submit."
)

PLACEMENT_SYSTEM = (
    "You are PF Coach's intake reasoner. Given a new member's intake answers, place them on "
    "the autonomy gradient and explain why in a warm, plain-language rationale written "
    "directly to the member.\n\n"
    "Modes:\n"
    "- guided: zero decisions; anchored on the 30-Minute Express Circuit. Use for nervous, "
    "inexperienced beginners.\n"
    "- coached: the app drives programming and rotation; the member can swap and rate "
    "difficulty. Use for those with some experience or confidence.\n"
    "- self_directed: the member customizes their own splits; the app advises. Use only for "
    "experienced, confident members.\n\n"
    "When in doubt, place lower (more guided) — it's easy to advance later. cardio_pct and "
    "strength_pct should sum to 100."
)

PLACEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_mode": {"type": "string", "enum": ["guided", "coached", "self_directed"]},
        "rationale": {"type": "string"},
        "goal": {"type": "string"},
        "experience_level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
        "days_per_week": {"type": "integer"},
        "cardio_pct": {"type": "integer"},
        "strength_pct": {"type": "integer"},
    },
    "required": [
        "recommended_mode", "rationale", "goal",
        "experience_level", "days_per_week", "cardio_pct", "strength_pct",
    ],
    "additionalProperties": False,
}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class SubmitRequest(BaseModel):
    answers: dict
    transcript: Optional[str] = None
    generate_program: bool = True
    club_id: Optional[str] = None


def _require_ai():
    if not ai.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not configured (ANTHROPIC_API_KEY missing)",
        )


@router.post("/chat")
def intake_chat(
    req: ChatRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_ai()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    if not messages:
        name = current_user.display_name or "there"
        messages = [{"role": "user", "content": f"Hi, I'm {name} and I'm just getting started."}]
    reply = ai.chat(system=INTERVIEW_SYSTEM, messages=messages)
    return {"reply": reply}


@router.post("/submit")
def intake_submit(
    req: SubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_ai()

    user_prompt = "Intake answers (JSON):\n" + json.dumps(req.answers, indent=2)
    if req.transcript:
        user_prompt += f"\n\nInterview transcript:\n{req.transcript[:4000]}"

    placement = ai.generate_json(system=PLACEMENT_SYSTEM, user=user_prompt, schema=PLACEMENT_SCHEMA)

    # Persist the versioned intake response.
    db.add(models.IntakeResponse(
        user_id=current_user.id,
        answers=req.answers,
        recommended_mode=placement["recommended_mode"],
        rationale=placement.get("rationale"),
    ))

    # Apply placement to the profile.
    old_mode = current_user.autonomy_mode
    new_mode = placement["recommended_mode"]
    current_user.autonomy_mode = new_mode
    current_user.goal = placement.get("goal") or current_user.goal
    if placement.get("experience_level"):
        current_user.experience_level = placement["experience_level"]
    if placement.get("days_per_week"):
        current_user.days_per_week = placement["days_per_week"]
    if placement.get("cardio_pct") is not None:
        current_user.cardio_pct = max(0, min(100, placement["cardio_pct"]))
    if placement.get("strength_pct") is not None:
        current_user.strength_pct = max(0, min(100, placement["strength_pct"]))

    if new_mode != old_mode:
        db.add(models.AutonomyEvent(
            user_id=current_user.id, from_mode=old_mode, to_mode=new_mode, trigger="intake"
        ))

    db.commit()
    db.refresh(current_user)

    result = {"placement": placement}
    if req.generate_program:
        try:
            club_id = req.club_id or (str(current_user.home_club_id) if current_user.home_club_id else None)
            import uuid as _uuid
            program = create_program_for_user(
                db, current_user, _uuid.UUID(club_id) if club_id else None
            )
            result["program"] = _serialize_program(db, program, current_week_only=True)
        except HTTPException as e:
            result["program_error"] = e.detail
    return result
