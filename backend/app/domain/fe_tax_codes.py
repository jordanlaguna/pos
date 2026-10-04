"""
El código de tarifa del IVA de Hacienda (nota 8.1 del anexo v4.4, RN-76).

**Once códigos para nueve porcentajes.** El catálogo no es una lista de tasas:
es una lista de *situaciones*, y dos situaciones distintas pueden cobrar lo
mismo. El 0 % del artículo 32 del reglamento —ventas a la CCSS, a una
municipalidad— da **derecho a crédito pleno**; el 0 % del código 11 no da
ninguno. Los dos multiplican por cero y significan cosas opuestas.

Por eso el código es el dato y la tarifa se deriva, nunca al revés:

* de un código sale siempre una tarifa (`rate_for`),
* de una tarifa **no siempre** sale un código (`suggested_code` devuelve `None`
  cuando hay más de uno, que es justo en el 0 %).

LOS TRANSITORIOS NO SON PARA VENDER
------------------------------------

Los códigos 05, 06 y 07 —0 %, 4 % y 8 %— existen solo para corregir con una nota
de crédito o de débito una factura emitida cuando esas tarifas regían. Usarlos
en una venta de hoy es un rechazo. `only_in_notes` los marca, y por eso
`suggested_code` no los propone jamás: el 8 % **solo** existe como transitorio,
así que una tarifa del 8 % no tiene código que proponer fuera de una nota.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from .errors import DomainError
from .tax import TaxRate


class InvalidTaxCode(DomainError):
    """Un código de tarifa que no está en la nota 8.1."""

    def __init__(self, value: object) -> None:
        super().__init__(f"código de tarifa no válido: {value!r}")
        self.value = value


@dataclass(frozen=True)
class TarifaIVA:
    """Una fila de la nota 8.1."""

    code: str
    rate: TaxRate
    #: Los transitorios solo valen en notas de crédito y de débito.
    only_in_notes: bool = False


def _fila(code: str, percent: str, only_in_notes: bool = False) -> TarifaIVA:
    return TarifaIVA(code, TaxRate.percent(Decimal(percent)), only_in_notes)


#: La nota 8.1 completa, en su orden.
CODES: Final[dict[str, TarifaIVA]] = {
    fila.code: fila
    for fila in (
        _fila("01", "0"),  # art. 32 num 1 RLIVA: 0 % con derecho a crédito pleno
        _fila("02", "1"),
        _fila("03", "2"),
        _fila("04", "4"),  # la de los servicios de salud privados
        _fila("05", "0", only_in_notes=True),
        _fila("06", "4", only_in_notes=True),
        _fila("07", "8", only_in_notes=True),
        _fila("08", "13"),  # la general
        _fila("09", "0.5"),
        _fila("10", "0"),  # exenta, ley 9635 art. 8
        _fila("11", "0"),  # no sujeta, sin derecho a crédito
    )
}

#: La general. Es la que se propone cuando nadie dice otra cosa.
GENERAL: Final = "08"
#: 0 % con derecho a crédito pleno (CCSS, municipalidades).
CERO_CON_CREDITO: Final = "01"
EXENTA: Final = "10"
NO_SUJETA: Final = "11"

#: Los que solo valen en una nota de crédito o de débito.
ONLY_IN_NOTES: Final = tuple(c for c, fila in CODES.items() if fila.only_in_notes)


def check_code(value: object) -> str:
    """El código, o `InvalidTaxCode`.

    Se aceptan los espacios de alrededor y nada más. En particular **no** se
    rellena con un cero a la izquierda: un `"8"` puede ser el 08 general o un
    dedazo, y adivinar cuál era es peor que rechazarlo.
    """
    if not isinstance(value, str):
        raise InvalidTaxCode(value)
    limpio = value.strip()
    if limpio not in CODES:
        raise InvalidTaxCode(value)
    return limpio


def rate_for(code: object) -> TaxRate:
    """La tarifa de ese código. De acá sale el porcentaje, no al revés."""
    return CODES[check_code(code)].rate


def only_in_notes(code: object) -> bool:
    """Si ese código solo vale en una nota de crédito o de débito."""
    return CODES[check_code(code)].only_in_notes


def codes_for(rate: TaxRate) -> tuple[str, ...]:
    """Todos los códigos que cobran esa tarifa, transitorios incluidos."""
    return tuple(code for code, fila in CODES.items() if fila.rate == rate)


def purchase_line_code(product_code: object, rate: TaxRate) -> str | None:
    """El código de una línea de compra (T-728, RN-53).

    La tarifa es la del documento del proveedor; el código es el del producto
    si dice esa misma tarifa —es lo que el negocio ya decidió sobre ese
    artículo— y, si no, el que se propone para ella. En el 0 % eso es `None`,
    por lo mismo que en `suggested_code`: nadie adivina el derecho a crédito.
    """
    if product_code in CODES and rate_for(product_code).value == rate.value:
        return str(product_code)
    return suggested_code(rate)


def suggested_code(rate: TaxRate) -> str | None:
    """El código que se propone para una tarifa, o `None` si hay más de uno.

    `None` es «hay que preguntar», y es la respuesta correcta en el 0 %: entre
    el 01, el 10 y el 11 no decide la aritmética sino qué se está vendiendo y a
    quién. Proponer uno sería elegir por quien factura el derecho a crédito de
    su cliente.
    """
    posibles = [c for c in codes_for(rate) if not CODES[c].only_in_notes]
    return posibles[0] if len(posibles) == 1 else None


__all__ = [
    "CERO_CON_CREDITO",
    "CODES",
    "EXENTA",
    "GENERAL",
    "NO_SUJETA",
    "ONLY_IN_NOTES",
    "InvalidTaxCode",
    "TarifaIVA",
    "check_code",
    "codes_for",
    "purchase_line_code",
    "only_in_notes",
    "rate_for",
    "suggested_code",
]
