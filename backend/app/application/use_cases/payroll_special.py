"""Las corridas que no son la quincena: aguinaldo, liquidación y ajuste
(F12, T-1208, T-1210, T-1212).

Las tres son corridas como las demás —borrador, aprobada, pagada, con su
asiento y su bitácora— y lo único distinto es **de dónde salen sus líneas**:

- El **aguinaldo** suma lo devengado en las corridas pagadas del 1 de diciembre
  al 30 de noviembre, más los meses de apertura de quien vino de otro sistema
  (RN-97), y lo divide entre doce (RN-69). Un solo rubro, sin cargas ni renta.
- La **liquidación** nace vacía al dar de baja (T-1205) y acá se llena: el
  promedio de los últimos seis meses, las vacaciones que quedan, el aguinaldo
  proporcional y, si la causa lo debe, preaviso y cesantía (RN-71).
- El **ajuste** vuelve a calcular el periodo de una corrida pagada con los
  datos de hoy y escribe **solo la diferencia**, rubro por rubro: la pagada no
  se toca nunca (RN-68), y el asiento del ajuste es la diferencia.

`CalculateRun` (en `payroll.py`) decide cuál de estas usar según la clase de la
corrida; acá no hay estados ni confirmaciones, solo cómo se arma cada línea.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Iterable, Mapping

from app.application.ports.payroll import (
    CalculatedLine,
    ContractSnapshot,
    EmployeeRepository,
    OpeningRepository,
    PayrollRepository,
    RateTable,
    RunSnapshot,
    ScheduleRepository,
    StoredLine,
    VacationRepository,
)
from app.domain.errors import DomainError, RatesMissing
from app.domain.money import Money
from app.domain.payroll import EARNING, EMPLOYEE, EMPLOYER, PayItem
from app.domain.payroll_benefits import (
    VACATION_ACCRUAL,
    VACATION_OPENING,
    VACATION_PAID,
    VACATION_TAKEN,
    SettlementInput,
    aguinaldo,
    aguinaldo_item,
    aguinaldo_period_containing,
    average_salary,
    average_window,
    by_month,
    settlement,
    settlement_vacation_days,
)
from app.domain.payroll_calendar import Period, monthly_equivalent

INCOME_TAX = "income_tax"


# ----------------------------------------------------------------- los «no»


class SettlementRequiresTermination(DomainError):
    """Una liquidación de alguien que no está dado de baja no tiene qué liquidar."""

    def __init__(self, run_id: int, employee_id: int | None) -> None:
        super().__init__(f"la liquidación {run_id} no tiene una baja que liquidar")
        self.run_id = run_id
        self.employee_id = employee_id


class RunNotPaid(DomainError):
    """Solo una corrida pagada se ajusta: la que no lo está se recalcula."""

    def __init__(self, run_id: int, status: str) -> None:
        super().__init__(f"la corrida {run_id} está {status}, no pagada")
        self.run_id = run_id
        self.status = status


class VacationBalanceExceeded(DomainError):
    """Pide más días de los que tiene (RN-70)."""

    def __init__(self, employee_id: int, balance: Decimal, requested: Decimal) -> None:
        super().__init__(f"el empleado {employee_id} tiene {balance} días y pide {requested}")
        self.employee_id = employee_id
        self.balance = balance
        self.requested = requested


# ------------------------------------------------------------ las líneas


def line_totals(employee_id: int, contract_id: int, items: Iterable[PayItem], ccss: frozenset[str]) -> CalculatedLine:
    """Los totales de una línea a partir de sus rubros.

    `ccss` son los conceptos de las cargas obreras que rigen: lo que el
    trabajador paga a la Caja va aparte de la renta y de las demás deducciones
    porque el libro y la boleta los separan (RN-75).
    """
    rubros = tuple(items)
    bruto = Money.sum(i.amount for i in rubros if i.payer == EARNING)
    cargas = Money.sum(i.amount for i in rubros if i.payer == EMPLOYEE and i.concept in ccss)
    renta = Money.sum(i.amount for i in rubros if i.payer == EMPLOYEE and i.concept == INCOME_TAX)
    otras = Money.sum(
        i.amount for i in rubros if i.payer == EMPLOYEE and i.concept not in ccss and i.concept != INCOME_TAX
    )
    patrono = Money.sum(i.amount for i in rubros if i.payer == EMPLOYER)
    return CalculatedLine(
        employee_id=employee_id,
        contract_id=contract_id,
        items=rubros,
        gross=bruto,
        employee_deductions=cargas,
        income_tax=renta,
        other_deductions=otras,
        net=bruto - cargas - renta - otras,
        employer_charges=patrono,
    )


def empty_line(employee_id: int, contract_id: int) -> CalculatedLine:
    """La línea con que nace la liquidación: dice de quién es y todavía no cuánto."""
    return line_totals(employee_id, contract_id, (), frozenset())


def _earned(runs: PayrollRepository, opening: OpeningRepository, employee_id: int, period: Period) -> list[tuple[date, Money]]:
    """Lo devengado en el periodo: corridas pagadas y meses de apertura, juntos."""
    return runs.paid_earnings(employee_id, period) + opening.earnings(employee_id, period)


# ---------------------------------------------------------------- aguinaldo


def aguinaldo_lines(
    run: RunSnapshot,
    *,
    employees: EmployeeRepository,
    runs: PayrollRepository,
    opening: OpeningRepository,
) -> list[CalculatedLine]:
    """Una línea por empleado con algo devengado en el periodo (RN-69, RN-97).

    Quien salió antes de que el periodo terminara no entra: su aguinaldo
    proporcional se le pagó en la liquidación. Quien no devengó nada —entró
    después del corte— tampoco: no hay doceava parte de cero.
    """
    periodo = Period(run.period_from, run.period_to)
    por_empleado: dict[int, list[ContractSnapshot]] = {}
    for contrato in employees.contracts_between(periodo):
        por_empleado.setdefault(contrato.employee_id, []).append(contrato)

    lineas: list[CalculatedLine] = []
    for employee_id in sorted(por_empleado):
        empleado = employees.get(employee_id)
        assert empleado is not None
        if empleado.terminated_on is not None and empleado.terminated_on <= periodo.ends_on:
            continue
        devengado = [monto for _, monto in _earned(runs, opening, employee_id, periodo)]
        monto = aguinaldo(devengado)
        if not monto.is_positive:
            continue
        contrato = sorted(por_empleado[employee_id], key=lambda c: c.valid_from)[-1]
        rubro = aguinaldo_item(monto, earned=Money.sum(devengado))
        lineas.append(line_totals(employee_id, contrato.id, (rubro,), frozenset()))
    return lineas


# -------------------------------------------------------------- liquidación


def settlement_lines(
    run: RunSnapshot,
    *,
    employees: EmployeeRepository,
    runs: PayrollRepository,
    opening: OpeningRepository,
    vacations: VacationRepository,
    rates: RateTable,
    schedules: ScheduleRepository,
    country: str,
) -> list[CalculatedLine]:
    """La única línea de la liquidación, calculada (RN-71, T-1210).

    De quién es lo dice la línea vacía con que nació: una liquidación sin línea,
    o de alguien que no está dado de baja, no tiene qué liquidar.

    - El promedio es el de los seis meses calendario anteriores a la salida,
      pagados o de apertura, o los que haya; sin ninguno, el salario mensual del
      contrato (quien se va en su primer mes).
    - Las vacaciones son el saldo de los movimientos, con el piso de un día por
      mes de quien no llegó a las cincuenta semanas; se pagan al promedio.
    - El aguinaldo proporcional suma lo devengado desde el 1 de diciembre hasta
      la salida.
    """
    existentes = runs.lines(run.id)
    if not existentes:
        raise SettlementRequiresTermination(run.id, None)
    linea = existentes[0]
    empleado = employees.get(linea.employee_id)
    if empleado is None or empleado.terminated_on is None or empleado.termination_cause is None:
        raise SettlementRequiresTermination(run.id, linea.employee_id)
    salida = empleado.terminated_on

    contratos = employees.contracts_of(empleado.id)
    ultimo = contratos[-1]
    jornada = schedules.get(ultimo.schedule_id)
    assert jornada is not None

    meses = by_month(_earned(runs, opening, empleado.id, average_window(salida)))
    promedio = average_salary(meses) if meses else monthly_equivalent(Money(ultimo.period_salary), jornada.frequency)

    movimientos = vacations.movements(empleado.id)
    ganados = sum((Decimal(m.days) for m in movimientos if m.kind in (VACATION_OPENING, VACATION_ACCRUAL)), Decimal(0))
    usados = sum((Decimal(m.days) for m in movimientos if m.kind in (VACATION_TAKEN, VACATION_PAID)), Decimal(0))
    dias = settlement_vacation_days(empleado.hired_on, salida, earned=ganados, used=usados)

    desde_diciembre = Period(aguinaldo_period_containing(salida).starts_on, salida)
    devengado = Money.sum(monto for _, monto in _earned(runs, opening, empleado.id, desde_diciembre))

    tabla = rates.severance_at(salida, country)
    if not tabla:
        raise RatesMissing(("severance:rule",), salida)

    rubros = settlement(
        SettlementInput(
            cause=empleado.termination_cause,
            hired_on=empleado.hired_on,
            terminated_on=salida,
            average_monthly=promedio,
            vacation_days=dias,
            aguinaldo_earned=devengado,
        ),
        tabla,
    )
    return [line_totals(empleado.id, ultimo.id, rubros, frozenset())]


# ------------------------------------------------------------------ ajuste


def _key(item: PayItem) -> tuple:
    return (item.concept, item.payer, item.action_id, item.applied_from, item.applied_to)


def difference_lines(
    original: Mapping[int, StoredLine],
    recalculated: Mapping[int, CalculatedLine],
    *,
    ccss: frozenset[str],
    contract_of: Callable[[int], int],
) -> list[CalculatedLine]:
    """Lo que el ajuste escribe: la diferencia, rubro por rubro (RN-68, T-1212).

    Se comparan los rubros del mismo concepto, pagador, acción y fechas. Lo que
    cambió deja un rubro con la diferencia; lo que no cambió, nada. Un empleado
    que no estaba en la pagada entra entero; uno que ya no debía estar sale
    entero, en negativo. Si a alguien no le cambió nada, no tiene línea.

    `contract_of` da el contrato de un empleado que está en la original pero no
    en el recálculo —quien ya no debía cobrar—, para que la línea diga de quién
    es.
    """
    lineas: list[CalculatedLine] = []
    for employee_id in sorted(set(original) | set(recalculated)):
        antes = {_key(i): i for i in (original[employee_id].items if employee_id in original else ())}
        ahora = {_key(i): i for i in (recalculated[employee_id].items if employee_id in recalculated else ())}
        rubros: list[PayItem] = []
        for clave in list(ahora) + [k for k in antes if k not in ahora]:
            nuevo = ahora.get(clave)
            viejo = antes.get(clave)
            diferencia = (nuevo.amount if nuevo else Money.zero()) - (viejo.amount if viejo else Money.zero())
            if diferencia.is_zero:
                continue
            modelo = nuevo or viejo
            assert modelo is not None
            rubros.append(
                PayItem(
                    modelo.concept,
                    modelo.payer,
                    modelo.base,
                    modelo.rate,
                    diferencia,
                    action_id=modelo.action_id,
                    quantity=modelo.quantity,
                    applied_from=modelo.applied_from,
                    applied_to=modelo.applied_to,
                )
            )
        if not rubros:
            continue
        contrato = recalculated[employee_id].contract_id if employee_id in recalculated else contract_of(employee_id)
        lineas.append(line_totals(employee_id, contrato, rubros, ccss))
    return lineas
