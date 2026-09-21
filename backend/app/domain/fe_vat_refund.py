"""
El IVA devuelto de los servicios de salud (T-718, RF-68, RN-79).

QUÉ ES Y QUÉ NO ES
-------------------

No es una exoneración ni un descuento: **el impuesto se cobra**. Lo que el campo
declara es cuánto de ese impuesto le devuelve el Estado a quien pagó con
tarjeta un servicio de salud privado, y por eso `TotalComprobante` lo resta. El
paciente paga 100 000, el comprobante declara 4 000 de IVA y 4 000 de IVA
devuelto, y el total es 100 000.

Hacienda lo valida cruzando dos cosas: que las líneas sean de servicios médicos
y que el medio de pago sea tarjeta. Si el monto no corresponde, **rechaza el
comprobante** (anexo p. 54).

QUÉ CABYS SON SERVICIOS DE SALUD
---------------------------------

Hacienda no publica esa lista como archivo; publica el catálogo CABYS, donde la
división **93** es «servicios de salud humana y de asistencia social» y el grupo
**931** los servicios de salud humana propiamente dichos —el ejemplo real de
`docs/…/protocolos/` factura un `9310100000100`—.

Se usa el grupo `931` y no la división entera: `932` es atención residencial y
`933` asistencia social, que no son el servicio médico del que habla la ley.
Está en una constante y no repartido por el código a propósito: el día que
Hacienda publique su lista, lo que cambia es esta línea.

EL PRORRATEO, QUE ES LA PARTE QUE SE OLVIDA
--------------------------------------------

El campo es el impuesto pagado **en tarjeta**, no el impuesto de las líneas de
salud. Con un pago mixto —la mitad en efectivo y la mitad con tarjeta— solo se
devuelve la mitad, y declararlo entero es un rechazo. Con un solo medio de pago
la proporción es 1 o 0 y el prorrateo no se nota; existe para cuando no lo es.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Iterable

from .fe_payment_methods import CARD

#: El grupo del CABYS que son servicios de salud humana.
HEALTH_PREFIX: Final = "931"

_CENTAVOS = Decimal("0.00001")


def is_health_service(cabys: object) -> bool:
    """Si ese código del catálogo es un servicio de salud."""
    return isinstance(cabys, str) and cabys.strip().startswith(HEALTH_PREFIX)


@dataclass(frozen=True)
class TaxedLine:
    """Lo único que hace falta de una línea para decidir: su CABYS y su impuesto."""

    cabys: str
    tax: Decimal


@dataclass(frozen=True)
class Payment:
    """Un medio de pago con su monto, ya en el código de Hacienda."""

    code: str
    amount: Decimal


def card_share(payments: Iterable[Payment]) -> Decimal:
    """Qué proporción del cobro se hizo con tarjeta, entre 0 y 1.

    Sin pagos declarados la proporción es cero y no uno: una venta a crédito no
    se pagó con tarjeta, se pagará; el recibo de pago dirá con qué.
    """
    montos = [p.amount for p in payments]
    total = sum(montos, Decimal(0))
    if total <= 0:
        return Decimal(0)
    con_tarjeta = sum((p.amount for p in payments if p.code == CARD), Decimal(0))
    return con_tarjeta / total


def vat_refund(lines: Iterable[TaxedLine], payments: Iterable[Payment]) -> Decimal:
    """El IVA devuelto del comprobante. Cero cuando no aplica.

    Cero y no `None`: el armador no emite el campo cuando vale cero, que es
    exactamente lo que Hacienda espera de una venta que no es de salud o que no
    se pagó con tarjeta.
    """
    pagos = list(payments)
    impuesto_de_salud = sum(
        (linea.tax for linea in lines if is_health_service(linea.cabys)), Decimal(0)
    )
    if impuesto_de_salud <= 0:
        return Decimal(0)
    return (impuesto_de_salud * card_share(pagos)).quantize(
        _CENTAVOS, rounding=ROUND_HALF_UP
    )


__all__ = [
    "HEALTH_PREFIX",
    "Payment",
    "TaxedLine",
    "card_share",
    "is_health_service",
    "vat_refund",
]
