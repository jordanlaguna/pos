"""
Subir, reemplazar y quitar las credenciales de Hacienda (T-603, T-603b, T-605).

Todo en memoria y sin Docker: es lo que pagan los puertos. Lo que se comprueba
acá no es que se guarden filas sino **el orden entre Vault y la base**, que es
lo único que no se puede deshacer leyendo el diff.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.application.ports.signing import InvalidCertificate, SigningKeyMissing
from app.application.use_cases.fe_credentials import (
    AtvUserRequired,
    ReadFeStatus,
    RemoveCertificate,
    SaveAtvCredentials,
    UploadCertificate,
)
from app.domain.errors import InvalidEnvironment
from app.domain.fe_credentials import EXPIRED, EXPIRING, MISSING, VALID
from app.domain.hacienda import PRODUCTION, SANDBOX
from app.infrastructure.clock import FixedClock
from tests.application.fakes import (
    FakeCertificateReader,
    FakeDocumentSigner,
    FakeFeCredentialsRepository,
    FakeSecretBox,
    FakeUnitOfWork,
)

AHORA = datetime(2026, 9, 13, 11, 0, 0)
COMPANIA = 7
USUARIO = 3

#: Una sola llave para toda la batería: generar RSA-2048 cuesta unas décimas de
#: segundo y acá se usa en casi todas las pruebas.
_PRIVADA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PKCS8 = _PRIVADA.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


def archivo(*, sujeto: str = "MI NEGOCIO S.A.", vence: datetime | None = None) -> bytes:
    vence = vence or (AHORA + timedelta(days=365))
    return f"P12|x|{sujeto}|{vence.isoformat()}".encode("utf-8")


@pytest.fixture
def escenario():
    class Escenario:
        def __init__(self) -> None:
            self.credenciales = FakeFeCredentialsRepository()
            self.lector = FakeCertificateReader(PKCS8)
            self.firmante = FakeDocumentSigner()
            self.cajita = FakeSecretBox()
            self.reloj = FixedClock(AHORA)
            self.uow = FakeUnitOfWork()

        @property
        def subir(self):
            return UploadCertificate(
                credentials=self.credenciales,
                reader=self.lector,
                signer=self.firmante,
                clock=self.reloj,
                uow=self.uow,
            )

        @property
        def quitar(self):
            return RemoveCertificate(
                credentials=self.credenciales,
                signer=self.firmante,
                clock=self.reloj,
                uow=self.uow,
            )

        @property
        def guardar_atv(self):
            return SaveAtvCredentials(
                credentials=self.credenciales,
                secrets=self.cajita,
                clock=self.reloj,
                uow=self.uow,
            )

        @property
        def estado(self):
            return ReadFeStatus(credentials=self.credenciales, clock=self.reloj)

    return Escenario()


class TestSubirElCertificado:
    def test_la_llave_queda_en_Vault_y_lo_publico_en_la_base(self, escenario):
        estado = escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )

        assert (COMPANIA, PRODUCTION) in escenario.firmante.llaves
        fila = escenario.credenciales.get(PRODUCTION)
        assert fila.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert fila.key_custody == "vault"
        assert estado.certificate_status == VALID

    def test_ni_el_archivo_ni_el_PIN_quedan_en_ninguna_columna(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        fila = escenario.credenciales.get(PRODUCTION)
        guardado = " ".join(str(v) for v in vars(fila).values())
        assert "1234" not in guardado
        assert "P12|" not in guardado

    def test_el_nombre_sale_del_certificado_y_no_del_archivo(self, escenario):
        # El archivo se llama como quiso quien lo bajó: «llave (1).p12» no le
        # dice nada a nadie seis meses después.
        estado = escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(sujeto="PANADERÍA LA ESPIGA S.A."),
            pin="1234",
            user_id=USUARIO,
        )
        assert estado.certificate_name == "PANADERÍA LA ESPIGA S.A."

    def test_un_PIN_que_no_abre_el_archivo_no_guarda_nada(self, escenario):
        with pytest.raises(InvalidCertificate) as e:
            escenario.subir(
                company_id=COMPANIA,
                environment=PRODUCTION,
                p12=archivo(),
                pin="mal",
                user_id=USUARIO,
            )
        assert e.value.reason == "bad_pin"
        assert escenario.credenciales.get(PRODUCTION) is None
        assert escenario.firmante.llaves == {}
        assert escenario.uow.committed is False

    def test_lo_que_no_es_un_p12_tampoco(self, escenario):
        with pytest.raises(InvalidCertificate) as e:
            escenario.subir(
                company_id=COMPANIA,
                environment=PRODUCTION,
                p12=b"esto es un .cer",
                pin="1234",
                user_id=USUARIO,
            )
        assert e.value.reason == "not_a_p12"

    def test_primero_Vault_y_despues_el_COMMIT(self, escenario):
        """El orden que no se puede deshacer leyendo el diff.

        Si Vault falla, **no puede quedar** una fila diciendo que hay
        certificado: esa fila rompería al firmar, que es el peor momento
        posible. Una llave importada sin fila, en cambio, no la nombra nadie.
        """

        class VaultCaido:
            def import_key(self, *a, **k):
                raise RuntimeError("Vault sellado")

        escenario.firmante = VaultCaido()
        with pytest.raises(RuntimeError):
            escenario.subir(
                company_id=COMPANIA,
                environment=PRODUCTION,
                p12=archivo(),
                pin="1234",
                user_id=USUARIO,
            )

        assert escenario.credenciales.get(PRODUCTION) is None
        assert escenario.uow.committed is False

    def test_un_ambiente_inventado_no_llega_ni_a_abrir_el_archivo(self, escenario):
        with pytest.raises(InvalidEnvironment):
            escenario.subir(
                company_id=COMPANIA,
                environment="produccion",
                p12=archivo(),
                pin="1234",
                user_id=USUARIO,
            )
        assert escenario.lector.leidos == 0

    def test_los_dos_ambientes_se_configuran_aparte(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=SANDBOX,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        pruebas, produccion = escenario.estado()
        assert pruebas.certificate_configured is True
        assert produccion.certificate_configured is False


class TestReemplazar:
    def test_deja_el_nuevo_y_no_hay_ventana_sin_firma(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(sujeto="EL VIEJO"),
            pin="1234",
            user_id=USUARIO,
        )
        estado = escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(sujeto="EL NUEVO"),
            pin="1234",
            user_id=USUARIO,
        )
        assert estado.certificate_name == "EL NUEVO"
        assert (COMPANIA, PRODUCTION) in escenario.firmante.llaves

    def test_no_toca_las_marcas_de_ATV(self, escenario):
        # RF-24 literal: rotar una cosa no puede hacer que la pantalla mienta
        # sobre la otra.
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="cpf-01-1234-5678@x.cr",
            password="secreta",
            user_id=USUARIO,
        )
        antes = escenario.credenciales.get(PRODUCTION).atv_updated_at

        escenario.reloj.set(AHORA + timedelta(days=180))
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )

        fila = escenario.credenciales.get(PRODUCTION)
        assert fila.atv_updated_at == antes
        assert fila.cert_uploaded_at != antes


class TestQuitar:
    def test_quita_la_fila_y_la_llave(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        estado = escenario.quitar(company_id=COMPANIA, environment=PRODUCTION)

        assert estado.certificate_status == MISSING
        with pytest.raises(SigningKeyMissing):
            escenario.firmante.sign(b"x" * 32, company_id=COMPANIA, environment=PRODUCTION)

    def test_no_borra_las_credenciales_de_transmision(self, escenario):
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="cpf-01-1234-5678@x.cr",
            password="secreta",
            user_id=USUARIO,
        )
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        estado = escenario.quitar(company_id=COMPANIA, environment=PRODUCTION)

        assert estado.atv_configured is True
        assert estado.atv_user == "cpf-01-1234-5678@x.cr"

    def test_quitar_lo_que_no_hay_deja_todo_igual(self, escenario):
        estado = escenario.quitar(company_id=COMPANIA, environment=SANDBOX)
        assert estado.certificate_status == MISSING

    def test_un_ambiente_inventado(self, escenario):
        with pytest.raises(InvalidEnvironment):
            escenario.quitar(company_id=COMPANIA, environment="prod")


class TestLasCredencialesDeATV:
    def test_la_contrasena_pasa_por_la_caja_y_el_usuario_no(self, escenario):
        """Que el cifrado de verdad no deje ver el texto se prueba en
        `test_cifrado_fe.py`, contra el AES. Acá lo que se comprueba es que el
        caso de uso **la mande a cifrar atada a esta compañía y este ambiente**,
        que es lo suyo; el doble no cifra a propósito."""
        estado = escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="cpf-01-1234-5678@x.cr",
            password="la-secreta",
            user_id=USUARIO,
        )
        guardada = escenario.credenciales.get(PRODUCTION).atv_password_encrypted
        assert guardada != "la-secreta"
        assert escenario.cajita.decrypt(
            guardada, company_id=COMPANIA, environment=PRODUCTION
        ) == "la-secreta"
        # El usuario, en cambio, se guarda tal cual y se muestra: es un
        # identificador, y sin verlo nadie puede comprobar que escribió el que
        # era (RN-16).
        assert escenario.credenciales.get(PRODUCTION).atv_user == "cpf-01-1234-5678@x.cr"
        assert estado.atv_user == "cpf-01-1234-5678@x.cr"

    def test_se_cifra_atada_a_la_compania_y_al_ambiente(self, escenario):
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="u@x.cr",
            password="p",
            user_id=USUARIO,
        )
        sellada = escenario.credenciales.get(PRODUCTION).atv_password_encrypted
        # La misma fila leída como si fuera de otra compañía no abre.
        from app.application.ports.secrets import SecretUnreadable

        with pytest.raises(SecretUnreadable):
            escenario.cajita.decrypt(sellada, company_id=99, environment=PRODUCTION)

    def test_sin_usuario_no_se_guarda(self, escenario):
        # La contraseña sola no abre nada: el IdP necesita saber a quién
        # autenticar.
        with pytest.raises(AtvUserRequired):
            escenario.guardar_atv(
                company_id=COMPANIA,
                environment=PRODUCTION,
                user="   ",
                password="p",
                user_id=USUARIO,
            )
        assert escenario.uow.committed is False

    def test_no_toca_el_certificado(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        antes = escenario.credenciales.get(PRODUCTION).cert_uploaded_at

        escenario.reloj.set(AHORA + timedelta(days=90))
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="u@x.cr",
            password="p",
            user_id=USUARIO,
        )
        assert escenario.credenciales.get(PRODUCTION).cert_uploaded_at == antes

    def test_un_ambiente_inventado(self, escenario):
        with pytest.raises(InvalidEnvironment):
            escenario.guardar_atv(
                company_id=COMPANIA,
                environment="qa",
                user="u@x.cr",
                password="p",
                user_id=USUARIO,
            )


class TestElEstadoDeLosDos:
    def test_siempre_devuelve_dos_aunque_no_haya_filas(self, escenario):
        # Con solo las filas presentes, «pruebas no está configurado» sería
        # indistinguible de «no se pudo leer».
        assert [e.environment for e in escenario.estado()] == [SANDBOX, PRODUCTION]

    def test_dice_cual_esta_listo_y_cual_no(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(),
            pin="1234",
            user_id=USUARIO,
        )
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="u@x.cr",
            password="p",
            user_id=USUARIO,
        )
        pruebas, produccion = escenario.estado()
        assert produccion.ready is True
        assert pruebas.ready is False

    def test_el_usuario_de_ATV_sin_contrasena_no_cuenta_como_configurado(self, escenario):
        # Se puede llegar ahí restaurando un respaldo: el usuario viaja y la
        # contraseña no (RN-47). La pantalla tiene que decir que falta.
        escenario.credenciales._fila(PRODUCTION).atv_user = "u@x.cr"
        _, produccion = escenario.estado()
        assert produccion.atv_user == "u@x.cr"
        assert produccion.atv_configured is False
        assert produccion.ready is False

    def test_avisa_del_vencimiento_treinta_dias_antes(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(vence=AHORA + timedelta(days=29)),
            pin="1234",
            user_id=USUARIO,
        )
        _, produccion = escenario.estado()
        assert produccion.certificate_status == EXPIRING
        assert produccion.days_left == 29

    def test_uno_vencido_se_ve_vencido(self, escenario):
        escenario.subir(
            company_id=COMPANIA,
            environment=PRODUCTION,
            p12=archivo(vence=AHORA + timedelta(days=10)),
            pin="1234",
            user_id=USUARIO,
        )
        escenario.reloj.set(AHORA + timedelta(days=20))
        _, produccion = escenario.estado()
        assert produccion.certificate_status == EXPIRED
        assert produccion.ready is False


class TestLaVerificacionNoSobrevive:
    def test_cambiar_la_contrasena_borra_la_verificacion_anterior(self, escenario):
        """Son otras credenciales, así que lo que se probó antes no dice nada.

        Sin esto, la pantalla seguiría diciendo «verificadas el 3 de
        septiembre» sobre una contraseña que se cambió hoy y que nadie probó —y
        eso es peor que no decir nada, porque invita a no probarla—.
        """
        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="u@x.cr",
            password="la-de-antes",
            user_id=USUARIO,
        )
        escenario.credenciales.mark_verified(environment=PRODUCTION, at=AHORA)
        assert escenario.estado()[1].atv_verified_at == AHORA

        escenario.guardar_atv(
            company_id=COMPANIA,
            environment=PRODUCTION,
            user="u@x.cr",
            password="la-nueva",
            user_id=USUARIO,
        )
        assert escenario.estado()[1].atv_verified_at is None
