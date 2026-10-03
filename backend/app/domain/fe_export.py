"""
La factura de exportación: lo que una venta necesita para salir como FEE
(RF-78, RN-87, T-727).

Son tres cosas y las tres se comprueban **antes de cobrar**, porque descubrirlas
al transmitir es enterarse cuando el cliente ya se fue con el papel equivocado:

* **La partida arancelaria de cada mercancía.** El XSD 4.4 la define de doce
  dígitos exactos y la deja opcional porque los servicios no la llevan; el
  anexo la exige en las mercancías. Lo que distingue una de otro es el CABYS,
  igual que en el armador: los códigos que empiezan con 5 a 9 son servicios.
  Una línea sin CABYS cuenta como mercancía —es lo que vende un mostrador— y de
  todos modos se va a detener por el CABYS.
* **Una tarifa que la exportación admita.** La FEE no tiene balde de no sujeto
  (T-720): una línea con tarifa 01 u 11 desaparecería del resumen y el total
  dejaría de cuadrar. El código efectivo es el del producto o, si no tiene, el
  que se propone para su tarifa, que es lo mismo que hace el armador.
* **La dirección extranjera del cliente**, que ocupa el lugar de la ubicación
  del país en el receptor.

Nada de acá toca la base: entra lo que la venta ya leyó y sale un «sí» o el
error que dice qué falta y de cuál producto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable

from .errors import (
    ExportLineNeedsTariffHeading,
    ExportNeedsForeignAddress,
    ExportTariffNotAllowed,
    InvalidForeignAddress,
    InvalidTariffHeading,
)
from .fe_tax_codes import suggested_code
from .fe_xml import TARIFA_NO_SUJETA, is_merchandise
from .tax import TaxRate

#: Doce dígitos exactos (XSD 4.4, `PartidaArancelaria`).
TARIFF_HEADING_LENGTH: Final = 12

#: Lo que cabe en `OtrasSenasExtranjero` (XSD 4.4).
FOREIGN_ADDRESS_MAX_LENGTH: Final = 300


def check_tariff_heading(value: object) -> str | None:
    """La partida saneada, o nula si viene vacía: vacía es «no tiene», y eso
    no es un error al guardar el producto sino al exportarlo."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidTariffHeading(value)
    limpia = value.strip()
    if not limpia:
        return None
    if len(limpia) != TARIFF_HEADING_LENGTH or not limpia.isdigit():
        raise InvalidTariffHeading(value)
    return limpia


@dataclass(frozen=True)
class ExportLine:
    """Lo que de una línea decide si puede ir en una FEE."""

    product_id: int
    cabys_code: str | None
    tariff_heading: str | None
    tax_code: str | None
    tax_rate: TaxRate | None = None

    @property
    def effective_tax_code(self) -> str | None:
        """El código que va a llevar la línea: el suyo o el que se propone para
        su tarifa. Nulo es «no se sabe todavía», y eso lo detiene el armador."""
        if self.tax_code:
            return self.tax_code
        if self.tax_rate is None:
            return None
        return suggested_code(self.tax_rate)


def check_export_lines(lines: Iterable[ExportLine]) -> None:
    """Dice que no a la primera línea que no puede ir en una FEE, y por qué."""
    for line in lines:
        codigo = line.effective_tax_code
        if codigo in TARIFA_NO_SUJETA:
            raise ExportTariffNotAllowed(line.product_id, str(codigo))
        if is_merchandise(line.cabys_code) and not line.tariff_heading:
            raise ExportLineNeedsTariffHeading(line.product_id)


def normalize_foreign_address(address: object) -> str | None:
    """Las señas extranjeras como se guardan: limpias, nulas en blanco, y nunca
    más largas que el XML. Es la única política del largo: la ficha la rechaza
    y el comprobante no la recorta."""
    limpia = address.strip() if isinstance(address, str) else ""
    if not limpia:
        return None
    if len(limpia) > FOREIGN_ADDRESS_MAX_LENGTH:
        raise InvalidForeignAddress(len(limpia), FOREIGN_ADDRESS_MAX_LENGTH)
    return limpia


def check_foreign_address(client_id: int, address: object) -> str:
    """Las señas que la exportación exige del receptor (RF-78), o el «no»."""
    limpia = normalize_foreign_address(address)
    if limpia is None:
        raise ExportNeedsForeignAddress(client_id)
    return limpia


__all__ = [
    "FOREIGN_ADDRESS_MAX_LENGTH",
    "TARIFF_HEADING_LENGTH",
    "ExportLine",
    "check_export_lines",
    "check_foreign_address",
    "check_tariff_heading",
    "is_merchandise",
    "normalize_foreign_address",
]
