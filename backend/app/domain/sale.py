"""
La venta: qué se cobra y cuánto da.

Acá no se guarda nada ni se consulta nada. Entran líneas y una tasa, salen los
totales. Es lo que permite comprobar que 3 × 1450 dan 4 915,50 sin levantar
MySQL.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    """Un producto, su precio, cuántas unidades van y con qué tarifa.

    `tax_rate` en `None` significa «la del documento»: la tasa configurada que
    pase quien llame. Es lo que tienen las líneas de una venta anterior a F5 y
    lo que tiene un producto al que nadie le puso tarifa propia (RN-9).
    """

    product_id: int
    unit_price: Money
    quantity: int
    tax_rate: TaxRate | None = None

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

    def rate_with(self, default: TaxRate) -> TaxRate:
        """La tarifa que le toca: la suya, o la del documento si no tiene."""
        return default if self.tax_rate is None else self.tax_rate

    def tax_with(self, default: TaxRate) -> Money:
        """El impuesto de ESTA línea, que es lo que se guarda en `sale_details`.

        Es la misma cuenta que hace `group_by_rate`, y tiene que serlo: si el
        detalle guardara un número y el encabezado otro, la factura no cuadraría
        consigo misma.
        """
        return self.rate_with(default).apply(self.subtotal)


@dataclass(frozen=True)
class RateBucket:
    """Lo que se cobró a una tarifa: su base y su impuesto.

    Es lo que necesita el documento impreso (RF-21) y, más adelante, el XML de
    Hacienda, que exige el desglose por tarifa y no solo el total.
    """

    rate: TaxRate
    base: Money
    tax: Money


@dataclass(frozen=True)
class Totals:
    subtotal: Money
    tax: Money
    total: Money
    #: Una entrada por tarifa presente, de menor a mayor. Siempre viene, aunque
    #: haya una sola: quien imprime decide si la muestra (RF-21 pide el desglose
    #: solo cuando hay más de una).
    by_rate: tuple[RateBucket, ...] = ()


def group_by_rate(
    lines: Iterable[tuple[Money, TaxRate | None]], default: TaxRate
) -> tuple[RateBucket, ...]:
    """Agrupa por tarifa y le calcula a cada grupo su impuesto.

    Recibe pares `(base, tarifa)` y no líneas, para que lo usen igual las ventas
    y las devoluciones sin que una tenga que conocer la forma de la otra. Una
    tarifa en `None` es «la del documento».

    **De menor a mayor tarifa**, para que el desglose salga siempre igual: en un
    documento impreso el orden no puede depender de en qué orden marcó el cajero.

    El impuesto de cada grupo es la **suma de los de sus líneas**, redondeados uno
    por uno, y no el de su base multiplicada de una vez. Ver `sale_totals` para el
    porqué, que es donde importa.
    """
    acumulado: dict[TaxRate, tuple[Money, Money]] = {}
    for base, rate in lines:
        efectiva = default if rate is None else rate
        acumulada, impuesto = acumulado.get(efectiva, (Money.zero(), Money.zero()))
        acumulado[efectiva] = (acumulada + base, impuesto + efectiva.apply(base))

    return tuple(
        RateBucket(rate=rate, base=base, tax=impuesto)
        for rate, (base, impuesto) in sorted(
            acumulado.items(), key=lambda par: par[0].value
        )
    )


def sale_totals(lines: list[SaleLine], default_rate: TaxRate) -> Totals:
    """
    Subtotal → impuesto → total, en ese orden.

    Desde F5 el impuesto es la **suma de los de cada línea** (RN-10) y no el
    subtotal por una tasa. Cada línea redondea el suyo, los grupos suman los de
    sus líneas y el documento suma los de sus grupos.

    **Por qué por línea y no por tarifa**, que era la otra opción y se descartó
    con las cifras delante:

    * `sale_details.tax_amount` tiene que **sumar exactamente** el impuesto del
      encabezado. Redondeando por tarifa, el impuesto del grupo es
      `round(base × tasa)` y la suma de sus líneas puede quedar un céntimo
      aparte: la factura no cuadraría consigo misma y un reporte que sume
      líneas contradiría el encabezado. Sumando líneas, cuadra por construcción.
    * Es la estructura del comprobante electrónico: Hacienda pide el impuesto
      **en cada línea** y un resumen que sea su suma, y valida esa igualdad.
    * **No cambia ninguna cifra de referencia**, y está medido: las cuatro de
      `progress.json` —4 915,50; 6 441,00; 5 796,90; 1 638,50— dan idéntico por
      las dos vías, porque los precios del catálogo son colones enteros. Las dos
      formas difieren en un céntimo en cerca del 39 % de las ventas con precios
      **con céntimos**, y en ninguna con precios enteros. Un céntimo es además lo
      que ya tolera `TOTALS_TOLERANCE` entre el POS y el servidor.

    Lo que **sí** se conserva de la versión anterior: se redondea línea por línea
    y no al final, igual que `CalculateTotalNew()` del original. Tres líneas de
    0,335 suman 1,01 redondeando cada una y 1,00 redondeando al final, y lo que
    el cajero ve en la pantalla son las líneas.
    """
    if not lines:
        raise EmptySale()

    by_rate = group_by_rate(((l.subtotal, l.tax_rate) for l in lines), default_rate)
    subtotal = Money.sum(grupo.base for grupo in by_rate)
    tax = Money.sum(grupo.tax for grupo in by_rate)
    return Totals(subtotal=subtotal, tax=tax, total=subtotal + tax, by_rate=by_rate)


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
    # Los nombres son los del API —'tax', no 'impuesto'—: viajan hasta el POS y
    # ahí se convierten en palabra, en el idioma que corresponda (RN-30).
    for campo, dicho, dado in (
        ("subtotal", declared.subtotal, computed.subtotal),
        ("tax", declared.tax, computed.tax),
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
