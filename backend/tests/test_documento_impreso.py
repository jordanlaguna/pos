"""
Lo que el comprobante impreso necesita del backend, contra el stack real (T-731).

Las plantillas del POS imprimen, por línea, el CABYS y la unidad con que se
vendió, y en el receptor el tipo de identificación del cliente (RN-86). Acá se
comprueba lo que solo se ve con MySQL: que la línea los **congele** —cambiar el
producto después no reescribe la venta—, que la nota de crédito los repita, y
que el cliente guarde su tipo, elegido o deducido de la cédula (T-617).
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo, marca_unica
from .test_tipo_de_comprobante import venta

pytestmark = pytest.mark.characterization


def clasificar(api: Api, producto: dict, *, cabys: str, unidad: str) -> None:
    api.ok(
        "PUT",
        f"/products/update_product/{producto['id_product']}",
        {"cabys_code": cabys, "unit_of_measure": unidad},
    )


def linea_de(api: Api, id_sale: int) -> dict:
    return api.ok("GET", f"/sales/sale/{id_sale}")["items"][0]


class TestLaLineaCongelaElCabys:
    def test_la_venta_guarda_el_cabys_y_la_unidad(self, api: Api, producto):
        p = producto("Arroz a granel", 1000, 5)
        clasificar(api, p, cabys="2316100000100", unidad="kg")

        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        linea = linea_de(api, hecha["id_sale"])

        assert linea["cabys_code"] == "2316100000100"
        assert linea["unit_of_measure"] == "kg"

    def test_cambiar_el_producto_despues_no_reescribe_la_venta(self, api: Api, producto):
        # Es la razón de congelarlo: la factura del mes pasado dice lo de entonces.
        p = producto("Reclasificado", 1000, 5)
        clasificar(api, p, cabys="2316100000100", unidad="kg")
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))

        clasificar(api, p, cabys="2399908000200", unidad="Unid")
        linea = linea_de(api, hecha["id_sale"])

        assert linea["cabys_code"] == "2316100000100"
        assert linea["unit_of_measure"] == "kg"

    def test_la_nota_de_credito_repite_los_de_la_venta(
        self, api: Api, producto, facturacion
    ):
        facturacion(True)
        p = producto("Devuelto con CABYS", 1000, 5)
        clasificar(api, p, cabys="2316100000100", unidad="kg")
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))

        devolucion = api.ok(
            "POST",
            "/returns/add_return",
            {
                "sale_id": hecha["id_sale"],
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "reason": "No era",
                "items": [{"id_product": p["id_product"], "quantity": 1}],
            },
        )
        nota = api.ok("GET", f"/returns/return/{devolucion['id_return']}")

        assert nota["items"][0]["cabys_code"] == "2316100000100"
        assert nota["items"][0]["unit_of_measure"] == "kg"


def cliente(**campos) -> dict:
    marca = marca_unica()
    return {
        "identification": f"1{marca[-8:]}",
        "name": "Receptor",
        "last_name": "Con Tipo",
        "second_name": "Prueba",
        "email": f"tipo{marca}@ejemplo.cr",
        "telephone": 22223333,
        "address": "San José",
        "register_date": "2026-01-01",
        **campos,
    }


def tipo_de(api: Api, id_client: int) -> str | None:
    return next(
        c for c in api.ok("GET", "/clients/clients_list") if c["id_client"] == id_client
    )["identification_type"]


class TestElTipoDeIdentificacionDelCliente:
    """T-617: el receptor imprime «Cédula física», y para eso el tipo se guarda."""

    def test_se_guarda_el_que_se_elige(self, api: Api):
        # Diez dígitos dirían jurídica; un NITE se elige y se respeta.
        hecho = api.ok(
            "POST",
            "/clients/register_client",
            cliente(identification=f"3{marca_unica()[-9:]}", identification_type="04"),
        )
        assert tipo_de(api, hecho["id_client"]) == "04"

    def test_sin_elegir_se_deduce_de_la_cedula(self, api: Api):
        hecho = api.ok("POST", "/clients/register_client", cliente())
        assert tipo_de(api, hecho["id_client"]) == "01"

    def test_uno_inventado_no_entra(self, api: Api):
        respuesta = api.call(
            "POST", "/clients/register_client", cliente(identification_type="07")
        )
        assert codigo(respuesta, 400) == "invalid_identification_type"

    def test_si_no_se_puede_saber_se_pide(self, api: Api):
        respuesta = api.call(
            "POST", "/clients/register_client", cliente(identification=f"X{marca_unica()}")
        )
        assert codigo(respuesta, 400) == "identification_type_required"

    def test_editar_lo_cambia_y_en_blanco_lo_deja(self, api: Api):
        hecho = api.ok("POST", "/clients/register_client", cliente())
        id_client = hecho["id_client"]

        api.ok("PUT", f"/clients/update_client/{id_client}", {"identification_type": "03"})
        assert tipo_de(api, id_client) == "03"

        api.ok("PUT", f"/clients/update_client/{id_client}", {"identification_type": ""})
        assert tipo_de(api, id_client) == "03"

    def test_editar_con_uno_inventado_no_entra(self, api: Api):
        hecho = api.ok("POST", "/clients/register_client", cliente())
        respuesta = api.call(
            "PUT",
            f"/clients/update_client/{hecho['id_client']}",
            {"identification_type": "07"},
        )
        assert codigo(respuesta, 400) == "invalid_identification_type"
