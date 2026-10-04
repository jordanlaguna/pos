"""Los módulos que incluye un plan (T-1002, RN-49 a RN-51, QA-01)."""

import pytest

from app.domain.errors import UnknownModule
from app.domain.modules import BASE, MODULES, PACKAGES, Modules


class TestModules:
    def test_por_omision_no_incluye_ninguno(self):
        # Falla cerrado: un plan del que no se sabe nada no incluye nada. Es lo
        # que devuelve el adaptador cuando la compañía no tiene plan.
        vacio = Modules()
        assert not vacio.includes("purchases")
        assert not vacio.includes("accounting")
        assert not vacio.includes("payroll")

    def test_incluye_el_que_esta_encendido(self):
        solo_compras = Modules(purchases=True)
        assert solo_compras.includes("purchases")
        assert not solo_compras.includes("accounting")

    def test_todos_encendidos(self):
        todos = Modules.of(MODULES)
        assert all(todos.includes(nombre) for nombre in MODULES)

    def test_un_modulo_que_no_existe_revienta(self):
        # En singular, que es el error de dedo real. Devolver False lo
        # convertiría en un 403 que parece un problema del plan del cliente.
        with pytest.raises(UnknownModule) as excepcion:
            Modules(purchases=True).includes("purchase")
        assert excepcion.value.module == "purchase"

    def test_la_factura_electronica_no_es_uno_de_estos(self):
        # Es una bandera del plan desde la 002 y no entró a MODULES: su nombre
        # está en español y nadie la consume todavía.
        with pytest.raises(UnknownModule):
            Modules().includes("factura_electronica")

    def test_es_inmutable(self):
        with pytest.raises(Exception):
            Modules().purchases = True


class TestAsDict:
    def test_devuelve_todos_siempre(self):
        # También los apagados: en JavaScript una clave ausente y una en `false`
        # no se leen igual, y la navegación tiene que poder distinguir «no lo
        # tiene» de «no vino el dato».
        assert Modules(accounting=True).as_dict() == {n: n == "accounting" for n in MODULES}

    def test_las_claves_son_las_de_MODULES(self):
        assert tuple(Modules().as_dict()) == MODULES

    def test_los_valores_son_booleanos(self):
        # El adaptador lee TINYINT(1) y MySQL puede devolver 0/1 enteros.
        de_la_base = Modules(purchases=1, accounting=0, payroll=1)
        assert de_la_base.as_dict() == {n: n in ("purchases", "payroll") for n in MODULES}
        assert all(isinstance(v, bool) for v in de_la_base.as_dict().values())

    def test_un_entero_de_la_base_tambien_sirve_para_includes(self):
        assert Modules(payroll=1).includes("payroll") is True
        assert Modules(payroll=0).includes("payroll") is False


class TestOf:
    def test_enciende_los_nombrados_y_nada_mas(self):
        assert Modules.of(("sales", "clients")).as_dict() == {
            n: n in ("sales", "clients") for n in MODULES
        }

    def test_un_nombre_que_no_existe_revienta(self):
        with pytest.raises(UnknownModule) as excepcion:
            Modules.of(("sales", "ventas"))
        assert excepcion.value.module == "ventas"


class TestLosPaquetes:
    """QA-01: los cuatro que se venden, decididos con el usuario el 2026-10-03."""

    def test_son_los_cuatro(self):
        assert list(PACKAGES) == ["Restaurante", "Comercio", "Comercio con compras", "Completo"]

    def test_todos_son_modulos_que_existen(self):
        for modulos in PACKAGES.values():
            Modules.of(modulos)

    def test_el_restaurante_no_lleva_caja_ni_inventario(self):
        assert set(PACKAGES["Restaurante"]) == {"sales", "invoices", "clients", "users"}

    def test_comercio_lleva_proveedores_y_no_compras(self):
        comercio = set(PACKAGES["Comercio"])
        assert {"cash", "returns", "inventory", "suppliers", "clients", "users"} <= comercio
        assert not comercio & {"purchases", "reports", "accounting", "payroll"}

    def test_el_de_compras_es_comercio_mas_reportes_y_compras(self):
        assert set(PACKAGES["Comercio con compras"]) == set(PACKAGES["Comercio"]) | {"reports", "purchases"}

    def test_completo_es_todo(self):
        assert PACKAGES["Completo"] == MODULES

    def test_ninguno_repite_un_modulo(self):
        for modulos in PACKAGES.values():
            assert len(modulos) == len(set(modulos))


class TestLaBase:
    def test_es_lo_que_el_pos_tuvo_siempre(self):
        # Lo que no se vendía aparte antes de QA-01: sin compras, proveedores,
        # contabilidad ni planilla, que eran los módulos de F10 a F12.
        assert set(BASE) == set(MODULES) - {"purchases", "suppliers", "accounting", "payroll"}
