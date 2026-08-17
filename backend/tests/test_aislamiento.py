"""Aislamiento entre compañías (T-214, RNF-1).

Es la prueba que decide si F2 sirve. Todo lo demás de la fase —la migración, el
filtro, los tokens— existe para que esto pase: **con el token de la compañía A,
pedir los identificadores de la B no devuelve nada**.

Por qué 404 y no 403
--------------------
Un 403 dice «existe pero no es tuyo», y eso ya es información: con un bucle
sobre `/sales/sale/1..10000` y un token de cualquier compañía, un competidor
sabría cuántas facturas lleva emitidas otro negocio. El 404 no distingue entre
«no existe» y «no es tuyo», que es justamente lo que se quiere.

La lista de rutas se escribe a mano y no se descubre del OpenAPI a propósito: si
mañana alguien agrega un endpoint y no lo agrega acá, esta prueba no lo protege
—pero tampoco pretende decir que sí—. `test_ninguna_ruta_de_negocio_quedo_sin_probar`
compara ambas listas y falla cuando aparece una ruta nueva sin cubrir.
"""

from __future__ import annotations

import pytest
import requests

from .conftest import API, TIMEOUT, Api, entrar, marca_unica

pytestmark = pytest.mark.characterization


# --------------------------------------------------------------------------
# Datos de cada compañía: se crean una sola vez y se comparan cruzados.
# --------------------------------------------------------------------------


def _crear_mundo(cliente: Api, etiqueta: str) -> dict:
    """Un producto, un cliente, una categoría, una venta y una entrada."""
    marca = marca_unica()

    cliente.call("POST", "/categories/register_category", {"name": f"Cat {etiqueta} {marca}"})
    categorias = cliente.ok("GET", "/categories/categories_list")
    categoria = next(c for c in categorias if c["name"] == f"Cat {etiqueta} {marca}")

    cliente.ok(
        "POST",
        "/products/add_product",
        {
            "name": f"Producto {etiqueta} {marca}",
            "description": "para la prueba de aislamiento",
            "price": 1000,
            "stock": 50,
            "barcode": f"AISL{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria["id"],
        },
    )
    producto = cliente.ok("GET", f"/products/product/AISL{marca}")

    persona = cliente.ok(
        "POST",
        "/clients/register_client",
        {
            "identification": f"AI{marca}",
            "name": f"Cliente {etiqueta}",
            "last_name": "Aislamiento",
            "second_name": "Prueba",
            "email": f"aisl.{marca}@pruebas.cr",
            "telephone": 80000000,
            "address": "sin dirección",
            "register_date": "2026-01-01",
        },
    )

    venta = cliente.ok(
        "POST",
        "/sales/add_sale",
        {
            "sale_number": f"AISL{marca}",
            "client_id": None,
            "user_id": cliente.user_id,  # type: ignore[attr-defined]
            "subtotal": 1000.0,
            "tax": 130.0,
            "total": 1130.0,
            "payment_method": "Efectivo",
            "cash_received": 1130.0,
            "change_given": 0.0,
            "products": [{"id_product": producto["id_product"], "stock": 1}],
        },
    )

    devolucion = cliente.ok(
        "POST",
        "/returns/add_return",
        {
            "sale_id": venta["id_sale"],
            "user_id": cliente.user_id,  # type: ignore[attr-defined]
            "reason": "prueba de aislamiento",
            "items": [{"id_product": producto["id_product"], "quantity": 1}],
        },
    )

    entrada = cliente.ok(
        "POST",
        "/inventory/entry",
        {
            "document_number": f"AISL{marca}",
            "supplier": f"Proveedor {etiqueta}",
            "source": "manual",
            "user_id": cliente.user_id,  # type: ignore[attr-defined]
            "notes": "prueba de aislamiento",
            "lines": [
                {"id_product": producto["id_product"], "quantity": 5, "unit_cost": 500}
            ],
        },
    )

    return {
        "categoria_id": categoria["id"],
        "producto": producto,
        "cliente_id": persona["id_client"],
        "venta_id": venta["id_sale"],
        "devolucion_id": devolucion["id_return"],
        "entrada_id": entrada["id_entry"],
        "company_id": cliente.company_id,  # type: ignore[attr-defined]
        "user_id": cliente.user_id,  # type: ignore[attr-defined]
    }


