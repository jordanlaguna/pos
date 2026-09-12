"""El panel de soporte, de punta a punta (F3, T-301 a T-307, T-309).

Es la prueba que decide si F3 sirve: que soporte pueda dar de alta un cliente y
operarlo, que **no** pueda ver datos de nadie sin entrar como esa compañía, y
que entrar deje rastro.

Lo que se comprueba acá y no se puede comprobar en el dominio: que el token de
soporte no abra el POS, que el de suplantación no escriba, y que cada acción
quede en la bitácora. Son propiedades de la puerta, no de la aritmética.
"""

from __future__ import annotations

import ast
import base64
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from .conftest import SOPORTE, Api, bootstrap, marca_unica

pytestmark = pytest.mark.characterization

HOY = date.today()
APP = Path(__file__).resolve().parent.parent / "app"


def cuerpo_del_token(token: str) -> dict:
    """El payload del JWT, sin verificar la firma.

    Verificar es tarea del backend; acá se lee para comprobar lo que el token
    **dice**: su tipo, su vigencia y el motivo. Es la única forma de probar que
    un *entrar como* dura media hora sin esperar media hora.
    """
    trozo = token.split(".")[1]
    relleno = "=" * (-len(trozo) % 4)
    return json.loads(base64.urlsafe_b64decode(trozo + relleno))


def nueva_compania(soporte: Api, plan_id: int, **extra) -> dict:
    """Da de alta una compañía de prueba y devuelve la respuesta del alta."""
    marca = marca_unica()
    datos = {
        "nombre": f"Cliente {marca}",
        "plan_id": plan_id,
        "admin": {
            "email": f"dueno.{marca}@pruebas.ventasys.cr",
            "password": "prueba123",
            "name": "Dueña",
            "lastName": "Nueva",
            "identification": f"7{marca}",
        },
    }
    datos.update(extra)
    return soporte.ok("POST", "/support/companies", datos)


def _plan(soporte: Api, nombre: str, **limites) -> dict:
    """Se asegura de que exista un plan con esos límites y lo devuelve.

    Los planes no se crean por la API a propósito —un plan es una decisión
    comercial y no un recurso más—, así que se crean con `bootstrap.py`, que es
    el mismo camino de una instalación de verdad. Hace falta una compañía que lo
    use, y esa compañía es el efecto colateral aceptado de la maniobra.
    """
    marca = abs(hash(nombre)) % 900 + 90
    bootstrap(
        afiliado=marca,
        compania=1,
        nombre=f"Compañía de {nombre}",
        email=f"plan.{marca}@pruebas.ventasys.cr",
        password="prueba123",
        plan=nombre,
        **limites,
    )
    planes = soporte.ok("GET", "/support/plans")
    encontrado = next((p for p in planes if p["nombre"] == nombre), None)
    assert encontrado, f"no se pudo crear el plan «{nombre}»: {[p['nombre'] for p in planes]}"
    return encontrado


@pytest.fixture(scope="module")
def plan_normal(soporte: Api) -> dict:
    """Un plan con límites de verdad, con el que se dan de alta las compañías.

    No sirve el de `conftest`: ese no limita nada —porque la batería crea un
    cajero por prueba— y con un plan sin techo no se puede comprobar que el
    cupo se muestre.
    """
    return _plan(
        soporte,
        "Comercio de pruebas",
        plan_max_sucursales=1,
        plan_max_terminales=3,
        plan_max_usuarios=5,
    )


@pytest.fixture(scope="module")
def plan_id(plan_normal: dict) -> int:
    return plan_normal["id"]


# --------------------------------------------------------------------------
# T-301, T-302 · Quién entra al panel y quién no
# --------------------------------------------------------------------------


