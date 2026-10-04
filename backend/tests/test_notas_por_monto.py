"""
Las notas por monto, contra el stack real (RF-77, T-726).

Las reglas están probadas sin base en `tests/domain/test_fe_notes.py` y
`tests/application/test_register_note.py`. Acá se comprueba lo que solo se ve
con MySQL y HTTP: que las dos tablas existan y se llenen con lo congelado de la
venta, que la plata aparezca en el arqueo del turno y en las ventas netas, que
solo el administrador las emita, y que una nota de otra compañía no se vea.

Toca la configuración de la compañía A y la deja como estaba al terminar.
"""

from __future__ import annotations

import pytest

from .conftest import Api, cerrar_caja_abierta, codigo
from .test_tipo_de_comprobante import venta

pytestmark = pytest.mark.characterization


def nota(api: Api, id_sale: int, tipo: str, lineas, **cambios) -> tuple[int, object]:
    cuerpo = {
        "sale_id": id_sale,
        "document_type": tipo,
        "reference_code": "02",
        "reason": "se cobró mal el precio",
        "items": [{"id_product": p, "amount": m} for p, m in lineas],
        "payment_method": "Efectivo" if tipo == "02" else None,
    }
    cuerpo.update(cambios)
    return api.call("POST", "/notes/add_note", cuerpo)


@pytest.fixture
def comprobante(api: Api, producto, facturacion):
    """Una venta con tiquete: dos unidades a ₡1 000 al 13 %, ₡2 260 con impuesto."""
    facturacion(True)
    p = producto("Con nota", 1000, 10)
    api.ok(
        "PUT",
        f"/products/update_product/{p['id_product']}",
        {"cabys_code": "2316100000100", "unit_of_measure": "kg"},
    )
    cuerpo = venta(api, p, subtotal=2000.0, tax=260.0, total=2260.0, cash_received=2260.0)
    cuerpo["products"] = [{"id_product": p["id_product"], "stock": 2}]
    hecha = api.ok("POST", "/sales/add_sale", cuerpo)
    return hecha["id_sale"], p


