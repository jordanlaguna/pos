"""
El turno de caja.

La aritmética del arqueo, sin base de datos. Quién vendió qué y en qué ventana
de tiempo lo resuelve el repositorio; acá solo se suma y se resta.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InsufficientCash, InvalidMovement
from .money import Money

#: Los únicos dos tipos de movimiento. No es un enum para no obligar a la capa
#: de persistencia a conocer uno: en la base es un `VARCHAR`.
MOVEMENT_TYPES = ("entrada", "salida")


@dataclass(frozen=True)
class CashCount:
    """Lo que compone el efectivo esperado de un turno."""

    opening: Money
    cash_sales: Money
    movements_in: Money
    movements_out: Money
    returns: Money


def expected_amount(count: CashCount) -> Money:
    """
    Lo que tiene que haber en la gaveta.

    Apertura + ventas en efectivo + entradas − salidas − devoluciones.

    **Solo el efectivo cuenta.** Una venta con tarjeta o transferencia no pone
    un colón en la gaveta, así que sumarla haría que todo turno con datáfono
    cerrara con un faltante igual a lo cobrado con tarjeta.
    """
    return (
        count.opening
        + count.cash_sales
        + count.movements_in
        - count.movements_out
        - count.returns
    )


def difference(counted: Money, expected: Money) -> Money:
    """Contado − esperado. Negativo es faltante; positivo, sobrante."""
    return counted - expected


def check_movement(type_: str, amount: Money, reason: str, available: Money) -> None:
    """
    Valida un movimiento de gaveta.

    La regla que importa es la última: no se puede sacar más efectivo del que
    hay. Sin ella, el esperado del turno queda negativo y el arqueo deja de
    significar nada.
    """
    if type_ not in MOVEMENT_TYPES:
        raise InvalidMovement("el tipo debe ser 'entrada' o 'salida'")
    if not amount.is_positive:
        raise InvalidMovement("el monto debe ser mayor que cero")
    if not reason or not reason.strip():
        raise InvalidMovement("hace falta el motivo del movimiento")
    if type_ == "salida" and (available - amount).is_negative:
        raise InsufficientCash(available, amount)


def check_opening(amount: Money) -> None:
    """El fondo de apertura puede ser cero, pero no negativo."""
    if amount.is_negative:
        raise InvalidMovement("el monto de apertura no puede ser negativo")
