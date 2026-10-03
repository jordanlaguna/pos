"""
La firma XAdES-EPES, sin Vault (T-712).

Lo que un verificador —Hacienda— hace con un comprobante firmado es volver a
calcular los dos resúmenes y comprobar la firma del `SignedInfo` con el
certificado que viene adentro. Acá se hace exactamente eso con una llave en
memoria: si pasa, la forma es la que Hacienda espera; si la llave es la de
Vault, lo único que cambia es quién calcula la firma RSA.

La canonicalización es la de la biblioteca estándar (C14N 2.0). Que coincida
con la exclusiva 1.0 que Hacienda pide se comprueba contra `lxml` cuando está
instalado, byte por byte, sobre los tres pedazos que se resumen.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric import utils as asimetrico
from cryptography.x509.oid import NameOID

from app.domain import fe_signature as firma
from app.domain.fe_signature import (
    DS,
    MIME_TYPE,
    POLICY_HASH,
    POLICY_ID,
    XADES,
    CertificateFacts,
    InvalidSignatureInput,
    canonical,
    declared_digests,
    sign_document,
    signature_parts,
    signing_time,
)
from app.domain.fe_xml import MedioPago, construir

from .test_fe_xml import ESQUEMAS, comprobante

# ------------------------------------------------------------- una llave real

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _certificado() -> x509.Certificate:
    nombre = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MINISTERIO DE HACIENDA - SANDBOX"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "DGT"),
            x509.NameAttribute(NameOID.COMMON_NAME, "CA PERSONA JURIDICA - SANDBOX"),
        ]
    )
    ahora = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(LLAVE.public_key())
        .serial_number(1775598635763)
        .not_valid_before(ahora - timedelta(days=1))
        .not_valid_after(ahora + timedelta(days=365))
        .sign(LLAVE, hashes.SHA256())
    )


CERTIFICADO = _certificado()
DATOS = CertificateFacts(
    der=CERTIFICADO.public_bytes(serialization.Encoding.DER),
    issuer_name="CN=CA PERSONA JURIDICA - SANDBOX, OU=DGT, O=MINISTERIO DE HACIENDA - SANDBOX, C=CR",
    serial_number=CERTIFICADO.serial_number,
)
CUANDO = datetime(2026, 10, 3, 0, 13, 39)


def firmar_digest(digest: bytes) -> bytes:
    return LLAVE.sign(digest, padding.PKCS1v15(), asimetrico.Prehashed(hashes.SHA256()))


def tiquete_xml() -> str:
    return construir(
        comprobante(tipo="04", receptor=None, medios_pago=(MedioPago("01", Decimal("1130")),))
    )


def firmado(**cambios) -> bytes:
    base = dict(certificate=DATOS, signed_at=CUANDO, sign=firmar_digest, salt="abc123def456")
    return sign_document(tiquete_xml(), **{**base, **cambios})


def verifica(parts) -> bool:
    try:
        LLAVE.public_key().verify(
            parts.signature,
            parts.signed_info_canonical,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:  # noqa: BLE001 — cualquier fallo es «no verifica»
        return False


# -------------------------------------------------------------------- lo que es


class TestLoQueLlevaLaFirma:
    def test_la_firma_va_envuelta_al_final_del_comprobante(self):
        raiz = ET.fromstring(firmado())
        assert raiz.tag.endswith("TiqueteElectronico")
        assert raiz[-1].tag == f"{{{DS}}}Signature"
        assert raiz[-1].get("Id") == "xades-Signature-abc123def456"

    def test_los_dos_resumenes_son_los_que_hacienda_recalcularia(self):
        bytes_firmados = firmado()
        documento, propiedades = declared_digests(bytes_firmados)
        partes = signature_parts(bytes_firmados)
        assert documento == partes.document_digest
        assert propiedades == partes.properties_digest

    def test_la_firma_verifica_con_el_certificado_que_va_adentro(self):
        partes = signature_parts(firmado())
        assert partes.certificate_der == DATOS.der
        assert verifica(partes)

    def test_un_byte_cambiado_deja_de_verificar(self):
        roto = firmado().replace(b"<Clave>5", b"<Clave>6", 1)
        documento, _ = declared_digests(roto)
        assert signature_parts(roto).document_digest != documento

    def test_la_politica_y_los_algoritmos_son_los_de_la_4_4(self):
        texto = firmado().decode("utf-8")
        assert POLICY_ID in texto
        assert POLICY_HASH in texto
        assert MIME_TYPE in texto
        assert 'Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"' in texto
        assert 'Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"' in texto
        assert 'Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"' in texto
        assert 'Type="http://uri.etsi.org/01903#SignedProperties"' in texto
        assert 'ObjectReference="#r-id-1"' in texto

    def test_las_propiedades_dicen_hora_certificado_y_emisor(self):
        raiz = ET.fromstring(firmado())
        propiedades = raiz.find(f".//{{{XADES}}}SignedProperties")
        assert propiedades is not None
        assert propiedades.get("Id") == "SignedProperties-abc123def456"
        assert propiedades.findtext(f".//{{{XADES}}}SigningTime") == "2026-10-03T00:13:39-06:00"
        assert propiedades.findtext(f".//{{{DS}}}X509IssuerName") == DATOS.issuer_name
        assert propiedades.findtext(f".//{{{DS}}}X509SerialNumber") == "1775598635763"
        esperado = base64.b64encode(hashlib.sha256(DATOS.der).digest()).decode()
        assert propiedades.findtext(f".//{{{XADES}}}CertDigest/{{{DS}}}DigestValue") == esperado

    def test_con_la_misma_sal_sale_lo_mismo_y_sin_sal_cambia(self):
        assert firmado() == firmado()
        a = sign_document(tiquete_xml(), certificate=DATOS, signed_at=CUANDO, sign=firmar_digest)
        b = sign_document(tiquete_xml(), certificate=DATOS, signed_at=CUANDO, sign=firmar_digest)
        assert a != b
        assert verifica(signature_parts(a)) and verifica(signature_parts(b))

    def test_empieza_con_la_declaracion_xml_en_utf_8(self):
        assert firmado().startswith(b"<?xml version='1.0' encoding='utf-8'?>")


class TestLaHoraDeLaFirma:
    def test_sin_zona_es_costa_rica(self):
        assert signing_time(datetime(2026, 10, 3, 0, 13, 39, 500)) == "2026-10-03T00:13:39-06:00"

    def test_con_zona_se_respeta(self):
        momento = datetime(2026, 10, 3, 6, 13, 39, tzinfo=timezone.utc)
        assert signing_time(momento) == "2026-10-03T06:13:39+00:00"


class TestLoQueNoSePuedeFirmar:
    def test_sin_xml(self):
        with pytest.raises(InvalidSignatureInput) as e:
            sign_document("   ", certificate=DATOS, signed_at=CUANDO, sign=firmar_digest)
        assert e.value.field == "xml"

    def test_un_firmante_que_no_devuelve_nada(self):
        with pytest.raises(InvalidSignatureInput) as e:
            firmado(sign=lambda _d: b"")
        assert e.value.field == "signature"

    @pytest.mark.parametrize(
        "cambios, campo",
        [
            (dict(der=b""), "certificate"),
            (dict(issuer_name="  "), "issuer_name"),
            (dict(serial_number=-1), "serial_number"),
        ],
    )
    def test_un_certificado_a_medias(self, cambios, campo):
        base = dict(der=DATOS.der, issuer_name=DATOS.issuer_name, serial_number=DATOS.serial_number)
        with pytest.raises(InvalidSignatureInput) as e:
            CertificateFacts(**{**base, **cambios})
        assert e.value.field == campo

    def test_el_base64_del_certificado(self):
        assert base64.b64decode(DATOS.base64) == DATOS.der


class TestDesarmarUnaFirma:
    def test_sin_firma_no_hay_partes(self):
        with pytest.raises(InvalidSignatureInput) as e:
            signature_parts(tiquete_xml().encode("utf-8"))
        assert e.value.field == "signature"

    def test_una_firma_vacia_tampoco(self):
        raiz = ET.fromstring(tiquete_xml())
        ET.SubElement(raiz, f"{{{DS}}}Signature")
        with pytest.raises(InvalidSignatureInput):
            signature_parts(ET.tostring(raiz))

    def test_las_referencias_tienen_que_ser_dos(self):
        with pytest.raises(InvalidSignatureInput) as e:
            declared_digests(tiquete_xml().encode("utf-8"))
        assert e.value.field == "references"


# ----------------------------------------------- contra lxml y contra el XSD


class TestContraLxml:
    """La forma canónica de la biblioteca estándar es la exclusiva de Hacienda."""

    @staticmethod
    def _lxml():
        return pytest.importorskip("lxml.etree", reason="lxml no está instalado")

    def _exclusiva(self, etree, elemento) -> bytes:
        return etree.tostring(elemento, method="c14n", exclusive=True, with_comments=False)

    def test_el_documento_sin_la_firma(self):
        etree = self._lxml()
        texto = tiquete_xml()
        assert canonical(ET.fromstring(texto)) == self._exclusiva(
            etree, etree.fromstring(texto.encode("utf-8"))
        )

    def test_el_signed_info_y_las_propiedades_dentro_del_documento_firmado(self):
        etree = self._lxml()
        bytes_firmados = firmado()
        arbol = etree.fromstring(bytes_firmados)
        ns = {"ds": DS, "xades": XADES}
        nuestro = ET.fromstring(bytes_firmados)

        signed_info = arbol.find(".//ds:SignedInfo", ns)
        assert canonical(nuestro.find(f".//{{{DS}}}SignedInfo")) == self._exclusiva(etree, signed_info)

        propiedades = arbol.find(".//xades:SignedProperties", ns)
        assert canonical(nuestro.find(f".//{{{XADES}}}SignedProperties")) == self._exclusiva(
            etree, propiedades
        )

    def test_quitar_la_firma_con_lxml_da_el_mismo_resumen_que_el_declarado(self):
        """Lo que hace la transformación `enveloped-signature` de verdad."""
        etree = self._lxml()
        bytes_firmados = firmado()
        arbol = etree.fromstring(bytes_firmados)
        for nodo in arbol.findall(f"{{{DS}}}Signature"):
            arbol.remove(nodo)
        resumen = base64.b64encode(hashlib.sha256(self._exclusiva(etree, arbol)).digest()).decode()
        assert resumen == declared_digests(bytes_firmados)[0]


class TestContraElEsquema:
    def test_el_tiquete_firmado_valida_contra_el_xsd_oficial(self, tmp_path: Path):
        etree = pytest.importorskip("lxml.etree", reason="lxml no está instalado")
        hondo = tmp_path / "v4" / "4"
        hondo.mkdir(parents=True)
        for archivo in ESQUEMAS.glob("*.xsd"):
            shutil.copy2(archivo, hondo / archivo.name)
        shutil.copy2(ESQUEMAS / "xmldsig-core-schema.xsd", tmp_path / "xmldsig-core-schema.xsd")
        esquema = etree.XMLSchema(etree.parse(str(hondo / "TiqueteElectronico_V4.4.xsd")))
        esquema.assertValid(etree.fromstring(firmado()))


def test_el_modulo_no_firma_el_solo():
    """No hay llave privada en el dominio: lo que firma entra como función."""
    import inspect

    fuente = inspect.getsource(firma)
    assert "cryptography" not in fuente
    assert "private_key" not in fuente
