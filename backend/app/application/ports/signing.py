"""
Quién firma los comprobantes (T-602, plan §7.1).

El puerto **no está para elegir entre Vault y otra cosa** —esa decisión ya se
tomó el 2026-09-13 y Vault ganó—. Está por dos razones distintas:

1. **§7.2 deja abierta la ruta de emisión.** Si la firma termina pasando por un
   proveedor autorizado, lo que cambia es el adaptador y no el caso de uso.
2. **Con contrato, firmar se puede probar sin Vault levantado.** Un caso de uso
   que necesitara un contenedor para probarse tendría la regla en la capa
   equivocada.

**La compañía y el ambiente van explícitos y no en un `ContextVar`.** Con estado
escondido, el caso de uso no se puede probar contra «firmá esto con el de
pruebas», y el adaptador no tendría cómo elegir llave sin heredar el contexto de
la petición — que es justo lo que el trabajador de transmisión no tiene, porque
corre fuera de una.

**El puerto recibe un digest, no el documento.** Es lo que permite que la llave
privada nunca entre en memoria de la aplicación: se manda el resumen, vuelve la
firma. Con el documento entero, el adaptador tendría que poder descifrar algo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class SigningUnavailable(Exception):
    """Hoy no se puede firmar, y mañana quizá sí.

    Vault sellado después de un reinicio, Vault caído, la red. **No es lo mismo
    que no tener certificado**: quien la atrapa deja el documento en la cola y
    reintenta, no le dice al negocio que configure nada.

    Es el modo de falla que la decisión de 2026-09-13 introdujo también en el
    negocio de una sola caja, y por eso tiene su propio tipo: lo que la hace
    visible es la alarma de antigüedad de la cola (§7.2), no un 500.
    """


class SigningKeyMissing(Exception):
    """Esta compañía no tiene llave en este ambiente.

    O nunca subió el certificado, o lo quitó. A diferencia de la anterior, esto
    **no se arregla reintentando**: hay que ir a la pantalla y cargar el `.p12`.
    """

    def __init__(self, company_id: int, environment: str) -> None:
        super().__init__(f"la compañía {company_id} no tiene llave en {environment}")
        self.company_id = company_id
        self.environment = environment


class DocumentSigner(Protocol):
    """Firma con la llave de una compañía sin entregarla nunca."""

    def import_key(self, pkcs8_der: bytes, *, company_id: int, environment: str) -> None:
        """Guarda la llave privada donde va a vivir, y la olvida acá.

        Se llama **una sola vez por certificado**, al subir el `.p12`. Volver a
        llamarla con la misma compañía y ambiente es reemplazar el certificado,
        no un error: deja la llave nueva en uso y la anterior detrás.
        """
        ...

    def sign(self, digest: bytes, *, company_id: int, environment: str) -> bytes:
        """La firma PKCS#1 v1.5 del digest, que es lo que pide XAdES-EPES."""
        ...

    def forget_key(self, *, company_id: int, environment: str) -> None:
        """Quita la llave. Es lo que hace «quitar el certificado» (RF-24).

        Sin esto, quitar el certificado dejaría la fila vacía y la llave viva:
        el negocio creería que no puede firmar y el sistema podría hacerlo.
        Quitar una llave que no está **no es un error** — es el estado que se
        pedía.
        """
        ...


class InvalidCertificate(Exception):
    """El `.p12` no se pudo abrir, o no trae lo que hace falta.

    Lleva un código y no una frase, como el resto del proyecto: quien arma el
    texto es el POS (RN-30). Los motivos son cuatro y se distinguen porque lo
    que tiene que hacer la persona es distinto en cada uno:

    * `bad_pin` — el PIN no abre el archivo. Volver a escribirlo.
    * `not_a_p12` — subió otra cosa: el `.cer` que ATV manda al lado, un ZIP.
    * `no_private_key` — es un `.p12` pero solo con la parte pública. Pasa al
      exportar desde el navegador sin marcar «incluir la llave privada».
    * `no_certificate` — trae la llave y no el certificado. Sin él no hay
      `KeyInfo` que meter en el XML.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"el certificado no sirve: {reason}")
        self.reason = reason


class ParsedCertificate(Protocol):
    """Lo que sale de abrir un `.p12`, y nada más.

    **No lleva el `.p12` ni el PIN**: existen durante la petición que los trajo
    y no vuelven a existir. Lo que sigue viaje es la parte pública —que va en
    cada XML firmado— y la privada, que va derecho a Vault y no se guarda.
    """

    #: La parte pública, en PEM. Se guarda en la base sin cifrar.
    certificate_pem: str
    #: La privada en PKCS#8 DER, lista para importar a Vault. No se guarda.
    private_key_der: bytes
    #: Cómo llamarlo en la pantalla. Sale del `subject` del certificado y no del
    #: nombre del archivo: el archivo se llama como quiso quien lo bajó.
    subject: str
    #: El `notAfter`, con hora.
    expires_at: datetime


class CertificateReader(Protocol):
    """Abre un `.p12` con su PIN. Es lo único que sabe de PKCS#12."""

    def read(self, p12: bytes, pin: str) -> ParsedCertificate:
        """Lo de adentro, o `InvalidCertificate` con su motivo."""
        ...