class TestLaPuertaDelPanel:
    def test_sin_token_no_se_entra(self, soporte: Api):
        estado, _ = soporte.call("GET", "/support/companies", token=None)
        assert estado == 401

    def test_el_administrador_de_una_compania_recibe_403(self, api: Api):
        """T-302: el panel no es para los clientes.

        403 y no 401: el token vale, lo que no vale es para esto. Un 401 le
        diría al POS «volvé a entrar», y volver a entrar no convierte a un
        administrador en soporte.
        """
        for ruta in ("/support/companies", "/support/plans", "/support/audit", "/support/me"):
            estado, cuerpo = api.call("GET", ruta)
            assert estado == 403, f"{ruta} respondió {estado}"
            assert cuerpo["detail"]["code"] == "support_only"

    def test_soporte_no_puede_operar_el_pos(self, soporte: Api):
        """T-302, la otra mitad: sin compañía no hay negocio que operar.

        Es el estado que el filtro de `tenancy.py` hace imposible por diseño: un
        token sin compañía no puede leer una tabla de negocio, así que la
        respuesta correcta es 401 antes de llegar a la base.
        """
        for metodo, ruta in (
            ("GET", "/users/me"),
            ("GET", "/products/products_list"),
            ("GET", "/sales/sales_list"),
            ("GET", "/settings/"),
        ):
            estado, cuerpo = soporte.call(metodo, ruta)
            assert estado == 401, f"{ruta} respondió {estado}"
            assert cuerpo["detail"]["code"] == "no_company_in_token"

    def test_soporte_se_reconoce_sin_compania(self, soporte: Api):
        yo = soporte.ok("GET", "/support/me")
        assert yo["is_support"] is True
        assert yo["email"] == SOPORTE["email"]
        # No hay `company_id` en la respuesta, y eso es el diseño (RN-4): no
        # existe un número que poner ahí.
        assert "company_id" not in yo


# --------------------------------------------------------------------------
# T-303 · El listado (RF-5)
# --------------------------------------------------------------------------


class TestElListado:
    def test_lista_todas_las_companias_con_su_plan_y_su_estado(self, soporte: Api):
        companias = soporte.ok("GET", "/support/companies")
        assert len(companias) >= 2, "tienen que verse las dos compañías de prueba"

        for c in companias:
            assert c["plan"] is not None, f"{c['nombre']} quedó sin plan"
            assert c["suscripcion"]["estado"]
            assert isinstance(c["suscripcion"]["puede_vender"], bool)
            assert "usuarios" in c["uso"]

    def test_el_uso_cuenta_lo_de_cada_compania_y_no_lo_de_todas(self, soporte: Api, api: Api):
        """La trampa de `count`: sumar las filas de todo el mundo en cada fila.

        Se comprueba con los productos, que es donde más se nota: si el conteo
        cruzara compañías, las dos tendrían el mismo número.
        """
        companias = {c["id"]: c for c in soporte.ok("GET", "/support/companies")}
        productos_de_a = len(api.ok("GET", "/products/products_list"))
        assert companias[api.company_id]["uso"]["productos"] == productos_de_a

    def test_una_compania_que_no_existe_es_404(self, soporte: Api):
        estado, cuerpo = soporte.call("GET", "/support/companies/999999")
        assert estado == 404
        assert cuerpo["detail"]["code"] == "company_not_found"


# --------------------------------------------------------------------------
# T-304 · El alta (RF-6)
# --------------------------------------------------------------------------


