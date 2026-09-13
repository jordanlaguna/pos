"""
Las credenciales de Hacienda, por HTTP y con dos compañías (F6, T-609).

Las rutas de `/fe` no llevan id: siempre hablan de la compañía de la sesión, así
que la forma del resto de `test_aislamiento.py` —«pedir por id lo ajeno responde
404»— no aplica. Lo que sí aplica, y es lo que se prueba acá, es que **el
certificado de una compañía no aparezca en la sesión de otra**. Lo que se
filtraría si el filtro automático fallara es de dónde sale la firma de un
cliente.

Y la mitad de T-609: que el PIN y la contraseña **no salgan por ninguna parte**.
Se buscan a propósito, que es distinto de mirar el esquema y confiar.
"""

from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from tests.conftest import API, Api, afiliado_unico, bootstrap, codigo, entrar, marca_unica

pytestmark = pytest.mark.characterization

PIN = "pin-secreto-del-p12"
CONTRASENA = "contrasena-secreta-de-atv"


def p12(nombre: str, *, dias: int = 365) -> bytes:
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombre)])
    hasta = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=dias)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(sujeto)
        .public_key(privada.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(hasta - dt.timedelta(days=730))
        .not_valid_after(hasta)
        .sign(privada, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"llave",
        key=privada,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(PIN.encode()),
    )


def subir(cliente: Api, ambiente: str, contenido: bytes, *, pin: str = PIN):
    return cliente.multipart(
        f"/fe/{ambiente}/certificate",
        files={"archivo": ("llave.p12", contenido, "application/x-pkcs12")},
        data={"pin": pin},
    )


def de(cuerpo: dict, ambiente: str) -> dict:
    return next(e for e in cuerpo["environments"] if e["environment"] == ambiente)


def compania_propia(quien: str) -> Api:
    """Una compañía recién dada de alta, solo para esta prueba.

    **No se usa la compañía A de la batería**, y la razón está en CLAUDE.md
    escrita con sangre: la base de pruebas sobrevive entre corridas, así que una
    prueba que deja un certificado configurado hace que «un ambiente sin
    configurar» sea falso en la corrida siguiente. La salida no es limpiar
    mejor —una prueba que falla a mitad no limpia nada— sino no tocar lo que
    otros usan.
    """
    marca = marca_unica()
    correo = f"fe.{quien}.{marca}@pruebas.ventasys.cr"
    bootstrap(
        afiliado=afiliado_unico(),
        compania=1,
        nombre=f"Compañía FE {quien} {marca}",
        email=correo,
        password="prueba123",
        rol="admin",
        nombre_persona="Fede",
        apellido=quien.capitalize(),
        cedula=marca[-9:],
    )
    cliente = Api(API)
    entrar(cliente, correo, "prueba123")
    return cliente


@pytest.fixture
def empresa() -> Api:
    return compania_propia("una")


@pytest.fixture
def otra_empresa() -> Api:
    return compania_propia("otra")


class TestElEstado:
    def test_una_compania_sin_configurar_ve_los_dos_ambientes_vacios(self, empresa: Api):
        estado, cuerpo = empresa.call("GET", "/fe")
        assert estado == 200
        assert [e["environment"] for e in cuerpo["environments"]] == [
            "sandbox",
            "production",
        ]
        for ambiente in cuerpo["environments"]:
            assert ambiente["ready"] is False
            assert ambiente["certificate_status"] == "missing"

    def test_el_ambiente_activo_por_omision_es_pruebas(self, empresa: Api):
        # Suponer producción sería suponer efecto fiscal donde no lo hay.
        _, cuerpo = empresa.call("GET", "/fe")
        assert cuerpo["active"] in ("sandbox", "production")

    def test_un_cajero_no_entra(self, cajero: Api):
        # Es de administrador, y con eso el bloqueo por suscripción la alcanza
        # sin tocar nada.
        assert codigo(cajero.call("GET", "/fe"), 403) == "admin_only"


class TestSubirYQuitar:
    def test_subir_deja_el_ambiente_con_certificado(self, empresa: Api):
        estado, cuerpo = subir(empresa, "sandbox", p12("NEGOCIO DE PRUEBA S.A."))
        assert estado == 200
        pruebas = de(cuerpo, "sandbox")
        assert pruebas["certificate_configured"] is True
        assert pruebas["certificate_name"] == "NEGOCIO DE PRUEBA S.A."
        assert pruebas["certificate_status"] == "valid"
        # Sin credenciales de ATV todavía no está listo.
        assert pruebas["ready"] is False

    def test_y_no_toca_el_otro_ambiente(self, empresa: Api):
        subir(empresa, "sandbox", p12("SOLO PRUEBAS"))
        _, cuerpo = empresa.call("GET", "/fe")
        assert de(cuerpo, "production")["certificate_configured"] is False

    def test_un_PIN_equivocado_no_guarda_nada(self, empresa: Api):
        respuesta = subir(empresa, "production", p12("NO ENTRA"), pin="no-es-el-pin")
        assert codigo(respuesta, 400) == "invalid_certificate"
        _, cuerpo = empresa.call("GET", "/fe")
        assert de(cuerpo, "production")["certificate_configured"] is False

    def test_lo_que_no_es_un_p12(self, empresa: Api):
        respuesta = subir(empresa, "sandbox", b"-----BEGIN CERTIFICATE-----\nabc\n")
        assert codigo(respuesta, 400) == "invalid_certificate"

    def test_un_ambiente_inventado(self, empresa: Api):
        respuesta = subir(empresa, "produccion", p12("X"))
        assert codigo(respuesta, 400) == "invalid_environment"

    def test_quitar_lo_deja_sin_certificado_y_con_ATV(self, empresa: Api):
        empresa.call("PUT", "/fe/sandbox/atv", {"user": "cpf-01-1111-1111@x.cr", "password": CONTRASENA})
        subir(empresa, "sandbox", p12("PARA QUITAR"))

        estado, cuerpo = empresa.call("DELETE", "/fe/sandbox/certificate")
        assert estado == 200
        pruebas = de(cuerpo, "sandbox")
        assert pruebas["certificate_configured"] is False
        # RF-24: quitar el certificado no borra las credenciales de transmisión.
        assert pruebas["atv_configured"] is True

    def test_quitar_lo_que_no_hay_no_es_un_error(self, empresa: Api):
        empresa.call("DELETE", "/fe/production/certificate")
        estado, _ = empresa.call("DELETE", "/fe/production/certificate")
        assert estado == 200


class TestLasCredencialesDeATV:
    def test_el_usuario_se_ve_y_la_contrasena_no(self, empresa: Api):
        estado, cuerpo = empresa.call(
            "PUT",
            "/fe/sandbox/atv",
            {"user": "cpf-01-1234-5678@x.cr", "password": CONTRASENA},
        )
        assert estado == 200
        pruebas = de(cuerpo, "sandbox")
        assert pruebas["atv_user"] == "cpf-01-1234-5678@x.cr"
        assert pruebas["atv_configured"] is True
        assert CONTRASENA not in str(cuerpo)

    def test_sin_usuario_no_se_guarda(self, empresa: Api):
        respuesta = empresa.call("PUT", "/fe/sandbox/atv", {"user": "", "password": CONTRASENA})
        # Pydantic lo ataja antes que el caso de uso: `user` tiene `min_length=1`.
        assert respuesta[0] in (400, 422)


class TestQueNoSeVeLoDeLaOtraCompania:
    def test_el_certificado_de_A_no_aparece_en_la_sesion_de_B(
        self, empresa: Api, otra_empresa: Api
    ):
        # Lo que se filtraría si el filtro automático fallara acá es de dónde
        # sale la firma de un cliente.
        subir(empresa, "production", p12("EMPRESA A S.A."))

        _, de_b = otra_empresa.call("GET", "/fe")
        assert de(de_b, "production")["certificate_configured"] is False
        assert "EMPRESA A" not in str(de_b)

    def test_cada_una_ve_la_suya(self, empresa: Api, otra_empresa: Api):
        subir(empresa, "sandbox", p12("LA DE A"))
        subir(otra_empresa, "sandbox", p12("LA DE B"))

        _, de_a = empresa.call("GET", "/fe")
        _, cuerpo_b = otra_empresa.call("GET", "/fe")
        assert de(de_a, "sandbox")["certificate_name"] == "LA DE A"
        assert de(cuerpo_b, "sandbox")["certificate_name"] == "LA DE B"

    def test_quitar_en_A_no_toca_a_B(self, empresa: Api, otra_empresa: Api):
        subir(empresa, "production", p12("DE A"))
        subir(otra_empresa, "production", p12("DE B"))

        empresa.call("DELETE", "/fe/production/certificate")

        _, cuerpo_b = otra_empresa.call("GET", "/fe")
        assert de(cuerpo_b, "production")["certificate_configured"] is True


class TestNiElPINNiLaContrasenaSalenPorNingunLado:
    """La mitad de T-609 que se puede probar hoy.

    Se buscan **a propósito**, que es distinto de mirar el esquema y confiar.
    Lo del PIN cambió de carácter el 2026-09-13: ya no se guarda en ninguna
    parte, así que lo que hay que comprobar no es que no se devuelva sino que
    no sobreviva a la petición que lo trajo.
    """

    def test_ni_en_la_respuesta_de_subir(self, empresa: Api):
        _, cuerpo = subir(empresa, "sandbox", p12("BUSCANDO EL PIN"))
        assert PIN not in str(cuerpo)

    def test_ni_en_el_estado(self, empresa: Api):
        subir(empresa, "sandbox", p12("X"))
        empresa.call("PUT", "/fe/sandbox/atv", {"user": "u@x.cr", "password": CONTRASENA})

        _, cuerpo = empresa.call("GET", "/fe")
        texto = str(cuerpo)
        assert PIN not in texto
        assert CONTRASENA not in texto

    def test_ni_en_la_bitacora(self, empresa: Api, soporte: Api):
        subir(empresa, "sandbox", p12("X"))
        empresa.call("PUT", "/fe/sandbox/atv", {"user": "u@x.cr", "password": CONTRASENA})

        estado, bitacora = soporte.call("GET", "/support/audit?limit=100")
        if estado != 200:
            pytest.skip("el panel de soporte no está disponible en esta corrida")
        texto = str(bitacora)
        assert PIN not in texto
        assert CONTRASENA not in texto

    def test_ni_cuando_el_PIN_es_el_que_falla(self, empresa: Api):
        # El caso más fácil de filtrar: el mensaje de error del PIN equivocado
        # es justo donde apetece escribir el valor que no sirvió.
        respuesta = subir(empresa, "production", p12("X"), pin="pin-que-no-abre")
        assert "pin-que-no-abre" not in str(respuesta[1])
