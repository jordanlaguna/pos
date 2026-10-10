"""
Dar salida a mercadería con motivo, y anular una salida (F15, RN-99).

Es la entrada vista en la otra dirección: lo que deja el inventario sin
venderse —merma, daño, vencido, consumo interno— con un motivo de un catálogo
de la compañía. Una salida sin motivo no existe. Se valora **al costo promedio
del producto en ese momento** y, con contabilidad activa, deja un asiento que
saca ese costo del inventario y lo lleva al gasto.

Una salida confirmada **no se edita**: se anula con motivo y bitácora, y la
anulación repone las existencias **al costo de la salida** —no al promedio de
hoy— y deja el asiento inverso por ese mismo valor (RN-98).

El orden es el de la venta: se valida todo, se bloquean todos los productos de
una, y se escribe al final en una sola transacción.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.inventory import StockExitRepository, StockReasonRepository
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.repositories import ProductRepository, UnitOfWork
from app.application.use_cases.move_stock import MoveStock
from app.domain.errors import DomainError, InvalidQuantity
from app.domain.inventory import (
    EXIT,
    EXIT_VOID,
    ExitLine,
    check_exit_reason,
    exit_total,
    exit_units,
)
from app.domain.ledger import StockExitDocument
from app.domain.money import Money


class ReasonNotFound(DomainError):
    """El motivo no existe, o es de otra compañía: para esta salida es lo mismo."""

    def __init__(self, reason_id: int) -> None:
        super().__init__(f"el motivo {reason_id} no existe")
        self.reason_id = reason_id


class ProductNotFoundInExit(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


class EmptyExit(DomainError):
    def __init__(self) -> None:
        super().__init__("la salida no tiene líneas")


class ExitNotFound(DomainError):
    def __init__(self, exit_id: int) -> None:
        super().__init__(f"la salida {exit_id} no existe")
        self.exit_id = exit_id


class ExitCancelled(DomainError):
    """Se quiso anular lo que ya está anulado: anular dos veces repondría dos veces."""

    def __init__(self, exit_id: int) -> None:
        super().__init__(f"la salida {exit_id} ya está anulada")
        self.exit_id = exit_id


class MissingVoidReason(DomainError):
    """Toda salida nació con motivo y se va con motivo (RN-99)."""

    def __init__(self) -> None:
        super().__init__("hace falta el motivo de la anulación")


@dataclass(frozen=True)
class RequestedExitLine:
    product_id: int
    quantity: int
    #: RN-104; viene con T-1507. Nulo es «sin lote».
    lot_id: int | None = None


@dataclass(frozen=True)
class ExitRequest:
    reason_id: int
    user_id: int
    #: De dónde sale (RN-102). Del `bid` de la sesión, como en la venta.
    branch_id: int
    notes: str | None
    lines: list[RequestedExitLine]


@dataclass(frozen=True)
class RegisteredExit:
    id_exit: int
    units: int
    total_cost: Money
    lines: list[ExitLine]


class RegisterStockExit:
    def __init__(
        self,
        *,
        products: ProductRepository,
        reasons: StockReasonRepository,
        exits: StockExitRepository,
        uow: UnitOfWork,
        clock: Clock,
        stock: MoveStock,
        ledger: Ledger | None = None,
    ) -> None:
        self._products = products
        self._reasons = reasons
        self._exits = exits
        self._uow = uow
        self._clock = clock
        self._stock = stock
        # Como en la venta: con el módulo apagado es el libro nulo (RN-59).
        self._ledger = ledger or NullLedger()

    def __call__(self, request: ExitRequest) -> RegisteredExit:
        if not request.lines:
            raise EmptyExit()
        for pedida in request.lines:
            if not pedida.product_id or pedida.quantity <= 0:
                raise InvalidQuantity(pedida.quantity)

        # El motivo, antes de tocar la base: existe, está activo y no es el de
        # la toma, que ese lo pone la toma (RN-100).
        motivo = self._reasons.get(request.reason_id)
        if motivo is None:
            raise ReasonNotFound(request.reason_id)
        check_exit_reason(motivo)

        with self._uow:
            # Todos de una y en orden de id, antes de tocar ninguno (plan §15.1).
            retratos = self._products.lock([pedida.product_id for pedida in request.lines])

            lineas: list[ExitLine] = []
            for pedida in request.lines:
                producto = retratos.get(pedida.product_id)
                if producto is None:
                    raise ProductNotFoundInExit(pedida.product_id)
                lineas.append(
                    ExitLine(
                        product_id=pedida.product_id,
                        quantity=pedida.quantity,
                        # Al promedio del momento (RN-99). Cero si nunca se
                        # compró: sale sin plata, y el valorado lo cuenta.
                        unit_cost=producto.cost,
                        lot_id=pedida.lot_id,
                    )
                )

            total = exit_total(lineas)
            # Una sola lectura del reloj para la salida, su kárdex y su asiento.
            momento = self._clock.now()
            id_exit = self._exits.add(
                branch_id=request.branch_id,
                reason_id=request.reason_id,
                user_id=request.user_id,
                notes=request.notes,
                total_cost=total,
                created_at=momento,
                lines=lineas,
            )

            # Lo que no hay no sale: lo dice `MoveStock` por línea, y la
            # transacción entera se revierte con la primera que falte.
            for indice, linea in enumerate(lineas, start=1):
                self._stock(
                    product_id=linea.product_id,
                    branch_id=request.branch_id,
                    delta=-linea.quantity,
                    kind=EXIT,
                    unit_cost=linea.unit_cost,
                    source_type="stock_exit",
                    source_id=id_exit,
                    source_line=indice,
                    lot_id=linea.lot_id,
                    user_id=request.user_id,
                    moved_at=momento,
                )

            # Del inventario al gasto, dentro de la misma transacción (RN-59).
            self._ledger.record_stock_exit(
                StockExitDocument(id=id_exit, date=momento.date()), total
            )
            self._uow.commit()

        return RegisteredExit(
            id_exit=id_exit, units=exit_units(lineas), total_cost=total, lines=lineas
        )


@dataclass(frozen=True)
class CancelledExit:
    id_exit: int
    units_returned: int
    total_cost: Money


class CancelStockExit:
    """Anula una salida y repone lo que sacó, al costo con que salió."""

    def __init__(
        self,
        *,
        products: ProductRepository,
        exits: StockExitRepository,
        uow: UnitOfWork,
        clock: Clock,
        stock: MoveStock,
        ledger: Ledger | None = None,
    ) -> None:
        self._products = products
        self._exits = exits
        self._uow = uow
        self._clock = clock
        self._stock = stock
        self._ledger = ledger or NullLedger()

    def __call__(self, exit_id: int, *, user_id: int, reason: str) -> CancelledExit:
        with self._uow:
            anulada = self.apply(exit_id, user_id=user_id, reason=reason)
            self._uow.commit()
        return anulada

    def apply(self, exit_id: int, *, user_id: int, reason: str) -> CancelledExit:
        """La anulación comprobada y escrita, **sin confirmar**, para que la
        bitácora entre en la misma transacción que el hecho que narra."""
        # El motivo es obligatorio **siempre**, a diferencia de la entrada, que
        # solo lo exige a las compras: toda salida nació con motivo (RN-99).
        if not reason or not reason.strip():
            raise MissingVoidReason()

        salida = self._exits.get(exit_id)
        if salida is None:
            raise ExitNotFound(exit_id)
        if salida.status == "voided":
            raise ExitCancelled(exit_id)

        lineas = self._exits.lines_of(exit_id)
        # Todos de una, en orden de id (plan §15.1). Los productos de una salida
        # no se pueden haber borrado: el kárdex los sostiene.
        self._products.lock([linea.product_id for linea in lineas])

        # Una reversión es un movimiento propio con signo contrario (RN-98), en
        # la sucursal de la salida y al costo de la salida. El promedio del
        # producto no se toca.
        momento = self._clock.now()
        for indice, linea in enumerate(lineas, start=1):
            self._stock(
                product_id=linea.product_id,
                branch_id=salida.branch_id,
                delta=+linea.quantity,
                kind=EXIT_VOID,
                unit_cost=linea.unit_cost,
                source_type="stock_exit",
                source_id=exit_id,
                source_line=indice,
                lot_id=linea.lot_id,
                user_id=user_id,
                moved_at=momento,
            )
        self._exits.mark_voided(exit_id, voided_at=momento, reason=reason.strip())

        # El asiento inverso, por el valor de la salida (RN-98).
        self._ledger.record_stock_exit_void(
            StockExitDocument(id=exit_id, date=momento.date()), salida.total_cost
        )
        return CancelledExit(
            id_exit=exit_id,
            units_returned=sum(linea.quantity for linea in lineas),
            total_cost=salida.total_cost,
        )
