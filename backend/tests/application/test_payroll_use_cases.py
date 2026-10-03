"""Acciones de personal y corridas (F12, T-1205, T-1206, T-1218).

**Las cifras son inventadas**, como en todo el dominio de planilla: 10 % de
cargas obreras (5 + 4 + 1), 1 % por cada rubro patronal, una prima de riesgos
del 1 %, tramos de renta en 500 000 y 1 000 000, y un salario inembargable de
300 000. Lo que se prueba es que la corrida tome lo que debe, lo parta donde
debe y lo congele; la aritmética de cada rubro ya está probada en el dominio.

El empleado de ejemplo gana 600 000 al mes por quincena: la quincena es
300 000, el día vale 20 000 y la hora 2 500.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.application.ports.ledger import NullLedger
from app.application.use_cases.payroll import (
    APPROVED,
    DRAFT,
    PAID,
    REGULAR,
    SETTLEMENT,
    SYSTEM,
    ActionAlreadyCancelled,
    ActionAlreadySuspended,
    ActionNotEditable,
    ActionNotFound,
    ActionNotRecurring,
    ActionRequest,
    ApproveRun,
    CalculateRun,
    CancelAction,
    ContractMissing,
    CreateRun,
    EmployeeNotFound,
    EmployeeTerminated,
    PayRun,
    PositionNotFound,
    RegisterAction,
    RunAlreadyExists,
    RunAlreadyPaid,
    RunNotApproved,
    RunNotCalculated,
    RunNotEditable,
    RunNotFound,
    ScheduleNotFound,
    SuspendAction,
    TerminateEmployee,
    UpdateAction,
)
from app.domain.errors import (
    InvalidAction,
    InvalidContract,
    InvalidCutDate,
    InvalidEmployee,
    InvalidSchedule,
    RatesMissing,
)
from app.domain.money import Money
from app.domain.payroll import EMPLOYEE, EMPLOYER, REQUIRED_CONTRIBUTIONS, RULE, Rate, TaxBracket, TaxCredits
from app.domain.payroll_actions import (
    BONUS,
    CHILD_SUPPORT,
    DEDUCTION,
    GARNISHMENT,
    OVERTIME,
    POSITION_CHANGE,
    RAISE,
    SICK_LEAVE_CCSS,
    TERMINATION,
)
from app.domain.payroll_calendar import Period

from .fakes import FakeUnitOfWork
from .fakes_payroll import (
    FakeActionRepository,
    FakeEmployeeRepository,
    FakePayrollRepository,
    FakePayrollSettings,
    FakeRateTable,
    FakeScheduleRepository,
    FilaDeAccion,
    FilaDeContrato,
    FilaDeCorrida,
    FilaDeEmpleado,
    FilaDeJornada,
    LibroEspia,
    RelojFijo,
)

D = Decimal
ENE_1, ENE_15, ENE_16, ENE_31 = date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 16), date(2026, 1, 31)
AHORA = datetime(2026, 1, 20, 9, 0)
USUARIO = 42

QUINCENAL = FilaDeJornada(1, "Quincenal", "semimonthly", first_cut_day=15)
APAGADA = FilaDeJornada(2, "Vieja", "monthly", is_active=False)

REGLAS = {
    "sick_leave_employer_days": "3",
    "sick_leave_employer_rate": "0.5",
    "ins_employer_days": "1",
    "ins_employer_rate": "1",
    "maternity_employer_rate": "0.5",
    "minimum_wage_unseizable": "300000",
}
OBRERAS = {"sem": "0.05", "ivm": "0.04", "banco_popular": "0.01"}


def tasas_inventadas(*sin: str) -> list[Rate]:
    filas = [Rate(c, EMPLOYEE, D(v), ENE_1) for c, v in OBRERAS.items() if c not in sin]
    filas += [Rate(c, EMPLOYER, D("0.01"), ENE_1) for c, p in sorted(REQUIRED_CONTRIBUTIONS["CR"]) if p == EMPLOYER]
    filas += [Rate(c, RULE, D(v), ENE_1) for c, v in REGLAS.items()]
    return filas


TRAMOS = [
    TaxBracket(Money(0), Money(500000), D(0)),
    TaxBracket(Money(500000), Money(1000000), D("0.10")),
    TaxBracket(Money(1000000), None, D("0.15")),
]
CREDITOS = TaxCredits(Money(1000), Money(2000))


def empleado(id: int = 1, hired_on: date = date(2025, 6, 1), **cambios) -> FilaDeEmpleado:
    return FilaDeEmpleado(id=id, hired_on=hired_on, **cambios)


def contrato(id: int = 1, employee_id: int = 1, valid_from: date = date(2025, 6, 1), salario: str = "300000", **cambios) -> FilaDeContrato:
    datos = dict(schedule_id=1, position_id=1, ins_policy_id=None, valid_to=None, solidarista_rate=None)
    datos.update(cambios)
    return FilaDeContrato(id=id, employee_id=employee_id, valid_from=valid_from, period_salary=D(salario), **datos)


def corrida(id: int = 1, desde: date = ENE_1, hasta: date = ENE_15, **cambios) -> FilaDeCorrida:
    datos = dict(kind=REGULAR, schedule_id=1, pay_date=hasta, created_by=USUARIO, created_at=AHORA)
    datos.update(cambios)
    return FilaDeCorrida(id=id, period_from=desde, period_to=hasta, **datos)


def accion(id: int, kind: str, starts_on: date, **cambios) -> FilaDeAccion:
    return FilaDeAccion(id=id, employee_id=1, kind=kind, starts_on=starts_on, **cambios)


class Mundo:
    """Una compañía con su jornada quincenal y lo que cada prueba le ponga."""

    def __init__(
        self,
        *,
        empleados=None,
        contratos=None,
        acciones=None,
        corridas=None,
        tasas=None,
        settings=None,
        puestos=None,
        polizas=None,
        poliza_por_omision=D("0.01"),
    ):
        self.jornadas = FakeScheduleRepository([QUINCENAL, APAGADA])
        self.empleados = FakeEmployeeRepository(
            empleados if empleados is not None else [empleado()],
            contratos if contratos is not None else [contrato()],
            puestos=puestos,
            polizas=polizas,
            poliza_por_omision=poliza_por_omision,
        )
        self.corridas = FakePayrollRepository(corridas if corridas is not None else [corrida()])
        self.acciones = FakeActionRepository(acciones or [], runs=self.corridas)
        self.tasas = FakeRateTable(tasas if tasas is not None else tasas_inventadas(), TRAMOS, CREDITOS)
        self.settings = FakePayrollSettings(**(settings or {}))
        self.uow = FakeUnitOfWork()
        self.reloj = RelojFijo(AHORA)

    # casos de uso, ya cableados
    def calcular(self, run_id: int = 1):
        return CalculateRun(
            runs=self.corridas,
            schedules=self.jornadas,
            employees=self.empleados,
            actions=self.acciones,
            rates=self.tasas,
            settings=self.settings,
            uow=self.uow,
        )(run_id)

    def crear(self, schedule_id: int, corte: date, **opciones):
        return CreateRun(runs=self.corridas, schedules=self.jornadas, uow=self.uow, clock=self.reloj)(
            schedule_id, corte, user_id=USUARIO, **opciones
        )

    def aprobar(self, run_id: int) -> None:
        ApproveRun(runs=self.corridas, uow=self.uow, clock=self.reloj)(run_id, user_id=USUARIO)

    def pagar(self, run_id: int, libro=None):
        return PayRun(runs=self.corridas, ledger=libro or NullLedger(), uow=self.uow, clock=self.reloj)(
            run_id, user_id=USUARIO
        )

    def registrar(self, request: ActionRequest) -> int:
        return RegisterAction(employees=self.empleados, actions=self.acciones, uow=self.uow, clock=self.reloj)(
            request, user_id=USUARIO
        )

    def editar(self, action_id: int, request: ActionRequest) -> None:
        UpdateAction(actions=self.acciones, uow=self.uow)(action_id, request)

    def anular(self, action_id: int, memo: str | None = None) -> int:
        return CancelAction(actions=self.acciones, uow=self.uow, clock=self.reloj)(
            action_id, user_id=USUARIO, memo=memo
        )

    def suspender(self, action_id: int, reason: str = "pidió pausa") -> None:
        SuspendAction(actions=self.acciones, uow=self.uow, clock=self.reloj)(
            action_id, user_id=USUARIO, reason=reason
        )

    def dar_de_baja(self, employee_id: int, on: date, cause: str = "resignation") -> int:
        return TerminateEmployee(
            employees=self.empleados, actions=self.acciones, runs=self.corridas, uow=self.uow, clock=self.reloj
        )(employee_id, on=on, cause=cause, user_id=USUARIO)

    # atajos para leer
    def linea(self, run_id: int = 1, employee_id: int = 1):
        return next(l for l in self.corridas.lineas[run_id] if l.employee_id == employee_id)


def rubros(linea, concepto: str, payer: str | None = None):
    return [i for i in linea.items if i.concept == concepto and (payer is None or i.payer == payer)]


def monto(linea, concepto: str, payer: str | None = None) -> Money:
    return Money.sum(i.amount for i in rubros(linea, concepto, payer))


# --------------------------------------------------------------- la corrida


class TestLaCorridaSimple:
    def test_la_quincena_entera_con_sus_cargas_y_su_renta(self):
        mundo = Mundo()
        resultado = mundo.calcular()

        assert (resultado.run_id, resultado.period, resultado.closes_month) == (1, Period(ENE_1, ENE_15), False)
        linea = mundo.linea()
        assert monto(linea, "base") == Money(300000)
        assert (monto(linea, "sem", EMPLOYEE), monto(linea, "ivm", EMPLOYEE), monto(linea, "banco_popular", EMPLOYEE)) == (
            Money(15000),
            Money(12000),
            Money(3000),
        )
        # 600 000 al mes caen en el tramo del 10 % por encima de 500 000: 10 000 al
        # mes, 5 000 por quincena (RN-73).
        assert linea.income_tax == Money(5000)
        assert (linea.gross, linea.employee_deductions, linea.other_deductions) == (
            Money(300000),
            Money(30000),
            Money.zero(),
        )
        assert linea.net == Money(265000)
        # Diez rubros patronales al 1 % más la prima de riesgos de la póliza por omisión.
        assert len(rubros(linea, "rt", EMPLOYER)) == 1
        assert linea.employer_charges == Money(33000)
        assert linea.contract_id == 1

    def test_los_rubros_llevan_base_tasa_y_monto(self):
        """RN-66: lo que se guarda alcanza para reimprimir sin recalcular."""
        mundo = Mundo()
        mundo.calcular()
        sem = rubros(mundo.linea(), "sem", EMPLOYEE)[0]
        assert (sem.base, sem.rate, sem.amount) == (Money(300000), D("0.05"), Money(15000))

    def test_los_creditos_fiscales_bajan_la_renta(self):
        mundo = Mundo(empleados=[empleado(dependent_children=2, spouse_credit=True)])
        mundo.calcular()
        # 10 000 − 2 × 1 000 − 2 000 = 6 000 al mes; 3 000 la quincena.
        assert mundo.linea().income_tax == Money(3000)

    def test_el_ina_exento_no_se_cobra(self):
        mundo = Mundo(settings={"ina_exempt": True})
        mundo.calcular()
        linea = mundo.linea()
        assert rubros(linea, "ina") == []
        assert linea.employer_charges == Money(30000)

    def test_la_prima_es_la_de_la_poliza_del_contrato(self):
        mundo = Mundo(contratos=[contrato(ins_policy_id=9)], polizas={9: D("0.05")})
        mundo.calcular()
        assert monto(mundo.linea(), "rt", EMPLOYER) == Money(15000)

    def test_el_solidarista_del_contrato_se_rebaja(self):
        mundo = Mundo(contratos=[contrato(solidarista_rate=D("0.05"))])
        mundo.calcular()
        linea = mundo.linea()
        assert monto(linea, "solidarista", EMPLOYEE) == Money(15000)
        assert linea.other_deductions == Money(15000)
        assert linea.net == Money(250000)

    def test_quien_entra_el_6_cobra_diez_dias(self):
        mundo = Mundo(empleados=[empleado(hired_on=date(2026, 1, 6))], contratos=[contrato(valid_from=date(2026, 1, 6))])
        mundo.calcular()
        base = rubros(mundo.linea(), "base")[0]
        assert (base.quantity, base.amount, base.applied_from) == (10, Money(200000), date(2026, 1, 6))

    def test_quien_salio_el_10_cobra_hasta_el_10(self):
        mundo = Mundo(empleados=[empleado(terminated_on=date(2026, 1, 10))], contratos=[contrato(valid_to=date(2026, 1, 10))])
        mundo.calcular()
        assert monto(mundo.linea(), "base") == Money(200000)

    def test_quien_salio_antes_del_periodo_no_entra(self):
        mundo = Mundo(empleados=[empleado(terminated_on=date(2025, 12, 31))])
        resultado = mundo.calcular()
        assert resultado.lines == ()

    def test_un_aumento_a_mitad_de_quincena_deja_dos_bases(self):
        mundo = Mundo(
            contratos=[
                contrato(valid_to=date(2026, 1, 7)),
                contrato(id=2, valid_from=date(2026, 1, 8), salario="450000"),
            ]
        )
        mundo.calcular()
        bases = rubros(mundo.linea(), "base")
        assert [(b.quantity, b.amount) for b in bases] == [(7, Money(140000)), (8, Money(240000))]
        assert mundo.linea().contract_id == 2

    def test_un_contrato_que_empieza_despues_de_la_baja_no_deja_rubro(self):
        # La fila existe por un error de carga; el cálculo no inventa días.
        mundo = Mundo(
            empleados=[empleado(terminated_on=date(2026, 1, 7))],
            contratos=[contrato(valid_to=date(2026, 1, 7)), contrato(id=2, valid_from=date(2026, 1, 8))],
        )
        mundo.calcular()
        assert len(rubros(mundo.linea(), "base")) == 1

    def test_sin_tasas_no_se_calcula(self):
        mundo = Mundo(tasas=tasas_inventadas("ivm"))
        with pytest.raises(RatesMissing) as e:
            mundo.calcular()
        assert "ivm:employee" in e.value.missing

    def test_recalcular_reescribe_el_borrador(self):
        mundo = Mundo()
        mundo.calcular()
        mundo.acciones.acciones.append(accion(1, BONUS, date(2026, 1, 10), amount=D(50000)))
        mundo.calcular()
        assert len(mundo.corridas.lineas[1]) == 1
        assert mundo.linea().gross == Money(350000)


class TestLaRentaDelMes:
    def test_la_segunda_quincena_liquida_lo_del_mes(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)])
        mundo.calcular(1)
        mundo.aprobar(1)
        resultado = mundo.calcular(2)
        assert resultado.closes_month is True
        # 600 000 en el mes → 10 000; la primera retuvo 5 000.
        assert mundo.linea(2).income_tax == Money(5000)

    def test_las_extras_de_la_segunda_cuadran_el_mes(self):
        mundo = Mundo(
            corridas=[corrida(), corrida(2, ENE_16, ENE_31)],
            acciones=[accion(1, OVERTIME, date(2026, 1, 20), hours=D(4))],
        )
        mundo.calcular(1)
        mundo.aprobar(1)
        mundo.calcular(2)
        linea = mundo.linea(2)
        assert monto(linea, OVERTIME) == Money(15000)
        # 615 000 en el mes → 11 500; menos los 5 000 ya retenidos.
        assert linea.income_tax == Money(6500)
        assert linea.net == Money(277000)

    def test_un_borrador_anterior_no_cuenta_como_retenido(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)])
        mundo.calcular(1)
        mundo.calcular(2)
        assert mundo.linea(2).income_tax == Money.zero()


class TestLasAccionesEntranEnSuCorrida:
    def test_las_horas_extra_y_la_bonificacion(self):
        mundo = Mundo(
            acciones=[
                accion(1, OVERTIME, date(2026, 1, 10), hours=D(4)),
                accion(2, BONUS, date(2026, 1, 12), amount=D(20000)),
                accion(3, OVERTIME, date(2026, 1, 20), hours=D(4)),  # de la otra quincena
            ]
        )
        mundo.calcular()
        linea = mundo.linea()
        assert monto(linea, OVERTIME) == Money(15000)
        assert monto(linea, BONUS) == Money(20000)
        assert rubros(linea, OVERTIME)[0].action_id == 1
        assert linea.gross == Money(335000)

    def test_la_incapacidad_que_cruza_la_quincena_se_parte(self):
        mundo = Mundo(
            corridas=[corrida(), corrida(2, ENE_16, ENE_31)],
            acciones=[accion(1, SICK_LEAVE_CCSS, date(2026, 1, 10), ends_on=date(2026, 1, 20))],
        )
        mundo.calcular(1)
        primera = mundo.linea(1)
        ausencia = rubros(primera, SICK_LEAVE_CCSS)[0]
        assert (ausencia.quantity, ausencia.amount, ausencia.applied_from, ausencia.applied_to) == (
            6,
            Money(-120000),
            date(2026, 1, 10),
            ENE_15,
        )
        # El patrono paga tres días a la mitad; el subsidio no cotiza.
        assert monto(primera, "sick_leave_subsidy") == Money(30000)
        assert (primera.gross, primera.employee_deductions) == (Money(210000), Money(18000))

        mundo.aprobar(1)
        mundo.calcular(2)
        segunda = mundo.linea(2)
        resto = rubros(segunda, SICK_LEAVE_CCSS)[0]
        assert (resto.quantity, resto.applied_from, resto.applied_to) == (5, ENE_16, date(2026, 1, 20))
        assert rubros(segunda, "sick_leave_subsidy") == []

    def test_la_que_llego_tarde_entra_en_la_siguiente_con_sus_fechas(self):
        """RN-91: la quincena pagada no se toca; la siguiente recoge el tramo."""
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)])
        mundo.calcular(1)
        mundo.aprobar(1)
        mundo.acciones.acciones.append(accion(1, SICK_LEAVE_CCSS, date(2026, 1, 12), ends_on=date(2026, 1, 17)))
        mundo.calcular(2)
        tramos = rubros(mundo.linea(2), SICK_LEAVE_CCSS)
        assert [(t.applied_from, t.applied_to, t.quantity) for t in tramos] == [
            (date(2026, 1, 12), ENE_15, 4),
            (ENE_16, date(2026, 1, 17), 2),
        ]

    def test_la_incapacidad_que_prolonga_otra_no_vuelve_a_cobrarle_al_patrono(self):
        mundo = Mundo(
            acciones=[
                accion(1, SICK_LEAVE_CCSS, date(2026, 1, 2), ends_on=date(2026, 1, 5)),
                accion(2, SICK_LEAVE_CCSS, date(2026, 1, 6), ends_on=date(2026, 1, 9)),
            ]
        )
        mundo.calcular()
        subsidios = rubros(mundo.linea(), "sick_leave_subsidy")
        assert len(subsidios) == 1 and subsidios[0].action_id == 1

    def test_las_del_contrato_no_dejan_rubro(self):
        mundo = Mundo(acciones=[accion(1, RAISE, date(2026, 1, 5), new_salary=D(400000))])
        mundo.calcular()
        assert [i.concept for i in mundo.linea().items if i.action_id] == []


class TestLasDeducciones:
    def test_el_prestamo_recurrente_baja_su_saldo(self):
        prestamo = accion(1, DEDUCTION, ENE_1, amount=D(25000), total_amount=D(300000), is_recurring=True)
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)], acciones=[prestamo])
        mundo.calcular(1)
        cuota = rubros(mundo.linea(1), DEDUCTION, EMPLOYEE)[0]
        assert (cuota.amount, cuota.action_id, cuota.applied_from, cuota.applied_to) == (Money(25000), 1, ENE_1, ENE_15)
        assert mundo.linea(1).net == Money(240000)
        mundo.aprobar(1)
        mundo.calcular(2)
        assert monto(mundo.linea(2), DEDUCTION, EMPLOYEE) == Money(25000)
        assert Money.sum(Money(i.amount) for i in mundo.acciones.applied(1)) == Money(25000)

    def test_la_cuota_final_es_lo_que_queda(self):
        mundo = Mundo(acciones=[accion(1, DEDUCTION, ENE_1, amount=D(25000), total_amount=D(10000), is_recurring=True)])
        mundo.calcular()
        assert monto(mundo.linea(), DEDUCTION, EMPLOYEE) == Money(10000)

    def test_la_no_recurrente_se_aplica_una_sola_vez(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)], acciones=[accion(1, DEDUCTION, ENE_1, amount=D(5000))])
        mundo.calcular(1)
        mundo.aprobar(1)
        mundo.calcular(2)
        assert monto(mundo.linea(1), DEDUCTION, EMPLOYEE) == Money(5000)
        assert rubros(mundo.linea(2), DEDUCTION, EMPLOYEE) == []

    def test_la_suspendida_ya_no_se_toma(self):
        # Se suspende el 20: la quincena que termina el 15 todavía la cobra, la
        # que termina el 31 ya no (RN-92: lo ya aplicado no se toca).
        mundo = Mundo(
            corridas=[corrida(), corrida(2, ENE_16, ENE_31)],
            acciones=[accion(1, DEDUCTION, ENE_1, amount=D(25000), is_recurring=True)],
        )
        mundo.suspender(1)
        mundo.calcular(1)
        mundo.calcular(2)
        assert monto(mundo.linea(1), DEDUCTION, EMPLOYEE) == Money(25000)
        assert rubros(mundo.linea(2), DEDUCTION, EMPLOYEE) == []

    def test_el_embargo_toma_un_octavo_del_exceso_del_mes_repartido(self):
        mundo = Mundo(acciones=[accion(1, GARNISHMENT, ENE_1, total_amount=D(100000))])
        mundo.calcular()
        # Neto mensual 530 000: (530 000 − 300 000) / 8 = 28 750 al mes; la mitad.
        assert monto(mundo.linea(), GARNISHMENT, EMPLOYEE) == Money(14375)

    def test_el_embargo_con_cuota_pactada_no_pasa_de_ella(self):
        mundo = Mundo(acciones=[accion(1, GARNISHMENT, ENE_1, amount=D(10000), total_amount=D(100000))])
        mundo.calcular()
        assert monto(mundo.linea(), GARNISHMENT, EMPLOYEE) == Money(10000)

    def test_dos_embargos_se_reparten_un_solo_tope(self):
        mundo = Mundo(
            acciones=[
                accion(1, GARNISHMENT, ENE_1, total_amount=D(100000)),
                accion(2, GARNISHMENT, date(2026, 1, 2), total_amount=D(100000)),
            ]
        )
        mundo.calcular()
        embargos = rubros(mundo.linea(), GARNISHMENT, EMPLOYEE)
        assert [(e.action_id, e.amount) for e in embargos] == [(1, Money(14375))]

    def test_el_embargo_vencido_no_toma_nada(self):
        mundo = Mundo(acciones=[accion(1, GARNISHMENT, date(2025, 1, 1), ends_on=date(2025, 12, 31), total_amount=D(100000))])
        mundo.calcular()
        assert rubros(mundo.linea(), GARNISHMENT, EMPLOYEE) == []

    def test_la_pension_alimentaria_hasta_la_mitad_y_primero(self):
        mundo = Mundo(
            acciones=[
                accion(1, DEDUCTION, ENE_1, amount=D(200000), is_recurring=True),
                accion(2, CHILD_SUPPORT, ENE_1, amount=D(200000), is_recurring=True),
            ]
        )
        mundo.calcular()
        linea = mundo.linea()
        # Neto 265 000: la pensión toma la mitad, 132 500; la deducción, lo que queda.
        assert monto(linea, CHILD_SUPPORT, EMPLOYEE) == Money(132500)
        assert monto(linea, DEDUCTION, EMPLOYEE) == Money(132500)
        assert linea.net == Money.zero()

    def test_lo_que_no_cabe_no_deja_rubro_ni_deuda(self):
        mundo = Mundo(
            acciones=[
                accion(1, DEDUCTION, ENE_1, amount=D(300000)),
                accion(2, DEDUCTION, date(2026, 1, 2), amount=D(1000)),
            ]
        )
        mundo.calcular()
        linea = mundo.linea()
        deducciones = rubros(linea, DEDUCTION, EMPLOYEE)
        assert [(d.action_id, d.base, d.amount) for d in deducciones] == [(1, Money(300000), Money(265000))]
        assert linea.net == Money.zero()


class TestLaAnulacion:
    def test_lo_aplicado_se_revierte_en_la_siguiente(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)], acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))])
        mundo.calcular(1)
        mundo.aprobar(1)
        anulacion = mundo.anular(1, memo="no eran de ella")
        mundo.calcular(2)
        reverso = rubros(mundo.linea(2), OVERTIME)
        assert [(r.action_id, r.amount, r.applied_from) for r in reverso] == [(anulacion, Money(-15000), date(2026, 1, 10))]
        assert mundo.linea(2).gross == Money(285000)

    def test_una_deduccion_aplicada_y_anulada_se_devuelve(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31)], acciones=[accion(1, DEDUCTION, ENE_1, amount=D(5000))])
        mundo.calcular(1)
        mundo.aprobar(1)
        mundo.anular(1)
        mundo.calcular(2)
        linea = mundo.linea(2)
        assert monto(linea, DEDUCTION, EMPLOYEE) == Money(-5000)
        assert linea.other_deductions == Money(-5000)
        assert linea.net == Money(270000)

    def test_la_anulada_sin_aplicar_deja_un_rubro_de_cero(self):
        mundo = Mundo(acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))])
        anulacion = mundo.anular(1)
        mundo.calcular()
        extras = rubros(mundo.linea(), OVERTIME)
        assert [(e.action_id, e.amount) for e in extras] == [(anulacion, Money.zero())]

    def test_la_anulacion_ya_aplicada_no_se_repite(self):
        mundo = Mundo(
            corridas=[corrida(), corrida(2, ENE_16, ENE_31), corrida(3, date(2026, 2, 1), date(2026, 2, 15))],
            acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))],
        )
        mundo.calcular(1)
        mundo.aprobar(1)
        mundo.anular(1)
        mundo.calcular(2)
        mundo.aprobar(2)
        mundo.calcular(3)
        assert rubros(mundo.linea(3), OVERTIME) == []


class TestElEstadoDeLaCorrida:
    def test_lo_que_no_se_calcula(self):
        mundo = Mundo(
            corridas=[
                corrida(1, status=PAID),
                corrida(2, status=APPROVED),
                corrida(3, kind=SETTLEMENT, schedule_id=None),
            ]
        )
        with pytest.raises(RunNotFound):
            mundo.calcular(9)
        with pytest.raises(RunAlreadyPaid):
            mundo.calcular(1)
        with pytest.raises(RunNotEditable) as e:
            mundo.calcular(2)
        assert e.value.reason == APPROVED
        with pytest.raises(RunNotEditable) as e:
            mundo.calcular(3)
        assert e.value.reason == SETTLEMENT

    def test_aprobar(self):
        mundo = Mundo(corridas=[corrida(), corrida(2, ENE_16, ENE_31, status=PAID)])
        with pytest.raises(RunNotFound):
            mundo.aprobar(9)
        with pytest.raises(RunAlreadyPaid):
            mundo.aprobar(2)
        with pytest.raises(RunNotCalculated):
            mundo.aprobar(1)
        mundo.calcular(1)
        mundo.aprobar(1)
        fila = mundo.corridas.get_run(1)
        assert (fila.status, fila.approved_by, fila.approved_at) == (APPROVED, USUARIO, AHORA)
        with pytest.raises(RunNotEditable):
            mundo.aprobar(1)

    def test_pagar_con_libro(self):
        mundo = Mundo()
        mundo.calcular(1)
        with pytest.raises(RunNotApproved) as e:
            mundo.pagar(1)
        assert e.value.status == DRAFT
        mundo.aprobar(1)
        libro = LibroEspia(asiento=77)
        assert mundo.pagar(1, libro) == 77
        fila = mundo.corridas.get_run(1)
        assert (fila.status, fila.paid_by, fila.paid_at, fila.journal_entry_id) == (PAID, USUARIO, AHORA, 77)
        [pagada] = libro.pagadas
        assert (pagada.id, pagada.date, pagada.gross, pagada.net) == (1, ENE_15, Money(300000), Money(265000))
        assert (pagada.social_security, pagada.income_tax, pagada.employer_charges) == (
            Money(30000),
            Money(5000),
            Money(33000),
        )
        with pytest.raises(RunAlreadyPaid):
            mundo.pagar(1, libro)
        with pytest.raises(RunNotFound):
            mundo.pagar(9)

    def test_pagar_sin_libro(self):
        mundo = Mundo()
        mundo.calcular(1)
        mundo.aprobar(1)
        assert mundo.pagar(1) is None
        assert mundo.corridas.get_run(1).journal_entry_id is None


class TestCrearLaCorrida:
    def test_el_periodo_sale_del_corte(self):
        mundo = Mundo(corridas=[])
        fila = mundo.crear(1, ENE_31)
        assert (fila.kind, fila.schedule_id, fila.period_from, fila.period_to, fila.pay_date) == (
            REGULAR,
            1,
            ENE_16,
            ENE_31,
            ENE_31,
        )
        assert (fila.status, fila.created_by, fila.created_at) == (DRAFT, USUARIO, AHORA)

    def test_con_fecha_de_pago_propia(self):
        mundo = Mundo(corridas=[])
        assert mundo.crear(1, ENE_15, pay_date=date(2026, 1, 17)).pay_date == date(2026, 1, 17)

    def test_lo_que_no_se_crea(self):
        mundo = Mundo()
        with pytest.raises(ScheduleNotFound):
            mundo.crear(9, ENE_15)
        with pytest.raises(InvalidSchedule) as e:
            mundo.crear(2, ENE_31)
        assert e.value.reason == "inactive"
        with pytest.raises(InvalidCutDate):
            mundo.crear(1, date(2026, 1, 20))
        with pytest.raises(RunAlreadyExists) as e:
            mundo.crear(1, ENE_15)
        assert e.value.run_id == 1


# ------------------------------------------------------ las acciones


def pedido(kind: str = BONUS, starts_on: date = date(2026, 1, 10), **cambios) -> ActionRequest:
    datos = dict(employee_id=1, amount=Money(20000) if kind == BONUS else None)
    datos.update(cambios)
    return ActionRequest(kind=kind, starts_on=starts_on, **datos)


class TestRegistrarUnaAccion:
    def test_queda_en_el_empleado_con_quien_y_cuando(self):
        mundo = Mundo()
        nueva = mundo.registrar(pedido(memo="por el inventario"))
        fila = mundo.acciones.get(nueva)
        assert (fila.employee_id, fila.kind, fila.amount, fila.memo) == (1, BONUS, D(20000), "por el inventario")
        assert (fila.source, fila.created_by, fila.created_at) == ("manual", USUARIO, AHORA)

    def test_lo_que_no_se_registra(self):
        mundo = Mundo(empleados=[empleado(), empleado(2, terminated_on=date(2026, 1, 5))], contratos=[contrato()])
        with pytest.raises(InvalidAction) as e:
            mundo.registrar(pedido(TERMINATION, amount=None))
        assert (e.value.field, e.value.reason) == ("kind", "not_allowed")
        with pytest.raises(InvalidAction):
            mundo.registrar(pedido(OVERTIME, amount=None))
        with pytest.raises(EmployeeNotFound):
            mundo.registrar(pedido(employee_id=9))
        with pytest.raises(EmployeeTerminated):
            mundo.registrar(pedido(employee_id=2))
        with pytest.raises(ContractMissing):
            mundo.registrar(pedido(starts_on=date(2025, 1, 10)))

    def test_una_bonificacion_el_dia_de_la_salida_todavia_entra(self):
        mundo = Mundo(empleados=[empleado(terminated_on=date(2026, 1, 10))])
        assert mundo.registrar(pedido()) == 1

    def test_el_aumento_cierra_el_contrato_y_abre_otro(self):
        mundo = Mundo(contratos=[contrato(solidarista_rate=D("0.03"), ins_policy_id=4)])
        mundo.registrar(pedido(RAISE, amount=None, new_salary=Money(400000)))
        viejo, nuevo = mundo.empleados.contracts_of(1)
        assert viejo.valid_to == date(2026, 1, 9)
        assert (nuevo.valid_from, nuevo.period_salary, nuevo.position_id) == (date(2026, 1, 10), D(400000), 1)
        assert (nuevo.schedule_id, nuevo.ins_policy_id, nuevo.solidarista_rate) == (1, 4, D("0.03"))

    def test_el_aumento_no_puede_caer_el_dia_en_que_empezo_el_contrato(self):
        mundo = Mundo()
        with pytest.raises(InvalidContract) as e:
            mundo.registrar(pedido(RAISE, starts_on=date(2025, 6, 1), amount=None, new_salary=Money(400000)))
        assert e.value.reason == "overlaps"

    def test_el_cambio_de_puesto(self):
        mundo = Mundo(puestos={1: True, 2: True, 3: False})
        mundo.registrar(pedido(POSITION_CHANGE, amount=None, position_id=2))
        _, nuevo = mundo.empleados.contracts_of(1)
        assert (nuevo.position_id, nuevo.period_salary) == (2, D(300000))
        with pytest.raises(PositionNotFound):
            mundo.registrar(pedido(POSITION_CHANGE, starts_on=date(2026, 1, 20), amount=None, position_id=9))
        with pytest.raises(InvalidContract) as e:
            mundo.registrar(pedido(POSITION_CHANGE, starts_on=date(2026, 1, 20), amount=None, position_id=3))
        assert (e.value.field, e.value.reason) == ("position_id", "inactive")


class TestEditarUnaAccion:
    def test_se_corrige_lo_que_nadie_aplico(self):
        mundo = Mundo(acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))])
        mundo.editar(1, pedido(OVERTIME, starts_on=date(2026, 1, 11), amount=None, hours=D(6), memo="eran seis"))
        fila = mundo.acciones.get(1)
        assert (fila.kind, fila.starts_on, fila.hours, fila.memo) == (OVERTIME, date(2026, 1, 11), D(6), "eran seis")

    def test_lo_que_no_se_edita(self):
        mundo = Mundo(
            acciones=[
                accion(1, OVERTIME, date(2026, 1, 10), hours=D(4)),
                accion(2, RAISE, date(2026, 1, 5), new_salary=D(400000)),
            ]
        )
        with pytest.raises(ActionNotFound):
            mundo.editar(9, pedido())
        with pytest.raises(ActionNotEditable) as e:
            mundo.editar(2, pedido())
        assert e.value.reason == "contract"
        with pytest.raises(InvalidAction):
            mundo.editar(1, pedido(OVERTIME, amount=None, hours=None))

        anulacion = mundo.anular(1)
        with pytest.raises(ActionNotEditable) as e:
            mundo.editar(anulacion, pedido())
        assert e.value.reason == "cancellation"
        with pytest.raises(ActionAlreadyCancelled):
            mundo.editar(1, pedido(OVERTIME, amount=None, hours=D(5)))

    def test_la_aplicada_en_una_corrida_no_se_edita(self):
        mundo = Mundo(acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))])
        mundo.calcular(1)
        mundo.aprobar(1)
        with pytest.raises(ActionNotEditable) as e:
            mundo.editar(1, pedido(OVERTIME, amount=None, hours=D(5)))
        assert e.value.reason == "applied"


class TestAnularUnaAccion:
    def test_queda_otra_que_la_referencia(self):
        mundo = Mundo(acciones=[accion(1, OVERTIME, date(2026, 1, 10), hours=D(4))])
        nueva = mundo.anular(1, memo="no eran de ella")
        fila = mundo.acciones.get(nueva)
        assert (fila.kind, fila.starts_on, fila.cancels_action_id, fila.memo) == (OVERTIME, date(2026, 1, 10), 1, "no eran de ella")
        assert (fila.hours, fila.created_by) == (None, USUARIO)

    def test_lo_que_no_se_anula(self):
        mundo = Mundo(
            acciones=[
                accion(1, OVERTIME, date(2026, 1, 10), hours=D(4)),
                accion(2, RAISE, date(2026, 1, 5), new_salary=D(400000)),
            ]
        )
        with pytest.raises(ActionNotFound):
            mundo.anular(9)
        with pytest.raises(ActionNotEditable) as e:
            mundo.anular(2)
        assert e.value.reason == "contract"
        anulacion = mundo.anular(1)
        with pytest.raises(ActionNotEditable) as e:
            mundo.anular(anulacion)
        assert e.value.reason == "cancellation"
        with pytest.raises(ActionAlreadyCancelled):
            mundo.anular(1)


class TestSuspenderUnaDeduccion:
    def test_queda_quien_cuando_y_por_que(self):
        mundo = Mundo(acciones=[accion(1, DEDUCTION, ENE_1, amount=D(25000), is_recurring=True)])
        mundo.suspender(1, "pidió pausa")
        fila = mundo.acciones.get(1)
        assert (fila.suspended_at, fila.suspended_by, fila.suspension_reason) == (AHORA, USUARIO, "pidió pausa")
        with pytest.raises(ActionAlreadySuspended):
            mundo.suspender(1)

    def test_solo_las_recurrentes(self):
        mundo = Mundo(
            acciones=[
                accion(1, DEDUCTION, ENE_1, amount=D(25000)),
                accion(2, GARNISHMENT, ENE_1, total_amount=D(100000)),
                accion(3, CHILD_SUPPORT, ENE_1, amount=D(25000), is_recurring=True),
            ]
        )
        with pytest.raises(ActionNotFound):
            mundo.suspender(9)
        with pytest.raises(ActionNotRecurring):
            mundo.suspender(1)
        with pytest.raises(ActionNotRecurring):
            mundo.suspender(2)
        mundo.anular(3)
        with pytest.raises(ActionAlreadyCancelled):
            mundo.suspender(3)


class TestLaBaja:
    def test_cierra_el_contrato_registra_la_accion_y_abre_la_liquidacion(self):
        mundo = Mundo(contratos=[contrato(valid_to=date(2025, 12, 31)), contrato(id=2, valid_from=ENE_1)])
        liquidacion = mundo.dar_de_baja(1, date(2026, 1, 20), "dismissal_without_cause")

        viejo, vigente = mundo.empleados.contracts_of(1)
        assert viejo.valid_to == date(2025, 12, 31)
        assert vigente.valid_to == date(2026, 1, 20)
        assert mundo.empleados.bajas == [(1, date(2026, 1, 20), "dismissal_without_cause")]
        [baja] = mundo.acciones.for_employee(1)
        assert (baja.kind, baja.starts_on, baja.source, baja.memo) == (TERMINATION, date(2026, 1, 20), SYSTEM, "dismissal_without_cause")
        corrida_ = mundo.corridas.get_run(liquidacion)
        assert (corrida_.kind, corrida_.status, corrida_.schedule_id, corrida_.period_to, corrida_.pay_date) == (
            SETTLEMENT,
            DRAFT,
            None,
            date(2026, 1, 20),
            date(2026, 1, 20),
        )

    def test_lo_que_no_es_una_baja(self):
        mundo = Mundo(empleados=[empleado(), empleado(2, terminated_on=ENE_1)])
        with pytest.raises(EmployeeNotFound):
            mundo.dar_de_baja(9, ENE_15)
        with pytest.raises(EmployeeTerminated):
            mundo.dar_de_baja(2, ENE_15)
        with pytest.raises(InvalidEmployee) as e:
            mundo.dar_de_baja(1, ENE_15, "se_fue")
        assert e.value.field == "termination_cause"
