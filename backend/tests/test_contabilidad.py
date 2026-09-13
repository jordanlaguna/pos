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
