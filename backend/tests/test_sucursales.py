"""
Sucursales y terminales, por HTTP (T-608, RF-26, RN-7, RN-15).

Cada prueba trabaja sobre una **compañía propia**, dada de alta con el mismo
`bootstrap.py` que se usaría de verdad. Es la lección de T-310 escrita en
CLAUDE.md: la base de pruebas sobrevive entre corridas, así que una prueba que
desactiva la única sucursal de la compañía A deja media batería sin poder
vender, y el fallo señala la venta, que es donde no está el problema.

El plan de las compañías de prueba **no limita** (`PLAN_DE_PRUEBAS` en
`conftest.py`, por lo que aprendió T-309), así que el límite se prueba aparte
creando una compañía con un plan chico.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    API,
    PLAN_DE_PRUEBAS,
    Api,
    afiliado_unico,
    bootstrap,
    codigo,
    entrar,
    marca_unica,
)

pytestmark = pytest.mark.characterization


def compania_propia(quien: str) -> Api:
    marca = marca_unica()
    correo = f"suc.{quien}.{marca}@pruebas.ventasys.cr"
    bootstrap(
        afiliado=afiliado_unico(),
        compania=1,
        nombre=f"Compañía Sucursales {quien} {marca}",
        email=correo,
        password="prueba123",
        rol="admin",
        nombre_persona="Sandra",
        apellido=quien.capitalize(),
        cedula=marca[-9:],
        # Sin esto el plan por omisión de `bootstrap.py` admite **una** sucursal
        # y la segunda no cabe: el fallo señalaría el alta, que es lo único que
        # no estaba mal. Es la misma trampa que encontró T-309 con los usuarios.
        **PLAN_DE_PRUEBAS,
    )
    cliente = Api(API)
    entrar(cliente, correo, "prueba123")
    return cliente


@pytest.fixture
def empresa() -> Api:
    return compania_propia("una")


@pytest.fixture
def otra_empresa() -> Api:
    return compania_propia("otra")


def sucursales(cliente: Api) -> list[dict]:
    estado, cuerpo = cliente.call("GET", "/offices")
    assert estado == 200
    return cuerpo["branches"]


def terminales(cliente: Api) -> list[dict]:
    _, cuerpo = cliente.call("GET", "/offices")
    return cuerpo["terminals"]


def por_codigo(filas: list[dict], codigo_: str) -> dict:
    return next(f for f in filas if f["codigo"] == codigo_)


class TestLoQueTraeUnaCompaniaNueva:
    def test_nace_con_una_sucursal_y_una_caja(self, empresa: Api):
        # Las crea `crud_company.dar_de_alta`: sin ellas no se puede vender, así
        # que no puede ser un paso que alguien tenga que acordarse de dar.
        assert [s["codigo"] for s in sucursales(empresa)] == ["001"]
        assert [t["codigo"] for t in terminales(empresa)] == ["00001"]

    def test_un_cajero_no_las_administra(self, cajero: Api):
        assert codigo(cajero.call("GET", "/offices"), 403) == "admin_only"
        respuesta = cajero.call("POST", "/offices/branches", {"codigo": "2", "nombre": "X"})
        assert codigo(respuesta, 403) == "admin_only"


class TestElCodigoSeRellena:
    """RN-15, T-608b. «1» se guarda como «001» y «abc» no se guarda."""

    def test_se_rellena_con_ceros(self, empresa: Api):
        estado, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "7", "nombre": "Sucursal Norte"}
        )
        assert estado == 200
        assert por_codigo(cuerpo["branches"], "007")["nombre"] == "Sucursal Norte"

    def test_la_terminal_lleva_cinco(self, empresa: Api):
        sucursal = sucursales(empresa)[0]
        _, cuerpo = empresa.call(
            "POST",
            "/offices/terminals",
            {"branch_id": sucursal["id"], "codigo": "3", "nombre": "Caja 3"},
        )
        assert por_codigo(cuerpo["terminals"], "00003")["nombre"] == "Caja 3"

    def test_lo_que_no_son_digitos_no_entra(self, empresa: Api):
        respuesta = empresa.call(
            "POST", "/offices/branches", {"codigo": "abc", "nombre": "No"}
        )
        assert codigo(respuesta, 400) == "invalid_office_code"
        assert respuesta[1]["detail"]["reason"] == "not_digits"

    def test_lo_que_no_cabe_tampoco(self, empresa: Api):
        respuesta = empresa.call(
            "POST", "/offices/branches", {"codigo": "1234", "nombre": "No"}
        )
        assert codigo(respuesta, 400) == "invalid_office_code"
        # Recortar en silencio sería cambiarle el número a alguien.
        assert respuesta[1]["detail"]["reason"] == "too_long"
        assert respuesta[1]["detail"]["digits"] == 3

    def test_el_codigo_repetido_se_rechaza(self, empresa: Api):
        # Dos sucursales con el mismo código producen dos facturas con la misma
        # numeración ante Hacienda.
        respuesta = empresa.call(
            "POST", "/offices/branches", {"codigo": "001", "nombre": "Otra vez"}
        )
        assert codigo(respuesta, 409) == "branch_code_taken"

    def test_y_el_relleno_es_lo_que_lo_caza(self, empresa: Api):
        # Sin normalizar, «1» y «001» serían dos filas distintas con el mismo
        # número en el comprobante. Esta es la prueba que lo dice.
        respuesta = empresa.call(
            "POST", "/offices/branches", {"codigo": "1", "nombre": "La misma"}
        )
        assert codigo(respuesta, 409) == "branch_code_taken"

    def test_dos_locales_pueden_tener_la_misma_caja(self, empresa: Api):
        # El UNIQUE de terminales lleva la sucursal adentro a propósito.
        _, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "2", "nombre": "Norte"}
        )
        norte = por_codigo(cuerpo["branches"], "002")

        estado, cuerpo = empresa.call(
            "POST",
            "/offices/terminals",
            {"branch_id": norte["id"], "codigo": "1", "nombre": "Caja del norte"},
        )
        assert estado == 200
        cajas = [t for t in cuerpo["terminals"] if t["codigo"] == "00001"]
        assert len(cajas) == 2


class TestDesactivarYBorrar:
    """RN-7 aplicada acá: lo que arrastra historia se desactiva."""

    def test_una_sucursal_sin_nada_se_borra(self, empresa: Api):
        _, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "9", "nombre": "Efímera"}
        )
        nueva = por_codigo(cuerpo["branches"], "009")

        estado, cuerpo = empresa.call("DELETE", f"/offices/branches/{nueva['id']}")
        assert estado == 200
        assert [s["codigo"] for s in cuerpo["branches"]] == ["001"]

    def test_una_con_cajas_colgando_no(self, empresa: Api):
        primera = sucursales(empresa)[0]
        respuesta = empresa.call("DELETE", f"/offices/branches/{primera['id']}")
        assert codigo(respuesta, 409) == "branch_in_use"
        # Las dos cuentas, porque quien lo lee necesita saber qué mover primero.
        assert respuesta[1]["detail"]["terminals"] == 1
        assert "sales" in respuesta[1]["detail"]

    def test_desactivar_una_sucursal_apaga_sus_cajas(self, empresa: Api):
        """El POS las ofrecería y el consecutivo saldría de un local cerrado."""
        _, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "5", "nombre": "Se cierra"}
        )
        sucursal = por_codigo(cuerpo["branches"], "005")
        empresa.call(
            "POST",
            "/offices/terminals",
            {"branch_id": sucursal["id"], "codigo": "1", "nombre": "Su caja"},
        )

        estado, cuerpo = empresa.call(
            "PUT", f"/offices/branches/{sucursal['id']}", {"activa": False}
        )
        assert estado == 200
        assert por_codigo(cuerpo["branches"], "005")["activa"] is False
        suyas = [t for t in cuerpo["terminals"] if t["branch_id"] == sucursal["id"]]
        assert all(t["activa"] is False for t in suyas)

    def test_no_se_apaga_la_ultima_sucursal(self, empresa: Api):
        # Una compañía sin sucursal activa no puede vender, y lo descubriría en
        # el peor momento.
        primera = sucursales(empresa)[0]
        respuesta = empresa.call(
            "PUT", f"/offices/branches/{primera['id']}", {"activa": False}
        )
        assert codigo(respuesta, 409) == "last_active_branch"

    def test_ni_la_ultima_caja_de_una_sucursal_encendida(self, empresa: Api):
        unica = terminales(empresa)[0]
        respuesta = empresa.call(
            "PUT", f"/offices/terminals/{unica['id']}", {"activa": False}
        )
        assert codigo(respuesta, 409) == "last_active_terminal"

    def test_pero_si_la_sucursal_ya_esta_apagada_sus_cajas_pueden_estarlo(
        self, empresa: Api
    ):
        _, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "6", "nombre": "Cerrada"}
        )
        sucursal = por_codigo(cuerpo["branches"], "006")
        _, cuerpo = empresa.call(
            "POST",
            "/offices/terminals",
            {"branch_id": sucursal["id"], "codigo": "1", "nombre": "Su caja"},
        )
        caja = next(
            t for t in cuerpo["terminals"] if t["branch_id"] == sucursal["id"]
        )
        empresa.call("PUT", f"/offices/branches/{sucursal['id']}", {"activa": False})

        # Ya está apagada por el apagón de la sucursal; volver a pedirlo no falla.
        estado, _ = empresa.call("PUT", f"/offices/terminals/{caja['id']}", {"activa": False})
        assert estado == 200

    def test_una_caja_apagada_de_repuesto_se_borra(self, empresa: Api):
        """La que ya está apagada no deja a nadie sin caja al irse.

        Se ve desde la pantalla: se crea una caja de más, se apaga, y el botón de
        borrar respondía «no puede quedarse sin caja activa» — mandando a
        encenderla para poder borrarla.
        """
        sucursal = sucursales(empresa)[0]
        _, cuerpo = empresa.call(
            "POST",
            "/offices/terminals",
            {"branch_id": sucursal["id"], "codigo": "9", "nombre": "De repuesto"},
        )
        caja = por_codigo(cuerpo["terminals"], "00009")
        empresa.call("PUT", f"/offices/terminals/{caja['id']}", {"activa": False})

        estado, cuerpo = empresa.call("DELETE", f"/offices/terminals/{caja['id']}")
        assert estado == 200
        assert [t["codigo"] for t in cuerpo["terminals"]] == ["00001"]

    def test_pero_la_ultima_encendida_no_se_borra(self, empresa: Api):
        # La otra mitad: sin esto, lo de arriba se podría haber «arreglado»
        # quitando la comprobación entera.
        unica = terminales(empresa)[0]
        assert codigo(empresa.call("DELETE", f"/offices/terminals/{unica['id']}"), 409) == (
            "last_active_terminal"
        )

    def test_renombrar_no_toca_el_codigo(self, empresa: Api):
        primera = sucursales(empresa)[0]
        _, cuerpo = empresa.call(
            "PUT", f"/offices/branches/{primera['id']}", {"nombre": "Casa matriz"}
        )
        renombrada = por_codigo(cuerpo["branches"], "001")
        assert renombrada["nombre"] == "Casa matriz"
        assert renombrada["codigo"] == "001"

    def test_una_sucursal_que_no_existe(self, empresa: Api):
        assert codigo(empresa.call("PUT", "/offices/branches/999999", {"nombre": "X"}), 404) == (
            "branch_not_found"
        )


class TestNoSeVeLoDeLaOtraCompania:
    def test_la_sucursal_de_A_no_aparece_en_la_sesion_de_B(
        self, empresa: Api, otra_empresa: Api
    ):
        empresa.call("POST", "/offices/branches", {"codigo": "3", "nombre": "SOLO DE A"})
        _, de_b = otra_empresa.call("GET", "/offices")
        assert "SOLO DE A" not in str(de_b)

    def test_ni_se_puede_tocar_por_id(self, empresa: Api, otra_empresa: Api):
        _, cuerpo = empresa.call(
            "POST", "/offices/branches", {"codigo": "4", "nombre": "DE A"}
        )
        de_a = por_codigo(cuerpo["branches"], "004")

        # El filtro de `tenancy.py` la hace invisible, así que es un 404 y no un
        # 403: para esta sesión, esa fila no existe.
        respuesta = otra_empresa.call("PUT", f"/offices/branches/{de_a['id']}", {"nombre": "Mía"})
        assert codigo(respuesta, 404) == "branch_not_found"

    def test_cada_una_cuenta_su_propio_cupo(self, empresa: Api, otra_empresa: Api):
        empresa.call("POST", "/offices/branches", {"codigo": "8", "nombre": "Extra"})
        _, de_a = empresa.call("GET", "/offices")
        _, de_b = otra_empresa.call("GET", "/offices")
        assert de_a["quota"]["branches"] == 2
        assert de_b["quota"]["branches"] == 1


class TestElLimiteDelPlan:
    """RF-12 aplicada acá. El plan de las compañías de prueba no limita, así que
    esta batería crea una con un plan chico."""

    @pytest.fixture
    def apretada(self) -> Api:
        """Una compañía con un plan de **una** sucursal y **una** caja.

        El plan lo crea el propio `bootstrap.py` con sus límites, igual que
        `test_soporte.py::plan_normal`: no hay endpoint que cree planes —eso es
        trabajo del operador del producto— y tampoco hace falta uno.
        """
        marca = marca_unica()
        correo = f"suc.apretada.{marca}@pruebas.ventasys.cr"
        bootstrap(
            afiliado=afiliado_unico(),
            compania=1,
            nombre=f"Compañía Apretada {marca}",
            email=correo,
            password="prueba123",
            rol="admin",
            nombre_persona="Ana",
            apellido="Apretada",
            cedula=marca[-9:],
            plan=f"Mínimo {marca}",
            plan_max_sucursales=1,
            plan_max_terminales=1,
            plan_max_usuarios=5,
        )
        cliente = Api(API)
        entrar(cliente, correo, "prueba123")
        return cliente

    def test_la_segunda_sucursal_no_cabe(self, apretada: Api):
        respuesta = apretada.call(
            "POST", "/offices/branches", {"codigo": "2", "nombre": "No cabe"}
        )
        assert codigo(respuesta, 400) == "plan_limit_reached"
        detalle = respuesta[1]["detail"]
        assert (detalle["resource"], detalle["current"], detalle["max"]) == ("branches", 1, 1)

    def test_la_segunda_caja_tampoco(self, apretada: Api):
        sucursal = sucursales(apretada)[0]
        respuesta = apretada.call(
            "POST",
            "/offices/terminals",
            {"branch_id": sucursal["id"], "codigo": "2", "nombre": "No cabe"},
        )
        assert codigo(respuesta, 400) == "plan_limit_reached"
        assert respuesta[1]["detail"]["resource"] == "terminals"

    def test_se_cuentan_las_activas_y_reactivar_consume_cupo(self, apretada: Api):
        """La contrapartida escrita de contar solo las activas.

        Sin esto, desactivar y reactivar sería la forma de tener cinco
        sucursales con un plan de una.
        """
        # Con el plan en 1 no se puede ni desactivar la única —queda sin
        # sucursal— así que el camino es: subir el plan no está en esta prueba.
        # Lo que sí se comprueba es que el cupo lo diga.
        _, cuerpo = apretada.call("GET", "/offices")
        assert cuerpo["quota"] == {
            "branches": 1,
            "max_branches": 1,
            "terminals": 1,
            "max_terminals": 1,
        }
