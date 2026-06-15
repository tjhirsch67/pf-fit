"""Authentication endpoints — register, login, current user."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from serializers import serialize_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: Optional[str] = None
    home_club_id: Optional[uuid.UUID] = None
    locale: str = "en"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _token_response(user: models.User) -> dict:
    token = auth.create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer", "user": serialize_user(user)}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = auth.normalize_email(req.email)
    existing = (
        db.query(models.User)
        .filter(models.User.email.ilike(email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if req.home_club_id is not None:
        club = db.query(models.Club).filter(models.Club.id == req.home_club_id).first()
        if not club:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown home club")

    user = models.User(
        email=email,
        password_hash=auth.hash_password(req.password),
        display_name=req.display_name,
        home_club_id=req.home_club_id,
        locale=req.locale or "en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = auth.normalize_email(req.email)
    user = db.query(models.User).filter(models.User.email.ilike(email)).first()
    if not user or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.status != models.RecordStatus.active.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    return _token_response(user)


@router.get("/me")
def me(current_user: models.User = Depends(auth.get_current_user)):
    return serialize_user(current_user)
