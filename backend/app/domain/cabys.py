"""
El código CABYS: qué es un código válido y qué tarifa le toca.

CABYS es el catálogo de bienes y servicios de Costa Rica. Cada artículo tiene un
código de **trece dígitos** y una tarifa de impuesto asociada, y esa tarifa es la
razón por la que el impuesto no puede ser un número global del negocio: la harina
de arroz va al 13 %, un medicamento al 2 % y un libro infantil al 0 %.

Acá no se habla con Hacienda ni se guarda nada: entran datos, salen reglas.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import DomainError
from .tax import TaxRate

#: Trece dígitos, ni uno más. Es la longitud del catálogo publicado.
CODE_LENGTH = 13


class InvalidCabysCode(DomainError):
    """Un código que el catálogo no podría tener."""

    def __init__(self, value: object, code: str) -> None:
        super().__init__(f"código CABYS no válido ({code}): {value!r}")
        self.value = value
        #: Qué tiene de malo, en código: 'empty', 'not_digits' o 'bad_length'.
        self.code = code


def normalize_code(raw: object) -> str:
    """El código limpio, o lanza.

    Se aceptan los espacios de alrededor —quien lo pega de una hoja de cálculo
    los arrastra— y nada más. En particular **no** se rellena con ceros a la
    izquierda: un código de doce dígitos no es uno de trece al que le falta algo,
    es un código mal copiado, y adivinar cuál era es peor que rechazarlo.
    """
    if not isinstance(raw, str):
        raise InvalidCabysCode(raw, "empty" if raw is None else "not_digits")

    limpio = raw.strip()
    if not limpio:
        raise InvalidCabysCode(raw, "empty")
    if not limpio.isdigit():
        raise InvalidCabysCode(raw, "not_digits")
    if len(limpio) != CODE_LENGTH:
        raise InvalidCabysCode(raw, "bad_length")
    return limpio


@dataclass(frozen=True)
class CabysCode:
    """Una entrada del catálogo: el código, qué es y cuánto paga."""

    code: str
    description: str
    tax_rate: TaxRate

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code))


def differs_from_official(chosen: TaxRate, official: TaxRate) -> bool:
    """Si la tarifa que puso el usuario no es la del catálogo (RN-11).

    Se puede cambiar —hay exoneraciones y casos especiales, y quien vende sabe
    de su negocio más que una tabla— pero **se le avisa**. El aviso no es un
    obstáculo: es lo que convierte un error de dedo en una decisión.
    """
    return chosen != official
