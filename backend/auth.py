"""Authentication & authorization — JWT (bearer) + bcrypt (CLAUDE.md §7).

Diverges from MARLON: UUID subjects (not int) and a ``role`` enum (member/admin) rather than
an ``is_admin`` bool. The token ``sub`` is the user's UUID as a string.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models
from config import settings
from database import get_db
from enums import RecordStatus, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=True)


# ─── Input normalization (shared) ───────────────────────────────────────────────

def normalize_email(email: str) -> str:
    """Emails are stored lowercased; the unique index is on lower(email)."""
    return (email or "").strip().lower()


# ─── Passwords ──────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ─── Tokens ───────────────────────────────────────────────────────────────────

def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# ─── Current-user dependencies ──────────────────────────────────────────────────

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[settings.algorithm]
        )
        sub = payload.get("sub")
        if not sub:
            raise _credentials_exception
        user_id = uuid.UUID(str(sub))
    except (JWTError, ValueError):
        raise _credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise _credentials_exception
    if user.status != RecordStatus.active.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    return user


def get_admin_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != UserRole.admin.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
