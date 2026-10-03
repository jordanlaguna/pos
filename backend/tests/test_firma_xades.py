"""
La firma XAdES con la llave en Vault de verdad (T-712, plan §7.1).

`tests/domain/test_fe_signature.py` prueba la forma con una llave en memoria.
Acá la llave se importa a Vault —el camino de T-602b— y lo que firma es Vault:
si lo firmado verifica con el certificado público, el adaptador y el dominio se
entienden sobre qué es «el resumen» y qué es «la firma». Se omite si la pila de
pruebas no está arriba, como `test_firma_fe.py`.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.domain.fe_signature import signature_parts, sign_document
from app.domain.fe_xml import MedioPago, construir
from app.domain.hacienda import SANDBOX
from app.infrastructure.crypto.certificate_facts import X509CertificateParser
from app.infrastructure.crypto.vault_signer import VaultDocumentSigner
from tests.conftest import marca_unica
from tests.domain.test_fe_signature import CERTIFICADO, CUANDO, LLAVE
from tests.domain.test_fe_xml import comprobante

VAULT = os.environ.get("VENTASYS_TEST_VAULT", "http://127.0.0.1:8202")
TOKEN = os.environ.get("VENTASYS_TEST_VAULT_TOKEN", "test-root-token")

pytestmark = pytest.mark.integration


def _vault_arriba() -> bool:
    try:
        with urllib.request.urlopen(f"{VAULT}/v1/sys/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
    except urllib.error.HTTPError as e:  # pragma: no cover - sellado o en espera
        return e.code in (429, 472, 473)


@pytest.fixture
def firmante():
    if not _vault_arriba():
        pytest.skip("la pila de pruebas (Vault en 8202) no está arriba")
    from cryptography.hazmat.primitives import serialization

    compania = int(marca_unica()[-6:])
    signer = VaultDocumentSigner(VAULT, TOKEN)
    signer.import_key(
        LLAVE.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        company_id=compania,
        environment=SANDBOX,
    )
    yield signer, compania
    signer.forget_key(company_id=compania, environment=SANDBOX)


def test_lo_que_firma_vault_verifica_con_el_certificado(firmante):
    signer, compania = firmante
    from cryptography.hazmat.primitives import serialization

    datos = X509CertificateParser().facts(
        CERTIFICADO.public_bytes(serialization.Encoding.PEM).decode("ascii")
    )
    xml = construir(comprobante(tipo="04", receptor=None, medios_pago=(MedioPago("01", Decimal("1130")),)))
    firmado = sign_document(
        xml,
        certificate=datos,
        signed_at=CUANDO,
        sign=lambda digest: signer.sign(digest, company_id=compania, environment=SANDBOX),
    )
    partes = signature_parts(firmado)
    LLAVE.public_key().verify(
        partes.signature, partes.signed_info_canonical, padding.PKCS1v15(), hashes.SHA256()
    )
    assert partes.certificate_der == datos.der


def test_el_emisor_del_certificado_se_escribe_como_en_los_ejemplos():
    from cryptography.hazmat.primitives import serialization

    datos = X509CertificateParser().facts(
        CERTIFICADO.public_bytes(serialization.Encoding.PEM).decode("ascii")
    )
    assert datos.issuer_name == (
        "CN=CA PERSONA JURIDICA - SANDBOX, OU=DGT, O=MINISTERIO DE HACIENDA - SANDBOX, C=CR"
    )
    assert datos.serial_number == CERTIFICADO.serial_number


def test_un_pem_que_no_es_un_certificado():
    from app.application.ports.signing import InvalidCertificate

    with pytest.raises(InvalidCertificate) as e:
        X509CertificateParser().facts("-----BEGIN CERTIFICATE-----\nno\n-----END CERTIFICATE-----\n")
    assert e.value.reason == "unreadable"
