"""
Salidas con motivo, de punta a punta (F15, T-1502, RN-99).

Contra la pila de verdad: el catálogo de motivos con el que nace la compañía,
la salida que baja la existencia al promedio del momento y deja su fila en el
kárdex, la anulación que repone al costo de la salida, y —con contabilidad
activa— el asiento que saca el costo del inventario y lo lleva al gasto.
"""

from __future__ import annotations

from datetime import date

from .conftest import Api, codigo, marca_unica
from .test_contabilidad import activar, compania_propia, cuenta_por_codigo
from .test_inventario import cuadra, entrar, kardex

LOS_SEIS = {"shrinkage", "damage", "expired", "internal_use", "sample", "count"}


def motivos(api: Api) -> list[dict]:
    return api.ok("GET", "/inventory/reasons")


def motivo(api: Api, code: str) -> dict:
    return next(m for m in motivos(api) if m["code"] == code)


def nuevo_motivo(api: Api, nombre: str = "Rotura") -> dict:
    return api.ok(
        "POST", "/inventory/reasons", {"code": f"m_{marca_unica()}", "name": nombre}
    )


def dar_salida(api: Api, producto: dict, cantidad: int, motivo_id: int, **cambios):
    cuerpo = {
        "reason_id": motivo_id,
        "notes": "prueba",
        "lines": [{"id_product": producto["id_product"], "quantity": cantidad}],
    }
    cuerpo.update(cambios)
    return api.call("POST", "/inventory/exits", cuerpo)


def salida_listada(api: Api, id_exit: int) -> dict:
    return next(s for s in api.ok("GET", "/inventory/exits") if s["id"] == id_exit)


class TestLosMotivos:
    def test_toda_compania_nace_con_los_seis(self, api: Api):
        por_codigo = {m["code"]: m for m in motivos(api)}
        assert LOS_SEIS <= set(por_codigo)
        assert por_codigo["count"]["is_system"] is True
        assert all(not por_codigo[c]["is_system"] for c in LOS_SEIS - {"count"})
        assert all(por_codigo[c]["is_active"] for c in LOS_SEIS)

    def test_se_agrega_se_renombra_y_se_apaga(self, api: Api):
        creado = nuevo_motivo(api)
        assert creado["is_system"] is False and creado["is_active"] is True

        renombrado = api.ok("PUT", f"/inventory/reasons/{creado['id']}", {"name": "Rotura en bodega"})
        assert renombrado["name"] == "Rotura en bodega"

        apagado = api.ok("PUT", f"/inventory/reasons/{creado['id']}", {"is_active": False})
        assert apagado["is_active"] is False
        # Sigue en la lista: las salidas viejas lo nombran.
        assert next(m for m in motivos(api) if m["id"] == creado["id"])["is_active"] is False

    def test_un_codigo_repetido_no_entra(self, api: Api):
        creado = nuevo_motivo(api)
        respuesta = api.call("POST", "/inventory/reasons", {"code": creado["code"], "name": "Otro"})
        assert codigo(respuesta, 400) == "reason_code_taken"
        assert respuesta[1]["detail"]["reason_code"] == creado["code"]

    def test_el_de_la_toma_no_se_apaga(self, api: Api):
        toma = motivo(api, "count")
        respuesta = api.call("PUT", f"/inventory/reasons/{toma['id']}", {"is_active": False})
        assert codigo(respuesta, 400) == "reason_is_system"
        assert motivo(api, "count")["is_active"] is True

    def test_uno_que_no_existe(self, api: Api):
        assert codigo(api.call("PUT", "/inventory/reasons/999999999", {"name": "x"}), 404) == (
            "reason_not_found"
        )


