"""Contabilidad contra el stack de verdad (F11).

**Cada clase da de alta su propia compañía.** Activar contabilidad cambia lo que
pasa en cada venta de esa compañía —desde entonces deja asiento—, y hacerlo sobre
la del resto de la batería se lo cambiaría a todas. Es la lección de F3 escrita
en `CLAUDE.md`: la salida no es restaurar mejor, es no tocar lo que otros usan.

Lo que se prueba acá es lo que solo se puede probar contra MySQL: que el catálogo
se siembre entero, que el único de (compañía, código) no reviente, que activar
dos veces responda con código y que una apertura descuadrada no deje nada a
medias.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.chart import CHART, default_mapping

from .conftest import Api, bootstrap, entrar, marca_unica

pytestmark = pytest.mark.characterization

HOY = date.today()
#: Lo que se activa: el primer día de este mes. Las ventas de la batería son de
#: hoy, así que caen dentro y el periodo existe.
INICIO = HOY.replace(day=1).isoformat()


def compania_propia(api: Api, etiqueta: str, *, modulos: str | None = None) -> Api:
    """Una compañía nueva, con su plan y su administrador."""
    marca = marca_unica()
    correo = f"{etiqueta}.{marca}@pruebas.ventasys.cr"
    opciones = {
        "afiliado": int(marca[-6:]),
        "compania": 1,
        "nombre": f"Compañía {etiqueta}",
        "email": correo,
        "password": "prueba123",
        "rol": "admin",
        "nombre_persona": "Conta",
        "apellido": "Bilidad",
        "plan": f"Plan {etiqueta} {marca}",
        "plan_max_usuarios": -1,
    }
    if modulos is not None:
        opciones["plan_modulos"] = modulos

    bootstrap(**opciones)
    cliente = Api(api.base)
    entrar(cliente, correo, "prueba123")
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    return cliente


class TestAntesDeActivar:
    @pytest.fixture(scope="class")
    def sin_activar(self, api: Api) -> Api:
        return compania_propia(api, "sin-activar", modulos="accounting")

    def test_el_estado_dice_que_no(self, sin_activar: Api):
        estado = sin_activar.ok("GET", "/accounting")

        assert estado["active"] is False
        assert estado["start_date"] is None

    def test_pero_ya_ofrece_la_plantilla_entera(self, sin_activar: Api):
        # Es lo que la pantalla de activación necesita para pedir los saldos
        # iniciales: antes de activar no hay ninguna cuenta que listar.
        estado = sin_activar.ok("GET", "/accounting")

        assert len(estado["chart"]) == len(CHART)
        assert {c["code"] for c in estado["chart"]} == {p.code for p in CHART}
        assert "commerce" in estado["templates"]


class TestActivar:
    @pytest.fixture(scope="class")
    def activada(self, api: Api) -> Api:
        cliente = compania_propia(api, "activa", modulos="accounting")
        cliente.activacion = cliente.ok(  # type: ignore[attr-defined]
            "POST",
            "/accounting/activate",
            {
                "template": "commerce",
                "start_date": INICIO,
                "description": "Saldos iniciales",
                "opening": [
                    {"account_code": "1.1.01", "debit": 100000, "credit": 0},
                    {"account_code": "1.2.01", "debit": 50000, "credit": 0},
                    {"account_code": "3.1.01", "debit": 0, "credit": 150000},
                ],
            },
        )
        return cliente

    def test_siembra_la_plantilla_completa(self, activada: Api):
        assert activada.activacion["accounts_created"] == len(CHART)  # type: ignore[attr-defined]

    def test_y_el_mapeo_completo(self, activada: Api):
        # La verificación de T-1107: ninguna fila falta. Un papel sin cuenta no
        # rompe nada —cae en 1.9.99— pero le deja al contador un saldo en rojo el
        # primer día por algo que el sistema sabía desde antes de empezar.
        assert activada.activacion["mappings_created"] == len(default_mapping())  # type: ignore[attr-defined]

    def test_deja_el_asiento_de_apertura(self, activada: Api):
        assert activada.activacion["opening_entry_id"] is not None  # type: ignore[attr-defined]

    def test_el_estado_queda_activo_con_su_fecha(self, activada: Api):
        estado = activada.ok("GET", "/accounting")

        assert estado["active"] is True
        assert estado["start_date"] == INICIO
        assert estado["template"] == "commerce"

    def test_activar_dos_veces_responde_codigo(self, activada: Api):
        # La segunda vez volvería a sembrar sobre un libro con movimiento y
        # podría cambiar el mapeo bajo los asientos que ya existen (RN-62).
        estado, cuerpo = activada.call(
            "POST", "/accounting/activate", {"start_date": INICIO}
        )

        assert estado == 400, cuerpo
        assert cuerpo["detail"]["code"] == "accounting_already_active"


class TestLaAperturaQueNoCuadra:
    @pytest.fixture(scope="class")
    def descuadrada(self, api: Api) -> Api:
        return compania_propia(api, "descuadrada", modulos="accounting")

    def test_responde_con_las_dos_sumas(self, descuadrada: Api):
        estado, cuerpo = descuadrada.call(
            "POST",
            "/accounting/activate",
            {
                "start_date": INICIO,
                "opening": [
                    {"account_code": "1.1.01", "debit": 100000, "credit": 0},
                    {"account_code": "3.1.01", "debit": 0, "credit": 90000},
                ],
            },
        )

        assert estado == 400, cuerpo
        assert cuerpo["detail"]["code"] == "invalid_opening_balance"
        # Las dos cifras, porque quien lo escribió necesita ver por cuánto.
        assert cuerpo["detail"]["debits"] == "100000.00"
        assert cuerpo["detail"]["credits"] == "90000.00"

    def test_y_no_deja_nada_a_medias(self, descuadrada: Api):
        # Un libro no arranca descuadrado, y reintentar tiene que ser seguro: si
        # las cuentas hubieran quedado escritas, el segundo intento chocaría
        # contra el único de (compañía, código).
        assert descuadrada.ok("GET", "/accounting")["active"] is False

        segundo = descuadrada.ok(
            "POST",
            "/accounting/activate",
            {
                "start_date": INICIO,
                "opening": [
                    {"account_code": "1.1.01", "debit": 90000, "credit": 0},
                    {"account_code": "3.1.01", "debit": 0, "credit": 90000},
                ],
            },
        )

        assert segundo["accounts_created"] == len(CHART)


class TestElCuerpoMalFormado:
    @pytest.fixture(scope="class")
    def cliente(self, api: Api) -> Api:
        return compania_propia(api, "mal-formada", modulos="accounting")

    def test_una_plantilla_que_no_existe(self, cliente: Api):
        estado, _ = cliente.call(
            "POST", "/accounting/activate", {"template": "restaurante", "start_date": INICIO}
        )

        # 422: la pantalla arma el formulario con la plantilla que el servidor le
        # dio, así que esto no es un «no» del negocio sino un cuerpo mal formado.
        assert estado == 422

    def test_un_saldo_inicial_contra_una_cuenta_inventada(self, cliente: Api):
        estado, _ = cliente.call(
            "POST",
            "/accounting/activate",
            {
                "start_date": INICIO,
                "opening": [{"account_code": "9.9.99", "debit": 1, "credit": 0}],
            },
        )

        assert estado == 422


def activar(cliente: Api) -> dict:
    """Activa la contabilidad de esa compañía y devuelve la respuesta."""
    return cliente.ok(
        "POST",
        "/accounting/activate",
        {"template": "commerce", "start_date": INICIO},
    )


def cuenta_por_codigo(cliente: Api, codigo: str) -> dict:
    return next(c for c in cliente.ok("GET", "/accounting/accounts") if c["code"] == codigo)


class TestElCatalogo:
    """RF-48 y RN-64: qué se le puede hacer a una cuenta."""

    @pytest.fixture(scope="class")
    def cliente(self, api: Api) -> Api:
        cliente = compania_propia(api, "catalogo", modulos="accounting")
        activar(cliente)
        return cliente

    def test_el_catalogo_sale_ordenado_por_codigo(self, cliente: Api):
        codigos = [c["code"] for c in cliente.ok("GET", "/accounting/accounts")]

        assert codigos == sorted(codigos)
        assert len(codigos) == len(CHART)

    def test_una_cuenta_del_contador_se_crea_y_no_es_de_sistema(self, cliente: Api):
        # Si el usuario pudiera marcarlas de sistema, se estaría dando una cuenta
        # que después no puede borrar.
        nueva = cliente.ok(
            "POST",
            "/accounting/accounts",
            {"code": "6.9.03", "name": "Papelería", "kind": "expense"},
        )

        assert nueva["is_system"] is False
        assert nueva["is_active"] is True

    def test_dos_cuentas_con_el_mismo_codigo_no(self, cliente: Api):
        cliente.ok(
            "POST",
            "/accounting/accounts",
            {"code": "6.9.04", "name": "Limpieza", "kind": "expense"},
        )
        estado, cuerpo = cliente.call(
            "POST",
            "/accounting/accounts",
            {"code": "6.9.04", "name": "Otra", "kind": "expense"},
        )

        assert estado == 400, cuerpo
        assert cuerpo["detail"]["code"] == "account_code_taken"

    def test_borrar_una_de_sistema_responde_codigo(self, cliente: Api):
        # La verificación de T-1108: borrar 1.1.01 → código.
        caja = cuenta_por_codigo(cliente, "1.1.01")
        estado, cuerpo = cliente.call("DELETE", f"/accounting/accounts/{caja['id']}")

        assert estado == 400, cuerpo
        assert cuerpo["detail"]["code"] == "account_is_system"

    def test_desactivar_una_de_sistema_tampoco(self, cliente: Api):
        # Es peor que borrarla: el mapeo la seguiría apuntando y el asiento se
        # escribiría contra una cuenta que la pantalla ya no ofrece.
        caja = cuenta_por_codigo(cliente, "1.1.01")
        estado, cuerpo = cliente.call(
            "PUT", f"/accounting/accounts/{caja['id']}", {"is_active": False}
        )

        assert estado == 400, cuerpo
        assert cuerpo["detail"]["code"] == "account_is_system"

    def test_pero_renombrarla_sí(self, cliente: Api):
        # El mapeo apunta al id, no al nombre.
        caja = cuenta_por_codigo(cliente, "1.1.01")
        renombrada = cliente.ok(
            "PUT", f"/accounting/accounts/{caja['id']}", {"name": "Caja general"}
        )

        assert renombrada["name"] == "Caja general"
        assert renombrada["is_system"] is True

    def test_una_cuenta_nueva_sin_movimientos_se_va(self, cliente: Api):
        nueva = cliente.ok(
            "POST",
            "/accounting/accounts",
            {"code": "6.9.05", "name": "Efímera", "kind": "expense"},
        )
        cliente.ok("DELETE", f"/accounting/accounts/{nueva['id']}")

        assert all(
            c["id"] != nueva["id"] for c in cliente.ok("GET", "/accounting/accounts")
        )

    def test_una_cuenta_que_no_existe(self, cliente: Api):
        estado, cuerpo = cliente.call("DELETE", "/accounting/accounts/999999")

        assert estado == 404, cuerpo
        assert cuerpo["detail"]["code"] == "account_not_found"


class TestElMapeo:
    @pytest.fixture(scope="class")
    def cliente(self, api: Api) -> Api:
        cliente = compania_propia(api, "mapeo", modulos="accounting")
        activar(cliente)
        return cliente

    def test_lista_todos_los_papeles_con_su_cuenta(self, cliente: Api):
        filas = cliente.ok("GET", "/accounting/mappings")["mappings"]
        puestos = [f for f in filas if not f["unmapped_on_purpose"]]

        assert len(puestos) == len(default_mapping())
        assert all(f["account_id"] is not None for f in puestos)

    def test_los_que_caen_en_por_clasificar_a_proposito_van_marcados(self, cliente: Api):
        # No se pintan en rojo: no están mal, es que el sistema no sabe.
        filas = cliente.ok("GET", "/accounting/mappings")["mappings"]
        sueltos = [f for f in filas if f["unmapped_on_purpose"]]

        assert {(f["event"], f["role"]) for f in sueltos} == {
            ("cash_movement", "counterpart"),
            ("supplier_payment", "unclassified"),
            ("sale", "unclassified"),
        }
        assert all(f["account_id"] is None for f in sueltos)

    def test_cambiar_una_cuenta_del_mapeo(self, cliente: Api):
        bancos = cuenta_por_codigo(cliente, "1.1.02")
        filas = cliente.ok(
            "PUT",
            "/accounting/mappings",
            {"mappings": [{"event": "sale", "role": "cash", "account_id": bancos["id"]}]},
        )["mappings"]

        fila = next(f for f in filas if (f["event"], f["role"]) == ("sale", "cash"))
        assert fila["account_id"] == bancos["id"]

    def test_contra_una_cuenta_que_no_existe(self, cliente: Api):
        estado, cuerpo = cliente.call(
            "PUT",
            "/accounting/mappings",
            {"mappings": [{"event": "sale", "role": "cash", "account_id": 999999}]},
        )

        assert estado == 404, cuerpo
        assert cuerpo["detail"]["code"] == "account_not_found"


class TestNoSeVeElLibroAjeno:
    """Dos compañías con contabilidad, cada una con la suya (RNF-1).

    No usa la compañía B de `test_aislamiento.py` a propósito: activarle la
    contabilidad le cambiaría el mundo a toda esa batería.
    """

    @pytest.fixture(scope="class")
    def dos(self, api: Api) -> tuple[Api, Api]:
        una = compania_propia(api, "libro-a", modulos="accounting")
        otra = compania_propia(api, "libro-b", modulos="accounting")
        activar(una)
        activar(otra)
        return una, otra

    def test_no_se_puede_borrar_una_cuenta_de_la_otra(self, dos):
        una, otra = dos
        ajena = cuenta_por_codigo(otra, "6.9.02")

        estado, _ = una.call("DELETE", f"/accounting/accounts/{ajena['id']}")

        # 404 y no 403: un 403 confirmaría que la cuenta existe.
        assert estado == 404

    def test_ni_renombrarla(self, dos):
        una, otra = dos
        ajena = cuenta_por_codigo(otra, "6.9.02")

        estado, _ = una.call(
            "PUT", f"/accounting/accounts/{ajena['id']}", {"name": "Secuestrada"}
        )

        assert estado == 404

    def test_ni_reclasificar_un_asiento_suyo(self, dos):
        una, otra = dos
        # El asiento de apertura de la otra no existe —no dictó saldos— así que
        # se usa cualquier id: lo que importa es que no se pueda entrar.
        propia = cuenta_por_codigo(una, "6.9.02")

        estado, _ = una.call(
            "POST", "/accounting/entries/999999/reclassify", {"account_id": propia["id"]}
        )

        assert estado == 404

    def test_cada_una_ve_su_propio_catalogo_completo(self, dos):
        # La contraprueba: sin esto, un 404 en todo también pasaría el examen.
        una, otra = dos

        assert len(una.ok("GET", "/accounting/accounts")) == len(CHART)
        assert len(otra.ok("GET", "/accounting/accounts")) == len(CHART)


class TestSinElModuloEnElPlan:
    @pytest.fixture(scope="class")
    def sin_modulo(self, api: Api) -> Api:
        return compania_propia(api, "sin-conta")

    def test_activar_responde_403_con_el_codigo(self, sin_modulo: Api):
        # RN-50: un módulo apagado impide **escribir**.
        estado, cuerpo = sin_modulo.call(
            "POST", "/accounting/activate", {"start_date": INICIO}
        )

        assert estado == 403, cuerpo
        assert cuerpo["detail"]["code"] == "module_not_in_plan"
        assert cuerpo["detail"]["module"] == "accounting"

    def test_pero_consultar_el_estado_sí(self, sin_modulo: Api):
        # La otra mitad: los libros de una compañía que bajó de plan siguen
        # siendo su respaldo ante Hacienda.
        assert sin_modulo.ok("GET", "/accounting")["active"] is False
