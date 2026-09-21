"""El código de tarifa del IVA contra la base de verdad (T-715, RF-65, RN-76).

Lo que se comprueba acá y no se puede comprobar sin base:

* que **el código manda sobre la tarifa**: guardar `04` deja el producto al 4 %
  aunque el formulario haya mandado otra cosa;
* que **se congela en la línea de la venta**, como la tarifa y por una razón
  más: del porcentaje no se vuelve al código;
* que los dos ceros con derechos opuestos —`01` y `11`— llegan distintos al otro
  lado, que es toda la razón de que exista la columna.
"""

from __future__ import annotations

import pytest

from .conftest import Api, marca_unica

pytestmark = pytest.mark.characterization


def clasificar(api: Api, producto_id: int, **campos) -> dict:
    api.ok("PUT", f"/products/update_product/{producto_id}", campos)
    return next(
        p
        for p in api.ok("GET", "/products/products_list")
        if p["id_product"] == producto_id
    )


class TestElCodigoMandaSobreLaTarifa:
    def test_guardar_un_codigo_fija_su_porcentaje(self, api: Api, producto):
        """El `04` es la tarifa reducida de los servicios de salud privados."""
        creado = producto("Consulta", 1000, 10)
        guardado = clasificar(api, creado["id_product"], tax_code="04")

        assert guardado["tax_code"] == "04"
        assert guardado["tax_rate"] == pytest.approx(0.04)

    def test_y_le_gana_a_la_tarifa_que_venga_en_el_mismo_guardado(self, api: Api, producto):
        """Dos datos del mismo hecho: uno tiene que mandar, y manda el código.

        Sin esta regla quedaría un producto que dice tarifa general y cobra 4 %,
        y el comprobante saldría con los dos datos peleados.
        """
        creado = producto("Consulta", 1000, 10)
        guardado = clasificar(api, creado["id_product"], tax_code="04", tax_rate=0.13)

        assert guardado["tax_rate"] == pytest.approx(0.04)

    def test_un_codigo_que_no_existe_se_rechaza(self, api: Api, producto):
        creado = producto("Consulta", 1000, 10)
        estado, cuerpo = api.call(
            "PUT", f"/products/update_product/{creado['id_product']}", {"tax_code": "12"}
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "invalid_tax_code"
        assert cuerpo["detail"]["tax_code"] == "12"

    def test_el_8_sin_cero_no_se_corrige(self, api: Api, producto):
        """Puede ser el `08` general o un dedazo, y adivinar es peor."""
        creado = producto("Arroz", 1000, 10)
        estado, cuerpo = api.call(
            "PUT", f"/products/update_product/{creado['id_product']}", {"tax_code": "8"}
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "invalid_tax_code"

    def test_se_puede_dejar_sin_clasificar(self, api: Api, producto):
        """Vaciarlo **no** toca la tarifa: sigue cobrando lo que cobraba."""
        creado = producto("Arroz", 1000, 10)
        clasificar(api, creado["id_product"], tax_code="08")
        vaciado = clasificar(api, creado["id_product"], tax_code="")

        assert vaciado["tax_code"] is None
        assert vaciado["tax_rate"] == pytest.approx(0.13)

    def test_nace_sin_clasificar(self, api: Api, producto):
        creado = producto("Arroz", 1000, 10)
        fila = next(
            p
            for p in api.ok("GET", "/products/products_list")
            if p["id_product"] == creado["id_product"]
        )
        assert fila["tax_code"] is None

    def test_se_puede_dar_de_alta_ya_clasificado(self, api: Api, categoria: int):
        marca = marca_unica()
        api.ok(
            "POST",
            "/products/add_product",
            {
                "name": f"Medicamento {marca}",
                "description": "producto de prueba",
                "price": 1000,
                "stock": 5,
                "barcode": f"T{marca}",
                "created_at": "2026-01-01T00:00:00",
                "category_id": categoria,
                "tax_code": "03",
            },
        )
        fila = api.ok("GET", f"/products/product/T{marca}")
        assert (fila["tax_code"], fila["tax_rate"]) == ("03", pytest.approx(0.02))


class TestLosDosCerosSonDistintos:
    """RN-76: el `01` da derecho a crédito pleno y el `11` no da ninguno.

    Los dos multiplican por cero, así que si solo se guardara el porcentaje
    serían indistinguibles al emitir el comprobante.
    """

    @pytest.mark.parametrize("codigo", ["01", "10", "11"])
    def test_los_tres_ceros_llegan_con_su_codigo(self, api: Api, producto, codigo):
        creado = producto("Cero", 1000, 10)
        guardado = clasificar(api, creado["id_product"], tax_code=codigo)

        assert guardado["tax_code"] == codigo
        assert guardado["tax_rate"] == pytest.approx(0.0)


class TestSeCongelaEnLaVenta:
    def test_la_linea_guarda_el_codigo_con_el_que_se_cobro(self, api: Api, producto):
        creado = producto("Medicamento", 1000, 10)
        clasificar(api, creado["id_product"], tax_code="03")

        venta = api.ok(
            "POST",
            "/sales/add_sale",
            {
                "sale_number": marca_unica(),
                "client_id": None,
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "subtotal": 1000.0,
                "tax": 20.0,
                "total": 1020.0,
                "payment_method": "Efectivo",
                "cash_received": 1020.0,
                "change_given": 0.0,
                "products": [{"id_product": creado["id_product"], "stock": 1}],
            },
        )
        linea = api.ok("GET", f"/sales/sale/{venta['id_sale']}")["items"][0]
        assert linea["tax_code"] == "03"
        assert linea["tax_rate"] == pytest.approx(0.02)

    def test_y_no_cambia_si_después_se_reclasifica_el_producto(self, api: Api, producto):
        """La misma regla que la tarifa (RN-12): lo cobrado no se reescribe."""
        creado = producto("Medicamento", 1000, 10)
        clasificar(api, creado["id_product"], tax_code="03")
        venta = api.ok(
            "POST",
            "/sales/add_sale",
            {
                "sale_number": marca_unica(),
                "client_id": None,
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "subtotal": 1000.0,
                "tax": 20.0,
                "total": 1020.0,
                "payment_method": "Efectivo",
                "cash_received": 1020.0,
                "change_given": 0.0,
                "products": [{"id_product": creado["id_product"], "stock": 1}],
            },
        )
        clasificar(api, creado["id_product"], tax_code="08")

        linea = api.ok("GET", f"/sales/sale/{venta['id_sale']}")["items"][0]
        assert linea["tax_code"] == "03"

    def test_un_producto_sin_clasificar_deja_la_linea_sin_codigo(self, api: Api, producto):
        """Y eso es lo cierto: nadie eligió, así que no hay nada que congelar."""
        creado = producto("Sin clasificar", 1000, 10)
        venta = api.ok(
            "POST",
            "/sales/add_sale",
            {
                "sale_number": marca_unica(),
                "client_id": None,
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "subtotal": 1000.0,
                "tax": 130.0,
                "total": 1130.0,
                "payment_method": "Efectivo",
                "cash_received": 1130.0,
                "change_given": 0.0,
                "products": [{"id_product": creado["id_product"], "stock": 1}],
            },
        )
        assert api.ok("GET", f"/sales/sale/{venta['id_sale']}")["items"][0]["tax_code"] is None


class TestLaAsignacionEnLote:
    def test_propone_el_codigo_cuando_la_tarifa_deja_uno_solo(self, api: Api, producto):
        """El CABYS trae la tarifa; el código sale de ella cuando no hay otro."""
        creado = producto("Harina de arroz", 1000, 10)
        api.ok(
            "PUT",
            "/products/assign_cabys",
            {
                "product_ids": [creado["id_product"]],
                "cabys_code": "2312000000300",
                "tax_rate": 0.13,
            },
        )
        fila = api.ok("GET", f"/products/product/{creado['barcode']}")
        assert fila["tax_code"] == "08"

    def test_y_no_lo_propone_en_el_cero(self, api: Api, producto):
        """Hay tres y la diferencia es el derecho a crédito de quien compra."""
        creado = producto("Libro infantil", 1000, 10)
        api.ok(
            "PUT",
            "/products/assign_cabys",
            {
                "product_ids": [creado["id_product"]],
                "cabys_code": "4761000000100",
                "tax_rate": 0.0,
            },
        )
        fila = api.ok("GET", f"/products/product/{creado['barcode']}")
        assert fila["tax_code"] is None