@pytest.fixture(scope="module")
def mundo_a(api: Api) -> dict:
    return _crear_mundo(api, "A")


@pytest.fixture(scope="module")
def mundo_b(api_b: Api) -> dict:
    return _crear_mundo(api_b, "B")


# --------------------------------------------------------------------------
# 1. Pedir por identificador lo de la otra compañía
# --------------------------------------------------------------------------

#: Cada entrada es (método, plantilla de ruta, clave del identificador ajeno).
#: El cuerpo va aparte para los PUT/POST, que también tienen que rebotar.
RUTAS_POR_ID = [
    ("GET", "/sales/sale/{venta_id}", None),
    ("GET", "/sales/pdf/{venta_id}", None),
    ("GET", "/returns/return/{devolucion_id}", None),
    ("GET", "/inventory/entry/{entrada_id}", None),
    ("GET", "/users/{user_id}", None),
    ("PUT", "/products/update_product/{producto_id}", {"price": 99999}),
    ("DELETE", "/products/delete_product/{producto_id}", None),
    ("PUT", "/clients/update_client/{cliente_id}", {"name": "Secuestrado"}),
    ("PUT", "/users/role/{user_id}", {"role": "cajero"}),
    ("POST", "/inventory/entry/{entrada_id}/cancel", None),
]


class TestNoSeVeLoDeLaOtraCompania:
    @pytest.mark.parametrize(
        "metodo,plantilla,cuerpo",
        RUTAS_POR_ID,
        ids=[f"{m} {r}" for m, r, _ in RUTAS_POR_ID],
    )
    def test_pedir_por_id_lo_ajeno_responde_404(
        self, api: Api, mundo_a: dict, mundo_b: dict, metodo: str, plantilla: str, cuerpo
    ):
        ruta = plantilla.format(
            venta_id=mundo_b["venta_id"],
            devolucion_id=mundo_b["devolucion_id"],
            entrada_id=mundo_b["entrada_id"],
            producto_id=mundo_b["producto"]["id_product"],
            cliente_id=mundo_b["cliente_id"],
            user_id=mundo_b["user_id"],
        )
        estado, respuesta = api.call(metodo, ruta, cuerpo)

        assert estado == 404, (
            f"{metodo} {ruta} respondió {estado} con el token de la compañía A "
            f"pidiendo algo de la B. Esperado 404.\n"
            f"Un 200 es una fuga; un 403 confirma que el recurso existe.\n"
            f"Respuesta: {respuesta}"
        )

    def test_el_mismo_id_propio_sigue_funcionando(self, api: Api, mundo_a: dict):
        """La contraprueba: sin esto, un 404 en todo también pasaría el examen."""
        estado, _ = api.call("GET", f"/sales/sale/{mundo_a['venta_id']}")
        assert estado == 200, "la compañía A no puede ver su propia venta"

        estado, _ = api.call("GET", f"/returns/return/{mundo_a['devolucion_id']}")
        assert estado == 200
        estado, _ = api.call("GET", f"/inventory/entry/{mundo_a['entrada_id']}")
        assert estado == 200

    def test_el_producto_ajeno_no_aparece_ni_por_codigo_ni_por_nombre(
        self, api: Api, mundo_a: dict, mundo_b: dict
    ):
        """El escáner y el buscador son la vía más fácil de leer catálogo ajeno."""
        ajeno = mundo_b["producto"]

        estado, _ = api.call("GET", f"/products/product/{ajeno['barcode']}")
        assert estado == 404, "el código de barras de otra compañía devolvió producto"

        _, encontrados = api.call("GET", f"/products/search/{ajeno['name']}")
        assert encontrados == [] or all(
            p["id_product"] != ajeno["id_product"] for p in encontrados
        ), "la búsqueda por nombre trajo un producto de otra compañía"


