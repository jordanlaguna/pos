"""Clasificar productos: uno a uno y en lote (T-505, T-506).

Son tres reglas, y las tres tienen que ver con la misma columna:

1. **`tax_rate` en nulo es un valor**, no una omisión. Significa «la tasa
   configurada del negocio», y un producto clasificado tiene que poder volver
   a heredarla. Sin eso, clasificar sería una puerta de una sola dirección.
2. **El lote es todo o nada.** Medio catálogo clasificado es el desorden que
   RF-20 existe para arreglar.
3. **Los identificadores del cuerpo no son menos ajenos que los de la ruta.**
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo

pytestmark = pytest.mark.characterization

#: Códigos reales del catálogo, con sus tarifas. Sirven de documentación: son
#: la razón por la que el impuesto no puede ser un número del negocio.
JARABE = ("3521000000100", 0.02)
HARINA_DE_ARROZ = ("2312000000300", 0.13)


class TestLaTarifaDeUnProducto:
    def test_nace_en_nulo_y_eso_significa_la_configurada(self, api: Api, producto):
        """Un producto que nadie clasificó no tiene tarifa propia.

        No es lo mismo que tener 0: eso sería una exoneración de verdad.
        """
        creado = producto("Sin clasificar", 1000, 10)
        assert creado["tax_rate"] is None
        assert creado["cabys_code"] is None

    def test_se_le_pone_una_y_se_le_puede_quitar(self, api: Api, producto):
        """La ida y **la vuelta**.

        La vuelta es la que se rompía: el bucle de `update_product_information`
        saltaba los nulos —correcto para un PUT parcial, que así no borra lo que
        no se mandó— y por eso un `tax_rate: null` no llegaba nunca a la base.
        """
        creado = producto("Jarabe", 1000, 10)
        pid = creado["id_product"]
        codigo_cabys, tarifa = JARABE

        api.ok("PUT", f"/products/update_product/{pid}", {"cabys_code": codigo_cabys, "tax_rate": tarifa})
        puesto = api.ok("GET", f"/products/product/{creado['barcode']}")
        assert puesto["tax_rate"] == pytest.approx(tarifa)
        assert puesto["cabys_code"] == codigo_cabys

        api.ok("PUT", f"/products/update_product/{pid}", {"cabys_code": None, "tax_rate": None})
        vaciado = api.ok("GET", f"/products/product/{creado['barcode']}")
        assert vaciado["tax_rate"] is None, "no se pudo volver a heredar la tasa configurada"
        assert vaciado["cabys_code"] is None

    def test_un_campo_que_no_se_manda_sigue_intacto(self, api: Api, producto):
        """La contraprueba de la anterior, y la razón de que la lista de columnas
        vaciables sea corta: un PUT parcial no puede borrar lo que no nombró."""
        creado = producto("Parcial", 1000, 10)
        pid = creado["id_product"]
        api.ok("PUT", f"/products/update_product/{pid}", {"tax_rate": 0.02})

        api.ok("PUT", f"/products/update_product/{pid}", {"price": 1500})
        despues = api.ok("GET", f"/products/product/{creado['barcode']}")
        assert despues["price"] == pytest.approx(1500)
        assert despues["tax_rate"] == pytest.approx(0.02), "un cambio de precio le borró la tarifa"
        assert despues["name"] == creado["name"]


class TestElLoteDeCabys:
    def test_clasifica_varios_de_una_vez(self, api: Api, producto):
        codigo_cabys, tarifa = HARINA_DE_ARROZ
        uno = producto("Harina A", 1000, 5)
        dos = producto("Harina B", 2000, 5)

        respuesta = api.ok(
            "PUT",
            "/products/assign_cabys",
            {
                "product_ids": [uno["id_product"], dos["id_product"]],
                "cabys_code": codigo_cabys,
                "tax_rate": tarifa,
            },
        )
        assert respuesta == {"message": "cabys_assigned", "updated": 2}

        for creado in (uno, dos):
            despues = api.ok("GET", f"/products/product/{creado['barcode']}")
            assert despues["cabys_code"] == codigo_cabys
            assert despues["tax_rate"] == pytest.approx(tarifa)

    def test_el_mismo_id_repetido_cuenta_una_vez(self, api: Api, producto):
        uno = producto("Repetido", 1000, 5)
        pid = uno["id_product"]
        respuesta = api.ok(
            "PUT",
            "/products/assign_cabys",
            {"product_ids": [pid, pid, pid], "cabys_code": JARABE[0], "tax_rate": JARABE[1]},
        )
        assert respuesta["updated"] == 1

    def test_sin_productos_no_hace_nada(self, api: Api):
        respuesta = api.ok(
            "PUT",
            "/products/assign_cabys",
            {"product_ids": [], "cabys_code": JARABE[0], "tax_rate": JARABE[1]},
        )
        assert respuesta["updated"] == 0

    def test_un_id_que_no_existe_no_aplica_ninguno(self, api: Api, producto):
        """Todo o nada. Si se aplicara «los que sí», quien lo pidió no tendría
        cómo saber qué mitad quedó hecha."""
        uno = producto("Con vecino fantasma", 1000, 5)
        respuesta = api.call(
            "PUT",
            "/products/assign_cabys",
            {
                "product_ids": [uno["id_product"], 999_999_999],
                "cabys_code": JARABE[0],
                "tax_rate": JARABE[1],
            },
        )
        assert codigo(respuesta, 404) == "product_not_found"

        intacto = api.ok("GET", f"/products/product/{uno['barcode']}")
        assert intacto["cabys_code"] is None, "se aplicó media asignación"

    @pytest.mark.parametrize(
        "malo, razon",
        [
            pytest.param("352100000010", "bad_length", id="doce dígitos"),
            pytest.param("35210000001A", "not_digits", id="con letra"),
            pytest.param("  ", "empty", id="en blanco"),
        ],
    )
    def test_valida_el_codigo_con_el_mismo_dominio(self, api: Api, producto, malo, razon):
        uno = producto("Código malo", 1000, 5)
        respuesta = api.call(
            "PUT",
            "/products/assign_cabys",
            {"product_ids": [uno["id_product"]], "cabys_code": malo, "tax_rate": 0.13},
        )
        assert codigo(respuesta, 400) == "cabys_invalid_code"
        assert respuesta[1]["detail"]["reason"] == razon

    @pytest.mark.parametrize("fuera", [13, -0.01, 1.5])
    def test_una_tarifa_fuera_de_rango_no_entra(self, api: Api, producto, fuera):
        """`13` en vez de `0.13` multiplica la factura por catorce, y en un lote
        lo haría en cien productos a la vez."""
        uno = producto("Tarifa mala", 1000, 5)
        respuesta = api.call(
            "PUT",
            "/products/assign_cabys",
            {"product_ids": [uno["id_product"]], "cabys_code": JARABE[0], "tax_rate": fuera},
        )
        assert codigo(respuesta, 400) == "tax_rate_out_of_range"

    def test_el_cajero_no_clasifica(self, api: Api, cajero: Api, producto):
        """Escribir el catálogo es de administrador, como el resto de la ficha."""
        uno = producto("De admin", 1000, 5)
        respuesta = cajero.call(
            "PUT",
            "/products/assign_cabys",
            {"product_ids": [uno["id_product"]], "cabys_code": JARABE[0], "tax_rate": JARABE[1]},
        )
        assert codigo(respuesta, 403) == "admin_only"