class TestElAlta:
    def test_queda_todo_lo_que_hace_falta_para_vender(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)

        assert alta["branch_codigo"] == "001"
        assert alta["terminal_codigo"] == "00001"
        assert alta["usuario_nuevo"] is True
        assert alta["membresia_pendiente"] is False

        # Y el administrador puede entrar de una: una compañía a la que hay que
        # arreglarle algo a mano después del alta no está dada de alta.
        cliente = Api(soporte.base)
        sesion = cliente.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        assert sesion["tipo"] == "sesion"
        cliente.token = sesion["access_token"]
        yo = cliente.ok("GET", "/users/me")
        assert yo["role"] == "admin"
        assert yo["company_id"] == alta["company_id"]
        # La sucursal y la caja llegan al token, que es lo que hace que se pueda
        # abrir caja y vender sin configurar nada.
        assert yo["branch_code"] == "001"
        assert yo["terminal_code"] == "00001"

    def test_el_par_afiliado_compania_se_calcula_solo(self, soporte: Api, plan_id: int):
        primera = nueva_compania(soporte, plan_id)
        segunda = nueva_compania(soporte, plan_id)
        assert segunda["afiliado"] > primera["afiliado"], (
            "un cliente nuevo es un afiliado nuevo"
        )

        # Y la segunda compañía del mismo cliente toma el número siguiente.
        otra = nueva_compania(soporte, plan_id, afiliado=primera["afiliado"])
        assert otra["afiliado"] == primera["afiliado"]
        assert otra["compania"] == primera["compania"] + 1

    def test_el_par_repetido_es_un_conflicto(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        estado, cuerpo = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "La misma otra vez",
                "plan_id": plan_id,
                "afiliado": alta["afiliado"],
                "compania": alta["compania"],
                "admin": {"email": "otro@pruebas.ventasys.cr", "password": "prueba123"},
            },
        )
        assert estado == 409
        assert cuerpo["detail"]["code"] == "company_already_exists"

    def test_los_textos_del_documento_los_siembra_el_pos(self, soporte: Api, plan_id: int):
        """T-304 y RN-30 al mismo tiempo.

        Los textos del tiquete nacen vacíos (T-816) y el backend no puede
        escribirlos: no tiene catálogo y no sabe en qué idioma. Así que vienen en
        el alta, ya resueltos por el POS, y lo que se comprueba acá es que se
        guardan tal cual y que la compañía nueva los ve.
        """
        gracias = "Obrigado pela sua compra!"
        alta = nueva_compania(
            soporte,
            plan_id,
            locale="pt",
            document_locale="pt",
            settings={"document": {"thanksMessage": gracias}},
        )

        cliente = Api(soporte.base)
        sesion = cliente.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        cliente.token = sesion["access_token"]

        guardada = cliente.ok("GET", "/settings/")
        assert guardada["data"]["document"]["thanksMessage"] == gracias
        # Y el idioma de la compañía llegó al token, así que la pantalla abre en
        # portugués sin que nadie la configure.
        assert cuerpo_del_token(sesion["access_token"])["loc"] == "pt"

    def test_un_correo_que_ya_existe_no_crea_otra_cuenta(self, soporte: Api, plan_id: int):
        """El caso del contador: una identidad, varias membresías (RN-3).

        Y la membresía nace **pendiente** (T-229): soporte puede sumar a alguien
        que ya trabaja en otra compañía, pero no puede darle acceso a su nombre.

        El correo que se reutiliza es el de una compañía que crea esta misma
        prueba, y no el del administrador de `conftest`: una invitación pendiente
        le queda en la lista para el resto de la corrida, y
        `test_invitaciones.py` comprueba justamente que el suyo no tenga
        ninguna. Una prueba que le deja basura a otra falla en la otra.
        """
        primera = nueva_compania(soporte, plan_id)

        alta = nueva_compania(
            soporte,
            plan_id,
            admin={"email": primera["email"], "password": "no-se-usa-123"},
        )
        assert alta["usuario_nuevo"] is False
        assert alta["membresia_pendiente"] is True
        assert alta["email"] == primera["email"]
        assert alta["company_id"] != primera["company_id"]

    def test_no_se_puede_hacer_administrador_a_soporte(self, soporte: Api, plan_id: int):
        estado, cuerpo = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "Compañía imposible",
                "plan_id": plan_id,
                "admin": {"email": SOPORTE["email"], "password": "prueba123"},
            },
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "support_cannot_be_member"

    def test_un_plan_que_no_existe_es_404(self, soporte: Api):
        estado, cuerpo = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "Sin plan",
                "plan_id": 999999,
                "admin": {"email": "sinplan@pruebas.ventasys.cr", "password": "prueba123"},
            },
        )
        assert estado == 404
        assert cuerpo["detail"]["code"] == "plan_not_found"

    def test_un_estado_inventado_no_pasa(self, soporte: Api, plan_id: int):
        estado, cuerpo = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "Estado raro",
                "plan_id": plan_id,
                "estado": "regalada",
                "admin": {"email": "raro@pruebas.ventasys.cr", "password": "prueba123"},
            },
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "invalid_company_state"

    def test_un_idioma_sin_catalogo_no_pasa(self, soporte: Api, plan_id: int):
        estado, cuerpo = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "En francés",
                "plan_id": plan_id,
                "locale": "fr",
                "admin": {"email": "fr@pruebas.ventasys.cr", "password": "prueba123"},
            },
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "unsupported_locale"

    def test_una_contrasena_corta_no_pasa(self, soporte: Api, plan_id: int):
        estado, _ = soporte.call(
            "POST",
            "/support/companies",
            {
                "nombre": "Clave corta",
                "plan_id": plan_id,
                "admin": {"email": "corta@pruebas.ventasys.cr", "password": "123"},
            },
        )
        assert estado == 422