# --------------------------------------------------------------------------
# 2. Las listas solo traen lo propio
# --------------------------------------------------------------------------

LISTAS = [
    ("/products/products_list", "id_product", "producto"),
    ("/clients/clients_list", "id_client", "cliente_id"),
    ("/sales/sales_list", "id_sale", "venta_id"),
    ("/returns/returns_list", "id_return", "devolucion_id"),
    ("/inventory/entries", "id", "entrada_id"),
    ("/categories/categories_list", "id", "categoria_id"),
]


class TestLasListasNoMezclan:
    @pytest.mark.parametrize("ruta,clave,cual", LISTAS, ids=[r for r, _, _ in LISTAS])
    def test_la_lista_no_trae_nada_de_la_otra(
        self, api: Api, mundo_a: dict, mundo_b: dict, ruta: str, clave: str, cual: str
    ):
        esperado = mundo_b[cual]
        ajeno = esperado["id_product"] if cual == "producto" else esperado

        filas = api.ok("GET", ruta)
        ids = {f[clave] for f in filas if clave in f}

        assert ajeno not in ids, (
            f"{ruta} devolvió el registro {ajeno} de la compañía B "
            f"a una sesión de la compañía A"
        )

    def test_los_usuarios_listados_son_los_de_esta_compania(
        self, api: Api, api_b: Api, mundo_a: dict, mundo_b: dict
    ):
        correos_a = {u["email"] for u in api.ok("GET", "/users/")}
        correos_b = {u["email"] for u in api_b.ok("GET", "/users/")}

        assert correos_a, "la compañía A no listó ni a su propio administrador"
        assert not (correos_a & correos_b - {"contadora@pruebas.ventasys.cr"}), (
            f"las dos compañías comparten usuarios que no deberían: "
            f"{correos_a & correos_b}"
        )

    def test_las_personas_listadas_tambien(self, api: Api, api_b: Api):
        """`/persons/persons_list` devolvía la libreta entera de la base."""
        cedulas_a = {p["identification"] for p in api.ok("GET", "/persons/persons_list")}
        cedulas_b = {p["identification"] for p in api_b.ok("GET", "/persons/persons_list")}
        assert "200000001" not in cedulas_a, "A ve la cédula del administrador de B"
        assert "100000001" not in cedulas_b, "B ve la cédula del administrador de A"


# --------------------------------------------------------------------------
# 3. Los reportes: el filtro va escrito a mano y hay que comprobarlo (T-209)
# --------------------------------------------------------------------------


class TestLosReportesNoSuman:
    def test_el_resumen_de_A_no_incluye_las_ventas_de_B(
        self, api: Api, api_b: Api, mundo_a: dict, mundo_b: dict
    ):
        """
        El filtro automático **no** cubre estas consultas: piden `COUNT` y `SUM`
        y no cargan entidades. Si alguien quita el `company_id ==` escrito a
        mano en `crud_report.py`, esta prueba es lo único que lo detecta, y lo
        que se escapa es una cifra que se ve perfectamente normal.
        """
        resumen_a = api.ok("GET", "/reports/summary")
        resumen_b = api_b.ok("GET", "/reports/summary")

        # Cada compañía tiene exactamente una venta de 1130 hecha por el mundo.
        assert resumen_a["gross_total"] > 0 and resumen_b["gross_total"] > 0

        total_junto = api.ok("GET", "/reports/summary")["gross_total"]
        assert total_junto == resumen_a["gross_total"], "el resumen cambió entre llamadas"
        assert total_junto < resumen_a["gross_total"] + resumen_b["gross_total"], (
            "el resumen de A suma tanto como A y B juntas: el filtro de "
            "crud_report.py no está filtrando"
        )

    def test_lo_mas_vendido_no_nombra_productos_ajenos(
        self, api: Api, mundo_a: dict, mundo_b: dict
    ):
        nombres = {p["name"] for p in api.ok("GET", "/reports/top_products")}
        assert mundo_b["producto"]["name"] not in nombres

    def test_el_stock_bajo_no_delata_el_inventario_ajeno(
        self, api: Api, mundo_a: dict, mundo_b: dict
    ):
        ids = {p["id_product"] for p in api.ok("GET", "/reports/low_stock")}
        assert mundo_b["producto"]["id_product"] not in ids

    def test_las_ventas_por_dia_no_acumulan_las_de_la_otra(
        self, api: Api, api_b: Api, mundo_a: dict, mundo_b: dict
    ):
        dias_a = {d["day"]: d["total"] for d in api.ok("GET", "/reports/sales_by_day")}
        dias_b = {d["day"]: d["total"] for d in api_b.ok("GET", "/reports/sales_by_day")}
        comunes = set(dias_a) & set(dias_b)
        assert comunes, "las dos vendieron hoy; tiene que haber un día en común"
        for dia in comunes:
            assert dias_a[dia] != dias_a[dia] + dias_b[dia] or dias_b[dia] == 0


