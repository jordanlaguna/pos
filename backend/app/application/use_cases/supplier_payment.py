"""
Abonar a una compra (F10, T-1010, RN-55 y RN-56).

Dos reglas y un orden. Las reglas: un abono no supera el saldo de **esa** compra
—el saldo del proveedor es la suma, no un número aparte— y un pago en efectivo
sale de la caja abierta o no sale.

El orden: la salida de caja se escribe **antes** que el abono, porque el abono
la apunta. Y las dos dentro de la misma transacción, porque una gaveta que bajó
por un abono que después falló es un descuadre que nadie va a saber explicar.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.repositories import (
    StockEntryRepository,
    SupplierPaymentRepository,
    UnitOfWork,
)
from app.application.use_cases.cash_session import AddCashMovement
from app.domain.errors import DomainError
from app.domain.ledger import SupplierPaymentRef
from app.domain.money import Money
from app.domain.purchases import CASH, apply_payment, check_payment, remaining_balance


class PurchaseNotFound(DomainError):
    """No hay compra que abonar con ese número.

    También cuando la entrada existe pero **no es una compra**: una entrada sin
    proveedor no genera cuenta por pagar (RN-52), así que desde las cuentas por
    pagar no existe. Es el mismo criterio con el que un proveedor de otra
    compañía responde «no está» en vez de «no es suyo» (RNF-1): la respuesta se
    da desde donde se pregunta.
    """

    def __init__(self, entry_id: int) -> None:
        super().__init__(f"la compra {entry_id} no existe")
        self.entry_id = entry_id


class PurchaseCancelled(DomainError):
    """Se quiso abonar a una compra anulada.

    Una anulada no debe nada: su cuenta por pagar se revirtió con ella. Pasa de
    verdad cuando dos personas trabajan a la vez —una anula mientras la otra
    tiene abierta la pantalla de saldos— y por eso no alcanza con esconder el
    botón.
    """

    def __init__(self, entry_id: int) -> None:
        super().__init__(f"la compra {entry_id} está anulada")
        self.entry_id = entry_id


@dataclass(frozen=True)
class PaymentRequest:
    entry_id: int
    amount: Money
    #: 'cash' | 'transfer' | 'other'. Solo el primero mueve la gaveta (RN-56).
    method: str
    user_id: int
    #: Número de transferencia o de cheque. Es lo que se compara con el banco.
    reference: str | None = None
    #: El motivo del movimiento de caja, **armado por la interfaz** (RN-30).
    #: Acá no se escribe: una capa que arma la oración tiene que saber el idioma
    #: de la pantalla, y entonces no es aplicación. Solo hace falta cuando el
    #: método es efectivo, que es el único que escribe en la gaveta.
    reason: str = ""


@dataclass(frozen=True)
class RegisteredPayment:
    id_payment: int
    #: Lo que queda por pagar de **esa** compra después del abono.
    balance: Money
    #: La salida de caja, si la hubo. `None` con cualquier método que no sea
    #: efectivo: es lo que después evita que el asiento cuente dos veces la
    #: misma plata.
    cash_movement_id: int | None


class PaySupplier:
    def __init__(
        self,
        *,
        entries: StockEntryRepository,
        payments: SupplierPaymentRepository,
        movements: AddCashMovement,
        uow: UnitOfWork,
        clock: Clock,
        ledger: Ledger | None = None,
    ) -> None:
        self._entries = entries
        self._payments = payments
        self._movements = movements
        self._uow = uow
        self._clock = clock
        self._ledger = ledger or NullLedger()

    def __call__(self, request: PaymentRequest) -> RegisteredPayment:
        with self._uow:
            resultado = self.apply(request)
            self._uow.commit()
        return resultado

    def apply(self, request: PaymentRequest) -> RegisteredPayment:
        """El abono, comprobado y escrito, **sin confirmar**.

        Separado del `__call__` por la misma razón que en `AddCashMovement`: una
        compra de contado registra su abono dentro de la transacción de la
        compra. O entran la mercadería, el costo y el pago, o no entra nada.
        """
        compra = self._entries.get(request.entry_id)
        if compra is None or compra.supplier_id is None:
            raise PurchaseNotFound(request.entry_id)
        if compra.status == "anulada":
            raise PurchaseCancelled(request.entry_id)

        check_payment(request.amount, request.method)

        saldo = remaining_balance(
            Money(compra.total_cost), self._payments.amounts_for(request.entry_id)
        )
        # Lanza si se abona de más: no se ajusta al saldo en silencio, porque o
        # es un dedo de más o el abono va a otra factura (RN-55).
        queda = apply_payment(saldo, request.amount)

        movimiento = None
        if request.method == CASH:
            # Primero la gaveta, después el abono: el abono la apunta. Y con
            # esto vienen de regalo las dos comprobaciones del turno —que haya
            # uno abierto y que alcance el efectivo—, que son las mismas de
            # cualquier salida de caja porque es la misma plata.
            movimiento = self._movements.apply(
                user_id=request.user_id,
                type_="salida",
                amount=request.amount,
                reason=request.reason,
                # Esa salida no deja asiento propio: lo deja este abono, abajo.
                # Las dos juntas sacarían de la caja el doble de lo que salió.
                from_supplier_payment=True,
            )

        momento = self._clock.now()
        id_payment = self._payments.add(
            supplier_id=compra.supplier_id,
            entry_id=request.entry_id,
            amount=request.amount,
            method=request.method,
            reference=request.reference,
            cash_movement_id=movimiento.id if movimiento else None,
            user_id=request.user_id,
            paid_at=momento,
        )

        # Proveedores contra caja, banco o «por clasificar», según el medio.
        self._ledger.record_supplier_payment(
            SupplierPaymentRef(
                id=id_payment,
                date=momento.date(),
                amount=request.amount,
                method=request.method,
            )
        )

        return RegisteredPayment(
            id_payment=id_payment,
            balance=queda,
            cash_movement_id=movimiento.id if movimiento else None,
        )
