"""
Quién firma los comprobantes (T-602, T-602b).

Una batería, dos implementaciones —el doble en memoria y Vault de verdad—, que
es el patrón de T-106. Lo que se comprueba en las dos no es que devuelvan bytes
sino **que lo firmado verifique con el certificado público**, que es lo único
que le importa a Hacienda y lo único que delata una llave equivocada.

La mitad de Vault se omite —no falla— si la pila de pruebas no está arriba.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric import utils as asimetrico

from app.application.ports.signing import SigningKeyMissing, SigningUnavailable
from app.domain.hacienda import PRODUCTION, SANDBOX
from app.infrastructure.crypto.vault_signer import VaultDocumentSigner
from tests.application.fakes import FakeDocumentSigner
from tests.conftest import marca_unica

VAULT = os.environ.get("VENTASYS_TEST_VAULT", "http://127.0.0.1:8202")
TOKEN = os.environ.get("VENTASYS_TEST_VAULT_TOKEN", "test-root-token")

pytestmark = pytest.mark.integration


def par_de_llaves(bits: int = 2048):
    """Lo que vendría adentro de un `.p12`: la privada en PKCS#8 y la pública."""
    privada = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    pkcs8 = privada.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pkcs8, privada.public_key()


def digest_de(documento: bytes) -> bytes:
    resumen = hashes.Hash(hashes.SHA256())
    resumen.update(documento)
    return resumen.finalize()


def verifica(publica, firma: bytes, digest: bytes) -> bool:
    """Lo que haría Hacienda con el `KeyInfo` del XML."""
    try:
        publica.verify(
            firma, digest, padding.PKCS1v15(), asimetrico.Prehashed(hashes.SHA256())
        )
        return True
    except Exception:  # noqa: BLE001 — cualquier fallo es «no verifica»
        return False


DIGEST = digest_de(b"<FacturaElectronica><Clave>506</Clave></FacturaElectronica>")


def _montar_transit() -> None:
    """El motor `transit`, que en modo -dev no viene montado.

    Lo monta la prueba y no el compose: así la batería no depende de que alguien
    se haya acordado de hacerlo, que es lo mismo que se pide de todo lo demás.
    """
    peticion = urllib.request.Request(
        f"{VAULT}/v1/sys/mounts/transit",
        data=json.dumps({"type": "transit"}).encode(),
        method="POST",
        headers={"X-Vault-Token": TOKEN, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(peticion, timeout=10)
    except urllib.error.HTTPError as exc:
        # 400 «path is already in use» es el estado que se quería.
        if exc.code != 400:
            raise
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"No hay Vault en {VAULT} ({exc}). Levantalo con:\n"
            "  docker compose -f docker-compose.test.yml up -d --wait vault"
        )


def _vault() -> VaultDocumentSigner:
    _montar_transit()
    return VaultDocumentSigner(VAULT, TOKEN)


#: Compañías distintas en cada prueba: las llaves de Vault sobreviven a la
#: corrida, igual que la base y el bucket, y dos pruebas sobre la misma compañía
#: se estorbarían —la que empieza segunda encontraría la llave de la primera—.
def compania() -> int:
    return int(marca_unica()[-7:])


@pytest.fixture(params=["doble", "vault"])
def firmante(request):
    return FakeDocumentSigner() if request.param == "doble" else _vault()


class TestElContrato:
    def test_lo_firmado_verifica_con_el_certificado_publico(self, firmante):
        # Es LA prueba: el certificado público se queda en la base y la privada
        # se va a Vault, así que lo único que ata a los dos es esto.
        pkcs8, publica = par_de_llaves()
        cid = compania()
        firmante.import_key(pkcs8, company_id=cid, environment=PRODUCTION)

        firma = firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)
        assert verifica(publica, firma, DIGEST)

    def test_cada_compania_firma_con_la_suya(self, firmante):
        # Lo que esto impide es emitir documentos fiscales firmados con el
        # certificado de otro cliente, que es la razón de que el nombre de la
        # llave se derive y no se guarde.
        pkcs8_uno, publica_uno = par_de_llaves()
        pkcs8_dos, _ = par_de_llaves()
        uno, dos = compania(), compania()

        firmante.import_key(pkcs8_uno, company_id=uno, environment=PRODUCTION)
        firmante.import_key(pkcs8_dos, company_id=dos, environment=PRODUCTION)

        del_otro = firmante.sign(DIGEST, company_id=dos, environment=PRODUCTION)
        assert not verifica(publica_uno, del_otro, DIGEST)

    def test_pruebas_y_produccion_son_llaves_distintas(self, firmante):
        # Con una sola, un ensayo se firmaría con el certificado de verdad.
        pkcs8_ensayo, publica_ensayo = par_de_llaves()
        pkcs8_real, _ = par_de_llaves()
        cid = compania()

        firmante.import_key(pkcs8_ensayo, company_id=cid, environment=SANDBOX)
        firmante.import_key(pkcs8_real, company_id=cid, environment=PRODUCTION)

        real = firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)
        assert not verifica(publica_ensayo, real, DIGEST)

    def test_sin_certificado_no_se_firma_y_se_dice_por_que(self, firmante):
        # `SigningKeyMissing` y no `SigningUnavailable`: la primera significa
        # «andá a cargar el certificado» y la segunda «reintentá». Confundirlas
        # deja la cola reintentando para siempre algo que no va a firmarse.
        with pytest.raises(SigningKeyMissing):
            firmante.sign(DIGEST, company_id=compania(), environment=PRODUCTION)

    def test_reemplazar_el_certificado_deja_firmando_con_el_nuevo(self, firmante):
        pkcs8_viejo, publica_vieja = par_de_llaves()
        pkcs8_nuevo, publica_nueva = par_de_llaves()
        cid = compania()

        firmante.import_key(pkcs8_viejo, company_id=cid, environment=PRODUCTION)
        firmante.import_key(pkcs8_nuevo, company_id=cid, environment=PRODUCTION)

        firma = firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)
        assert verifica(publica_nueva, firma, DIGEST)
        assert not verifica(publica_vieja, firma, DIGEST)

    def test_quitar_el_certificado_quita_la_llave(self, firmante):
        # Sin esto, quitar dejaría la fila vacía y la llave viva: el negocio
        # creería que no puede firmar y el sistema podría hacerlo.
        pkcs8, _ = par_de_llaves()
        cid = compania()
        firmante.import_key(pkcs8, company_id=cid, environment=PRODUCTION)
        firmante.forget_key(company_id=cid, environment=PRODUCTION)

        with pytest.raises(SigningKeyMissing):
            firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)

    def test_quitar_lo_que_no_esta_no_es_un_error(self, firmante):
        # Es el estado que se pedía. Y pasa de verdad: dos pestañas abiertas.
        firmante.forget_key(company_id=compania(), environment=PRODUCTION)

    def test_quitar_no_toca_el_otro_ambiente(self, firmante):
        pkcs8, publica = par_de_llaves()
        cid = compania()
        firmante.import_key(pkcs8, company_id=cid, environment=SANDBOX)
        firmante.import_key(pkcs8, company_id=cid, environment=PRODUCTION)

        firmante.forget_key(company_id=cid, environment=SANDBOX)

        firma = firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)
        assert verifica(publica, firma, DIGEST)


