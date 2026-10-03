"""Dobles de prueba de los puertos de planilla (F12).

Son listas en memoria que cumplen `ports/payroll.py` sin heredar nada. Lo único
con lógica es `applied`: igual que el adaptador real, mira los rubros de las
corridas aprobadas o pagadas, así que las pruebas de la segunda corrida pueden
aprobar la primera y ver cómo cambia lo que se aplica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from app.application.ports.payroll import CalculatedLine
from app.domain.ledger import PaidPayroll
from app.domain.money import Money
from app.domain.payroll import EARNING, Rate, TaxBracket, TaxCredits
from app.domain.payroll_actions import TAXABLE
from app.domain.payroll_calendar import Period


class RelojFijo:
    def __init__(self, ahora: datetime) -> None:
        self.ahora = ahora

    def now(self) -> datetime:
        return self.ahora

    def today(self) -> date:
        return self.ahora.date()


@dataclass
class FilaDeJornada:
    id: int
    name: str
    frequency: str
    shift: str = "day"
    hours_per_day: Decimal = Decimal(8)
    workdays_per_week: int = 6
    rest_day_paid: bool = True
    first_cut_day: int | None = None
    cut_weekday: int | None = None
    series_start: date | None = None
    is_active: bool = True


@dataclass
class FilaDeEmpleado:
    id: int
    hired_on: date
    terminated_on: date | None = None
    termination_cause: str | None = None
    dependent_children: int = 0
    spouse_credit: bool = False


@dataclass
class FilaDeContrato:
    id: int
    employee_id: int
    schedule_id: int
    position_id: int
    ins_policy_id: int | None
    valid_from: date
    valid_to: date | None
    period_salary: Decimal
    solidarista_rate: Decimal | None = None


@dataclass
class FilaDeAccion:
    id: int
    employee_id: int
    kind: str
    starts_on: date
    ends_on: date | None = None
    hours: Decimal | None = None
    days: Decimal | None = None
    amount: Decimal | None = None
    total_amount: Decimal | None = None
    new_salary: Decimal | None = None
    position_id: int | None = None
    is_recurring: bool = False
    memo: str | None = None
    cancels_action_id: int | None = None
    suspended_at: datetime | None = None
    suspended_by: int | None = None
    suspension_reason: str | None = None
    source: str = "manual"
    created_by: int = 0
    created_at: datetime | None = None


@dataclass
class FilaDeCorrida:
    id: int
    kind: str
    schedule_id: int | None
    period_from: date
    period_to: date
    pay_date: date
    created_by: int
    created_at: datetime
    status: str = "draft"
    journal_entry_id: int | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    paid_by: int | None = None
    paid_at: datetime | None = None


@dataclass(frozen=True)
class RubroAplicado:
    run_id: int
    concept: str
    payer: str
    base: Decimal
    rate: Decimal | None
    amount: Decimal
    quantity: Decimal | None
    applied_from: date | None
    applied_to: date | None


class FakeScheduleRepository:
    def __init__(self, jornadas: list[FilaDeJornada]) -> None:
        self.jornadas = {j.id: j for j in jornadas}

    def get(self, schedule_id: int) -> FilaDeJornada | None:
        return self.jornadas.get(schedule_id)


class FakeEmployeeRepository:
    def __init__(
        self,
        empleados: list[FilaDeEmpleado] | None = None,
        contratos: list[FilaDeContrato] | None = None,
        *,
        puestos: dict[int, bool] | None = None,
        polizas: dict[int, Decimal] | None = None,
        poliza_por_omision: Decimal | None = None,
    ) -> None:
        self.empleados = {e.id: e for e in (empleados or [])}
        self.contratos = list(contratos or [])
        self.puestos = puestos if puestos is not None else {1: True}
        self.polizas = polizas or {}
        self.poliza_por_omision = poliza_por_omision
        self.bajas: list[tuple[int, date, str]] = []

    def get(self, employee_id: int) -> FilaDeEmpleado | None:
        return self.empleados.get(employee_id)

    def contracts_of(self, employee_id: int) -> list[FilaDeContrato]:
        return sorted((c for c in self.contratos if c.employee_id == employee_id), key=lambda c: c.valid_from)

    def contracts_in(self, schedule_id: int, period: Period) -> list[FilaDeContrato]:
        return [
            c
            for c in self.contratos
            if c.schedule_id == schedule_id
            and c.valid_from <= period.ends_on
            and (c.valid_to is None or c.valid_to >= period.starts_on)
        ]

    def add_contract(self, **datos) -> int:
        nuevo = FilaDeContrato(
            id=max((c.id for c in self.contratos), default=0) + 1,
            valid_to=None,
            **{**datos, "period_salary": datos["period_salary"].amount},
        )
        self.contratos.append(nuevo)
        return nuevo.id

    def close_contract(self, contract_id: int, *, valid_to: date) -> None:
        next(c for c in self.contratos if c.id == contract_id).valid_to = valid_to

    def terminate(self, employee_id: int, *, on: date, cause: str) -> None:
        empleado = self.empleados[employee_id]
        empleado.terminated_on = on
        empleado.termination_cause = cause
        self.bajas.append((employee_id, on, cause))

    def position_active(self, position_id: int) -> bool | None:
        return self.puestos.get(position_id)

    def rt_rate(self, ins_policy_id: int | None) -> Decimal:
        if ins_policy_id is not None:
            return self.polizas[ins_policy_id]
        return self.poliza_por_omision if self.poliza_por_omision is not None else Decimal(0)


class FakePayrollRepository:
    def __init__(self, corridas: list[FilaDeCorrida] | None = None) -> None:
        self.corridas = {c.id: c for c in (corridas or [])}
        self.lineas: dict[int, list[CalculatedLine]] = {}

    def get_run(self, run_id: int) -> FilaDeCorrida | None:
        return self.corridas.get(run_id)

    def find_run(self, *, schedule_id: int, period_to: date, kind: str) -> FilaDeCorrida | None:
        return next(
            (
                c
                for c in self.corridas.values()
                if c.schedule_id == schedule_id and c.period_to == period_to and c.kind == kind
            ),
            None,
        )

    def add_run(self, **datos) -> FilaDeCorrida:
        corrida = FilaDeCorrida(id=max(self.corridas, default=0) + 1, **datos)
        self.corridas[corrida.id] = corrida
        return corrida

    def line_count(self, run_id: int) -> int:
        return len(self.lineas.get(run_id, []))

    def replace_lines(self, run_id: int, lines: Sequence[CalculatedLine]) -> None:
        self.lineas[run_id] = list(lines)

    def totals(self, run_id: int) -> PaidPayroll:
        corrida = self.corridas[run_id]
        lineas = self.lineas.get(run_id, [])
        return PaidPayroll(
            id=run_id,
            date=corrida.pay_date,
            gross=Money.sum(l.gross for l in lineas),
            employer_charges=Money.sum(l.employer_charges for l in lineas),
            social_security=Money.sum(l.employee_deductions for l in lineas),
            income_tax=Money.sum(l.income_tax for l in lineas),
            other_deductions=Money.sum(l.other_deductions for l in lineas),
            net=Money.sum(l.net for l in lineas),
        )

    def month_withholding(self, employee_id: int, year: int, month: int, *, exclude_run_id: int) -> tuple[Money, Money]:
        base = Money.zero()
        retenido = Money.zero()
        for corrida in self.corridas.values():
            if corrida.id == exclude_run_id or corrida.kind != "regular" or corrida.status not in ("approved", "paid"):
                continue
            if (corrida.period_to.year, corrida.period_to.month) != (year, month):
                continue
            for linea in self.lineas.get(corrida.id, []):
                if linea.employee_id != employee_id:
                    continue
                base = base + Money.sum(i.amount for i in linea.items if i.payer == EARNING and i.concept in TAXABLE)
                retenido = retenido + linea.income_tax
        return base, retenido

    def approve(self, run_id: int, *, by: int, at: datetime) -> None:
        corrida = self.corridas[run_id]
        corrida.status = "approved"
        corrida.approved_by = by
        corrida.approved_at = at

    def pay(self, run_id: int, *, by: int, at: datetime, journal_entry_id: int | None) -> None:
        corrida = self.corridas[run_id]
        corrida.status = "paid"
        corrida.paid_by = by
        corrida.paid_at = at
        corrida.journal_entry_id = journal_entry_id


class FakeActionRepository:
    """Las acciones, y lo que aplicó cada una según las corridas del otro doble."""

    def __init__(self, acciones: list[FilaDeAccion] | None = None, *, runs: FakePayrollRepository | None = None) -> None:
        self.acciones = list(acciones or [])
        self.runs = runs or FakePayrollRepository()

    def get(self, action_id: int) -> FilaDeAccion | None:
        return next((a for a in self.acciones if a.id == action_id), None)

    def for_employee(self, employee_id: int) -> list[FilaDeAccion]:
        return sorted((a for a in self.acciones if a.employee_id == employee_id), key=lambda a: (a.starts_on, a.id))

    def add(self, **datos) -> int:
        nueva = FilaDeAccion(id=max((a.id for a in self.acciones), default=0) + 1, **datos)
        self.acciones.append(nueva)
        return nueva.id

    def update(self, action_id: int, **datos) -> None:
        accion = self.get(action_id)
        assert accion is not None
        for clave, valor in datos.items():
            setattr(accion, clave, valor)

    def suspend(self, action_id: int, *, at: datetime, by: int, reason: str) -> None:
        accion = self.get(action_id)
        assert accion is not None
        accion.suspended_at = at
        accion.suspended_by = by
        accion.suspension_reason = reason

    def applied(self, action_id: int) -> list[RubroAplicado]:
        rubros = []
        for corrida in self.runs.corridas.values():
            if corrida.status not in ("approved", "paid"):
                continue
            for linea in self.runs.lineas.get(corrida.id, []):
                for i in linea.items:
                    if i.action_id == action_id:
                        rubros.append(
                            RubroAplicado(
                                corrida.id,
                                i.concept,
                                i.payer,
                                i.base.amount,
                                i.rate,
                                i.amount.amount,
                                i.quantity,
                                i.applied_from,
                                i.applied_to,
                            )
                        )
        return rubros


class FakeRateTable:
    def __init__(self, tasas: list[Rate], tramos: list[TaxBracket] | None = None, creditos: TaxCredits | None = None) -> None:
        self.tasas = tasas
        self.tramos = tramos or []
        self.creditos = creditos or TaxCredits(Money.zero(), Money.zero())

    def rates(self, country: str) -> list[Rate]:
        return self.tasas

    def brackets_at(self, on: date, country: str) -> list[TaxBracket]:
        return self.tramos

    def credits_at(self, on: date, country: str) -> TaxCredits:
        return self.creditos


class FakePayrollSettings:
    def __init__(self, **datos) -> None:
        self.datos = datos

    def payroll(self) -> dict:
        return dict(self.datos)


@dataclass
class LibroEspia:
    """Anota la corrida que le cuentan y devuelve el id de asiento que se le dio."""

    asiento: int | None = 7
    pagadas: list[PaidPayroll] = field(default_factory=list)

    def record_payroll(self, payroll: PaidPayroll) -> int | None:
        self.pagadas.append(payroll)
        return self.asiento

    def post(self, entry):  # pragma: no cover - no se usa acá
        return None
