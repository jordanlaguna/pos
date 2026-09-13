"""Cuentas por pagar (F10, RF-44).

Aparte de `/purchases` a propósito: lo que se debe no es una compra sino el
estado de un conjunto de ellas, y F11 va a leerlo para el asiento sin tener que
entrar por el módulo de compras.

**Sin `require_module`**, como toda lectura (RN-50): una compañía que bajó de
plan tiene que poder seguir viendo a quién le debe. Dejar de pagar no es una
funcionalidad que se compre.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.schemas.schemas_purchases import Payables
from app.services import crud_payables
from app.utils.auth_dependency import Sesion, get_db, require_admin

router = APIRouter()


@router.get("", response_model=Payables)
def cuentas_por_pagar(
    supplier_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Saldo por proveedor y por compra, con antigüedad (RF-44).

    Es de administración porque dice cuánto debe el negocio y a quién: un cajero
    no tiene por qué verlo, igual que no ve los reportes.
    """
    return crud_payables.payables(db, supplier_id)
