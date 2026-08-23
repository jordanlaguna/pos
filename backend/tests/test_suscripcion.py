"""El bloqueo por vencimiento, aplicado (T-308, RF-10, RF-11, RN-1, RN-2).

`tests/domain/test_subscription.py` prueba la aritmética: qué estado manda, cuántos
días de gracia quedan, quién puede vender. Esto prueba la **puerta**: que una
compañía a la que se le pasó la gracia pueda consultar y no pueda escribir, que
la caja abierta se pueda cerrar igual, y que ninguna ruta nueva se salte el
control por descuido.

El último es un guardián y no necesita backend: lee el árbol de sintaxis de los
routers. Es el que importa a largo plazo —las dos primeras prueban lo que hay,
él prueba lo que venga—.
"""

from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from .conftest import Api, marca_unica
from .test_soporte import nueva_compania  # noqa: F401  (fixture-helper compartido)

APP = Path(__file__).resolve().parent.parent / "app"
HOY = date.today()


# --------------------------------------------------------------------------
# Con la suscripción vencida: se lee, no se escribe
# --------------------------------------------------------------------------


@pytest.mark.characterization
class TestSoloLectura:
    @pytest.fixture(scope="class")
    def vencida(self, soporte: Api) -> Api:
        """Una compañía con la gracia agotada, y la sesión de su administrador."""
        planes = soporte.ok("GET", "/support/plans")
        alta = nueva_compania(soporte, planes[0]["id"])
        soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            # Treinta días atrás: vencida y con la gracia de siete días agotada.
            {"estado": "activa", "vence_el": str(HOY - timedelta(days=30))},
        )

        cliente = Api(soporte.base)
        sesion = cliente.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        cliente.token = sesion["access_token"]
        cliente.company_id = alta["company_id"]  # type: ignore[attr-defined]
        cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
        return cliente

    def test_se_entra_y_el_estado_lo_dice(self, vencida: Api):
        """Dejar de pagar es dejar de vender, no dejar de entrar: los datos
        siguen siendo del cliente y tiene que poder consultarlos."""
        yo = vencida.ok("GET", "/users/me")
        assert yo["subscription"]["estado"] == "vencida"
        assert yo["subscription"]["guardado"] == "activa"
        assert yo["subscription"]["puede_vender"] is False
        assert yo["subscription"]["gracia"] == 0
        assert yo["subscription"]["aviso"] == "solo_lectura"

    def test_se_puede_consultar_todo(self, vencida: Api):
        for ruta in (
            "/products/products_list",
            "/sales/sales_list",
            "/clients/clients_list",
            "/reports/summary",
            "/settings/",
        ):
            estado, _ = vencida.call("GET", ruta)
            assert estado == 200, f"{ruta} respondió {estado} en solo lectura"

    def test_no_se_puede_vender_ni_cambiar_nada(self, vencida: Api):
        intentos = (
            ("POST", "/categories/register_category", {"name": "No entra"}),
            (
                "POST",
                "/products/add_product",
                {
                    "name": "No entra",
                    "description": "",
                    "price": 1,
                    "stock": 1,
                    "barcode": f"VEN{marca_unica()}",
                    "created_at": "2026-01-01T00:00:00",
                    "category_id": 1,
                },
            ),
            ("POST", "/cash/open", {"user_id": vencida.user_id, "opening_amount": 1000}),
            ("PUT", "/settings/", {"data": {}}),
        )
        for metodo, ruta, cuerpo_pedido in intentos:
            estado, cuerpo = vencida.call(metodo, ruta, cuerpo_pedido)
            assert estado == 403, f"{metodo} {ruta} respondió {estado}"
            assert cuerpo["detail"]["code"] == "subscription_read_only"
            assert cuerpo["detail"]["state"] == "vencida"

    def test_la_caja_abierta_siempre_se_puede_cerrar(self, vencida: Api):
        """RN-1, y es la excepción que justifica el mecanismo entero.

        No se puede abrir caja en solo lectura, así que acá no hay turno que
        cerrar; lo que se comprueba es que el «no» venga de la caja y no del
        cobrador: `cash_no_open_session` significa que la petición **pasó** el
        control de suscripción. Si algún día alguien saca `/cash/close` de la
        lista de excepciones, esta prueba se cae con un `subscription_read_only`
        en la mano.
        """
        estado, cuerpo = vencida.call(
            "POST",
            "/cash/close",
            {"user_id": vencida.user_id, "closing_amount": 0, "notes": "cierre"},
        )
        assert estado != 403 or cuerpo["detail"]["code"] != "subscription_read_only"
        assert cuerpo["detail"]["code"] == "cash_no_open_session"

    def test_el_idioma_se_puede_cambiar(self, vencida: Api):
        """La otra excepción: quien queda en solo lectura necesita leer el aviso
        de pago en su idioma."""
        assert vencida.ok("POST", "/auth/locale", {"locale": "en"})["locale"] == "en"
        vencida.token = vencida.ok("POST", "/auth/locale", {"locale": None})["access_token"]

    def test_al_pagar_vuelve_a_vender_en_el_siguiente_clic(self, soporte: Api, vencida: Api):
        """RF-10: el estado se evalúa en cada petición.

        Es lo que se compra al no meter la suscripción en el token: un pago que
        entra hoy le devuelve el POS al cliente ahora, no en su próximo login.
        """
        soporte.ok(
            "PUT",
            f"/support/companies/{vencida.company_id}/subscription",
            {"estado": "activa", "vence_el": str(HOY + timedelta(days=30))},
        )
        estado, _ = vencida.call(
            "POST", "/categories/register_category", {"name": f"Ya paga {marca_unica()}"}
        )
        assert estado == 200

        # Y el aviso desaparece, porque falta más de una semana.
        assert vencida.ok("GET", "/users/me")["subscription"]["aviso"] is None


