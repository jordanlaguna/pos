"""
La toma física de punta a punta (F15, T-1503, RN-100).

Contra la pila de verdad: abrir por categoría, contar con lo que decía el
sistema en ese momento, vender entre contar y aplicar sin que cambie el ajuste,
aplicar con su fila en el kárdex y su asiento, y las dos tomas que no pueden
coexistir. Cada prueba abre su toma sobre una categoría **propia**: una de toda
la sucursal bloquearía a las demás —y a `test_aislamiento.py`, que deja una
abierta por compañía—.
"""

from __future__ import annotations

from datetime import date

from .conftest import Api, codigo, marca_unica
from .test_characterization import vender
from .test_contabilidad import activar, compania_propia
from .test_inventario import cuadra, entrar, kardex


def categoria(api: Api, nombre: str, parent_id: int | None = None) -> dict:
    marca = marca_unica()
    cuerpo = {"name": f"{nombre} {marca}"}
    if parent_id is not None:
        cuerpo["parent_id"] = parent_id
    api.ok("POST", "/categories/register_category", cuerpo)
    return next(c for c in api.ok("GET", "/categories/categories_list") if c["name"] == cuerpo["name"])


def producto_en(api: Api, categoria_id: int, nombre: str, stock: int) -> dict:
    marca = marca_unica()
    api.ok(
        "POST",
        "/products/add_product",
        {
            "name": f"{nombre} {marca}",
            "description": "para la toma",
            "price": 1000,
            "stock": stock,
            "barcode": f"TF{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria_id,
        },
    )
    return api.ok("GET", f"/products/product/TF{marca}")


def abrir(api: Api, category_id: int | None, **cambios):
    return api.call("POST", "/inventory/counts", {"category_id": category_id, **cambios})


def contar(api: Api, toma: int, producto: dict, contado: int):
    return api.call(
        "PUT",
        f"/inventory/counts/{toma}/lines",
        {"id_product": producto["id_product"], "counted_qty": contado},
    )


class TestAbrir:
    def test_de_una_categoria_y_la_lista_la_trae_abierta(self, api: Api):
        cat = categoria(api, "Toma")
        estado, abierta = abrir(api, cat["id"], notes="la de octubre")
        assert estado == 200, abierta
        listada = next(t for t in api.ok("GET", "/inventory/counts") if t["id"] == abierta["id_count"])
        assert (listada["status"], listada["category_id"], listada["category_name"]) == (
            "open", cat["id"], cat["name"],
        )
        assert listada["notes"] == "la de octubre" and listada["lines_count"] == 0
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/discard")

    def test_de_una_categoria_que_no_existe(self, api: Api):
        assert codigo(abrir(api, 999999999), 404) == "category_not_found"

    def test_una_raiz_abierta_bloquea_a_su_hija_y_viceversa(self, api: Api):
        raiz = categoria(api, "Raíz")
        hija = categoria(api, "Hija", parent_id=raiz["id"])
        _, de_la_raiz = abrir(api, raiz["id"])
        respuesta = abrir(api, hija["id"])
        assert codigo(respuesta, 409) == "count_already_open"
        assert respuesta[1]["detail"]["count_id"] == de_la_raiz["id_count"]
        assert respuesta[1]["detail"]["category_id"] == raiz["id"]
        api.ok("POST", f"/inventory/counts/{de_la_raiz['id_count']}/discard")

        _, de_la_hija = abrir(api, hija["id"])
        assert codigo(abrir(api, raiz["id"]), 409) == "count_already_open"
        api.ok("POST", f"/inventory/counts/{de_la_hija['id_count']}/discard")

    def test_dos_categorias_distintas_conviven(self, api: Api):
        una, otra = categoria(api, "Una"), categoria(api, "Otra")
        _, a = abrir(api, una["id"])
        estado, b = abrir(api, otra["id"])
        assert estado == 200, b
        for toma in (a, b):
            api.ok("POST", f"/inventory/counts/{toma['id_count']}/discard")


