"""
Los «no» del servidor, uno por uno (T-802, T-803, RN-30).

Dos cosas distintas se comprueban acá y por eso el archivo tiene dos mitades.

**El guardián** lee el árbol de sintaxis de `app/` y no necesita nada levantado.
Comprueba que todo `HTTPException` se construya en `app/utils/api_errors.py`,
que ningún código sea de invención propia y que ninguno del catálogo esté de
adorno. Es lo que impide que la regla se afloje a la primera: un `detail="…"`
escrito en un apuro tumba `pytest` en vez de llegar a la pantalla de alguien.

**Situación → código** habla con la API por HTTP y arma la situación de verdad:
vender sin existencias, cerrar una caja que no está abierta, cargar dos veces la
misma factura. Reemplaza a comparar cadenas, que era la única forma que había de
saber por qué había fallado algo. Comparar cadenas ataba las pruebas al idioma
—cambiar una coma en un mensaje rompía una prueba de negocio— y aun así no
distinguía dos errores que empezaran igual.

La segunda mitad necesita la pila de `docker-compose.test.yml`; sin ella se
omite, como el resto.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.utils.api_errors import CODES, DONE
from .conftest import Api, bootstrap, cerrar_caja_abierta, entrar, marca_unica

APP = Path(__file__).resolve().parent.parent / "app"

#: El único módulo donde se puede construir un `HTTPException`.
FABRICA = APP / "utils" / "api_errors.py"

#: Las funciones que lo construyen. Todo `raise` del backend pasa por una.
#: `_no_autorizado` es el envoltorio de `unauthorized` en `auth_dependency`.
CONSTRUCTORES = {"api_error", "unauthorized", "_no_autorizado"}

#: Las que tienen código por omisión: llamarlas sin argumentos es 'unauthorized'.
CON_OMISION = {"unauthorized", "_no_autorizado"}


def modulos() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p != FABRICA)


def arbol(archivo: Path) -> ast.Module:
    return ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))


def nombre_llamado(nodo: ast.Call) -> str | None:
    """`api_error(...)` → 'api_error'; `mod.api_error(...)` → 'api_error'."""
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def codigos_usados() -> dict[str, list[str]]:
    """Cada código que el backend levanta, con dónde lo hace."""
    encontrados: dict[str, list[str]] = {}
    for archivo in modulos():
        for nodo in ast.walk(arbol(archivo)):
            if not isinstance(nodo, ast.Call):
                continue
            llamada = nombre_llamado(nodo)
            if llamada not in CONSTRUCTORES:
                continue

            donde = f"{archivo.relative_to(APP)}:{nodo.lineno}".replace("\\", "/")
            # `api_error(400, "x")` → el código es el segundo posicional;
            # `unauthorized("x")` → el primero. Los que no son literales
            # (`api_error(400, codigos[e.code])`) no se pueden leer acá y los
            # cubre la segunda mitad del archivo, situación por situación.
            literal = next(
                (
                    a.value
                    for a in nodo.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ),
                None,
            )
            if literal is None and llamada in CON_OMISION:
                literal = "unauthorized"
            if literal is not None:
                encontrados.setdefault(literal, []).append(donde)
    return encontrados


# --------------------------------------------------------------- el guardián


def test_todo_HTTPException_se_construye_en_un_solo_lugar():
    """
    RN-30 no se sostiene con buena voluntad.

    Mientras `HTTPException(detail="…")` se pueda escribir en cualquier archivo,
    alguien con prisa lo va a escribir, y el POS mostrará esa frase en español a
    quien tenga la aplicación en portugués. Acá el atajo no compila.
    """
    culpables = []
    for archivo in modulos():
        for nodo in ast.walk(arbol(archivo)):
            if isinstance(nodo, ast.Call) and nombre_llamado(nodo) == "HTTPException":
                culpables.append(f"{archivo.relative_to(APP)}:{nodo.lineno}".replace("\\", "/"))

    assert not culpables, (
        "Estos lugares construyen un HTTPException por su cuenta:\n  "
        + "\n  ".join(culpables)
        + "\n\nUsá `api_error(status, code, **datos)` de app/utils/api_errors.py: "
        "el backend devuelve un código y los datos, no una frase (RN-30)."
    )


def test_ningun_codigo_esta_inventado():
    """Un código que no está en el catálogo es un código sin traducción."""
    desconocidos = {c: d for c, d in codigos_usados().items() if c not in CODES}
    assert not desconocidos, (
        "Códigos que no están en CODES:\n  "
        + "\n  ".join(f"{c} — {', '.join(d)}" for c, d in sorted(desconocidos.items()))
        + "\n\nAgregalos a app/utils/api_errors.py y al catálogo del POS "
        "(frontend/messages/es/errors.json)."
    )


def test_ningun_codigo_del_catalogo_esta_de_adorno():
    """
    Al revés: un código en la lista que nadie levanta.

    Suele ser un error de dedo —el catálogo dice `product_not_found` y el
    `raise` dice `produt_not_found`— y sin esta prueba las dos anteriores pasan
    igual, porque cada una mira su lado.
    """
    usados = set(codigos_usados())
    # `cash_invalid_movement_type` y compañía se levantan desde una tabla
    # (`codigos[e.code]`), no como literal en la llamada: el AST no los ve.
    desde_tabla = {
        "cash_invalid_movement_type",
        "cash_amount_not_positive",
        "cash_missing_reason",
    }
    huerfanos = CODES - usados - desde_tabla
    assert not huerfanos, (
        f"Códigos en el catálogo que nadie levanta: {sorted(huerfanos)}. "
        "O falta el `raise`, o hay un error de dedo en uno de los dos lados."
    )


def test_las_frases_de_los_codigos_de_la_tabla_estan_en_el_catalogo():
    """Los tres que el AST no ve tienen que estar declarados igual que el resto."""
    from app.services import crud_cash  # noqa: PLC0415  (se importa acá y no arriba

    # a propósito: el módulo arrastra SQLAlchemy y el resto del archivo no lo
    # necesita.)
    fuente = Path(crud_cash.__file__).read_text(encoding="utf-8")
    for code in ("cash_invalid_movement_type", "cash_amount_not_positive", "cash_missing_reason"):
        assert code in fuente, f"{code} ya no se levanta en crud_cash.py"
        assert code in CODES


def test_los_si_tambien_son_codigos():
    """
    Los mensajes de éxito no los lee nadie, y aun así iban en español.

    Una respuesta con prosa adentro es prosa que alguien acabará mostrando: es
    exactamente lo que pasó con los `detail`. El campo se sigue llamando
    `message` porque es el contrato publicado; el valor es un código.
    """
    prosa = []
    for archivo in modulos():
        for nodo in ast.walk(arbol(archivo)):
            if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
                continue
            valor = nodo.value
            # Una frase para persona tiene espacios; un código, nunca.
            if valor in DONE or " " not in valor:
                continue
            donde = f"{archivo.relative_to(APP)}:{nodo.lineno}".replace("\\", "/")
            if "exitosamente" in valor.lower() or "successfully" in valor.lower():
                prosa.append(f"{donde} — {valor!r}")

    assert not prosa, (
        "Quedan mensajes de éxito en prosa:\n  " + "\n  ".join(prosa) +
        "\n\nUsá uno de los códigos de DONE (app/utils/api_errors.py)."
    )


# --------------------------------------------------- situación → código (HTTP)


def codigo(respuesta: tuple[int, object], estado_esperado: int) -> str:
    """El código de un «no», comprobando de paso el estado HTTP."""
    estado, cuerpo = respuesta
    assert estado == estado_esperado, f"se esperaba {estado_esperado} y vino {estado}: {cuerpo}"
    assert isinstance(cuerpo, dict), f"el cuerpo no es un objeto: {cuerpo}"
    detail = cuerpo.get("detail")
    assert isinstance(detail, dict), (
        f"el detalle tiene que ser código y datos, y vino {detail!r}. "
        "El backend no escribe frases (RN-30)."
    )
    return detail["code"]


def venta(api: Api, lineas: list[tuple[dict, int]], **cambios) -> dict:
    """Cuerpo de venta con los totales calculados como los calcula el POS."""
    subtotal = round(sum(p["price"] * c for p, c in lineas), 2)
    impuesto = round(subtotal * 0.13, 2)
    total = round(subtotal + impuesto, 2)
    cuerpo = {
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
    }
    cuerpo.update(cambios)
    return cuerpo


@pytest.mark.characterization
class TestSesion:
    def test_sin_token(self, api: Api):
        assert codigo(api.call("GET", "/products/products_list", token=None), 401) == "unauthorized"

    def test_token_que_no_es_un_token(self, api: Api):
        assert codigo(api.call("GET", "/products/products_list", token="no-soy-un-jwt"), 401) == (
            "unauthorized"
        )

    def test_contraseña_incorrecta(self, api: Api):
        respuesta = api.call(
            "POST", "/auth/login", {"email": "admin@pruebas.ventasys.cr", "password": "x"}
        )
        assert codigo(respuesta, 401) == "invalid_credentials"

    def test_correo_que_no_existe(self, api: Api):
        """El mismo código que la contraseña mala: distinguirlos convertiría el
        login en un verificador de correos registrados."""
        respuesta = api.call(
            "POST", "/auth/login", {"email": "nadie@pruebas.ventasys.cr", "password": "x"}
        )
        assert codigo(respuesta, 401) == "invalid_credentials"

    def test_compañia_que_no_es_suya(self, api: Api):
        assert codigo(api.call("POST", "/auth/company", {"company_id": 99999}), 404) == (
            "membership_not_found"
        )

    def test_accion_de_invitacion_que_no_existe(self, api: Api):
        respuesta = api.call("POST", "/auth/invitation", {"company_id": 1, "accion": "quizás"})
        assert codigo(respuesta, 400) == "invalid_invitation_action"

    def test_solo_administradores(self, cajero: Api):
        # La configuración la LEE cualquier sesión; los reportes son solo del
        # administrador. Se prueba con los reportes por eso.
        assert codigo(cajero.call("GET", "/reports/summary"), 403) == "admin_only"


@pytest.mark.characterization
class TestCatalogo:
    def test_codigo_de_barras_repetido_al_crear(self, api: Api, producto, categoria: int):
        p = producto("Repetido", 1000, 5)
        respuesta = api.call(
            "POST",
            "/products/add_product",
            {
                "name": "Otro con el mismo código",
                "description": "",
                "price": 1000,
                "stock": 1,
                "barcode": p["barcode"],
                "created_at": "2026-01-01T00:00:00",
                "category_id": categoria,
            },
        )
        assert codigo(respuesta, 400) == "barcode_taken"

    def test_codigo_de_barras_repetido_al_editar(self, api: Api, producto):
        uno = producto("Primero", 1000, 5)
        otro = producto("Segundo", 1000, 5)
        respuesta = api.call(
            "PUT", f"/products/update_product/{otro['id_product']}", {"barcode": uno["barcode"]}
        )
        assert codigo(respuesta, 400) == "barcode_taken"

    def test_producto_que_no_existe(self, api: Api):
        assert codigo(api.call("GET", "/products/product/no-existe-99999"), 404) == (
            "product_not_found"
        )

    def test_borrar_un_producto_ya_vendido(self, api: Api, producto):
        p = producto("Vendido", 1000, 5)
        api.ok("POST", "/sales/add_sale", venta(api, [(p, 1)]))
        respuesta = api.call("DELETE", f"/products/delete_product/{p['id_product']}")
        assert codigo(respuesta, 400) == "product_has_sales"

    def test_categoria_repetida(self, api: Api, categoria: int):
        respuesta = api.call("POST", "/categories/register_category", {"name": "Pruebas"})
        assert codigo(respuesta, 400) == "category_name_taken"


@pytest.mark.characterization
class TestVenta:
    def test_sin_lineas(self, api: Api, producto):
        p = producto("Sin líneas", 1000, 5)
        assert codigo(api.call("POST", "/sales/add_sale", venta(api, [(p, 1)], products=[])), 400) == (
            "empty_sale"
        )

    def test_numero_repetido(self, api: Api, producto):
        p = producto("Consecutivo", 1000, 20)
        primera = venta(api, [(p, 1)])
        api.ok("POST", "/sales/add_sale", primera)
        repetida = venta(api, [(p, 1)], sale_number=primera["sale_number"])
        assert codigo(api.call("POST", "/sales/add_sale", repetida), 400) == "duplicate_sale_number"

    def test_producto_que_no_existe(self, api: Api, producto):
        p = producto("Fantasma", 1000, 5)
        cuerpo = venta(api, [(p, 1)], products=[{"id_product": 999999, "stock": 1}])
        assert codigo(api.call("POST", "/sales/add_sale", cuerpo), 404) == "product_not_found"

    def test_cantidad_que_no_es_cantidad(self, api: Api, producto):
        p = producto("Cantidad mala", 1000, 5)
        cuerpo = venta(api, [(p, 1)], products=[{"id_product": p["id_product"], "stock": 0}])
        assert codigo(api.call("POST", "/sales/add_sale", cuerpo), 400) == "invalid_sale_line"

    def test_sin_existencias(self, api: Api, producto):
        p = producto("Poco stock", 1000, 2)
        estado, cuerpo = api.call("POST", "/sales/add_sale", venta(api, [(p, 5)]))
        assert codigo((estado, cuerpo), 400) == "insufficient_stock"
        # Los datos son lo que le deja al POS armar la frase, y con el nombre
        # adentro: «quedan 2 de Poco stock», no «del producto 47».
        detail = cuerpo["detail"]
        assert detail["available"] == 2 and detail["requested"] == 5
        assert p["name"] == detail["product"]

    def test_total_alterado(self, api: Api, producto):
        p = producto("Total alterado", 1450, 10)
        estado, cuerpo = api.call(
            "POST", "/sales/add_sale", venta(api, [(p, 3)], total=1.0, cash_received=1.0)
        )
        assert codigo((estado, cuerpo), 400) == "totals_mismatch"
        # El campo viaja con el nombre del API, no con la palabra de la frase.
        assert cuerpo["detail"]["field"] in ("subtotal", "tax", "total")

    def test_efectivo_que_no_alcanza(self, api: Api, producto):
        p = producto("Pago corto", 1450, 10)
        respuesta = api.call("POST", "/sales/add_sale", venta(api, [(p, 3)], cash_received=100.0))
        assert codigo(respuesta, 400) == "insufficient_payment"

    def test_venta_que_no_existe(self, api: Api):
        assert codigo(api.call("GET", "/sales/sale/999999"), 404) == "sale_not_found"


@pytest.mark.characterization
class TestDevolucion:
    def test_venta_que_no_existe(self, api: Api):
        cuerpo = {"sale_id": 999999, "user_id": api.user_id, "reason": "x", "items": []}
        assert codigo(api.call("POST", "/returns/add_return", cuerpo), 404) == "sale_not_found"

    def test_sin_productos(self, api: Api, producto):
        p = producto("Devolución vacía", 1000, 5)
        v = api.ok("POST", "/sales/add_sale", venta(api, [(p, 1)]))
        cuerpo = {"sale_id": v["id_sale"], "user_id": api.user_id, "reason": "x", "items": []}
        assert codigo(api.call("POST", "/returns/add_return", cuerpo), 400) == "empty_return"

    def test_sin_motivo(self, api: Api, producto):
        p = producto("Sin motivo", 1000, 5)
        v = api.ok("POST", "/sales/add_sale", venta(api, [(p, 1)]))
        cuerpo = {
            "sale_id": v["id_sale"],
            "user_id": api.user_id,
            "reason": "   ",
            "items": [{"id_product": p["id_product"], "quantity": 1}],
        }
        assert codigo(api.call("POST", "/returns/add_return", cuerpo), 400) == (
            "missing_return_reason"
        )

    def test_producto_que_esa_venta_no_llevaba(self, api: Api, producto):
        p = producto("Vendido", 1000, 5)
        otro = producto("No vendido", 1000, 5)
        v = api.ok("POST", "/sales/add_sale", venta(api, [(p, 1)]))
        cuerpo = {
            "sale_id": v["id_sale"],
            "user_id": api.user_id,
            "reason": "dañado",
            "items": [{"id_product": otro["id_product"], "quantity": 1}],
        }
        assert codigo(api.call("POST", "/returns/add_return", cuerpo), 400) == (
            "not_sold_in_this_sale"
        )

    def test_mas_unidades_de_las_que_quedan(self, api: Api, producto):
        p = producto("Dos vendidas", 1000, 5)
        v = api.ok("POST", "/sales/add_sale", venta(api, [(p, 2)]))
        cuerpo = {
            "sale_id": v["id_sale"],
            "user_id": api.user_id,
            "reason": "dañado",
            "items": [{"id_product": p["id_product"], "quantity": 3}],
        }
        estado, respuesta = api.call("POST", "/returns/add_return", cuerpo)
        assert codigo((estado, respuesta), 400) == "excessive_return"
        assert respuesta["detail"]["remaining"] == 2

    def test_devolucion_que_no_existe(self, api: Api):
        assert codigo(api.call("GET", "/returns/return/999999"), 404) == "return_not_found"


@pytest.mark.characterization
class TestCaja:
    def test_abrir_dos_veces(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        respuesta = cajero.call(
            "POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000}
        )
        assert codigo(respuesta, 400) == "cash_already_open"
        cerrar_caja_abierta(cajero)

    def test_apertura_negativa(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        respuesta = cajero.call(
            "POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": -1}
        )
        assert codigo(respuesta, 400) == "cash_opening_negative"

    def test_mover_sin_caja_abierta(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        respuesta = cajero.call(
            "POST",
            "/cash/movement",
            {"user_id": cajero.user_id, "type": "entrada", "amount": 100, "reason": "x"},
        )
        assert codigo(respuesta, 400) == "cash_no_open_session"

    def test_cerrar_sin_caja_abierta(self, cajero: Api):
        """El mismo código que al mover: es la misma situación. Antes eran dos
        frases distintas nada más que por dónde se topaba."""
        cerrar_caja_abierta(cajero)
        respuesta = cajero.call(
            "POST", "/cash/close", {"user_id": cajero.user_id, "closing_amount": 0}
        )
        assert codigo(respuesta, 400) == "cash_no_open_session"

    def test_movimiento_de_tipo_desconocido(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        respuesta = cajero.call(
            "POST",
            "/cash/movement",
            {"user_id": cajero.user_id, "type": "cualquiera", "amount": 100, "reason": "x"},
        )
        assert codigo(respuesta, 400) == "cash_invalid_movement_type"
        cerrar_caja_abierta(cajero)

    def test_movimiento_sin_monto(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        respuesta = cajero.call(
            "POST",
            "/cash/movement",
            {"user_id": cajero.user_id, "type": "entrada", "amount": 0, "reason": "x"},
        )
        assert codigo(respuesta, 400) == "cash_amount_not_positive"
        cerrar_caja_abierta(cajero)

    def test_movimiento_sin_motivo(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        respuesta = cajero.call(
            "POST",
            "/cash/movement",
            {"user_id": cajero.user_id, "type": "entrada", "amount": 100, "reason": "  "},
        )
        assert codigo(respuesta, 400) == "cash_missing_reason"
        cerrar_caja_abierta(cajero)

    def test_sacar_mas_efectivo_del_que_hay(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        estado, cuerpo = cajero.call(
            "POST",
            "/cash/movement",
            {"user_id": cajero.user_id, "type": "salida", "amount": 5000, "reason": "prueba"},
        )
        assert codigo((estado, cuerpo), 400) == "cash_insufficient"
        # La cifra va como número: el símbolo de moneda lo pone el POS.
        assert cuerpo["detail"]["available"] == 1000.0
        cerrar_caja_abierta(cajero)

    def test_cerrar_con_un_conteo_negativo(self, cajero: Api):
        cerrar_caja_abierta(cajero)
        cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 1000})
        respuesta = cajero.call(
            "POST", "/cash/close", {"user_id": cajero.user_id, "closing_amount": -5}
        )
        assert codigo(respuesta, 400) == "cash_counted_negative"
        cerrar_caja_abierta(cajero)

    def test_la_caja_de_otro(self, api: Api, cajero: Api):
        """Un cajero no puede espiar la caja de nadie más. Cuatro códigos, uno
        por operación, porque son cuatro frases distintas."""
        ajeno = api.user_id  # type: ignore[attr-defined]
        assert codigo(cajero.call("GET", f"/cash/current?user_id={ajeno}"), 403) == (
            "cash_read_not_yours"
        )
        assert codigo(
            cajero.call("POST", "/cash/open", {"user_id": ajeno, "opening_amount": 0}), 403
        ) == "cash_open_not_yours"
        assert codigo(
            cajero.call(
                "POST",
                "/cash/movement",
                {"user_id": ajeno, "type": "entrada", "amount": 1, "reason": "x"},
            ),
            403,
        ) == "cash_movement_not_yours"
        assert codigo(
            cajero.call("POST", "/cash/close", {"user_id": ajeno, "closing_amount": 0}), 403
        ) == "cash_close_not_yours"

    def test_turno_que_no_existe(self, api: Api):
        assert codigo(api.call("GET", "/cash/session/999999"), 404) == "cash_session_not_found"

    def test_turno_de_otro(self, api: Api, cajero: Api):
        cerrar_caja_abierta(cajero)
        turno = cajero.ok("POST", "/cash/open", {"user_id": cajero.user_id, "opening_amount": 500})
        otro = Api(api.base)
        # Un tercer cajero, para que ni sea el dueño ni sea administrador.
        marca = marca_unica()
        persona = {
            "name": "Tercero",
            "lastName": "Curioso",
            "secondName": marca,
            "identification": f"8{marca}",
            "birth_date": "1995-05-05",
            "telephone": "80000000",
            "email": f"curioso.{marca}@pruebas.ventasys.cr",
            "password": "prueba123",
        }
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})
        entrar(otro, persona["email"], persona["password"], aceptando_invitaciones=True)
        assert codigo(otro.call("GET", f"/cash/session/{turno['id']}"), 403) == (
            "cash_session_not_yours"
        )
        cerrar_caja_abierta(cajero)


@pytest.mark.characterization
class TestEntradas:
    def _entrada(self, api: Api, lineas: list[dict], **cambios) -> dict:
        cuerpo = {
            "document_number": f"F{marca_unica()}",
            "supplier": "Proveedor de pruebas",
            "source": "manual",
            "user_id": api.user_id,  # type: ignore[attr-defined]
            "notes": None,
            "lines": lineas,
        }
        cuerpo.update(cambios)
        return cuerpo

    def test_sin_lineas(self, api: Api):
        respuesta = api.call("POST", "/inventory/entry", self._entrada(api, []))
        assert codigo(respuesta, 400) == "empty_entry"

    def test_origen_que_no_existe(self, api: Api, producto):
        p = producto("Origen", 1000, 1)
        cuerpo = self._entrada(
            api,
            [{"id_product": p["id_product"], "quantity": 1, "unit_cost": 500}],
            source="regalo",
        )
        assert codigo(api.call("POST", "/inventory/entry", cuerpo), 400) == (
            "invalid_entry_source"
        )

    def test_documento_ya_cargado(self, api: Api, producto):
        p = producto("Documento", 1000, 1)
        linea = [{"id_product": p["id_product"], "quantity": 1, "unit_cost": 500}]
        primera = self._entrada(api, linea)
        api.ok("POST", "/inventory/entry", primera)

        estado, cuerpo = api.call(
            "POST",
            "/inventory/entry",
            self._entrada(api, linea, document_number=primera["document_number"]),
        )
        assert codigo((estado, cuerpo), 400) == "duplicate_document"
        # La fecha va en ISO: el día y el mes no van en el mismo orden en todos
        # los idiomas, así que el formato lo pone el POS.
        assert "T" in cuerpo["detail"]["loaded_at"]

    def test_cantidad_o_costo_invalidos(self, api: Api, producto):
        p = producto("Línea mala", 1000, 1)
        cuerpo = self._entrada(api, [{"id_product": p["id_product"], "quantity": 0, "unit_cost": 1}])
        estado, respuesta = api.call("POST", "/inventory/entry", cuerpo)
        assert codigo((estado, respuesta), 400) == "invalid_entry_line"
        assert respuesta["detail"]["line"] == 1

    def test_producto_que_no_existe(self, api: Api):
        cuerpo = self._entrada(api, [{"id_product": 999999, "quantity": 1, "unit_cost": 1}])
        assert codigo(api.call("POST", "/inventory/entry", cuerpo), 404) == (
            "entry_product_not_found"
        )

    def test_producto_nuevo_sin_codigo_de_barras(self, api: Api, categoria: int):
        cuerpo = self._entrada(
            api,
            [
                {
                    "quantity": 1,
                    "unit_cost": 500,
                    "new_product": {
                        "name": "Sin código",
                        "description": "",
                        "price": 1000,
                        "barcode": "",
                        "category_id": categoria,
                    },
                }
            ],
        )
        assert codigo(api.call("POST", "/inventory/entry", cuerpo), 400) == (
            "entry_missing_barcode"
        )

    def test_producto_nuevo_con_un_codigo_que_ya_existe(self, api: Api, producto, categoria: int):
        p = producto("Ya está", 1000, 1)
        cuerpo = self._entrada(
            api,
            [
                {
                    "quantity": 1,
                    "unit_cost": 500,
                    "new_product": {
                        "name": "Repetido",
                        "description": "",
                        "price": 1000,
                        "barcode": p["barcode"],
                        "category_id": categoria,
                    },
                }
            ],
        )
        assert codigo(api.call("POST", "/inventory/entry", cuerpo), 400) == "barcode_taken"

    def test_linea_que_no_dice_que_producto(self, api: Api):
        cuerpo = self._entrada(api, [{"quantity": 1, "unit_cost": 500}])
        assert codigo(api.call("POST", "/inventory/entry", cuerpo), 400) == (
            "entry_line_without_product"
        )

    def test_entrada_que_no_existe(self, api: Api):
        assert codigo(api.call("GET", "/inventory/entry/999999"), 404) == "entry_not_found"

    def test_anular_dos_veces(self, api: Api, producto):
        p = producto("Anulada", 1000, 1)
        entrada = api.ok(
            "POST",
            "/inventory/entry",
            self._entrada(api, [{"id_product": p["id_product"], "quantity": 2, "unit_cost": 500}]),
        )
        api.ok("POST", f"/inventory/entry/{entrada['id_entry']}/cancel")
        respuesta = api.call("POST", f"/inventory/entry/{entrada['id_entry']}/cancel")
        assert codigo(respuesta, 400) == "entry_already_cancelled"

    def test_anular_lo_que_ya_se_vendio(self, api: Api, producto):
        """Anular devolvería el inventario a negativo: parte ya salió por caja."""
        p = producto("Entró y salió", 1000, 0)
        entrada = api.ok(
            "POST",
            "/inventory/entry",
            self._entrada(api, [{"id_product": p["id_product"], "quantity": 3, "unit_cost": 500}]),
        )
        api.ok("POST", "/sales/add_sale", venta(api, [(p, 2)]))

        estado, cuerpo = api.call("POST", f"/inventory/entry/{entrada['id_entry']}/cancel")
        assert codigo((estado, cuerpo), 400) == "entry_cannot_cancel"
        assert cuerpo["detail"]["available"] == 1 and cuerpo["detail"]["added"] == 3


@pytest.mark.characterization
class TestPersonasYUsuarios:
    def test_cedula_repetida(self, api: Api):
        marca = marca_unica()
        persona = {
            "name": "Doble",
            "lastName": "Cédula",
            "secondName": marca,
            "identification": f"7{marca}",
            "birth_date": "1990-01-01",
            "telephone": "80000000",
            "email": f"doble.{marca}@pruebas.ventasys.cr",
            "password": "prueba123",
        }
        api.ok("POST", "/persons/register", persona)
        otra = dict(persona, email=f"otro.{marca}@pruebas.ventasys.cr")
        assert codigo(api.call("POST", "/persons/register", otra), 400) == (
            "person_identification_taken"
        )

    def test_correo_repetido(self, api: Api):
        marca = marca_unica()
        persona = {
            "name": "Doble",
            "lastName": "Correo",
            "secondName": marca,
            "identification": f"6{marca}",
            "birth_date": "1990-01-01",
            "telephone": "80000000",
            "email": f"correo.{marca}@pruebas.ventasys.cr",
            "password": "prueba123",
        }
        api.ok("POST", "/persons/register", persona)
        otra = dict(persona, identification=f"5{marca}")
        assert codigo(api.call("POST", "/persons/register", otra), 400) == "email_taken"

    def test_editar_los_datos_de_otro(self, api: Api, cajero: Api):
        respuesta = cajero.call("PUT", "/persons/update/1", {"name": "Nadie"})
        assert codigo(respuesta, 403) == "person_not_yours"

    def test_rol_que_no_existe(self, api: Api):
        respuesta = api.call(
            "POST", "/users/membership", {"email": "admin@pruebas.ventasys.cr", "role": "jefe"}
        )
        assert codigo(respuesta, 400) == "invalid_role"

    def test_cuenta_que_no_existe(self, api: Api):
        respuesta = api.call(
            "POST", "/users/membership", {"email": "nadie@pruebas.ventasys.cr", "role": "cajero"}
        )
        assert codigo(respuesta, 404) == "account_not_found"

    def test_usuario_que_no_existe(self, api: Api):
        assert codigo(api.call("PUT", "/users/role/999999", {"role": "cajero"}), 404) == (
            "user_not_found"
        )

    def test_quedarse_sin_administradores(self, api: Api):
        """Degradar al último administrador dejaría la compañía sin quien la
        gestione, y nadie podría volver a otorgar el rol.

        Se prueba en una compañía **propia** y no en la de las demás pruebas por
        eso mismo: si el rechazo fallara, la degradación pasaría, y no habría
        forma de revertirla —el único administrador ya sería cajero—. La
        compañía A tampoco es «la última administradora» de forma fiable: la
        contadora también es admin ahí.
        """
        # Afiliado 4 y no 3: el 3 es de `test_respaldo_compania.py`, que lo
        # borra. Dos pruebas peleándose por la misma compañía fallan según el
        # orden en que corran, que es la peor forma de fallar.
        correo = "solo.admin@pruebas.ventasys.cr"
        bootstrap(
            afiliado=4,
            compania=1,
            nombre="Compañía D de pruebas",
            email=correo,
            password="prueba123",
            rol="admin",
            nombre_persona="Única",
            apellido="Admin",
            cedula="500000001",
        )
        suyo = Api(api.base)
        entrar(suyo, correo, "prueba123")
        yo = suyo.ok("GET", "/users/me")

        respuesta = suyo.call("PUT", f"/users/role/{yo['id_user']}", {"role": "cajero"})
        assert codigo(respuesta, 400) == "last_admin"

    def test_consultar_a_otro(self, api: Api, cajero: Api):
        ajeno = api.user_id  # type: ignore[attr-defined]
        assert codigo(cajero.call("GET", f"/users/{ajeno}"), 403) == "user_not_yours"


@pytest.mark.characterization
class TestClientes:
    def _cliente(self, marca: str) -> dict:
        return {
            "name": "Cliente",
            "last_name": "Prueba",
            "second_name": "Códigos",
            "identification": f"4{marca}",
            "telephone": "80000000",
            "email": f"cliente.{marca}@pruebas.ventasys.cr",
            "address": "San José",
        }

    def test_cedula_repetida(self, api: Api):
        marca = marca_unica()
        api.ok("POST", "/clients/register_client", self._cliente(marca))
        otro = dict(self._cliente(marca_unica()), identification=f"4{marca}")
        assert codigo(api.call("POST", "/clients/register_client", otro), 400) == (
            "client_identification_taken"
        )

    def test_cliente_que_no_existe(self, api: Api):
        respuesta = api.call("PUT", "/clients/update_client/999999", {"name": "Nadie"})
        assert codigo(respuesta, 404) == "client_not_found"


@pytest.mark.characterization
class TestConfiguracion:
    def test_tasa_que_no_es_un_numero(self, api: Api):
        respuesta = api.call("PUT", "/settings/", {"data": {"impuesto": {"tasa": "mucho"}}})
        assert codigo(respuesta, 400) == "tax_rate_not_a_number"

    def test_tasa_fuera_de_rango(self, api: Api):
        """El 13 % es 0,13, no 13."""
        respuesta = api.call("PUT", "/settings/", {"data": {"impuesto": {"tasa": 13}}})
        assert codigo(respuesta, 400) == "tax_rate_out_of_range"

    def test_configuracion_demasiado_grande(self, api: Api):
        respuesta = api.call("PUT", "/settings/", {"data": {"relleno": "x" * 25_000}})
        assert codigo(respuesta, 400) == "settings_too_large"
