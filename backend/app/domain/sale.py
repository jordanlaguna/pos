"""
La venta: qué se cobra y cuánto da.

Acá no se guarda nada ni se consulta nada. Entran líneas y una tasa, salen los
totales. Es lo que permite comprobar que 3 × 1450 dan 4 915,50 sin levantar
MySQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import (
    EmptySale,
    InsufficientPayment,
    InsufficientStock,
    InvalidQuantity,
    TotalsMismatch,
)
from .money import Money
from .tax import TaxRate


@dataclass(frozen=True)
class SaleLine:
    """Un producto, su precio y cuántas unidades van."""

    product_id: int
    unit_price: Money
    quantity: int

    def __post_init__(self) -> None:
        # `bool` antes que `int` por lo mismo que en Money: `True` es 1.
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidQuantity(self.quantity)
        if self.quantity <= 0:
            raise InvalidQuantity(self.quantity)
        if self.unit_price.is_negative:
            raise InvalidQuantity(self.unit_price)

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Totals:
    subtotal: Money
    tax: Money
    total: Money


def sale_totals(lines: list[SaleLine], rate: TaxRate) -> Totals:
    """
    Subtotal → impuesto → total, en ese orden.

    Se redondea línea por línea y no al final, igual que hacía
    `CalculateTotalNew()` del original. No es lo mismo: tres líneas de 0,335
    suman 1,01 redondeando cada una y 1,00 redondeando al final, y lo que el
    cajero ve en la pantalla son las líneas.
    """
    if not lines:
        raise EmptySale()

    subtotal = Money.sum(line.subtotal for line in lines)
    tax = rate.apply(subtotal)
    return Totals(subtotal=subtotal, tax=tax, total=subtotal + tax)


#: Tolerancia al comparar lo que declara el POS contra lo que calcula el
#: servidor.
#:
#: Un céntimo, y no cero, porque los dos no calculan igual y no pueden: el POS
#: hace la aritmética en coma flotante binaria y el servidor en decimal exacto.
#: Cotejando 1 208 montos representativos, los dos coinciden salvo cuando el
#: binario cae justo por debajo de un empate a medio céntimo —`0.035` se guarda
#: como `0.034999999999999996`—, y ahí difieren en exactamente 0,01. Con precios
#: en colones enteros el caso no se alcanza nunca; con céntimos, sí.
#:
#: Que la tolerancia exista no afloja nada: **lo que se guarda es siempre el
#: número del servidor**. Esta comparación no es un control de seguridad, es un
#: detector de errores de verdad —una lista de precios vieja, un carrito que
#: quedó desincronizado—, y con tolerancia cero saltaría por ruido binario en
#: vez de por esos.
TOTALS_TOLERANCE = Money("0.01")


def check_declared_totals(declared: Totals, computed: Totals) -> None:
    """
    Compara lo que dice el POS con lo que da el servidor.

    Se comparan las tres cifras y no solo el total: un subtotal y un impuesto
    que se compensan entre sí dan el mismo total y son, aun así, un error.
    """
    for campo, dicho, dado in (
        ("subtotal", declared.subtotal, computed.subtotal),
        ("impuesto", declared.tax, computed.tax),
        ("total", declared.total, computed.total),
    ):
        if abs(dicho - dado) > TOTALS_TOLERANCE:
            raise TotalsMismatch(campo, dicho, dado)


def check_payment(cash_received: Money, total: Money) -> None:
    """El efectivo recibido tiene que alcanzar. Se mide contra el total del
    servidor, no contra el declarado."""
    if not is_payment_enough(cash_received, total):
        raise InsufficientPayment(cash_received, total)


def change_due(cash_received: Money, total: Money) -> Money:
    """
    El vuelto. Nunca negativo.

    Que un pago insuficiente dé cero y no un número rojo es a propósito: quien
    decide si alcanza es `is_payment_enough`, antes de llegar acá. Un vuelto
    negativo mostrado en pantalla se lee como si el cliente debiera plata.
    """
    vuelto = cash_received - total
    return Money.zero() if vuelto.is_negative else vuelto


def is_payment_enough(cash_received: Money, total: Money) -> bool:
    return not (cash_received - total).is_negative


def check_stock(product_id: int, available: int, requested: int) -> None:
    """Lanza si no alcanzan las existencias. No devuelve nada: o pasa, o no."""
    if requested > available:
        raise InsufficientStock(product_id, available, requested)
