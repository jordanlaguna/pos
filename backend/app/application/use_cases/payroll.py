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
    PayrollRepository,
    PayrollSettings,
    RateTable,
    RunSnapshot,
    ScheduleRepository,
    ScheduleSnapshot,
)
from app.application.ports.repositories import UnitOfWork
from app.domain.errors import DomainError, InvalidAction, InvalidContract, InvalidSchedule
from app.domain.money import Money
from app.domain.payroll import (
    EARNING,
    EMPLOYEE,
    EMPLOYER,
    INA_CONCEPT,
    PayItem,
    RateSet,
    employee_deductions,
    employer_charges,
    income_tax_withholding,
    rates_at,
)
from app.domain.payroll_actions import (
    CHILD_SUPPORT,
    DEDUCTION,
    DEDUCTION_ORDER,
    GARNISHMENT,
    POSITION_CHANGE,
    RAISE,
    TERMINATION,
    Action,
    action_items,
    apply_deductions,
    base_item,
    check_action,
    child_support_capacity,
    contribution_base,
    deduction_due,
    deduction_order,
    garnishment_capacity,
    is_active,
    portions,
    remaining_balance,
    taxable_base,
)
from app.domain.payroll_calendar import Period, Schedule, closes_month, period_for
from app.domain.payroll_staff import check_termination

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

INCOME_TAX = "income_tax"
SOLIDARISTA = "solidarista"
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
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._employees = employees
        self._actions = actions
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

    def __init__(self, *, actions: ActionRepository, uow: UnitOfWork) -> None:
        self._actions = actions
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
        with self._uow:
            self._actions.update(action_id, **corregida.fields())
            self._uow.commit()


