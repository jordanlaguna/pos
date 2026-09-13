"""Compras y cuentas por pagar (F10, RN-53 a RN-57).

Cuatro reglas puras: cuánto pasa a costar un producto después de una compra,
cuánto suma una compra, cuánto se le debe todavía a un proveedor y cuán vieja
es esa deuda. Ninguna sabe de base de datos ni de reloj —la fecha de hoy entra
como argumento— y por eso se prueban con una tabla de casos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import PaymentExceedsBalance
from .money import Money
from .tax import TaxRate

#: Los tramos de antigüedad de un saldo, en días y de menor a mayor (RF-44).
#: Son los que usa cualquier contador y los que espera ver quien cobra.
TRAMOS: tuple[int, ...] = (30, 60, 90)


def weighted_average_cost(
    stock: int, cost: Money, quantity: int, unit_cost: Money
) -> Money:
    """El costo del producto después de entrarle `quantity` a `unit_cost` (RN-54).

    Promedio ponderado móvil: lo que había por lo que costaba, más lo que entra
    por lo que costó, entre el total.

        10 unidades a ₡100  +  10 a ₡120  →  ₡110

    **Con existencia menor o igual a cero, el costo es el de la compra.** No es
    un caso raro: pasa con el primer ingreso de un producto —que nace en cero— y
    con uno que se vendió de más. Promediar contra una existencia nula daría una
    división por cero, y contra una negativa daría un costo negativo, que es
    peor: se arrastraría a todos los asientos siguientes sin que nadie lo mire.
    """
    if stock <= 0:
        return unit_cost

    total = (cost * stock) + (unit_cost * quantity)
    return Money(total.amount / (stock + quantity))


@dataclass(frozen=True)
class PurchaseLine:
    """Una línea del documento del proveedor, con su impuesto (RN-53)."""

    quantity: int
    unit_cost: Money
    #: La del documento, no la del producto: el crédito fiscal es lo que se pagó.
    tax_rate: TaxRate

    @property
    def subtotal(self) -> Money:
        return self.unit_cost * self.quantity

    @property
    def tax(self) -> Money:
        return self.tax_rate.apply(self.subtotal)


@dataclass(frozen=True)
class PurchaseTotals:
    subtotal: Money
    tax: Money
    total: Money
    #: Base e impuesto por tarifa, que es el crédito fiscal del D-104 (RF-45).
    by_rate: tuple[tuple[TaxRate, Money, Money], ...]


def purchase_totals(lines: list[PurchaseLine]) -> PurchaseTotals:
    """Lo que suma una compra, con su desglose por tarifa.

    Se suma **línea por línea** y no aplicando una tasa al subtotal, por lo
    mismo que las ventas (RN-10): un documento puede traer 13 %, 1 % y exento a
    la vez, y el promedio no es ninguno de los tres.
    """
    subtotal = Money.sum(linea.subtotal for linea in lines)
    tax = Money.sum(linea.tax for linea in lines)

    por_tarifa: dict[TaxRate, tuple[Money, Money]] = {}
    for linea in lines:
        base, impuesto = por_tarifa.get(linea.tax_rate, (Money.zero(), Money.zero()))
        por_tarifa[linea.tax_rate] = (base + linea.subtotal, impuesto + linea.tax)

    return PurchaseTotals(
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
        # Ordenado por tarifa para que el reporte salga siempre igual: sin esto,
        # el orden lo decide en qué fila del documento apareció cada tarifa.
        by_rate=tuple(
            (tarifa, base, impuesto) for tarifa, (base, impuesto) in sorted(por_tarifa.items())
        ),
    )


def due_date(document_date: date, payment_terms_days: int) -> date:
    """Cuándo vence una compra a crédito.

    Se cuenta desde la **fecha del documento** y no desde la de carga: una
    factura del día 28 que se captura el 3 del mes siguiente vence a los 30 días
    del 28, que es lo que el proveedor va a cobrar. Contar desde la captura le
    regalaría al negocio los días que tardó en digitarla.
    """
    return document_date + timedelta(days=max(0, payment_terms_days))


def remaining_balance(total: Money, payments: list[Money]) -> Money:
    """Lo que falta por pagar de una compra (RN-55).

    Nunca negativo: un abono de más es un error de captura, y un saldo negativo
    se sumaría al del proveedor y le rebajaría lo que sí debe en otra factura.
    Quien impide llegar a eso es `apply_payment`; esto es la red por si una fila
    vieja ya lo trae.
    """
    saldo = total - Money.sum(payments)
    return Money.zero() if saldo.is_negative else saldo


def apply_payment(balance: Money, amount: Money) -> Money:
    """El saldo después de abonar `amount`, o `PaymentExceedsBalance` (RN-55).

    Abonar de más no se corrige solo: o es un dedo de más al escribir, o el
    abono va a otra factura. Las dos cosas las arregla una persona, y para eso
    tiene que enterarse.
    """
    if amount > balance:
        raise PaymentExceedsBalance(balance=str(balance), requested=str(amount))
    return balance - amount


def aging_bucket(due_date: date | None, today: date) -> int:
    """En qué tramo de antigüedad cae un saldo: 0, 30, 60 o 90 (RF-44).

    El número es el **piso** del tramo en días —0 es «0 a 30», 90 es «más de
    90»— y no una etiqueta: la frase la arma el POS (RN-30).

    Sin fecha de vencimiento cae en el primer tramo. Es lo mismo que hace la
    suscripción sin fecha, pero al revés a propósito: allá no tener fecha
    cierra la puerta porque lo caro es vender gratis; acá lo caro sería marcar
    de morosa una compra de contado que nunca tuvo vencimiento.
    """
    if due_date is None:
        return 0

    dias = (today - due_date).days
    for tramo in reversed(TRAMOS):
        if dias > tramo:
            return tramo
    return 0
