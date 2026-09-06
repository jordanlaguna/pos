"""
Devoluciones.

Dos reglas mandan acá y las dos son de plata:

1. **No se puede devolver más de lo que se llevó.** Ni de una vez ni sumando
   varias devoluciones parciales de la misma venta.
2. **Se reembolsa con la tasa de SU venta**, no con la configurada hoy. Vive en
   `TaxRate.of_sale`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ExcessiveReturn, InvalidQuantity, NotSoldInThisSale
from .money import Money
from .sale import Totals, group_by_rate
from .tax import TaxRate


@dataclass(frozen=True)
class ReturnLine:
    """Lo que se devuelve, con **la tarifa que llevaba esa línea al venderse**.

    En `None` para las ventas anteriores a F5, que no tienen la columna: ahí la
    tasa se reconstruye del encabezado con `TaxRate.of_sale`, que es correcto
    porque esas ventas llevan una sola tarifa.
    """

    product_id: int
    unit_price: Money
    quantity: int
    tax_rate: TaxRate | None = None

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidQuantity(self.quantity)
        if self.quantity <= 0:
            raise InvalidQuantity(self.quantity)

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


def remaining_units(sold: int, already_returned: int) -> int:
    """Unidades que todavía se pueden devolver. Nunca negativo."""
    return max(0, sold - already_returned)


def check_returnable(
    product_id: int,
    sold: dict[int, int],
    already_returned: dict[int, int],
    requested: int,
) -> None:
    """Lanza si ese producto no iba en la venta o si ya no quedan unidades."""
    if product_id not in sold:
        raise NotSoldInThisSale(product_id)

    quedan = remaining_units(sold[product_id], already_returned.get(product_id, 0))
    if requested > quedan:
        raise ExcessiveReturn(product_id, quedan, requested)


def is_fully_returned(sold: dict[int, int], already_returned: dict[int, int]) -> bool:
    """
    True cuando no queda ni una unidad de la venta por devolver.

    Una venta sin líneas cuenta como devuelta del todo: no queda nada por
    devolver. Es el caso de `all()` sobre una lista vacía, y acá es el resultado
    correcto y no un accidente.
    """
    return all(
        already_returned.get(product_id, 0) >= cantidad
        for product_id, cantidad in sold.items()
    )


def refund_totals(lines: list[ReturnLine], rate: TaxRate) -> Totals:
    """
    Lo que se le devuelve al cliente, desglosado por tarifa.

    `rate` es el respaldo: se usa en las líneas que no traen la suya, o sea las
    de una venta anterior a F5. Para esas sigue siendo lo correcto —llevaban una
    sola tarifa— y es lo que hace que subir el IVA no cambie lo que se reembolsa
    por algo cobrado antes.

    **Por qué la tarifa tiene que venir en la línea y no deducirse del
    encabezado.** Mientras toda la venta lleve una tasa, `tax / subtotal`
    (`TaxRate.of_sale`) la reconstruye exacta. En cuanto se mezclan, ese cociente
    es un **promedio**, y devolver una sola línea con el promedio devuelve de más
    o de menos:

        venta: 1 medicamento ₡1 000 al 2 %  +  1 arroz ₡1 000 al 13 %
               subtotal ₡2 000 · impuesto ₡150 · promedio 7,5 %

        devolver solo el medicamento →  con su tarifa   1 000 × 1,02 = ₡1 020
                                        con el promedio 1 000 × 1,075 = ₡1 075

    ₡55 de más, y ₡55 de menos si lo que se devuelve es el arroz. La caja no
    cuadra y nadie sabe por qué.
    """
    by_rate = group_by_rate(((l.subtotal, l.tax_rate) for l in lines), rate)
    neto = Money.sum(grupo.base for grupo in by_rate)
    impuesto = Money.sum(grupo.tax for grupo in by_rate)
    return Totals(
        subtotal=neto, tax=impuesto, total=neto + impuesto, by_rate=by_rate
    )


def refund_total(lines: list[ReturnLine], rate: TaxRate) -> Money:
    """Solo la cifra que se le entrega al cliente. El desglose está en
    `refund_totals`, que es lo que hay que guardar (`returns` lo parte en
    subtotal e impuesto desde F5)."""
    return refund_totals(lines, rate).total
