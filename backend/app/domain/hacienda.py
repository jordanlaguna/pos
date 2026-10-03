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
    IdentificationTypeRequired,
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


def needs_confirmation(target: object) -> bool:
    """Si pasar a ese ambiente hay que confirmarlo (RN-35, T-611).

    **Solo producción.** Es el momento en que los documentos dejan de ser un
    ensayo y pasan a tener efecto fiscal, y RN-35 dice que no puede ocurrir por
    haber tocado un desplegable sin querer.

    Volver a pruebas **no** se confirma y sí se registra, y la asimetría es a
    propósito: exigir confirmación para deshacer convierte la salida de un error
    en un segundo trámite, justo cuando alguien acaba de darse cuenta de que
    emitió en el ambiente equivocado. Que quede en bitácora es lo que hace que
    el cambio no pase inadvertido, que es lo que de verdad importa de ese lado.
    """
    return check_environment(target) == PRODUCTION


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


#: El dominio de Hacienda. La recepción de pruebas está en **otro servidor**
#: (`api-sandbox.`), con la misma ruta que la de producción.
#:
#: Hasta el 2026-10-03 decía lo contrario —«el sandbox es la misma máquina con
#: otra ruta, `api.…/recepcion-sandbox/v1/`»—, copiado del README de `docs/`.
#: Esa ruta ya no existe: el Gateway de AWS que está delante contesta **403**
#: `IncompleteSignatureException` a cualquier token, y la cola lo leía como
#: «credenciales sin permiso». Se comprobó consultando la misma clave en las
#: dos: `api-sandbox.…/recepcion/v1/` contesta Hacienda («no ha sido
#: recibido»), la otra el Gateway.
_HOST: Final = "comprobanteselectronicos.go.cr"


def _idp(realm: str) -> str:
    """La URL del token a partir del realm.

    Se construye y no se escribe porque el realm aparecía **dos veces** —en su
    campo y dentro de la URL— y dos copias de un dato es cómo se desincronizan.
    Lo encontró el guardián de este mismo módulo al no poder hallar `/realms/rut`
    en el texto: estaba partido entre dos literales.
    """
    return f"https://idp.{_HOST}/auth/realms/{realm}/protocol/openid-connect/token"


#: Lo publicado en `docs/hacienda/costa-rica/README.md` §7 y §12. El IdP de los
#: dos y la recepción de producción, verificados el 2026-09-13; la recepción
#: del sandbox, corregida y verificada el 2026-10-03 (ver `_HOST`).
_PUBLICADOS: Final[dict[str, HaciendaEndpoints]] = {
    SANDBOX: HaciendaEndpoints(
        api_url=f"https://api-sandbox.{_HOST}/recepcion/v1/",
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


#: La política de firma XAdES-EPES de la 4.4 (README §6), tal como la escribe
#: el comprobante aceptado: con los acentos codificados por ciento. El resumen
#: es el del PDF que publica Hacienda; si Hacienda cambia el PDF hay que volver a
#: calcularlo, y mientras tanto todo comprobante se rechaza por política. Viven
#: acá y no en el firmante por lo mismo que las URLs: son quién es Hacienda.
SIGNATURE_POLICY_ID: Final = (
    f"https://cdn.{_HOST}/xml-schemas/"
    "Resoluci%C3%B3n_General_sobre_disposiciones_t%C3%A9cnicas_comprobantes_"
    "electr%C3%B3nicos_para_efectos_tributarios.pdf"
)
SIGNATURE_POLICY_HASH: Final = "DWxin1xWOeI8OuWQXazh4VjLWAaCLAA954em7DMh0h8="

#: El espacio de nombres de cada tipo de comprobante, por su código en el
#: consecutivo (nota 3 del anexo).
#:
#: Viven **acá y no en el armador** por lo mismo que las URLs de arriba: son
#: quién es Hacienda, y el guardián de este módulo tumba `pytest` si aparecen en
#: otro archivo. No son configurables como las demás: un espacio de nombres
#: identifica una versión del esquema, así que moverlo no es apuntar a otro
#: servidor sino emitir otra cosa.
_ESQUEMAS: Final = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4"

NAMESPACES: Final[dict[str, str]] = {
    "01": f"{_ESQUEMAS}/facturaElectronica",
    "02": f"{_ESQUEMAS}/notaDebitoElectronica",
    "03": f"{_ESQUEMAS}/notaCreditoElectronica",
    "04": f"{_ESQUEMAS}/tiqueteElectronico",
    "08": f"{_ESQUEMAS}/facturaElectronicaCompra",
    "09": f"{_ESQUEMAS}/facturaElectronicaExportacion",
    "10": f"{_ESQUEMAS}/reciboElectronicoPago",
}

#: El nombre del elemento raíz de cada uno, con el mismo código por llave.
RAICES: Final[dict[str, str]] = {
    "01": "FacturaElectronica",
    "02": "NotaDebitoElectronica",
    "03": "NotaCreditoElectronica",
    "04": "TiqueteElectronico",
    "08": "FacturaElectronicaCompra",
    "09": "FacturaElectronicaExportacion",
    "10": "ReciboElectronicoPago",
}


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


#: Los seis de la 4.4. Física, jurídica, DIMEX (residencia), NITE, extranjero
#: no domiciliado y no contribuyente. Los dos últimos entraron con F7: el `05`
#: es el receptor de una factura de exportación (T-727) y el `06` el vendedor
#: de una factura de compra (T-728). Son de clientes y proveedores; el emisor
#: sigue siendo de los cuatro primeros (`ISSUER_IDENTIFICATION_TYPES`).
IDENTIFICATION_TYPES: Final = ("01", "02", "03", "04", "05", "06")

PHYSICAL: Final = "01"
LEGAL: Final = "02"
DIMEX: Final = "03"
NITE: Final = "04"
FOREIGN: Final = "05"
NON_TAXPAYER: Final = "06"

#: Con los que se puede emitir: quien firma tiene cédula del país y está
#: inscrito. Un extranjero no domiciliado o un no contribuyente reciben
#: comprobantes; no los emiten.
ISSUER_IDENTIFICATION_TYPES: Final = (PHYSICAL, LEGAL, DIMEX, NITE)


def is_foreign(identification_type: object) -> bool:
    """Si un receptor con este tipo es del extranjero, y por eso se le exporta
    (T-727). Espejo de `isForeign` en el POS."""
    return identification_type == FOREIGN


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


def client_identification_type(requested: object, identification: str) -> str:
    """El tipo con que se guarda un cliente (T-617).

    El que se eligió, si se eligió; si no, el que deja ver la longitud de la
    cédula. Es lo que permite que un cliente dado de alta por el API sin el
    campo —`seed.py`, una importación— quede igual que los que ya estaban, que
    la migración 011 clasificó así.

    Y si tampoco así se sabe, **no se guarda**: el tipo va en el receptor del
    comprobante, y un receptor sin tipo es un rechazo de Hacienda que llega
    cuando el cliente ya se fue.
    """
    if requested not in (None, ""):
        return check_identification_type(requested)
    deducido = identification_type_for(identification)
    if deducido is None:
        raise IdentificationTypeRequired()
    return deducido
