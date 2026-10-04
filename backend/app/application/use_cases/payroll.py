"""Acciones de personal y corridas de planilla (F12, T-1205, T-1206, T-1218).

Nueve casos de uso y una sola idea detrás: **la acción es la fuente y la
corrida la consume** (RN-90). Registrar una acción no toca ninguna boleta;
calcular una corrida toma las acciones que le tocan, las parte por el
calendario y deja cada tramo aplicado como un rubro con sus fechas. Lo que una
acción ya aplicó es la suma de sus rubros en corridas aprobadas o pagadas, y
de ahí salen el saldo de un préstamo (RN-92), el primer día que nadie aplicó de
una incapacidad (RN-91) y si una anulación ya surtió efecto.

Lo que escribe `CalculateRun` es el congelamiento de RN-66: cada rubro con su
base, su tasa y su monto. Recalcular un borrador lo reescribe entero; una
corrida aprobada o pagada no se recalcula nunca.

Las tres acciones que cambian el contrato —aumento, cambio de puesto y baja— se
aplican al registrarlas, no en la corrida: cierran el contrato vigente el día
antes y abren otro. Así una corrida de marzo lee el salario de marzo aunque hoy
sea otro, y la boleta no necesita saber que hubo un aumento.

Ningún caso de uso conoce un porcentaje ni una fecha de corte: el dominio
decide y acá solo se le dan los datos que pide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.application.ports.clock import Clock
from app.application.ports.ledger import Ledger
from app.application.ports.payroll import (
    ActionRepository,
    ActionSnapshot,
    CalculatedLine,
    ContractSnapshot,
    EmployeeRepository,
    OpeningRepository,
    PayrollRepository,
    PayrollSettings,
    RateTable,
    RunSnapshot,
    ScheduleRepository,
    ScheduleSnapshot,
    StoredLine,
    VacationRepository,
)
from app.application.ports.repositories import UnitOfWork
from app.application.use_cases.payroll_special import (
    INCOME_TAX,
    RunNotPaid,
    SettlementRequiresTermination,
    VacationBalanceExceeded,
    aguinaldo_lines,
    difference_lines,
    empty_line,
    line_totals,
    settlement_lines,
)
from app.domain.errors import DomainError, InvalidAction, InvalidContract, InvalidSchedule
from app.domain.money import Money
from app.domain.payroll import (
    EARNING,
    EMPLOYEE,
    INA_CONCEPT,
    PayItem,
    RateSet,
    TaxBracket,
    TaxCredits,
    employee_deductions,
    employer_charges,
    income_tax_withholding,
    rates_at,
)
from app.domain.payroll_actions import (
    BASE,
    CHILD_SUPPORT,
    DEDUCTION,
    DEDUCTION_ORDER,
    GARNISHMENT,
    POSITION_CHANGE,
    RAISE,
    SINGLE_DAY_KINDS,
    TERMINATION,
    VACATION,
    Action,
    Portion,
    action_items,
    apply_deductions,
    base_item,
    check_action,
    child_support_capacity,
    contribution_base,
    counted_days,
    deduction_due,
    deduction_order,
    garnishment_capacity,
    is_active,
    portions,
    remaining_balance,
    taxable_base,
)
from app.domain.payroll_benefits import (
    VACATION_ACCRUAL,
    VACATION_PAID,
    VACATION_PAYOUT,
    VACATION_TAKEN,
    aguinaldo_period,
    calendar_days,
    vacation_accrual,
    vacation_balance,
)
from app.domain.payroll_calendar import Period, Schedule, closes_month, next_cut, period_for
from app.domain.payroll_staff import check_termination

__all__ = [
    "INCOME_TAX",
    "RunNotPaid",
    "SettlementRequiresTermination",
    "VacationBalanceExceeded",
]

REGULAR = "regular"
AGUINALDO = "aguinaldo"
SETTLEMENT = "settlement"
ADJUSTMENT = "adjustment"

DRAFT = "draft"
APPROVED = "approved"
PAID = "paid"

MANUAL = "manual"
SYSTEM = "system"

#: Las que cambian el contrato y no la boleta: se aplican al registrarlas.
CONTRACT_KINDS = frozenset({RAISE, POSITION_CHANGE, TERMINATION})

SOLIDARISTA = "solidarista"
#: La Ley 2412 manda pagar el aguinaldo en los primeros veinte días de diciembre.
AGUINALDO_PAY_DAY = 20
#: La regla de RN-93: el menor salario mensual del decreto de salarios mínimos.
UNSEIZABLE_RULE = "minimum_wage_unseizable"

UN_DIA = timedelta(days=1)


# ----------------------------------------------------------------- los «no»


class EmployeeNotFound(DomainError):
    def __init__(self, employee_id: int) -> None:
        super().__init__(f"no hay empleado {employee_id}")
        self.employee_id = employee_id


class EmployeeTerminated(DomainError):
    """Ya está dado de baja, o la acción es posterior a su baja."""

    def __init__(self, employee_id: int, terminated_on: date) -> None:
        super().__init__(f"el empleado {employee_id} salió el {terminated_on}")
        self.employee_id = employee_id
        self.terminated_on = terminated_on


class ContractMissing(DomainError):
    """No tiene contrato vigente en esa fecha: no hay salario del que calcular."""

    def __init__(self, employee_id: int) -> None:
        super().__init__(f"el empleado {employee_id} no tiene contrato en esa fecha")
        self.employee_id = employee_id


class ScheduleNotFound(DomainError):
    def __init__(self, schedule_id: int) -> None:
        super().__init__(f"no hay jornada {schedule_id}")
        self.schedule_id = schedule_id


class PositionNotFound(DomainError):
    def __init__(self, position_id: int) -> None:
        super().__init__(f"no hay puesto {position_id}")
        self.position_id = position_id


class ActionNotFound(DomainError):
    def __init__(self, action_id: int) -> None:
        super().__init__(f"no hay acción {action_id}")
        self.action_id = action_id


class ActionNotEditable(DomainError):
    """`reason`: `applied` (ya entró en una corrida: se anula, RN-91),
    `cancellation` (una anulación no se edita ni se anula) o `contract` (un
    aumento o un cambio de puesto ya cerró y abrió contratos)."""

    def __init__(self, action_id: int, reason: str) -> None:
        super().__init__(f"la acción {action_id} no se puede editar ({reason})")
        self.action_id = action_id
        self.reason = reason


class ActionAlreadyCancelled(DomainError):
    def __init__(self, action_id: int) -> None:
        super().__init__(f"la acción {action_id} ya está anulada")
        self.action_id = action_id


class ActionNotRecurring(DomainError):
    def __init__(self, action_id: int) -> None:
        super().__init__(f"la acción {action_id} no es recurrente")
        self.action_id = action_id


class ActionAlreadySuspended(DomainError):
    def __init__(self, action_id: int) -> None:
        super().__init__(f"la acción {action_id} ya está suspendida")
        self.action_id = action_id


class RunNotFound(DomainError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"no hay corrida {run_id}")
        self.run_id = run_id


class RunAlreadyExists(DomainError):
    """Ya hay una corrida de esa jornada con ese corte."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"ya existe la corrida {run_id} para ese corte")
        self.run_id = run_id