class TestSoloContraVault:
    def test_la_privada_no_vuelve_a_salir(self):
        """Lo que hace que esta decisión valga la pena.

        Transit no tiene endpoint de exportación para una llave importada sin
        marcarla exportable, y no se la marca. Se comprueba a propósito: es la
        única forma de saber que un cambio futuro no la habilitó sin querer.
        """
        firmante = _vault()
        pkcs8, _ = par_de_llaves()
        cid = compania()
        firmante.import_key(pkcs8, company_id=cid, environment=PRODUCTION)

        peticion = urllib.request.Request(
            f"{VAULT}/v1/transit/export/signing-key/fe-{cid}-{PRODUCTION}",
            headers={"X-Vault-Token": TOKEN},
        )
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(peticion, timeout=10)
        assert e.value.code == 400

        firmante.forget_key(company_id=cid, environment=PRODUCTION)

    def test_una_llave_que_no_es_RSA_se_rechaza_antes_de_mandarla(self):
        # Mandar un tipo que no coincide hace que Vault la acepte y falle
        # después, al firmar, con un mensaje que no menciona el tamaño.
        from cryptography.hazmat.primitives.asymmetric import ec

        curva = ec.generate_private_key(ec.SECP256R1())
        pkcs8 = curva.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with pytest.raises(SigningUnavailable) as e:
            _vault().import_key(pkcs8, company_id=compania(), environment=PRODUCTION)
        assert "RSA" in str(e.value)

    def test_con_Vault_caido_se_reintenta_y_no_se_reconfigura(self):
        # El modo de falla que la decisión de 2026-09-13 introdujo también en el
        # negocio de una sola caja: Vault sellado o abajo. Tiene que salir como
        # `SigningUnavailable` —dejá el documento en la cola— y nunca como
        # `SigningKeyMissing`, que mandaría a alguien a subir un certificado que
        # ya está.
        muerto = VaultDocumentSigner("http://127.0.0.1:9", TOKEN)
        with pytest.raises(SigningUnavailable):
            muerto.sign(DIGEST, company_id=1, environment=PRODUCTION)

    def test_la_firma_es_de_256_bytes_para_una_llave_de_2048(self):
        # PKCS#1 v1.5, que es lo que pide XAdES-EPES. El de fábrica de Vault es
        # PSS, que Hacienda no acepta, y la diferencia no se ve en el tamaño:
        # se vería el día del primer rechazo.
        firmante = _vault()
        pkcs8, publica = par_de_llaves()
        cid = compania()
        firmante.import_key(pkcs8, company_id=cid, environment=PRODUCTION)

        firma = firmante.sign(DIGEST, company_id=cid, environment=PRODUCTION)
        assert len(firma) == 256
        assert verifica(publica, firma, DIGEST)
        firmante.forget_key(company_id=cid, environment=PRODUCTION)
