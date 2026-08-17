"""
Registrar una venta.

Es el caso de uso donde vivía el defecto 1: la cabecera se confirmaba **antes**
de validar las existencias, y como el `except` solo atrapaba `SQLAlchemyError`,
un `HTTPException` por falta de stock subía sin revertir nada. Cada intento
fallido dejaba una factura guardada sin líneas y sin descontar inventario, que
además ensuciaba todos los reportes.

El orden de acá es lo que lo impide, y no es un detalle de estilo:

1. **Se valida todo.** Nada se escribe.
2. **Se bloquean los productos** mientras se valida, para que dos cajas no
   vendan la misma última unidad.
3. **Se escribe al final**, en una sola transacción.

O entra la venta completa, o no entra nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.repositories import (
    ProductRepository,
    SaleRepository,
    SettingsRepository,
    UnitOfWork,
)
from app.domain.errors import (
    DomainError,
    DuplicateSaleNumber,
    EmptySale,
    InvalidQuantity,
)
from app.domain.money import Money
from app.domain.sale import (
    SaleLine,
    Totals,
    change_due,
    check_declared_totals,
    check_payment,
    check_stock,
    sale_totals,
)


class ProductNotFound(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


class ProductWithoutPrice(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no tiene precio")
        self.product_id = product_id


@dataclass(frozen=True)
class RequestedLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class SaleRequest:
    """
    Lo que pide quien cobra.

    Los montos que trae son lo que el POS **le mostró al cliente**, no lo que se
    va a guardar. El servidor los recalcula con sus propios precios y su propia
    tasa, guarda los suyos y solo usa los declarados para comprobar que las dos
    partes están viendo lo mismo.
    """

    sale_number: str
    client_id: int | None
    user_id: int
    subtotal: Money
    tax: Money
    total: Money
    payment_method: str
    cash_received: Money
    change_given: Money
    lines: list[RequestedLine]

    @property
    def declared(self) -> Totals:
        return Totals(subtotal=self.subtotal, tax=self.tax, total=self.total)


@dataclass(frozen=True)
class RegisteredSale:
    id_sale: int
    lines: list[SaleLine]
    totals: Totals
    change_given: Money


class RegisterSale:
    def __init__(
        self,
        *,
        products: ProductRepository,
        sales: SaleRepository,
        settings: SettingsRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._products = products
        self._sales = sales
        self._settings = settings
        self._uow = uow
        self._clock = clock

    def __call__(self, request: SaleRequest) -> RegisteredSale:
        if not request.lines:
            raise EmptySale()
        # El número de factura es único. Estaba en el router; es una regla de la
        # venta, no del transporte.
        if self._sales.exists_with_number(request.sale_number):
            raise DuplicateSaleNumber(request.sale_number)

        for pedida in request.lines:
            if not pedida.product_id or pedida.quantity <= 0:
                raise InvalidQuantity(pedida.quantity)

        with self._uow:
            # Se bloquean todos de una: pedirlos uno por uno en distinto orden
            # desde dos cajas es como se fabrica un interbloqueo.
            disponibles = self._products.lock_for_sale(
                [line.product_id for line in request.lines]
            )

            lineas: list[SaleLine] = []
            for pedida in request.lines:
                producto = disponibles.get(pedida.product_id)
                if producto is None:
                    raise ProductNotFound(pedida.product_id)
                if producto.price is None:
                    raise ProductWithoutPrice(pedida.product_id)

                check_stock(pedida.product_id, producto.stock, pedida.quantity)
                lineas.append(
                    SaleLine(
                        product_id=pedida.product_id,
                        unit_price=producto.price,
                        quantity=pedida.quantity,
                    )
                )

            # ------------------------------------------------- la plata
            #
            # Los totales los calcula el servidor, con los precios que acaba de
            # leer y la tasa que tiene configurada. Los que mandó el POS solo
            # sirven para comprobar que ambos están viendo lo mismo; si no
            # cuadran, la venta no entra. Antes se guardaba la cabecera tal como
            # llegaba: un cliente con una lista de precios vieja —o alterada—
            # dejaba en la base una venta cuyos totales no correspondían a sus
            # propias líneas.
            totales = sale_totals(lineas, self._settings.tax_rate())
            check_declared_totals(request.declared, totales)
            check_payment(request.cash_received, totales.total)
            vuelto = change_due(request.cash_received, totales.total)

            # A partir de acá se escribe. Todo lo que podía decir que no, ya dijo
            # que sí.
            id_sale = self._sales.add(
                sale_number=request.sale_number,
                client_id=request.client_id,
                user_id=request.user_id,
                subtotal=totales.subtotal,
                tax=totales.tax,
                total=totales.total,
                payment_method=request.payment_method,
                cash_received=request.cash_received,
                change_given=vuelto,
                # La hora la pone el servidor, nunca el cliente (defecto 9). El
                # turno de caja se delimita comparando contra `opened_at`, que
                # sella este mismo backend: dos relojes no se pueden comparar.
                created_at=self._clock.now(),
                lines=lineas,
            )

            for linea in lineas:
                self._products.adjust_stock(linea.product_id, -linea.quantity)

            self._uow.commit()

        return RegisteredSale(
            id_sale=id_sale, lines=lineas, totals=totales, change_given=vuelto
        )
