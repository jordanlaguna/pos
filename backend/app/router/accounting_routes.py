"""Contabilidad (F11, RF-47).

La activación es de administración y **exige el módulo**: es una escritura, y
RN-50 dice que un módulo apagado impide escribir. La lectura del estado no lo
exige, por la otra mitad de la misma regla: una compañía que bajó de plan tiene
que seguir viendo sus libros, que son su respaldo ante Hacienda.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas_accounting import Activated, ActivationIn, AccountingStatus
from app.services import crud_accounting
from app.utils.auth_dependency import Sesion, get_db, require_admin, require_module

router = APIRouter()


@router.get("", response_model=AccountingStatus)
def estado(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Si esta compañía lleva libros, desde cuándo y con qué plantilla."""
    return crud_accounting.estado(db)


@router.post("/activate", response_model=Activated)
def activar(
    payload: ActivationIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Siembra el catálogo, el mapeo, el primer periodo y la apertura (RF-47)."""
    return crud_accounting.activar(db, payload, user_id=admin.user.id_user)
