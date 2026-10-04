"""
El consecutivo y la clave contra el stack real (T-704, T-705), y la puerta de
Configuración que no deja encender la facturación sin emisor (T-722).

Las reglas están probadas sin base en `tests/domain/test_fe_key.py` y
`tests/application/test_number_document.py`. Acá se comprueba lo que solo se ve
con MySQL: que el contador de `fe_sequences` se bloquee y avance de a uno, que
una venta que falla no consuma número —la transacción es la de la venta—, y que
la clave vuelva en el detalle con la cédula de `companies` y la fecha de hoy.

Toca la configuración de la compañía A y la deja como estaba al terminar.
"""

from __future__ import annotations

from datetime import date

import pytest

from .conftest import CEDULA_DE_A, EMISOR_COMPLETO, Api, codigo, marca_unica
from .test_nota_de_credito import devolver, leer, vender

pytestmark = pytest.mark.characterization


def comprobante(api: Api, venta: int) -> dict:
    detalle = api.ok("GET", f"/sales/sale/{venta}")
    assert detalle["einvoice"] is not None, "la venta con tipo tenía que salir numerada"
    return detalle["einvoice"]


def secuencia(consecutivo: str) -> int:
    return int(consecutivo[10:])


class TestLaVentaSaleNumerada:
    def test_el_tiquete_lleva_su_clave(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Numerado", 1000, 10)
        emitido = comprobante(api, vender(api, p, 1))

        clave, numero = emitido["clave"], emitido["consecutive"]
        assert len(clave) == 50 and clave.isdigit()
        assert clave[:3] == "506"
        assert clave[3:9] == date.today().strftime("%d%m%y")
        # La cédula de `companies` (RN-45), jurídica: dos ceros delante.
        assert clave[9:21] == CEDULA_DE_A.zfill(12)
        assert clave[21:41] == numero
        assert clave[41] == "1"
        # El consecutivo: la sucursal y la caja con las que nace toda compañía,
        # y el tipo del tiquete.
        assert numero[:8] == "00100001"
        assert numero[8:10] == "04"
        assert emitido["environment"] == "sandbox"
        assert emitido["situation"] == "1"

    def test_dos_tiquetes_seguidos_van_de_a_uno(self, api: Api, producto, facturacion):
        facturacion(True)
        p = producto("Seguidos", 1000, 10)
        primero = comprobante(api, vender(api, p, 1))
        segundo = comprobante(api, vender(api, p, 1))

        assert secuencia(segundo["consecutive"]) == secuencia(primero["consecutive"]) + 1
        assert primero["clave"] != segundo["clave"]

    def test_la_venta_que_falla_no_consume_numero(self, api: Api, producto, facturacion):
        # El defecto 1 del lado del contador: el número se toma en la misma
        # transacción que la venta, y la venta que no entra se lo lleva.
        facturacion(True)
        p = producto("Escaso numerado", 1000, 2)
        antes = comprobante(api, vender(api, p, 1))

        subtotal, impuesto = 5000.0, 650.0
        estado, cuerpo = api.call(
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
                "products": [{"id_product": p["id_product"], "stock": 5}],
            },
        )
        assert codigo((estado, cuerpo), 400) == "insufficient_stock"

        despues = comprobante(api, vender(api, p, 1))
        assert secuencia(despues["consecutive"]) == secuencia(antes["consecutive"]) + 1

    def test_sin_facturacion_no_hay_clave(self, api: Api, producto, facturacion):
        facturacion(False)
        p = producto("Sin clave", 1000, 10)
        assert api.ok("GET", f"/sales/sale/{vender(api, p, 1)}")["einvoice"] is None


class TestLaNotaDeCredito:
    def test_va_en_la_serie_03_y_referencia_la_clave_del_original(
        self, api: Api, producto, facturacion
    ):
        facturacion(True)
        p = producto("NC numerada", 1000, 10)
        venta = vender(api, p, 2)
        original = comprobante(api, venta)

        estado, cuerpo = devolver(api, venta, p, 1)
        assert estado == 200, cuerpo
        nota = leer(api, cuerpo["id_return"])

        assert nota["einvoice"]["consecutive"][8:10] == "03"
        assert nota["sale_clave"] == original["clave"]


