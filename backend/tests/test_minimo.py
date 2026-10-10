"""
El mínimo por producto y el general (F15, T-1504, RN-101, RF-90).

Contra la pila de verdad: la ficha guarda y quita el mínimo propio, el reporte
de bajo mínimo aplica el propio y, sin él, el general de Configuración —que se
cambia por `PUT /settings/` y se restaura al final—, y lo que lista trae la
existencia por sucursal.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from .conftest import Api, codigo, marca_unica
from .test_tomas import categoria


@pytest.fixture
def categoria_id(api: Api) -> int:
    return categoria(api, "Mínimo")["id"]


def producto(api: Api, categoria_id: int, nombre: str, stock: int, **extra) -> dict:
    marca = marca_unica()
    api.ok(
        "POST",
        "/products/add_product",
        {
            "name": f"{nombre} {marca}",
            "description": "para el mínimo",
            "price": 1000,
            "stock": stock,
            "barcode": f"MN{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria_id,
            **extra,
        },
    )
    return api.ok("GET", f"/products/product/MN{marca}")


def bajos(api: Api) -> dict[int, dict]:
    return {p["id_product"]: p for p in api.ok("GET", "/reports/low_stock")}


@contextmanager
def minimo_general(api: Api, valor: int | None):
    """Deja el general en `valor` y lo devuelve a como estaba al salir."""
    original = api.ok("GET", "/settings/")["data"] or {}
    inventario = dict(original.get("inventory") or {})
    api.ok(
        "PUT",
        "/settings/",
        {"data": {**original, "inventory": {**inventario, "minStock": valor}}, "keep_logo": True},
    )
    try:
        yield
    finally:
        api.ok("PUT", "/settings/", {"data": original, "keep_logo": True})


class TestLaFicha:
    def test_nace_sin_minimo_y_se_le_pone_uno(self, api: Api, categoria_id):
        p = producto(api, categoria_id, "Sin mínimo", 20)
        assert p["min_stock"] is None

        api.ok("PUT", f"/products/update_product/{p['id_product']}", {"min_stock": 25})
        assert api.ok("GET", f"/products/product/{p['barcode']}")["min_stock"] == 25

        # Nulo lo quita: vuelve al general (RN-101).
        api.ok("PUT", f"/products/update_product/{p['id_product']}", {"min_stock": None})
        assert api.ok("GET", f"/products/product/{p['barcode']}")["min_stock"] is None

    def test_nace_con_el_suyo(self, api: Api, categoria_id):
        p = producto(api, categoria_id, "Con mínimo", 20, min_stock=3)
        assert p["min_stock"] == 3

    def test_un_minimo_negativo_responde_con_codigo(self, api: Api, categoria_id):
        p = producto(api, categoria_id, "Negativo", 20)
        assert codigo(api.call("PUT", f"/products/update_product/{p['id_product']}", {"min_stock": -1}), 400) == (
            "min_stock_negative"
        )
        marca = marca_unica()
        respuesta = api.call(
            "POST",
            "/products/add_product",
            {
                "name": f"Negativo al nacer {marca}",
                "description": "x",
                "price": 1,
                "stock": 0,
                "barcode": f"MN{marca}",
                "created_at": "2026-01-01T00:00:00",
                "category_id": categoria_id,
                "min_stock": -5,
            },
        )
        assert codigo(respuesta, 400) == "min_stock_negative"


class TestElReporte:
    def test_el_propio_manda_y_sin_propio_manda_el_general(self, api: Api, categoria_id):
        """La verificación de T-1504, tal como está escrita en task.md."""
        propio_bajo = producto(api, categoria_id, "Propio bajo", 20, min_stock=20)
        propio_alto = producto(api, categoria_id, "Propio holgado", 20, min_stock=5)
        general_bajo = producto(api, categoria_id, "General bajo", 10)
        general_alto = producto(api, categoria_id, "General holgado", 11)

        # Con el general de fábrica (10): el 20 con mínimo 20 avisa, el de 10
        # sin mínimo avisa, los otros dos no.
        with minimo_general(api, 10):
            lista = bajos(api)
        assert propio_bajo["id_product"] in lista and general_bajo["id_product"] in lista
        assert propio_alto["id_product"] not in lista and general_alto["id_product"] not in lista
        assert lista[propio_bajo["id_product"]]["threshold"] == 20
        assert lista[general_bajo["id_product"]]["threshold"] == 10

        # Subir el general a 15 alcanza al de 11; el de mínimo propio 5 sigue sin avisar.
        with minimo_general(api, 15):
            lista = bajos(api)
        assert general_alto["id_product"] in lista
        assert propio_alto["id_product"] not in lista

    def test_sin_general_solo_avisan_los_que_tienen_minimo_propio(self, api: Api, categoria_id):
        con = producto(api, categoria_id, "Con propio", 0, min_stock=1)
        sin = producto(api, categoria_id, "Sin nada", 0)
        with minimo_general(api, None):
            lista = bajos(api)
        assert con["id_product"] in lista
        assert sin["id_product"] not in lista
        assert lista[con["id_product"]]["threshold"] == 1

    def test_trae_la_existencia_por_sucursal(self, api: Api, categoria_id):
        p = producto(api, categoria_id, "Por sucursal", 4, min_stock=4)
        fila = bajos(api)[p["id_product"]]
        assert fila["stock"] == 4 and fila["min_stock"] == 4
        [sucursal] = fila["branches"]
        assert sucursal["quantity"] == 4 and sucursal["name"]

    def test_un_umbral_en_la_consulta_ya_no_cuenta(self, api: Api, categoria_id):
        p = producto(api, categoria_id, "Umbral viejo", 50, min_stock=5)
        assert p["id_product"] not in {
            f["id_product"] for f in api.ok("GET", "/reports/low_stock?threshold=100")
        }
