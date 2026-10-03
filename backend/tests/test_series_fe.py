"""El arranque de las series, contra el stack real (T-616, RF-32, RN-36 a RN-38).

La regla está probada sin base en `tests/domain/test_fe_key.py`
(`TestElArranqueDeUnaSerie`). Acá se ve lo que solo se ve con MySQL y HTTP: que
la serie se escriba donde la lee la numeración, que el cambio quede en
bitácora, que la caja de otra compañía no exista, y que una serie con la que el
sistema ya emitió no se mueva.

Las pruebas que escriben usan **una compañía propia**: moverle la serie a la
compañía A le cambiaría el consecutivo a `test_emision.py`. La de la serie ya
usada sí va sobre A, porque solo intenta y se le rechaza: no cambia nada.
"""

from __future__ import annotations

import pytest

from .conftest import PLAN_DE_PRUEBAS, Api, afiliado_unico, bootstrap, codigo, entrar, marca_unica

pytestmark = pytest.mark.characterization


@pytest.fixture(scope="module")
def propia(api: Api) -> Api:
    marca = marca_unica()
    correo = f"series.{marca}@pruebas.ventasys.cr"
    bootstrap(
        afiliado=afiliado_unico(),
        compania=1,
        nombre="Compañía de las series",
        email=correo,
        password="prueba123",
        rol="admin",
        nombre_persona="Serie",
        apellido="Arranque",
        **PLAN_DE_PRUEBAS,
    )
    cliente = Api(api.base)
    entrar(cliente, correo, "prueba123")
    return cliente


def serie(cliente: Api, tipo: str) -> dict:
    return next(s for s in cliente.ok("GET", "/fe/sequences")["items"] if s["document_type"] == tipo)


class TestElArranque:
    def test_cada_caja_por_cada_tipo_encendido(self, propia: Api):
        cuerpo = propia.ok("GET", "/fe/sequences")
        assert cuerpo["environment"] == "sandbox"
        factura = serie(propia, "01")
        assert (factura["branch_code"], factura["terminal_code"]) == ("001", "00001")
        assert (factura["last_number"], factura["in_use"]) == (0, False)

    def test_se_indica_el_ultimo_emitido_y_queda_en_bitacora(self, propia: Api, soporte: Api):
        caja = serie(propia, "01")["terminal_id"]
        hecho = propia.ok(
            "PUT", "/fe/sequences", {"terminal_id": caja, "document_type": "01", "last_number": 500209}
        )
        assert (hecho["last_number"], hecho["environment"]) == (500209, "sandbox")
        assert serie(propia, "01")["last_number"] == 500209

        lineas = soporte.ok("GET", "/support/audit?accion=serie_arranque&limite=10")["lineas"]
        assert any("01 001-00001 (sandbox): 0 → 500209" in (l["detalle"] or "") for l in lineas)

    def test_no_baja(self, propia: Api):
        caja = serie(propia, "01")["terminal_id"]
        respuesta = propia.call(
            "PUT", "/fe/sequences", {"terminal_id": caja, "document_type": "01", "last_number": 500100}
        )
        assert codigo(respuesta, 409) == "sequence_cannot_go_down"
        assert (respuesta[1]["detail"]["current"], respuesta[1]["detail"]["requested"]) == (500209, 500100)
        assert serie(propia, "01")["last_number"] == 500209

    def test_tiene_que_caber_en_la_clave(self, propia: Api):
        caja = serie(propia, "04")["terminal_id"]
        for malo in (-1, 10**10):
            respuesta = propia.call(
                "PUT", "/fe/sequences", {"terminal_id": caja, "document_type": "04", "last_number": malo}
            )
            assert codigo(respuesta, 400) == "invalid_sequence_start"

    def test_un_tipo_que_la_compania_no_emite(self, propia: Api):
        caja = serie(propia, "01")["terminal_id"]
        respuesta = propia.call(
            "PUT", "/fe/sequences", {"terminal_id": caja, "document_type": "09", "last_number": 10}
        )
        assert codigo(respuesta, 400) == "invalid_sale_document_type"

    def test_la_caja_de_otra_compania_no_existe(self, propia: Api, api: Api):
        ajena = serie(api, "01")["terminal_id"]
        respuesta = propia.call(
            "PUT", "/fe/sequences", {"terminal_id": ajena, "document_type": "01", "last_number": 10}
        )
        assert codigo(respuesta, 404) == "terminal_not_found"

    def test_un_cajero_no_lo_toca(self, cajero: Api):
        estado, cuerpo = cajero.call(
            "PUT", "/fe/sequences", {"terminal_id": 1, "document_type": "01", "last_number": 10}
        )
        assert estado == 403
        assert cuerpo["detail"]["code"] == "admin_only"


def test_una_serie_que_el_sistema_ya_uso_es_suya(api: Api, producto, facturacion):
    """RN-38: desde que el sistema emitió, el contador no se mueve a mano. Sobre
    la compañía A, porque solo se intenta: el rechazo no cambia nada."""
    facturacion(True, tipos=["04", "01"])
    p = producto("Serie usada", 1000, 5)
    subtotal, impuesto = 1000.0, 130.0
    api.ok(
        "POST",
        "/sales/add_sale",
        {
            "sale_number": marca_unica(),
            "client_id": None,
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "subtotal": subtotal,
            "tax": impuesto,
            "total": subtotal + impuesto,
            "payment_method": "Efectivo",
            "cash_received": subtotal + impuesto,
            "change_given": 0.0,
            "products": [{"id_product": p["id_product"], "stock": 1}],
            "document_type": "04",
        },
    )
    tiquete = serie(api, "04")
    assert tiquete["in_use"] is True
    respuesta = api.call(
        "PUT",
        "/fe/sequences",
        {"terminal_id": tiquete["terminal_id"], "document_type": "04", "last_number": tiquete["last_number"] + 1000},
    )
    assert codigo(respuesta, 409) == "sequence_in_use"
    assert serie(api, "04")["last_number"] == tiquete["last_number"]