class RunNotEditable(DomainError):
    """`reason`: el estado que lo impide (`approved`) o la clase de corrida que
    todavía no se calcula acá (`aguinaldo`, `settlement`, `adjustment`)."""

    def __init__(self, run_id: int, reason: str) -> None:
        super().__init__(f"la corrida {run_id} no se puede cambiar ({reason})")
        self.run_id = run_id
        self.reason = reason


class RunNotCalculated(DomainError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"la corrida {run_id} no tiene líneas calculadas")
        self.run_id = run_id


class RunNotApproved(DomainError):
    def __init__(self, run_id: int, status: str) -> None:
        super().__init__(f"la corrida {run_id} está {status}, no aprobada")
        self.run_id = run_id
        self.status = status


class RunAlreadyPaid(DomainError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"la corrida {run_id} ya está pagada (RN-68)")
        self.run_id = run_id


# ------------------------------------------------------------- traducciones


def _schedule(s: ScheduleSnapshot) -> Schedule:
    return Schedule(
        frequency=s.frequency,
        shift=s.shift,
        hours_per_day=Decimal(s.hours_per_day),
        rest_day_paid=bool(s.rest_day_paid),
        workdays_per_week=int(s.workdays_per_week),
        first_cut_day=s.first_cut_day,
        cut_weekday=s.cut_weekday,
        series_start=s.series_start,
    )


def _money(value: Decimal | None) -> Money | None:
    return None if value is None else Money(value)


def _action(a: ActionSnapshot) -> Action:
    return Action(
        kind=a.kind,
        starts_on=a.starts_on,
        ends_on=a.ends_on,
        hours=a.hours,
        days=a.days,
        amount=_money(a.amount),
        total_amount=_money(a.total_amount),
        new_salary=_money(a.new_salary),
        position_id=a.position_id,
        is_recurring=bool(a.is_recurring),
        suspended_on=a.suspended_at.date() if a.suspended_at is not None else None,
        id=a.id,
    )


def _contract_on(contracts: list[ContractSnapshot], day: date) -> ContractSnapshot | None:
    """El contrato que rige ese día, si hay."""
    for c in contracts:
        if c.valid_from <= day and (c.valid_to is None or day <= c.valid_to):
            return c
    return None


def _is_cancelled(action: ActionSnapshot, siblings: list[ActionSnapshot]) -> bool:
    return any(s.cancels_action_id == action.id for s in siblings)


@dataclass(frozen=True)
class ActionRequest:
    """Lo que llega para registrar o editar una acción (RF-82)."""

    employee_id: int
    kind: str
    starts_on: date
    ends_on: date | None = None
    hours: Decimal | None = None
    days: Decimal | None = None
    amount: Money | None = None
    total_amount: Money | None = None
    new_salary: Money | None = None
    position_id: int | None = None
    is_recurring: bool = False
    memo: str | None = None

    def as_action(self) -> Action:
        return Action(
            kind=self.kind,
            starts_on=self.starts_on,
            ends_on=self.ends_on,
            hours=self.hours,
            days=self.days,
            amount=self.amount,
            total_amount=self.total_amount,
            new_salary=self.new_salary,
            position_id=self.position_id,
            is_recurring=self.is_recurring,
        )

    def fields(self) -> dict[str, object]:
        """Las columnas que se escriben, con la plata ya como `Decimal`."""
        return {
            "starts_on": self.starts_on,
            "ends_on": self.ends_on,
            "hours": self.hours,
            "days": self.days,
            "amount": None if self.amount is None else self.amount.amount,
            "total_amount": None if self.total_amount is None else self.total_amount.amount,
            "new_salary": None if self.new_salary is None else self.new_salary.amount,
            "position_id": self.position_id,
            "is_recurring": self.is_recurring,
            "memo": self.memo,
        }


# ----------------------------------------------------- acciones de personal


