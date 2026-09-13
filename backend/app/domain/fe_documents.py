"""
Dónde vive cada comprobante dentro del almacén (T-623, plan §7.3).

Son cinco clases de documento y todas tienen la misma forma: un archivo que hay
que devolver idéntico años después, porque de eso depende que una firma todavía
verifique. Lo que decide este módulo es **el nombre**, que es lo único de todo
el asunto que tiene reglas de negocio.

La ruta la arma el servidor y nunca quien llama:

    {company_id}/{environment}/{kind}/{yyyy}/{mm}/{clave}.{xml|pdf}

Cada tramo está por una razón distinta y ninguna es estética:

* **`company_id` primero** porque una ruta que pudiera escribir el cliente
  dejaría que la compañía 7 leyera el comprobante de la 3. Es la tercera vez que
  el proyecto escribe esta misma frase —el dato asociado del AES-GCM y el nombre
  de la llave de Vault son las otras dos— y las tres veces significa lo mismo:
  la identidad la fija el servidor. De paso, el prefijo de una compañía es lo
  que se copia, se le entrega al irse o se borra al darla de baja.
* **`environment`** porque la clave numérica se arma con el consecutivo, y el de
  pruebas y el de producción se numeran aparte: **dos documentos distintos
  pueden tener la misma clave**. Sin este tramo, un tiquete de ensayo pisa una
  factura de verdad.
* **Año y mes** porque la custodia tiene plazo, y borrar lo vencido así es
  listar un prefijo en vez de recorrer el bucket entero.
* **La clave numérica** como nombre, que es el identificador que ya usan
  Hacienda, el proveedor y nosotros. Buscar «el XML de esta factura» no necesita
  un índice.

**El año y el mes salen de la propia clave, no de un parámetro.** La clave los
lleva adentro —posiciones 4 a 9, `ddmmaa`— y pedirlos aparte sería admitir que
puedan no coincidir: el mismo documento archivado en dos meses según quién lo
guarde. Una sola fuente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import InvalidClave, InvalidDocumentKind, InvalidEnvironment

# ------------------------------------------------------------------ ambientes

SANDBOX: Final = "sandbox"
PRODUCTION: Final = "production"

#: En inglés y no en español, como el resto de las columnas nuevas (plan §3.9).
#: `'sandbox'` es además el valor que el POS ya publica hoy.
ENVIRONMENTS: Final = (SANDBOX, PRODUCTION)

# -------------------------------------------------------- clases de documento

#: El XML firmado que se le manda a Hacienda.
SIGNED_PAYLOAD: Final = "signed-payload"
#: La respuesta firmada de Hacienda: es la que prueba que aceptó.
GOV_RESPONSE: Final = "gov-response"
#: El comprobante que manda un proveedor.
RECEIVED_COMPROBANTE: Final = "received-comprobante"
#: Nuestro mensaje receptor, firmado: aceptado, aceptado parcial o rechazado.
RECEIVED_RESPONSE: Final = "received-response"
#: La representación gráfica que suele venir con el recibido.
RECEIVED_PDF: Final = "received-pdf"

#: Extensión y tipo de contenido de cada clase. La tabla es la lista de clases
#: válidas: una clase que no esté acá no tiene dónde guardarse, y eso es un
#: error de programación, no un dato del usuario.
_MEDIA: Final[dict[str, tuple[str, str]]] = {
    SIGNED_PAYLOAD: ("xml", "application/xml"),
    GOV_RESPONSE: ("xml", "application/xml"),
    RECEIVED_COMPROBANTE: ("xml", "application/xml"),
    RECEIVED_RESPONSE: ("xml", "application/xml"),
    RECEIVED_PDF: ("pdf", "application/pdf"),
}

KINDS: Final = tuple(_MEDIA)

# ------------------------------------------------------------ clave numérica

#: 3 país + 2 día + 2 mes + 2 año + 12 identificación + 20 consecutivo
#: + 1 situación + 8 código de seguridad.
CLAVE_LENGTH: Final = 50

#: El siglo que le falta a los dos dígitos del año. La clave numérica nació con
#: dos y no hay forma de arreglarlo desde acá; lo que sí se puede es dejar
#: escrito de dónde sale el «20».
_CENTURY: Final = 2000


def _check_clave(clave: str) -> None:
    """Lo justo para que la ruta tenga sentido, y ni un control más.

    No se valida que el país sea 506 ni que el código de seguridad sea el que
    corresponde: un comprobante extranjero o una clave mal calculada son
    problemas de otro, y rechazarlos acá dejaría documentos legítimos sin poder
    archivarse. Lo que sí se valida es lo que **arma la ruta** —el largo y la
    fecha—, porque un mes «00» produce una carpeta que nadie va a volver a
    encontrar.
    """
    if not isinstance(clave, str) or len(clave) != CLAVE_LENGTH:
        raise InvalidClave(clave, "length")
    if not clave.isdigit():
        raise InvalidClave(clave, "not_digits")

    dia = int(clave[3:5])
    mes = int(clave[5:7])
    if not 1 <= mes <= 12:
        raise InvalidClave(clave, "month")
    if not 1 <= dia <= 31:
        raise InvalidClave(clave, "day")


@dataclass(frozen=True)
class DocumentRef:
    """Un documento custodiado, dicho de la única forma que el almacén entiende.

    Es un objeto de valor y no una cadena a propósito: el adaptador recibe esto
    y no una ruta, así que no hay ningún punto del programa donde alguien pueda
    componer una ruta a mano y equivocarse de compañía.
    """

    company_id: int
    environment: str
    kind: str
    clave: str

    def __post_init__(self) -> None:
        if not isinstance(self.company_id, int) or self.company_id <= 0:
            raise InvalidClave(self.company_id, "company")
        if self.environment not in ENVIRONMENTS:
            raise InvalidEnvironment(self.environment)
        if self.kind not in _MEDIA:
            raise InvalidDocumentKind(self.kind)
        _check_clave(self.clave)

    @property
    def year(self) -> int:
        return _CENTURY + int(self.clave[7:9])

    @property
    def month(self) -> int:
        return int(self.clave[5:7])

    @property
    def extension(self) -> str:
        return _MEDIA[self.kind][0]

    @property
    def content_type(self) -> str:
        return _MEDIA[self.kind][1]

    @property
    def key(self) -> str:
        """La ruta dentro del bucket."""
        return (
            f"{self.company_id}/{self.environment}/{self.kind}/"
            f"{self.year:04d}/{self.month:02d}/{self.clave}.{self.extension}"
        )

    def __str__(self) -> str:
        return self.key


def company_prefix(company_id: int) -> str:
    """Todo lo de una compañía, para copiarlo, entregarlo o borrarlo de una vez.

    Existe para que `company_dump.py` y la baja de un cliente no tengan que
    saber cómo se arma una ruta: preguntan por el prefijo y listan.
    """
    if not isinstance(company_id, int) or company_id <= 0:
        raise InvalidClave(company_id, "company")
    return f"{company_id}/"
