"""Acciones de personal: tramos, rubros y deducciones (RN-90 a RN-94, T-1216).

Salario de ejemplo: 600 000 al mes, pagado por quincena. La quincena es
300 000, el día vale 20 000 y la hora diurna 2 500. Las reglas de
incapacidad son inventadas, como todas las cifras de estas pruebas.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import InvalidAction, RatesMissing
from app.domain.money import Money
from app.domain.payroll import EARNING, EMPLOYEE, REQUIRED_CONTRIBUTIONS, RULE, PayItem, Rate, rates_at
from app.domain.payroll_actions import (
    ABSENCE,
    ACTION_KINDS,
    BONUS,
    CHILD_SUPPORT,
    DEDUCTION,
    DOUBLE_TIME,
    GARNISHMENT,
    MATERNITY,
    MATERNITY_PAY,
    OVERTIME,
    PAID_LEAVE,
    POSITION_CHANGE,
    RAISE,
    SICK_LEAVE_CCSS,
    SICK_LEAVE_INS,
    TERMINATION,
    UNPAID_LEAVE,
    VACATION,
    Action,
    Portion,
    action_items,
    apply_deductions,
    base_item,
    check_action,
    contribution_base,
    counted_days,
    deduction_due,
    deduction_order,
    child_support_capacity,
    garnishment_amount,
    garnishment_capacity,
    is_active,
    portions,
    remaining_balance,
    taxable_base,
)
from app.domain.payroll_calendar import SEMIMONTHLY, WEEKLY, Period, Schedule

OCHO = Decimal(8)
QUINCENA = Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=15)
QUINCENA_14 = Schedule(SEMIMONTHLY, "day", OCHO, first_cut_day=14)
SEMANA_COMERCIAL = Schedule(WEEKLY, "day", OCHO, cut_weekday=6)
SEMANA_NO_COMERCIAL = Schedule(WEEKLY, "day", OCHO, rest_day_paid=False, cut_weekday=6)

PRIMERA = Period(date(2026, 1, 1), date(2026, 1, 15))
SEGUNDA = Period(date(2026, 1, 16), date(2026, 1, 31))
QUINCENA_SALARIO = Money(300000)

REGLAS = {
    "sick_leave_employer_days": "3",
    "sick_leave_employer_rate": "0.5",
    "ins_employer_days": "1",
    "ins_employer_rate": "1",
    "maternity_employer_rate": "0.5",
}


def tasas(**sin: bool):
    filas = [Rate(c, p, Decimal("0.01"), date(2026, 1, 1)) for c, p in REQUIRED_CONTRIBUTIONS["CR"]]
    filas += [Rate(c, RULE, Decimal(v), date(2026, 1, 1)) for c, v in REGLAS.items() if c not in sin]
    return rates_at(filas, date(2026, 1, 15))


def incapacidad(desde=date(2026, 1, 10), hasta=date(2026, 1, 20), kind=SICK_LEAVE_CCSS):
    return Action(kind, desde, hasta, id=7)


class TestCadaTipoPideLoSuyo:
    @pytest.mark.parametrize(
        "accion",
        [
            Action(OVERTIME, date(2026, 1, 5), hours=Decimal(4)),
            Action(OVERTIME, date(2026, 1, 5), date(2026, 1, 5), hours=Decimal(4)),
            Action(DOUBLE_TIME, date(2026, 1, 5), hours=Decimal(8)),
            Action(BONUS, date(2026, 1, 5), amount=Money(50000)),
            Action(SICK_LEAVE_CCSS, date(2026, 1, 5), date(2026, 1, 9)),
            Action(VACATION, date(2026, 1, 5), date(2026, 1, 11), days=Decimal(6)),
            Action(DEDUCTION, date(2026, 1, 5), amount=Money(25000), total_amount=Money(300000), is_recurring=True),
            Action(CHILD_SUPPORT, date(2026, 1, 5), amount=Money(40000), is_recurring=True),
            Action(GARNISHMENT, date(2026, 1, 5), total_amount=Money(500000)),
            Action(RAISE, date(2026, 1, 5), new_salary=Money(650000)),
            Action(POSITION_CHANGE, date(2026, 1, 5), position_id=2),
            Action(TERMINATION, date(2026, 1, 5)),
        ],
    )
    def test_bien_formadas(self, accion):
        check_action(accion)

    def test_son_dieciseis(self):
        assert len(ACTION_KINDS) == len(set(ACTION_KINDS)) == 16

    @pytest.mark.parametrize(
        "accion, campo, motivo",
        [
            (Action("loan", date(2026, 1, 5)), "kind", "unknown"),
            (Action(OVERTIME, date(2026, 1, 5)), "hours", "required"),
            (Action(ABSENCE, date(2026, 1, 5)), "ends_on", "required"),
            (Action(VACATION, date(2026, 1, 5), date(2026, 1, 9)), "days", "required"),
            (Action(BONUS, date(2026, 1, 5)), "amount", "required"),
            (Action(DEDUCTION, date(2026, 1, 5)), "amount", "required"),
            (Action(GARNISHMENT, date(2026, 1, 5)), "total_amount", "required"),
            (Action(RAISE, date(2026, 1, 5)), "new_salary", "required"),
            (Action(POSITION_CHANGE, date(2026, 1, 5)), "position_id", "required"),
            (Action(OVERTIME, date(2026, 1, 5), hours=Decimal(0)), "hours", "not_positive"),
            (Action(BONUS, date(2026, 1, 5), amount=Money(-1)), "amount", "not_positive"),
            (Action(OVERTIME, date(2026, 1, 5), date(2026, 1, 6), hours=Decimal(4)), "ends_on", "single_day"),
            (Action(ABSENCE, date(2026, 1, 5), date(2026, 1, 4)), "ends_on", "before_start"),
            (Action(VACATION, date(2026, 1, 5), date(2026, 1, 11), days=Decimal(8)), "days", "too_many"),
            (Action(GARNISHMENT, date(2026, 1, 5), total_amount=Money(1), is_recurring=True), "is_recurring", "not_allowed"),
            (Action(BONUS, date(2026, 1, 5), amount=Money(1), is_recurring=True), "is_recurring", "not_allowed"),
        ],
    )
    def test_lo_que_falta_o_sobra(self, accion, campo, motivo):
        with pytest.raises(InvalidAction) as error:
            check_action(accion)
        assert (error.value.field, error.value.reason) == (campo, motivo)


class TestElMesComercial:
    @pytest.mark.parametrize(
        "jornada, desde, hasta, dias",
        [
            (QUINCENA, date(2026, 1, 10), date(2026, 1, 15), 6),
            # Una segunda quincena entera son quince días en enero…
            (QUINCENA, date(2026, 1, 16), date(2026, 1, 31), 15),
            # …y en febrero.
            (QUINCENA, date(2026, 2, 16), date(2026, 2, 28), 15),
            # Del 15 al 28 de febrero serían dieciséis, y la quincena paga quince.
            (QUINCENA_14, date(2026, 2, 15), date(2026, 2, 28), 15),
            # El 31 no se cuenta.
            (QUINCENA, date(2026, 1, 31), date(2026, 1, 31), 0),
            # Una quincena que cruza el fin de marzo.
            (QUINCENA_14, date(2026, 3, 30), date(2026, 4, 14), 15),
            (SEMANA_COMERCIAL, date(2025, 12, 29), date(2026, 1, 4), 7),
            # Sin descanso pagado, la semana paga seis y no se rebajan siete.
            (SEMANA_NO_COMERCIAL, date(2025, 12, 29), date(2026, 1, 4), 6),
        ],
    )
    def test_los_dias_que_cuenta_un_tramo(self, jornada, desde, hasta, dias):
        assert counted_days(jornada, desde, hasta) == Decimal(dias)


class TestLaCorridaTomaSuTramo:
    def test_una_incapacidad_que_cruza_la_quincena_se_parte_sola(self):
        accion = incapacidad()
        assert portions(accion, QUINCENA, date(2026, 1, 1), PRIMERA) == (
            Portion(date(2026, 1, 10), date(2026, 1, 15), Decimal(6), 0),
        )
        assert portions(accion, QUINCENA, date(2026, 1, 16), SEGUNDA) == (
            Portion(date(2026, 1, 16), date(2026, 1, 20), Decimal(5), 6),
        )

    def test_la_que_llego_tarde_entra_en_la_siguiente_con_sus_fechas(self):
        """RN-91: la primera quincena ya se pagó y no se toca."""
        assert portions(incapacidad(), QUINCENA, date(2026, 1, 10), SEGUNDA) == (
            Portion(date(2026, 1, 10), date(2026, 1, 15), Decimal(6), 0),
            Portion(date(2026, 1, 16), date(2026, 1, 20), Decimal(5), 6),
        )

    def test_la_ya_aplicada_y_la_futura_no_dan_nada(self):
        assert portions(incapacidad(), QUINCENA, date(2026, 1, 21), SEGUNDA) == ()
        futura = incapacidad(date(2026, 2, 3), date(2026, 2, 5))
        assert portions(futura, QUINCENA, date(2026, 2, 3), SEGUNDA) == ()

    def test_las_de_un_dia_se_aplican_una_vez_en_su_periodo(self):
        extras = Action(OVERTIME, date(2026, 1, 12), hours=Decimal(4), id=3)
        assert portions(extras, QUINCENA, date(2026, 1, 1), PRIMERA) == (
            Portion(date(2026, 1, 12), date(2026, 1, 12), Decimal(0), 0),
        )
        assert portions(extras, QUINCENA, date(2026, 1, 13), SEGUNDA) == ()
        assert portions(Action(OVERTIME, date(2026, 1, 20), hours=Decimal(1)), QUINCENA, date(2026, 1, 1), PRIMERA) == ()


def rubros(accion, tramo, **opciones):
    return action_items(accion, tramo, QUINCENA_SALARIO, QUINCENA, tasas(), **opciones)


def tramo(desde, hasta, dias, offset=0):
    return Portion(desde, hasta, Decimal(dias), offset)


UN_DIA = tramo(date(2026, 1, 12), date(2026, 1, 12), 0)


class TestLoQueDejaCadaTramo:
    def test_horas_extra_a_tiempo_y_medio(self):
        (rubro,) = rubros(Action(OVERTIME, date(2026, 1, 12), hours=Decimal(4), id=3), UN_DIA)
        assert rubro == PayItem(
            OVERTIME,
            EARNING,
            Money(2500),
            Decimal("1.5"),
            Money(15000),
            action_id=3,
            quantity=Decimal(4),
            applied_from=date(2026, 1, 12),
            applied_to=date(2026, 1, 12),
        )

    def test_dobles_al_doble(self):
        (rubro,) = rubros(Action(DOUBLE_TIME, date(2026, 1, 12), hours=Decimal(8)), UN_DIA)
        assert rubro.amount == Money(40000)

    def test_bonificacion(self):
        (rubro,) = rubros(Action(BONUS, date(2026, 1, 12), amount=Money(50000)), UN_DIA)
        assert (rubro.concept, rubro.amount, rubro.rate) == (BONUS, Money(50000), None)

    @pytest.mark.parametrize("kind", [RAISE, POSITION_CHANGE, TERMINATION])
    def test_lo_del_contrato_no_toca_la_boleta(self, kind):
        assert rubros(Action(kind, date(2026, 1, 12)), UN_DIA) == ()

    @pytest.mark.parametrize("kind", [PAID_LEAVE, VACATION])
    def test_un_permiso_con_goce_deja_un_rubro_de_cero(self, kind):
        """Para que conste que se aplicó: la CCSS pide sus fechas."""
        (rubro,) = rubros(Action(kind, date(2026, 1, 5), date(2026, 1, 7)), tramo(date(2026, 1, 5), date(2026, 1, 7), 3))
        assert (rubro.amount, rubro.quantity) == (Money(0), Decimal(3))

    @pytest.mark.parametrize("kind", [ABSENCE, UNPAID_LEAVE])
    def test_una_ausencia_rebaja_sus_dias(self, kind):
        (rubro,) = rubros(Action(kind, date(2026, 1, 5), date(2026, 1, 6)), tramo(date(2026, 1, 5), date(2026, 1, 6), 2))
        assert rubro.amount == Money(-40000)

    def test_la_incapacidad_rebaja_y_el_patrono_paga_sus_primeros_dias(self):
        rebajo, subsidio = rubros(incapacidad(), tramo(date(2026, 1, 10), date(2026, 1, 15), 6))
        assert (rebajo.concept, rebajo.amount) == (SICK_LEAVE_CCSS, Money(-120000))
        assert (subsidio.concept, subsidio.quantity, subsidio.rate, subsidio.amount) == (
            "sick_leave_subsidy",
            Decimal(3),
            Decimal("0.5"),
            Money(30000),
        )

    def test_en_el_segundo_tramo_esos_dias_ya_pasaron(self):
        assert len(rubros(incapacidad(), tramo(date(2026, 1, 16), date(2026, 1, 20), 5, offset=6))) == 1

    def test_si_el_primer_tramo_empezo_tarde_quedan_los_que_faltan(self):
        _, subsidio = rubros(incapacidad(), tramo(date(2026, 1, 11), date(2026, 1, 15), 5, offset=1))
        assert subsidio.quantity == Decimal(2)

    def test_la_que_prolonga_otra_no_vuelve_a_cobrarle_al_patrono(self):
        assert len(rubros(incapacidad(), tramo(date(2026, 1, 10), date(2026, 1, 15), 6), extends_previous=True)) == 1

    def test_la_del_ins_con_sus_reglas(self):
        rebajo, subsidio = rubros(incapacidad(kind=SICK_LEAVE_INS), tramo(date(2026, 1, 10), date(2026, 1, 15), 6))
        assert (subsidio.concept, subsidio.amount) == ("ins_subsidy", Money(20000))

    def test_la_licencia_de_maternidad(self):
        rebajo, pago = rubros(Action(MATERNITY, date(2026, 1, 1), date(2026, 4, 30)), tramo(PRIMERA.starts_on, PRIMERA.ends_on, 15))
        assert (rebajo.amount, pago.concept, pago.amount) == (Money(-300000), MATERNITY_PAY, Money(150000))

    def test_sin_la_regla_no_se_calcula(self):
        with pytest.raises(RatesMissing):
            action_items(
                incapacidad(),
                tramo(date(2026, 1, 10), date(2026, 1, 15), 6),
                QUINCENA_SALARIO,
                QUINCENA,
                tasas(sick_leave_employer_rate=True),
            )


class TestLasBases:
    def item(self, concept, amount, payer=EARNING):
        return PayItem(concept, payer, Money(0), None, Money(amount))

    def test_el_subsidio_no_cotiza_ni_paga_renta(self):
        items = [
            self.item("base", 300000),
            self.item(OVERTIME, 15000),
            self.item(SICK_LEAVE_CCSS, -120000),
            self.item("sick_leave_subsidy", 30000),
            self.item("sem", 9000, payer=EMPLOYEE),
        ]
        assert contribution_base(items) == Money(195000)
        assert taxable_base(items) == Money(195000)

    def test_la_maternidad_cotiza_sobre_el_salario_entero(self):
        """Art. 95: la base de la CCSS no baja; la renta, sobre lo que paga el patrono."""
        items = [self.item("base", 300000), self.item(MATERNITY, -300000), self.item(MATERNITY_PAY, 150000)]
        assert contribution_base(items) == Money(300000)
        assert taxable_base(items) == Money(150000)

    def test_nunca_es_negativa(self):
        items = [self.item("base", 100000), self.item(ABSENCE, -150000)]
        assert contribution_base(items) == Money(0)
        assert taxable_base(items) == Money(0)


def prestamo(**cambios):
    datos = dict(amount=Money(25000), total_amount=Money(300000), is_recurring=True, id=9)
    datos.update(cambios)
    return Action(DEDUCTION, date(2026, 1, 1), **datos)


class TestLasDeducciones:
    def test_el_saldo_es_lo_pactado_menos_lo_aplicado(self):
        assert remaining_balance(Money(300000), Money(100000)) == Money(200000)
        assert remaining_balance(Money(300000), Money(310000)) == Money(0)

    @pytest.mark.parametrize(
        "aplicado, pide",
        [("0", "25000"), ("290000", "10000"), ("300000", "0")],
    )
    def test_un_prestamo_hasta_agotar_su_saldo(self, aplicado, pide):
        assert deduction_due(prestamo(), PRIMERA, applied=Money(aplicado), applied_before=True) == Money(pide)

    def test_una_que_no_es_recurrente_se_aplica_una_vez(self):
        una = prestamo(is_recurring=False, total_amount=None)
        assert deduction_due(una, PRIMERA, applied=Money(0), applied_before=False) == Money(25000)
        assert deduction_due(una, SEGUNDA, applied=Money(25000), applied_before=True) == Money(0)

    def test_una_pension_sin_tope_sigue(self):
        pension = Action(CHILD_SUPPORT, date(2026, 1, 1), amount=Money(40000), is_recurring=True)
        assert deduction_due(pension, SEGUNDA, applied=Money(40000), applied_before=True) == Money(40000)

    @pytest.mark.parametrize(
        "accion, vigente",
        [
            (prestamo(), True),
            (prestamo(suspended_on=date(2026, 1, 10)), False),
            (prestamo(suspended_on=date(2026, 1, 16)), True),
            (prestamo(ends_on=date(2025, 12, 31)), False),
            (Action(DEDUCTION, date(2026, 1, 16), amount=Money(1)), False),
        ],
    )
    def test_vigente_si_empezo_no_termino_y_no_se_suspendio(self, accion, vigente):
        assert is_active(accion, PRIMERA) is vigente
        pide = deduction_due(accion, PRIMERA, applied=Money(0), applied_before=False)
        assert pide.is_positive is vigente

    def test_el_embargo_se_pide_aparte(self):
        with pytest.raises(InvalidAction):
            deduction_due(Action(GARNISHMENT, date(2026, 1, 1), total_amount=Money(1)), PRIMERA, applied=Money(0), applied_before=False)


MINIMO = Money(300000)


class TestElEmbargo:
    """Art. 172: el mínimo no se toca; ⅛ hasta el triple, ¼ de ahí en adelante."""

    @pytest.mark.parametrize(
        "neto, embargable",
        [
            ("250000", "0"),
            ("300000", "0"),
            ("700000", "50000"),
            ("900000", "75000"),
            ("1300000", "175000"),
        ],
    )
    def test_los_tramos(self, neto, embargable):
        assert garnishment_amount(Money(neto), MINIMO) == Money(embargable)

    def test_una_quincena_lleva_la_mitad_del_mes(self):
        assert garnishment_capacity(Money(350000), SEMIMONTHLY, MINIMO) == Money(25000)

    def test_dos_embargos_se_reparten_el_mismo_tope(self):
        """«No podrá embargarse respecto a un mismo sueldo sino únicamente la
        parte que fuere embargable»: el tope es del salario, no de cada embargo."""
        tope = garnishment_capacity(Money(350000), SEMIMONTHLY, MINIMO)
        # Dos saldos pendientes de 20 000: el primero entra entero, el segundo en lo que queda.
        assert apply_deductions(tope, [Money(20000), Money(20000)]) == (Money(20000), Money(5000))

    def test_la_pension_alimentaria_toma_hasta_la_mitad(self):
        assert child_support_capacity(Money(300000)) == Money(150000)
        assert child_support_capacity(Money(-1)) == Money(0)


class TestElNetoNuncaEsNegativo:
    def test_todas_caben(self):
        assert apply_deductions(Money(100000), [Money(30000), Money(50000)]) == (Money(30000), Money(50000))

    def test_la_que_no_cabe_entra_en_parte_y_la_siguiente_en_nada(self):
        assert apply_deductions(Money(60000), [Money(30000), Money(50000), Money(10000)]) == (
            Money(30000),
            Money(30000),
            Money(0),
        )

    def test_con_neto_negativo_no_se_aplica_ninguna(self):
        assert apply_deductions(Money(-5000), [Money(1000)]) == (Money(0),)

    def test_el_orden_es_pension_embargo_y_las_demas(self):
        acciones = [
            prestamo(id=2),
            Action(GARNISHMENT, date(2026, 1, 1), total_amount=Money(1), id=5),
            prestamo(id=1),
            Action(CHILD_SUPPORT, date(2026, 1, 3), amount=Money(1), id=4),
        ]
        assert [a.id for a in sorted(acciones, key=deduction_order)] == [4, 5, 1, 2]


# ------------------------------------------------------------ el salario base


class TestElSalarioBase:
    def test_el_contrato_que_cubre_el_periodo_cobra_la_quincena_entera(self):
        rubro = base_item(QUINCENA_SALARIO, QUINCENA, PRIMERA, Period(date(2025, 1, 1), date(2030, 1, 1)))
        assert rubro.concept == "base" and rubro.payer == EARNING
        assert rubro.amount == QUINCENA_SALARIO
        assert (rubro.quantity, rubro.applied_from, rubro.applied_to) == (15, PRIMERA.starts_on, PRIMERA.ends_on)

    def test_quien_entra_el_6_cobra_diez_dias(self):
        rubro = base_item(QUINCENA_SALARIO, QUINCENA, PRIMERA, Period(date(2026, 1, 6), date(2030, 1, 1)))
        assert (rubro.quantity, rubro.amount) == (10, Money(200000))
        assert rubro.base == Money(20000)
        assert rubro.applied_from == date(2026, 1, 6)

    def test_quien_sale_el_20_cobra_cinco_dias_de_la_segunda(self):
        rubro = base_item(QUINCENA_SALARIO, QUINCENA, SEGUNDA, Period(date(2025, 1, 1), date(2026, 1, 20)))
        assert (rubro.quantity, rubro.amount) == (5, Money(100000))

    def test_la_segunda_quincena_entera_son_quince_dias_tambien_en_enero(self):
        # Entra el 16: el tramo es el periodo entero y no pasa por el mes comercial.
        rubro = base_item(QUINCENA_SALARIO, QUINCENA, SEGUNDA, Period(date(2026, 1, 16), date(2030, 1, 1)))
        assert rubro.amount == QUINCENA_SALARIO

    def test_fuera_del_periodo_no_hay_rubro(self):
        assert base_item(QUINCENA_SALARIO, QUINCENA, PRIMERA, Period(date(2026, 2, 1), date(2030, 1, 1))) is None
        assert base_item(QUINCENA_SALARIO, QUINCENA, SEGUNDA, Period(date(2025, 1, 1), date(2026, 1, 10))) is None

    def test_en_semana_comercial_se_pagan_siete_dias(self):
        semana = Period(date(2026, 1, 5), date(2026, 1, 11))
        entero = base_item(Money(140000), SEMANA_COMERCIAL, semana, Period(date(2025, 1, 1), date(2030, 1, 1)))
        parcial = base_item(Money(140000), SEMANA_COMERCIAL, semana, Period(date(2026, 1, 9), date(2030, 1, 1)))
        assert (entero.quantity, entero.amount) == (7, Money(140000))
        assert (parcial.quantity, parcial.amount) == (3, Money(60000))
