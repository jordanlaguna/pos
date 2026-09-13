"""
El cifrado en reposo de la contraseña de ATV (T-602a, T-618).

Una batería, dos implementaciones, igual que el almacén de documentos: lo que
se prueba es **el contrato** y no el AES. La parte que solo tiene sentido
contra el cifrado de verdad —que el valor guardado no contenga la contraseña,
que un byte cambiado lo invalide— va en su propia clase.

Corre sin Docker: es todo en memoria.
"""

from __future__ import annotations

import base64
import os

import pytest

from app.application.ports.secrets import SecretUnreadable
from app.infrastructure.crypto.fe_crypto import (
    ENV_KEY,
    KEY_BYTES,
    NONCE_BYTES,
    AesGcmSecretBox,
    CryptoKeyMissing,
    load_key,
    secret_box,
)
from tests.application.fakes import FakeSecretBox

CLAVE = os.urandom(KEY_BYTES)

#: Una contraseña de ATV con lo que de verdad traen: tildes, símbolos y largo.
#: Hacienda no restringe el juego de caracteres, y un cifrado que se coma un
#: acento se descubre el día de transmitir.
CONTRASENA = "Contraseñ@-de-ATV_2026#árbol"


@pytest.fixture(params=["doble", "aes-gcm"])
def caja(request):
    return FakeSecretBox() if request.param == "doble" else AesGcmSecretBox(CLAVE)


class TestElContrato:
    def test_ida_y_vuelta(self, caja):
        sellado = caja.encrypt(CONTRASENA, company_id=1, environment="production")
        assert caja.decrypt(sellado, company_id=1, environment="production") == CONTRASENA

    def test_una_fila_copiada_a_otra_compania_no_abre(self, caja):
        # Es lo que verifica RF-22 y RNF-5, y la razón de que la compañía entre
        # como dato asociado en vez de quedarse solo en la fila.
        sellado = caja.encrypt(CONTRASENA, company_id=1, environment="production")
        with pytest.raises(SecretUnreadable):
            caja.decrypt(sellado, company_id=2, environment="production")

    def test_una_fila_copiada_al_otro_ambiente_tampoco(self, caja):
        # El caso menos obvio y el más probable: la misma compañía, «pasando a
        # producción» a mano con un UPDATE. Las credenciales de pruebas no valen
        # para producción, y esto lo impide en vez de dejar que fallen contra el
        # IdP el día de emitir.
        sellado = caja.encrypt(CONTRASENA, company_id=1, environment="sandbox")
        with pytest.raises(SecretUnreadable):
            caja.decrypt(sellado, company_id=1, environment="production")

    def test_un_valor_que_no_es_un_cifrado(self, caja):
        with pytest.raises(SecretUnreadable):
            caja.decrypt("cualquier cosa", company_id=1, environment="production")

    def test_una_contrasena_vacia_se_puede_guardar_y_volver(self, caja):
        # Cero caracteres es un valor, no una ausencia: quien decide si vale la
        # pena guardarlo es el caso de uso, no el cifrado.
        sellado = caja.encrypt("", company_id=1, environment="sandbox")
        assert caja.decrypt(sellado, company_id=1, environment="sandbox") == ""


