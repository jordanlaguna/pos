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
from app.application.ports.ledger import Ledger, NullLedger
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
from app.domain.ledger import SoldDocument, SoldLine
from app.domain.money import Money
from app.domain.sale import (
    SaleLine,
    Totals,
    change_due,
    check_declared_totals,
    check_payment,
    check_payment_method,
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
        ledger: Ledger | None = None,
    ) -> None:
        self._products = products
        self._sales = sales
        self._settings = settings
        self._uow = uow
        self._clock = clock
        # Con contabilidad apagada —que es el caso de casi todas las compañías—
        # el libro es el nulo y no hace nada. El caso de uso no pregunta si está
        # activa: siempre cuenta lo que pasó (RN-59).
        self._ledger = ledger or NullLedger()

    def __call__(self, request: SaleRequest) -> RegisteredSale:
        if not request.lines:
            raise EmptySale()
        # El número de factura es único. Estaba en el router; es una regla de la
        # venta, no del transporte.
        if self._sales.exists_with_number(request.sale_number):
            raise DuplicateSaleNumber(request.sale_number)

        # Antes de tocar la base: el método es un conjunto cerrado (T-1104) y no
        # depende de nada que haya que ir a leer.
        check_payment_method(request.payment_method)

        for pedida in request.lines:
            if not pedida.product_id or pedida.quantity <= 0:
                raise InvalidQuantity(pedida.quantity)

        with self._uow:
            # Se bloquean todos de una: pedirlos uno por uno en distinto orden
            # desde dos cajas es como se fabrica un interbloqueo.
            disponibles = self._products.lock_for_sale(
                [line.product_id for line in request.lines]
            )

            # La tasa del negocio se lee UNA vez y sirve de respaldo para los
            # productos que no tienen la suya (RN-9). Leerla por línea abriría la
            # puerta a que dos líneas de la misma venta usaran tasas distintas si
            # alguien guarda la configuración en medio del cobro.
            tasa_del_negocio = self._settings.tax_rate()

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
                        # **Resuelta acá, no al guardar.** La línea sale de este
                        # bucle con una tarifa concreta, nunca con un nulo: lo que
                        # se congela en `sale_details` no puede depender de lo que
                        # esté configurado el día que alguien devuelva (RN-12).
                        tax_rate=(
                            producto.tax_rate
                            if producto.tax_rate is not None
                            else tasa_del_negocio
                        ),
                        # El costo también se congela (RN-63). En cero significa
                        # «nunca se compró» —así nace `products.cost`— y eso se
                        # guarda como nulo: cero diría que fue gratis.
                        unit_cost=producto.cost if producto.cost.is_positive else None,
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
            # Desde F5 cada línea trae la suya, así que la tasa que se pasa acá
            # es solo el respaldo —y no la usa ninguna línea, porque ya se
            # resolvieron todas arriba—. Se sigue pasando porque la firma la
            # exige y porque el día que entre una línea sin tarifa, la correcta
            # es esta y no cero.
            totales = sale_totals(lineas, tasa_del_negocio)
            check_declared_totals(request.declared, totales)
            check_payment(request.cash_received, totales.total)
            vuelto = change_due(request.cash_received, totales.total)

            # A partir de acá se escribe. Todo lo que podía decir que no, ya dijo
            # que sí.
            #
            # Una sola lectura del reloj para la venta y para su asiento: con dos
            # podrían caer a los lados de la medianoche y el asiento quedaría en
            # otro día —y, una vez al mes, en otro periodo contable—.
            momento = self._clock.now()
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
                created_at=momento,
                lines=lineas,
            )

            for linea in lineas:
                self._products.adjust_stock(linea.product_id, -linea.quantity)

            # El asiento va **dentro** de la transacción (RN-59). Si no se puede
            # escribir, esto lanza y la venta entera se revierte: un libro no
            # puede tener el estado «venta sin asiento». Lo que nunca lo tumba es
            # un mapeo incompleto, porque no existe: lo que falta cae en 1.9.99.
            self._ledger.record_sale(
                SoldDocument(
                    id=id_sale,
                    date=momento.date(),
                    payment_method=request.payment_method,
                ),
                [
                    SoldLine(
                        subtotal=linea.subtotal,
                        tax=linea.tax_with(tasa_del_negocio),
                        tax_rate=linea.rate_with(tasa_del_negocio),
                        quantity=linea.quantity,
                        unit_cost=linea.unit_cost,
                    )
                    for linea in lineas
                ],
            )

            self._uow.commit()

        return RegisteredSale(
            id_sale=id_sale, lines=lineas, totals=totales, change_given=vuelto
        )
