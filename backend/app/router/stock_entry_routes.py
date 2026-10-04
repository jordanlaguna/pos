from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_stock_entry import StockEntry
from app.models.model_user import User
from app.schemas.schemas_stock_entry import (
    EntryCancel,
    StockEntryCreate,
    StockEntryResponse,
    StockEntrySuccess,
)
from app.services import crud_stock_entry
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, exigir_modulo, require_admin, require_module

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Recibir mercadería cambia el inventario y su valor: es cosa de administración.
@router.post("/entry", response_model=StockEntrySuccess)
def create_entry(
    payload: StockEntryCreate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Recibe mercadería. Con proveedor es una compra (RN-52).

    Los módulos dependen de lo que trae, y por eso se comprueban acá y no como
    dependencia, que decide antes de que exista el cuerpo (QA-01):

    - recibir mercadería es del **inventario**;
    - nombrar a quién se le compró es de **proveedores**, que el paquete
      Comercio trae sin compras;
    - comprar **a crédito** deja una cuenta por pagar, y eso es de **compras**.

    Pedir compras para cualquier entrada con proveedor —como antes de QA-01—
    le cerraría a Comercio el recibir de su proveedor al contado, y no pedir
    nada la dejaría registrando deudas sin el módulo (RN-49).
    """
    exigir_modulo(db, admin, "inventory")
    if payload.supplier_id is not None:
        exigir_modulo(db, admin, "suppliers")
        if payload.payment_terms == "credit":
            exigir_modulo(db, admin, "purchases")
    return crud_stock_entry.create_entry(db, payload)


@router.get("/entries", response_model=list[StockEntryResponse])
def list_entries(
    limit: int = 200,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    entries = (
        db.query(StockEntry).order_by(StockEntry.created_at.desc()).limit(limit).all()
    )
    return [crud_stock_entry.serialize(db, e) for e in entries]


@router.get("/entry/{entry_id}", response_model=StockEntryResponse)
def get_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    entry = db.query(StockEntry).filter(StockEntry.id == entry_id).first()
    if not entry:
        raise api_error(404, "entry_not_found")
    return crud_stock_entry.serialize(db, entry)


@router.post("/entry/{entry_id}/cancel")
def cancel_entry(
    entry_id: int,
    payload: EntryCancel | None = None,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(require_module("inventory")),
):
    """Anula la entrada y devuelve el stock al valor previo.

    Anula también compras (RF-46): es el mismo acto sobre la misma fila, y por
    eso no hay un `/purchases/{id}/void` aparte. Lo que cambia con proveedor es
    que el motivo pasa a ser obligatorio y que una con abonos no se anula
    (RN-57).

    El cuerpo es opcional para no romper a quien ya llamaba sin él —la pantalla
    de entradas—; la que sí lo exige es la compra, y lo dice con su código.
    """
    return crud_stock_entry.cancel_entry(
        db,
        entry_id,
        user_id=admin.user.id_user,
        company_id=admin.company_id,
        reason=payload.reason if payload else None,
    )