class TestSoloElDeVerdad:
    def test_lo_guardado_no_contiene_la_contrasena(self):
        sellado = AesGcmSecretBox(CLAVE).encrypt(
            CONTRASENA, company_id=1, environment="production"
        )
        assert CONTRASENA not in sellado
        # Ni en el crudo: un base64 de algo sin cifrar la contendría al decodificar.
        crudo = base64.urlsafe_b64decode(sellado + "=" * (-len(sellado) % 4))
        assert CONTRASENA.encode("utf-8") not in crudo

    def test_dos_cifrados_del_mismo_valor_son_distintos(self):
        # El nonce se sortea en cada cifrado. Sin eso, dos compañías con la misma
        # contraseña tendrían la misma fila, y comparar filas diría quién la
        # comparte con quién sin descifrar nada.
        caja = AesGcmSecretBox(CLAVE)
        uno = caja.encrypt(CONTRASENA, company_id=1, environment="production")
        otro = caja.encrypt(CONTRASENA, company_id=1, environment="production")
        assert uno != otro

    def test_cambiar_un_byte_lo_invalida(self):
        # GCM autentica además de cifrar: un valor modificado falla en vez de
        # devolver basura que alguien mandaría al IdP.
        caja = AesGcmSecretBox(CLAVE)
        sellado = caja.encrypt(CONTRASENA, company_id=1, environment="production")
        crudo = bytearray(base64.urlsafe_b64decode(sellado + "=" * (-len(sellado) % 4)))
        crudo[-1] ^= 0x01
        tocado = base64.urlsafe_b64encode(bytes(crudo)).decode()

        with pytest.raises(SecretUnreadable):
            caja.decrypt(tocado, company_id=1, environment="production")

    def test_con_otra_llave_no_abre(self):
        sellado = AesGcmSecretBox(CLAVE).encrypt(
            CONTRASENA, company_id=1, environment="production"
        )
        with pytest.raises(SecretUnreadable):
            AesGcmSecretBox(os.urandom(KEY_BYTES)).decrypt(
                sellado, company_id=1, environment="production"
            )

    def test_un_valor_mas_corto_que_el_nonce(self):
        caja = AesGcmSecretBox(CLAVE)
        corto = base64.urlsafe_b64encode(b"x" * (NONCE_BYTES - 1)).decode()
        with pytest.raises(SecretUnreadable):
            caja.decrypt(corto, company_id=1, environment="production")


class TestLaLlaveDelEntorno:
    """T-618: el arranque falla si no está o no mide 32 bytes."""

    def test_la_que_genera_el_comando_del_README_sirve(self):
        import secrets

        assert len(load_key(secrets.token_urlsafe(32))) == KEY_BYTES

    @pytest.mark.parametrize("valor", [None, ""])
    def test_sin_llave_no_arranca(self, valor):
        with pytest.raises(CryptoKeyMissing) as e:
            load_key(valor)
        # El mensaje trae el comando que la genera: quien despliega está viendo
        # un contenedor que no levanta, no la documentación.
        assert "token_urlsafe" in str(e.value)

    def test_una_llave_corta_no_arranca(self):
        # 16 bytes también es una llave de AES válida, y daría cifrado más débil
        # sin que nada avise. Por eso se comprueba el tamaño y no solo que abra.
        corta = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
        with pytest.raises(CryptoKeyMissing) as e:
            load_key(corta)
        assert "16" in str(e.value)

    def test_una_llave_que_no_es_base64(self):
        with pytest.raises(CryptoKeyMissing):
            load_key("no es base64 ni de lejos!!!")

    def test_la_caja_se_arma_del_entorno(self, monkeypatch):
        monkeypatch.setenv(ENV_KEY, base64.urlsafe_b64encode(CLAVE).decode().rstrip("="))
        caja = secret_box()
        sellado = caja.encrypt("x", company_id=1, environment="sandbox")
        assert caja.decrypt(sellado, company_id=1, environment="sandbox") == "x"

    def test_sin_la_variable_el_armado_se_cae(self, monkeypatch):
        monkeypatch.delenv(ENV_KEY, raising=False)
        with pytest.raises(CryptoKeyMissing):
            secret_box()

    def test_una_llave_de_32_bytes_construida_a_mano_tambien(self):
        # Quien despliega puede generarla con `openssl rand -base64 32`, que sí
        # pone el relleno. Las dos formas tienen que servir.
        con_relleno = base64.urlsafe_b64encode(CLAVE).decode()
        assert con_relleno.endswith("=")
        assert load_key(con_relleno) == CLAVE
