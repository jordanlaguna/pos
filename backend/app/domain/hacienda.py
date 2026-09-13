"""
Todo lo que el dominio sabe de Hacienda, en un solo sitio (T-613, plan §7.1).

**Por qué un módulo y no las constantes donde hagan falta**: TRIBU-CR reemplaza
a ATV desde octubre de 2025 y `docs/hacienda/costa-rica/README.md` §12 deja
pendiente confirmar si cambia URLs o credenciales. Con el dominio de Hacienda
repartido por el código, ese cambio es una cacería; con un módulo, es una tabla.
Hay una prueba que tumba `pytest` si `comprobanteselectronicos.go.cr` aparece
escrito fuera de acá — el mismo patrón que ya sostiene `test_error_codes.py`.

Y **las funciones son puras**: reciben el ambiente y devuelven datos. Lo que
lee el entorno es el adaptador, que le pasa lo que encuentre; así la derivación
se prueba sin variables de entorno y sin red.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Mapping

from .errors import (
    InvalidEnvironment,
    InvalidIdentificationType,
    InvalidSigningKey,
)

# ------------------------------------------------------------------ ambientes

SANDBOX: Final = "sandbox"
PRODUCTION: Final = "production"

#: En inglés y no en español (plan §3.9), y `'sandbox'` además es el valor que
#: el POS ya publica hoy en `settings.eInvoicing.environment`. Tener dos vocablos
#: para el mismo estado es cómo se pierde una migración.
ENVIRONMENTS: Final = (SANDBOX, PRODUCTION)


def check_environment(value: object) -> str:
    """El ambiente, o `InvalidEnvironment`."""
    if value not in ENVIRONMENTS:
        raise InvalidEnvironment(value)
    return str(value)


# ------------------------------------------------------- dónde vive Hacienda


@dataclass(frozen=True)
class HaciendaEndpoints:
    """Con quién se habla para transmitir, en un ambiente.

    `client_id` y `realm` van separados aunque el realm ya esté dentro de
    `idp_url`: el realm se manda también en el cuerpo de algunas peticiones, y
    sacarlo de la URL con un `split` sería fabricar un acoplamiento entre dos
    datos que Hacienda publica por separado.
    """

    api_url: str
    idp_url: str
    client_id: str
    realm: str


#: El servidor de Hacienda. Uno solo: el sandbox NO está en otra máquina, es la
#: misma con otra ruta (`recepcion-sandbox`), y eso es lo que se escribe mal de
#: memoria.
_HOST: Final = "comprobanteselectronicos.go.cr"


def _idp(realm: str) -> str:
    """La URL del token a partir del realm.

    Se construye y no se escribe porque el realm aparecía **dos veces** —en su
    campo y dentro de la URL— y dos copias de un dato es cómo se desincronizan.
    Lo encontró el guardián de este mismo módulo al no poder hallar `/realms/rut`
    en el texto: estaba partido entre dos literales.
    """
    return f"https://idp.{_HOST}/auth/realms/{realm}/protocol/openid-connect/token"


#: Lo publicado en `docs/hacienda/costa-rica/README.md` §7 y §12, verificado el
#: 2026-09-13.
_PUBLICADOS: Final[dict[str, HaciendaEndpoints]] = {
    SANDBOX: HaciendaEndpoints(
        api_url=f"https://api.{_HOST}/recepcion-sandbox/v1/",
        idp_url=_idp("rut-stag"),
        client_id="api-stag",
        realm="rut-stag",
    ),
    PRODUCTION: HaciendaEndpoints(
        api_url=f"https://api.{_HOST}/recepcion/v1/",
        idp_url=_idp("rut"),
        client_id="api-prod",
        realm="rut",
    ),
}

#: Los campos que un despliegue puede cambiar sin tocar el código. Es la lista
#: entera a propósito: el día que TRIBU-CR mueva algo, lo que hay que poder
#: hacer es apuntar a otro lado ese mismo día, no esperar una versión.
OVERRIDABLE: Final = ("api_url", "idp_url", "client_id", "realm")


def endpoints(
    environment: str, overrides: Mapping[str, str] | None = None
) -> HaciendaEndpoints:
    """Dónde vive Hacienda para ese ambiente, con lo que el despliegue cambie.

    Un `override` vacío o en blanco **no cuenta**: una variable de entorno
    declarada y sin valor es lo normal en un `.env` copiado del ejemplo, y
    dejarla pisar el valor bueno convertiría el arranque en «no encuentra a
    Hacienda» sin ninguna pista de por qué.
    """
    base = _PUBLICADOS[check_environment(environment)]
    if not overrides:
        return base

    cambios = {
        campo: valor.strip()
        for campo, valor in overrides.items()
        if campo in OVERRIDABLE and valor and valor.strip()
    }
    return replace(base, **cambios) if cambios else base


# ---------------------------------------------------- la llave de la firma


def signing_key_name(company_id: int, environment: str) -> str:
    """Cómo se llama en Vault la llave con la que firma esta compañía.

    **Se deriva, no se guarda.** Un campo escribible con este nombre dejaría que
    el administrador de la compañía 7 apuntara a la llave de la 3 y emitiera
    documentos fiscales firmados con el certificado de otro cliente. Es la misma
    frase que rige el dato asociado del AES-GCM y la ruta del almacén: la
    identidad la fija el servidor.
    """
    if not isinstance(company_id, int) or isinstance(company_id, bool) or company_id <= 0:
        raise InvalidSigningKey(company_id)
    return f"fe-{company_id}-{check_environment(environment)}"


# ------------------------------------------------- tipos de identificación


#: Los cuatro de Hacienda. Física, jurídica, DIMEX (residencia) y NITE.
IDENTIFICATION_TYPES: Final = ("01", "02", "03", "04")

PHYSICAL: Final = "01"
LEGAL: Final = "02"
DIMEX: Final = "03"
NITE: Final = "04"


def check_identification_type(value: object) -> str:
    if value not in IDENTIFICATION_TYPES:
        raise InvalidIdentificationType(value)
    return str(value)


def identification_type_for(identification: str) -> str | None:
    """El tipo que deja ver la longitud de la cédula, o `None`.

    Es lo único que se puede saber sin preguntarle a nadie, y por eso existe:
    los clientes que ya estaban en la base no tienen a quién preguntarle.

    **El 04 (NITE) también son diez dígitos** y no hay forma de distinguirlo del
    02 mirando el número. Se devuelve jurídica porque es órdenes de magnitud más
    común; quien tenga un NITE lo corrige una vez. Devolver `None` ahí sería más
    honesto y dejaría a todos los clientes de empresa sin tipo el día de
    facturar, que es peor.

    `None` es «no se sabe», y es distinto de un tipo equivocado: quien lo reciba
    tiene que preguntar, no adivinar.
    """
    if not isinstance(identification, str):
        return None

    digitos = "".join(c for c in identification if c.isdigit())
    if len(digitos) == 9:
        return PHYSICAL
    if len(digitos) == 10:
        return LEGAL
    if len(digitos) in (11, 12):
        return DIMEX
    return None
