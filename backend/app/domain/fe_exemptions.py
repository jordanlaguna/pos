"""
La exoneración de un cliente (T-717, RF-67, RN-78).

**Son puntos de tarifa, no una tarifa.** Lo que el documento de exoneración
otorga es cuántos puntos se perdonan: una línea al 13 % con nueve puntos
exonerados paga 4 %. No existe ninguna tarifa del 9 %, así que modelarla como
tarifa da un total equivocado y un comprobante que no cuadra consigo mismo.

QUÉ SE GUARDA Y POR QUÉ CADA COSA
----------------------------------

Los siete campos son los que el XML pide y ninguno se puede deducir de otro:

* **tipo de documento** (nota 10.1): qué clase de autorización es. Cuatro de los
  doce solo valen en notas de crédito y de débito.
* **número**: el del documento, tal como lo emitió la institución.
* **institución** (nota 23): quién lo emitió. El `99` obliga a escribir cuál.
* **artículo e inciso**: obligatorios cuando el tipo remite a una ley.
* **fecha**: la de emisión del documento.
* **puntos**: cuántos puntos de tarifa se perdonan.

LO QUE HACIENDA COMPRUEBA Y ACÁ NO SE PUEDE
--------------------------------------------

Con los tipos `04` y `11` Hacienda valida contra su registro que el documento
exista, esté vigente y que los puntos no excedan los autorizados. Eso no se
puede replicar sin consultarle, así que lo que hace este módulo es lo otro: que
lo que se guarda tenga forma de exoneración. Lo demás llega como un rechazo
minutos después de emitir, con el cliente ya ido, y por eso conviene que la
pantalla lo advierta (T-717).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from .errors import DomainError


class InvalidExemption(DomainError):
    """Una exoneración que no se puede emitir, con el motivo como código."""

    def __init__(self, code: str, value: object = None) -> None:
        super().__init__(f"exoneración no válida ({code}): {value!r}")
        self.code = code
        self.value = value


@dataclass(frozen=True)
class TipoExoneracion:
    code: str
    #: Cuatro de los doce solo valen en notas de crédito y de débito.
    only_in_notes: bool = False
    #: Los que obligan a decir el artículo de la ley.
    needs_article: bool = False
    #: Los que Hacienda cruza contra su registro de exenciones.
    verified_by_hacienda: bool = False


#: La nota 10.1 del anexo v4.4, completa y en su orden.
DOCUMENT_TYPES: Final[dict[str, TipoExoneracion]] = {
    t.code: t
    for t in (
        TipoExoneracion("01", only_in_notes=True),
        TipoExoneracion("02", needs_article=True),
        TipoExoneracion("03", needs_article=True),
        TipoExoneracion("04", verified_by_hacienda=True),
        TipoExoneracion("05", only_in_notes=True),
        TipoExoneracion("06", only_in_notes=True, needs_article=True),
        TipoExoneracion("07", only_in_notes=True, needs_article=True),
        TipoExoneracion("08", needs_article=True),
        TipoExoneracion("09"),
        TipoExoneracion("10"),
        TipoExoneracion("11", verified_by_hacienda=True),
        TipoExoneracion("99"),
    )
}

#: La nota 23: quién emitió la exoneración. El `99` obliga a escribir cuál.
INSTITUTIONS: Final = (
    "01",  # Ministerio de Hacienda
    "02",  # Ministerio de Relaciones Exteriores y Culto
    "03",  # Ministerio de Agricultura y Ganadería
    "04",  # Ministerio de Economía, Industria y Comercio
    "05",  # Cruz Roja Costarricense
    "06",  # Benemérito Cuerpo de Bomberos
    "07",  # Asociación Obras del Espíritu Santo
    "08",  # Fecrunapa
    "09",  # EARTH
    "10",  # INCAE
    "11",  # Junta de Protección Social
    "12",  # Aresep
    "99",  # Otros
)

OTROS: Final = "99"

#: La tarifa exonerada es `decimal 4,2`: cuatro dígitos con dos decimales.
MAX_POINTS: Final = Decimal("99.99")

#: Los que solo valen en una nota de crédito o de débito.
ONLY_IN_NOTES: Final = tuple(c for c, t in DOCUMENT_TYPES.items() if t.only_in_notes)

#: Los que se le pueden poner a un cliente para facturarle.
SELLABLE_TYPES: Final = tuple(c for c, t in DOCUMENT_TYPES.items() if not t.only_in_notes)


@dataclass(frozen=True)
class Exemption:
    """La exoneración de un cliente, ya comprobada.

    Se valida al construirse, como `Ubicacion` y por lo mismo: una exoneración a
    medias no es válida en ningún contexto, y dejarla existir solo mueve el
    rechazo al momento de emitir.
    """

    document_type: str
    document_number: str
    institution: str
    date: str
    points: Decimal
    article: int | None = None
    subsection: int | None = None
    institution_other: str = ""

    def __post_init__(self) -> None:
        if self.document_type not in DOCUMENT_TYPES:
            raise InvalidExemption("unknown_document_type", self.document_type)
        if self.document_type in ONLY_IN_NOTES:
            # El 01, el 05, el 06 y el 07 corrigen facturas de cuando esas
            # exoneraciones regían. Ponérselos a un cliente para facturarle es
            # guardar un rechazo.
            raise InvalidExemption("document_type_only_in_notes", self.document_type)
        if not self.document_number.strip():
            raise InvalidExemption("missing_document_number")
        if self.institution not in INSTITUTIONS:
            raise InvalidExemption("unknown_institution", self.institution)
        if self.institution == OTROS and not self.institution_other.strip():
            raise InvalidExemption("missing_institution_name")
        if not self.date.strip():
            raise InvalidExemption("missing_date")
        if DOCUMENT_TYPES[self.document_type].needs_article and self.article is None:
            raise InvalidExemption("missing_article", self.document_type)
        if self.points <= 0 or self.points > MAX_POINTS:
            # Cero puntos no es una exoneración: es no tenerla, y guardarla así
            # dejaría un comprobante declarando un perdón de nada.
            raise InvalidExemption("points_out_of_range", str(self.points))

    @property
    def verified_by_hacienda(self) -> bool:
        """Si Hacienda va a cruzar este documento contra su registro.

        Con los tipos `04` y `11` comprueba que exista, esté vigente y que los
        puntos no excedan los autorizados. No se puede comprobar acá; lo que sí
        se puede es avisar de que el rechazo va a llegar después.
        """
        return DOCUMENT_TYPES[self.document_type].verified_by_hacienda


def check_document_type(value: object) -> str:
    if value not in DOCUMENT_TYPES:
        raise InvalidExemption("unknown_document_type", value)
    return str(value)


def check_institution(value: object) -> str:
    if value not in INSTITUTIONS:
        raise InvalidExemption("unknown_institution", value)
    return str(value)


def needs_article(document_type: object) -> bool:
    """Si ese tipo obliga a decir el artículo de la ley."""
    return DOCUMENT_TYPES[check_document_type(document_type)].needs_article


__all__ = [
    "DOCUMENT_TYPES",
    "INSTITUTIONS",
    "MAX_POINTS",
    "ONLY_IN_NOTES",
    "OTROS",
    "SELLABLE_TYPES",
    "Exemption",
    "InvalidExemption",
    "TipoExoneracion",
    "check_document_type",
    "check_institution",
    "needs_article",
]