@pytest.mark.characterization
class TestElAvisoPrevio:
    def test_avisa_una_semana_antes(self, soporte: Api):
        """RF-11: aviso visible desde 7 días antes del vencimiento."""
        planes = soporte.ok("GET", "/support/plans")
        alta = nueva_compania(soporte, planes[0]["id"])
        soporte.ok(
            "PUT",
            f"/support/companies/{alta['company_id']}/subscription",
            {"estado": "activa", "vence_el": str(HOY + timedelta(days=3))},
        )
        cliente = Api(soporte.base)
        sesion = cliente.ok(
            "POST", "/auth/login", {"email": alta["email"], "password": "prueba123"}
        )
        cliente.token = sesion["access_token"]

        suscripcion = cliente.ok("GET", "/users/me")["subscription"]
        assert suscripcion["aviso"] == "vence_pronto"
        assert suscripcion["dias"] == 3
        assert suscripcion["puede_vender"] is True


# --------------------------------------------------------------------------
# El guardián: ninguna ruta que escriba se salta la sesión
# --------------------------------------------------------------------------

#: Rutas que escriben **sin** pasar por `get_current_user`, con su motivo. Cada
#: una es una puerta que el bloqueo por vencimiento no cubre, así que la lista
#: tiene que ser corta y estar justificada.
#:
#: Las claves son `archivo:función`, que es lo que el guardián puede leer sin
#: importar el módulo —importar `app.main` abriría la base—.
SIN_SESION: dict[str, str] = {
    "auth_routes.py:login": "es el que entrega el token; todavía no hay sesión",
    "auth_routes.py:responder_invitacion": (
        "acepta o rechaza una invitación con el token de tránsito, que por "
        "definición no tiene compañía (RN-26)"
    ),
    "auth_routes.py:elegir_compania": "es el paso que crea la sesión",
    "person_routes.py:register_person": (
        "público a propósito: crea una identidad, que todavía no pertenece a "
        "ninguna compañía"
    ),
    "support_routes.py:alta_de_compania": "panel de soporte: `require_soporte`",
    "support_routes.py:cambiar_suscripcion": "panel de soporte: `require_soporte`",
    "support_routes.py:entrar_como": "panel de soporte: `require_soporte`",
}

#: Las dependencias que sí aplican el control de suscripción, porque las tres
#: pasan por `get_current_user`.
CON_SESION = {"get_current_user", "require_admin", "require_write"}

METODOS_QUE_ESCRIBEN = {"post", "put", "patch", "delete"}


def _rutas_que_escriben() -> list[tuple[str, str, set[str]]]:
    """(archivo, función, dependencias) de cada endpoint que cambia algo."""
    encontradas = []
    for archivo in sorted((APP / "router").glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            escribe = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr in METODOS_QUE_ESCRIBEN
                for d in nodo.decorator_list
            )
            if not escribe:
                continue

            # `x: T = Depends(f)` → se anota `f`.
            dependencias = {
                d.args[0].id
                for d in nodo.args.defaults
                if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Name)
                and d.func.id == "Depends"
                and d.args
                and isinstance(d.args[0], ast.Name)
            }
            encontradas.append((archivo.name, nodo.name, dependencias))
    return encontradas