class TestLaCedulaDelEmisor:
    def test_configuracion_la_muestra_de_companies(self, api: Api, facturacion):
        # `facturacion` la fija por soporte, que es la única puerta (RN-45).
        facturacion(False)
        emisor = api.ok("GET", "/settings/")["issuer"]
        assert emisor == {"identification": CEDULA_DE_A, "identification_type": "02"}

    def test_guardar_la_configuracion_no_la_cambia(self, api: Api, facturacion):
        # RF-37: esconder el campo no es control de acceso.
        facturacion(False)
        datos = api.ok("GET", "/settings/")["data"]
        datos["business"] = {**(datos.get("business") or {}), "taxId": "999999999"}
        api.ok("PUT", "/settings/", {"data": datos, "keep_logo": True})
        assert api.ok("GET", "/settings/")["issuer"]["identification"] == CEDULA_DE_A

    def test_soporte_la_guarda_sin_guiones(self, api: Api, soporte: Api):
        compania = soporte.ok(
            "PUT",
            f"/support/companies/{api.company_id}/issuer",  # type: ignore[attr-defined]
            {"identificacion": "3-101-234567"},
        )
        assert (compania["identificacion"], compania["identification_type"]) == (CEDULA_DE_A, "02")

    def test_una_que_no_cabe_en_la_clave_no_se_guarda(self, api: Api, soporte: Api):
        respuesta = soporte.call(
            "PUT",
            f"/support/companies/{api.company_id}/issuer",  # type: ignore[attr-defined]
            {"identificacion": "31012345678901"},
        )
        assert codigo(respuesta, 409) == "issuer_identification_required"
        assert respuesta[1]["detail"]["reason"] == "invalid"

    def test_la_compania_no_la_puede_cambiar_por_ahi(self, api: Api):
        respuesta = api.call(
            "PUT",
            f"/support/companies/{api.company_id}/issuer",  # type: ignore[attr-defined]
            {"identificacion": "3101999999"},
        )
        assert respuesta[0] == 403


class TestLaPuertaDeConfiguracion:
    """T-722: la facturación no se enciende sin el emisor completo."""

    def _guardar(self, api: Api, **negocio) -> tuple[int, object]:
        datos = api.ok("GET", "/settings/")["data"]
        datos["business"] = {**(datos.get("business") or {}), **negocio}
        datos["eInvoicing"] = {**(datos.get("eInvoicing") or {}), "enabled": True}
        return api.call("PUT", "/settings/", {"data": datos, "keep_logo": True})

    def test_sin_ubicacion_no_se_enciende(self, api: Api, facturacion):
        facturacion(False)
        respuesta = self._guardar(api, email=EMISOR_COMPLETO["email"], location=None)
        assert codigo(respuesta, 400) == "einvoicing_needs_issuer"
        assert respuesta[1]["detail"]["missing"] == ["location"]

    def test_dice_todo_lo_que_falta_de_una_vez(self, api: Api, facturacion):
        facturacion(False)
        respuesta = self._guardar(api, email="", location={})
        assert respuesta[1]["detail"]["missing"] == ["email", "location"]

    def test_un_distrito_que_no_es_de_ese_canton(self, api: Api, facturacion):
        facturacion(False)
        mala = {**EMISOR_COMPLETO["location"], "canton": "18"}  # Curridabat: cuatro distritos
        respuesta = self._guardar(api, email=EMISOR_COMPLETO["email"], location=mala)
        assert codigo(respuesta, 400) == "invalid_location"
        assert respuesta[1]["detail"]["field"] == "district"

    def test_con_todo_se_enciende(self, api: Api, facturacion):
        facturacion(False)
        estado, cuerpo = self._guardar(api, **EMISOR_COMPLETO)
        assert estado == 200, cuerpo
        assert cuerpo["data"]["business"]["location"]["district"] == "05"
