"""Compras y cuentas por pagar (F10, RF-44).

La compra se registra por `/inventory/entry`, porque **es** una entrada de
mercadería con proveedor, documento y condición de pago (plan §12.1). Lo que
vive acá es lo que solo tiene una compra: su saldo y sus abonos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas_purchases import SupplierPaymentIn, SupplierPaymentSuccess
from app.services import crud_supplier_payment
from app.utils.auth_dependency import Sesion, get_db, require_admin, require_module

router = APIRouter()

exige_compras = require_module("purchases")


@router.post("/{entry_id}/payments", response_model=SupplierPaymentSuccess)
def abonar(
    entry_id: int,
    datos: SupplierPaymentIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(exige_compras),
):
    """Abona a una compra (RN-55, RN-56).

    El abono lo hace **quien lo pide**, y eso importa cuando es en efectivo: la
    salida sale de *su* turno de caja, que es el que tiene la gaveta abierta. Un
    administrador sin caja abierta paga por transferencia o abre la suya; no
    puede sacarle plata al turno de otro.
    """
    return crud_supplier_payment.pagar(db, entry_id, datos, user_id=admin.user.id_user)
