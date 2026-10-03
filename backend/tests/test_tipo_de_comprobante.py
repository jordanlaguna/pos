"""
El tipo de comprobante de cada venta, contra el stack real (T-723, RN-85).

Las reglas están probadas sin base en `tests/domain/test_fe_document_type.py` y
`tests/application/test_register_sale.py`. Acá se comprueba lo que solo se ve
con MySQL y HTTP: que la columna exista y se llene, que el detalle y el listado
la devuelvan, que el interruptor de Configuración se lea igual que en el POS, y
que un cliente de **otra compañía** no pase por la foránea, que no sabe de
compañías.

Toca la configuración de la compañía A y la deja como estaba al terminar.
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo, marca_unica

pytestmark = pytest.mark.characterization


def venta(api: Api, producto: dict, **cambios) -> dict:
    subtotal = round(producto["price"], 2)
    impuesto = round(subtotal * 0.13, 2)
    total = round(subtotal + impuesto, 2)
    cuerpo = {
        "sale_number": marca_unica(),
        "client_id": None,
        "user_id": api.user_id,  # type: ignore[attr-defined]
        "subtotal": subtotal,
        "tax": impuesto,
        "total": total,
        "payment_method": "Efectivo",
        "cash_received": total,
        "change_given": 0.0,
        "products": [{"id_product": producto["id_product"], "stock": 1}],
    }
    cuerpo.update(cambios)
    return cuerpo


def cliente_de(api: Api) -> int:
    marca = marca_unica()
    hecho = api.ok(
        "POST",
        "/clients/register_client",
        {
            "identification": f"7{marca[-8:]}",
            "name": "Receptor",
            "last_name": "De Prueba",
            "second_name": "Integración",
            "email": f"receptor{marca}@ejemplo.cr",
            "telephone": 22223333,
            "address": "San José",
            "register_date": "2026-01-01",
        },
    )
    return hecho["id_client"]


def tipo_guardado(api: Api, id_sale: int) -> str | None:
    return api.ok("GET", f"/sales/sale/{id_sale}")["document_type"]


class TestConLaFacturacionActiva:
    def test_sin_cliente_sale_tiquete(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Tiquete", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        assert tipo_guardado(api, hecha["id_sale"]) == "04"

    def test_con_cliente_sale_factura(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Factura", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_de(api)))
        assert tipo_guardado(api, hecha["id_sale"]) == "01"

    def test_el_cajero_puede_dejarla_en_tiquete(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Cliente sin factura", 1000, 5)
        hecha = api.ok(
            "POST",
            "/sales/add_sale",
            venta(api, p, client_id=cliente_de(api), document_type="04"),
        )
        assert tipo_guardado(api, hecha["id_sale"]) == "04"

    def test_la_factura_sin_cliente_no_entra(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Factura sin receptor", 1000, 5)
        respuesta = api.call("POST", "/sales/add_sale", venta(api, p, document_type="01"))
        assert codigo(respuesta, 400) == "invoice_needs_receiver"
        # Y no tocó el inventario: la regla corre antes de la transacción.
        assert api.ok("GET", f"/products/product/{p['barcode']}")["stock"] == 5

    def test_la_forma_vieja_de_la_configuracion_tambien_cuenta(
        self, api: Api, producto, facturacion
    ):
        facturacion(True, forma="vieja")
        p = producto("Configuración vieja", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        assert tipo_guardado(api, hecha["id_sale"]) == "04"


class TestConLaFacturacionApagada:
    def test_la_venta_no_lleva_tipo_aunque_se_lo_pidan(self, api: Api, producto, facturacion):
        facturacion(False)
        p = producto("Sin facturación", 1000, 5)
        hecha = api.ok(
            "POST",
            "/sales/add_sale",
            venta(api, p, client_id=cliente_de(api), document_type="01"),
        )
        assert tipo_guardado(api, hecha["id_sale"]) is None


class TestLoQueEmiteLaCompania:
    """RN-88, contra el stack: la lista de Configuración manda en la venta."""

    def test_solo_factura_obliga_a_elegir_cliente(self, api: Api, producto, facturacion):
        facturacion(True, tipos=["01", "03"])
        p = producto("Solo factura", 1000, 5)
        assert codigo(api.call("POST", "/sales/add_sale", venta(api, p)), 400) == (
            "invoice_needs_receiver"
        )
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_de(api)))
        assert tipo_guardado(api, hecha["id_sale"]) == "01"

    def test_un_tipo_apagado_no_entra(self, api: Api, producto, facturacion):
        facturacion(True, tipos=["01", "03"])
        p = producto("Tiquete apagado", 1000, 5)
        estado, cuerpo = api.call(
            "POST", "/sales/add_sale", venta(api, p, client_id=cliente_de(api), document_type="04")
        )
        assert codigo((estado, cuerpo), 400) == "document_type_not_enabled"
        assert cuerpo["detail"]["document_type"] == "04"

    def test_una_lista_sin_con_que_vender_vuelve_a_la_de_fabrica(
        self, api: Api, producto, facturacion
    ):
        # Escrita a mano: solo notas. El servidor no la obedece hasta dejar al
        # negocio sin poder cobrar.
        facturacion(True, tipos=["03", "02"])
        p = producto("Lista rota", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        assert tipo_guardado(api, hecha["id_sale"]) == "04"


class TestLoQueSeRechazaSiempre:
    def test_un_tipo_que_el_mostrador_no_emite(self, api: Api, producto, facturacion):
        facturacion(False)
        p = producto("Tipo raro", 1000, 5)
        estado, cuerpo = api.call("POST", "/sales/add_sale", venta(api, p, document_type="03"))
        assert codigo((estado, cuerpo), 400) == "invalid_sale_document_type"
        assert cuerpo["detail"]["document_type"] == "03"

    def test_el_cliente_de_otra_compania(self, api: Api, api_b: Api, producto):
        """Antes entraba: la foránea de `sales.client_id` no sabe de compañías."""
        ajeno = cliente_de(api_b)
        p = producto("Cliente ajeno", 1000, 5)
        respuesta = api.call("POST", "/sales/add_sale", venta(api, p, client_id=ajeno))
        assert codigo(respuesta, 404) == "client_not_found"
        assert api.ok("GET", f"/products/product/{p['barcode']}")["stock"] == 5


def test_el_listado_trae_el_tipo(api: Api, producto, facturacion):
    facturacion(True)
    p = producto("En el listado", 1000, 5)
    hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
    fila = next(s for s in api.ok("GET", "/sales/sales_list") if s["id"] == hecha["id_sale"])
    assert fila["document_type"] == "04"


def test_el_pdf_del_backend_ya_no_existe(api: Api, producto):
    """T-922: el documento impreso sale de la plantilla del POS y de ningún otro lado."""
    p = producto("Sin PDF", 1000, 5)
    hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
    estado, _ = api.call("GET", f"/sales/pdf/{hecha['id_sale']}")
    assert estado == 404
