"""
Subir, reemplazar y quitar las credenciales de Hacienda (T-603, T-603b, T-605).

**El `.p12` y el PIN existen durante una petición y no vuelven a existir.** El
caso de uso los abre en memoria, manda la privada a Vault, guarda la parte
pública y descarta el resto. Que no haya dónde guardarlos no es una disciplina
que alguien deba recordar: no hay columna.

EL ORDEN DE LOS DOS SISTEMAS, QUE ES LO ÚNICO DELICADO
------------------------------------------------------

Vault y MySQL no comparten transacción, así que en cada operación hay que elegir
**cuál de los dos desenlaces malos se prefiere**, y la respuesta es distinta en
cada sentido:

* **Al subir: primero Vault, después el `COMMIT`.** Una llave importada sin fila
  es inofensiva —no la nombra nadie y la pisa la próxima subida—; una fila que
  dice «tiene certificado» sin llave en Vault rompe al firmar, que es el peor
  momento posible.
* **Al quitar: primero el `COMMIT`, después Vault.** Al revés exactamente, y por
  lo mismo: una llave huérfana en Vault no firma nada porque no hay fila que la
  nombre, mientras que una fila que promete un certificado sobre una llave ya
  borrada vuelve a fallar al firmar.

En los dos casos el criterio es el mismo —**que nunca exista una fila que
prometa más de lo que hay**— y da órdenes opuestos porque las operaciones son
opuestas.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.fe_credentials import FeCredentialsRepository
from app.application.ports.repositories import UnitOfWork
from app.application.ports.secrets import SecretBox
from app.application.ports.signing import CertificateReader, DocumentSigner
from app.domain.errors import DomainError
from app.domain.fe_credentials import EnvironmentStatus, environment_status
from app.domain.hacienda import ENVIRONMENTS, check_environment


class AtvUserRequired(DomainError):
    """Se quiso guardar una contraseña de ATV sin decir de quién es.

    El usuario **no** es opcional aunque la contraseña sea lo secreto: tiene la
    forma `cpf-01-1234-5678@…` —el dominio lo pone `domain/hacienda.py`— y es lo
    que el IdP usa para saber a quién autenticar. Sin él no abre nada.
    """

    def __init__(self) -> None:
        super().__init__("falta el usuario de ATV")


@dataclass(frozen=True)
class UploadCertificate:
    """Sube el `.p12` de un ambiente (RF-22).

    Reemplazar es esto mismo otra vez: `import_key` deja la llave nueva en uso y
    la anterior detrás, así que no hay ventana en la que la compañía se quede
    sin poder firmar.
    """

    credentials: FeCredentialsRepository
    reader: CertificateReader
    signer: DocumentSigner
    clock: Clock
    uow: UnitOfWork

    def __call__(
        self,
        *,
        company_id: int,
        environment: str,
        p12: bytes,
        pin: str,
        user_id: int,
    ) -> EnvironmentStatus:
        check_environment(environment)

        # Abrir el archivo es además la validación del PIN, y sale gratis: hay
        # que abrirlo igual para leer el vencimiento (T-606). Un PIN que no abre
        # el `.p12` no se guarda porque no se guarda nada.
        leido = self.reader.read(p12, pin)

        # Primero Vault. Ver el encabezado del módulo.
        self.signer.import_key(
            leido.private_key_der, company_id=company_id, environment=environment
        )

        ahora = self.clock.now()
        self.credentials.save_certificate(
            environment=environment,
            certificate_pem=leido.certificate_pem,
            certificate_name=leido.subject,
            expires_at=leido.expires_at,
            uploaded_at=ahora,
            uploaded_by=user_id,
        )
        self.uow.commit()

        return _estado(self.credentials, environment, ahora)


@dataclass(frozen=True)
class RemoveCertificate:
    """Quita el certificado de un ambiente (RF-24).

    **No toca las credenciales de ATV.** Son dos cosas con vidas distintas y
    quien quita una no está pidiendo nada de la otra; borrarlas juntas obligaría
    a volver a escribir una contraseña que nadie dijo que estuviera mal.
    """

    credentials: FeCredentialsRepository
    signer: DocumentSigner
    clock: Clock
    uow: UnitOfWork

    def __call__(self, *, company_id: int, environment: str) -> EnvironmentStatus:
        check_environment(environment)

        self.credentials.clear_certificate(environment=environment)
        self.uow.commit()

        # Después del COMMIT, y al revés que al subir. Ver el encabezado.
        self.signer.forget_key(company_id=company_id, environment=environment)

        return _estado(self.credentials, environment, self.clock.now())


@dataclass(frozen=True)
class SaveAtvCredentials:
    """Guarda el usuario y la contraseña de transmisión (RF-29, RN-16).

    La contraseña se cifra con `(company_id, environment)` como dato asociado,
    así que la fila copiada a otra compañía o al otro ambiente no descifra. El
    usuario **no** se cifra: es un identificador y la pantalla lo muestra, para
    que alguien pueda comprobar que escribió el que era.
    """

    credentials: FeCredentialsRepository
    secrets: SecretBox
    clock: Clock
    uow: UnitOfWork

    def __call__(
        self,
        *,
        company_id: int,
        environment: str,
        user: str,
        password: str,
        user_id: int,
    ) -> EnvironmentStatus:
        check_environment(environment)
        usuario = (user or "").strip()
        if not usuario:
            raise AtvUserRequired()

        ahora = self.clock.now()
        self.credentials.save_atv(
            environment=environment,
            user=usuario,
            password_encrypted=self.secrets.encrypt(
                password, company_id=company_id, environment=environment
            ),
            updated_at=ahora,
            updated_by=user_id,
        )
        self.uow.commit()

        return _estado(self.credentials, environment, ahora)


@dataclass(frozen=True)
class ReadFeStatus:
    """El estado de **los dos** ambientes (RF-23, RF-30).

    Devuelve siempre dos, haya filas o no: un ambiente que nunca se configuró
    existe igual y la pantalla tiene que poder decir qué le falta. Con solo las
    filas presentes, «pruebas no está configurado» sería indistinguible de «no
    se pudo leer».
    """

    credentials: FeCredentialsRepository
    clock: Clock

    def __call__(self) -> list[EnvironmentStatus]:
        ahora = self.clock.now()
        filas = {fila.environment: fila for fila in self.credentials.all()}
        return [
            _desde(filas.get(ambiente), ambiente, ahora) for ambiente in ENVIRONMENTS
        ]


# --------------------------------------------------------------------- común


def _desde(fila, environment: str, ahora) -> EnvironmentStatus:
    if fila is None:
        return environment_status(environment=environment, now=ahora)
    return environment_status(
        environment=environment,
        now=ahora,
        certificate_name=fila.certificate_name,
        expires_at=fila.expires_at,
        uploaded_at=fila.cert_uploaded_at,
        atv_user=fila.atv_user,
        # Configurado es que HAYA contraseña, no que haya usuario: el usuario se
        # puede guardar solo y con eso no se transmite nada.
        atv_configured=bool(fila.atv_password_encrypted),
        atv_verified_at=fila.atv_verified_at,
    )


def _estado(credentials: FeCredentialsRepository, environment: str, ahora) -> EnvironmentStatus:
    """El estado de un ambiente, releído después de escribir.

    Se relee en vez de componerlo con lo que se acaba de guardar: así lo que
    devuelve la operación es lo que de verdad quedó, y un `save` que escribiera
    de menos se vería acá y no tres pantallas después.
    """
    return _desde(credentials.get(environment), environment, ahora)
