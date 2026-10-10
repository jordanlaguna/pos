"""El kárdex y las existencias por sucursal (F15, RF-87).

Lecturas, y por eso libres para cualquier sesión de la compañía (RN-50): el
cajero que ve «hay 7» tiene que poder ver por qué. Las escrituras —salidas,
traslados, tomas— llegan con sus tareas y piden el módulo.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.schemas.schemas_inventory import (
    ExitCancel,
    ExitCancelSuccess,
    StockExitCreate,
    StockExitOut,
    StockExitSuccess,
    StockLevelOut,
    StockMovementOut,
    StockReasonCreate,
    StockReasonOut,
    StockReasonUpdate,
)
from app.services import crud_inventory
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user, require_admin, require_module

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# `from` es palabra reservada en Python: el alias lo expone como `?from=`.
FromParam = Query(None, alias="from", description="Desde esta fecha y hora")
ToParam = Query(None, alias="to", description="Hasta esta fecha y hora")


@router.get("/kardex", response_model=list[StockMovementOut])
def get_kardex(
    product_id: int | None = None,
    branch_id: int | None = None,
    since: datetime | None = FromParam,
    until: datetime | None = ToParam,
    source_type: str | None = None,
    source_id: int | None = None,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Los movimientos de un producto, o los que dejó un documento (RF-87).

    Se pregunta por producto —con sucursal y periodo opcionales— o por
    documento (`source_type` y `source_id`, los dos). Sin ninguna de las dos
    cosas no hay nada que listar, y se dice: una lista vacía parecería «no se
    movió nunca».
    """
    if product_id is None and (source_type is None or source_id is None):
        raise api_error(400, "kardex_filter_required")
    return crud_inventory.kardex(
        db,
        product_id=product_id,
        branch_id=branch_id,
        since=since,
        until=until,
        source_type=source_type,
        source_id=source_id,
    )


@router.get("/levels", response_model=list[StockLevelOut])
def get_levels(
    product_id: int | None = None,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """La existencia por sucursal de un producto, o la de una sucursal entera."""
    if product_id is None and branch_id is None:
        raise api_error(400, "kardex_filter_required")
    return crud_inventory.niveles(db, product_id=product_id, branch_id=branch_id)


# ------------------------------------------------------ los motivos (RN-99)
#
# Son del administrador, como las categorías: el cajero no da salidas.


@router.get("/reasons", response_model=list[StockReasonOut])
def list_reasons(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_inventory.reasons(db)


@router.post("/reasons", response_model=StockReasonOut)
def create_reason(
    payload: StockReasonCreate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(require_module("inventory")),
):
    return crud_inventory.create_reason(db, payload)


@router.put("/reasons/{reason_id}", response_model=StockReasonOut)
def update_reason(
    reason_id: int,
    payload: StockReasonUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(require_module("inventory")),
):
    """Se renombra y se apaga; no se borra. El de la toma no se apaga (RN-100)."""
    return crud_inventory.update_reason(db, reason_id, payload)


# ------------------------------------------------------ las salidas (RN-99)


@router.get("/exits", response_model=list[StockExitOut])
def list_exits(
    limit: int = 200,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_inventory.exits(db, limit)


@router.post("/exits", response_model=StockExitSuccess)
def create_exit(
    payload: StockExitCreate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(require_module("inventory")),
):
    """Mercadería que deja el inventario sin venderse, con motivo (RN-99)."""
    return crud_inventory.create_exit(db, payload, user_id=admin.user.id_user)


@router.post("/exits/{exit_id}/cancel", response_model=ExitCancelSuccess)
def cancel_exit(
    exit_id: int,
    payload: ExitCancel,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(require_module("inventory")),
):
    """Una salida no se edita: se anula con motivo y bitácora (RN-99)."""
    return crud_inventory.cancel_exit(
        db,
        exit_id,
        user_id=admin.user.id_user,
        company_id=admin.company_id,
        reason=payload.reason,
    )