class TestLaNota:
    def test_la_nd_queda_con_su_motivo_su_monto_y_lo_de_la_venta(self, api: Api, comprobante):
        id_sale, p = comprobante
        estado, cuerpo = nota(api, id_sale, "02", [(p["id_product"], 1130)])
        assert estado == 200, cuerpo
        assert (cuerpo["document_type"], cuerpo["total"]) == ("02", 1130.0)

        leida = api.ok("GET", f"/notes/note/{cuerpo['id_note']}")
        assert (leida["reference_code"], leida["payment_method"]) == ("02", "Efectivo")
        assert (leida["subtotal"], leida["tax"], leida["total"]) == (1000.0, 130.0, 1130.0)
        # Lo que la nota impresa dice del original (RN-89)…
        assert leida["sale_id"] == id_sale
        assert leida["sale_document_type"] == "04"
        # …y la línea con lo congelado en la venta (RN-86).
        [linea] = leida["items"]
        assert (linea["tax_rate"], linea["cabys_code"], linea["unit_of_measure"]) == (
            0.13,
            "2316100000100",
            "kg",
        )

        de_la_venta = api.ok("GET", f"/notes/by_sale/{id_sale}")
        assert [n["id"] for n in de_la_venta] == [cuerpo["id_note"]]

    def test_la_nc_sale_de_la_gaveta_y_no_lleva_medio(self, api: Api, comprobante):
        id_sale, p = comprobante
        estado, cuerpo = nota(api, id_sale, "03", [(p["id_product"], 565)])
        assert estado == 200, cuerpo
        assert api.ok("GET", f"/notes/note/{cuerpo['id_note']}")["payment_method"] is None

    def test_una_nc_que_pasa_de_lo_que_queda_no_entra(self, api: Api, comprobante):
        id_sale, p = comprobante
        estado, cuerpo = nota(api, id_sale, "03", [(p["id_product"], 2261)])
        assert codigo((estado, cuerpo), 400) == "credit_exceeds_line"
        assert cuerpo["detail"]["available"] == 2260.0

    def test_sobre_una_venta_sin_comprobante_no_hay_nota(self, api: Api, producto, facturacion):
        facturacion(False)
        p = producto("Sin comprobante", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        respuesta = nota(api, hecha["id_sale"], "03", [(p["id_product"], 100)])
        assert codigo(respuesta, 400) == "note_needs_document"

    def test_un_motivo_que_un_mostrador_no_emite(self, api: Api, comprobante):
        id_sale, p = comprobante
        respuesta = nota(api, id_sale, "03", [(p["id_product"], 100)], reference_code="09")
        assert codigo(respuesta, 400) == "invalid_note_reason"

    def test_la_nd_apagada_no_se_emite(self, api: Api, comprobante, facturacion):
        id_sale, p = comprobante
        facturacion(True, tipos=["04", "01", "03"])
        respuesta = nota(api, id_sale, "02", [(p["id_product"], 100)])
        assert codigo(respuesta, 400) == "document_type_not_enabled"

    def test_el_cajero_no_las_emite(self, cajero: Api, comprobante):
        id_sale, p = comprobante
        assert codigo(nota(cajero, id_sale, "03", [(p["id_product"], 100)]), 403) == "admin_only"


class TestLoQueUnaNotaCambia:
    def test_la_linea_con_nc_ya_no_se_devuelve_y_la_venta_no_se_anula(
        self, api: Api, comprobante
    ):
        id_sale, p = comprobante
        assert nota(api, id_sale, "03", [(p["id_product"], 100)])[0] == 200

        devolver = {
            "sale_id": id_sale,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "reason": "no era",
            "items": [{"id_product": p["id_product"], "quantity": 1}],
        }
        assert codigo(api.call("POST", "/returns/add_return", devolver), 409) == (
            "return_after_credit_note"
        )
        anular = dict(devolver, items=[{"id_product": p["id_product"], "quantity": 2}], annul=True)
        assert codigo(api.call("POST", "/returns/add_return", anular), 409) == "annul_after_note"

    def test_el_arqueo_suma_la_nd_en_efectivo_y_resta_la_nc(self, api: Api, comprobante):
        id_sale, p = comprobante
        cerrar_caja_abierta(api)
        api.ok("POST", "/cash/open", {"user_id": api.user_id, "opening_amount": 10000})  # type: ignore[attr-defined]
        try:
            antes = api.ok("GET", "/cash/current")
            assert nota(api, id_sale, "02", [(p["id_product"], 1130)])[0] == 200
            assert nota(api, id_sale, "03", [(p["id_product"], 565)])[0] == 200
            despues = api.ok("GET", "/cash/current")
        finally:
            cerrar_caja_abierta(api)

        assert despues["expected_amount"] == pytest.approx(antes["expected_amount"] + 1130 - 565)
        assert despues["debit_notes_cash"] - antes["debit_notes_cash"] == pytest.approx(1130)
        assert despues["credit_notes_total"] - antes["credit_notes_total"] == pytest.approx(565)

    def test_las_ventas_netas_las_cuentan(self, api: Api, comprobante):
        id_sale, p = comprobante
        antes = api.ok("GET", "/reports/summary")
        assert nota(api, id_sale, "02", [(p["id_product"], 226)])[0] == 200
        assert nota(api, id_sale, "03", [(p["id_product"], 113)])[0] == 200
        despues = api.ok("GET", "/reports/summary")

        assert despues["debit_notes_total"] - antes["debit_notes_total"] == pytest.approx(226)
        assert despues["credit_notes_total"] - antes["credit_notes_total"] == pytest.approx(113)
        assert despues["net_total"] - antes["net_total"] == pytest.approx(226 - 113)


class TestLaOtraCompania:
    def test_no_ve_la_nota_ni_la_emite_sobre_la_venta_ajena(
        self, api: Api, api_b: Api, comprobante
    ):
        id_sale, p = comprobante
        _, cuerpo = nota(api, id_sale, "02", [(p["id_product"], 113)])

        assert codigo(api_b.call("GET", f"/notes/note/{cuerpo['id_note']}"), 404) == (
            "note_not_found"
        )
        assert api_b.ok("GET", f"/notes/by_sale/{id_sale}") == []
        assert codigo(nota(api_b, id_sale, "02", [(p["id_product"], 113)]), 404) == (
            "sale_not_found"
        )
