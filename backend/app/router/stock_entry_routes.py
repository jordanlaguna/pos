from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_stock_entry import StockEntry
from app.models.model_user import User
from app.schemas.schemas_stock_entry import (
    StockEntryCreate,
    StockEntryResponse,
    StockEntrySuccess,
)
from app.services import crud_stock_entry
from app.utils.auth_dependency import require_admin

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
    admin: User = Depends(require_admin),
):
    return crud_stock_entry.create_entry(db, payload)


@router.get("/entries", response_model=list[StockEntryResponse])
def list_entries(
    limit: int = 200,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entries = (
        db.query(StockEntry).order_by(StockEntry.created_at.desc()).limit(limit).all()
    )
    return [crud_stock_entry.serialize(db, e) for e in entries]


@router.get("/entry/{entry_id}", response_model=StockEntryResponse)
def get_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entry = db.query(StockEntry).filter(StockEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    return crud_stock_entry.serialize(db, entry)


@router.post("/entry/{entry_id}/cancel")
def cancel_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Anula la entrada y devuelve el stock al valor previo."""
    return crud_stock_entry.cancel_entry(db, entry_id)
