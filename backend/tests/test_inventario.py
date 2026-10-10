"""
El kárdex de punta a punta (F15, T-1502, RN-98).

Contra la pila de verdad, porque lo que se comprueba acá es justo lo que los
dobles no pueden: que `products.stock`, `stock_levels` y el kárdex digan lo
mismo después de cada documento que mueve existencias, con MySQL en el medio y
los candados de verdad. Es la prueba de integración que pide el plan §15.7.
"""

from __future__ import annotations

from .conftest import Api, codigo, marca_unica
from .test_characterization import vender


def kardex(api: Api, producto: dict) -> list[dict]:
    return api.ok("GET", f"/inventory/kardex?product_id={producto['id_product']}")


def niveles(api: Api, producto: dict) -> list[dict]:
    return api.ok("GET", f"/inventory/levels?product_id={producto['id_product']}")


def existencia(api: Api, producto: dict) -> int:
    return api.ok("GET", f"/products/product/{producto['barcode']}")["stock"]


def cuadra(api: Api, producto: dict) -> int:
    """La ficha es la suma de las sucursales. Devuelve la existencia."""
    total = existencia(api, producto)
    assert total == sum(n["quantity"] for n in niveles(api, producto)), (
        "`products.stock` y `stock_levels` se separaron"
    )
    return total


def entrar(api: Api, producto: dict, cantidad: int, costo: float) -> dict:
    return api.ok(
        "POST",
        "/inventory/entry",
        {
            "document_number": f"K-{marca_unica()}",
            "source": "manual",
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "lines": [
                {"id_product": producto["id_product"], "quantity": cantidad, "unit_cost": costo}
            ],
        },
    )


def devolver(api: Api, venta: dict, producto: dict, cantidad: int) -> dict:
    return api.ok(
        "POST",
        "/returns/add_return",
        {
            "sale_id": venta["id_sale"],
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "reason": "no era",
            "items": [{"id_product": producto["id_product"], "quantity": cantidad}],
        },
    )


class TestLaApertura:
    def test_la_existencia_inicial_es_un_movimiento_de_apertura(self, api: Api, producto):
        """RF-94: la ficha ya no escribe `stock`; lo abre el kárdex."""
        p = producto("Apertura", 1000, 10)

        [apertura] = kardex(api, p)
        assert apertura["kind"] == "opening"
        assert (apertura["before_qty"], apertura["quantity"], apertura["after_qty"]) == (0, 10, 10)
        assert apertura["source_type"] == "product"
        assert apertura["source_id"] == p["id_product"]
        assert apertura["source_line"] is None
        # A costo cero: no se conoce hasta la primera compra (RN-54).
        assert apertura["unit_cost"] == 0 and apertura["avg_cost_after"] == 0
        assert apertura["user_id"] == api.user_id  # type: ignore[attr-defined]

        [nivel] = niveles(api, p)
        assert nivel["quantity"] == 10 and nivel["branch_id"] == apertura["branch_id"]
        assert cuadra(api, p) == 10

    def test_un_producto_sin_existencia_no_deja_fila(self, api: Api, producto):
        p = producto("En cero", 1000, 0)
        assert kardex(api, p) == []
        assert niveles(api, p) == []
        assert cuadra(api, p) == 0


