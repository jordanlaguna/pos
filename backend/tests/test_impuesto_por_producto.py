"""El caso de aceptación de F5, contra la base de verdad (T-511).

Es el ejemplo que traen el spec y el plan, con una tercera línea al 0 % porque
las tres tarifas de Costa Rica juntas son lo que rompía el promedio:

    medicamento ₡1 000 al  2 %  →  impuesto ₡ 20
    arroz       ₡1 000 al 13 %  →  impuesto ₡130
    libro       ₡1 000 al  0 %  →  impuesto ₡  0
    ------------------------------------------------
    subtotal ₡3 000 · impuesto ₡150 · total ₡3 150

Devolver **solo el medicamento** tiene que reembolsar ₡1 020. Con la tasa del
encabezado —₡150 / ₡3 000 = 5 %— saldrían ₡1 050: treinta colones que el negocio
regala, y setenta que le quita al cliente si lo que devuelve es el arroz. Con
tres tarifas el promedio no se acerca a ninguna.

Lo que se comprueba acá y no se puede comprobar sin base:

* que la tarifa **quede escrita en la línea** y sobreviva a un cambio del
  catálogo (RN-12);
* que las líneas **sumen exactamente** el impuesto del encabezado, que es lo que
  valida Hacienda;
* que las devoluciones parciales sumen la venta entera, ni un céntimo más ni uno
  menos, sin importar en qué orden se devuelva.
"""

from __future__ import annotations

import pytest

from .conftest import Api, marca_unica

pytestmark = pytest.mark.characterization

#: Códigos reales del catálogo, con su tarifa. Son la razón de toda la fase.
JARABE = ("3521000000100", 0.02)
HARINA_DE_ARROZ = ("2312000000300", 0.13)
LIBRO_INFANTIL = ("4761000000100", 0.0)


@pytest.fixture
def canasta(api: Api, producto) -> dict:
    """Tres productos de ₡1 000 con las tres tarifas del país."""
    hechos = {}
    for nombre, (codigo, tarifa) in (
        ("medicamento", JARABE),
        ("arroz", HARINA_DE_ARROZ),
        ("libro", LIBRO_INFANTIL),
    ):
        creado = producto(nombre.capitalize(), 1000, 10)
        api.ok(
            "PUT",
            f"/products/update_product/{creado['id_product']}",
            {"cabys_code": codigo, "tax_rate": tarifa},
        )
        hechos[nombre] = api.ok("GET", f"/products/product/{creado['barcode']}")
    return hechos


def vender(api: Api, lineas: list[tuple[dict, int]]):
    """Cobra, calculando los totales línea por línea como los calcula el POS."""
    subtotal = round(sum(p["price"] * cant for p, cant in lineas), 2)
    impuesto = round(
        sum(round(p["price"] * cant * (p["tax_rate"] or 0), 2) for p, cant in lineas), 2
    )
    total = round(subtotal + impuesto, 2)

    return api.ok(
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
            "products": [{"id_product": p["id_product"], "stock": c} for p, c in lineas],
        },
    )


def devolver(api: Api, venta_id: int, lineas: list[tuple[dict, int]]):
    return api.ok(
        "POST",
        "/returns/add_return",
        {
            "sale_id": venta_id,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "reason": "prueba de aceptación de F5",
            "items": [{"id_product": p["id_product"], "quantity": c} for p, c in lineas],
        },
    )


class TestLaVentaConTresTarifas:
    def test_los_totales_son_los_del_spec(self, api: Api, canasta):
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])

        guardada = api.ok("GET", f"/sales/sale/{venta['id_sale']}")
        assert guardada["subtotal"] == 3000.0
        assert guardada["tax"] == 150.0
        assert guardada["total"] == 3150.0

    def test_cada_linea_guarda_SU_tarifa_y_SU_impuesto(self, api: Api, canasta):
        """RN-12: la tarifa se congela al cobrar. Sin esto, devolver algo vendido
        el mes pasado usaría la tarifa de hoy."""
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])
        por_producto = {
            d["id_product"]: d for d in api.ok("GET", f"/sales/sale/{venta['id_sale']}")["items"]
        }
        esperado = {
            canasta["medicamento"]["id_product"]: (0.02, 20.0),
            canasta["arroz"]["id_product"]: (0.13, 130.0),
            canasta["libro"]["id_product"]: (0.0, 0.0),
        }
        for pid, (tarifa, impuesto) in esperado.items():
            assert por_producto[pid]["tax_rate"] == pytest.approx(tarifa)
            assert por_producto[pid]["tax_amount"] == pytest.approx(impuesto)

    def test_las_lineas_suman_exactamente_el_impuesto_del_encabezado(self, api: Api, canasta):
        """Es la igualdad que valida Hacienda: si no cuadra, la factura no cuadra
        consigo misma. Es también la razón de que el redondeo vaya por línea."""
        venta = vender(api, [(canasta[n], 2) for n in ("medicamento", "arroz", "libro")])

        guardada = api.ok("GET", f"/sales/sale/{venta['id_sale']}")
        assert round(sum(i["tax_amount"] for i in guardada["items"]), 2) == guardada["tax"]


