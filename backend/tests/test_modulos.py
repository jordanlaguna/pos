"""Los módulos que incluye el plan, aplicados en el servidor (T-1002, RN-49, RN-50).

La dependencia se prueba **directa** y no por HTTP, y es a propósito: la primera
ruta que la usa llega con T-1007, y lo que hay que dejar fijado antes de
escribirla es la asimetría —una lectura pasa siempre, una escritura no— porque
es la mitad de la regla que se olvida. Cuando existan las rutas, `test_aislamiento.py`
las cubre por el otro lado.

La consulta del plan se sustituye: lo que se está probando es la regla, no que
SQLAlchemy sepa hacer un `JOIN`. Eso lo prueba la base de verdad, con las rutas.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from app.domain.errors import UnknownModule
from app.domain.modules import Modules
from app.models.model_user import User
from app.utils import auth_dependency
from app.utils.auth_dependency import Sesion, require_module


def peticion(metodo: str, ruta: str = "/purchases") -> Request:
    """Lo mínimo que mira la dependencia: el método y la ruta."""
    return Request({"type": "http", "method": metodo, "path": ruta, "headers": []})


def sesion() -> Sesion:
    return Sesion(user=User(id_user=1, email="a@b.cr"), company_id=7, rol="admin")


@pytest.fixture
def plan(monkeypatch):
    """Fija qué módulos devuelve el plan de la compañía."""

    def con(**modulos: bool):
        monkeypatch.setattr(
            auth_dependency.crud_membership,
            "modulos_de",
            lambda db, company_id: Modules(**modulos),
        )

    return con


class TestLoQueEscribe:
    @pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
    def test_sin_el_modulo_responde_403_con_el_codigo(self, plan, metodo):
        plan(purchases=False)
        with pytest.raises(HTTPException) as excepcion:
            require_module("purchases")(peticion(metodo), sesion(), db=None)

        # 403 y no un redirect ni un 401: el token vale, lo que no está
        # comprado es esto. Es la misma forma que las dos puertas de soporte.
        assert excepcion.value.status_code == 403
        assert excepcion.value.detail["code"] == "module_not_in_plan"
        # El módulo viaja como dato para que el POS arme la frase (RN-30).
        assert excepcion.value.detail["module"] == "purchases"

    @pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
    def test_con_el_modulo_pasa(self, plan, metodo):
        plan(purchases=True)
        assert require_module("purchases")(peticion(metodo), sesion(), db=None).company_id == 7

    def test_cada_modulo_mira_el_suyo(self, plan):
        # Tener contabilidad no da compras. Parece obvio y es justo lo que se
        # rompe cuando alguien resuelve el permiso con un solo booleano.
        plan(accounting=True, purchases=False)
        with pytest.raises(HTTPException):
            require_module("purchases")(peticion("POST"), sesion(), db=None)
        assert require_module("accounting")(peticion("POST"), sesion(), db=None)


class TestLoQueLee:
    @pytest.mark.parametrize("metodo", ["GET", "HEAD", "OPTIONS"])
    def test_pasa_aunque_el_plan_no_lo_incluya(self, plan, metodo):
        # RN-50: apagar un módulo no borra nada, lo deja en solo lectura. Los
        # libros de una compañía que bajó de plan siguen siendo su respaldo ante
        # Hacienda, y las boletas, la prueba de lo pagado.
        plan(purchases=False, accounting=False, payroll=False)
        assert require_module("accounting")(peticion(metodo), sesion(), db=None)

    def test_no_consulta_el_plan_para_leer(self, monkeypatch):
        # Y por eso una lectura no paga la consulta. Si algún día alguien mueve
        # la comprobación antes del `if`, esta prueba lo dice.
        def no_deberia(db, company_id):
            raise AssertionError("una lectura no tiene que consultar el plan")

        monkeypatch.setattr(auth_dependency.crud_membership, "modulos_de", no_deberia)
        assert require_module("payroll")(peticion("GET"), sesion(), db=None)


class TestElNombreDelModulo:
    def test_uno_que_no_existe_revienta_en_vez_de_dar_403(self, plan):
        # `require_module("purchase")`, en singular, es un error de quien escribe
        # la ruta. Un 403 lo disfrazaría de problema del plan del cliente y
        # mandaría a soporte a mirar la suscripción equivocada.
        plan(purchases=True)
        with pytest.raises(UnknownModule):
            require_module("purchase")(peticion("POST"), sesion(), db=None)
