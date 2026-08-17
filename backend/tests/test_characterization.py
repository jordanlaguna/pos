"""
Pruebas de caracterización (T-104).

Fijan el comportamiento de HOY, antes de reorganizar el backend por capas. No
juzgan si está bien: dicen qué hace. Si al mover el código una de estas cambia,
el refactor cambió algo que no debía, y eso es lo único que distingue mover
código de romperlo.

Las cifras salen de `.specify/progress.json` → `invariantes_verificados`, que
se verificaron a mano contra el sistema corriendo. Acá dejan de depender de que
alguien se acuerde de repetirlo.

Necesitan la pila de `docker-compose.test.yml`. Sin ella se omiten.
"""

from __future__ import annotations

import pytest

from .conftest import Api, cerrar_caja_abierta, entrar, marca_unica

pytestmark = pytest.mark.characterization

IVA = 0.13


def numero_de_venta() -> str:
    """Único por venta: el backend lo exige y la prueba corre varias veces."""
    return marca_unica()


def vender(api: Api, lineas: list[tuple[dict, int]], metodo: str = "Efectivo", pago: float | None = None):
    """Cobra una venta calculando los totales como los calcula el POS."""
    subtotal = round(sum(p["price"] * cant for p, cant in lineas), 2)
    impuesto = round(subtotal * IVA, 2)
    total = round(subtotal + impuesto, 2)
    recibido = total if pago is None else pago

    cuerpo = {
        "sale_number": numero_de_venta(),
        "client_id": None,
        "user_id": api.user_id,  # type: ignore[attr-defined]
        "subtotal": subtotal,
        "tax": impuesto,
        "total": total,
        "payment_method": metodo,
        "cash_received": recibido,
        "change_given": round(recibido - total, 2),
        "products": [{"id_product": p["id_product"], "stock": c} for p, c in lineas],
    }
    return cuerpo, api.call("POST", "/sales/add_sale", cuerpo)


# --------------------------------------------------------------- aritmética

class TestTotalesDeVenta:
    """Los números que tiene que dar una venta, tal como se verificaron."""

    def test_tres_unidades_de_1450_dan_4915_50(self, api: Api, producto):
        arroz = producto("Arroz", 1450, 20)
        cuerpo, (estado, respuesta) = vender(api, [(arroz, 3)], pago=5000)

        assert estado == 200, respuesta
        assert cuerpo["subtotal"] == 4350
        assert cuerpo["tax"] == 565.5
        assert cuerpo["total"] == 4915.5
        assert cuerpo["change_given"] == 84.5

        guardada = api.ok("GET", f"/sales/sale/{respuesta['id_sale']}")
        assert guardada["subtotal"] == 4350
        assert guardada["tax"] == 565.5
        assert guardada["total"] == 4915.5

    def test_arroz_mas_cafe_dan_6441(self, api: Api, producto):
        arroz = producto("Arroz", 1450, 20)
        cafe = producto("Café", 4250, 20)
        cuerpo, (estado, _) = vender(api, [(arroz, 1), (cafe, 1)], pago=10000)

        assert estado == 200
        assert (cuerpo["subtotal"], cuerpo["tax"], cuerpo["total"]) == (5700, 741.0, 6441.0)
        assert cuerpo["change_given"] == 3559.0

    def test_la_factura_de_ejemplo_da_5796_90(self, api: Api, producto):
        arroz = producto("Arroz", 1450, 20)
        te = producto("Té", 950, 20)
        chiverre = producto("Chiverre", 2730, 20)
        cuerpo, (estado, _) = vender(api, [(arroz, 1), (te, 1), (chiverre, 1)], pago=6000)

        assert estado == 200
        assert (cuerpo["subtotal"], cuerpo["tax"], cuerpo["total"]) == (5130, 666.9, 5796.9)
        assert cuerpo["change_given"] == 203.1


