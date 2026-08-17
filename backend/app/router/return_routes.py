from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_return import Return
from app.models.model_user import User
from app.schemas.schemas_return import ReturnCreate, ReturnCreateSuccess, ReturnResponse
from app.services import crud_return
from app.utils.auth_dependency import Sesion, get_current_user

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/returns_list", response_model=list[ReturnResponse])
def list_returns(
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    records = db.query(Return).order_by(Return.created_at.desc()).limit(500).all()
    return [crud_return.serialize(db, r) for r in records]


@router.get("/return/{return_id}", response_model=ReturnResponse)
def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    record = db.query(Return).filter(Return.id == return_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    return crud_return.serialize(db, record)


@router.post("/add_return", response_model=ReturnCreateSuccess)
def add_return(
    payload: ReturnCreate,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Registra la devolución y devuelve las unidades al inventario."""
    return crud_return.create_return(db, payload)
