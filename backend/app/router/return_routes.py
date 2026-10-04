from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_return import Return
from app.models.model_user import User
from app.schemas.schemas_return import ReturnCreate, ReturnCreateSuccess, ReturnResponse
from app.services import crud_return
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, exigir_modulo, get_current_user

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
        raise api_error(404, "return_not_found")
    return crud_return.serialize(db, record)


@router.post("/add_return", response_model=ReturnCreateSuccess)
def add_return(
    payload: ReturnCreate,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Registra la devolución y devuelve las unidades al inventario.

    El módulo depende de lo que se pide (QA-01): anular un comprobante entero es
    del módulo de facturas, y devolver unidades, del de devoluciones. Un
    restaurante no compra devoluciones, pero tiene que poder anular una factura
    mal hecha. Por eso se decide acá y no en una dependencia, que no ve el
    cuerpo.
    """
    exigir_modulo(db, current, "invoices" if payload.annul else "returns")
    return crud_return.create_return(db, payload)