class TestExistencias:
    def test_la_venta_descuenta_lo_vendido(self, api: Api, producto):
        p = producto("Leche", 1290, 10)
        vender(api, [(p, 3)])

        assert api.ok("GET", f"/products/product/{p['barcode']}")["stock"] == 7

    def test_sin_existencias_no_queda_factura_fantasma(self, api: Api, producto):
        """Defecto 1. Es la prueba que más importa de este archivo."""
        p = producto("Escaso", 1000, 2)
        antes = len(api.ok("GET", "/sales/sales_list"))

        _, (estado, _) = vender(api, [(p, 5)])

        assert estado == 400, "vender sin existencias tiene que fallar"
        assert len(api.ok("GET", "/sales/sales_list")) == antes, (
            "quedó una venta guardada pese al fallo: volvió el defecto 1"
        )
        assert api.ok("GET", f"/products/product/{p['barcode']}")["stock"] == 2


class TestDevolucion:
    def test_devolver_una_unidad_reembolsa_1638_50_y_repone(self, api: Api, producto):
        arroz = producto("Arroz", 1450, 8)
        _, (estado, venta) = vender(api, [(arroz, 1)])
        assert estado == 200
        assert api.ok("GET", f"/products/product/{arroz['barcode']}")["stock"] == 7

        estado, dev = api.call(
            "POST",
            "/returns/add_return",
            {
                "sale_id": venta["id_sale"],
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "reason": "prueba de caracterización",
                "items": [{"id_product": arroz["id_product"], "quantity": 1}],
            },
        )

        assert estado == 200, dev
        assert dev["total"] == 1638.5
        assert api.ok("GET", f"/products/product/{arroz['barcode']}")["stock"] == 8

    def test_usa_la_tasa_de_su_venta_y_no_la_configurada_hoy(self, api: Api, producto):
        """
        Regla del proyecto: si el dueño cambia el IVA, lo que se reembolsa sigue
        siendo lo que se cobró. La tasa se reconstruye como tax / subtotal.

        Se cobra al 13 %, se cambia la configuración al 25 % y recién entonces
        se devuelve. Antes esta prueba fabricaba una venta al 5 % mandando esos
        montos directo al API; desde T-108b eso ya no se puede, porque el
        servidor recalcula los totales con **su** tasa y rechaza lo que no
        cuadre. Cambiar la configuración de verdad es además lo que la regla
        describe.
        """
        p = producto("Cambio de tasa", 1000, 5)
        _, (estado, venta) = vender(api, [(p, 1)])
        assert estado == 200

        original = api.ok("GET", "/settings/")["data"]
        try:
            nueva = {**(original or {}), "impuesto": {"nombre": "IVA", "tasa": 0.25}}
            api.ok("PUT", "/settings/", {"data": nueva, "keep_logo": True})
            assert api.ok("GET", "/settings/")["data"]["impuesto"]["tasa"] == 0.25

            dev = api.ok(
                "POST",
                "/returns/add_return",
                {
                    "sale_id": venta["id_sale"],
                    "user_id": api.user_id,  # type: ignore[attr-defined]
                    "reason": "cambio de tasa",
                    "items": [{"id_product": p["id_product"], "quantity": 1}],
                },
            )
        finally:
            api.ok("PUT", "/settings/", {"data": original, "keep_logo": True})

        # 1000 × 1,13, no × 1,25.
        assert dev["total"] == 1130.0, (
            "se reembolsó con la tasa de hoy y no con la de la venta"
        )


