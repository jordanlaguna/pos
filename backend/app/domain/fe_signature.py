"""
La firma XAdES-EPES del comprobante (T-712, README §6).

Hacienda exige una firma **envuelta** (`ds:Signature` adentro del comprobante),
XAdES-EPES —o sea con política de firma—, canonicalización exclusiva, SHA-256 y
RSA PKCS#1 v1.5. Lo que firma es la llave privada del certificado, y esa llave
vive en Vault y no sale (plan §7.1): por eso este módulo **no firma**. Arma todo
lo que se puede armar sin la llave —los resúmenes, las propiedades, el
`SignedInfo`— y le pide a quien sí la tiene que firme un resumen de 32 bytes. Es
lo que lo deja en el dominio: entra texto y una función, sale texto.

CÓMO SE ARMA, Y POR QUÉ ASÍ
---------------------------

Una firma XML son dos resúmenes y una firma:

1. El resumen del **documento sin la firma** (`Reference URI=""`, con la
   transformación `enveloped-signature`). Se calcula canonicalizando el
   comprobante **antes** de meterle la firma, que es exactamente lo que la
   transformación quiere decir.
2. El resumen de las **propiedades firmadas** de XAdES (`SignedProperties`):
   la hora, el certificado y la política.
3. La firma RSA sobre el `SignedInfo` canonicalizado, que es donde van los dos
   resúmenes de arriba.

**La canonicalización es la de la biblioteca estándar** (`ET.canonicalize`, C14N
2.0) y no `lxml`, que no está en `requirements.txt` a propósito. Sobre un
documento como este —sin comentarios, sin instrucciones de proceso, sin
atributos `xml:*`, con el espacio de nombres por omisión en la raíz y los
prefijos `ds` y `xades` solo donde se usan— la forma canónica 2.0 coincide con la
exclusiva 1.0 que Hacienda pide: las dos escriben una declaración de espacio de
nombres solo donde se **usa visiblemente**. `tests/domain/test_fe_signature.py`
lo comprueba byte por byte contra `lxml` cuando está instalado, y el sandbox de
Hacienda es la prueba de fondo.

Lo que se copia de los comprobantes **aceptados** de `docs/hacienda/costa-rica/
XML-Ejemplos/` es la forma: la referencia con `enveloped-signature` seguida de
`exc-c14n`, el `MimeType` `application/octet-stream`, la política y su resumen.
Lo que no se copia es el `SHA-1` del resumen del certificado: el anexo admite
SHA-256 y es el que se usa.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Final

from .hacienda import SIGNATURE_POLICY_HASH, SIGNATURE_POLICY_ID

DS: Final = "http://www.w3.org/2000/09/xmldsig#"
XADES: Final = "http://uri.etsi.org/01903/v1.3.2#"

EXC_C14N: Final = "http://www.w3.org/2001/10/xml-exc-c14n#"
RSA_SHA256: Final = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256: Final = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED: Final = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
SIGNED_PROPERTIES_TYPE: Final = "http://uri.etsi.org/01903#SignedProperties"

#: La política de firma de la 4.4 (README §6). Vive en `hacienda.py`, que es el
#: único módulo que nombra a Hacienda (T-613); acá solo se usa.
POLICY_ID: Final = SIGNATURE_POLICY_ID
POLICY_HASH: Final = SIGNATURE_POLICY_HASH

#: Lo que declaran los ejemplos oficiales; `text/xml` no.
MIME_TYPE: Final = "application/octet-stream"

#: Costa Rica no tiene horario de verano: la hora local es siempre UTC-6. Es lo
#: que se asume de un `datetime` sin zona, que es lo que da el reloj del
#: servidor (`TZ=America/Costa_Rica`).
COSTA_RICA: Final = timezone(timedelta(hours=-6))


@dataclass(frozen=True)
class CertificateFacts:
    """Lo que la firma necesita saber del certificado, ya leído por el adaptador.

    `issuer_name` va como Hacienda lo escribe en sus ejemplos
    (`CN=…, OU=…, O=…, C=CR`); quien lo arma es el adaptador, que es el que
    tiene la biblioteca de X.509. Acá solo se copia.
    """

    der: bytes
    issuer_name: str
    serial_number: int

    def __post_init__(self) -> None:
        if not self.der:
            raise InvalidSignatureInput("certificate")
        if not self.issuer_name.strip():
            raise InvalidSignatureInput("issuer_name")
        if self.serial_number < 0:
            raise InvalidSignatureInput("serial_number")

    @property
    def base64(self) -> str:
        return base64.b64encode(self.der).decode("ascii")

    @property
    def digest(self) -> str:
        """SHA-256 del DER, en base64: el `CertDigest` de XAdES."""
        return _b64(hashlib.sha256(self.der).digest())


class InvalidSignatureInput(Exception):
    """Falta algo sin lo cual no hay firma. `field` dice qué."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


