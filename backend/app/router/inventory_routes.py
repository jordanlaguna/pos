"""El kárdex y las existencias por sucursal (F15, RF-87).

Lecturas, y por eso libres para cualquier sesión de la compañía (RN-50): el
cajero que ve «hay 7» tiene que poder ver por qué. Las escrituras —salidas,
traslados, tomas— llegan con sus tareas y piden el módulo.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.schemas.schemas_inventory import StockLevelOut, StockMovementOut
from app.services import crud_inventory
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user

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
