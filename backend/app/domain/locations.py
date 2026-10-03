"""
La ubicación del emisor con los códigos de Hacienda (T-722, RN-83).

El XML del comprobante no lleva una dirección: lleva **provincia, cantón y
distrito numerados** —un dígito, dos y dos, de la nota 14 del anexo— y las
**otras señas** en texto. Hacienda los cruza contra el Registro Único
Tributario, así que una frase como «San José, 200 m sur del parque» no sirve
aunque diga lo mismo.

Dos cosas que no son lo que parecen, y las dos salieron del XSD y del anexo:

* **Las otras señas son lo obligatorio y el barrio lo opcional.** En la 4.4 el
  barrio dejó de ser un código: es texto libre, de 5 a 50 caracteres.
* **Un código solo vale dentro de su padre.** El cantón «02» existe en las siete
  provincias y es un lugar distinto en cada una; lo que se valida es el par, y
  el distrito, el trío.

La dirección de texto libre de Configuración sigue existiendo y se sigue
imprimiendo en el tiquete: son dos datos para dos lectores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import InvalidLocation
from .locations_data import CANTONS, DISTRICTS, PROVINCES

#: Los largos del anexo (p. 21). Por debajo de cinco, Hacienda rechaza.
NEIGHBORHOOD_MIN: Final = 5
NEIGHBORHOOD_MAX: Final = 50
OTHER_SIGNS_MIN: Final = 5
OTHER_SIGNS_MAX: Final = 250


@dataclass(frozen=True)
class Location:
    """Una ubicación que Hacienda acepta. Solo la construye `check_location`."""

    province: str
    canton: str
    district: str
    other_signs: str
    neighborhood: str = ""

    @property
    def names(self) -> tuple[str, str, str]:
        """Provincia, cantón y distrito con su nombre, para imprimirlos."""
        return (
            PROVINCES[self.province],
            CANTONS[self.province][self.canton],
            DISTRICTS[f"{self.province}-{self.canton}"][self.district],
        )


def _codigo(field: str, value: object, digits: int) -> str:
    """El código con sus ceros: «1» es el cantón «01».

    Acepta un número porque así lo guarda un JSON escrito a mano, pero no un
    booleano, que en Python también es un entero.
    """
    if value is None or isinstance(value, bool):
        raise InvalidLocation(field, "required", value)
    texto = str(value).strip()
    if not texto:
        raise InvalidLocation(field, "required", value)
    if not texto.isascii() or not texto.isdigit() or len(texto.lstrip("0") or "0") > digits:
        raise InvalidLocation(field, "unknown", value)
    return texto.zfill(digits)[-digits:]


def _texto(field: str, value: object, minimo: int, maximo: int, *, required: bool) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InvalidLocation(field, "unknown", value)
    limpio = " ".join(value.split())
    if not limpio:
        if required:
            raise InvalidLocation(field, "required", value)
        return ""
    if len(limpio) < minimo:
        raise InvalidLocation(field, "too_short", value)
    if len(limpio) > maximo:
        raise InvalidLocation(field, "too_long", value)
    return limpio


def check_location(
    *,
    province: object,
    canton: object,
    district: object,
    other_signs: object,
    neighborhood: object = None,
) -> Location:
    """La ubicación, o `InvalidLocation` con el primer campo que falla.

    En el orden de la pantalla: primero la provincia, porque sin ella el cantón
    no se puede juzgar.
    """
    provincia = _codigo("province", province, 1)
    if provincia not in PROVINCES:
        raise InvalidLocation("province", "unknown", province)

    canton_ = _codigo("canton", canton, 2)
    if canton_ not in CANTONS[provincia]:
        raise InvalidLocation("canton", "unknown", canton)

    distrito = _codigo("district", district, 2)
    if distrito not in DISTRICTS[f"{provincia}-{canton_}"]:
        raise InvalidLocation("district", "unknown", district)

    barrio = _texto(
        "neighborhood", neighborhood, NEIGHBORHOOD_MIN, NEIGHBORHOOD_MAX, required=False
    )
    senas = _texto("other_signs", other_signs, OTHER_SIGNS_MIN, OTHER_SIGNS_MAX, required=True)

    return Location(
        province=provincia,
        canton=canton_,
        district=distrito,
        other_signs=senas,
        neighborhood=barrio,
    )


def location_from_settings(raw: object) -> Location:
    """La ubicación tal como la guarda Configuración, en `business.location`.

    Las llaves son las del JSON del POS —`otherSigns` en camelCase, como el resto
    de la configuración—. Algo que no es un objeto es una ubicación que falta.
    """
    if not isinstance(raw, dict):
        raise InvalidLocation("province", "required", raw)
    return check_location(
        province=raw.get("province"),
        canton=raw.get("canton"),
        district=raw.get("district"),
        other_signs=raw.get("otherSigns"),
        neighborhood=raw.get("neighborhood"),
    )


def is_blank(raw: object) -> bool:
    """Si la ubicación está vacía del todo: nadie empezó a llenarla.

    Es distinto de una a medias. La vacía se guarda —la compañía que no emite no
    tiene por qué dar su distrito—; la a medias es un error de quien escribe y se
    le dice cuál campo falta.
    """
    if raw is None:
        return True
    if not isinstance(raw, dict):
        return False
    return all(
        v is None or (isinstance(v, str) and not v.strip())
        for v in (
            raw.get("province"),
            raw.get("canton"),
            raw.get("district"),
            raw.get("otherSigns"),
            raw.get("neighborhood"),
        )
    )
