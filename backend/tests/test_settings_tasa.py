"""Dónde busca la tasa de impuesto la configuración.

`tasa_declarada` es el único lector, y existe por un defecto: la validación de
`save_settings` miraba `impuesto.tasa` —la forma de antes de T-113— mientras el
POS escribía `tax.rate`. Una tasa fuera de rango pasaba el control sin que nada
avisara y se perdía después en el respaldo de `get_tax_rate`, así que el dueño
configuraba 500 %, la pantalla se lo mostraba y el servidor cobraba 13 %.

Se prueba acá, sobre la función pura, y no por el API: la configuración es de la
compañía y la comparten todas las pruebas de la corrida. Una prueba que guarde
una tasa se la cambia a las demás —pasó, y tumbó diecinueve—.

Importa cuando F5 llegue: RN-9 convierte esta tasa en el valor por omisión de
todo producto nuevo, así que un silencio acá dejaría de ser una fila mal
configurada para ser el impuesto de un catálogo entero.
"""

from __future__ import annotations

import pytest

from app.services.crud_settings import tasa_declarada


class TestLaEncuentra:
    def test_en_la_forma_nueva(self):
        assert tasa_declarada({"tax": {"rate": 0.13}}) == ("tax.rate", 0.13)

    def test_en_la_forma_vieja(self):
        """Una fila guardada antes de T-113 tiene que seguir entendiéndose: si
        no, actualizar el sistema le borraría la tasa al dueño en silencio."""
        assert tasa_declarada({"impuesto": {"tasa": 0.07}}) == ("impuesto.tasa", 0.07)

    def test_la_nueva_gana_cuando_están_las_dos(self):
        datos = {"tax": {"rate": 0.13}, "impuesto": {"tasa": 0.07}}
        assert tasa_declarada(datos) == ("tax.rate", 0.13)

    def test_cae_a_la_vieja_si_la_nueva_viene_nula(self):
        """Es el orden que ya tenía `get_tax_rate`, y se conserva: un nulo es
        ausencia de valor, no un valor."""
        datos = {"tax": {"rate": None}, "impuesto": {"tasa": 0.07}}
        assert tasa_declarada(datos) == ("impuesto.tasa", 0.07)

    def test_devuelve_el_valor_tal_cual_para_que_lo_valide_quien_llama(self):
        """No convierte: si convirtiera, un texto se volvería excepción acá y
        quien llama no podría decir `tax_rate_not_a_number` con el valor
        adentro."""
        assert tasa_declarada({"tax": {"rate": "mucho"}}) == ("tax.rate", "mucho")

    def test_encuentra_una_tasa_fuera_de_rango(self):
        """El caso del defecto: 5 es 500 %, y tiene que llegar a la validación en
        vez de perderse."""
        assert tasa_declarada({"tax": {"rate": 5}}) == ("tax.rate", 5)

    def test_encuentra_el_cero(self):
        """Un negocio exento configura 0 %, y el 0 es un valor, no una ausencia."""
        assert tasa_declarada({"tax": {"rate": 0}}) == ("tax.rate", 0)


class TestNoLaEncuentra:
    @pytest.mark.parametrize(
        "datos",
        [
            pytest.param({}, id="configuración vacía"),
            pytest.param({"moneda": {"simbolo": "₡"}}, id="sin sección de impuesto"),
            pytest.param({"tax": {}}, id="sección sin el campo"),
            pytest.param({"tax": {"rate": None}}, id="campo nulo"),
            pytest.param({"tax": {"nombre": "IVA"}}, id="sección con otros campos"),
        ],
    )
    def test_devuelve_nada(self, datos):
        assert tasa_declarada(datos) is None

    @pytest.mark.parametrize(
        "seccion",
        [
            pytest.param("0.13", id="cadena en vez de objeto"),
            pytest.param(13, id="número en vez de objeto"),
            pytest.param(None, id="nulo"),
            pytest.param(["rate", 0.13], id="lista"),
        ],
    )
    def test_una_seccion_que_no_es_un_objeto_no_revienta(self, seccion):
        """Una fila escrita a mano o por una versión anterior puede traer
        cualquier cosa. Vale más caer a la tasa de fábrica que no abrir."""
        assert tasa_declarada({"tax": seccion}) is None
