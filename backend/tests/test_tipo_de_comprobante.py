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

from .conftest import (
    API,
    EMISOR_COMPLETO,
    PLAN_DE_PRUEBAS,
    Api,
    afiliado_unico,
    bootstrap,
    codigo,
    entrar,
    fijar_cedula,
    marca_unica,
)

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


PARTIDA = "090111000000"
CABYS_MERCANCIA = "2316100000100"
DIRECCION = "12 Main St, Miami, FL 33101, United States"


def cliente_extranjero(api: Api, *, direccion: str | None = DIRECCION) -> int:
    """Un cliente del extranjero (identificación 05): un pasaporte, no dígitos."""
    marca = marca_unica()
    cuerpo = {
        "identification": f"P{marca[-7:]}",
        "identification_type": "05",
        "name": "Foreign",
        "last_name": "Buyer",
        "second_name": "Inc",
        "email": f"buyer{marca}@example.com",
        "register_date": "2026-01-01",
    }
    if direccion is not None:
        cuerpo["foreign_address"] = direccion
    return api.ok("POST", "/clients/register_client", cuerpo)["id_client"]


def exportable(api: Api, producto: dict, *, partida: str | None = PARTIDA, tax_code: str = "08") -> dict:
    """Una mercancía con CABYS, unidad, tarifa y partida: lo que la FEE pide."""
    api.ok(
        "PUT",
        f"/products/update_product/{producto['id_product']}",
        {
            "cabys_code": CABYS_MERCANCIA,
            "unit_of_measure": "Unid",
            "tax_code": tax_code,
            "tariff_heading": partida,
        },
    )
    return producto


def compania_sin_ambiente_elegido(soporte: Api, quien: str) -> Api:
    """Una compañía recién dada de alta, con cédula de emisor y nada más.

    Es la única que puede estar en la forma vieja de la configuración. La A ya
    no: `eInvoicing.environment` se escribe por su puerta protegida (T-611) y
    sobrevive a cualquier guardado, y en cuanto existe la clave nueva **está**
    y manda sobre `electronica` aunque no diga si la facturación está
    encendida (`_seccion_electronica`, la misma regla que `legacy()` en el
    POS). La A pasa a producción y vuelve en `test_emision.py`, así que en
    ella la forma vieja ya no puede darse.
    """
    marca = marca_unica()
    # Corto: `users.email` es VARCHAR(50) y el alta falla callada si se pasa.
    correo = f"tipo.{quien}.{marca}@pruebas.cr"
    bootstrap(
        afiliado=afiliado_unico(),
        compania=1,
        nombre=f"Compañía {quien} {marca}",
        email=correo,
        password="prueba123",
        rol="admin",
        nombre_persona="Vera",
        apellido=quien.capitalize(),
        cedula=marca[-9:],
        **PLAN_DE_PRUEBAS,
    )
    cliente = Api(API)
    sesion = entrar(cliente, correo, "prueba123")
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    cliente.company_id = sesion["company_id"]  # type: ignore[attr-defined]
    fijar_cedula(soporte, cliente.company_id)  # type: ignore[attr-defined]
    return cliente


def producto_de(cliente: Api, nombre: str, precio: float, stock: int) -> dict:
    """Como la fixture `producto`, pero en la compañía que se le diga."""
    cliente.call("POST", "/categories/register_category", {"name": "Pruebas"})
    categoria = next(
        c["id"] for c in cliente.ok("GET", "/categories/categories_list") if c["name"] == "Pruebas"
    )
    marca = marca_unica()
    cuerpo = {
        "name": f"{nombre} {marca}",
        "description": "producto de prueba",
        "price": precio,
        "stock": stock,
        "barcode": f"T{marca}",
        "created_at": "2026-01-01T00:00:00",
        "category_id": categoria,
    }
    cliente.ok("POST", "/products/add_product", cuerpo)
    return cliente.ok("GET", f"/products/product/{cuerpo['barcode']}")


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

    def test_la_forma_vieja_de_la_configuracion_tambien_cuenta(self, soporte: Api):
        """Una fila de antes de T-113 —`electronica.activa`, sin `eInvoicing`—
        tiene que seguir queriendo decir lo mismo. Sobre una compañía propia:
        ver `compania_sin_ambiente_elegido`."""
        vieja = compania_sin_ambiente_elegido(soporte, "forma-vieja")
        datos = vieja.ok("GET", "/settings/")["data"] or {}
        datos["business"] = {**(datos.get("business") or {}), **EMISOR_COMPLETO}
        datos.pop("eInvoicing", None)
        datos["electronica"] = {"activa": True}
        vieja.ok("PUT", "/settings/", {"data": datos, "keep_logo": True})

        p = producto_de(vieja, "Configuración vieja", 1000, 5)
        hecha = vieja.ok("POST", "/sales/add_sale", venta(vieja, p))
        assert tipo_guardado(vieja, hecha["id_sale"]) == "04"