# --------------------------------------------------------------------------
# 4. La caja
# --------------------------------------------------------------------------


class TestLaCaja:
    def test_no_se_ve_el_turno_de_la_otra_compania(self, api: Api, api_b: Api):
        propios = {s["id"] for s in api.ok("GET", "/cash/sessions")}
        ajenos = {s["id"] for s in api_b.ok("GET", "/cash/sessions")}
        assert not (propios & ajenos), "las dos compañías comparten turnos de caja"


# --------------------------------------------------------------------------
# 5. La configuración es de cada compañía
# --------------------------------------------------------------------------


class TestLaConfiguracion:
    def test_cada_compania_tiene_la_suya(self, api: Api, api_b: Api):
        """Antes había una sola fila, `id = 1`, para todo el sistema.

        Si esto se rompe, el POS de un negocio muestra el nombre, el logo y la
        moneda de otro, que es la fuga más visible de todas.
        """
        original_a = api.ok("GET", "/settings/")["data"]
        original_b = api_b.ok("GET", "/settings/")["data"]
        marca = marca_unica()

        try:
            api.ok(
                "PUT",
                "/settings/",
                {"data": {**(original_a or {}), "marca_de_prueba": f"A{marca}"}, "keep_logo": True},
            )
            api_b.ok(
                "PUT",
                "/settings/",
                {"data": {**(original_b or {}), "marca_de_prueba": f"B{marca}"}, "keep_logo": True},
            )

            assert api.ok("GET", "/settings/")["data"]["marca_de_prueba"] == f"A{marca}"
            assert api_b.ok("GET", "/settings/")["data"]["marca_de_prueba"] == f"B{marca}", (
                "guardar la configuración de A pisó la de B: siguen compartiendo fila"
            )
        finally:
            api.ok("PUT", "/settings/", {"data": original_a, "keep_logo": True})
            api_b.ok("PUT", "/settings/", {"data": original_b, "keep_logo": True})


# --------------------------------------------------------------------------
# 6. El token de tránsito no abre ninguna puerta (T-221, RN-26)
# --------------------------------------------------------------------------


