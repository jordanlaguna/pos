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
from .tax import TaxRate


@dataclass(frozen=True)
class ReturnLine:
    product_id: int
    unit_price: Money
    quantity: int

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


def refund_total(lines: list[ReturnLine], rate: TaxRate) -> Money:
    """
    Lo que se le devuelve al cliente: el neto de las líneas más su impuesto.

    Con la tasa de la venta original, que es lo que hace que subir el IVA no
    cambie lo que se reembolsa por algo cobrado antes.
    """
    neto = Money.sum(line.subtotal for line in lines)
    return rate.add_to(neto)