class TestLaPlataLaCalculaElServidor:
    """T-108b, contra el stack de verdad."""

    def _cuerpo(self, api: Api, p, cantidad=3, **cambios):
        subtotal = round(p["price"] * cantidad, 2)
        impuesto = round(subtotal * IVA, 2)
        total = round(subtotal + impuesto, 2)
        cuerpo = {
            "sale_number": numero_de_venta(),
            "client_id": None,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "subtotal": subtotal,
            "tax": impuesto,
            "total": total,
            "payment_method": "Efectivo",
            "cash_received": total,
            "change_given": 0.0,
            "products": [{"id_product": p["id_product"], "stock": cantidad}],
        }
        cuerpo.update(cambios)
        return cuerpo

    def test_un_total_alterado_no_entra(self, api: Api, producto):
        p = producto("Alterado", 1450, 10)
        antes = len(api.ok("GET", "/sales/sales_list"))

        estado, cuerpo = api.call(
            "POST", "/sales/add_sale", self._cuerpo(api, p, total=1.0, cash_received=1.0)
        )

        assert estado == 400, f"se aceptó un total alterado: {cuerpo}"
        assert "no coincide" in str(cuerpo.get("detail", "")).lower()
        assert len(api.ok("GET", "/sales/sales_list")) == antes
        assert api.ok("GET", f"/products/product/{p['barcode']}")["stock"] == 10

    def test_un_subtotal_alterado_tampoco_aunque_el_total_cuadre(self, api: Api, producto):
        # Subtotal e impuesto que se compensan: el total da bien y aun así está mal.
        p = producto("Compensado", 1450, 10)
        estado, _ = api.call(
            "POST", "/sales/add_sale", self._cuerpo(api, p, subtotal=4000.0, tax=915.50)
        )
        assert estado == 400

    def test_lo_que_se_guarda_es_lo_que_calcula_el_servidor(self, api: Api, producto):
        p = producto("Autoridad", 1450, 10)
        venta = api.ok("POST", "/sales/add_sale", self._cuerpo(api, p, cash_received=5000.0))
        guardada = api.ok("GET", f"/sales/sale/{venta['id_sale']}")

        assert guardada["subtotal"] == 4350.0
        assert guardada["tax"] == 565.5
        assert guardada["total"] == 4915.5
        # El vuelto ni se manda: se calcula.
        assert guardada["change_given"] == 84.5

    def test_el_efectivo_tiene_que_alcanzar(self, api: Api, producto):
        p = producto("Pago corto", 1450, 10)
        estado, cuerpo = api.call(
            "POST", "/sales/add_sale", self._cuerpo(api, p, cash_received=100.0)
        )
        assert estado == 400
        assert "efectivo" in str(cuerpo.get("detail", "")).lower()


class TestArqueoDeCaja:
    """
    Cada prueba usa un cajero recién creado (fixture `cajero`).

    No es preciosismo: el turno se delimita por ventana de tiempo sobre
    `sales.created_at`, que es `DATETIME` sin fracción de segundo, y estas
    pruebas corren en milisegundos. Con un cajero compartido, la venta de una
    prueba cae dentro del turno de la siguiente. Ver el comentario del fixture.
    """

    def test_apertura_venta_y_devolucion_dan_53277(self, cajero: Api, producto):
        arroz = producto("Arroz", 1450, 10)

        turno = cajero.ok(
            "POST",
            "/cash/open",
            {"user_id": cajero.user_id, "opening_amount": 50000, "notes": "caracterización"},  # type: ignore[attr-defined]
        )
        assert turno["expected_amount"] == 50000

        _, (estado, venta) = vender(cajero, [(arroz, 3)], pago=5000)
        assert estado == 200

        cajero.ok(
            "POST",
            "/returns/add_return",
            {
                "sale_id": venta["id_sale"],
                "user_id": cajero.user_id,  # type: ignore[attr-defined]
                "reason": "arqueo",
                "items": [{"id_product": arroz["id_product"], "quantity": 1}],
            },
        )

        actual = cajero.ok("GET", "/cash/current")
        assert actual["cash_sales"] == 4915.5
        assert actual["returns_total"] == 1638.5
        # 50 000 + 4 915,50 − 1 638,50
        assert actual["expected_amount"] == 53277.0

        cierre = cajero.ok(
            "POST",
            "/cash/close",
            {"user_id": cajero.user_id, "closing_amount": 53000, "notes": "faltante"},  # type: ignore[attr-defined]
        )
        assert cierre["difference"] == -277.0, "el faltante dejó de calcularse igual"
        assert cierre["status"] == "cerrada"

    def test_la_hora_de_la_venta_la_pone_el_servidor(self, cajero: Api, producto):
        """
        Defecto 9. El POS mandaba `created_at` y bastaban unos segundos de
        desfase para que una venta quedara fechada antes de la apertura del
        turno y desapareciera del arqueo.
        """
        p = producto("Reloj", 1000, 5)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 0})  # type: ignore[attr-defined]

        cuerpo = {
            "sale_number": numero_de_venta(),
            "client_id": None,
            "user_id": cajero.user_id,  # type: ignore[attr-defined]
            "subtotal": 1000.0,
            "tax": 130.0,
            "total": 1130.0,
            "payment_method": "Efectivo",
            "cash_received": 1130.0,
            "change_given": 0.0,
            # Un año atrás: si el backend lo respetara, la venta caería fuera
            # del turno y el arqueo daría 0.
            "created_at": "2025-01-01T00:00:00",
            "products": [{"id_product": p["id_product"], "stock": 1}],
        }
        cajero.ok("POST", "/sales/add_sale", cuerpo)

        actual = cajero.ok("GET", "/cash/current")
        assert actual["cash_sales"] == 1130.0, (
            "la venta no entró en el turno: el backend usó la fecha del cliente"
        )
        cerrar_caja_abierta(cajero)


