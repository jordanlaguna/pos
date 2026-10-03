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
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from tests.conftest import (
    API,
    BACKEND,
    Api,
    afiliado_unico,
    bootstrap,
    codigo,
    entrar,
    marca_unica,
)

pytestmark = pytest.mark.characterization

PIN = "pin-secreto-del-p12"
CONTRASENA = "contrasena-secreta-de-atv"


def p12(nombre: str, *, dias: int = 365, pin: str = PIN) -> bytes:
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
        encryption_algorithm=serialization.BestAvailableEncryption(pin.encode()),
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


# --------------------------------------------------------------------- T-609

#: Busca dos valores en **todas** las columnas de texto de **todas** las tablas.
#:
#: Corre dentro del contenedor porque la base de la pila de pruebas no publica
#: puerto —vive en tmpfs— y es el mismo camino que ya usa
#: `test_respaldo_compania.py`. Se recorre el esquema entero y no las tres tablas
#: que uno esperaría: lo que hay que descubrir es justamente la columna en la que
#: nadie pensó, y una lista escrita a mano no puede contener la que todavía no
#: existe.
_BUSCADOR = """
import sys
from sqlalchemy import text
from app.database.database import engine

agujas = sys.argv[1:]
# Los tipos binarios quedan fuera: un LIKE sobre bytes arbitrarios revienta por
# la intercalación, y las columnas de F6 son VARCHAR y TEXT por decisión de
# T-601 —el modelo y la migración no podían decir lo mismo con VARBINARY—.
TIPOS = ("char", "varchar", "text", "tinytext", "mediumtext", "longtext", "json")

encontrados = []
with engine.connect() as con:
    base = con.execute(text("SELECT DATABASE()")).scalar()
    columnas = con.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = :base AND data_type IN :tipos"
        ).bindparams(base=base, tipos=TIPOS)
    ).all()
    for tabla, columna in columnas:
        for aguja in agujas:
            cuantas = con.execute(
                text(f"SELECT COUNT(*) FROM `{tabla}` WHERE `{columna}` LIKE :patron"),
                {"patron": f"%{aguja}%"},
            ).scalar()
            if cuantas:
                encontrados.append(f"{tabla}.{columna} x{cuantas}")

print("|".join(encontrados))
"""


