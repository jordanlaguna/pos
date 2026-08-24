"""Categorías de dos niveles (T-401 a T-405; RF-13, RF-14; RN-5 a RN-8).

Las reglas puras se prueban sin base en `tests/domain/test_categories.py`. Acá
está lo que solo se ve con la base y el HTTP de verdad: que el UNIQUE compuesto
cierre el hueco de los nulos, que mover una subcategoría no se lleve los
productos, y que cada «no» llegue con su código (RN-30).

Necesita la pila de `docker-compose.test.yml`; sin ella se omite, como el resto.
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo, marca_unica


def _lista(api: Api) -> list[dict]:
    return api.ok("GET", "/categories/categories_list")


def _una(api: Api, category_id: int) -> dict:
    fila = next((c for c in _lista(api) if c["id"] == category_id), None)
    assert fila is not None, f"la categoría {category_id} no está en la lista"
    return fila


def _crear(api: Api, nombre: str, parent_id: int | None = None) -> dict:
    return api.ok(
        "POST", "/categories/register_category", {"name": nombre, "parent_id": parent_id}
    )


def _producto_en(api: Api, category_id: int, nombre: str = "Producto") -> dict:
    """Un producto colgado de esta categoría, con código de barras único."""
    marca = marca_unica()
    cuerpo = {
        "name": f"{nombre} {marca}",
        "description": "",
        "price": 1000,
        "stock": 5,
        "barcode": f"C{marca}",
        "created_at": "2026-01-01T00:00:00",
        "category_id": category_id,
    }
    api.ok("POST", "/products/add_product", cuerpo)
    return api.ok("GET", f"/products/product/{cuerpo['barcode']}")


@pytest.fixture
def raiz(api: Api) -> dict:
    """Una raíz nueva y solo para esta prueba.

    No se usa la del fixture `categoria`: esa la comparten casi veinte pruebas
    de producto, y colgarle una hija le impediría recibir productos (RN-6). Es
    la lección de T-309 —una prueba que cambia lo que otras usan las tumba
    todas— aplicada antes de que pase.
    """
    return _crear(api, f"Raíz {marca_unica()}")


class TestAlta:
    def test_una_raiz_nace_activa_y_al_final(self, api: Api, raiz: dict):
        fila = _una(api, raiz["id"])
        assert fila["parent_id"] is None
        assert fila["is_active"] is True
        # Al final de sus hermanas: quien la crea la ve donde la puso.
        raices = [c for c in _lista(api) if c["parent_id"] is None]
        assert max(c["sort_order"] for c in raices) == fila["sort_order"]

    def test_una_subcategoria_cuelga_de_su_raiz(self, api: Api, raiz: dict):
        hija = _crear(api, "Cervezas", raiz["id"])
        assert hija["parent_id"] == raiz["id"]
        assert _una(api, hija["id"])["parent_id"] == raiz["id"]

    def test_no_se_puede_colgar_de_una_subcategoria(self, api: Api, raiz: dict):
        """RN-5: exactamente dos niveles."""
        hija = _crear(api, "Cervezas", raiz["id"])
        respuesta = api.call(
            "POST", "/categories/register_category", {"name": "Rubias", "parent_id": hija["id"]}
        )
        assert codigo(respuesta, 400) == "category_too_deep"

    def test_dos_hermanas_no_se_llaman_igual(self, api: Api, raiz: dict):
        _crear(api, "Cervezas", raiz["id"])
        respuesta = api.call(
            "POST", "/categories/register_category", {"name": "Cervezas", "parent_id": raiz["id"]}
        )
        assert codigo(respuesta, 400) == "category_name_taken"

    def test_dos_raices_con_el_mismo_nombre_tampoco(self, api: Api):
        """El hueco que cierra la columna generada.

        Escrito como pedía la tarea —UNIQUE (company_id, parent_id, name)—, esto
        pasaba: MySQL no considera iguales dos nulos, así que el índice no dice
        nada de dos raíces homónimas, que es el caso más común de todos.
        """
        nombre = f"Duplicada {marca_unica()}"
        _crear(api, nombre)
        respuesta = api.call("POST", "/categories/register_category", {"name": nombre})
        assert codigo(respuesta, 400) == "category_name_taken"

    def test_el_mismo_nombre_en_dos_ramas_distintas_si(self, api: Api):
        """Y esto tiene que seguir pasando: es para lo que el UNIQUE lleva la madre.

        Un súper tiene «Bebidas → Latas» y «Conservas → Latas», y son dos cosas
        distintas.
        """
        una = _crear(api, f"Bebidas {marca_unica()}")
        otra = _crear(api, f"Conservas {marca_unica()}")
        _crear(api, "Latas", una["id"])
        _crear(api, "Latas", otra["id"])

    def test_una_madre_que_no_existe(self, api: Api):
        respuesta = api.call(
            "POST", "/categories/register_category", {"name": "Huérfana", "parent_id": 999999}
        )
        assert codigo(respuesta, 404) == "category_not_found"

    def test_la_madre_de_otra_compania_no_existe(self, api: Api, api_b: Api):
        """RN-8: las categorías son de la compañía.

        El filtro de `tenancy.py` hace que la raíz de B no exista para A, así que
        el «no» es 404 y no 403: un 403 confirmaría que ese id está usado.
        """
        ajena = _crear(api_b, f"De B {marca_unica()}")
        respuesta = api.call(
            "POST",
            "/categories/register_category",
            {"name": "Colada", "parent_id": ajena["id"]},
        )
        assert codigo(respuesta, 404) == "category_not_found"


class TestRenombrarYMover:
    def test_renombrar(self, api: Api, raiz: dict):
        nuevo = f"Renombrada {marca_unica()}"
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"name": nuevo})
        assert _una(api, raiz["id"])["name"] == nuevo

    def test_renombrar_una_hija_no_la_promueve_a_raiz(self, api: Api, raiz: dict):
        """La diferencia entre omitir `parent_id` y mandarlo en nulo.

        Sin distinguirlas, cualquier renombrado de subcategoría la desprendería
        de su rama y el catálogo se iría aplanando solo.
        """
        hija = _crear(api, "Cervezas", raiz["id"])
        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"name": "Cervezas frías"})
        assert _una(api, hija["id"])["parent_id"] == raiz["id"]

    def test_mover_a_otra_raiz_no_toca_los_productos(self, api: Api, raiz: dict):
        """RF-14, que es la razón de que el producto apunte a la categoría."""
        otra = _crear(api, f"Destino {marca_unica()}")
        hija = _crear(api, "Cervezas", raiz["id"])
        producto = _producto_en(api, hija["id"], "Imperial")

        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"parent_id": otra["id"]})

        assert _una(api, hija["id"])["parent_id"] == otra["id"]
        despues = api.ok("GET", f"/products/product/{producto['barcode']}")
        assert despues["category_id"] == hija["id"], "el producto se movió de categoría"

    def test_el_orden_se_renumera_en_el_destino(self, api: Api, raiz: dict):
        """El orden viejo pertenecía a la numeración de la madre anterior."""
        otra = _crear(api, f"Destino {marca_unica()}")
        _crear(api, "Primera", otra["id"])
        hija = _crear(api, "Cervezas", raiz["id"])

        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"parent_id": otra["id"]})
        assert _una(api, hija["id"])["sort_order"] == 2

    def test_una_raiz_con_hijas_no_puede_volverse_hija(self, api: Api, raiz: dict):
        """La otra mitad de RN-5: sin esto se crea un tercer nivel sin crear filas."""
        _crear(api, "Cervezas", raiz["id"])
        otra = _crear(api, f"Licores {marca_unica()}")

        respuesta = api.call(
            "PUT", f"/categories/update_category/{raiz['id']}", {"parent_id": otra["id"]}
        )
        assert codigo(respuesta, 400) == "category_has_children"
        assert respuesta[1]["detail"]["children"] == 1

    def test_no_puede_ser_su_propia_madre(self, api: Api, raiz: dict):
        """Lo único que la foránea no impide: una fila puede apuntarse a sí misma."""
        respuesta = api.call(
            "PUT", f"/categories/update_category/{raiz['id']}", {"parent_id": raiz["id"]}
        )
        assert codigo(respuesta, 400) == "category_self_parent"

    def test_promover_una_hija_a_raiz(self, api: Api, raiz: dict):
        """`parent_id` explícitamente en nulo: «pasala a raíz»."""
        hija = _crear(api, f"Emancipada {marca_unica()}", raiz["id"])
        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"parent_id": None})
        assert _una(api, hija["id"])["parent_id"] is None

    def test_mover_donde_el_nombre_ya_esta_tomado(self, api: Api, raiz: dict):
        """Al mudarse, un nombre libre entre las hermanas viejas puede estar tomado."""
        otra = _crear(api, f"Destino {marca_unica()}")
        _crear(api, "Cervezas", otra["id"])
        hija = _crear(api, "Cervezas", raiz["id"])

        respuesta = api.call(
            "PUT", f"/categories/update_category/{hija['id']}", {"parent_id": otra["id"]}
        )
        assert codigo(respuesta, 400) == "category_name_taken"

    def test_una_categoria_que_no_existe(self, api: Api):
        respuesta = api.call("PUT", "/categories/update_category/999999", {"name": "Fantasma"})
        assert codigo(respuesta, 404) == "category_not_found"


class TestDesactivar:
    def test_desactivar_no_la_saca_de_la_lista(self, api: Api, raiz: dict):
        """La lista trae activas e inactivas: el inventario tiene que poder
        nombrar la categoría de un producto y volver a activarla."""
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"is_active": False})
        assert _una(api, raiz["id"])["is_active"] is False

    def test_a_una_desactivada_no_se_le_cuelgan_productos_nuevos(self, api: Api, raiz: dict):
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"is_active": False})
        marca = marca_unica()
        respuesta = api.call(
            "POST",
            "/products/add_product",
            {
                "name": f"Tardío {marca}",
                "description": "",
                "price": 1000,
                "stock": 1,
                "barcode": f"C{marca}",
                "created_at": "2026-01-01T00:00:00",
                "category_id": raiz["id"],
            },
        )
        assert codigo(respuesta, 400) == "category_inactive"

    def test_los_productos_que_ya_estaban_se_quedan(self, api: Api, raiz: dict):
        """Desactivar no mueve nada: es lo que la distingue de borrar."""
        producto = _producto_en(api, raiz["id"], "Anterior")
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"is_active": False})
        despues = api.ok("GET", f"/products/product/{producto['barcode']}")
        assert despues["category_id"] == raiz["id"]

    def test_volver_a_activarla(self, api: Api, raiz: dict):
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"is_active": False})
        api.ok("PUT", f"/categories/update_category/{raiz['id']}", {"is_active": True})
        assert _una(api, raiz["id"])["is_active"] is True


class TestBorrar:
    def test_una_vacia_se_borra(self, api: Api, raiz: dict):
        estado, _ = api.call("DELETE", f"/categories/delete_category/{raiz['id']}")
        assert estado == 204
        assert all(c["id"] != raiz["id"] for c in _lista(api))

    def test_con_productos_no(self, api: Api, raiz: dict):
        """RN-7. Borrarla dejaría productos apuntando a una fila que no existe."""
        _producto_en(api, raiz["id"])
        respuesta = api.call("DELETE", f"/categories/delete_category/{raiz['id']}")
        assert codigo(respuesta, 409) == "category_in_use"
        assert respuesta[1]["detail"]["products"] == 1

    def test_con_hijas_no(self, api: Api, raiz: dict):
        _crear(api, "Cervezas", raiz["id"])
        respuesta = api.call("DELETE", f"/categories/delete_category/{raiz['id']}")
        assert codigo(respuesta, 409) == "category_in_use"
        assert respuesta[1]["detail"]["children"] == 1

    def test_una_que_no_existe(self, api: Api):
        respuesta = api.call("DELETE", "/categories/delete_category/999999")
        assert codigo(respuesta, 404) == "category_not_found"


class TestElProductoVaEnLaHoja:
    """RN-6, en los dos caminos por los que nace un producto."""

    def test_una_raiz_con_hijas_no_recibe_productos(self, api: Api, raiz: dict):
        _crear(api, "Cervezas", raiz["id"])
        marca = marca_unica()
        respuesta = api.call(
            "POST",
            "/products/add_product",
            {
                "name": f"Colgado {marca}",
                "description": "",
                "price": 1000,
                "stock": 1,
                "barcode": f"C{marca}",
                "created_at": "2026-01-01T00:00:00",
                "category_id": raiz["id"],
            },
        )
        assert codigo(respuesta, 400) == "category_needs_subcategory"
        # El nombre y la cuenta van en los datos: el POS arma «Bebidas tiene 1
        # subcategoría: elija una».
        assert respuesta[1]["detail"]["children"] == 1

    def test_la_subcategoria_si(self, api: Api, raiz: dict):
        hija = _crear(api, "Cervezas", raiz["id"])
        producto = _producto_en(api, hija["id"])
        assert producto["category_id"] == hija["id"]

    def test_mover_un_producto_a_una_raiz_con_hijas(self, api: Api, raiz: dict):
        producto = _producto_en(api, raiz["id"])
        otra = _crear(api, f"Con rama {marca_unica()}")
        _crear(api, "Cervezas", otra["id"])

        respuesta = api.call(
            "PUT",
            f"/products/update_product/{producto['id_product']}",
            {"category_id": otra["id"]},
        )
        assert codigo(respuesta, 400) == "category_needs_subcategory"

    def test_una_raiz_con_su_unica_hija_desactivada_vuelve_a_recibir(self, api: Api, raiz: dict):
        """La decisión de contar solo las hijas **activas**.

        Contando también las desactivadas, esta rama se quedaría sin ningún
        sitio donde poner un producto: la raíz bloqueada por su hija, y la hija
        fuera de circulación. La única salida sería reactivar algo que el dueño
        acaba de retirar a propósito.
        """
        hija = _crear(api, "Cervezas", raiz["id"])
        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"is_active": False})

        producto = _producto_en(api, raiz["id"], "De vuelta")
        assert producto["category_id"] == raiz["id"]

    def test_pero_para_borrar_la_hija_desactivada_sigue_contando(self, api: Api, raiz: dict):
        """La otra mitad de la decisión: una hija desactivada sigue siendo una fila."""
        hija = _crear(api, "Cervezas", raiz["id"])
        api.ok("PUT", f"/categories/update_category/{hija['id']}", {"is_active": False})

        respuesta = api.call("DELETE", f"/categories/delete_category/{raiz['id']}")
        assert codigo(respuesta, 409) == "category_in_use"
        assert respuesta[1]["detail"]["children"] == 1

    def test_cambiar_el_precio_no_revalida_la_categoria(self, api: Api, raiz: dict):
        """El producto que ya estaba colgado de una raíz se queda ahí.

        Si al cambiarle el precio se revalidara su categoría, agregarle una hija
        a esa raíz dejaría a sus productos sin poder editarse.
        """
        producto = _producto_en(api, raiz["id"])
        _crear(api, "Cervezas", raiz["id"])
        api.ok("PUT", f"/products/update_product/{producto['id_product']}", {"price": 1500})

    def test_la_entrada_de_mercaderia_tambien(self, api: Api, raiz: dict):
        """Sin esto, el archivo del proveedor es la puerta de atrás de RN-6."""
        _crear(api, "Cervezas", raiz["id"])
        marca = marca_unica()
        cuerpo = {
            "document_number": f"F{marca}",
            "supplier": "Proveedor de pruebas",
            "source": "manual",
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "notes": None,
            "lines": [
                {
                    "quantity": 1,
                    "unit_cost": 500,
                    "new_product": {
                        "name": f"Importado {marca}",
                        "description": "",
                        "price": 1000,
                        "barcode": f"E{marca}",
                        "category_id": raiz["id"],
                    },
                }
            ],
        }
        respuesta = api.call("POST", "/inventory/entry", cuerpo)
        assert codigo(respuesta, 400) == "category_needs_subcategory"


class TestReordenar:
    """RF-13. Se reordenan hijas y no raíces a propósito: las raíces las
    comparten las demás pruebas, y cambiarles el orden es cambiarles el estado."""

    def test_el_orden_es_el_que_se_pide(self, api: Api, raiz: dict):
        una = _crear(api, "Primera", raiz["id"])
        dos = _crear(api, "Segunda", raiz["id"])
        tres = _crear(api, "Tercera", raiz["id"])

        api.ok(
            "PUT",
            "/categories/reorder",
            {"parent_id": raiz["id"], "ids": [tres["id"], una["id"], dos["id"]]},
        )

        hijas = sorted(
            (c for c in _lista(api) if c["parent_id"] == raiz["id"]),
            key=lambda c: c["sort_order"],
        )
        assert [c["id"] for c in hijas] == [tres["id"], una["id"], dos["id"]]
        # Renumeradas desde 1: los huecos de los borrados se arreglan solos.
        assert [c["sort_order"] for c in hijas] == [1, 2, 3]

    def test_la_lista_tiene_que_estar_completa(self, api: Api, raiz: dict):
        una = _crear(api, "Primera", raiz["id"])
        _crear(api, "Segunda", raiz["id"])

        respuesta = api.call(
            "PUT", "/categories/reorder", {"parent_id": raiz["id"], "ids": [una["id"]]}
        )
        assert codigo(respuesta, 400) == "category_reorder_incomplete"

    def test_con_ids_de_otra_compania_tampoco(self, api: Api, api_b: Api, raiz: dict):
        """RN-8 por la vía del reordenamiento, que no recibe id en la ruta."""
        _crear(api, "Primera", raiz["id"])
        ajena = _crear(api_b, f"De B {marca_unica()}")

        respuesta = api.call(
            "PUT", "/categories/reorder", {"parent_id": raiz["id"], "ids": [ajena["id"]]}
        )
        assert codigo(respuesta, 400) == "category_reorder_incomplete"


class TestSoloElAdministrador:
    """Leer el catálogo es de cualquiera —el cajero necesita la grilla—;
    cambiarlo, no."""

    def test_el_cajero_lee(self, cajero: Api):
        cajero.ok("GET", "/categories/categories_list")

    def test_el_cajero_no_crea(self, cajero: Api):
        respuesta = cajero.call(
            "POST", "/categories/register_category", {"name": f"Del cajero {marca_unica()}"}
        )
        assert codigo(respuesta, 403) == "admin_only"

    def test_el_cajero_no_renombra(self, cajero: Api, raiz: dict):
        respuesta = cajero.call(
            "PUT", f"/categories/update_category/{raiz['id']}", {"name": "Cambiada"}
        )
        assert codigo(respuesta, 403) == "admin_only"

    def test_el_cajero_no_reordena(self, cajero: Api, raiz: dict):
        respuesta = cajero.call(
            "PUT", "/categories/reorder", {"parent_id": None, "ids": [raiz["id"]]}
        )
        assert codigo(respuesta, 403) == "admin_only"

    def test_el_cajero_no_borra(self, cajero: Api, raiz: dict):
        respuesta = cajero.call("DELETE", f"/categories/delete_category/{raiz['id']}")
        assert codigo(respuesta, 403) == "admin_only"