class RegisterAction:
    """Registra una acción en el empleado (RF-82, RN-90).

    No calcula nada: la corrida que le toque la tomará. Lo único que pasa en el
    acto son las dos que cambian el contrato —el aumento y el cambio de puesto—,
    que cierran el vigente el día antes y abren otro desde la fecha de la acción.
    La baja no entra por acá: tiene su propio caso de uso, porque además del
    contrato cierra al empleado y abre la liquidación.
    """

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        actions: ActionRepository,
        vacations: VacationRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._employees = employees
        self._actions = actions
        self._vacations = vacations
        self._uow = uow
        self._clock = clock

    def __call__(self, request: ActionRequest, *, user_id: int) -> int:
        if request.kind == TERMINATION:
            raise InvalidAction("kind", "not_allowed", TERMINATION)
        check_action(request.as_action())

        empleado = self._employees.get(request.employee_id)
        if empleado is None:
            raise EmployeeNotFound(request.employee_id)
        if empleado.terminated_on is not None and request.starts_on > empleado.terminated_on:
            raise EmployeeTerminated(empleado.id, empleado.terminated_on)
        contrato = _contract_on(self._employees.contracts_of(empleado.id), request.starts_on)
        if contrato is None:
            raise ContractMissing(empleado.id)
        if request.kind == VACATION:
            # El disfrute sale del saldo (RN-70): pedir más de lo que hay no es
            # una acción, es un reclamo.
            assert request.days is not None
            _check_balance(self._vacations, empleado.id, request.days)

        with self._uow:
            if request.kind in (RAISE, POSITION_CHANGE):
                self._replace_contract(contrato, request)
            action_id = self._actions.add(
                employee_id=empleado.id,
                kind=request.kind,
                **request.fields(),
                source=MANUAL,
                created_by=user_id,
                created_at=self._clock.now(),
            )
            if request.kind == VACATION:
                assert request.days is not None
                self._vacations.add(
                    empleado.id, kind=VACATION_TAKEN, days=request.days, on_date=request.starts_on, action_id=action_id
                )
            self._uow.commit()
        return action_id

    def _replace_contract(self, contrato: ContractSnapshot, request: ActionRequest) -> None:
        """Cierra el vigente el día antes y abre el nuevo desde la acción."""
        if request.starts_on <= contrato.valid_from:
            # El mismo día en que empezó el contrato no hay nada que cerrar: se
            # corrige el contrato, no se le pone un aumento encima.
            raise InvalidContract("valid_from", "overlaps", request.starts_on)

        position_id = contrato.position_id
        salario = Money(contrato.period_salary)
        if request.kind == POSITION_CHANGE:
            assert request.position_id is not None
            activo = self._employees.position_active(request.position_id)
            if activo is None:
                raise PositionNotFound(request.position_id)
            if not activo:
                raise InvalidContract("position_id", "inactive", request.position_id)
            position_id = request.position_id
        else:
            assert request.new_salary is not None
            salario = request.new_salary

        self._employees.close_contract(contrato.id, valid_to=request.starts_on - UN_DIA)
        self._employees.add_contract(
            employee_id=contrato.employee_id,
            schedule_id=contrato.schedule_id,
            position_id=position_id,
            ins_policy_id=contrato.ins_policy_id,
            valid_from=request.starts_on,
            period_salary=salario,
            solidarista_rate=contrato.solidarista_rate,
        )


def _balance(vacations: VacationRepository, employee_id: int) -> Decimal:
    return vacation_balance((m.kind, m.days) for m in vacations.movements(employee_id))


def _check_balance(vacations: VacationRepository, employee_id: int, days: Decimal, *, giving_back: Decimal = Decimal(0)) -> None:
    """`VacationBalanceExceeded` si pide más días de los que tiene (RN-70).

    `giving_back` son los días de la acción que se está corrigiendo: vuelven al
    saldo antes de comparar.
    """
    saldo = _balance(vacations, employee_id) + giving_back
    if days > saldo:
        raise VacationBalanceExceeded(employee_id, saldo, days)


def _editable(action: ActionSnapshot, siblings: list[ActionSnapshot], actions: ActionRepository) -> None:
    """Lo que tiene que cumplir una acción para editarse o anularse (RN-91)."""
    if action.cancels_action_id is not None:
        raise ActionNotEditable(action.id, "cancellation")
    if action.kind in CONTRACT_KINDS:
        raise ActionNotEditable(action.id, "contract")
    if _is_cancelled(action, siblings):
        raise ActionAlreadyCancelled(action.id)
    if actions.applied(action.id):
        raise ActionNotEditable(action.id, "applied")


class UpdateAction:
    """Corrige una acción que **ninguna corrida aplicó** todavía.

    El empleado y el tipo no se cambian: una acción de otro tipo es otra acción.
    Una que ya entró en una corrida aprobada o pagada no se edita: se anula y se
    registra otra (RN-91).
    """

    def __init__(self, *, actions: ActionRepository, vacations: VacationRepository, uow: UnitOfWork) -> None:
        self._actions = actions
        self._vacations = vacations
        self._uow = uow

    def __call__(self, action_id: int, request: ActionRequest) -> None:
        accion = self._actions.get(action_id)
        if accion is None:
            raise ActionNotFound(action_id)
        _editable(accion, self._actions.for_employee(accion.employee_id), self._actions)

        corregida = ActionRequest(
            employee_id=accion.employee_id,
            kind=accion.kind,
            starts_on=request.starts_on,
            ends_on=request.ends_on,
            hours=request.hours,
            days=request.days,
            amount=request.amount,
            total_amount=request.total_amount,
            new_salary=None,
            position_id=None,
            is_recurring=request.is_recurring,
            memo=request.memo,
        )
        check_action(corregida.as_action())
        if accion.kind == VACATION:
            assert corregida.days is not None
            _check_balance(self._vacations, accion.employee_id, corregida.days, giving_back=Decimal(accion.days or 0))
        with self._uow:
            self._actions.update(action_id, **corregida.fields())
            if accion.kind == VACATION:
                assert corregida.days is not None
                self._vacations.update_for_action(action_id, days=corregida.days, on_date=corregida.starts_on)
            self._uow.commit()