def test_ninguna_ruta_que_escribe_se_salta_el_control_de_suscripcion():
    """El bloqueo por vencimiento vive en `get_current_user`, y esto vigila que
    toda ruta que escriba pase por ahí.

    Es la otra mitad del diseño. Centralizar el control fue lo que evitó tocar
    cuarenta endpoints; el precio es que una ruta nueva puede esquivarlo sin
    querer —usando `get_identidad`, o ninguna dependencia— y nadie lo notaría
    hasta que un cliente vencido siga vendiendo. Esta prueba lo nota el día que
    se escribe.
    """
    huerfanas = []
    for archivo, funcion, dependencias in _rutas_que_escriben():
        clave = f"{archivo}:{funcion}"
        if clave in SIN_SESION:
            continue
        if dependencias & CON_SESION:
            continue
        huerfanas.append(clave)

    assert not huerfanas, (
        "Estas rutas cambian algo y no pasan por `get_current_user`, así que el "
        f"bloqueo por vencimiento no las cubre: {huerfanas}\n"
        "Agregales `Depends(get_current_user)` o `Depends(require_admin)`, o "
        "declaralas en SIN_SESION con su motivo."
    )


def test_las_excepciones_al_bloqueo_siguen_existiendo():
    """Que las dos rutas exentas sigan siendo rutas.

    Se comparan cadenas literales: si mañana `/cash/close` pasa a ser
    `/cash/session/close`, la excepción dejaría de aplicar en silencio y RN-1 se
    rompería sin que nada fallara. Ahora falla acá.
    """
    from app.utils.auth_dependency import ESCRITURA_EN_SOLO_LECTURA

    declaradas = set()
    for archivo in sorted((APP / "router").glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        prefijo = {
            "auth_routes.py": "/auth",
            "cash_routes.py": "/cash",
            "categories_routes.py": "/categories",
            "client_routes.py": "/clients",
            "person_routes.py": "/persons",
            "product_routes.py": "/products",
            "report_routes.py": "/reports",
            "return_routes.py": "/returns",
            "sale_routes.py": "/sales",
            "settings_routes.py": "/settings",
            "stock_entry_routes.py": "/inventory",
            "support_routes.py": "/support",
            "user_routes.py": "/users",
        }.get(archivo.name, "")
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in METODOS_QUE_ESCRIBEN
                and nodo.args
                and isinstance(nodo.args[0], ast.Constant)
            ):
                declaradas.add(prefijo + nodo.args[0].value)

    faltan = sorted(set(ESCRITURA_EN_SOLO_LECTURA) - declaradas)
    assert not faltan, (
        f"Estas rutas están exentas del bloqueo por vencimiento y ya no existen "
        f"con ese nombre: {faltan}\n"
        "Una excepción a una ruta que no existe no protege nada: RN-1 se "
        "rompería sin que nada falle. Actualizá ESCRITURA_EN_SOLO_LECTURA."
    )


def test_ninguna_excepcion_sobra():
    """Una excepción que ya no hace falta es peor que ninguna.

    Mientras esté escrita, esa ruta queda fuera del guardián: el día que alguien
    le agregue una sesión —o le quite la que tenía— nadie se enteraría. Y de
    hecho pasó al escribir esta prueba: `update_person` estaba en la lista y sí
    pasa por `get_current_user`, así que llevaba un permiso que no usaba.
    """
    escriben = {f"{a}:{f}": d for a, f, d in _rutas_que_escriben()}

    sobran = []
    for clave in SIN_SESION:
        if clave not in escriben:
            sobran.append(f"{clave} (ya no es una ruta que escriba)")
        elif escriben[clave] & CON_SESION:
            sobran.append(f"{clave} (ya pasa por {sorted(escriben[clave] & CON_SESION)})")

    assert not sobran, (
        f"Estas excepciones ya no hacen falta y hay que borrarlas: {sobran}"
    )


def test_cada_excepcion_dice_por_que():
    """Una lista de excepciones sin motivos se vuelve una lista de costumbres."""
    from app.utils.auth_dependency import ESCRITURA_EN_SOLO_LECTURA

    flojas = [
        ruta for ruta, motivo in ESCRITURA_EN_SOLO_LECTURA.items() if len(motivo) < 30
    ]
    assert not flojas, f"Estas excepciones no explican nada: {flojas}"