#: Quien firma: recibe el resumen SHA-256 del `SignedInfo` canonicalizado y
#: devuelve la firma RSA PKCS#1 v1.5. En producción es Vault; en las pruebas,
#: una llave en memoria.
Signer = Callable[[bytes], bytes]


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def canonical(element: ET.Element) -> bytes:
    """La forma canónica de un elemento y lo que cuelga de él.

    Se serializa el elemento solo —con las declaraciones de espacio de nombres
    que él mismo necesita— y se canonicaliza eso. Es lo que la canonicalización
    exclusiva hace con un subárbol: escribir cada espacio de nombres donde se
    usa, sin arrastrar los del documento que lo contiene.
    """
    texto = ET.tostring(element, encoding="unicode")
    return ET.canonicalize(texto, with_comments=False).encode("utf-8")


def digest_of(element: ET.Element) -> str:
    return _b64(hashlib.sha256(canonical(element)).digest())


def signing_time(moment: datetime) -> str:
    """`2026-10-03T00:13:39-06:00`. Un reloj sin zona es hora de Costa Rica."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=COSTA_RICA)
    return moment.replace(microsecond=0).isoformat()


def sign_document(
    xml: str,
    *,
    certificate: CertificateFacts,
    signed_at: datetime,
    sign: Signer,
    salt: str | None = None,
) -> bytes:
    """El comprobante firmado, en UTF-8, listo para enviarse y para guardarse.

    Lo que devuelve es **lo que se archiva**: la firma cubre estos bytes
    exactos y volver a serializar daría otra firma (RN-44). `salt` fija los
    identificadores internos de la firma; sin él son aleatorios, como en los
    ejemplos. Las pruebas lo fijan para poder comparar.
    """
    if not xml or not xml.lstrip():
        raise InvalidSignatureInput("xml")
    ET.register_namespace("ds", DS)
    ET.register_namespace("xades", XADES)

    raiz = ET.fromstring(xml)
    sufijo = salt or secrets.token_hex(6)
    id_firma = f"xades-Signature-{sufijo}"
    id_propiedades = f"SignedProperties-{sufijo}"
    id_referencia = "r-id-1"

    # 1. El documento sin la firma: es la transformación `enveloped-signature`
    #    hecha antes de que exista lo que habría que quitar.
    resumen_documento = digest_of(raiz)

    # 2. Las propiedades firmadas de XAdES.
    propiedades = _signed_properties(
        id_propiedades,
        certificate=certificate,
        moment=signed_at,
        id_referencia=id_referencia,
    )
    resumen_propiedades = digest_of(propiedades)

    # 3. El SignedInfo con los dos resúmenes, y su firma.
    signed_info = _signed_info(
        id_referencia=id_referencia,
        id_propiedades=id_propiedades,
        resumen_documento=resumen_documento,
        resumen_propiedades=resumen_propiedades,
    )
    firma = sign(hashlib.sha256(canonical(signed_info)).digest())
    if not firma:
        raise InvalidSignatureInput("signature")

    signature = ET.Element(f"{{{DS}}}Signature", {"Id": id_firma})
    signature.append(signed_info)
    ET.SubElement(signature, f"{{{DS}}}SignatureValue").text = _b64(firma)
    key_info = ET.SubElement(signature, f"{{{DS}}}KeyInfo", {"Id": f"KeyInfo-{sufijo}"})
    x509 = ET.SubElement(key_info, f"{{{DS}}}X509Data")
    ET.SubElement(x509, f"{{{DS}}}X509Certificate").text = certificate.base64
    objeto = ET.SubElement(signature, f"{{{DS}}}Object")
    calificadoras = ET.SubElement(
        objeto, f"{{{XADES}}}QualifyingProperties", {"Target": f"#{id_firma}"}
    )
    calificadoras.append(propiedades)

    raiz.append(signature)
    return ET.tostring(raiz, encoding="unicode", xml_declaration=True).encode("utf-8")


def _signed_info(
    *,
    id_referencia: str,
    id_propiedades: str,
    resumen_documento: str,
    resumen_propiedades: str,
) -> ET.Element:
    signed_info = ET.Element(f"{{{DS}}}SignedInfo")
    ET.SubElement(signed_info, f"{{{DS}}}CanonicalizationMethod", {"Algorithm": EXC_C14N})
    ET.SubElement(signed_info, f"{{{DS}}}SignatureMethod", {"Algorithm": RSA_SHA256})

    documento = ET.SubElement(signed_info, f"{{{DS}}}Reference", {"Id": id_referencia, "URI": ""})
    transformaciones = ET.SubElement(documento, f"{{{DS}}}Transforms")
    ET.SubElement(transformaciones, f"{{{DS}}}Transform", {"Algorithm": ENVELOPED})
    ET.SubElement(transformaciones, f"{{{DS}}}Transform", {"Algorithm": EXC_C14N})
    ET.SubElement(documento, f"{{{DS}}}DigestMethod", {"Algorithm": SHA256})
    ET.SubElement(documento, f"{{{DS}}}DigestValue").text = resumen_documento

    propiedades = ET.SubElement(
        signed_info,
        f"{{{DS}}}Reference",
        {"URI": f"#{id_propiedades}", "Type": SIGNED_PROPERTIES_TYPE},
    )
    transformaciones = ET.SubElement(propiedades, f"{{{DS}}}Transforms")
    ET.SubElement(transformaciones, f"{{{DS}}}Transform", {"Algorithm": EXC_C14N})
    ET.SubElement(propiedades, f"{{{DS}}}DigestMethod", {"Algorithm": SHA256})
    ET.SubElement(propiedades, f"{{{DS}}}DigestValue").text = resumen_propiedades
    return signed_info


def _signed_properties(
    id_propiedades: str,
    *,
    certificate: CertificateFacts,
    moment: datetime,
    id_referencia: str,
) -> ET.Element:
    propiedades = ET.Element(f"{{{XADES}}}SignedProperties", {"Id": id_propiedades})
    firma = ET.SubElement(propiedades, f"{{{XADES}}}SignedSignatureProperties")
    ET.SubElement(firma, f"{{{XADES}}}SigningTime").text = signing_time(moment)

    certificado = ET.SubElement(
        ET.SubElement(firma, f"{{{XADES}}}SigningCertificate"), f"{{{XADES}}}Cert"
    )
    resumen = ET.SubElement(certificado, f"{{{XADES}}}CertDigest")
    ET.SubElement(resumen, f"{{{DS}}}DigestMethod", {"Algorithm": SHA256})
    ET.SubElement(resumen, f"{{{DS}}}DigestValue").text = certificate.digest
    emisor = ET.SubElement(certificado, f"{{{XADES}}}IssuerSerial")
    ET.SubElement(emisor, f"{{{DS}}}X509IssuerName").text = certificate.issuer_name
    ET.SubElement(emisor, f"{{{DS}}}X509SerialNumber").text = str(certificate.serial_number)

    politica = ET.SubElement(
        ET.SubElement(firma, f"{{{XADES}}}SignaturePolicyIdentifier"),
        f"{{{XADES}}}SignaturePolicyId",
    )
    ET.SubElement(
        ET.SubElement(politica, f"{{{XADES}}}SigPolicyId"), f"{{{XADES}}}Identifier"
    ).text = POLICY_ID
    hash_politica = ET.SubElement(politica, f"{{{XADES}}}SigPolicyHash")
    ET.SubElement(hash_politica, f"{{{DS}}}DigestMethod", {"Algorithm": SHA256})
    ET.SubElement(hash_politica, f"{{{DS}}}DigestValue").text = POLICY_HASH

    datos = ET.SubElement(propiedades, f"{{{XADES}}}SignedDataObjectProperties")
    formato = ET.SubElement(
        datos, f"{{{XADES}}}DataObjectFormat", {"ObjectReference": f"#{id_referencia}"}
    )
    ET.SubElement(formato, f"{{{XADES}}}MimeType").text = MIME_TYPE
    return propiedades


# ------------------------------------------------------------- para verificar


@dataclass(frozen=True)
class SignatureParts:
    """Lo que un verificador necesita sacar de un comprobante firmado."""

    document_digest: str
    properties_digest: str
    signed_info_canonical: bytes
    signature: bytes
    certificate_der: bytes


def signature_parts(signed_xml: bytes) -> SignatureParts:
    """Desarma una firma para comprobarla: lo que haría Hacienda.

    Vuelve a calcular el resumen del documento quitando la firma y el de las
    propiedades canonicalizándolas, y devuelve además el `SignedInfo` canónico
    con la firma y el certificado, para que quien tenga la llave pública decida.
    No depende de ningún secreto: sirve para verificar lo archivado años después.
    """
    raiz = ET.fromstring(signed_xml)
    firma = raiz.find(f"{{{DS}}}Signature")
    if firma is None:
        raise InvalidSignatureInput("signature")
    raiz.remove(firma)
    resumen_documento = digest_of(raiz)

    propiedades = firma.find(f".//{{{XADES}}}SignedProperties")
    signed_info = firma.find(f"{{{DS}}}SignedInfo")
    valor = firma.findtext(f"{{{DS}}}SignatureValue") or ""
    certificado = firma.findtext(f".//{{{DS}}}X509Certificate") or ""
    if propiedades is None or signed_info is None or not valor or not certificado:
        raise InvalidSignatureInput("signature")
    return SignatureParts(
        document_digest=resumen_documento,
        properties_digest=digest_of(propiedades),
        signed_info_canonical=canonical(signed_info),
        signature=base64.b64decode(valor),
        certificate_der=base64.b64decode(certificado),
    )


def declared_digests(signed_xml: bytes) -> tuple[str, str]:
    """Los dos `DigestValue` que la firma dice, en el orden del `SignedInfo`."""
    raiz = ET.fromstring(signed_xml)
    valores = [
        (r.findtext(f"{{{DS}}}DigestValue") or "")
        for r in raiz.findall(f"{{{DS}}}Signature/{{{DS}}}SignedInfo/{{{DS}}}Reference")
    ]
    if len(valores) != 2:
        raise InvalidSignatureInput("references")
    return valores[0], valores[1]