class TestLaDevolucionParcial:
    def test_devolver_solo_el_medicamento_reembolsa_1020(self, api: Api, canasta):
        """El número del spec. Con el promedio del encabezado saldrían ₡1 050."""
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])

        devolucion = devolver(api, venta["id_sale"], [(canasta["medicamento"], 1)])
        assert devolucion["total"] == 1020.0

    def test_devolver_solo_el_arroz_reembolsa_1130(self, api: Api, canasta):
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])

        devolucion = devolver(api, venta["id_sale"], [(canasta["arroz"], 1)])
        assert devolucion["total"] == 1130.0

    def test_devolver_solo_el_libro_reembolsa_1000_sin_un_centimo_de_impuesto(
        self, api: Api, canasta
    ):
        """El 0 % es una tarifa, no una ausencia: se reembolsa el precio y nada
        más. Con el promedio se devolvería impuesto que nunca se cobró."""
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])

        devolucion = devolver(api, venta["id_sale"], [(canasta["libro"], 1)])
        assert devolucion["total"] == 1000.0

    def test_las_tres_parciales_suman_la_venta_entera(self, api: Api, canasta):
        """Lo que impide que el negocio gane o pierda según el orden en que se
        devuelva. Es la propiedad, no un número más."""
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz", "libro")])

        reembolsado = sum(
            devolver(api, venta["id_sale"], [(canasta[n], 1)])["total"]
            for n in ("medicamento", "arroz", "libro")
        )
        assert round(reembolsado, 2) == 3150.0

    def test_la_devolucion_guarda_su_propio_desglose(self, api: Api, canasta):
        """`returns` dejó de guardar solo el total en la 006: con tarifas
        mezcladas el impuesto no se puede deducir del total (T-509b)."""
        venta = vender(api, [(canasta[n], 1) for n in ("medicamento", "arroz")])

        devolucion = devolver(api, venta["id_sale"], [(canasta["medicamento"], 1)])
        guardada = api.ok("GET", f"/returns/return/{devolucion['id_return']}")
        assert guardada["subtotal"] == 1000.0
        assert guardada["tax"] == 20.0
        assert guardada["total"] == 1020.0


class TestElCatalogoPuedeCambiarDespues:
    def test_reclasificar_el_producto_no_mueve_lo_ya_vendido(self, api: Api, canasta):
        """RN-12 con todas sus letras.

        Hacienda actualiza el catálogo y el dueño corrige códigos; lo que ya se
        cobró no se puede mover, porque la factura está impresa.
        """
        venta = vender(api, [(canasta["medicamento"], 1)])
        antes = api.ok("GET", f"/sales/sale/{venta['id_sale']}")

        # El medicamento pasa a ser arroz: mismo producto, tarifa nueva.
        api.ok(
            "PUT",
            f"/products/update_product/{canasta['medicamento']['id_product']}",
            {"cabys_code": HARINA_DE_ARROZ[0], "tax_rate": HARINA_DE_ARROZ[1]},
        )

        despues = api.ok("GET", f"/sales/sale/{venta['id_sale']}")
        assert despues["tax"] == antes["tax"] == 20.0

        devolucion = devolver(api, venta["id_sale"], [(canasta["medicamento"], 1)])
        assert devolucion["total"] == 1020.0, "la devolución usó la tarifa de hoy"

    def test_un_producto_sin_clasificar_cobra_la_tasa_configurada(self, api: Api, producto):
        """RN-9: en nulo significa «la configurada», que es lo que aplica
        mientras nadie lo clasifique. No es lo mismo que 0."""
        suelto = producto("Sin clasificar", 1000, 5)
        assert suelto["tax_rate"] is None

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
                "products": [{"id_product": suelto["id_product"], "stock": 1}],
            },
        )
        guardada = api.ok("GET", f"/sales/sale/{venta['id_sale']}")
        assert guardada["tax"] == 130.0
        assert guardada["items"][0]["tax_rate"] == pytest.approx(0.13), (
            "la línea tiene que guardar la tarifa RESUELTA, no un nulo: si no, "
            "una devolución posterior dependería de la configuración de ese día"
        )