class TestCadaDocumentoDejaSuFila:
    def test_venta_devolucion_entrada_y_anulacion(self, api: Api, producto):
        """La verificación de T-1502, tal como está escrita en task.md."""
        p = producto("Recorrido", 1000, 10)

        _, (estado, venta) = vender(api, [(p, 3)])
        assert estado == 200
        assert cuadra(api, p) == 7
        [salida, _apertura] = kardex(api, p)
        assert salida["kind"] == "sale"
        assert (salida["before_qty"], salida["quantity"], salida["after_qty"]) == (10, -3, 7)
        assert (salida["source_type"], salida["source_id"], salida["source_line"]) == (
            "sale", venta["id_sale"], 1,
        )

        devolver(api, venta, p, 1)
        assert cuadra(api, p) == 8
        [reposicion, *_] = kardex(api, p)
        assert reposicion["kind"] == "return"
        assert (reposicion["before_qty"], reposicion["quantity"], reposicion["after_qty"]) == (7, 1, 8)
        assert reposicion["source_type"] == "return"

        entrada = entrar(api, p, 24, 1200)
        assert cuadra(api, p) == 32
        [ingreso, *_] = kardex(api, p)
        assert ingreso["kind"] == "entry"
        assert (ingreso["before_qty"], ingreso["quantity"], ingreso["after_qty"]) == (8, 24, 32)
        assert ingreso["unit_cost"] == 1200
        # El promedio DESPUÉS de la entrada (RN-98): 8 sin costo y 24 a 1 200.
        assert ingreso["avg_cost_after"] == 900
        assert (ingreso["source_type"], ingreso["source_id"]) == ("stock_entry", entrada["id_entry"])

        api.ok("POST", f"/inventory/entry/{entrada['id_entry']}/cancel")
        assert cuadra(api, p) == 8
        [reversion, *_] = kardex(api, p)
        assert reversion["kind"] == "entry_void"
        assert (reversion["before_qty"], reversion["quantity"], reversion["after_qty"]) == (32, -24, 8)
        # Al costo de la entrada, no al promedio de hoy.
        assert reversion["unit_cost"] == 1200
        assert (reversion["source_type"], reversion["source_id"]) == ("stock_entry", entrada["id_entry"])

        # Cinco filas, de la más reciente a la más vieja, y ninguna editada.
        assert [m["kind"] for m in kardex(api, p)] == [
            "entry_void", "entry", "return", "sale", "opening",
        ]

    def test_la_venta_sale_al_promedio_del_momento(self, api: Api, producto):
        p = producto("Promedio", 1000, 0)
        entrar(api, p, 10, 900)
        _, (estado, _) = vender(api, [(p, 2)])
        assert estado == 200

        [salida, *_] = kardex(api, p)
        assert salida["unit_cost"] == 900 and salida["avg_cost_after"] == 900
        assert cuadra(api, p) == 8

    def test_el_kardex_se_lee_tambien_por_documento(self, api: Api, producto):
        p = producto("Por documento", 1000, 5)
        q = producto("Por documento 2", 2000, 5)
        _, (estado, venta) = vender(api, [(p, 1), (q, 2)])
        assert estado == 200

        filas = api.ok("GET", f"/inventory/kardex?source_type=sale&source_id={venta['id_sale']}")
        assert [(f["product_id"], f["source_line"], f["quantity"]) for f in filas] == [
            (p["id_product"], 1, -1),
            (q["id_product"], 2, -2),
        ]
        # Y acotado a un producto, cuando se pregunta desde la línea.
        de_q = api.ok(
            "GET",
            f"/inventory/kardex?product_id={q['id_product']}&source_type=sale&source_id={venta['id_sale']}",
        )
        assert [f["source_line"] for f in de_q] == [2]

    def test_sin_producto_ni_documento_no_hay_que_listar(self, api: Api):
        assert codigo(api.call("GET", "/inventory/kardex"), 400) == "kardex_filter_required"
        assert codigo(api.call("GET", "/inventory/kardex?source_type=sale"), 400) == (
            "kardex_filter_required"
        )
        assert codigo(api.call("GET", "/inventory/levels"), 400) == "kardex_filter_required"


class TestLaFichaYaNoEscribeLaExistencia:
    def test_editar_el_stock_desde_la_ficha_responde_con_codigo(self, api: Api, producto):
        p = producto("Intocable", 1000, 10)
        respuesta = api.call("PUT", f"/products/update_product/{p['id_product']}", {"stock": 99})
        assert codigo(respuesta, 400) == "stock_not_editable"
        assert respuesta[1]["detail"]["product_id"] == p["id_product"]
        assert cuadra(api, p) == 10

    def test_lo_demas_de_la_ficha_sigue_editandose(self, api: Api, producto):
        p = producto("Editable", 1000, 10)
        api.ok("PUT", f"/products/update_product/{p['id_product']}", {"price": 1200})
        assert api.ok("GET", f"/products/product/{p['barcode']}")["price"] == 1200

    def test_un_producto_con_kardex_no_se_borra(self, api: Api, producto):
        p = producto("Con historia", 1000, 3)
        respuesta = api.call("DELETE", f"/products/delete_product/{p['id_product']}")
        assert codigo(respuesta, 400) == "product_has_movements"
        assert respuesta[1]["detail"]["movements"] == 1
        assert cuadra(api, p) == 3

    def test_uno_que_nunca_tuvo_existencia_si(self, api: Api, producto):
        p = producto("Sin historia", 1000, 0)
        api.ok("DELETE", f"/products/delete_product/{p['id_product']}")
        assert api.call("GET", f"/products/product/{p['barcode']}")[0] == 404
