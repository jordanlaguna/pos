"""Tasas, cargas y renta (RN-66, RN-67, RN-73, T-1202).

**Las cifras son inventadas a propósito.** Ninguna es la de la CCSS ni la de
Hacienda: se prueba la aritmética, y una cifra real vencería con el próximo
decreto y dejaría una prueba que miente en verde.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import InvalidPayrollRate, InvalidTaxBrackets, RateNotNewer, RatesMissing
from app.domain.money import Money
from app.domain.payroll import (
    EMPLOYEE,
    EMPLOYER,
    INA_CONCEPT,
    REQUIRED_CONTRIBUTIONS,
    RT_CONCEPT,
    RULE,
    PayItem,
    Rate,
    TaxBracket,
    TaxCredits,
    check_new_rate,
    check_tax_brackets,
    employee_deductions,
    employer_charges,
    income_tax,
    income_tax_withholding,
    is_stale,
    rates_at,
    total,
)
from app.domain.payroll_calendar import SEMIMONTHLY, WEEKLY

ENERO = date(2026, 1, 1)
CORTE = date(2026, 3, 15)

#: Un juego completo e inventado: 5 %, 4 % y 1 % obrero; 1 % por cada rubro
#: patronal.
OBRERO = {"sem": "0.05", "ivm": "0.04", "banco_popular": "0.01"}


def juego(desde: date = ENERO, **cambios: str) -> list[Rate]:
    filas = [Rate(c, EMPLOYEE, Decimal(v), desde) for c, v in OBRERO.items()]
    filas += [
        Rate(c, EMPLOYER, Decimal("0.01"), desde)
        for c, p in sorted(REQUIRED_CONTRIBUTIONS["CR"])
        if p == EMPLOYER
    ]
    filas.append(Rate("sick_leave_employer_days", RULE, Decimal(3), desde))
    return filas


class TestLasTasasQueRigenAUnaFecha:
    def test_un_juego_completo_se_resuelve(self):
        tasas = rates_at(juego(), CORTE)
        assert [r.concept for r in tasas.contributions(EMPLOYEE)] == ["banco_popular", "ivm", "sem"]
        assert len(tasas.contributions(EMPLOYER)) == 10

    def test_la_fila_nueva_gana_sin_que_la_vieja_se_edite(self):
        """Una tasa nueva es una fila con fecha, no un despliegue (RN-67)."""
        filas = juego() + [Rate("ivm", EMPLOYEE, Decimal("0.045"), date(2026, 3, 1))]
        antes = rates_at(filas, date(2026, 2, 28))
        despues = rates_at(filas, CORTE)
        ivm = lambda s: next(r for r in s.contributions(EMPLOYEE) if r.concept == "ivm")  # noqa: E731
        assert ivm(antes).value == Decimal("0.04")
        assert ivm(despues).value == Decimal("0.045")
        # Y no depende del orden en que la base devuelva las filas.
        assert ivm(rates_at(list(reversed(filas)), CORTE)).value == Decimal("0.045")

    def test_lo_vencido_y_lo_futuro_no_rigen(self):
        filas = juego() + [
            Rate("ivm", EMPLOYEE, Decimal("0.09"), date(2025, 1, 1), valid_to=date(2025, 12, 31)),
            Rate("ivm", EMPLOYEE, Decimal("0.08"), date(2027, 1, 1)),
        ]
        ivm = next(r for r in rates_at(filas, CORTE).contributions(EMPLOYEE) if r.concept == "ivm")
        assert ivm.value == Decimal("0.04")

    def test_sin_una_carga_no_se_calcula(self):
        """Sin la fila del IVM, la boleta saldría sin IVM y nadie lo notaría."""
        filas = [r for r in juego() if not (r.concept == "ivm")]
        with pytest.raises(RatesMissing) as error:
            rates_at(filas, CORTE)
        assert error.value.missing == ("ivm:employee", "ivm:employer")
        assert error.value.on == CORTE

    def test_antes_de_la_primera_vigencia_falta_todo(self):
        with pytest.raises(RatesMissing):
            rates_at(juego(desde=date(2026, 6, 1)), CORTE)

    def test_una_regla_se_pide_cuando_hace_falta(self):
        tasas = rates_at(juego(), CORTE)
        assert tasas.rule("sick_leave_employer_days") == Decimal(3)
        with pytest.raises(RatesMissing) as error:
            tasas.rule("minimum_wage_unseizable")
        assert error.value.missing == ("minimum_wage_unseizable:rule",)


class TestLasCargas:
    def test_las_obreras_una_por_rubro(self):
        rubros = employee_deductions(Money(300000), rates_at(juego(), CORTE))
        assert [(r.concept, r.amount) for r in rubros] == [
            ("banco_popular", Money(3000)),
            ("ivm", Money(12000)),
            ("sem", Money(15000)),
        ]
        assert all(r.payer == EMPLOYEE and r.base == Money(300000) for r in rubros)

    def test_se_redondea_cada_rubro_y_se_suman_los_redondeados(self):
        """La suma de la boleta es la de sus renglones, no un total aparte."""
        tasas = rates_at(juego(), CORTE)
        rubros = employee_deductions(Money("333333.33"), tasas)
        # 16 666,67 + 13 333,33 + 3 333,33: cada uno redondeado.
        assert [r.amount for r in rubros] == [Money("3333.33"), Money("13333.33"), Money("16666.67")]
        assert total(rubros) == Money("33333.33")

    def test_las_patronales_llevan_la_prima_de_la_poliza(self):
        rubros = employer_charges(Money(300000), rates_at(juego(), CORTE), Decimal("0.015"))
        rt = [r for r in rubros if r.concept == RT_CONCEPT]
        assert rt == [PayItem(RT_CONCEPT, EMPLOYER, Money(300000), Decimal("0.015"), Money(4500))]
        assert total(rubros) == Money(10 * 3000 + 4500)

    def test_el_patrono_exento_no_paga_el_ina(self):
        """Patrono no agrícola con menos de cinco trabajadores permanentes."""
        rubros = employer_charges(Money(300000), rates_at(juego(), CORTE), Decimal("0.015"), exempt=frozenset({INA_CONCEPT}))
        assert INA_CONCEPT not in {r.concept for r in rubros}
        assert total(rubros) == Money(9 * 3000 + 4500)


#: Tramos inventados: exento hasta 900 000, 10 % hasta 1 300 000, 15 % hasta
#: 2 300 000 y 20 % de ahí en adelante.
TRAMOS = (
    TaxBracket(Money(0), Money(900000), Decimal(0)),
    TaxBracket(Money(900000), Money(1300000), Decimal("0.10")),
    TaxBracket(Money(1300000), Money(2300000), Decimal("0.15")),
    TaxBracket(Money(2300000), None, Decimal("0.20")),
)
SIN_CREDITOS = Money(0)


class TestLaRenta:
    @pytest.mark.parametrize(
        "salario, impuesto",
        [
            ("800000", "0"),
            ("900000", "0"),
            ("1000000", "10000"),
            # Marginal: 40 000 del segundo tramo y 30 000 del tercero.
            ("1500000", "70000"),
            # Los cuatro tramos: 40 000 + 150 000 + 140 000 del último, sin techo.
            ("3000000", "330000"),
        ],
    )
    def test_tramos_marginales(self, salario, impuesto):
        assert income_tax(Money(salario), TRAMOS, SIN_CREDITOS) == Money(impuesto)

    def test_los_creditos_restan_del_impuesto(self):
        creditos = TaxCredits(child=Money(1700), spouse=Money(2600))
        assert creditos.for_employee(2, spouse=True) == Money(6000)
        assert creditos.for_employee(0, spouse=False) == Money(0)
        assert income_tax(Money(1500000), TRAMOS, Money(6000)) == Money(64000)

    def test_el_credito_no_le_paga_al_empleado(self):
        assert income_tax(Money(1000000), TRAMOS, Money(50000)) == Money(0)


def retener(gravable, periodicidad=SEMIMONTHLY, *, cierra, antes="0", retenido="0"):
    return income_tax_withholding(
        Money(gravable),
        periodicidad,
        closes_month=cierra,
        month_taxable_before=Money(antes),
        month_withheld_before=Money(retenido),
        brackets=TRAMOS,
        credits=SIN_CREDITOS,
    )


class TestLaRentaDelMesCuadra:
    """RN-73: la última del mes liquida, y el mes retiene el impuesto del mes."""

    def test_dos_quincenas_iguales_mitad_y_mitad(self):
        primera = retener("750000", cierra=False)
        segunda = retener("750000", cierra=True, antes="750000", retenido=primera.amount)
        assert (primera, segunda) == (Money(35000), Money(35000))

    def test_con_extras_solo_en_la_segunda_la_segunda_liquida(self):
        primera = retener("600000", cierra=False)
        segunda = retener("900000", cierra=True, antes="600000", retenido=primera.amount)
        assert primera == Money(15000)
        assert primera + segunda == income_tax(Money(1500000), TRAMOS, SIN_CREDITOS)

    def test_si_la_primera_retuvo_de_mas_la_segunda_devuelve(self):
        primera = retener("900000", cierra=False)
        segunda = retener("300000", cierra=True, antes="900000", retenido=primera.amount)
        assert primera == Money(57500)
        assert segunda == Money(-27500)
        assert primera + segunda == Money(30000)

    def test_una_semana_retiene_su_parte_de_la_proyeccion(self):
        # 300 000 × 52 / 12 = 1 300 000 → 40 000 al mes → entre 52/12.
        assert retener("300000", WEEKLY, cierra=False) == Money("9230.77")


class TestLaTasaNuevaSeAgregaNoSeEdita:
    def test_una_valida(self):
        check_new_rate("ivm", EMPLOYEE, Decimal("0.045"), date(2029, 1, 1), date(2026, 1, 1))
        check_new_rate("minimum_wage_unseizable", RULE, Decimal("275000"), date(2027, 1, 1), None)

    @pytest.mark.parametrize(
        "pagador, valor, campo",
        [("state", Decimal("0.01"), "payer"), (EMPLOYEE, Decimal("5.5"), "value"), (RULE, Decimal(-1), "value")],
    )
    def test_lo_que_no_es_una_tasa(self, pagador, valor, campo):
        with pytest.raises(InvalidPayrollRate) as error:
            check_new_rate("sem", pagador, valor, date(2027, 1, 1), None)
        assert error.value.field == campo

    @pytest.mark.parametrize("desde", [date(2026, 1, 1), date(2025, 6, 1)])
    def test_no_reescribe_la_vigente_ni_el_pasado(self, desde):
        with pytest.raises(RateNotNewer) as error:
            check_new_rate("ivm", EMPLOYEE, Decimal("0.045"), desde, date(2026, 1, 1))
        assert (error.value.concept, error.value.payer, error.value.latest) == ("ivm", EMPLOYEE, date(2026, 1, 1))

    def test_seis_meses_sin_comprobar_es_vieja(self):
        assert not is_stale(date(2026, 1, 1), date(2026, 7, 3))
        assert is_stale(date(2026, 1, 1), date(2026, 7, 4))


# ------------------------------------------- los tramos del año siguiente

MILLON = Decimal(1000000)


def tramos(*filas):
    return [(Decimal(a), None if b is None else Decimal(b), Decimal(t)) for a, b, t in filas]


BUENOS = tramos((0, 922000, "0"), (922000, 1352000, "0.10"), (1352000, None, "0.15"))
CREDITOS = {"child": Decimal(1710), "spouse": Decimal(2590)}
ENERO_27 = date(2027, 1, 1)


class TestUnJuegoDeTramosNuevo:
    def test_un_juego_completo_y_posterior_entra(self):
        check_tax_brackets(BUENOS, CREDITOS, ENERO_27, latest=ENERO)
        check_tax_brackets(BUENOS, CREDITOS, ENERO_27, latest=None)

    @pytest.mark.parametrize(
        "filas, motivo, indice",
        [
            ([], "empty", None),
            (tramos((100, 500, "0.1"), (500, None, "0.2")), "not_from_zero", 0),
            (tramos((0, 500, "0"), (600, None, "0.1")), "gap", 1),
            (tramos((0, 500, "0"), (400, None, "0.1")), "gap", 1),
            (tramos((0, 500, "1.5"), (500, None, "0.1")), "rate_out_of_range", 0),
            (tramos((0, None, "0"), (500, None, "0.1")), "open_end_not_last", 0),
            (tramos((0, 0, "0"), (500, None, "0.1")), "empty_range", 0),
            (tramos((0, 500, "0"), (500, 900, "0.1")), "no_open_end", 1),
        ],
    )
    def test_lo_que_deja_un_salario_sin_tramo(self, filas, motivo, indice):
        with pytest.raises(InvalidTaxBrackets) as e:
            check_tax_brackets(filas, CREDITOS, ENERO_27, latest=None)
        assert (e.value.reason, e.value.index) == (motivo, indice)

    def test_un_credito_negativo(self):
        with pytest.raises(InvalidTaxBrackets) as e:
            check_tax_brackets(BUENOS, {"child": Decimal(-1)}, ENERO_27, latest=None)
        assert e.value.reason == "credit_negative"

    def test_el_juego_no_se_edita_se_agrega_uno_posterior(self):
        with pytest.raises(RateNotNewer) as e:
            check_tax_brackets(BUENOS, CREDITOS, ENERO, latest=ENERO)
        assert (e.value.concept, e.value.latest) == ("income_tax_brackets", ENERO)
        with pytest.raises(RateNotNewer):
            check_tax_brackets(BUENOS, CREDITOS, date(2026, 6, 1), latest=ENERO_27)
