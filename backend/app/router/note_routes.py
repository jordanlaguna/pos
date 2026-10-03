from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.model_note import SaleNote
from app.schemas.schemas_note import NoteCreate, NoteCreateSuccess, NoteResponse
from app.services import crud_note
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user, get_db, require_admin

router = APIRouter()


@router.post("/add_note", response_model=NoteCreateSuccess)
def add_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Emite una nota por monto sobre un comprobante (RF-77, T-726).

    **Solo el administrador**: mueve plata sin mercadería, que es justo lo que un
    arqueo no puede cruzar contra el inventario. Quién la emite sale del token.
    """
    return crud_note.create_note(db, payload, user_id=admin.user.id_user)


@router.get("/note/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    nota = db.query(SaleNote).filter(SaleNote.id == note_id).first()
    if not nota:
        raise api_error(404, "note_not_found")
    return crud_note.serialize(db, nota)


@router.get("/by_sale/{sale_id}", response_model=list[NoteResponse])
def notes_of_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Las notas por monto de una venta, de la más vieja a la más nueva. Una venta
    de otra compañía no tiene ninguna: el filtro de `tenancy.py` no la ve."""
    notas = (
        db.query(SaleNote)
        .filter(SaleNote.sale_id == sale_id)
        .order_by(SaleNote.created_at, SaleNote.id)
        .all()
    )
    return [crud_note.serialize(db, n) for n in notas]
