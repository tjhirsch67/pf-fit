"""Nutrition & supplements — marketing/affiliate surfaces (illustrative placeholders).

Per the guardrails: partner meals are illustrative, not claimed integrations; affiliate
links need FTC disclosure; no prescriptive calorie targets.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import ai
import auth
import models
from database import get_db

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


@router.get("/partners")
def partners(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    rows = db.query(models.NutritionPartner).filter(models.NutritionPartner.is_active.is_(True)).all()
    return [
        {"id": str(p.id), "name": p.name, "image_url": p.image_url, "affiliate_url": p.affiliate_url}
        for p in rows
    ]


@router.get("/meals")
def meals(
    day_of_week: Optional[int] = Query(default=None, ge=0, le=6),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    q = db.query(models.MealSuggestion).filter(models.MealSuggestion.is_active.is_(True))
    if day_of_week is not None:
        q = q.filter(models.MealSuggestion.day_of_week == day_of_week)
    rows = q.order_by(models.MealSuggestion.day_of_week).all()
    return [
        {
            "id": str(m.id),
            "day_of_week": m.day_of_week,
            "title": m.title,
            "description": m.description,
            "image_url": m.image_url,
            "link_url": m.link_url,
            "tags": m.tags,
            "partner_id": str(m.partner_id) if m.partner_id else None,
        }
        for m in rows
    ]


@router.get("/supplements")
def supplements(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    rows = db.query(models.Supplement).filter(models.Supplement.is_active.is_(True)).all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "category": s.category,
            "description": s.description,
            "image_url": s.image_url,
            "link_url": s.link_url,
        }
        for s in rows
    ]


RECIPES_SCHEMA = {
    "type": "object",
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["name", "description", "url"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["recipes"],
    "additionalProperties": False,
}


@router.get("/recipes")
def recipe_ideas(current_user: models.User = Depends(auth.get_current_user)):
    """A few illustrative recipe ideas (AI, Haiku). Links are generic search URLs — not a
    claimed integration. Returns an empty list if AI is unconfigured."""
    if not ai.is_configured():
        return {"recipes": []}
    goal = current_user.goal or "general fitness"
    user = (
        f"Suggest 6 simple, varied meal ideas supporting a '{goal}' goal. For each, give a "
        f"name, a one-sentence description, and a Google search URL "
        f"(https://www.google.com/search?q=...+recipe, spaces as plus signs). No calorie targets."
    )
    data = ai.generate_json(
        system="You are a friendly nutrition idea generator. Keep it non-prescriptive.",
        user=user, schema=RECIPES_SCHEMA, model=ai.HAIKU, thinking=False, max_tokens=1500,
    )
    return data