# --------------------------------------------------------------------------
# T-305 · Cambiar el estado y la fecha (RF-7)
# --------------------------------------------------------------------------


class TestLaSuscripcion:
    def test_suspenderla_deja_al_cajero_afuera_y_al_administrador_adentro(
        self, soporte: Api, plan_id: int
    ):
        alta = nueva_compania(soporte, plan_id)

        # Un cajero de esa compañía, aceptando su invitación.
        marca = marca_unica()
        cajero = {
            "name": "Caja",
            "lastName": "Suspendida",
            "secondName": marca,
            "identification": f"8{marca}",
            "birth_date": "1995-05-05",
            "telephone": "80000000",
            "email": f"caja.{marca}@pruebas.ventasys.cr",
            "password": "prueba123",
        }
        dueno = Api(soporte.base)
        sesion = dueno.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        dueno.token = sesion["access_token"]
        dueno.registrar(cajero)
        dueno.ok("POST", "/users/membership", {"email": cajero["email"], "role": "cajero"})

        suyo = Api(soporte.base)
        pendiente = suyo.ok(
            "POST", "/auth/login", {"email": cajero["email"], "password": cajero["password"]}
        )
        suyo.token = pendiente["access_token"]
        suyo.ok(
            "POST",
            "/auth/invitation",
            {"company_id": alta["company_id"], "accion": "aceptar"},
        )

        soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "suspendida", "vence_el": str(HOY)},
        )

        # El cajero ya no puede entrar, y se le dice por qué.
        cuerpo = suyo.ok(
            "POST", "/auth/login", {"email": cajero["email"], "password": cajero["password"]}
        )
        assert cuerpo["tipo"] == "transito", "sin compañías disponibles no hay sesión"
        opcion = next(c for c in cuerpo["companies"] if c["id"] == alta["company_id"])
        assert opcion["puede_entrar"] is False
        assert opcion["motivo"] == "suspendida"

        # El administrador sí, y solo para ver el aviso de pago.
        adentro = Api(soporte.base)
        cuerpo = adentro.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        assert cuerpo["tipo"] == "sesion"
        adentro.token = cuerpo["access_token"]
        yo = adentro.ok("GET", "/users/me")
        assert yo["subscription"]["puede_vender"] is False
        assert yo["subscription"]["aviso"] == "suspendida"

    def test_cancelarla_deja_afuera_al_administrador(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "cancelada", "vence_el": str(HOY)},
        )
        cliente = Api(soporte.base)
        cuerpo = cliente.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        opcion = next(c for c in cuerpo["companies"] if c["id"] == alta["company_id"])
        assert opcion["puede_entrar"] is False
        assert opcion["motivo"] == "cancelada"

    def test_el_estado_efectivo_lo_pone_la_fecha(self, soporte: Api, plan_id: int):
        """T-308: `activa` con la fecha pasada sale como `vencida`.

        El estado guardado no se toca: el panel muestra lo que alguien puso y lo
        que el sistema deduce, que no son lo mismo.
        """
        alta = nueva_compania(soporte, plan_id)
        ficha = soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "activa", "vence_el": str(HOY - timedelta(days=2))},
        )
        assert ficha["suscripcion"]["guardado"] == "activa"
        assert ficha["suscripcion"]["estado"] == "vencida"
        assert ficha["suscripcion"]["puede_vender"] is True, "está en gracia"
        assert ficha["suscripcion"]["gracia"] == 6
        assert ficha["suscripcion"]["aviso"] == "en_gracia"

    def test_el_plan_se_puede_cambiar(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        ficha = soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "activa", "vence_el": str(HOY + timedelta(days=30)), "plan_id": plan_id},
        )
        assert ficha["plan"]["id"] == plan_id

    def test_un_estado_inventado_no_pasa(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        estado, cuerpo = soporte.call(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "gratis"},
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "invalid_company_state"

    def test_una_compania_que_no_existe_es_404(self, soporte: Api):
        estado, cuerpo = soporte.call(
            "PUT", "/support/companies/999999/subscription", {"estado": "activa"}
        )
        assert estado == 404
        assert cuerpo["detail"]["code"] == "company_not_found"


# --------------------------------------------------------------------------
# T-1003 · Los módulos de un plan (RF-39, RN-49)
# --------------------------------------------------------------------------


class TestLosModulosDelPlan:
    def test_un_plan_nace_sin_ningun_modulo(self, soporte: Api, plan_id: int):
        plan = next(p for p in soporte.ok("GET", "/support/plans") if p["id"] == plan_id)
        # Apagados por omisión: un plan que ya existe es uno que alguien compró
        # sin estos módulos.
        assert (plan["purchases"], plan["accounting"], plan["payroll"]) == (False, False, False)

    def test_se_encienden_y_se_apagan(self, soporte: Api, plan_id: int):
        encendido = soporte.ok(
            "PUT",
            f"/support/plans/{plan_id}/modules",
            {"purchases": True, "accounting": True, "payroll": False},
        )
        assert (encendido["purchases"], encendido["accounting"], encendido["payroll"]) == (
            True,
            True,
            False,
        )

        # Y se apagan: el plan es el catálogo, no un interruptor de una sola vía.
        apagado = soporte.ok(
            "PUT",
            f"/support/plans/{plan_id}/modules",
            {"purchases": False, "accounting": False, "payroll": False},
        )
        assert apagado["purchases"] is False
        assert apagado["accounting"] is False

    def test_el_cambio_queda_en_bitacora_con_cuantas_companias_alcanza(
        self, soporte: Api, plan_id: int
    ):
        soporte.ok(
            "PUT",
            f"/support/plans/{plan_id}/modules",
            {"purchases": True, "accounting": False, "payroll": False},
        )
        lineas = soporte.ok("GET", "/support/audit?accion=plan_modulos&limite=10")["lineas"]
        assert lineas, "el cambio de módulos tiene que quedar registrado"

        # El detalle trae el antes, el después y a cuántos alcanza: sin el
        # número, dentro de seis meses no hay forma de entender qué pasó ese día.
        detalle = lineas[0]["detalle"]
        assert "purchases no → sí" in detalle
        assert "compañías" in detalle

    def test_guardar_sin_cambiar_nada_se_registra_y_lo_dice(self, soporte: Api, plan_id: int):
        apagar = {"purchases": False, "accounting": False, "payroll": False}
        soporte.ok("PUT", f"/support/plans/{plan_id}/modules", apagar)
        soporte.ok("PUT", f"/support/plans/{plan_id}/modules", apagar)

        # Se registra igual que `cambiar_suscripcion`: haber abierto el panel y
        # pulsado guardar es un hecho, y saber quién anduvo tocando los planes es
        # para lo que sirve la bitácora. Lo que no hace es fingir un cambio.
        detalle = soporte.ok("GET", "/support/audit?accion=plan_modulos&limite=1")["lineas"][0]
        assert detalle["detalle"].endswith("sin cambios")

    def test_un_plan_que_no_existe_es_404(self, soporte: Api):
        estado, cuerpo = soporte.call(
            "PUT",
            "/support/plans/999999/modules",
            {"purchases": True, "accounting": False, "payroll": False},
        )
        assert estado == 404
        assert cuerpo["detail"]["code"] == "plan_not_found"

    def test_el_administrador_de_una_compania_no_los_toca(self, api: Api, plan_id: int):
        # Es la puerta de RN-4 en su segundo sentido: el token vale, y no vale
        # para esto. 403 y no un redirect.
        estado, cuerpo = api.call(
            "PUT",
            f"/support/plans/{plan_id}/modules",
            {"purchases": True, "accounting": True, "payroll": True},
        )
        assert estado == 403
        assert cuerpo["detail"]["code"] == "support_only"


# --------------------------------------------------------------------------
# T-306 · Entrar como (RF-8, RN-4)
# --------------------------------------------------------------------------


class TestEntrarComo:
    def test_sin_motivo_no_se_entra(self, soporte: Api, api: Api):
        for motivo in ("", "x"):
            estado, _ = soporte.call(
                "POST", f"/support/companies/{api.company_id}/enter", {"motivo": motivo}
            )
            assert estado == 422, "el motivo es obligatorio y no puede ser un garabato"

    def test_con_motivo_se_ve_lo_de_esa_compania(self, soporte: Api, api: Api):
        respuesta = soporte.ok(
            "POST",
            f"/support/companies/{api.company_id}/enter",
            {"motivo": "el cliente reporta que no puede cerrar caja"},
        )
        assert respuesta["company_id"] == api.company_id
        assert respuesta["minutos"] == 30

        payload = cuerpo_del_token(respuesta["access_token"])
        assert payload["tipo"] == "suplantacion"
        assert payload["cid"] == api.company_id
        assert payload["mot"].startswith("el cliente reporta")
        # Media hora, no ocho: es una visita. Se comprueba en el token porque
        # esperar media hora no es una prueba.
        assert 0 < payload["exp"] - int(time.time()) <= 31 * 60

        visita = Api(soporte.base)
        visita.token = respuesta["access_token"]

        yo = visita.ok("GET", "/users/me")
        assert yo["company_id"] == api.company_id
        assert yo["impersonated_by"] == SOPORTE["email"]
        assert yo["impersonation_reason"].startswith("el cliente reporta")
        # Sin compañías que ofrecer: el menú no puede ofrecerle «cambiar de
        # compañía» a quien no tiene ninguna.
        assert yo["companies_available"] == 0

        # Y ve los datos del cliente, que es para lo que existe.
        productos = visita.ok("GET", "/products/products_list")
        assert productos == api.ok("GET", "/products/products_list")

    def test_la_visita_no_escribe_nada(self, soporte: Api, api: Api, categoria: int):
        """RF-8 leído literal: soporte entra a **diagnosticar**.

        Es la decisión más discutible de F3 y la más fácil de aflojar después: si
        un día hay que dejar que soporte arregle algo, se abre a propósito y con
        su bitácora, no por descuido.
        """
        respuesta = soporte.ok(
            "POST",
            f"/support/companies/{api.company_id}/enter",
            {"motivo": "revisar por qué no entra el inventario"},
        )
        visita = Api(soporte.base)
        visita.token = respuesta["access_token"]

        for metodo, ruta, cuerpo_pedido in (
            ("POST", "/categories/register_category", {"name": "Metida"}),
            (
                "POST",
                "/products/add_product",
                {
                    "name": "Producto de soporte",
                    "description": "no debería entrar",
                    "price": 1,
                    "stock": 1,
                    "barcode": f"SOP{marca_unica()}",
                    "created_at": "2026-01-01T00:00:00",
                    "category_id": categoria,
                },
            ),
            ("PUT", "/settings/", {"data": {}}),
        ):
            estado, cuerpo = visita.call(metodo, ruta, cuerpo_pedido)
            assert estado == 403, f"{ruta} respondió {estado}"
            assert cuerpo["detail"]["code"] == "impersonation_read_only"

    def test_la_visita_no_abre_el_panel(self, soporte: Api, api: Api):
        """Un token de suplantación es para mirar una compañía, no para
        administrar la plataforma: son dos permisos y se comprueban aparte."""
        respuesta = soporte.ok(
            "POST",
            f"/support/companies/{api.company_id}/enter",
            {"motivo": "comprobar que la visita no abre el panel"},
        )
        visita = Api(soporte.base)
        visita.token = respuesta["access_token"]
        estado, cuerpo = visita.call("GET", "/support/companies")
        assert estado == 403
        assert cuerpo["detail"]["code"] == "support_only"

    def test_una_compania_que_no_existe_es_404(self, soporte: Api):
        estado, cuerpo = soporte.call(
            "POST", "/support/companies/999999/enter", {"motivo": "no existe, a ver qué pasa"}
        )
        assert estado == 404
        assert cuerpo["detail"]["code"] == "company_not_found"


# --------------------------------------------------------------------------
# T-307 · La bitácora (RF-9)
# --------------------------------------------------------------------------


class TestLaBitacora:
    def test_cada_accion_de_soporte_deja_su_linea(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "activa", "vence_el": str(HOY + timedelta(days=15))},
        )
        soporte.ok(
            "POST",
            f"/support/companies/{alta['company_id']}/enter",
            {"motivo": "comprobar la bitácora de punta a punta"},
        )

        pagina = soporte.ok("GET", f"/support/audit?company_id={alta['company_id']}")
        acciones = [linea["accion"] for linea in pagina["lineas"]]
        assert "alta_compania" in acciones
        assert "suscripcion" in acciones
        assert "entrar_como" in acciones

        # Y con el detalle que hace útil una bitácora: el motivo completo, y el
        # antes y el después del cambio.
        entrada = next(x for x in pagina["lineas"] if x["accion"] == "entrar_como")
        assert entrada["detalle"] == "comprobar la bitácora de punta a punta"
        assert entrada["email"] == SOPORTE["email"]
        assert entrada["company_nombre"] == alta["nombre"]

        cambio = next(x for x in pagina["lineas"] if x["accion"] == "suscripcion")
        assert "vence" in cambio["detalle"]

    def test_esta_ordenada_de_lo_ultimo_a_lo_primero(self, soporte: Api):
        pagina = soporte.ok("GET", "/support/audit?limite=20")
        fechas = [linea["creado_el"] for linea in pagina["lineas"]]
        assert fechas == sorted(fechas, reverse=True)

    def test_se_puede_filtrar_por_accion(self, soporte: Api):
        pagina = soporte.ok("GET", "/support/audit?accion=entrar_como&limite=10")
        assert pagina["lineas"], "tendría que haber al menos una visita"
        assert {linea["accion"] for linea in pagina["lineas"]} == {"entrar_como"}
        assert "entrar_como" in pagina["acciones"]

    def test_el_login_de_los_clientes_tambien_queda(self, soporte: Api):
        """La bitácora no es solo de soporte, y es a propósito: la pregunta que
        se hace de verdad es «por qué este cajero no puede entrar»."""
        pagina = soporte.ok("GET", "/support/audit?accion=login&limite=5")
        assert pagina["lineas"]

    def test_un_cliente_no_la_puede_leer(self, api: Api):
        estado, cuerpo = api.call("GET", "/support/audit")
        assert estado == 403
        assert cuerpo["detail"]["code"] == "support_only"