class TestUnaSalida:
    def test_baja_la_existencia_al_promedio_y_deja_su_fila(self, api: Api, producto):
        p = producto("Merma", 1000, 0)
        entrar(api, p, 10, 900)

        estado, hecha = dar_salida(api, p, 3, motivo(api, "shrinkage")["id"])
        assert estado == 200, hecha
        assert hecha["units"] == 3 and hecha["total_cost"] == 2700
        assert cuadra(api, p) == 7

        [fila, *_] = kardex(api, p)
        assert fila["kind"] == "exit"
        assert (fila["before_qty"], fila["quantity"], fila["after_qty"]) == (10, -3, 7)
        assert fila["unit_cost"] == 900 and fila["avg_cost_after"] == 900
        assert (fila["source_type"], fila["source_id"], fila["source_line"]) == (
            "stock_exit", hecha["id_exit"], 1,
        )

        listada = salida_listada(api, hecha["id_exit"])
        assert listada["status"] == "applied"
        assert listada["reason_code"] == "shrinkage"
        assert listada["items_count"] == 3 and listada["total_cost"] == 2700
        assert listada["lines"][0]["subtotal"] == 2700 and listada["lines"][0]["name"] == p["name"]

    def test_un_producto_sin_costo_sale_sin_plata(self, api: Api, producto):
        p = producto("Sin costo", 1000, 5)
        estado, hecha = dar_salida(api, p, 2, motivo(api, "damage")["id"])
        assert estado == 200, hecha
        assert hecha["total_cost"] == 0
        assert cuadra(api, p) == 3

    def test_un_motivo_apagado_no_sirve(self, api: Api, producto):
        p = producto("Apagado", 1000, 5)
        creado = nuevo_motivo(api)
        api.ok("PUT", f"/inventory/reasons/{creado['id']}", {"is_active": False})
        assert codigo(dar_salida(api, p, 1, creado["id"]), 400) == "reason_inactive"
        assert cuadra(api, p) == 5

    def test_el_motivo_de_la_toma_no_se_elige(self, api: Api, producto):
        p = producto("Toma", 1000, 5)
        assert codigo(dar_salida(api, p, 1, motivo(api, "count")["id"]), 400) == "reason_is_system"

    def test_un_motivo_que_no_existe(self, api: Api, producto):
        p = producto("Sin motivo", 1000, 5)
        assert codigo(dar_salida(api, p, 1, 999999999), 404) == "reason_not_found"

    def test_sin_lineas_o_con_cantidad_cero(self, api: Api, producto):
        p = producto("Vacía", 1000, 5)
        merma = motivo(api, "shrinkage")["id"]
        assert codigo(dar_salida(api, p, 1, merma, lines=[]), 400) == "empty_exit"
        respuesta = dar_salida(api, p, 0, merma)
        assert codigo(respuesta, 400) == "invalid_exit_line"
        assert respuesta[1]["detail"]["line"] == 1

    def test_lo_que_no_hay_no_sale(self, api: Api, producto):
        p = producto("Escaso", 1000, 2)
        respuesta = dar_salida(api, p, 3, motivo(api, "shrinkage")["id"])
        assert codigo(respuesta, 400) == "insufficient_stock"
        assert respuesta[1]["detail"]["available"] == 2
        assert cuadra(api, p) == 2
        assert [f["kind"] for f in kardex(api, p)] == ["opening"], "quedó una fila de una salida que falló"

    def test_un_producto_que_no_existe(self, api: Api, producto):
        p = producto("Existe", 1000, 5)
        respuesta = dar_salida(
            api, p, 1, motivo(api, "shrinkage")["id"],
            lines=[{"id_product": 999999999, "quantity": 1}],
        )
        assert codigo(respuesta, 404) == "product_not_found"


class TestAnularUnaSalida:
    def test_repone_al_costo_de_la_salida_y_no_al_promedio_de_hoy(self, api: Api, producto):
        p = producto("Anulable", 1000, 0)
        entrar(api, p, 10, 900)
        _, hecha = dar_salida(api, p, 4, motivo(api, "shrinkage")["id"])
        assert cuadra(api, p) == 6
        # Una compra más cara: el promedio sube a (6×900 + 10×1500) / 16 = 1 275.
        entrar(api, p, 10, 1500)

        anulada = api.ok(
            "POST", f"/inventory/exits/{hecha['id_exit']}/cancel", {"reason": "se contó mal"}
        )
        assert anulada["units_returned"] == 4
        assert cuadra(api, p) == 20

        [reversion, *_] = kardex(api, p)
        assert reversion["kind"] == "exit_void"
        assert (reversion["before_qty"], reversion["quantity"], reversion["after_qty"]) == (16, 4, 20)
        assert reversion["unit_cost"] == 900, "repuso al promedio de hoy"
        assert reversion["avg_cost_after"] == 1275, "el promedio no se deshace"

        listada = salida_listada(api, hecha["id_exit"])
        assert listada["status"] == "voided" and listada["void_reason"] == "se contó mal"
        assert listada["voided_at"] is not None

    def test_sin_motivo_no_se_anula(self, api: Api, producto):
        p = producto("Con motivo", 1000, 5)
        _, hecha = dar_salida(api, p, 1, motivo(api, "shrinkage")["id"])
        respuesta = api.call("POST", f"/inventory/exits/{hecha['id_exit']}/cancel", {"reason": "   "})
        assert codigo(respuesta, 400) == "void_reason_required"
        assert cuadra(api, p) == 4

    def test_no_se_anula_dos_veces(self, api: Api, producto):
        p = producto("Dos veces", 1000, 5)
        _, hecha = dar_salida(api, p, 1, motivo(api, "shrinkage")["id"])
        api.ok("POST", f"/inventory/exits/{hecha['id_exit']}/cancel", {"reason": "x"})
        respuesta = api.call("POST", f"/inventory/exits/{hecha['id_exit']}/cancel", {"reason": "otra"})
        assert codigo(respuesta, 400) == "exit_cancelled"
        assert cuadra(api, p) == 5, "repuso dos veces"

    def test_una_que_no_existe(self, api: Api):
        respuesta = api.call("POST", "/inventory/exits/999999999/cancel", {"reason": "x"})
        assert codigo(respuesta, 404) == "exit_not_found"


