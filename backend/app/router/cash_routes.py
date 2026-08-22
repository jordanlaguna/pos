from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_cash import CashSession
from app.models.model_user import User
from app.schemas.schemas_cash import (
    CashClose,
    CashOpen,
    CashSessionReport,
    MovementCreate,
    MovementResponse,
)
from app.services import crud_cash
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/current", response_model=CashSessionReport | None)
def current_session(
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Turno abierto del usuario. `null` si la caja está cerrada."""
    target = user_id or current.id_user
    # Un cajero no puede espiar la caja de otro; el admin sí necesita hacerlo.
    if target != current.id_user and current.rol != "admin":
        raise api_error(403, "cash_read_not_yours")

    session = crud_cash.get_open_session(db, target)
    return crud_cash.build_report(db, session) if session else None


@router.post("/open", response_model=CashSessionReport)
def open_cash(
    payload: CashOpen,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    if payload.user_id != current.id_user and current.rol != "admin":
        raise api_error(403, "cash_open_not_yours")
    return crud_cash.open_session(db, payload.user_id, payload.opening_amount, payload.notes)


@router.post("/movement", response_model=MovementResponse)
def add_movement(
    payload: MovementCreate,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    if payload.user_id != current.id_user and current.rol != "admin":
        raise api_error(403, "cash_movement_not_yours")
    return crud_cash.add_movement(
        db, payload.user_id, payload.type, payload.amount, payload.reason
    )


@router.post("/close", response_model=CashSessionReport)
def close_cash(
    payload: CashClose,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    if payload.user_id != current.id_user and current.rol != "admin":
        raise api_error(403, "cash_close_not_yours")
    return crud_cash.close_session(db, payload.user_id, payload.closing_amount, payload.notes)


@router.get("/sessions", response_model=list[CashSessionReport])
def list_sessions(
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Historial de turnos. El cajero solo ve los suyos."""
    query = db.query(CashSession)
    if current.rol != "admin":
        query = query.filter(CashSession.user_id == current.id_user)
    elif user_id:
        query = query.filter(CashSession.user_id == user_id)

    sessions = query.order_by(CashSession.opened_at.desc()).limit(100).all()
    return [crud_cash.build_report(db, s) for s in sessions]


@router.get("/session/{session_id}", response_model=CashSessionReport)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    session = db.query(CashSession).filter(CashSession.id == session_id).first()
    if not session:
        raise api_error(404, "cash_session_not_found")
    if session.user_id != current.id_user and current.rol != "admin":
        raise api_error(403, "cash_session_not_yours")
    return crud_cash.build_report(db, session)
