"""Jornadas, cortes y periodos (RN-94, T-1202)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import InvalidCutDate, InvalidSchedule
from app.domain.money import Money
from app.domain.payroll_calendar import (
    BIWEEKLY,
    MONTHLY,
    SEMIMONTHLY,
    WEEKLY,
    Period,
    Schedule,
    check_schedule,
    closes_month,
    day_value,
    hour_value,
    monthly_equivalent,
    next_cut,
    paid_days,
    period_for,
)

OCHO = Decimal(8)

MENSUAL = Schedule(MONTHLY, "day", OCHO)
QUINCENA_15 = Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=15)
QUINCENA_14 = Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=14)
#: El 5 de enero de 2026 es lunes: la serie corre de lunes a domingo.
BISEMANAL = Schedule(BIWEEKLY, "day", OCHO, series_start=date(2026, 1, 5))
#: Corta los domingos. El 4 de enero de 2026 es domingo.
SEMANAL = Schedule(WEEKLY, "day", OCHO, cut_weekday=6)


def P(desde: date, hasta: date) -> Period:
    return Period(desde, hasta)


class TestUnaJornadaDiceLoQueSuPeriodicidadPide:
    @pytest.mark.parametrize("jornada", [MENSUAL, QUINCENA_15, QUINCENA_14, BISEMANAL, SEMANAL])
    def test_las_cinco_de_ejemplo_son_validas(self, jornada):
        check_schedule(jornada)

    @pytest.mark.parametrize(
        "jornada, campo, motivo",
        [
            (Schedule("fortnightly", "day", OCHO), "frequency", "unknown"),
            (Schedule(MONTHLY, "evening", OCHO), "shift", "unknown"),
            (Schedule(MONTHLY, "day", Decimal(0)), "hours_per_day", "out_of_range"),
            (Schedule(MONTHLY, "day", Decimal(13)), "hours_per_day", "out_of_range"),
            (Schedule(MONTHLY, "day", OCHO, workdays_per_week=7), "workdays_per_week", "out_of_range"),
            (Schedule(SEMIMONTHLY, "day", OCHO), "first_cut_day", "required"),
            (Schedule(BIWEEKLY, "day", OCHO), "series_start", "required"),
            (Schedule(WEEKLY, "day", OCHO), "cut_weekday", "required"),
            # Una mensual con día de corte de quincena: ¿cuál quiso decir?
            (Schedule(MONTHLY, "day", OCHO, first_cut_day=15), "first_cut_day", "unexpected"),
            (Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=16), "first_cut_day", "out_of_range"),
            (Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=7), "first_cut_day", "out_of_range"),
            (Schedule(WEEKLY, "day", OCHO, cut_weekday=7), "cut_weekday", "out_of_range"),
        ],
    )
    def test_lo_que_falta_o_sobra_se_dice_por_campo(self, jornada, campo, motivo):
        with pytest.raises(InvalidSchedule) as error:
            check_schedule(jornada)
        assert (error.value.field, error.value.reason) == (campo, motivo)


class TestElPeriodoSaleDelCorte:
    def test_mensual_a_fin_de_mes(self):
        assert period_for(MENSUAL, date(2026, 4, 30)) == P(date(2026, 4, 1), date(2026, 4, 30))

    def test_mensual_solo_corta_el_ultimo_dia(self):
        with pytest.raises(InvalidCutDate):
            period_for(MENSUAL, date(2026, 4, 29))

    @pytest.mark.parametrize(
        "corte, desde",
        [
            (date(2026, 1, 15), date(2026, 1, 1)),
            (date(2026, 1, 31), date(2026, 1, 16)),
            (date(2026, 2, 28), date(2026, 2, 16)),
        ],
    )
    def test_quincenal_que_corta_el_15(self, corte, desde):
        assert period_for(QUINCENA_15, corte) == P(desde, corte)

    @pytest.mark.parametrize(
        "corte, desde",
        [
            (date(2026, 3, 29), date(2026, 3, 15)),
            # La primera empieza el día después del 29 del mes anterior.
            (date(2026, 4, 14), date(2026, 3, 30)),
            # Febrero no tiene 29: la segunda corta el 28…
            (date(2026, 2, 28), date(2026, 2, 15)),
            # …y la de marzo empieza el 1.
            (date(2026, 3, 14), date(2026, 3, 1)),
            # Y cruzando el año.
            (date(2026, 1, 14), date(2025, 12, 30)),
            # En un bisiesto sí hay 29.
            (date(2028, 2, 29), date(2028, 2, 15)),
        ],
    )
    def test_quincenal_que_corta_el_14(self, corte, desde):
        assert period_for(QUINCENA_14, corte) == P(desde, corte)

    @pytest.mark.parametrize("corte", [date(2026, 1, 20), date(2026, 1, 30)])
    def test_una_quincenal_no_corta_cualquier_dia(self, corte):
        with pytest.raises(InvalidCutDate) as error:
            period_for(QUINCENA_14, corte)
        assert error.value.cut == corte and error.value.frequency == SEMIMONTHLY

    @pytest.mark.parametrize(
        "corte, desde",
        [
            (date(2026, 1, 18), date(2026, 1, 5)),
            (date(2026, 2, 1), date(2026, 1, 19)),
        ],
    )
    def test_bisemanal_cada_catorce_dias_desde_su_serie(self, corte, desde):
        assert period_for(BISEMANAL, corte) == P(desde, corte)

    @pytest.mark.parametrize("corte", [date(2026, 1, 17), date(2026, 1, 25), date(2026, 1, 4)])
    def test_bisemanal_fuera_de_la_serie(self, corte):
        with pytest.raises(InvalidCutDate):
            period_for(BISEMANAL, corte)

    def test_semanal_de_lunes_a_domingo(self):
        assert period_for(SEMANAL, date(2026, 1, 4)) == P(date(2025, 12, 29), date(2026, 1, 4))

    def test_semanal_solo_corta_su_dia(self):
        with pytest.raises(InvalidCutDate):
            period_for(SEMANAL, date(2026, 1, 5))

    def test_un_dia_esta_en_el_periodo_si_cae_entre_sus_extremos(self):
        periodo = P(date(2026, 1, 1), date(2026, 1, 15))
        assert date(2026, 1, 1) in periodo and date(2026, 1, 15) in periodo
        assert date(2026, 1, 16) not in periodo


class TestLaUltimaCorridaDelMes:
    @pytest.mark.parametrize(
        "jornada, corte, siguiente",
        [
            (MENSUAL, date(2026, 1, 31), date(2026, 2, 28)),
            (QUINCENA_15, date(2026, 1, 15), date(2026, 1, 31)),
            (QUINCENA_14, date(2026, 1, 14), date(2026, 1, 29)),
            # Después del 29, el siguiente es el 14 del mes que viene.
            (QUINCENA_14, date(2026, 1, 29), date(2026, 2, 14)),
            (QUINCENA_14, date(2026, 12, 29), date(2027, 1, 14)),
            (BISEMANAL, date(2026, 1, 18), date(2026, 2, 1)),
            (SEMANAL, date(2026, 1, 4), date(2026, 1, 11)),
        ],
    )
    def test_el_corte_que_sigue(self, jornada, corte, siguiente):
        assert next_cut(jornada, corte) == siguiente

    @pytest.mark.parametrize(
        "jornada, corte, cierra",
        [
            (MENSUAL, date(2026, 1, 31), True),
            (QUINCENA_15, date(2026, 1, 15), False),
            (QUINCENA_15, date(2026, 1, 31), True),
            (QUINCENA_14, date(2026, 1, 14), False),
            (QUINCENA_14, date(2026, 1, 29), True),
            (SEMANAL, date(2026, 1, 18), False),
            (SEMANAL, date(2026, 1, 25), True),
        ],
    )
    def test_cierra_el_mes_si_el_corte_siguiente_es_de_otro(self, jornada, corte, cierra):
        assert closes_month(jornada, corte) is cierra


class TestDeUnPeriodoAlMes:
    @pytest.mark.parametrize(
        "monto, periodicidad, mensual",
        [
            ("600000", MONTHLY, "600000"),
            ("300000", SEMIMONTHLY, "600000"),
            ("200000", BIWEEKLY, "433333.33"),
            ("100000", WEEKLY, "433333.33"),
        ],
    )
    def test_los_cuatro_factores(self, monto, periodicidad, mensual):
        assert monthly_equivalent(Money(monto), periodicidad) == Money(mensual)


class TestLoQueValeUnDia:
    """Decreto de salarios mínimos, art. 7: el mes paga 30, la quincena 15 y la
    semana 6, o 7 en los establecimientos comerciales."""

    @pytest.mark.parametrize(
        "jornada, dias",
        [
            (MENSUAL, 30),
            (QUINCENA_15, 15),
            (SEMANAL, 7),
            (Schedule(WEEKLY, "day", OCHO, rest_day_paid=False, cut_weekday=6), 6),
            (BISEMANAL, 14),
            (Schedule(BIWEEKLY, "day", OCHO, rest_day_paid=False, series_start=date(2026, 1, 5)), 12),
        ],
    )
    def test_los_dias_que_paga_el_salario_del_periodo(self, jornada, dias):
        assert paid_days(jornada) == dias

    @pytest.mark.parametrize(
        "salario, jornada",
        [
            ("600000", MENSUAL),
            ("300000", QUINCENA_15),
            ("140000", SEMANAL),
            ("120000", Schedule(WEEKLY, "day", OCHO, rest_day_paid=False, cut_weekday=6)),
        ],
    )
    def test_el_dia_vale_lo_mismo_sea_cual_sea_la_periodicidad(self, salario, jornada):
        assert day_value(Money(salario), jornada) == Decimal(20000)

    def test_el_dia_no_se_redondea(self):
        # 100 000 entre 7: el rubro se redondea, la tarifa no.
        assert day_value(Money(100000), SEMANAL) == Decimal(100000) / 7

    @pytest.mark.parametrize(
        "clase, horas, hora",
        [
            ("day", Decimal(8), Decimal(2500)),
            ("mixed", Decimal(7), Decimal(600000) / 210),
            ("night", Decimal(6), Decimal(600000) / 180),
        ],
    )
    def test_la_hora_es_el_dia_entre_las_horas_de_la_jornada(self, clase, horas, hora):
        assert hour_value(Money(600000), Schedule(MONTHLY, clase, horas)) == hora