# --------------------------------------------------------------------------
# T-309 · Los límites del plan (RF-12)
# --------------------------------------------------------------------------


class TestElLimiteDelPlan:
    @pytest.fixture(scope="class")
    def plan_chico(self, soporte: Api) -> dict:
        """Un plan de dos usuarios.

        Con el plan normal habría que crear cinco personas para llegar al techo,
        y lo que se está probando no es el número: es que exista el techo. Dos
        alcanzan y la prueba tarda un cuarto.
        """
        return _plan(
            soporte,
            "Plan de dos",
            plan_max_sucursales=1,
            plan_max_terminales=1,
            plan_max_usuarios=2,
        )

    def test_no_se_pueden_crear_mas_usuarios_de_los_que_permite_el_plan(
        self, soporte: Api, plan_chico: dict
    ):
        """Se llena el plan y se comprueba que el siguiente no entra."""
        maximo = plan_chico["max_usuarios"]
        alta = nueva_compania(soporte, plan_chico["id"])

        dueno = Api(soporte.base)
        sesion = dueno.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        dueno.token = sesion["access_token"]

        # La compañía nace con un usuario: su administrador.
        rechazos = 0
        for i in range(maximo):
            marca = marca_unica()
            persona = {
                "name": "Relleno",
                "lastName": f"Numero{i}",
                "secondName": marca,
                "identification": f"6{marca}",
                "birth_date": "1995-05-05",
                "telephone": "80000000",
                "email": f"relleno.{marca}@pruebas.ventasys.cr",
                "password": "prueba123",
            }
            dueno.registrar(persona)
            estado, cuerpo = dueno.call(
                "POST", "/users/membership", {"email": persona["email"], "role": "cajero"}
            )
            if estado == 400 and cuerpo["detail"]["code"] == "plan_limit_reached":
                rechazos += 1
                assert cuerpo["detail"]["max"] == maximo
                assert cuerpo["detail"]["current"] == maximo
                assert cuerpo["detail"]["resource"] == "users"
                break
            assert estado == 200, f"la persona {i} no entró: {cuerpo}"

        assert rechazos == 1, (
            f"con el plan en {maximo} usuarios, el {maximo + 1} tenía que ser rechazado"
        )

    def test_el_cupo_se_ve_en_el_panel(self, soporte: Api, plan_id: int):
        alta = nueva_compania(soporte, plan_id)
        ficha = soporte.ok("GET", f"/support/companies/{alta['company_id']}")
        assert ficha["uso"]["usuarios"] == 1
        assert ficha["uso"]["cupo_usuarios"] == ficha["plan"]["max_usuarios"] - 1


