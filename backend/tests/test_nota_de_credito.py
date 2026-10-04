"""
La nota de crédito de una devolución, contra el stack real (T-725, RN-89).

Las reglas están probadas sin base en `tests/domain/test_fe_notes.py` y
`tests/application/test_register_return.py`. Acá se comprueba lo que solo se ve
con MySQL y HTTP: que las columnas se llenen y vuelvan en el API, que anular
reponga el inventario como una devolución total, y que la nota la decida la
venta original aunque la configuración haya cambiado después.

Toca la configuración de la compañía A y la deja como estaba al terminar.
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo, marca_unica

pytestmark = pytest.mark.characterization


def vender(api: Api, producto: dict, cantidad: int = 3) -> int:
    subtotal = round(producto["price"] * cantidad, 2)
    impuesto = round(subtotal * 0.13, 2)
    total = round(subtotal + impuesto, 2)
    hecha = api.ok(
        "POST",
        "/sales/add_sale",
        {
            "sale_number": marca_unica(),
            "client_id": None,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "subtotal": subtotal,
            "tax": impuesto,
            "total": total,
            "payment_method": "Efectivo",
            "cash_received": total,
            "change_given": 0.0,
            "products": [{"id_product": producto["id_product"], "stock": cantidad}],
        },
    )
    return hecha["id_sale"]


def devolver(api: Api, venta: int, producto: dict, cantidad: int, *, anular: bool = False):
    return api.call(
        "POST",
        "/returns/add_return",
        {
            "sale_id": venta,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "reason": "anulación de prueba" if anular else "devolución de prueba",
            "items": [{"id_product": producto["id_product"], "quantity": cantidad}],
            "annul": anular,
        },
    )


def leer(api: Api, id_return: int) -> dict:
    return api.ok("GET", f"/returns/return/{id_return}")


def existencias(api: Api, producto: dict) -> int:
    return api.ok("GET", f"/products/product/{producto['barcode']}")["stock"]


class TestLaDevolucionDeUnComprobante:
    def test_devolver_parte_de_un_tiquete_es_nc_por_devolucion(
        self, api: Api, producto, facturacion
    ):
        facturacion(True)
        p = producto("NC parcial", 1000, 10)
        venta = vender(api, p)

        estado, cuerpo = devolver(api, venta, p, 1)
        assert estado == 200, cuerpo
        assert cuerpo["document_type"] == "03"

        nota = leer(api, cuerpo["id_return"])
        assert (nota["document_type"], nota["reference_code"]) == ("03", "06")
        # Lo que la nota impresa dice del original.
        assert nota["sale_document_type"] == "04"
        assert nota["sale_created_at"] is not None
        assert nota["items"][0]["tax_rate"] == pytest.approx(0.13)

    def test_la_nota_la_decide_la_venta_y_no_la_configuracion_de_hoy(
        self, api: Api, producto, facturacion
    ):
        facturacion(True)
        p = producto("NC tras apagar", 1000, 10)
        venta = vender(api, p)

        facturacion(False)
        estado, cuerpo = devolver(api, venta, p, 1)
        assert estado == 200, cuerpo
        assert leer(api, cuerpo["id_return"])["document_type"] == "03"

    def test_una_venta_que_no_fue_comprobante_no_emite_nota(
        self, api: Api, producto, facturacion
    ):
        facturacion(False)
        p = producto("Sin NC", 1000, 10)
        venta = vender(api, p)

        estado, cuerpo = devolver(api, venta, p, 1)
        assert estado == 200, cuerpo
        assert cuerpo["document_type"] is None
        nota = leer(api, cuerpo["id_return"])
        assert (nota["document_type"], nota["reference_code"]) == (None, None)


class TestAnular:
    def test_anular_es_una_nc_que_anula_y_repone_todo(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Anular", 1000, 10)
        venta = vender(api, p, cantidad=3)
        assert existencias(api, p) == 7

        estado, cuerpo = devolver(api, venta, p, 3, anular=True)
        assert estado == 200, cuerpo

        nota = leer(api, cuerpo["id_return"])
        assert (nota["document_type"], nota["reference_code"]) == ("03", "01")
        assert nota["is_full"] is True
        assert nota["total"] == pytest.approx(3390.0)
        assert existencias(api, p) == 10

    def test_anular_a_medias_no(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Anular a medias", 1000, 10)
        venta = vender(api, p, cantidad=3)

        assert codigo(devolver(api, venta, p, 2, anular=True), 400) == "annul_must_be_full"
        assert existencias(api, p) == 7

    def test_una_venta_con_devoluciones_ya_no_se_anula(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Anular devuelta", 1000, 10)
        venta = vender(api, p, cantidad=3)
        assert devolver(api, venta, p, 1)[0] == 200

        assert codigo(devolver(api, venta, p, 3, anular=True), 409) == "annul_after_return"
        assert existencias(api, p) == 8
