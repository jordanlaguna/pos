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
from app.domain.payroll_calendar import Period


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
    journal_entry_id: int | None


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

    def find_run(self, *, schedule_id: int, period_to: date, kind: str) -> RunSnapshot | None: ...

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
    ) -> RunSnapshot: ...

    def line_count(self, run_id: int) -> int: ...

    def replace_lines(self, run_id: int, lines: Sequence[CalculatedLine]) -> None:
        """Borra lo que la corrida tuviera y escribe estas líneas con sus rubros."""
        ...

    def totals(self, run_id: int) -> PaidPayroll:
        """Las sumas de sus líneas, en la forma en que el libro las quiere."""
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


class PayrollSettings(Protocol):
    """La sección `payroll` de la configuración: número patronal y si el INA
    está exento (T-1217)."""

    def payroll(self) -> dict: ...
