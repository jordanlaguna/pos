"""Las tasas que se siembran, contra lo publicado (T-1204, RN-67).

Corre sin Docker: lee `app/infrastructure/payroll_rates_cr.py` y lo pasa por el
dominio. Lo que comprueba es que la siembra **dice lo mismo que la fuente** el
día que se verificó: que las filas de la CCSS sumen los totales publicados, que
los tramos de renta no dejen huecos, y que cada regla que el dominio va a pedir
exista. Una cifra mal copiada no se nota en una prueba con tasas inventadas;
acá sí.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import RatesMissing
from app.domain.money import Money
from app.domain.payroll import (
    EMPLOYEE,
    EMPLOYER,
    REQUIRED_CONTRIBUTIONS,
    RULE,
    Rate,
    TaxBracket,
    check_new_rate,
    income_tax,
    rates_at,
)
from app.domain.payroll_actions import MATERNITY_RATE, SUBSIDIES
from app.domain.payroll_benefits import SeveranceBracket, severance_days
from app.infrastructure import payroll_rates_cr as cr


def filas() -> list[Rate]:
    return [Rate(r.concept, r.payer, r.value, r.valid_from) for r in cr.RATES]


class TestLasCargasSumanLoPublicado:
    @pytest.mark.parametrize("pagador", [EMPLOYEE, EMPLOYER])
    def test_la_suma_de_las_filas(self, pagador):
        suma = sum(r.value for r in cr.RATES if r.payer == pagador)
        assert suma == cr.PUBLISHED_TOTALS[pagador]

    def test_no_sobra_ni_falta_ningun_rubro(self):
        sembrados = {(r.concept, r.payer) for r in cr.RATES if r.payer != RULE}
        assert sembrados == REQUIRED_CONTRIBUTIONS["CR"]

    def test_se_resuelven_el_dia_que_se_verificaron(self):
        tasas = rates_at(filas(), cr.VERIFIED_AT)
        assert len(tasas.contributions(EMPLOYEE)) == 3

    def test_antes_de_2026_no_hay_tasas(self):
        """No se sembró el pasado: una corrida de 2025 fallaría con el código."""
        with pytest.raises(RatesMissing):
            rates_at(filas(), date(2025, 12, 31))

    def test_cada_fila_es_una_tasa_valida_y_tiene_fuente(self):
        for r in cr.RATES:
            check_new_rate(r.concept, r.payer, r.value, r.valid_from, None)
            assert len(r.source) > 10, r.concept


class TestLasReglasQueElDominioPide:
    def test_estan_todas(self):
        tasas = rates_at(filas(), cr.VERIFIED_AT)
        pedidas = {MATERNITY_RATE, "minimum_wage_unseizable"}
        for _, dias, tasa in SUBSIDIES.values():
            pedidas |= {dias, tasa}
        for concepto in pedidas:
            tasas.rule(concepto)

    def test_el_patrono_no_paga_dias_del_ins(self):
        """Art. 236: el INS paga desde la fecha del riesgo."""
        assert rates_at(filas(), cr.VERIFIED_AT).rule("ins_employer_days") == 0


class TestLaRentaDe2026:
    def tramos(self):
        return [TaxBracket(Money(d), None if h is None else Money(h), t) for d, h, t in cr.BRACKETS]

    def test_los_tramos_no_dejan_huecos(self):
        assert cr.BRACKETS[0][0] == 0 and cr.BRACKETS[-1][1] is None
        for anterior, siguiente in zip(cr.BRACKETS, cr.BRACKETS[1:]):
            assert anterior[1] == siguiente[0]
            assert anterior[2] < siguiente[2]

    @pytest.mark.parametrize(
        "salario, impuesto",
        [("918000", "0"), ("1000000", "8200"), ("1500000", "65850"), ("5000000", "736300")],
    )
    def test_ejemplos(self, salario, impuesto):
        # 5 000 000: 42 900 + 152 550 + 472 600 + 68 250.
        assert income_tax(Money(salario), self.tramos(), Money(0)) == Money(impuesto)

    def test_los_creditos(self):
        assert cr.CREDITS == {"child": Decimal(1710), "spouse": Decimal(2590)}


class TestLaCesantiaDelArticulo29:
    def tabla(self):
        return [SeveranceBracket(d, h, dias) for d, h, dias in cr.SEVERANCE]

    @pytest.mark.parametrize(
        "anos, por_ano",
        [(1, "19.5"), (2, "20"), (3, "20.5"), (4, "21"), (5, "21.24"), (6, "21.5"), (7, "22"), (8, "22"), (9, "22"), (10, "21.5"), (11, "21"), (12, "20.5"), (13, "20"), (20, "20")],
    )
    def test_los_dias_por_ano_del_texto(self, anos, por_ano):
        dias = severance_days(anos * 12, self.tabla())
        assert dias == Decimal(por_ano) * min(anos, 8)

    def test_bajo_el_ano(self):
        assert severance_days(4, self.tabla()) == 7
        assert severance_days(9, self.tabla()) == 14


def test_el_simulado_siembra_lo_mismo_que_la_api():
    """El POS en modo simulado lee un archivo generado de este; si se editó uno
    y no se regeneró el otro, las dos aplicaciones responden distinto."""
    import generar_tasas_simulado as gen

    assert gen.DESTINO.read_text(encoding="utf-8") == gen.contenido(), (
        "payrollRates.ts quedó viejo: corra `python backend/generar_tasas_simulado.py`"
    )
