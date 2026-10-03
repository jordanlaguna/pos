"""Los datos de la planilla, dichos desde adentro (F12, T-1205, T-1206, T-1218).

Siete puertos, por siete razones de cambio distintas: las jornadas, la gente y
sus contratos, las acciones de personal, las corridas con sus líneas y rubros,
las tasas del país, la configuración de planilla de la compañía y —de F11— el
libro, que vive en `ports/ledger.py`.

Igual que el resto de los puertos, cada método es una pregunta en el idioma del
negocio: `contracts_in(schedule, period)` y no un `SELECT`. Los *snapshots* son
la forma de los datos, no filas de SQLAlchemy: `period_salary` llega como
`Decimal` y el caso de uso lo envuelve en `Money`, que es quien sabe redondear.

Lo que la aplicación escribe de una corrida es `CalculatedLine`: un empleado
con sus rubros ya calculados (`PayItem`, del dominio). El repositorio los guarda
tal cual, con base, tasa y monto; **esa escritura es el congelamiento** de RN-66.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, Sequence

from app.domain.ledger import PaidPayroll
from app.domain.money import Money
from app.domain.payroll import PayItem, Rate, TaxBracket, TaxCredits
from app.domain.payroll_benefits import SeveranceBracket
from app.domain.payroll_calendar import Period
from app.domain.payroll_files import Employer, WorkerMonth


class ScheduleSnapshot(Protocol):
    id: int
    name: str
    frequency: str
    shift: str
    hours_per_day: Decimal
    workdays_per_week: int
    rest_day_paid: bool
    first_cut_day: int | None
    cut_weekday: int | None
    series_start: date | None
    is_active: bool


class EmployeeSnapshot(Protocol):
    id: int
    hired_on: date
    terminated_on: date | None
    #: Una de las cinco causas de RN-71, cuando ya salió.
    termination_cause: str | None
    #: Para el crédito fiscal de la renta (RN-73).
    dependent_children: int
    spouse_credit: bool


class ContractSnapshot(Protocol):
    id: int
    employee_id: int
    schedule_id: int
    position_id: int
    ins_policy_id: int | None
    valid_from: date
    valid_to: date | None
    #: El salario del periodo de su jornada (RN-94).
    period_salary: Decimal
    solidarista_rate: Decimal | None


class ActionSnapshot(Protocol):
    id: int
    employee_id: int
    kind: str
    starts_on: date
    ends_on: date | None
    hours: Decimal | None
    days: Decimal | None
    amount: Decimal | None
    total_amount: Decimal | None
    new_salary: Decimal | None
    position_id: int | None
    is_recurring: bool
    memo: str | None
    #: A cuál anula, si es una anulación (RN-91).
    cancels_action_id: int | None
    suspended_at: datetime | None


class AppliedItem(Protocol):
    """Un rubro que una corrida aprobada o pagada ya dejó por una acción."""

    run_id: int
    concept: str
    payer: str
    base: Decimal
    rate: Decimal | None
    amount: Decimal
    quantity: Decimal | None
    applied_from: date | None
    applied_to: date | None


class RunSnapshot(Protocol):
    id: int
    kind: str
    schedule_id: int | None
    period_from: date
    period_to: date
    pay_date: date
    status: str
    #: La corrida pagada que este ajuste corrige (RN-68, T-1212).
    adjusts_run_id: int | None
    journal_entry_id: int | None


class VacationSnapshot(Protocol):
    """Una fila de `vacation_movements` (RN-70)."""

    id: int
    employee_id: int
    #: 'opening' | 'accrual' | 'taken' | 'paid'.
    kind: str
    days: Decimal
    on_date: date
    run_id: int | None
    action_id: int | None


@dataclass(frozen=True)
class CalculatedLine:
    """Un empleado en una corrida, con sus rubros: lo que se congela (RN-66)."""

    employee_id: int
    contract_id: int
    items: tuple[PayItem, ...]
    gross: Money
    employee_deductions: Money
    income_tax: Money
    other_deductions: Money
    net: Money
    employer_charges: Money


@dataclass(frozen=True)
class StoredLine:
    """Una línea ya escrita, leída de vuelta con sus rubros congelados.

    Es lo que un ajuste compara (T-1212), lo que la liquidación usa para saber
    de quién es (T-1210) y lo que el pago lee para acumular vacaciones (T-1209).
    """

    id: int
    employee_id: int
    contract_id: int
    gross: Money
    employee_deductions: Money
    income_tax: Money
    other_deductions: Money
    net: Money
    employer_charges: Money
    items: tuple[PayItem, ...]


class ScheduleRepository(Protocol):
    def get(self, schedule_id: int) -> ScheduleSnapshot | None: ...


class EmployeeRepository(Protocol):
    def get(self, employee_id: int) -> EmployeeSnapshot | None: ...

    def contracts_of(self, employee_id: int) -> list[ContractSnapshot]:
        """Todos los del empleado, del más viejo al más nuevo."""
        ...

    def contracts_in(self, schedule_id: int, period: Period) -> list[ContractSnapshot]:
        """Los contratos de esa jornada que tocan el periodo, de cualquier empleado."""
        ...

    def contracts_between(self, period: Period) -> list[ContractSnapshot]:
        """Los contratos que tocan el periodo, de cualquier jornada: el aguinaldo
        es de toda la compañía, no de un grupo de pago."""
        ...

    def add_contract(
        self,
        *,
        employee_id: int,
        schedule_id: int,
        position_id: int,
        ins_policy_id: int | None,
        valid_from: date,
        period_salary: Money,
        solidarista_rate: Decimal | None,
    ) -> int: ...

    def close_contract(self, contract_id: int, *, valid_to: date) -> None: ...

    def terminate(self, employee_id: int, *, on: date, cause: str) -> None: ...

    def position_active(self, position_id: int) -> bool | None:
        """Si el puesto está activo, o `None` si no existe en esta compañía."""
        ...

    def rt_rate(self, ins_policy_id: int | None) -> Decimal:
        """La prima de riesgos del trabajo de esa póliza, o de la póliza por
        omisión si el contrato no dice una. Cero si la compañía no tiene
        ninguna: la prima es costo del patrono y no toca lo que cobra el
        empleado, y la pantalla de lo que falta lo reclama."""
        ...


class ActionRepository(Protocol):
    def get(self, action_id: int) -> ActionSnapshot | None: ...

    def for_employee(self, employee_id: int) -> list[ActionSnapshot]:
        """Todas, incluidas las anulaciones y las suspendidas, por fecha."""
        ...

    def add(self, **fields: object) -> int: ...

    def update(self, action_id: int, **fields: object) -> None: ...

    def suspend(self, action_id: int, *, at: datetime, by: int, reason: str) -> None: ...

    def applied(self, action_id: int) -> list[AppliedItem]:
        """Los rubros que dejó en corridas **aprobadas o pagadas**.

        Aprobadas también, y no solo pagadas como dice RN-92 del saldo: una
        aprobada no se recalcula, así que lo que aplicó ya no va a cambiar, y
        contarla evita que la corrida siguiente vuelva a aplicar lo mismo
        mientras la anterior espera el pago.
        """
        ...


class PayrollRepository(Protocol):
    def get_run(self, run_id: int) -> RunSnapshot | None: ...

    def find_run(self, *, schedule_id: int | None, period_to: date, kind: str) -> RunSnapshot | None:
        """La corrida de esa clase con ese corte; sin jornada, la del aguinaldo."""
        ...

    def add_run(
        self,
        *,
        kind: str,
        schedule_id: int | None,
        period_from: date,
        period_to: date,
        pay_date: date,
        created_by: int,
        created_at: datetime,
        adjusts_run_id: int | None = None,
    ) -> RunSnapshot: ...

    def line_count(self, run_id: int) -> int: ...

    def lines(self, run_id: int) -> list[StoredLine]:
        """Las líneas de la corrida con sus rubros, por empleado."""
        ...

    def replace_lines(self, run_id: int, lines: Sequence[CalculatedLine]) -> None:
        """Borra lo que la corrida tuviera y escribe estas líneas con sus rubros."""
        ...

    def totals(self, run_id: int) -> PaidPayroll:
        """Las sumas de sus líneas, en la forma en que el libro las quiere."""
        ...

    def paid_earnings(self, employee_id: int, period: Period) -> list[tuple[date, Money]]:
        """`(corte, salario devengado)` por cada corrida **pagada** —regular o de
        ajuste— del empleado cuyo corte cae en el periodo. Lo devengado es la
        suma de los rubros de `EARNED_CONCEPTS`: lo que cuenta para el aguinaldo
        y el promedio de la liquidación (RN-69, RN-71)."""
        ...

    def month_withholding(
        self, employee_id: int, year: int, month: int, *, exclude_run_id: int
    ) -> tuple[Money, Money]:
        """`(base gravable, renta retenida)` del empleado en las corridas
        regulares aprobadas o pagadas cuyo corte cae en ese mes, sin contar
        la que se está calculando (RN-73)."""
        ...

    def approve(self, run_id: int, *, by: int, at: datetime) -> None: ...

    def pay(self, run_id: int, *, by: int, at: datetime, journal_entry_id: int | None) -> None: ...


class RateTable(Protocol):
    def rates(self, country: str) -> list[Rate]:
        """Todas las filas del país; el dominio decide cuáles rigen (`rates_at`)."""
        ...

    def brackets_at(self, on: date, country: str) -> list[TaxBracket]: ...

    def credits_at(self, on: date, country: str) -> TaxCredits: ...

    def severance_at(self, on: date, country: str) -> list[SeveranceBracket]:
        """La tabla de cesantía que rige a esa fecha (art. 29, RN-71), vacía si no hay."""
        ...


class VacationRepository(Protocol):
    """Los movimientos de vacaciones; el saldo es su suma, nunca una columna (RN-70)."""

    def movements(self, employee_id: int) -> list[VacationSnapshot]: ...

    def add(
        self,
        employee_id: int,
        *,
        kind: str,
        days: Decimal,
        on_date: date,
        run_id: int | None = None,
        action_id: int | None = None,
    ) -> int: ...

    def update_for_action(self, action_id: int, *, days: Decimal, on_date: date) -> None:
        """Corrige el disfrute de una acción que nadie aplicó todavía."""
        ...


class OpeningRepository(Protocol):
    """Lo devengado antes de VentaSys, mes a mes (RN-97)."""

    def earnings(self, employee_id: int, period: Period) -> list[tuple[date, Money]]:
        """`(primer día del mes, bruto)` de los meses de apertura dentro del periodo."""
        ...

    def add_earning(self, employee_id: int, *, month: date, gross: Money, by: int, at: datetime) -> None: ...


class PayrollReports(Protocol):
    """Lo que un mes pagado sabe de cada trabajador, para los archivos (RN-96).

    Es un modelo de lectura: junta lo que las corridas pagadas del mes dejaron
    con los datos de la ficha, del contrato y de las acciones, en la forma que
    el dominio formatea (`payroll_files.py`).
    """

    def month(self, year: int, month: int) -> list[WorkerMonth]:
        """Un `WorkerMonth` por empleado con alguna línea en las corridas
        pagadas —regulares y ajustes— cuyo corte cae en el mes."""
        ...

    def employer(self) -> Employer: ...

    def policy_number(self, policy_id: int) -> str | None: ...


class ImportRepository(Protocol):
    """Lo que la importación busca por nombre y da de alta (RN-97, T-1220).

    Quien viene de otro sistema trae nombres, no ids: la jornada «Quincenal», el
    puesto «Cajera», la póliza «RT-1». Acá se traducen.
    """

    def position_by_name(self, name: str) -> tuple[int, bool] | None:
        """`(id, activo)` del puesto con ese nombre, o `None`."""
        ...

    def add_position(self, *, name: str, ccss_code: str, ins_code: str) -> int: ...

    def schedule_by_name(self, name: str) -> ScheduleSnapshot | None: ...

    def policy_by_number(self, number: str) -> int | None: ...

    def employee_by_identification(self, identification: str) -> int | None: ...

    def add_employee(self, **fields: object) -> int: ...


class PayrollSettings(Protocol):
    """La sección `payroll` de la configuración: número patronal y si el INA
    está exento (T-1217)."""

    def payroll(self) -> dict: ...