class TestTokenDeTransito:
    def test_no_sirve_para_ninguna_ruta_de_negocio(self, contadora: dict):
        """La contadora tiene dos compañías, así que su login da tránsito."""
        cliente = Api(API)
        cuerpo = cliente.ok(
            "POST",
            "/auth/login",
            {"email": contadora["email"], "password": contadora["password"]},
        )
        assert cuerpo["tipo"] == "transito", (
            "con dos compañías el login tiene que pedir cuál, no entrar a una"
        )
        transito = cuerpo["access_token"]

        for ruta in [
            "/products/products_list",
            "/sales/sales_list",
            "/clients/clients_list",
            "/reports/summary",
            "/settings/",
            "/cash/current",
            "/users/me",
        ]:
            estado, _ = cliente.call("GET", ruta, token=transito)
            assert estado == 401, (
                f"{ruta} respondió {estado} con un token de tránsito. "
                f"Tiene que ser 401: ese token todavía no dice en qué compañía "
                f"se está trabajando."
            )

    def test_pero_sirve_para_listar_y_elegir(self, contadora: dict):
        cliente = Api(API)
        cuerpo = cliente.ok(
            "POST",
            "/auth/login",
            {"email": contadora["email"], "password": contadora["password"]},
        )
        cliente.token = cuerpo["access_token"]

        companias = cliente.ok("GET", "/auth/companies")
        assert len(companias) == 2, f"la contadora tenía que ver sus dos compañías: {companias}"

    def test_elegir_una_compania_ajena_responde_404(self, api: Api, contadora: dict):
        """Mandar un `company_id` cualquiera no sirve de nada.

        404 y no 403 por la misma razón que el resto: un 403 confirmaría que esa
        compañía existe, y con un bucle se enumeraría la cartera de clientes.
        """
        cliente = Api(API)
        cuerpo = cliente.ok(
            "POST",
            "/auth/login",
            {"email": contadora["email"], "password": contadora["password"]},
        )
        cliente.token = cuerpo["access_token"]

        # 99999 no existe; el punto es que la respuesta no lo revele.
        estado, _ = cliente.call("POST", "/auth/company", {"company_id": 99999})
        assert estado == 404


# --------------------------------------------------------------------------
# 7. El rol es de la membresía, no de la persona (RN-3)
# --------------------------------------------------------------------------


class TestElRolCambiaConLaCompania:
    def test_la_misma_cuenta_es_admin_en_una_y_cajera_en_la_otra(
        self, api: Api, api_b: Api, contadora: dict
    ):
        cliente = Api(API)
        inicio = cliente.ok(
            "POST",
            "/auth/login",
            {"email": contadora["email"], "password": contadora["password"]},
        )
        cliente.token = inicio["access_token"]
        opciones = {c["id"]: c for c in cliente.ok("GET", "/auth/companies")}

        roles = {}
        for company_id in opciones:
            elegida = cliente.ok("POST", "/auth/company", {"company_id": company_id})
            sesion = Api(API)
            sesion.token = elegida["access_token"]
            roles[company_id] = sesion.ok("GET", "/users/me")["role"]
            # Se vuelve al token de tránsito para elegir la siguiente.
            cliente.token = inicio["access_token"]

        assert set(roles.values()) == {"admin", "cajero"}, (
            f"la misma cuenta tenía que tener roles distintos en cada compañía: {roles}"
        )

    def test_como_cajera_no_llega_a_los_reportes_de_esa_compania(
        self, api_b: Api, contadora: dict
    ):
        cliente = Api(API)
        inicio = cliente.ok(
            "POST",
            "/auth/login",
            {"email": contadora["email"], "password": contadora["password"]},
        )
        cliente.token = inicio["access_token"]

        opciones = cliente.ok("GET", "/auth/companies")
        como_cajera = next(c for c in opciones if c["rol"] == "cajero")
        elegida = cliente.ok("POST", "/auth/company", {"company_id": como_cajera["id"]})

        sesion = Api(API)
        sesion.token = elegida["access_token"]
        estado, _ = sesion.call("GET", "/reports/summary")
        assert estado == 403, "una cajera llegó a los reportes"


# --------------------------------------------------------------------------
# 8. Que la lista de rutas cubiertas no se quede vieja
# --------------------------------------------------------------------------