class TestContarYAplicar:
    def test_contar_8_donde_dice_10_deja_un_ajuste_de_menos_2(self, api: Api):
        """La verificación de T-1503, tal como está escrita en task.md."""
        cat = categoria(api, "Cuenta")
        p = producto_en(api, cat["id"], "Contado", 10)
        _, abierta = abrir(api, cat["id"])
        toma = abierta["id_count"]

        estado, contada = contar(api, toma, p, 8)
        assert estado == 200, contada
        assert (contada["system_qty"], contada["counted_qty"], contada["difference"]) == (10, 8, -2)

        # Vender una unidad entre contar y aplicar no cambia el ajuste.
        _, (estado, _) = vender(api, [(p, 1)])
        assert estado == 200
        assert cuadra(api, p) == 9

        aplicada = api.ok("POST", f"/inventory/counts/{toma}/apply")
        assert aplicada["adjustments"] == 1 and aplicada["difference_cost"] == 0
        assert cuadra(api, p) == 7

        [ajuste, *_] = kardex(api, p)
        assert ajuste["kind"] == "count"
        assert (ajuste["before_qty"], ajuste["quantity"], ajuste["after_qty"]) == (9, -2, 7)
        assert (ajuste["source_type"], ajuste["source_id"], ajuste["source_line"]) == ("stock_count", toma, 1)

        detalle = api.ok("GET", f"/inventory/counts/{toma}")
        assert detalle["status"] == "applied" and detalle["closed_by"] == api.user_id  # type: ignore[attr-defined]
        [linea] = detalle["lines"]
        assert (linea["name"], linea["system_qty"], linea["counted_qty"], linea["difference"]) == (
            p["name"], 10, 8, -2,
        )

    def test_volver_a_contar_reemplaza_y_lo_que_cuadra_no_deja_fila(self, api: Api):
        cat = categoria(api, "Repite")
        p = producto_en(api, cat["id"], "Repetido", 5)
        _, abierta = abrir(api, cat["id"])
        toma = abierta["id_count"]
        contar(api, toma, p, 3)
        contar(api, toma, p, 5)
        assert api.ok("GET", f"/inventory/counts/{toma}")["lines_count"] == 1

        aplicada = api.ok("POST", f"/inventory/counts/{toma}/apply")
        assert aplicada["adjustments"] == 0
        assert [f["kind"] for f in kardex(api, p)] == ["opening"]
        assert cuadra(api, p) == 5

    def test_un_sobrante_entra_al_kardex_con_signo_positivo(self, api: Api):
        cat = categoria(api, "Sobra")
        p = producto_en(api, cat["id"], "Sobrante", 2)
        _, abierta = abrir(api, cat["id"])
        contar(api, abierta["id_count"], p, 4)
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/apply")
        assert cuadra(api, p) == 4
        assert kardex(api, p)[0]["quantity"] == 2

    def test_fuera_del_alcance_no_se_cuenta(self, api: Api):
        cat, otra = categoria(api, "Dentro"), categoria(api, "Fuera")
        ajeno = producto_en(api, otra["id"], "Ajeno", 1)
        _, abierta = abrir(api, cat["id"])
        respuesta = contar(api, abierta["id_count"], ajeno, 1)
        assert codigo(respuesta, 400) == "count_outside_scope"
        assert respuesta[1]["detail"]["scope_category_id"] == cat["id"]
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/discard")

    def test_una_toma_de_la_raiz_cuenta_a_sus_hijas(self, api: Api):
        raiz = categoria(api, "Madre")
        hija = categoria(api, "Hija", parent_id=raiz["id"])
        p = producto_en(api, hija["id"], "De la hija", 3)
        _, abierta = abrir(api, raiz["id"])
        estado, _ = contar(api, abierta["id_count"], p, 3)
        assert estado == 200
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/discard")

    def test_sin_lineas_no_se_aplica_y_cerrada_no_se_toca(self, api: Api):
        cat = categoria(api, "Vacía")
        p = producto_en(api, cat["id"], "Intacto", 1)
        _, abierta = abrir(api, cat["id"])
        toma = abierta["id_count"]
        assert codigo(api.call("POST", f"/inventory/counts/{toma}/apply"), 400) == "count_has_no_lines"

        api.ok("POST", f"/inventory/counts/{toma}/discard")
        assert codigo(contar(api, toma, p, 1), 400) == "count_not_open"
        assert codigo(api.call("POST", f"/inventory/counts/{toma}/apply"), 400) == "count_not_open"
        assert codigo(api.call("POST", f"/inventory/counts/{toma}/discard"), 400) == "count_not_open"
        assert codigo(api.call("GET", "/inventory/counts/999999999"), 404) == "count_not_found"

    def test_lo_contado_no_puede_ser_negativo(self, api: Api):
        cat = categoria(api, "Negativo")
        p = producto_en(api, cat["id"], "Negado", 1)
        _, abierta = abrir(api, cat["id"])
        assert contar(api, abierta["id_count"], p, -1)[0] == 422
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/discard")

    def test_el_cajero_cuenta_pero_no_abre_ni_aplica(self, api: Api, cajero: Api):
        cat = categoria(api, "Cajero")
        p = producto_en(api, cat["id"], "Contado por caja", 2)
        assert abrir(cajero, cat["id"])[0] == 403
        _, abierta = abrir(api, cat["id"])
        estado, contada = contar(cajero, abierta["id_count"], p, 2)
        assert estado == 200, contada
        assert api.call("POST", f"/inventory/counts/{abierta['id_count']}/apply", token=cajero.token)[0] == 403
        api.ok("POST", f"/inventory/counts/{abierta['id_count']}/discard")


