"""
Registrar una devolución.

Dos reglas mandan, y las dos son de plata:

1. **No se puede devolver más de lo que se llevó**, ni de una vez ni sumando
   varias parciales de la misma venta.
2. **Se reembolsa con la tasa de SU venta**, no con la configurada hoy. Si el
   dueño sube el IVA, lo que se devuelve por algo cobrado antes sigue siendo lo
   que se cobró.

Y una consecuencia que sí se veía en el sistema original: **el stock vuelve al
inventario**. Antes no volvía.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.repositories import (
    ProductRepository,
    ReturnRepository,
    SaleRepository,
    SettingsRepository,
    UnitOfWork,
)
from app.domain.errors import DomainError, InvalidQuantity
from app.domain.ledger import ReturnDocument, SoldLine
from app.domain.money import Money
from app.domain.returns import (
    ReturnLine,
    check_returnable,
    is_fully_returned,
    refund_totals,
)
from app.domain.tax import TaxRate


class SaleNotFound(DomainError):
    def __init__(self, sale_id: int) -> None:
        super().__init__(f"la venta {sale_id} no existe")
        self.sale_id = sale_id


class EmptyReturn(DomainError):
    def __init__(self) -> None:
        super().__init__("la devolución no tiene productos")


class MissingReason(DomainError):
    def __init__(self) -> None:
        super().__init__("hace falta el motivo de la devolución")


@dataclass(frozen=True)
class RequestedReturnLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class ReturnRequest:
    sale_id: int
    user_id: int
    reason: str
    lines: list[RequestedReturnLine]


@dataclass(frozen=True)
class RegisteredReturn:
    id_return: int
    total: Money
    lines: list[ReturnLine]
    is_full: bool


class RegisterReturn:
    def __init__(
        self,
        *,
        sales: SaleRepository,
        returns: ReturnRepository,
        products: ProductRepository,
        settings: SettingsRepository,
        uow: UnitOfWork,
        clock: Clock,
        ledger: Ledger | None = None,
    ) -> None:
        self._sales = sales
        self._returns = returns
        self._products = products
        self._settings = settings
        self._uow = uow
        self._clock = clock
        self._ledger = ledger or NullLedger()

    def __call__(self, request: ReturnRequest) -> RegisteredReturn:
        venta = self._sales.get(request.sale_id)
        if venta is None:
            raise SaleNotFound(request.sale_id)
        if not request.lines:
            raise EmptyReturn()
        if not request.reason or not request.reason.strip():
            raise MissingReason()

        vendido = self._sales.sold_quantities(request.sale_id)
        precios = self._sales.sold_prices(request.sale_id)
        tarifas = self._sales.sold_tax_rates(request.sale_id)
        # El costo con el que salió la mercadería (RN-63). Devolverla al
        # inventario por lo que cuesta hoy inventaría utilidad cada vez que el
        # proveedor sube el precio entre la venta y la devolución.
        costos = self._sales.sold_costs(request.sale_id)
        ya_devuelto = self._returns.returned_quantities(request.sale_id)

        # La tasa del ENCABEZADO de esta venta, reconstruida de sus montos. Desde
        # F5 es solo el respaldo: sirve para las ventas anteriores a la migración
        # 006, que no tienen tarifa en la línea y llevan una sola, así que el
        # cociente la reconstruye exacta. La configurada entra un escalón más
        # abajo, para las del WinForms que quedaron sin desglose.
        #
        # **No sirve cuando la venta mezcla tarifas**: ahí `tax / subtotal` es un
        # promedio, y devolver una sola línea con el promedio reembolsa de más o
        # de menos. Por eso lo primero que se mira es la tarifa de la línea.
        del_encabezado = TaxRate.of_sale(
            Money(venta.subtotal), Money(venta.tax), default=self._settings.tax_rate()
        )

        # Se valida TODO antes de escribir: o entra la devolución completa, o
        # ninguna.
        lineas: list[ReturnLine] = []
        for pedida in request.lines:
            if pedida.quantity <= 0:
                raise InvalidQuantity(pedida.quantity)
            check_returnable(pedida.product_id, vendido, ya_devuelto, pedida.quantity)
            lineas.append(
                ReturnLine(
                    product_id=pedida.product_id,
                    unit_price=precios[pedida.product_id],
                    quantity=pedida.quantity,
                    # Resuelta acá y nunca nula, igual que en la venta: lo que se
                    # guarda no puede depender de lo que esté configurado el día
                    # que alguien lea esta devolución.
                    tax_rate=tarifas.get(pedida.product_id, del_encabezado),
                )
            )

        totales = refund_totals(lineas, del_encabezado)

        with self._uow:
            # Una sola lectura del reloj para la devolución y su asiento.
            momento = self._clock.now()
            id_return = self._returns.add(
                sale_id=request.sale_id,
                user_id=request.user_id,
                reason=request.reason.strip(),
                subtotal=totales.subtotal,
                tax=totales.tax,
                total=totales.total,
                created_at=momento,
                lines=lineas,
            )
            for linea in lineas:
                # Lo que el sistema original no hacía: reponer.
                self._products.adjust_stock(linea.product_id, +linea.quantity)

            # El inverso de la venta, dentro de la misma transacción (RN-59).
            self._ledger.record_return(
                ReturnDocument(id=id_return, date=momento.date()),
                [
                    SoldLine(
                        subtotal=linea.subtotal,
                        tax=(linea.tax_rate or del_encabezado).apply(linea.subtotal),
                        tax_rate=linea.tax_rate or del_encabezado,
                        quantity=linea.quantity,
                        unit_cost=costos.get(linea.product_id),
                    )
                    for linea in lineas
                ],
            )
            self._uow.commit()

        despues = dict(ya_devuelto)
        for linea in lineas:
            despues[linea.product_id] = despues.get(linea.product_id, 0) + linea.quantity

        return RegisteredReturn(
            id_return=id_return,
            total=totales.total,
            lines=lineas,
            is_full=is_fully_returned(vendido, despues),
        )