class TestReportes:
    def test_las_netas_son_las_brutas_menos_las_devoluciones(
        self, api: Api, cajero: Api, producto
    ):
        """
        El invariante `reportes_dia` de progress.json: brutas 4 915,50,
        devoluciones 1 638,50, netas 3 277,00.

        El reporte lo lee el **administrador**: `/reports/` es solo para ese rol,
        y esa restricción tiene su propia prueba más abajo. La venta la hace un
        cajero recién creado.

        Se comparan **diferencias** y no totales absolutos: el reporte suma por
        rango de fechas, no por cajero, así que el total del día arrastra lo que
        hicieron las otras pruebas. La diferencia sí es solo lo de esta.
        """
        arroz = producto("Arroz", 1450, 10)

        antes = api.ok("GET", "/reports/summary?days=1")
        _, (estado, venta) = vender(cajero, [(arroz, 3)], pago=5000)
        assert estado == 200

        cajero.ok(
            "POST",
            "/returns/add_return",
            {
                "sale_id": venta["id_sale"],
                "user_id": cajero.user_id,  # type: ignore[attr-defined]
                "reason": "reportes",
                "items": [{"id_product": arroz["id_product"], "quantity": 1}],
            },
        )
        despues = api.ok("GET", "/reports/summary?days=1")

        assert round(despues["gross_total"] - antes["gross_total"], 2) == 4915.50
        assert round(despues["returns_total"] - antes["returns_total"], 2) == 1638.50
        assert round(despues["net_total"] - antes["net_total"], 2) == 3277.00


class TestPermisos:
    def test_sin_credenciales_no_se_lee_nada(self, api: Api):
        for ruta in [
            "/products/products_list",
            "/sales/sales_list",
            "/cash/current",
            "/reports/summary",
            "/settings/",
        ]:
            estado, _ = api.call("GET", ruta, token=None)
            assert estado == 401, f"{ruta} respondió {estado} sin token"

    def test_el_cajero_no_entra_a_lo_de_administracion(self, api: Api):
        cajero = {
            "name": "Beto",
            "lastName": "Caja",
            "secondName": "Prueba",
            "identification": "100000002",
            "birth_date": "1995-05-05",
            "telephone": "80000002",
            "email": "cajero@pruebas.ventasys.cr",
            "password": "prueba123",
        }
        api.registrar(cajero)
        api.ok("POST", "/users/membership", {"email": cajero["email"], "role": "cajero"})

        suyo = Api(api.base)
        entrar(suyo, cajero["email"], cajero["password"], aceptando_invitaciones=True)
        token = suyo.token

        assert api.call("GET", "/users/me", token=token)[0] == 200
        assert api.call("GET", "/products/products_list", token=token)[0] == 200

        estado, _ = api.call("GET", "/reports/summary", token=token)
        assert estado == 403, f"un cajero llegó a los reportes: {estado}"

        estado, _ = api.call("PUT", "/settings/", {"data": {}}, token=token)
        assert estado == 403, f"un cajero pudo tocar la configuración: {estado}"


class TestConfiguracion:
    def test_la_lee_cualquiera_con_sesion_y_la_escribe_solo_admin(self, api: Api):
        estado, cuerpo = api.call("GET", "/settings/")
        assert estado == 200
        assert "data" in cuerpo