class TestElAsiento:
    def _producto(self, cliente: Api, stock: int) -> tuple[dict, dict]:
        cat = categoria(cliente, "Libro")
        return cat, producto_en(cliente, cat["id"], "Asentado", stock)

    def _asientos_de(self, cliente: Api, toma: int) -> list[dict]:
        hoy = date.today()
        diario = cliente.ok("GET", f"/accounting/reports/journal?year={hoy.year}&month={hoy.month}")
        return [a for a in diario["entries"] if a["source_type"] == "stock_count" and a["source_id"] == toma]

    def test_el_faltante_va_al_gasto_y_el_sobrante_al_ingreso(self, api: Api):
        negocio = compania_propia(api, "Tomas", modulos="accounting")
        activar(negocio)
        cat, p = self._producto(negocio, 0)
        entrar(negocio, p, 10, 900)

        _, abierta = abrir(negocio, cat["id"])
        contar(negocio, abierta["id_count"], p, 8)  # faltante de 2 × 900
        aplicada = negocio.ok("POST", f"/inventory/counts/{abierta['id_count']}/apply")
        assert aplicada["difference_cost"] == -1800
        [asiento] = self._asientos_de(negocio, abierta["id_count"])
        assert {(l["account_code"], l["debit"], l["credit"]) for l in asiento["lines"]} == {
            ("6.3.01", 1800, 0), ("1.2.01", 0, 1800),
        }

        _, segunda = abrir(negocio, cat["id"])
        contar(negocio, segunda["id_count"], p, 9)  # sobrante de 1 × 900
        aplicada = negocio.ok("POST", f"/inventory/counts/{segunda['id_count']}/apply")
        assert aplicada["difference_cost"] == 900
        [asiento] = self._asientos_de(negocio, segunda["id_count"])
        assert {(l["account_code"], l["debit"], l["credit"]) for l in asiento["lines"]} == {
            ("1.2.01", 900, 0), ("4.9.02", 0, 900),
        }
        assert cuadra(negocio, p) == 9