# --------------------------------------------------------------------------
# El guardián: toda acción de soporte se registra (T-307)
# --------------------------------------------------------------------------


def test_toda_accion_de_soporte_queda_en_bitacora():
    """Lee el árbol de sintaxis del router y exige la línea de bitácora.

    Las tres acciones de hoy están probadas arriba una por una. Esto es para la
    cuarta: un endpoint nuevo que cambie algo y no registre nada tumba `pytest`
    el día que se escribe, no el día que alguien pregunta qué pasó.

    No necesita backend, así que no se omite nunca.
    """
    fuente = (APP / "router" / "support_routes.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    metodos_que_escriben = {"post", "put", "patch", "delete"}
    sin_registrar = []

    for nodo in arbol.body:
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        escribe = any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr in metodos_que_escriben
            for d in nodo.decorator_list
        )
        if not escribe:
            continue

        cuerpo = ast.dump(nodo)
        if "registrar" not in cuerpo:
            sin_registrar.append(nodo.name)

    assert not sin_registrar, (
        "Estos endpoints del panel cambian algo y no dejan línea en la "
        f"bitácora: {sin_registrar}\n"
        "Toda acción de soporte se registra (RF-9). Se hace con "
        "`crud_membership.registrar(...)` antes del commit, para que la "
        "anotación entre en la misma transacción que el hecho que narra."
    )
