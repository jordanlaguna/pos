"""
Lo que la firma necesita del certificado público (T-712).

`fe_credentials.certificate_pem` guarda la parte pública del `.p12` que se
subió en F6. XAdES la pide tres veces: el certificado entero en `KeyInfo`, su
resumen en `CertDigest` y el emisor con el serial en `IssuerSerial`. Leer un
X.509 es cosa de `cryptography`, y por eso esto es un adaptador y no parte de
`domain/fe_signature.py`, que solo copia lo que de acá sale.
"""

from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from app.application.ports.signing import InvalidCertificate
from app.domain.fe_signature import CertificateFacts


def _nombre_del_emisor(certificado: x509.Certificate) -> str:
    """`CN=…, OU=…, O=…, C=CR`, como lo escriben los comprobantes aceptados.

    Es el orden de RFC 4514 —el más específico primero— con coma y espacio entre
    partes, que es como lo imprime Java y como lo traen los ejemplos de
    `docs/hacienda/costa-rica/XML-Ejemplos/`. Se arma parte por parte y no con
    un `replace` sobre la cadena entera: un valor con coma la lleva escapada y
    un `replace` la rompería.
    """
    return ", ".join(rdn.rfc4514_string() for rdn in reversed(list(certificado.issuer.rdns)))


class X509CertificateParser:
    """Cumple `CertificateParser` con `cryptography`."""

    def facts(self, certificate_pem: str) -> CertificateFacts:
        try:
            certificado = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise InvalidCertificate("unreadable") from exc
        return CertificateFacts(
            der=certificado.public_bytes(serialization.Encoding.DER),
            issuer_name=_nombre_del_emisor(certificado),
            serial_number=certificado.serial_number,
        )