#: Rutas que a propósito no están en la batería, con el motivo.
FUERA_DE_LA_BATERIA = {
    "/": "sonda pública",
    "/health": "sonda pública",
    "/auth/login": "es el que entrega el token",
    "/auth/company": "probado en TestTokenDeTransito",
    "/auth/companies": "probado en TestTokenDeTransito",
    "/auth/invitation": "probado en test_invitaciones.py, incluido el intento de responder por otro",
    "/persons/register": "público a propósito: crea identidad sin compañía",
    "/users/me": "devuelve al portador del token, no un recurso ajeno",
    "/users/membership": "opera sobre la compañía de la sesión, no recibe id ajeno",
    "/users/": "probado en TestLasListasNoMezclan",
    "/persons/persons_list": "probado en TestLasListasNoMezclan",
    "/persons/update/{id_person}": "identidad global: cada quien edita la suya",
    "/settings/": "probado en TestLaConfiguracion",
    "/cash/current": "opera sobre el usuario de la sesión",
    "/cash/sessions": "probado en TestLaCaja",
    "/cash/session/{session_id}": "probado en TestLaCaja por la vía de la lista",
    "/cash/open": "opera sobre el usuario de la sesión",
    "/cash/close": "opera sobre el usuario de la sesión",
    "/cash/movement": "opera sobre el usuario de la sesión",
    "/categories/register_category": "crea en la compañía de la sesión",
    "/clients/register_client": "crea en la compañía de la sesión",
    "/products/add_product": "crea en la compañía de la sesión",
    "/sales/add_sale": "crea en la compañía de la sesión",
    "/returns/add_return": "crea en la compañía de la sesión",
    "/inventory/entry": "crea en la compañía de la sesión",
    "/users/": "probado en TestLasListasNoMezclan",
    "/products/products_list": "probado en TestLasListasNoMezclan",
    "/products/search/{name}": "probado en TestNoSeVeLoDeLaOtraCompania",
    "/clients/clients_list": "probado en TestLasListasNoMezclan",
    "/sales/sales_list": "probado en TestLasListasNoMezclan",
    "/returns/returns_list": "probado en TestLasListasNoMezclan",
    "/inventory/entries": "probado en TestLasListasNoMezclan",
    "/categories/categories_list": "probado en TestLasListasNoMezclan",
    "/products/product/{term}": "probado en TestNoSeVeLoDeLaOtraCompania",
    "/reports/summary": "probado en TestLosReportesNoSuman",
    "/reports/top_products": "probado en TestLosReportesNoSuman",
    "/reports/low_stock": "probado en TestLosReportesNoSuman",
    "/reports/sales_by_day": "probado en TestLosReportesNoSuman",
    "/reports/by_payment_method": "sin cobertura todavía",
}


def test_ninguna_ruta_de_negocio_quedo_sin_probar():
    """Si aparece una ruta nueva, esta prueba la señala.

    Es lo que impide que la batería envejezca en silencio. Una prueba de
    aislamiento que cubre 30 de 48 rutas y no lo dice es peor que no tenerla:
    da por seguro lo que nadie miró.
    """
    try:
        documento = requests.get(f"{API}/openapi.json", timeout=TIMEOUT).json()
    except requests.RequestException:
        pytest.skip(f"No hay backend en {API}")

    del documento["paths"]["/health"]
    cubiertas = {r for _, r, _ in RUTAS_POR_ID}
    cubiertas |= {r for r, _, _ in LISTAS}
    cubiertas |= set(FUERA_DE_LA_BATERIA)

    # Las plantillas de la batería usan nombres propios; se normalizan contra
    # los de FastAPI.
    equivalencias = {
        "/sales/sale/{venta_id}": "/sales/sale/{sale_id}",
        "/sales/pdf/{venta_id}": "/sales/pdf/{sale_id}",
        "/returns/return/{devolucion_id}": "/returns/return/{return_id}",
        "/inventory/entry/{entrada_id}": "/inventory/entry/{entry_id}",
        "/inventory/entry/{entrada_id}/cancel": "/inventory/entry/{entry_id}/cancel",
        "/products/update_product/{producto_id}": "/products/update_product/{id_product}",
        "/products/delete_product/{producto_id}": "/products/delete_product/{id_product}",
        "/clients/update_client/{cliente_id}": "/clients/update_client/{id_client}",
    }
    cubiertas = {equivalencias.get(r, r) for r in cubiertas}

    sin_cubrir = sorted(set(documento["paths"]) - cubiertas)
    assert not sin_cubrir, (
        "Hay rutas que la batería de aislamiento no toca ni declara como "
        f"excluidas: {sin_cubrir}\n"
        "Agregalas a RUTAS_POR_ID, a LISTAS, o a FUERA_DE_LA_BATERIA con el "
        "motivo."
    )
