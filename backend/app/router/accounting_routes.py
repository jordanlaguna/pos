"""Contabilidad (F11, RF-47).

La activación es de administración y **exige el módulo**: es una escritura, y
RN-50 dice que un módulo apagado impide escribir. La lectura del estado no lo
exige, por la otra mitad de la misma regla: una compañía que bajó de plan tiene
que seguir viendo sus libros, que son su respaldo ante Hacienda.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas_accounting import (
    Account,
    AccountIn,
    AccountingStatus,
    AccountPatch,
    Activated,
    ActivationIn,
    Deleted,
    Mappings,
    MappingsIn,
    Reclassified,
    ReclassifyIn,
)
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


# ---------------------------------------------------------------- el catálogo


@router.get("/accounts", response_model=list[Account])
def cuentas(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """El catálogo, ordenado por código (RF-48)."""
    return crud_accounting.cuentas(db)


@router.post("/accounts", response_model=Account)
def crear_cuenta(
    payload: AccountIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    return crud_accounting.crear_cuenta(db, payload)


@router.put("/accounts/{account_id}", response_model=Account)
def actualizar_cuenta(
    account_id: int,
    payload: AccountPatch,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Renombrar, y activar o desactivar. Las de sistema no se desactivan (RN-64)."""
    return crud_accounting.actualizar_cuenta(db, account_id, payload)


@router.delete("/accounts/{account_id}", response_model=Deleted)
def borrar_cuenta(
    account_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Solo si nunca tuvo movimientos y no es de sistema (RN-64)."""
    return crud_accounting.borrar_cuenta(db, account_id)


# ------------------------------------------------------------------- el mapeo


@router.get("/mappings", response_model=Mappings)
def mapeo(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Qué cuenta usa cada papel, y qué falta (RF-49)."""
    return crud_accounting.mapeo(db)


@router.put("/mappings", response_model=Mappings)
def guardar_mapeo(
    payload: MappingsIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Afecta lo que venga, nunca lo que ya está en el libro (RN-62)."""
    return crud_accounting.guardar_mapeo(db, payload)


@router.post("/entries/{entry_id}/reclassify", response_model=Reclassified)
def reclasificar(
    entry_id: int,
    payload: ReclassifyIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Mueve a su cuenta lo que cayó en «por clasificar», con un ajuste (RF-49)."""
    return crud_accounting.reclasificar(db, entry_id, payload, user_id=admin.user.id_user)
