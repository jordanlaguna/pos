"""
El código de barras.

Lo escribe un lector láser, no una persona: llega siempre como una tira de
caracteres imprimibles seguida de un Enter. Por eso el tipo recorta los espacios
de los bordes pero rechaza los de adentro —un código con un espacio en medio son
dos lecturas pegadas, y buscar por él no encuentra nada—.

No se valida el dígito de control de EAN-13 a propósito: el catálogo tiene
códigos internos del negocio, impresos con la etiquetadora del mostrador, que no
son EAN y no tienen por qué serlo.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidBarcode

#: La columna de la base es `VARCHAR(50)`. Cortar en silencio convertiría dos
#: productos distintos en el mismo.
MAX_LENGTH = 50


@dataclass(frozen=True, order=True)
class Barcode:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidBarcode(self.value, "no es texto")

        limpio = self.value.strip()
        if not limpio:
            raise InvalidBarcode(self.value, "vacío")
        if len(limpio) > MAX_LENGTH:
            raise InvalidBarcode(self.value, f"más de {MAX_LENGTH} caracteres")
        if any(c.isspace() for c in limpio):
            raise InvalidBarcode(self.value, "tiene espacios en medio")
        if not limpio.isprintable():
            raise InvalidBarcode(self.value, "tiene caracteres de control")

        object.__setattr__(self, "value", limpio)

    def __str__(self) -> str:
        return self.value