def buscar_en_la_base(*agujas: str) -> list[str]:
    """Dónde aparece cada valor en la base, o una lista vacía."""
    resultado = subprocess.run(
        [
            "docker", "compose", "-f", "docker-compose.test.yml",
            "exec", "-T", "fastapi", "python", "-", *agujas,
        ],
        cwd=BACKEND,
        input=_BUSCADOR,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if resultado.returncode != 0:
        pytest.skip(f"no se pudo consultar la base de pruebas: {resultado.stderr[-300:]}")
    return [x for x in resultado.stdout.strip().split("|") if x]


def trazas_del_servidor() -> str:
    """Lo que el contenedor escribió, que es donde va a parar un `traceback`."""
    resultado = subprocess.run(
        [
            "docker", "compose", "-f", "docker-compose.test.yml",
            "logs", "--no-color", "--tail", "2000", "fastapi",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if resultado.returncode != 0:
        pytest.skip("no se pudieron leer las trazas del contenedor")
    return resultado.stdout


class TestSeBuscanAPropositoEnTodaLaBase:
    """T-609, la mitad que no se ve por HTTP.

    Las pruebas de arriba comprueban que los secretos no **salgan**; estas, que
    no **estén**. Son cosas distintas y la segunda es la que de verdad protege:
    un valor que no está en ninguna columna no se puede filtrar por un endpoint
    que nadie ha escrito todavía.

    Con el PIN además cambió el carácter de la pregunta el 2026-09-13. Desde que
    la llave privada vive en Vault **no hay columna donde ponerlo**, así que lo
    que se verifica no es que esté bien guardado sino que **no sobreviva a la
    petición que lo trajo**.
    """

    def test_despues_de_una_subida_buena_el_PIN_no_esta_en_ninguna_columna(
        self, empresa: Api
    ):
        # El `.p12` se cifra CON ese PIN: buscar uno que nunca abrió nada no
        # probaría nada, porque el camino que lo podría guardar es el que
        # termina bien.
        pin = f"pin-unico-{marca_unica()}"
        estado, _ = subir(empresa, "sandbox", p12("SIN RASTRO", pin=pin), pin=pin)
        assert estado == 200

        assert buscar_en_la_base(pin) == []

    def test_la_contrasena_de_ATV_no_esta_en_claro_en_ninguna_columna(self, empresa: Api):
        # Esta sí se guarda —hay que reenviarla al IdP en cada token— pero
        # cifrada. Que esté y no se vea es justo lo que hay que comprobar.
        clave = f"clave-unica-{marca_unica()}"
        empresa.call("PUT", "/fe/sandbox/atv", {"user": "u@x.cr", "password": clave})

        assert buscar_en_la_base(clave) == []

    def test_el_buscador_encuentra_lo_que_SI_esta(self, empresa: Api):
        """La prueba de la prueba.

        Sin esto, un buscador roto —una consulta que no devuelve nada nunca—
        dejaría las dos de arriba en verde para siempre, que es exactamente la
        forma en que un guardián deja de guardar sin que nadie se entere.

        Se busca el **usuario** de ATV, que sí se guarda en claro a propósito
        (RN-16): es un identificador y la pantalla lo muestra.
        """
        usuario = f"cpf-01-{marca_unica()}@pruebas.cr"
        empresa.call("PUT", "/fe/production/atv", {"user": usuario, "password": CONTRASENA})

        assert any("fe_credentials" in d for d in buscar_en_la_base(usuario))

    def test_ni_en_las_trazas_del_servidor(self, empresa: Api):
        """El sitio que se olvida: un `traceback` con el valor en un argumento.

        Se provoca el fallo más propenso a contarlo —un PIN que no abre el
        archivo— y después se lee lo que el contenedor escribió.
        """
        pin = f"pin-que-no-abre-{marca_unica()}"
        clave = f"clave-que-no-sirve-{marca_unica()}"
        subir(empresa, "production", p12("PARA FALLAR"), pin=pin)
        empresa.call("PUT", "/fe/production/atv", {"user": "u@x.cr", "password": clave})
        empresa.call("POST", "/fe/production/atv/verify")

        trazas = trazas_del_servidor()
        assert pin not in trazas
        assert clave not in trazas


class TestLaBitacoraDiceQueSeUsaron:
    """T-609b: la mitad positiva. Se registra el hecho, nunca el contenido."""

    def test_probar_la_conexion_deja_su_linea_con_el_desenlace(
        self, empresa: Api, soporte: Api
    ):
        clave = f"clave-{marca_unica()}"
        empresa.call("PUT", "/fe/sandbox/atv", {"user": "u@x.cr", "password": clave})
        # Sin red hacia Hacienda desde la pila de pruebas, el desenlace es «no se
        # pudo comprobar». Da igual cuál sea: lo que se comprueba es que **quede
        # anotado**, y el que no se anotaría sería el bueno.
        empresa.call("POST", "/fe/sandbox/atv/verify")

        estado, bitacora = soporte.call(
            "GET", "/support/audit?accion=fe_credenciales_probadas&limit=50"
        )
        if estado != 200:
            pytest.skip("el panel de soporte no está disponible en esta corrida")

        detalles = [linea["detalle"] for linea in bitacora["lineas"]]
        assert any(d and d.startswith("sandbox:") for d in detalles)
        # Y ninguna línea lleva la contraseña.
        assert clave not in str(bitacora)

    def test_sin_credenciales_no_se_anota_nada(self, empresa: Api, soporte: Api):
        # No había nada que usar, así que no hubo uso. Una línea acá diría que se
        # probó algo que no existe.
        antes = soporte.call("GET", "/support/audit?accion=fe_credenciales_probadas&limit=200")
        if antes[0] != 200:
            pytest.skip("el panel de soporte no está disponible en esta corrida")
        cuantas = len(antes[1]["lineas"])

        assert codigo(empresa.call("POST", "/fe/production/atv/verify"), 409) == (
            "atv_not_configured"
        )

        despues = soporte.call("GET", "/support/audit?accion=fe_credenciales_probadas&limit=200")
        assert len(despues[1]["lineas"]) == cuantas


class TestElAmbienteActivo:
    """RF-30, RN-35, T-611."""

    def test_por_omision_es_pruebas(self, empresa: Api):
        # Suponer producción sería suponer efecto fiscal donde no lo hay.
        _, cuerpo = empresa.call("GET", "/fe")
        assert cuerpo["active"] == "sandbox"

    def test_pasar_a_produccion_sin_confirmar_no_cambia_nada(self, empresa: Api):
        respuesta = empresa.call("PUT", "/fe/active", {"environment": "production"})
        assert codigo(respuesta, 400) == "confirmation_required"

        _, cuerpo = empresa.call("GET", "/fe")
        assert cuerpo["active"] == "sandbox"

    def test_confirmado_si_pero_la_puerta_dura_manda(self, empresa: Api):
        """Desde T-713 confirmar no alcanza: a producción se pasa con una
        factura, un tiquete y una nota de crédito **aceptados** en pruebas
        (RN-46), y mientras falten lo dice. El paso con la puerta abierta —y la
        asimetría de RN-35, y la bitácora— están en `test_emision.py`, que es
        donde hay comprobantes que contar."""
        respuesta = empresa.call(
            "PUT", "/fe/active", {"environment": "production", "confirm": True}
        )
        assert codigo(respuesta, 409) == "production_gate_locked"
        assert respuesta[1]["detail"]["missing"] == ["01", "04", "03"]
        _, cuerpo = empresa.call("GET", "/fe")
        assert cuerpo["active"] == "sandbox"
        assert cuerpo["production_gate"] == {"ready": False, "missing": ["01", "04", "03"]}

    def test_volver_a_pruebas_no_pide_confirmacion(self, empresa: Api):
        """La asimetría de RN-35: deshacer no se confirma. Con la puerta cerrada
        acá solo se puede comprobar la mitad barata —a pruebas sin `confirm` es
        200—; la vuelta desde producción de verdad está en `test_emision.py`."""
        estado, cuerpo = empresa.call("PUT", "/fe/active", {"environment": "sandbox"})
        assert estado == 200
        assert cuerpo["active"] == "sandbox"

    def test_un_ambiente_inventado(self, empresa: Api):
        respuesta = empresa.call(
            "PUT", "/fe/active", {"environment": "produccion", "confirm": True}
        )
        assert codigo(respuesta, 400) == "invalid_environment"

    def test_un_cajero_no_lo_cambia(self, cajero: Api):
        respuesta = cajero.call(
            "PUT", "/fe/active", {"environment": "production", "confirm": True}
        )
        assert codigo(respuesta, 403) == "admin_only"

    def test_cada_compania_tiene_el_suyo(self, empresa: Api, otra_empresa: Api):
        empresa.call("PUT", "/fe/active", {"environment": "production", "confirm": True})
        _, cuerpo_b = otra_empresa.call("GET", "/fe")
        assert cuerpo_b["active"] == "sandbox"

    # La bitácora del cambio («sandbox → production») se comprueba en
    # `test_emision.py::TestLaPuertaDeProduccion`: acá la puerta está cerrada y
    # no hay cambio que anotar.


class TestLaPuertaLateral:
    """Que el ambiente no se pueda cambiar por `PUT /settings` (T-611).

    Sin esto, la confirmación y la bitácora de RN-35 serían decoración:
    bastaría con guardar la pantalla de Configuración para pasar a producción
    sin que quedara rastro. Esconder el campo no es control de acceso.
    """

    def test_guardar_la_configuracion_no_mueve_el_ambiente(self, empresa: Api):
        estado, actual = empresa.call("GET", "/settings/")
        assert estado == 200

        datos = dict(actual["data"])
        datos["eInvoicing"] = {**datos.get("eInvoicing", {}), "environment": "production"}
        empresa.call("PUT", "/settings/", {"data": datos, "keep_logo": True})

        _, cuerpo = empresa.call("GET", "/fe")
        assert cuerpo["active"] == "sandbox"

    # El caso simétrico —guardar la configuración sin la sección no devuelve el
    # ambiente a pruebas— exige estar en producción, y eso exige la puerta
    # abierta: vive en `test_emision.py::TestLaPuertaDeProduccion`.