class CancelAction:
    """Anula una acción con **otra** que la referencia (RN-91).

    Siempre con otra, también si la original todavía no entró en ninguna
    corrida: así el historial dice que existió y que se anuló, y la corrida que
    la recoja deja constancia de las dos. Si ya se había aplicado, la corrida
    siguiente escribe sus rubros al revés.
    """

    def __init__(self, *, actions: ActionRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._actions = actions
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

        ahora = self._clock.now()
        with self._uow:
            for contrato in self._employees.contracts_of(employee_id):
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
            self._uow.commit()
        return liquidacion.id


# ------------------------------------------------------------------ corridas


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


class CalculateRun:
    """Calcula un borrador: toma las acciones, las parte y congela los rubros.

    Por cada empleado con contrato en el periodo:

    1. El salario base de cada contrato que tocó el periodo (entero o
       proporcional, RN-94).
    2. Los tramos de sus acciones que ninguna corrida aplicó, con sus fechas
       (RN-90, RN-91), y las anulaciones de lo que sí se aplicó, al revés.
    3. Las cargas obreras sobre lo que cotiza, el solidarista si el contrato lo
       tiene, y la renta del mes (RN-73).
    4. Las deducciones en el orden de RN-93 —pensión, embargo, las demás— sin
       dejar el neto negativo.
    5. Las cargas patronales y la prima de riesgos del trabajo de su póliza.

    Solo las corridas regulares: el aguinaldo, la liquidación y el ajuste
    tienen cada uno su cálculo (T-1208, T-1210, T-1212).
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
        uow: UnitOfWork,
        country: str = "CR",
    ) -> None:
        self._runs = runs
        self._schedules = schedules
        self._employees = employees
        self._actions = actions
        self._rates = rates
        self._settings = settings
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
        if corrida.kind != REGULAR:
            raise RunNotEditable(run_id, corrida.kind)

        assert corrida.schedule_id is not None
        jornada = self._schedules.get(corrida.schedule_id)
        assert jornada is not None
        schedule = _schedule(jornada)
        periodo = Period(corrida.period_from, corrida.period_to)
        corte = corrida.period_to

        # Las cargas se exigen todas al resolver (`RatesMissing`); las reglas,
        # cuando hacen falta.
        tasas = rates_at(self._rates.rates(self._country), corte, self._country)
        tramos = tuple(self._rates.brackets_at(corte, self._country))
        creditos = self._rates.credits_at(corte, self._country)
        exentas = frozenset({INA_CONCEPT}) if self._settings.payroll().get("ina_exempt") else frozenset()
        cierra = closes_month(schedule, corte)

        por_empleado: dict[int, list[ContractSnapshot]] = {}
        for contrato in self._employees.contracts_in(jornada.id, periodo):
            por_empleado.setdefault(contrato.employee_id, []).append(contrato)

        lineas: list[CalculatedLine] = []
        for employee_id in sorted(por_empleado):
            linea = self._line(
                employee_id,
                por_empleado[employee_id],
                schedule=schedule,
                period=periodo,
                rates=tasas,
                brackets=tramos,
                credits=creditos,
                exempt=exentas,
                closes=cierra,
                run_id=corrida.id,
            )
            if linea is not None:
                lineas.append(linea)

        with self._uow:
            self._runs.replace_lines(corrida.id, lineas)
            self._uow.commit()
        return CalculatedRun(corrida.id, periodo, cierra, tuple(lineas))

    # ------------------------------------------------------------ por dentro

    def _line(
        self,
        employee_id: int,
        contratos: list[ContractSnapshot],
        *,
        schedule: Schedule,
        period: Period,
        rates: RateSet,
        brackets: tuple,
        credits,
        exempt: frozenset[str],
        closes: bool,
        run_id: int,
    ) -> CalculatedLine | None:
        empleado = self._employees.get(employee_id)
        assert empleado is not None
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

        revertidas: list[PayItem] = []
        for accion in acciones:
            if accion.cancels_action_id is not None:
                revertidas.extend(self._reversal(accion))
                continue
            if accion.id in anuladas or accion.kind in CONTRACT_KINDS or accion.kind in DEDUCTION_ORDER:
                continue
            devengos.extend(self._portions(accion, acciones, anuladas, schedule, period, salario, rates))
        devengos.extend(r for r in revertidas if r.payer == EARNING)

        cotiza = contribution_base(devengos)
        obreras = list(employee_deductions(cotiza, rates))
        if actual.solidarista_rate:
            tasa = Decimal(actual.solidarista_rate)
            obreras.append(PayItem(SOLIDARISTA, EMPLOYEE, cotiza, tasa, cotiza * tasa))
        patronales = employer_charges(
            cotiza, rates, Decimal(self._employees.rt_rate(actual.ins_policy_id)), exempt=exempt
        )

        gravable = taxable_base(devengos)
        base_antes, retenido_antes = self._runs.month_withholding(
            employee_id, period.ends_on.year, period.ends_on.month, exclude_run_id=run_id
        )
        renta = income_tax_withholding(
            gravable,
            schedule.frequency,
            closes_month=closes,
            month_taxable_before=base_antes,
            month_withheld_before=retenido_antes,
            brackets=brackets,
            credits=credits.for_employee(empleado.dependent_children, empleado.spouse_credit),
        )
        retenciones = obreras + [PayItem(INCOME_TAX, EMPLOYEE, gravable, None, renta)]
        retenciones += [r for r in revertidas if r.payer == EMPLOYEE]

        bruto = Money.sum(i.amount for i in devengos)
        neto = bruto - Money.sum(i.amount for i in retenciones)
        otras = self._deductions(acciones, anuladas, period, schedule, rates, neto)

        rubros = tuple(devengos + retenciones + otras + list(patronales))
        return self._totals(employee_id, actual.id, rubros, rates)

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
        # Una incapacidad que prolonga a otra sin interrupción: los días del
        # patrono ya se pagaron en la anterior.
        extiende = any(
            o.kind == accion.kind and o.ends_on == accion.starts_on - UN_DIA and o.id not in anuladas
            for o in acciones
        )
        rubros: list[PayItem] = []
        for tramo in portions(action, schedule, primero, period):
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

    @staticmethod
    def _totals(employee_id: int, contract_id: int, rubros: tuple[PayItem, ...], rates: RateSet) -> CalculatedLine:
        ccss = {r.concept for r in rates.contributions(EMPLOYEE)}
        bruto = Money.sum(i.amount for i in rubros if i.payer == EARNING)
        cargas = Money.sum(i.amount for i in rubros if i.payer == EMPLOYEE and i.concept in ccss)
        renta = Money.sum(i.amount for i in rubros if i.payer == EMPLOYEE and i.concept == INCOME_TAX)
        otras = Money.sum(
            i.amount
            for i in rubros
            if i.payer == EMPLOYEE and i.concept not in ccss and i.concept != INCOME_TAX
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
    """

    def __init__(self, *, runs: PayrollRepository, ledger: Ledger, uow: UnitOfWork, clock: Clock) -> None:
        self._runs = runs
        self._ledger = ledger
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
            self._uow.commit()
        return asiento