class TestLaExportacion:
    """RF-78, RN-87, T-727, contra el stack: al cliente del extranjero se le
    exporta, y lo que falte se dice **antes** de cobrar, con el producto."""

    TIPOS = ["01", "04", "03", "02", "09"]

    def test_al_extranjero_le_sale_exportacion_con_la_partida_en_la_linea(
        self, api: Api, producto, facturacion
    ):
        facturacion(True, tipos=self.TIPOS)
        p = exportable(api, producto("Café de exportación", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_extranjero(api)))
        detalle = api.ok("GET", f"/sales/sale/{hecha['id_sale']}")
        assert detalle["document_type"] == "09"
        assert detalle["items"][0]["tariff_heading"] == PARTIDA
        # Numerada en la serie 09 (RN-37): el tipo va en el consecutivo.
        assert detalle["einvoice"]["consecutive"][8:10] == "09"

    def test_el_tiquete_al_extranjero_sigue_pudiendose(self, api: Api, producto, facturacion):
        facturacion(True, tipos=self.TIPOS)
        p = exportable(api, producto("Café", 1000, 5))
        hecha = api.ok(
            "POST",
            "/sales/add_sale",
            venta(api, p, client_id=cliente_extranjero(api), document_type="04"),
        )
        detalle = api.ok("GET", f"/sales/sale/{hecha['id_sale']}")
        assert detalle["document_type"] == "04"
        assert detalle["items"][0]["tariff_heading"] is None

    def test_la_factura_al_extranjero_no(self, api: Api, producto, facturacion):
        facturacion(True, tipos=self.TIPOS)
        p = exportable(api, producto("Café", 1000, 5))
        respuesta = api.call(
            "POST",
            "/sales/add_sale",
            venta(api, p, client_id=cliente_extranjero(api), document_type="01"),
        )
        assert codigo(respuesta, 400) == "invoice_needs_resident"

    def test_una_mercancia_sin_partida_no_deja_cobrar_y_dice_cual(
        self, api: Api, producto, facturacion
    ):
        facturacion(True, tipos=self.TIPOS)
        con = exportable(api, producto("Con partida", 1000, 5))
        sin = exportable(api, producto("Sin partida", 1000, 5), partida=None)
        cuerpo = venta(api, con, client_id=cliente_extranjero(api))
        cuerpo["products"].append({"id_product": sin["id_product"], "stock": 1})
        cuerpo["subtotal"] = 2000.0
        cuerpo["tax"] = 260.0
        cuerpo["total"] = cuerpo["cash_received"] = 2260.0
        estado, respuesta = api.call("POST", "/sales/add_sale", cuerpo)
        assert codigo((estado, respuesta), 400) == "export_line_needs_tariff_heading"
        assert respuesta["detail"]["product_id"] == sin["id_product"]
        assert respuesta["detail"]["name"] == sin["name"]
        # Y no tocó el inventario de ninguno de los dos.
        assert api.ok("GET", f"/products/product/{con['barcode']}")["stock"] == 5
        assert api.ok("GET", f"/products/product/{sin['barcode']}")["stock"] == 5

    def test_la_tarifa_cero_con_credito_no_cabe_en_la_exportacion(
        self, api: Api, producto, facturacion
    ):
        facturacion(True, tipos=self.TIPOS)
        p = exportable(api, producto("Canasta básica", 1000, 5), tax_code="01")
        cuerpo = venta(api, p, client_id=cliente_extranjero(api))
        cuerpo["tax"] = 0.0
        cuerpo["total"] = cuerpo["cash_received"] = cuerpo["subtotal"]
        estado, respuesta = api.call("POST", "/sales/add_sale", cuerpo)
        assert codigo((estado, respuesta), 400) == "export_tariff_not_allowed"
        assert respuesta["detail"]["tax_code"] == "01"
        assert respuesta["detail"]["product_id"] == p["id_product"]

    def test_sin_direccion_extranjera_no_se_cobra(self, api: Api, producto, facturacion):
        facturacion(True, tipos=self.TIPOS)
        p = exportable(api, producto("Café", 1000, 5))
        cliente = cliente_extranjero(api, direccion=None)
        estado, respuesta = api.call("POST", "/sales/add_sale", venta(api, p, client_id=cliente))
        assert codigo((estado, respuesta), 400) == "export_needs_foreign_address"
        assert respuesta["detail"]["client_id"] == cliente

    def test_con_la_exportacion_apagada_el_extranjero_recibe_tiquete(
        self, api: Api, producto, facturacion
    ):
        facturacion(True)
        p = exportable(api, producto("Café", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_extranjero(api)))
        assert tipo_guardado(api, hecha["id_sale"]) == "04"

    def test_la_partida_se_valida_en_la_ficha_del_producto(self, api: Api, producto):
        p = producto("Partida mala", 1000, 5)
        respuesta = api.call(
            "PUT", f"/products/update_product/{p['id_product']}", {"tariff_heading": "0901"}
        )
        assert codigo(respuesta, 400) == "invalid_tariff_heading"
        exportable(api, p)
        assert api.ok("GET", f"/products/product/{p['barcode']}")["tariff_heading"] == PARTIDA
        # Y en blanco la quita, como el CABYS.
        api.ok("PUT", f"/products/update_product/{p['id_product']}", {"tariff_heading": ""})
        assert api.ok("GET", f"/products/product/{p['barcode']}")["tariff_heading"] is None

    def test_la_direccion_extranjera_tiene_el_largo_del_xml(self, api: Api):
        marca = marca_unica()
        respuesta = api.call(
            "POST",
            "/clients/register_client",
            {
                "identification": f"P{marca[-7:]}",
                "identification_type": "05",
                "name": "Foreign",
                "last_name": "Buyer",
                "second_name": "Inc",
                "email": f"largo{marca}@example.com",
                "foreign_address": "x" * 301,
            },
        )
        assert codigo(respuesta, 400) == "invalid_foreign_address"


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