class CancelAction:
    """Anula una acción con **otra** que la referencia (RN-91).

    Siempre con otra, también si la original todavía no entró en ninguna
    corrida: así el historial dice que existió y que se anuló, y la corrida que
    la recoja deja constancia de las dos. Si ya se había aplicado, la corrida
    siguiente escribe sus rubros al revés.
    """

    def __init__(self, *, actions: ActionRepository, vacations: VacationRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._actions = actions
        self._vacations = vacations
        self._uow = uow
        self._clock = clock

    def __call__(self, action_id: int, *, user_id: int, memo: str | None = None) -> int:
        accion = self._actions.get(action_id)
        if accion is None:
            raise ActionNotFound(action_id)
        if accion.cancels_action_id is not None:
            raise ActionNotEditable(action_id, "cancellation")
        if accion.kind in CONTRACT_KINDS:
            raise ActionNotEditable(action_id, "contract")
        if _is_cancelled(accion, self._actions.for_employee(accion.employee_id)):
            raise ActionAlreadyCancelled(action_id)

        with self._uow:
            nueva = self._actions.add(
                employee_id=accion.employee_id,
                kind=accion.kind,
                starts_on=accion.starts_on,
                ends_on=accion.ends_on,
                hours=None,
                days=None,
                amount=None,
                total_amount=None,
                new_salary=None,
                position_id=None,
                is_recurring=False,
                memo=memo,
                cancels_action_id=accion.id,
                source=MANUAL,
                created_by=user_id,
                created_at=self._clock.now(),
            )
            if accion.kind == VACATION and accion.days:
                # Los días vuelven al saldo con un movimiento al revés, para que
                # el historial diga que se pidieron y se devolvieron.
                self._vacations.add(
                    accion.employee_id,
                    kind=VACATION_TAKEN,
                    days=-Decimal(accion.days),
                    on_date=accion.starts_on,
                    action_id=nueva,
                )
            self._uow.commit()
        return nueva


class SuspendAction:
    """Suspende una deducción recurrente, con quién, cuándo y por qué (RN-92).

    Lo ya aplicado no se toca; la corrida siguiente ya no la toma. Un embargo
    no se suspende por acá: se aplica hasta agotar su saldo, y lo levanta el
    juzgado anulándolo.
    """

    def __init__(self, *, actions: ActionRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._actions = actions
        self._uow = uow
        self._clock = clock

    def __call__(self, action_id: int, *, user_id: int, reason: str) -> None:
        accion = self._actions.get(action_id)
        if accion is None:
            raise ActionNotFound(action_id)
        if accion.kind not in (DEDUCTION, CHILD_SUPPORT) or not accion.is_recurring:
            raise ActionNotRecurring(action_id)
        if _is_cancelled(accion, self._actions.for_employee(accion.employee_id)):
            raise ActionAlreadyCancelled(action_id)
        if accion.suspended_at is not None:
            raise ActionAlreadySuspended(action_id)
        with self._uow:
            self._actions.suspend(action_id, at=self._clock.now(), by=user_id, reason=reason)
            self._uow.commit()


class TerminateEmployee:
    """La baja (RF-55, RN-72): fecha y causa, el contrato cerrado, la acción
    `termination` en el historial y la liquidación en borrador (RF-61).

    La liquidación nace vacía: sus rubros los calcula T-1210 con el promedio de
    los últimos seis meses, las vacaciones sin disfrutar y lo devengado desde
    diciembre. Nace acá para que no se olvide: un ex empleado sin liquidación
    en la lista es un reclamo laboral dentro de un mes.
    """

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        actions: ActionRepository,
        runs: PayrollRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._employees = employees
        self._actions = actions
        self._runs = runs
        self._uow = uow
        self._clock = clock

    def __call__(self, employee_id: int, *, on: date, cause: str, user_id: int) -> int:
        empleado = self._employees.get(employee_id)
        if empleado is None:
            raise EmployeeNotFound(employee_id)
        if empleado.terminated_on is not None:
            raise EmployeeTerminated(employee_id, empleado.terminated_on)
        check_termination(empleado.hired_on, on, cause)
        contratos = self._employees.contracts_of(employee_id)
        if not contratos:
            # Sin contrato no hay salario del que liquidar; se corrige la ficha
            # antes de darla de baja.
            raise ContractMissing(employee_id)

        ahora = self._clock.now()
        with self._uow:
            for contrato in contratos:
                if contrato.valid_to is None or contrato.valid_to > on:
                    self._employees.close_contract(contrato.id, valid_to=on)
            self._employees.terminate(employee_id, on=on, cause=cause)
            self._actions.add(
                employee_id=employee_id,
                kind=TERMINATION,
                starts_on=on,
                ends_on=None,
                hours=None,
                days=None,
                amount=None,
                total_amount=None,
                new_salary=None,
                position_id=None,
                is_recurring=False,
                memo=cause,
                source=SYSTEM,
                created_by=user_id,
                created_at=ahora,
            )
            liquidacion = self._runs.add_run(
                kind=SETTLEMENT,
                schedule_id=None,
                period_from=on,
                period_to=on,
                pay_date=on,
                created_by=user_id,
                created_at=ahora,
            )
            # La línea vacía es lo que dice de quién es la liquidación: la
            # corrida no tiene columna de empleado porque las demás son de muchos.
            self._runs.replace_lines(liquidacion.id, [empty_line(employee_id, contratos[-1].id)])
            self._uow.commit()
        return liquidacion.id


# ------------------------------------------------------------------ corridas


class CreateAguinaldoRun:
    """La corrida de aguinaldo de un año (RF-59, RN-69): del 1 de diciembre
    anterior al 30 de noviembre, para toda la compañía. Una por año; la fecha de
    pago, si no se dice, el 20 de diciembre, que es el último día que da la ley.
    """

    def __init__(self, *, runs: PayrollRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._runs = runs
        self._uow = uow
        self._clock = clock

    def __call__(self, year: int, *, pay_date: date | None = None, user_id: int) -> RunSnapshot:
        periodo = aguinaldo_period(year)
        existente = self._runs.find_run(schedule_id=None, period_to=periodo.ends_on, kind=AGUINALDO)
        if existente is not None:
            raise RunAlreadyExists(existente.id)
        with self._uow:
            corrida = self._runs.add_run(
                kind=AGUINALDO,
                schedule_id=None,
                period_from=periodo.starts_on,
                period_to=periodo.ends_on,
                pay_date=pay_date or date(year, 12, AGUINALDO_PAY_DAY),
                created_by=user_id,
                created_at=self._clock.now(),
            )
            self._uow.commit()
        return corrida


class AdjustRun:
    """Una corrida de ajuste sobre una pagada (RF-63, RN-68).

    Nace vacía y referenciando a la original, con su mismo periodo; calcularla
    escribe la diferencia entre lo que se pagó y lo que hoy daría. Solo las
    regulares pagadas se ajustan: un borrador se recalcula, y el aguinaldo o
    una liquidación equivocados se corrigen con otra corrida de su clase.
    """

    def __init__(self, *, runs: PayrollRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._runs = runs
        self._uow = uow
        self._clock = clock

    def __call__(self, run_id: int, *, user_id: int) -> RunSnapshot:
        original = self._runs.get_run(run_id)
        if original is None:
            raise RunNotFound(run_id)
        if original.status != PAID:
            raise RunNotPaid(run_id, original.status)
        if original.kind != REGULAR:
            raise RunNotEditable(run_id, original.kind)
        with self._uow:
            ajuste = self._runs.add_run(
                kind=ADJUSTMENT,
                schedule_id=original.schedule_id,
                period_from=original.period_from,
                period_to=original.period_to,
                pay_date=self._clock.today(),
                created_by=user_id,
                created_at=self._clock.now(),
                adjusts_run_id=original.id,
            )
            self._uow.commit()
        return ajuste


class CreateRun:
    """Una corrida regular: de una jornada y de un corte válido para ella (RN-94).

    El periodo sale del corte, nadie lo escribe. Dos corridas del mismo corte
    serían pagar dos veces la misma quincena, así que la segunda no entra.
    """

    def __init__(
        self,
        *,
        runs: PayrollRepository,
        schedules: ScheduleRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._runs = runs
        self._schedules = schedules
        self._uow = uow
        self._clock = clock

    def __call__(
        self, schedule_id: int, cut: date, *, pay_date: date | None = None, user_id: int
    ) -> RunSnapshot:
        jornada = self._schedules.get(schedule_id)
        if jornada is None:
            raise ScheduleNotFound(schedule_id)
        if not jornada.is_active:
            raise InvalidSchedule("is_active", "inactive", schedule_id)
        periodo = period_for(_schedule(jornada), cut)
        existente = self._runs.find_run(schedule_id=schedule_id, period_to=cut, kind=REGULAR)
        if existente is not None:
            raise RunAlreadyExists(existente.id)

        with self._uow:
            corrida = self._runs.add_run(
                kind=REGULAR,
                schedule_id=schedule_id,
                period_from=periodo.starts_on,
                period_to=cut,
                pay_date=pay_date or cut,
                created_by=user_id,
                created_at=self._clock.now(),
            )
            self._uow.commit()
        return corrida


@dataclass(frozen=True)
class CalculatedRun:
    run_id: int
    period: Period
    closes_month: bool
    lines: tuple[CalculatedLine, ...]


@dataclass(frozen=True)
class _Context:
    """Lo que se resuelve una vez por corrida: la jornada y lo que rige al corte."""

    schedule: Schedule
    schedule_id: int
    period: Period
    rates: RateSet
    brackets: tuple[TaxBracket, ...]
    credits: TaxCredits
    exempt: frozenset[str]
    closes: bool


def _ccss(rates: RateSet) -> frozenset[str]:
    """Los conceptos de las cargas obreras que rigen: lo que va a la Caja."""
    return frozenset(r.concept for r in rates.contributions(EMPLOYEE))


def _applied_portions(line: StoredLine) -> dict[int, list[tuple[date, date]]]:
    """Qué tramo de cada acción aplicó una línea ya pagada, por sus fechas.

    Un ajuste vuelve a valorar **esos** tramos y no otros (RN-91): lo que la
    pagada no aplicó entra en la corrida regular siguiente, como siempre.
    """
    tramos: dict[int, list[tuple[date, date]]] = {}
    for i in line.items:
        if i.action_id is None or i.payer != EARNING or i.applied_from is None or i.applied_to is None:
            continue
        par = (i.applied_from, i.applied_to)
        suyos = tramos.setdefault(i.action_id, [])
        if par not in suyos:
            suyos.append(par)
    return tramos


def _copied(line: StoredLine, action_id: int) -> list[PayItem]:
    """Los rubros que una línea pagada dejó por una acción, tal cual."""
    return [i for i in line.items if i.action_id == action_id]


class CalculateRun:
    """Calcula un borrador: toma lo que le toca y congela los rubros (RN-66).

    Cada clase de corrida tiene su cálculo:

    - **Regular**: por cada empleado con contrato en el periodo, el salario base
      (entero o proporcional, RN-94), los tramos de sus acciones que ninguna
      corrida aplicó (RN-90, RN-91) y las anulaciones de lo que sí se aplicó, las
      cargas obreras sobre lo que cotiza, el solidarista del contrato, la renta
      del mes (RN-73), las deducciones en el orden de RN-93 sin dejar el neto
      negativo, y las cargas patronales con la prima de su póliza.
    - **Aguinaldo**, **liquidación** y **ajuste**: `payroll_special.py`. El
      ajuste vuelve a correr el cálculo regular sobre el periodo de la pagada,
      valorando los mismos tramos que ella aplicó con los datos de hoy, y
      escribe solo la diferencia.

    Recalcular un borrador lo reescribe entero; una aprobada o pagada no se
    recalcula nunca.
    """

    def __init__(
        self,
        *,
        runs: PayrollRepository,
        schedules: ScheduleRepository,
        employees: EmployeeRepository,
        actions: ActionRepository,
        rates: RateTable,
        settings: PayrollSettings,
        vacations: VacationRepository,
        opening: OpeningRepository,
        uow: UnitOfWork,
        country: str = "CR",
    ) -> None:
        self._runs = runs
        self._schedules = schedules
        self._employees = employees
        self._actions = actions
        self._rates = rates
        self._settings = settings
        self._vacations = vacations
        self._opening = opening
        self._uow = uow
        self._country = country

    def __call__(self, run_id: int) -> CalculatedRun:
        corrida = self._runs.get_run(run_id)
        if corrida is None:
            raise RunNotFound(run_id)
        if corrida.status == PAID:
            raise RunAlreadyPaid(run_id)
        if corrida.status != DRAFT:
            raise RunNotEditable(run_id, corrida.status)

        periodo = Period(corrida.period_from, corrida.period_to)
        cierra = False
        if corrida.kind == AGUINALDO:
            lineas = aguinaldo_lines(corrida, employees=self._employees, runs=self._runs, opening=self._opening)
        elif corrida.kind == SETTLEMENT:
            lineas = settlement_lines(
                corrida,
                employees=self._employees,
                runs=self._runs,
                opening=self._opening,
                vacations=self._vacations,
                rates=self._rates,
                schedules=self._schedules,
                country=self._country,
            )
        elif corrida.kind == ADJUSTMENT:
            lineas = self._adjustment(corrida)
        else:
            contexto = self._context(corrida)
            cierra = contexto.closes
            lineas = self._regular(contexto, run_id=corrida.id)

        with self._uow:
            self._runs.replace_lines(corrida.id, lineas)
            self._uow.commit()
        return CalculatedRun(corrida.id, periodo, cierra, tuple(lineas))

    # ------------------------------------------------------------ por dentro

    def _context(self, corrida: RunSnapshot) -> _Context:
        assert corrida.schedule_id is not None
        jornada = self._schedules.get(corrida.schedule_id)
        assert jornada is not None
        schedule = _schedule(jornada)
        corte = corrida.period_to
        # Las cargas se exigen todas al resolver (`RatesMissing`); las reglas,
        # cuando hacen falta.
        tasas = rates_at(self._rates.rates(self._country), corte, self._country)
        return _Context(
            schedule=schedule,
            schedule_id=jornada.id,
            period=Period(corrida.period_from, corte),
            rates=tasas,
            brackets=tuple(self._rates.brackets_at(corte, self._country)),
            credits=self._rates.credits_at(corte, self._country),
            exempt=frozenset({INA_CONCEPT}) if self._settings.payroll().get("ina_exempt") else frozenset(),
            closes=closes_month(schedule, corte),
        )

    def _regular(
        self,
        ctx: _Context,
        *,
        run_id: int,
        originals: dict[int, StoredLine] | None = None,
        exclude_run_id: int | None = None,
    ) -> list[CalculatedLine]:
        """Las líneas del periodo. Con `originals`, es el recálculo de un ajuste:
        cada empleado que estaba en la pagada se valora sobre los tramos que
        ella aplicó, y la renta se liquida contra el mes sin contar la pagada."""
        por_empleado: dict[int, list[ContractSnapshot]] = {}
        for contrato in self._employees.contracts_in(ctx.schedule_id, ctx.period):
            por_empleado.setdefault(contrato.employee_id, []).append(contrato)

        lineas: list[CalculatedLine] = []
        for employee_id in sorted(por_empleado):
            linea = self._line(
                employee_id,
                por_empleado[employee_id],
                ctx,
                exclude_run_id=exclude_run_id if exclude_run_id is not None else run_id,
                original=originals.get(employee_id) if originals is not None else None,
            )
            if linea is not None:
                lineas.append(linea)
        return lineas

    def _adjustment(self, corrida: RunSnapshot) -> list[CalculatedLine]:
        """La diferencia entre lo que se pagó y lo que daría hoy (RN-68, T-1212)."""
        assert corrida.adjusts_run_id is not None
        original = self._runs.get_run(corrida.adjusts_run_id)
        assert original is not None
        ctx = self._context(corrida)
        originales = {l.employee_id: l for l in self._runs.lines(original.id)}
        recalculadas = {
            l.employee_id: l
            for l in self._regular(ctx, run_id=corrida.id, originals=originales, exclude_run_id=original.id)
        }
        return difference_lines(
            originales,
            recalculadas,
            ccss=_ccss(ctx.rates),
            contract_of=lambda employee_id: originales[employee_id].contract_id,
        )

    def _line(
        self,
        employee_id: int,
        contratos: list[ContractSnapshot],
        ctx: _Context,
        *,
        exclude_run_id: int,
        original: StoredLine | None,
    ) -> CalculatedLine | None:
        empleado = self._employees.get(employee_id)
        assert empleado is not None
        period = ctx.period
        schedule = ctx.schedule
        rates = ctx.rates
        empleo = Period(empleado.hired_on, empleado.terminated_on or period.ends_on)
        contratos = sorted(contratos, key=lambda c: c.valid_from)

        devengos: list[PayItem] = []
        for contrato in contratos:
            vigente = Period(
                max(contrato.valid_from, empleo.starts_on),
                min(contrato.valid_to or period.ends_on, empleo.ends_on),
            )
            rubro = base_item(Money(contrato.period_salary), schedule, period, vigente)
            if rubro is not None:
                devengos.append(rubro)
        if not devengos:
            # Un contrato que toca el periodo de una persona que ya había salido
            # antes de que empezara: no hay nada que pagarle en esta.
            return None

        actual = contratos[-1]
        salario = Money(actual.period_salary)
        acciones = self._actions.for_employee(employee_id)
        anuladas = {a.cancels_action_id for a in acciones if a.cancels_action_id is not None}
        cancelaciones = {a.id for a in acciones if a.cancels_action_id is not None}
        # En un ajuste se valoran los tramos que la pagada aplicó, ni más ni menos.
        fijas = _applied_portions(original) if original is not None else None

        revertidas: list[PayItem] = []
        for accion in acciones:
            if accion.cancels_action_id is not None:
                if original is not None:
                    revertidas.extend(_copied(original, accion.id))
                else:
                    revertidas.extend(self._reversal(accion))
                continue
            if accion.kind in CONTRACT_KINDS or accion.kind in DEDUCTION_ORDER:
                continue
            if fijas is None:
                if accion.id in anuladas:
                    continue
                devengos.extend(self._portions(accion, acciones, anuladas, schedule, period, salario, rates))
            else:
                # Una anulada después de pagarse sigue acá: su reverso va en la
                # regular siguiente (RN-91), y quitarla del ajuste la revertiría dos veces.
                devengos.extend(
                    self._repriced(accion, acciones, anuladas, fijas.get(accion.id, ()), schedule, salario, rates)
                )
        devengos.extend(r for r in revertidas if r.payer == EARNING)

        cotiza = contribution_base(devengos)
        obreras = list(employee_deductions(cotiza, rates))
        if actual.solidarista_rate:
            tasa = Decimal(actual.solidarista_rate)
            obreras.append(PayItem(SOLIDARISTA, EMPLOYEE, cotiza, tasa, cotiza * tasa))
        patronales = employer_charges(
            cotiza, rates, Decimal(self._employees.rt_rate(actual.ins_policy_id)), exempt=ctx.exempt
        )

        gravable = taxable_base(devengos)
        base_antes, retenido_antes = self._runs.month_withholding(
            employee_id, period.ends_on.year, period.ends_on.month, exclude_run_id=exclude_run_id
        )
        renta = income_tax_withholding(
            gravable,
            schedule.frequency,
            # Un ajuste de un mes ya cerrado liquida contra el mes: lo que debió
            # retener la pagada para que, con lo demás que ya se retuvo, cuadre.
            # Con el mes abierto proyecta como la pagada, y la que cierre ajusta.
            closes_month=ctx.closes or (original is not None and self._month_closed(ctx)),
            month_taxable_before=base_antes,
            month_withheld_before=retenido_antes,
            brackets=ctx.brackets,
            credits=ctx.credits.for_employee(empleado.dependent_children, empleado.spouse_credit),
        )
        retenciones = obreras + [PayItem(INCOME_TAX, EMPLOYEE, gravable, None, renta)]
        retenciones += [r for r in revertidas if r.payer == EMPLOYEE]

        bruto = Money.sum(i.amount for i in devengos)
        neto = bruto - Money.sum(i.amount for i in retenciones)
        if original is None:
            otras = self._deductions(acciones, anuladas, period, schedule, rates, neto)
        else:
            # Las cuotas que ya se cobraron no se vuelven a calcular: se copian.
            otras = [
                i
                for i in original.items
                if i.payer == EMPLOYEE and i.concept in DEDUCTION_ORDER and i.action_id not in cancelaciones
            ]

        rubros = tuple(devengos + retenciones + otras + list(patronales))
        return line_totals(employee_id, actual.id, rubros, _ccss(rates))

    def _month_closed(self, ctx: _Context) -> bool:
        """Si la corrida que cierra el mes del periodo ya está aprobada o pagada."""
        corte = ctx.period.ends_on
        ultimo = corte
        while True:
            siguiente = next_cut(ctx.schedule, ultimo)
            if (siguiente.year, siguiente.month) != (corte.year, corte.month):
                break
            ultimo = siguiente
        # Si el propio corte fuera el último del mes, `ctx.closes` ya lo habría
        # dicho y nadie preguntaría acá.
        cierre = self._runs.find_run(schedule_id=ctx.schedule_id, period_to=ultimo, kind=REGULAR)
        return cierre is not None and cierre.status in (APPROVED, PAID)

    @staticmethod
    def _extends(accion: ActionSnapshot, acciones: list[ActionSnapshot], anuladas: set[int]) -> bool:
        """Una incapacidad que prolonga a otra sin interrupción: los días del
        patrono ya se pagaron en la anterior."""
        return any(
            o.kind == accion.kind and o.ends_on == accion.starts_on - UN_DIA and o.id not in anuladas
            for o in acciones
        )

    def _portions(
        self,
        accion: ActionSnapshot,
        acciones: list[ActionSnapshot],
        anuladas: set[int],
        schedule: Schedule,
        period: Period,
        salario: Money,
        rates: RateSet,
    ) -> list[PayItem]:
        """Los tramos de una acción que esta corrida tiene que aplicar."""
        aplicados = self._actions.applied(accion.id)
        fechas = [i.applied_to for i in aplicados if i.applied_to is not None]
        primero = max(fechas) + UN_DIA if fechas else accion.starts_on
        action = _action(accion)
        extiende = self._extends(accion, acciones, anuladas)
        rubros: list[PayItem] = []
        for tramo in portions(action, schedule, primero, period):
            rubros.extend(action_items(action, tramo, salario, schedule, rates, extends_previous=extiende))
        return rubros

    def _repriced(
        self,
        accion: ActionSnapshot,
        acciones: list[ActionSnapshot],
        anuladas: set[int],
        tramos: list[tuple[date, date]] | tuple[()],
        schedule: Schedule,
        salario: Money,
        rates: RateSet,
    ) -> list[PayItem]:
        """Los mismos tramos que aplicó la pagada, valorados con los datos de hoy."""
        if not tramos:
            return []
        action = _action(accion)
        extiende = self._extends(accion, acciones, anuladas)
        rubros: list[PayItem] = []
        for desde, hasta in tramos:
            if accion.kind in SINGLE_DAY_KINDS:
                tramo = Portion(desde, desde, Decimal(0), 0)
            else:
                tramo = Portion(desde, hasta, counted_days(schedule, desde, hasta), (desde - accion.starts_on).days)
            rubros.extend(action_items(action, tramo, salario, schedule, rates, extends_previous=extiende))
        return rubros

    def _reversal(self, anulacion: ActionSnapshot) -> list[PayItem]:
        """Lo que la anulada ya aplicó, al revés (RN-91); nada si ya se revirtió."""
        if self._actions.applied(anulacion.id):
            return []
        assert anulacion.cancels_action_id is not None
        originales = self._actions.applied(anulacion.cancels_action_id)
        if not originales:
            # La original nunca entró en una corrida: la anulación deja un rubro
            # de cero, que es lo que dice que esta corrida la recogió.
            return [
                PayItem(
                    anulacion.kind,
                    EARNING,
                    Money.zero(),
                    None,
                    Money.zero(),
                    action_id=anulacion.id,
                    applied_from=anulacion.starts_on,
                    applied_to=anulacion.starts_on,
                )
            ]
        return [
            PayItem(
                i.concept,
                i.payer,
                Money(i.base),
                i.rate,
                -Money(i.amount),
                action_id=anulacion.id,
                quantity=i.quantity,
                applied_from=i.applied_from,
                applied_to=i.applied_to,
            )
            for i in originales
        ]

    def _deductions(
        self,
        acciones: list[ActionSnapshot],
        anuladas: set[int],
        period: Period,
        schedule: Schedule,
        rates: RateSet,
        neto: Money,
    ) -> list[PayItem]:
        """Pensión, embargo y las demás, en ese orden, sin pasar del neto (RN-93)."""
        candidatas = sorted(
            (
                a
                for a in acciones
                if a.kind in DEDUCTION_ORDER and a.cancels_action_id is None and a.id not in anuladas
            ),
            key=lambda a: deduction_order(_action(a)),
        )
        if not candidatas:
            return []

        pedidos: list[Money] = []
        cupo_pension = child_support_capacity(neto)
        cupo_embargo: Money | None = None
        for a in candidatas:
            action = _action(a)
            aplicados = self._actions.applied(a.id)
            suma = Money.sum(Money(i.amount) for i in aplicados)
            if a.kind == GARNISHMENT:
                if cupo_embargo is None:
                    # Un solo tope por salario, que todos los embargos se reparten.
                    cupo_embargo = garnishment_capacity(neto, schedule.frequency, Money(rates.rule(UNSEIZABLE_RULE)))
                assert action.total_amount is not None
                pide = Money.zero()
                if is_active(action, period):
                    pide = min(remaining_balance(action.total_amount, suma), cupo_embargo)
                    if action.amount is not None:
                        pide = min(pide, action.amount)
                cupo_embargo = cupo_embargo - pide
            else:
                pide = deduction_due(action, period, applied=suma, applied_before=bool(aplicados))
                if a.kind == CHILD_SUPPORT:
                    pide = min(pide, cupo_pension)
                    cupo_pension = cupo_pension - pide
            pedidos.append(pide)

        aplicado = apply_deductions(neto, pedidos)
        return [
            PayItem(
                a.kind,
                EMPLOYEE,
                pide,
                None,
                monto,
                action_id=a.id,
                applied_from=period.starts_on,
                applied_to=period.ends_on,
            )
            for a, pide, monto in zip(candidatas, pedidos, aplicado)
            # Lo que no cupo no deja rubro: su saldo lo arrastra a la siguiente,
            # y una no recurrente que no entró tiene que poder entrar después.
            if monto.is_positive
        ]
class ApproveRun:
    """Borrador → aprobada (RN-68). Solo con líneas: aprobar el vacío es nada."""

    def __init__(self, *, runs: PayrollRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._runs = runs
        self._uow = uow
        self._clock = clock

    def __call__(self, run_id: int, *, user_id: int) -> None:
        corrida = self._runs.get_run(run_id)
        if corrida is None:
            raise RunNotFound(run_id)
        if corrida.status == PAID:
            raise RunAlreadyPaid(run_id)
        if corrida.status != DRAFT:
            raise RunNotEditable(run_id, corrida.status)
        if self._runs.line_count(run_id) == 0:
            raise RunNotCalculated(run_id)
        with self._uow:
            self._runs.approve(run_id, by=user_id, at=self._clock.now())
            self._uow.commit()


class PayRun:
    """Aprobada → pagada, con fecha del servidor y el asiento si hay libro
    (RN-68, RN-75). La planilla no mueve la caja (RN-74): marcarla pagada es
    todo lo que pasa acá; la plata sale por transferencia, afuera.

    Pagar también mueve las vacaciones (RN-70, T-1209): una corrida regular
    acumula lo ganado por los días del periodo, y una liquidación deja pagados
    los días que liquidó. Van en la misma transacción que el pago: una corrida
    pagada sin su acumulación sería un saldo que nadie puede explicar.
    """

    def __init__(
        self,
        *,
        runs: PayrollRepository,
        ledger: Ledger,
        vacations: VacationRepository,
        schedules: ScheduleRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._runs = runs
        self._ledger = ledger
        self._vacations = vacations
        self._schedules = schedules
        self._uow = uow
        self._clock = clock

    def __call__(self, run_id: int, *, user_id: int) -> int | None:
        corrida = self._runs.get_run(run_id)
        if corrida is None:
            raise RunNotFound(run_id)
        if corrida.status == PAID:
            raise RunAlreadyPaid(run_id)
        if corrida.status != APPROVED:
            raise RunNotApproved(run_id, corrida.status)
        with self._uow:
            asiento = self._ledger.record_payroll(self._runs.totals(run_id))
            self._runs.pay(run_id, by=user_id, at=self._clock.now(), journal_entry_id=asiento)
            self._vacations_after(corrida)
            self._uow.commit()
        return asiento

    def _vacations_after(self, corrida: RunSnapshot) -> None:
        if corrida.kind == REGULAR:
            assert corrida.schedule_id is not None
            jornada = self._schedules.get(corrida.schedule_id)
            assert jornada is not None
            for linea in self._runs.lines(corrida.id):
                # Los días de calendario que el salario base cubrió: quien entró
                # el 20 acumula por once días, no por quince.
                dias = sum(
                    calendar_days(i.applied_from, i.applied_to)
                    for i in linea.items
                    if i.concept == BASE
                    and i.payer == EARNING
                    and i.applied_from is not None
                    and i.applied_to is not None
                )
                # Toda línea regular tiene su salario base con fechas: siempre hay días.
                self._vacations.add(
                    linea.employee_id,
                    kind=VACATION_ACCRUAL,
                    days=vacation_accrual(dias, int(jornada.workdays_per_week)),
                    on_date=corrida.period_to,
                    run_id=corrida.id,
                )
        elif corrida.kind == SETTLEMENT:
            for linea in self._runs.lines(corrida.id):
                for i in linea.items:
                    if i.concept == VACATION_PAYOUT and i.quantity:
                        self._vacations.add(
                            linea.employee_id,
                            kind=VACATION_PAID,
                            days=Decimal(i.quantity),
                            on_date=corrida.period_to,
                            run_id=corrida.id,
                        )
