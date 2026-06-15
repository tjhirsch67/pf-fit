"""Admin — user listing and audited reverse transactions (house principle: never hard-delete).

Reversible business actions are performed by an admin and recorded in ``admin_transactions``
so they can be replayed/audited (Schema.md §12).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from enums import RecordStatus, SessionStatus
from serializers import serialize_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _log(db: Session, admin: models.User, action: str, table: str, target_id, before, after):
    db.add(models.AdminTransaction(
        admin_id=admin.id, action=action, target_table=table,
        target_id=target_id, before_state=before, after_state=after,
    ))


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_admin_user),
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return [serialize_user(u) for u in users]


@router.post("/sessions/{session_id}/reverse")
def reverse_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_admin_user),
):
    """Undo a logged session (e.g. mistaken completion): mark it skipped, audited."""
    s = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    before = {"status": s.status.value if hasattr(s.status, "value") else s.status}
    s.status = SessionStatus.skipped.value
    _log(db, admin, "reverse_session", "sessions", s.id, before, {"status": SessionStatus.skipped.value})
    db.commit()
    return {"id": str(s.id), "status": SessionStatus.skipped.value}


@router.post("/programs/{program_id}/restore")
def restore_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_admin_user),
):
    """Un-archive a program (reactivate), archiving any other active program for that user."""
    program = db.query(models.Program).filter(models.Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    before = {"status": program.status.value if hasattr(program.status, "value") else program.status}
    db.query(models.Program).filter(
        models.Program.user_id == program.user_id,
        models.Program.status == RecordStatus.active.value,
        models.Program.id != program.id,
    ).update({"status": RecordStatus.archived.value})
    program.status = RecordStatus.active.value
    program.deleted_at = None
    _log(db, admin, "restore_program", "programs", program.id, before, {"status": RecordStatus.active.value})
    db.commit()
    return {"id": str(program.id), "status": RecordStatus.active.value}