class TestElAsiento:
    """Con contabilidad activa: del inventario al gasto, y al revés al anular."""

    def _producto(self, cliente: Api, stock: int = 0) -> dict:
        marca = marca_unica()
        cliente.ok("POST", "/categories/register_category", {"name": f"Cat {marca}"})
        categoria = next(
            c for c in cliente.ok("GET", "/categories/categories_list") if c["name"] == f"Cat {marca}"
        )
        cliente.ok(
            "POST",
            "/products/add_product",
            {
                "name": f"Asentado {marca}",
                "description": "para el asiento",
                "price": 1000,
                "stock": stock,
                "barcode": f"AS{marca}",
                "created_at": "2026-01-01T00:00:00",
                "category_id": categoria["id"],
            },
        )
        return cliente.ok("GET", f"/products/product/AS{marca}")

    def _asientos_de(self, cliente: Api, id_exit: int) -> list[dict]:
        hoy = date.today()
        diario = cliente.ok("GET", f"/accounting/reports/journal?year={hoy.year}&month={hoy.month}")
        return [
            a for a in diario["entries"]
            if a["source_type"] == "stock_exit" and a["source_id"] == id_exit
        ]

    def test_la_salida_y_su_anulacion_dejan_sus_asientos(self, api: Api):
        negocio = compania_propia(api, "Salidas", modulos="accounting")
        activar(negocio)
        # La plantilla trae las dos cuentas nuevas (RN-99, RN-100).
        assert cuenta_por_codigo(negocio, "6.3.01")["name"] == "Mermas y ajustes de inventario"
        assert cuenta_por_codigo(negocio, "4.9.02")["kind"] == "income"

        p = self._producto(negocio)
        entrar(negocio, p, 10, 900)
        _, hecha = dar_salida(negocio, p, 2, motivo(negocio, "expired")["id"])
        assert hecha["total_cost"] == 1800

        [asiento] = self._asientos_de(negocio, hecha["id_exit"])
        por_cuenta = {(l["account_code"], l["debit"], l["credit"]) for l in asiento["lines"]}
        assert por_cuenta == {("6.3.01", 1800, 0), ("1.2.01", 0, 1800)}

        negocio.ok("POST", f"/inventory/exits/{hecha['id_exit']}/cancel", {"reason": "error"})
        asientos = self._asientos_de(negocio, hecha["id_exit"])
        assert {a["kind"] for a in asientos} == {"auto", "adjustment"}
        [ajuste] = [a for a in asientos if a["kind"] == "adjustment"]
        inverso = {(l["account_code"], l["debit"], l["credit"]) for l in ajuste["lines"]}
        assert inverso == {("1.2.01", 1800, 0), ("6.3.01", 0, 1800)}

    def test_una_salida_sin_costo_no_deja_asiento(self, api: Api):
        negocio = compania_propia(api, "Sin costo", modulos="accounting")
        activar(negocio)
        p = self._producto(negocio, stock=5)
        _, hecha = dar_salida(negocio, p, 1, motivo(negocio, "sample")["id"])
        assert hecha["total_cost"] == 0
        assert self._asientos_de(negocio, hecha["id_exit"]) == []
