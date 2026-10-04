"""
Lo que el emisor tiene que tener para poder emitir (T-722, RN-83, RN-45).

Son tres datos y cada uno falla en un sitio distinto si falta:

* **La identificación** va dentro de la clave, en las posiciones 10 a 21. Sin
  ella no hay comprobante que numerar. Es la de `companies`, la del certificado
  (RN-45), no la que se escribe en Configuración.
* **El correo** es obligatorio en el `Emisor` de todos los comprobantes: el XSD
  no lo deja vacío.
* **La ubicación** codificada (`locations.py`), por lo mismo.

Se revisan **al encender** la factura electrónica y no al vender: una venta que
se rechaza en el mostrador por un dato de Configuración le cobra el problema al
cliente que está esperando. Encenderla sin esto es lo que se impide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .errors import (
    EInvoicingNeedsIssuer,
    InvalidIdentificationType,
    InvalidLocation,
    IssuerIdentificationRequired,
)
from .fe_key import ISSUER_DIGITS
from .hacienda import ISSUER_IDENTIFICATION_TYPES, client_identification_type
from .locations import is_blank, location_from_settings

#: El largo del XSD para `CorreoElectronico`.
EMAIL_MAX: Final = 160

# Lo que tiene que tener un correo para que alguien lo reciba: algo, una arroba,
# un dominio con punto. No es la gramática entera del RFC 5322 —nadie la cumple
# de verdad— sino la que ya aplica el formulario del POS.
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value.strip()) <= EMAIL_MAX
        and _CORREO.match(value.strip()) is not None
    )


def missing_for_einvoicing(
    *, identification: object, email: object, location: object
) -> tuple[str, ...]:
    """Lo que falta para emitir, en el orden en que se le dice a la persona.

    Una ubicación a medias cuenta como que falta: el XML la pide entera.
    """
    faltan: list[str] = []
    if not isinstance(identification, str) or not any(c.isdigit() for c in identification):
        faltan.append("identification")
    if not is_valid_email(email):
        faltan.append("email")
    if is_blank(location):
        faltan.append("location")
    else:
        try:
            location_from_settings(location)
        except InvalidLocation:
            faltan.append("location")
    return tuple(faltan)


def check_ready_to_emit(*, identification: object, email: object, location: object) -> None:
    """Lanza `EInvoicingNeedsIssuer` con la lista entera, no con el primero.

    Quien enciende la facturación tiene que ver todo lo que le falta de una vez,
    no descubrirlo de a uno guardando tres veces.
    """
    faltan = missing_for_einvoicing(identification=identification, email=email, location=location)
    if faltan:
        raise EInvoicingNeedsIssuer(faltan)


@dataclass(frozen=True)
class IssuerIdentity:
    """La cédula del emisor como se guarda en `companies`: solo dígitos, con tipo."""

    identification: str
    identification_type: str


#: De nueve —la física— a doce —el DIMEX largo—. La jurídica y el NITE son diez.
ISSUER_ID_MIN: Final = 9


def check_issuer_identity(identification: object, identification_type: object) -> IssuerIdentity:
    """La identificación que soporte le fija a una compañía (RN-45, T-621).

    Se guarda **sin guiones**, que es como va en la clave y en el XML: un
    «3-101-702934» guardado así obligaría a limpiarlo cada vez que se usa, y el
    día que alguien se olvide sale una clave corrida. El tipo, si no se da, es
    el que deja ver la longitud (`client_identification_type`, la misma regla
    que los clientes).
    """
    if not isinstance(identification, str) or not identification.strip():
        raise IssuerIdentificationRequired("missing")
    digitos = "".join(c for c in identification if c not in "- \t")
    if (
        not digitos.isascii()
        or not digitos.isdigit()
        or not ISSUER_ID_MIN <= len(digitos) <= ISSUER_DIGITS
    ):
        raise IssuerIdentificationRequired("invalid")
    tipo = client_identification_type(identification_type, digitos)
    # Los seis tipos son de clientes y proveedores; quien emite tiene cédula del
    # país y está inscrito (T-727). Un emisor «extranjero no domiciliado» firmaría
    # claves que Hacienda rechaza.
    if tipo not in ISSUER_IDENTIFICATION_TYPES:
        raise InvalidIdentificationType(tipo)
    return IssuerIdentity(identification=digitos, identification_type=tipo)
