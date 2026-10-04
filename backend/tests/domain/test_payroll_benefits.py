"""Aguinaldo, vacaciones y liquidación (RN-69, RN-70, RN-71, RN-97, T-1203).

La tabla de cesantía de estas pruebas es la del art. 29 del Código de Trabajo,
la misma que siembra T-1204: la cesantía no vence con un decreto, así que acá
no hay cifra que inventar.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.money import Money
from app.domain.payroll import EARNING
from app.domain.payroll_benefits import (
    DISMISSAL_WITH_CAUSE,
    DISMISSAL_WITHOUT_CAUSE,
    END_OF_CONTRACT,
    MUTUAL,
    RESIGNATION,
    TERMINATION_CAUSES,
    VACATION_ACCRUAL,
    VACATION_OPENING,
    VACATION_PAID,
    VACATION_TAKEN,
    SettlementInput,
    SeveranceBracket,
    aguinaldo,
    aguinaldo_item,
    aguinaldo_period,
    aguinaldo_period_containing,
    average_salary,
    average_window,
    by_month,
    calendar_days,
    month_of,
    months_between,
    notice_days,
    proportional_vacation,
    settlement,
    settlement_vacation_days,
    severance_days,
    severance_years,
    vacation_accrual,
    vacation_balance,
)
from app.domain.payroll_calendar import Period

D = Decimal

TABLA = (
    SeveranceBracket(D("0.25"), D("0.5"), D(7)),
    SeveranceBracket(D("0.5"), D(1), D(14)),
    SeveranceBracket(D(1), D(2), D("19.5")),
    SeveranceBracket(D(2), D(3), D(20)),
    SeveranceBracket(D(3), D(4), D("20.5")),
    SeveranceBracket(D(4), D(5), D(21)),
    SeveranceBracket(D(5), D(6), D("21.24")),
    SeveranceBracket(D(6), D(7), D("21.5")),
    SeveranceBracket(D(7), D(10), D(22)),
    SeveranceBracket(D(10), D(11), D("21.5")),
    SeveranceBracket(D(11), D(12), D(21)),
    SeveranceBracket(D(12), D(13), D("20.5")),
    SeveranceBracket(D(13), None, D(20)),
)


class TestElAguinaldo:
    def test_el_periodo_va_de_diciembre_a_noviembre(self):
        assert aguinaldo_period(2026) == Period(date(2025, 12, 1), date(2026, 11, 30))

    def test_doce_meses_iguales_dan_un_mes(self):
        assert aguinaldo([Money(500000)] * 12) == Money(500000)

    def test_siete_meses(self):
        assert aguinaldo([Money(600000)] * 7) == Money(350000)

    def test_con_extras_cuentan_como_devengado(self):
        assert aguinaldo([Money(500000)] * 11 + [Money(560000)]) == Money(505000)

    def test_los_meses_de_apertura_suman_igual_que_los_pagados(self):
        """RN-97: quien migró en mayo no pierde lo que ganó en el otro sistema."""
        apertura, pagados = [Money(500000)] * 5, [Money(500000)] * 7
        assert aguinaldo(apertura + pagados) == aguinaldo([Money(500000)] * 12)

    def test_no_lleva_cargas_ni_renta(self):
        """RN-69: la exención que más se olvida. La corrida tiene un solo rubro."""
        rubro = aguinaldo_item(Money(500000))
        assert (rubro.concept, rubro.payer, rubro.amount) == ("aguinaldo", EARNING, Money(500000))


class TestLasVacaciones:
    @pytest.mark.parametrize(
        "dias, semana, ganados",
        [(350, 6, "12"), (350, 5, "10"), (25, 6, "0.86"), (700, 6, "24")],
    )
    def test_dos_semanas_por_cada_cincuenta(self, dias, semana, ganados):
        assert vacation_accrual(dias, semana) == D(ganados)

    def test_al_salir_antes_de_las_cincuenta_semanas_al_menos_un_dia_por_mes(self):
        # Cuatro meses en semana de cinco: 3,43 ganados contra 4 del mínimo.
        ganados = vacation_accrual(120, 5)
        assert proportional_vacation(date(2026, 1, 1), date(2026, 4, 30), ganados) == D(4)
        # En semana de seis lo ganado ya es el mínimo o más.
        assert proportional_vacation(date(2026, 1, 1), date(2026, 4, 30), D("4.11")) == D("4.11")


class TestLaAntiguedad:
    @pytest.mark.parametrize(
        "desde, hasta, meses",
        [
            (date(2026, 1, 10), date(2026, 4, 9), 3),
            (date(2026, 1, 10), date(2026, 4, 8), 2),
            (date(2024, 3, 1), date(2026, 2, 28), 24),
            (date(2026, 1, 10), date(2026, 1, 12), 0),
            (date(2026, 1, 1), date(2026, 4, 30), 4),
            # Febrero no tiene 31: del 31 de enero al 28 de febrero ya es un mes.
            (date(2026, 1, 31), date(2026, 2, 28), 1),
            (date(2026, 1, 31), date(2026, 2, 27), 0),
        ],
    )
    def test_meses_completos(self, desde, hasta, meses):
        assert months_between(desde, hasta) == meses

    @pytest.mark.parametrize("meses, dias", [(2, 0), (4, 7), (8, 15), (24, 30)])
    def test_el_preaviso(self, meses, dias):
        assert notice_days(meses) == dias


class TestLaCesantia:
    @pytest.mark.parametrize("meses, anos", [(30, 2), (31, 3), (18, 1), (19, 2), (12, 1)])
    def test_la_fraccion_de_mas_de_seis_meses_cuenta_como_ano(self, meses, anos):
        assert severance_years(meses) == anos

    @pytest.mark.parametrize(
        "meses, dias",
        [
            (2, "0"),
            (3, "7"),
            (6, "7"),
            (7, "14"),
            (11, "14"),
            (12, "19.5"),
            (24, "40"),
            # Dos años y siete meses son tres años de la fila del tres.
            (31, "61.5"),
            (60, "106.2"),
            (96, "176"),
            # Doce años cobran por ocho, a los días de la fila del doce.
            (144, "164"),
            (180, "160"),
        ],
    )
    def test_por_antiguedad_y_con_tope(self, meses, dias):
        assert severance_days(meses, TABLA) == D(dias)


class TestElPromedio:
    def test_de_los_ultimos_seis(self):
        meses = [Money(900000)] + [Money(600000)] * 5 + [Money(660000)]
        assert average_salary(meses) == Money(610000)

    def test_con_menos_de_seis_los_que_haya(self):
        assert average_salary([Money(500000), Money(700000)]) == Money(600000)

    def test_sin_ninguno(self):
        assert average_salary([]) == Money(0)


def liquidar(causa, desde=date(2024, 1, 1), hasta=date(2025, 12, 31)):
    datos = SettlementInput(
        cause=causa,
        hired_on=desde,
        terminated_on=hasta,
        average_monthly=Money(600000),
        vacation_days=D(6),
        aguinaldo_earned=Money(6600000),
    )
    return {r.concept: r.amount for r in settlement(datos, TABLA)}


class TestLaLiquidacionDependeDeLaCausa:
    """RN-71. Dos años con un promedio de 600 000: el día vale 20 000."""

    def test_el_despido_sin_causa_lo_paga_todo(self):
        assert liquidar(DISMISSAL_WITHOUT_CAUSE) == {
            "notice": Money(600000),
            "severance": Money(800000),
            "vacation_payout": Money(120000),
            "aguinaldo": Money(550000),
        }

    @pytest.mark.parametrize("causa", [RESIGNATION, DISMISSAL_WITH_CAUSE, MUTUAL, END_OF_CONTRACT])
    def test_las_demas_solo_los_proporcionales(self, causa):
        assert liquidar(causa) == {"vacation_payout": Money(120000), "aguinaldo": Money(550000)}

    def test_sin_vacaciones_pendientes_no_hay_renglon(self):
        datos = SettlementInput(RESIGNATION, date(2025, 1, 1), date(2025, 6, 30), Money(600000), D(0), Money(0))
        assert [r.concept for r in settlement(datos, TABLA)] == ["aguinaldo"]

    def test_son_cinco_causas(self):
        assert len(set(TERMINATION_CAUSES)) == 5


class TestLoDevengado:
    """Los meses con que se arman el aguinaldo y el promedio (RN-69, RN-71, RN-97)."""

    def test_el_periodo_de_aguinaldo_en_que_cae_un_dia(self):
        assert aguinaldo_period_containing(date(2026, 3, 15)) == aguinaldo_period(2026)
        assert aguinaldo_period_containing(date(2026, 11, 30)) == aguinaldo_period(2026)
        # Diciembre ya es del aguinaldo del año siguiente.
        assert aguinaldo_period_containing(date(2026, 12, 1)) == aguinaldo_period(2027)

    def test_el_mes_de_una_fecha(self):
        assert month_of(date(2026, 2, 28)) == date(2026, 2, 1)

    def test_la_ventana_del_promedio_son_los_seis_meses_anteriores(self):
        # Quien sale el 15 de marzo: de setiembre a febrero, el mes de la salida no.
        assert average_window(date(2026, 3, 15)) == Period(date(2025, 9, 1), date(2026, 2, 28))
        assert average_window(date(2026, 1, 31)) == Period(date(2025, 7, 1), date(2025, 12, 31))

    def test_por_mes_suma_las_corridas_del_mismo_mes_y_salta_los_vacios(self):
        meses = by_month(
            [
                (date(2026, 1, 15), Money(300000)),
                (date(2026, 1, 31), Money(310000)),
                (date(2026, 3, 31), Money(600000)),  # febrero no tuvo nada
                (date(2025, 12, 31), Money(590000)),
            ]
        )
        assert meses == [Money(590000), Money(610000), Money(600000)]
        assert by_month([]) == []

    def test_los_dias_de_calendario_cuentan_los_dos_extremos(self):
        assert calendar_days(date(2026, 1, 1), date(2026, 1, 15)) == 15
        assert calendar_days(date(2026, 1, 15), date(2026, 1, 1)) == 0


class TestElSaldoDeVacaciones:
    def test_es_la_suma_con_signo_de_los_movimientos(self):
        saldo = vacation_balance(
            [(VACATION_OPENING, D(5)), (VACATION_ACCRUAL, D("1.03")), (VACATION_TAKEN, D(2)), (VACATION_PAID, D("0.5"))]
        )
        assert saldo == D("3.53")
        assert vacation_balance([]) == 0

    def test_un_tipo_que_no_existe_revienta(self):
        with pytest.raises(KeyError):
            vacation_balance([("bonus", D(1))])

    def test_al_salir_se_liquida_lo_ganado_menos_lo_usado(self):
        # Dos años: lo acumulado manda y el piso de un día por mes no aplica.
        assert settlement_vacation_days(date(2024, 1, 1), date(2025, 12, 31), earned=D("24.5"), used=D(10)) == D("14.5")

    def test_antes_de_las_cincuenta_semanas_rige_el_piso_de_un_dia_por_mes(self):
        # Cuatro meses en semana de cinco: acumuló 3,43 pero el piso son 4.
        assert settlement_vacation_days(date(2026, 1, 1), date(2026, 4, 30), earned=D("3.43"), used=D(0)) == D(4)
        # Y si ya disfrutó dos, quedan dos.
        assert settlement_vacation_days(date(2026, 1, 1), date(2026, 4, 30), earned=D("3.43"), used=D(2)) == D(2)

    def test_nunca_negativo(self):
        assert settlement_vacation_days(date(2024, 1, 1), date(2025, 12, 31), earned=D(10), used=D(12)) == 0
