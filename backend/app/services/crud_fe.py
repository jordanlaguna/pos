"""
Factura electrónica — adaptador (T-603, T-604, T-605).

Arma los casos de uso con sus adaptadores y traduce sus «no» a códigos del API.
Acá no se decide nada del negocio: lo que decide qué está listo y qué no es
`domain/fe_credentials.py`, y lo que decide el orden entre Vault y la base es el
caso de uso.

**El módulo del plan no se exige, y es una decisión** (2026-09-13). El plan
tiene una bandera `factura_electronica` desde la 002 que nadie consumía, y
`domain/modules.py` dejaba escrito que el día que F6 la usara habría que decidir
si entra a `MODULES` o se queda aparte. Se queda aparte:

* `MODULES` es a la vez la lista de módulos **y la de columnas** —se lee con
  `getattr(Plan, nombre)`—, así que meter `factura_electronica` ahí pondría un
  nombre en español dentro de un contrato que viaja al POS en inglés, o
  obligaría a una capa de traducción que existiría por un solo caso.
* Y sobre todo, **la puerta es emitir, no configurar**. Subir un certificado en
  una compañía cuyo plan no incluye factura electrónica no emite nada; el
  candado que importa es el de F7 (T-713). Cerrar la configuración y dejar
  abierta la emisión sería cerrar la puerta equivocada.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.ports.signing import (
    InvalidCertificate,
    SigningKeyMissing,
    SigningUnavailable,
)
from app.application.use_cases.fe_credentials import (
    AtvUserRequired,
    ReadFeStatus,
    RemoveCertificate,
    SaveAtvCredentials,
    UploadCertificate,
)
from app.domain.errors import InvalidEnvironment
from app.domain.fe_credentials import EnvironmentStatus
from app.domain.hacienda import SANDBOX, check_environment
from app.infrastructure.clock import SystemClock
from app.infrastructure.crypto.fe_crypto import secret_box
from app.infrastructure.crypto.pkcs12_reader import Pkcs12CertificateReader
from app.infrastructure.crypto.vault_signer import document_signer
from app.infrastructure.persistence.sqlalchemy_fe import SqlAlchemyFeCredentialsRepository
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyUnitOfWork
from app.services import crud_settings
from app.utils.api_errors import api_error

#: Lo máximo que puede pesar un `.p12`. Uno de Hacienda no pasa de 5 KB; el
#: techo está para que subir un ISO por equivocación no se lea entero en memoria
#: antes de rechazarlo.
MAX_P12_BYTES = 256 * 1024


def _ambiente(valor: str) -> str:
    try:
        return check_environment(valor)
    except InvalidEnvironment:
        raise api_error(400, "invalid_environment", environment=valor) from None


def _credenciales(db: Session) -> SqlAlchemyFeCredentialsRepository:
    return SqlAlchemyFeCredentialsRepository(db)


def estado(db: Session) -> dict:
    """Los dos ambientes y cuál está en uso (RF-23, RF-30).

    **Las tres escrituras devuelven esto mismo**, y no solo el ambiente que
    tocaron: una sola forma de respuesta significa que la pantalla no tiene que
    mezclar lo que tenía con lo que le llega, que es donde se cuelan los
    estados a medias.
    """
    caso = ReadFeStatus(credentials=_credenciales(db), clock=SystemClock())
    return {
        "environments": [_salida(e) for e in caso()],
        "active": _activo(db),
    }


def subir_certificado(
    db: Session, ambiente: str, *, contenido: bytes, pin: str, user_id: int, company_id: int
) -> dict:
    """RF-22. El `.p12` y el PIN viven solo dentro de esta función."""
    entorno = _ambiente(ambiente)
    if len(contenido) > MAX_P12_BYTES:
        raise api_error(413, "certificate_too_large", limit=MAX_P12_BYTES)

    caso = UploadCertificate(
        credentials=_credenciales(db),
        reader=Pkcs12CertificateReader(),
        signer=document_signer(),
        clock=SystemClock(),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(
            company_id=company_id,
            environment=entorno,
            p12=contenido,
            pin=pin,
            user_id=user_id,
        )
    except InvalidCertificate as exc:
        # El motivo viaja como dato y no como frase: lo que hay que hacer es
        # distinto en cada uno y quien escribe la oración es el POS (RN-30).
        raise api_error(400, "invalid_certificate", reason=exc.reason) from None
    except SigningUnavailable:
        raise _sin_vault() from None

    return estado(db)


def quitar_certificado(db: Session, ambiente: str, *, company_id: int) -> dict:
    """RF-24. No toca las credenciales de transmisión."""
    entorno = _ambiente(ambiente)
    caso = RemoveCertificate(
        credentials=_credenciales(db),
        signer=document_signer(),
        clock=SystemClock(),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(company_id=company_id, environment=entorno)
    except (SigningUnavailable, SigningKeyMissing):
        raise _sin_vault() from None

    return estado(db)


def guardar_atv(
    db: Session, ambiente: str, payload, *, user_id: int, company_id: int
) -> dict:
    """RF-29. La contraseña recibe el mismo trato que recibía el PIN."""
    entorno = _ambiente(ambiente)
    caso = SaveAtvCredentials(
        credentials=_credenciales(db),
        secrets=secret_box(),
        clock=SystemClock(),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(
            company_id=company_id,
            environment=entorno,
            user=payload.user,
            password=payload.password,
            user_id=user_id,
        )
    except AtvUserRequired:
        raise api_error(400, "atv_user_required") from None

    return estado(db)


# --------------------------------------------------------------------- común


def _sin_vault():
    """Vault sellado, caído o sin el motor montado.

    Es 503 y no 500 a propósito: 503 dice «esto se puede reintentar», que es
    exactamente lo que pasa cuando alguien reinició la VM y nadie abrió Vault.
    Un 500 invitaría a buscar un defecto en el código.
    """
    return api_error(503, "signing_unavailable")


def _activo(db: Session) -> str:
    """El ambiente en uso, que vive en la configuración de la compañía.

    Por omisión `sandbox`: una compañía que nunca lo configuró **no** está
    emitiendo en producción, y suponer lo contrario sería suponer efecto fiscal
    donde no lo hay.
    """
    guardado = (crud_settings.get_settings(db) or {}).get("eInvoicing") or {}
    try:
        return check_environment(guardado.get("environment"))
    except InvalidEnvironment:
        return SANDBOX


def _salida(estado_de: EnvironmentStatus) -> dict:
    return {
        "environment": estado_de.environment,
        "certificate_configured": estado_de.certificate_configured,
        "certificate_name": estado_de.certificate_name,
        "expires_at": estado_de.expires_at,
        "days_left": estado_de.days_left,
        "certificate_status": estado_de.certificate_status,
        "uploaded_at": estado_de.uploaded_at,
        "atv_user": estado_de.atv_user,
        "atv_configured": estado_de.atv_configured,
        "atv_verified_at": estado_de.atv_verified_at,
        "ready": estado_de.ready,
    }
