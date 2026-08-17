"""
Entradas de mercadería.

Lo que entra al inventario. Tres reglas y las tres duelen si faltan:

1. **Una factura no se carga dos veces.** Duplicarla suma el inventario en
   silencio, y el error solo se descubre contando físicamente.
2. **Anular devuelve el stock**, pero solo si todavía está. Si parte ya se
   vendió, revertir dejaría existencias negativas.
3. **Una línea sin producto no entra.** Ni el que existe, ni el que se va a
   crear: hay que decir cuál.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import CannotCancel, InvalidQuantity, InvalidSource
from .money import Money

#: De dónde puede venir una entrada: cargada a mano, de una hoja de cálculo o
#: del XML de una factura electrónica de Hacienda.
SOURCES = ("manual", "excel", "xml")


@dataclass(frozen=True)
class EntryLine:
    """Un producto que entra, con su costo."""

    product_id: int
    quantity: int
    unit_cost: Money

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidQuantity(self.quantity)
        if self.quantity <= 0:
            raise InvalidQuantity(self.quantity)
        if self.unit_cost.is_negative:
            raise InvalidQuantity(self.unit_cost)

    @property
    def subtotal(self) -> Money:
        return self.unit_cost * self.quantity


def check_source(source: object) -> None:
    if source not in SOURCES:
        raise InvalidSource(source)


def entry_total(lines: list[EntryLine]) -> Money:
    """Costo total. Se redondea línea por línea, como en la venta."""
    return Money.sum(line.subtotal for line in lines)


def entry_units(lines: list[EntryLine]) -> int:
    return sum(line.quantity for line in lines)


def check_cancellable(product_id: int, available: int, added: int) -> None:
    """
    Lanza si anular dejaría el inventario en negativo.

    Se avisa con el producto concreto en vez de romper el stock: quien lo lea
    tiene que poder ajustarlo a mano sabiendo cuál es.
    """
    if available < added:
        raise CannotCancel(product_id, available, added)
