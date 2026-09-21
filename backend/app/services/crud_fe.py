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

from app.application.ports.secrets import SecretUnreadable
from app.application.ports.signing import (
    InvalidCertificate,
    SigningKeyMissing,
    SigningUnavailable,
)
from app.application.ports.transmission import CredentialsRejected, IdpUnreachable
from app.application.use_cases.fe_credentials import (
    AtvNotConfigured,
    AtvUserRequired,
    ReadFeStatus,
    RemoveCertificate,
    SaveAtvCredentials,
    UploadCertificate,
    VerifyAtvCredentials,
)
from app.domain.errors import InvalidEnvironment
from app.domain.fe_credentials import EnvironmentStatus
from app.domain.hacienda import SANDBOX, check_environment, needs_confirmation
from app.infrastructure.clock import SystemClock
from app.infrastructure.crypto.fe_crypto import secret_box
from app.infrastructure.crypto.pkcs12_reader import Pkcs12CertificateReader
from app.infrastructure.crypto.vault_signer import document_signer
from app.infrastructure.external.hacienda_idp import endpoints_for, hacienda_idp
from app.infrastructure.persistence.sqlalchemy_fe import SqlAlchemyFeCredentialsRepository
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyUnitOfWork
from app.services import crud_membership, crud_settings
from app.utils.api_errors import api_error

#: Dónde vive el ambiente activo. Es un campo protegido de la configuración
#: (`crud_settings.PROTECTED_PATHS`): se lee por ahí y **solo se escribe** por
#: `cambiar_ambiente`, que confirma y deja bitácora.
ACTIVE_PATH = ("eInvoicing", "environment")

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


def verificar_atv(db: Session, ambiente: str, *, user_id: int, company_id: int) -> dict:
    """RF-31. Pide un token y lo tira: comprueba sin emitir nada.

    Los cuatro «no» son cuatro códigos distintos porque mandan a hacer cuatro
    cosas distintas, y el que más importa es el último: **«no se pudo
    comprobar» no es «no sirven»**. Quien reciba el segundo va a rotar su
    contraseña en ATV, y hacerlo el día que Hacienda está en mantenimiento es
    trabajo perdido sobre una credencial que estaba bien.

    **Queda en bitácora que se usaron, con su desenlace y sin su contenido**
    (T-609b, plan §7.1). Los cuatro desenlaces se anotan y no solo el bueno: la
    pregunta que se hace de verdad seis meses después no es «probó alguna vez»
    sino «desde cuándo esto no funciona», y esa la contestan los «no».
    """
    entorno = _ambiente(ambiente)
    caso = VerifyAtvCredentials(
        credentials=_credenciales(db),
        secrets=secret_box(),
        idp=hacienda_idp(),
        clock=SystemClock(),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(
            company_id=company_id,
            environment=entorno,
            endpoints=endpoints_for(entorno),
        )
    except AtvNotConfigured:
        # El único que NO se anota: no había credenciales, así que no se usó
        # ninguna. Una línea acá diría que se probó algo que no existe.
        raise api_error(409, "atv_not_configured", environment=entorno) from None
    except SecretUnreadable:
        _anotar_uso(db, user_id, company_id, entorno, "no se pudo descifrar")
        raise api_error(409, "atv_password_unreadable", environment=entorno) from None
    except CredentialsRejected:
        _anotar_uso(db, user_id, company_id, entorno, "rechazadas por Hacienda")
        raise api_error(400, "atv_invalid_credentials", environment=entorno) from None
    except IdpUnreachable:
        _anotar_uso(db, user_id, company_id, entorno, "sin respuesta de Hacienda")
        # 503 y no 502: dice «reintentá», que es lo único cierto que se sabe.
        raise api_error(503, "atv_unreachable", environment=entorno) from None

    _anotar_uso(db, user_id, company_id, entorno, "aceptadas")
    return estado(db)


def _anotar_uso(
    db: Session, user_id: int, company_id: int, entorno: str, desenlace: str
) -> None:
    """La mitad positiva de la bitácora (T-609b): se usaron, y cómo salió.

    **El detalle no lleva ni el usuario de ATV ni un fragmento de la
    contraseña**, y eso no es prudencia sino la regla: lo que se registra es el
    hecho, no el secreto. El usuario se puede ver en la pantalla, que es donde
    corresponde; en una bitácora que soporte lee de todas las compañías, no.

    Confirma acá y no lo deja al endpoint porque tres de los cuatro desenlaces
    terminan en una excepción: sin `commit`, la línea que explica el fallo se
    iría con la sesión justo en el caso que hacía falta narrar.
    """
    crud_membership.registrar(
        db,
        user_id=user_id,
        company_id=company_id,
        accion="fe_credenciales_probadas",
        detalle=f"{entorno}: {desenlace}",
        ip=None,
    )
    db.commit()


def cambiar_ambiente(
    db: Session, ambiente: str, *, confirmado: bool, user_id: int, company_id: int
) -> dict:
    """RF-30, RN-35. Elige el ambiente en uso, con confirmación y bitácora.

    **El aviso de la certificación de Hacienda lo da el POS**, no esto (RN-46,
    RN-30): la confirmación enumera la factura, el tiquete y la nota de crédito
    que §12 exige haber emitido en pruebas, y el backend **no lo impide** porque
    todavía no hay comprobantes que contar. La puerta dura es T-713, en F7.

    Cambiar al mismo ambiente que ya estaba no escribe ni registra nada: no
    hubo cambio, y una bitácora con líneas que dicen «de producción a
    producción» es una bitácora que nadie lee.
    """
    entorno = _ambiente(ambiente)
    anterior = _activo(db)
    if entorno == anterior:
        return estado(db)

    if needs_confirmation(entorno) and not confirmado:
        raise api_error(400, "confirmation_required", environment=entorno)

    crud_settings.write_protected(db, *ACTIVE_PATH, entorno)
    crud_membership.registrar(
        db,
        user_id=user_id,
        company_id=company_id,
        accion="fe_ambiente",
        # El antes y el después, como la entrada de T-305. «Cambió el ambiente»
        # no sirve para nada dentro de seis meses, que es justo cuando alguien
        # va a preguntar desde cuándo estas facturas tienen efecto fiscal.
        detalle=f"{anterior} → {entorno}",
        ip=None,
    )
    # Un solo `commit` para el cambio y su línea: no puede quedar uno sin la
    # otra. Es la misma razón por la que `registrar` no confirma.
    db.commit()

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
    donde no lo hay. Lo mismo con un valor que no se entiende — cae al ambiente
    inofensivo, no al que tiene consecuencias.
    """
    try:
        return check_environment(crud_settings.read_protected(db, *ACTIVE_PATH))
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
