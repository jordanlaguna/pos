"""
Los códigos de sucursal y de terminal (T-608b, RN-15).

Son dos números con ceros a la izquierda —tres dígitos la sucursal, cinco la
terminal— y **no son un `String` cualquiera**: van dentro de la clave de 50
dígitos del comprobante, en posiciones fijas. Un código de dos dígitos corre
todo lo que viene detrás, y eso no lo descubre el sistema sino Hacienda, al
rechazar la factura con el cliente enfrente.

**«1» se guarda como «001», y esa es la mitad del valor de este módulo.** Quien
da de alta una sucursal escribe el número que tiene en la cabeza; rellenar es lo
que evita que la caja 1 y la caja 001 sean dos filas distintas —el UNIQUE es
sobre el texto—.

El precedente es `Barcode`: un tipo, sin dependencias, con su prueba. La
diferencia es que acá el valor **se normaliza** en vez de solo recortarse, y por
eso importa que exista un solo sitio donde se hace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import InvalidOfficeCode

#: Los que fija Hacienda. No se configuran: son parte del formato de la clave.
BRANCH_DIGITS: Final = 3
TERMINAL_DIGITS: Final = 5


def _normalizar(value: object, digits: int) -> str:
    if not isinstance(value, str) and not isinstance(value, int):
        raise InvalidOfficeCode(value, "not_text", digits)
    # Un booleano es un `int` en Python y `True` daría «001». No es un código.
    if isinstance(value, bool):
        raise InvalidOfficeCode(value, "not_text", digits)

    limpio = str(value).strip()
    if not limpio:
        raise InvalidOfficeCode(value, "empty", digits)
    if not limpio.isdigit():
        # `isdigit()` acepta dígitos de otros alfabetos —«٣» es un tres árabe— y
        # eso es lo correcto acá: lo que sigue es `zfill` sobre el texto tal
        # cual, así que el valor guardado sería el que se escribió. Lo que se
        # rechaza es lo que de verdad rompe: letras, signos, espacios adentro.
        raise InvalidOfficeCode(value, "not_digits", digits)
    if len(limpio.lstrip("0") or "0") > digits:
        # Se miden los dígitos **significativos**: «00001» con tres dígitos es 1
        # y cabe; «1234» no cabe de ninguna manera. Recortar en silencio sería
        # cambiarle el número a alguien.
        raise InvalidOfficeCode(value, "too_long", digits)

    return limpio.zfill(digits)[-digits:]


@dataclass(frozen=True, order=True)
class BranchCode:
    """Tres dígitos. La oficina, en el vocabulario de Hacienda."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalizar(self.value, BRANCH_DIGITS))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class TerminalCode:
    """Cinco dígitos. La caja."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalizar(self.value, TERMINAL_DIGITS))

    def __str__(self) -> str:
        return self.value
