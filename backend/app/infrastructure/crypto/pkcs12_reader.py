"""
Abrir el `.p12` que emite ATV (T-603, T-606).

Es lo único del sistema que sabe qué es PKCS#12. Devuelve tres cosas —la parte
pública en PEM, la privada en PKCS#8 para mandarla a Vault, y el vencimiento— y
**no devuelve el archivo ni el PIN**: los dos existen durante la petición que
los trajo y no vuelven a existir.

Sin dependencia nueva: `cryptography` ya estaba y sabe leer PKCS#12 —comprobado
en el contenedor el 2026-09-05, versión 50.0.1—.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.application.ports.signing import InvalidCertificate

#: Todo DER empieza con una SEQUENCE. Es lo que separa «subiste otra cosa» de
#: «el PIN está mal»: un `.cer` en PEM empieza con «-----», un ZIP con «PK», un
#: PDF con «%PDF».
_DER_SEQUENCE = 0x30


@dataclass(frozen=True)
class CertificadoDelP12:
    certificate_pem: str
    private_key_der: bytes
    subject: str
    expires_at: datetime


class Pkcs12CertificateReader:
    """Implementa `CertificateReader` con `cryptography`."""

    def read(self, p12: bytes, pin: str) -> CertificadoDelP12:
        if not p12 or p12[0] != _DER_SEQUENCE:
            raise InvalidCertificate("not_a_p12")

        try:
            privada, certificado, _ = pkcs12.load_key_and_certificates(
                p12, pin.encode("utf-8") if pin else None
            )
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # `cryptography` lanza el **mismo** `ValueError` para un PIN
            # equivocado y para un PKCS#12 corrupto: «Invalid password or
            # PKCS12 data». No hay forma de separarlos desde acá, así que se
            # reporta el PIN, que es la causa mucho más frecuente y la única
            # sobre la que quien está mirando la pantalla puede hacer algo.
            # Lo que sí se separa —arriba— es haber subido otro archivo.
            raise InvalidCertificate("bad_pin") from exc

        if privada is None:
            # Pasa de verdad: al exportar desde el navegador sin marcar
            # «incluir la llave privada».
            raise InvalidCertificate("no_private_key")
        if certificado is None:
            raise InvalidCertificate("no_certificate")

        return CertificadoDelP12(
            certificate_pem=certificado.public_bytes(
                serialization.Encoding.PEM
            ).decode("ascii"),
            private_key_der=privada.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            subject=_nombre(certificado),
            expires_at=_vence(certificado),
        )


def _nombre(certificado: x509.Certificate) -> str:
    """Cómo llamarlo en la pantalla.

    El `CN` primero, que es el nombre del negocio tal como lo emitió Hacienda.
    Si no lo trae, el sujeto entero —feo, pero cierto—; y si tampoco, el número
    de serie, que siempre está. **No se usa el nombre del archivo**: el archivo
    se llama como quiso quien lo bajó, y «llave (1).p12» no le dice nada a nadie
    seis meses después.
    """
    comunes = certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if comunes and isinstance(comunes[0].value, str):
        return comunes[0].value
    entero = certificado.subject.rfc4514_string()
    return entero or f"{certificado.serial_number:x}"


def _vence(certificado: x509.Certificate) -> datetime:
    """El `notAfter`, en la hora local y sin zona.

    **La conversión es lo que importa acá.** `cryptography` devuelve UTC con
    zona, y todo el resto del sistema trabaja en hora local sin zona: los
    contenedores llevan `TZ` justamente para eso (defecto 8). Guardarlo en UTC
    haría que un certificado que vence a las 18:00 de Costa Rica se mostrara
    venciendo a la medianoche del día siguiente, y compararlo con `Clock.now()`
    —que es naíf— lanzaría `TypeError` en vez de dar un resultado raro, que al
    menos es una falla honesta.
    """
    return certificado.not_valid_after_utc.astimezone().replace(tzinfo=None)
