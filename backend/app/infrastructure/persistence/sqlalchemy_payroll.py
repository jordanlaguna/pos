"""Los datos de planilla en SQLAlchemy (F12, T-1205, T-1206, T-1218).

Adaptadores de `ports/payroll.py`. Ninguno confirma: escriben en la sesión que
les pasan y el `commit` lo da quien abrió la unidad de trabajo, igual que el
resto de los repositorios.

El `company_id` no se escribe en ninguna parte y no es un olvido: lo pone el
escuchador de `before_flush` (plan §3.3), el mismo que lo pone en una venta. Las
cuatro tablas del país —tasas, tramos, créditos y cesantía— no lo llevan, y la
tabla de tasas se lee igual desde cualquier compañía (RN-67).

Las sumas se hacen en Python sobre las filas de la corrida y no con
agregados de SQL: son decenas de filas, y un `func.sum` envuelve la consulta en
una subconsulta donde el filtro de compañía no entra (la misma trampa que
`count()`, plan §3.3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from app.application.ports.payroll import CalculatedLine
from app.domain.ledger import PaidPayroll
from app.domain.money import Money
from app.domain.payroll import EARNING, Rate, TaxBracket, TaxCredits
from app.domain.payroll_actions import TAXABLE
from app.domain.payroll_calendar import Period
from app.models.model_payroll import (
    Employee,
    EmploymentContract,
    IncomeTaxBracket,
    IncomeTaxCredit,
    InsPolicy,
    PayrollRate,
    PayrollRun,
    PayrollRunItem,
    PayrollRunLine,
    PersonnelAction,
    Position,
    WorkSchedule,
)
from app.models.model_settings import Settings
from app.utils.tenancy import compania_actual

APROBADA_O_PAGADA = ("approved", "paid")


class SqlAlchemyScheduleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, schedule_id: int) -> WorkSchedule | None:
        return self._db.query(WorkSchedule).filter(WorkSchedule.id == schedule_id).first()

    def has_paid_runs(self, schedule_id: int) -> bool:
        """Si alguna corrida pagada es de esta jornada: entonces sus cortes no se
        tocan (RF-83, `schedule_locked`)."""
        return (
            self._db.query(PayrollRun.id)
            .filter(PayrollRun.schedule_id == schedule_id, PayrollRun.status == "paid")
            .first()
            is not None
        )


class SqlAlchemyEmployeeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, employee_id: int) -> Employee | None:
        return self._db.query(Employee).filter(Employee.id == employee_id).first()

    def contracts_of(self, employee_id: int) -> list[EmploymentContract]:
        return (
            self._db.query(EmploymentContract)
            .filter(EmploymentContract.employee_id == employee_id)
            .order_by(EmploymentContract.valid_from, EmploymentContract.id)
            .all()
        )

    def contracts_in(self, schedule_id: int, period: Period) -> list[EmploymentContract]:
        return (
            self._db.query(EmploymentContract)
            .filter(
                EmploymentContract.schedule_id == schedule_id,
                EmploymentContract.valid_from <= period.ends_on,
                (EmploymentContract.valid_to.is_(None)) | (EmploymentContract.valid_to >= period.starts_on),
            )
            .order_by(EmploymentContract.employee_id, EmploymentContract.valid_from)
            .all()
        )

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
    ) -> int:
        contrato = EmploymentContract(
            employee_id=employee_id,
            schedule_id=schedule_id,
            position_id=position_id,
            ins_policy_id=ins_policy_id,
            valid_from=valid_from,
            valid_to=None,
            period_salary=period_salary.amount,
            solidarista_rate=solidarista_rate,
        )
        self._db.add(contrato)
        self._db.flush()
        return contrato.id

    def close_contract(self, contract_id: int, *, valid_to: date) -> None:
        contrato = self._db.query(EmploymentContract).filter(EmploymentContract.id == contract_id).first()
        contrato.valid_to = valid_to
        self._db.flush()

    def terminate(self, employee_id: int, *, on: date, cause: str) -> None:
        empleado = self.get(employee_id)
        empleado.terminated_on = on
        empleado.termination_cause = cause
        empleado.is_active = False
        self._db.flush()

    def position_active(self, position_id: int) -> bool | None:
        puesto = self._db.query(Position).filter(Position.id == position_id).first()
        return None if puesto is None else bool(puesto.is_active)

    def rt_rate(self, ins_policy_id: int | None) -> Decimal:
        consulta = self._db.query(InsPolicy)
        if ins_policy_id is not None:
            poliza = consulta.filter(InsPolicy.id == ins_policy_id).first()
        else:
            poliza = consulta.filter(InsPolicy.is_default.is_(True)).first()
        return Decimal(poliza.rt_rate) if poliza is not None else Decimal(0)


@dataclass(frozen=True)
class RubroAplicado:
    """Un rubro que una corrida aprobada o pagada dejó por una acción."""

    run_id: int
    run_status: str
    period_from: date
    period_to: date
    concept: str
    payer: str
    base: Decimal
    rate: Decimal | None
    amount: Decimal
    quantity: Decimal | None
    applied_from: date | None
    applied_to: date | None


class SqlAlchemyActionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, action_id: int) -> PersonnelAction | None:
        return self._db.query(PersonnelAction).filter(PersonnelAction.id == action_id).first()

    def for_employee(self, employee_id: int) -> list[PersonnelAction]:
        return (
            self._db.query(PersonnelAction)
            .filter(PersonnelAction.employee_id == employee_id)
            .order_by(PersonnelAction.starts_on, PersonnelAction.id)
            .all()
        )

    def add(self, **fields: object) -> int:
        accion = PersonnelAction(**fields)
        self._db.add(accion)
        self._db.flush()
        return accion.id

    def update(self, action_id: int, **fields: object) -> None:
        accion = self.get(action_id)
        for clave, valor in fields.items():
            setattr(accion, clave, valor)
        self._db.flush()

    def suspend(self, action_id: int, *, at: datetime, by: int, reason: str) -> None:
        accion = self.get(action_id)
        accion.suspended_at = at
        accion.suspended_by = by
        accion.suspension_reason = reason
        self._db.flush()

    def applied(self, action_id: int) -> list[RubroAplicado]:
        filas = (
            self._db.query(PayrollRunItem, PayrollRun)
            .join(PayrollRunLine, PayrollRunLine.id == PayrollRunItem.line_id)
            .join(PayrollRun, PayrollRun.id == PayrollRunLine.run_id)
            .filter(PayrollRunItem.action_id == action_id, PayrollRun.status.in_(APROBADA_O_PAGADA))
            .order_by(PayrollRun.period_to, PayrollRunItem.id)
            .all()
        )
        return [
            RubroAplicado(
                run_id=corrida.id,
                run_status=corrida.status,
                period_from=corrida.period_from,
                period_to=corrida.period_to,
                concept=rubro.concept,
                payer=rubro.payer,
                base=rubro.base,
                rate=rubro.rate,
                amount=rubro.amount,
                quantity=rubro.quantity,
                applied_from=rubro.applied_from,
                applied_to=rubro.applied_to,
            )
            for rubro, corrida in filas
        ]


class SqlAlchemyPayrollRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_run(self, run_id: int) -> PayrollRun | None:
        return self._db.query(PayrollRun).filter(PayrollRun.id == run_id).first()

    def find_run(self, *, schedule_id: int, period_to: date, kind: str) -> PayrollRun | None:
        return (
            self._db.query(PayrollRun)
            .filter(
                PayrollRun.schedule_id == schedule_id,
                PayrollRun.period_to == period_to,
                PayrollRun.kind == kind,
            )
            .first()
        )

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
    ) -> PayrollRun:
        corrida = PayrollRun(
            kind=kind,
            schedule_id=schedule_id,
            period_from=period_from,
            period_to=period_to,
            pay_date=pay_date,
            status="draft",
            created_by=created_by,
            created_at=created_at,
        )
        self._db.add(corrida)
        self._db.flush()
        return corrida

    def lines_of(self, run_id: int) -> list[PayrollRunLine]:
        return (
            self._db.query(PayrollRunLine)
            .filter(PayrollRunLine.run_id == run_id)
            .order_by(PayrollRunLine.employee_id)
            .all()
        )

    def items_of(self, line_id: int) -> list[PayrollRunItem]:
        return (
            self._db.query(PayrollRunItem)
            .filter(PayrollRunItem.line_id == line_id)
            .order_by(PayrollRunItem.id)
            .all()
        )

    def line_count(self, run_id: int) -> int:
        return len(self.lines_of(run_id))

    def replace_lines(self, run_id: int, lines: Sequence[CalculatedLine]) -> None:
        for linea in self.lines_of(run_id):
            for rubro in self.items_of(linea.id):
                self._db.delete(rubro)
            self._db.delete(linea)
        self._db.flush()

        for linea in lines:
            fila = PayrollRunLine(
                run_id=run_id,
                employee_id=linea.employee_id,
                contract_id=linea.contract_id,
                gross=linea.gross.amount,
                employee_deductions=linea.employee_deductions.amount,
                income_tax=linea.income_tax.amount,
                other_deductions=linea.other_deductions.amount,
                net=linea.net.amount,
                employer_charges=linea.employer_charges.amount,
            )
            self._db.add(fila)
            self._db.flush()
            for rubro in linea.items:
                self._db.add(
                    PayrollRunItem(
                        line_id=fila.id,
                        concept=rubro.concept,
                        payer=rubro.payer,
                        base=rubro.base.amount,
                        rate=rubro.rate,
                        amount=rubro.amount.amount,
                        action_id=rubro.action_id,
                        quantity=rubro.quantity,
                        applied_from=rubro.applied_from,
                        applied_to=rubro.applied_to,
                    )
                )
        self._db.flush()

    def totals(self, run_id: int) -> PaidPayroll:
        corrida = self.get_run(run_id)
        lineas = self.lines_of(run_id)
        return PaidPayroll(
            id=corrida.id,
            date=corrida.pay_date,
            gross=Money.sum(Money(l.gross) for l in lineas),
            employer_charges=Money.sum(Money(l.employer_charges) for l in lineas),
            social_security=Money.sum(Money(l.employee_deductions) for l in lineas),
            income_tax=Money.sum(Money(l.income_tax) for l in lineas),
            other_deductions=Money.sum(Money(l.other_deductions) for l in lineas),
            net=Money.sum(Money(l.net) for l in lineas),
        )

    def month_withholding(
        self, employee_id: int, year: int, month: int, *, exclude_run_id: int
    ) -> tuple[Money, Money]:
        desde = date(year, month, 1)
        hasta = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        filas = (
            self._db.query(PayrollRunLine)
            .join(PayrollRun, PayrollRun.id == PayrollRunLine.run_id)
            .filter(
                PayrollRunLine.employee_id == employee_id,
                PayrollRun.id != exclude_run_id,
                PayrollRun.kind == "regular",
                PayrollRun.status.in_(APROBADA_O_PAGADA),
                PayrollRun.period_to >= desde,
                PayrollRun.period_to < hasta,
            )
            .all()
        )
        base = Money.zero()
        retenido = Money.zero()
        for linea in filas:
            base = base + Money.sum(
                Money(i.amount) for i in self.items_of(linea.id) if i.payer == EARNING and i.concept in TAXABLE
            )
            retenido = retenido + Money(linea.income_tax)
        return base, retenido

    def approve(self, run_id: int, *, by: int, at: datetime) -> None:
        corrida = self.get_run(run_id)
        corrida.status = "approved"
        corrida.approved_by = by
        corrida.approved_at = at
        self._db.flush()

    def pay(self, run_id: int, *, by: int, at: datetime, journal_entry_id: int | None) -> None:
        corrida = self.get_run(run_id)
        corrida.status = "paid"
        corrida.paid_by = by
        corrida.paid_at = at
        corrida.journal_entry_id = journal_entry_id
        self._db.flush()


def _rige(fila, on: date) -> bool:
    return fila.valid_from <= on and (fila.valid_to is None or on <= fila.valid_to)


class SqlAlchemyRateTable:
    """Las tablas del país. Sin filtro de compañía porque no son de ninguna."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def rates(self, country: str) -> list[Rate]:
        return [
            Rate(f.concept, f.payer, Decimal(f.value), f.valid_from, f.valid_to)
            for f in self._db.query(PayrollRate).filter(PayrollRate.country == country).all()
        ]

    def brackets_at(self, on: date, country: str) -> list[TaxBracket]:
        """El juego más reciente que rige: todos los tramos de la misma fecha.
        Un decreto nuevo trae el juego entero, no un tramo."""
        filas = [
            f
            for f in self._db.query(IncomeTaxBracket).filter(IncomeTaxBracket.country == country).all()
            if _rige(f, on)
        ]
        if not filas:
            return []
        ultima = max(f.valid_from for f in filas)
        return [
            TaxBracket(
                Money(f.lower_bound),
                None if f.upper_bound is None else Money(f.upper_bound),
                Decimal(f.rate),
            )
            for f in sorted((f for f in filas if f.valid_from == ultima), key=lambda f: f.lower_bound)
        ]

    def credits_at(self, on: date, country: str) -> TaxCredits:
        vigentes: dict[str, IncomeTaxCredit] = {}
        for f in self._db.query(IncomeTaxCredit).filter(IncomeTaxCredit.country == country).all():
            if not _rige(f, on):
                continue
            if f.concept not in vigentes or f.valid_from > vigentes[f.concept].valid_from:
                vigentes[f.concept] = f

        def monto(concepto: str) -> Money:
            fila = vigentes.get(concepto)
            return Money.zero() if fila is None else Money(fila.amount)

        return TaxCredits(child=monto("child"), spouse=monto("spouse"))


class SqlAlchemyPayrollSettings:
    """La sección `payroll` del JSON de configuración: número patronal y si el
    INA está exento (T-1217). Como la de contabilidad, escribe con `flush` y
    confirma quien llama."""

    SECCION = "payroll"

    def __init__(self, db: Session) -> None:
        self._db = db

    def _fila(self) -> Settings:
        fila = self._db.query(Settings).first()
        if fila is None:
            fila = Settings(company_id=compania_actual(), data="{}")
            self._db.add(fila)
            self._db.flush()
        return fila

    def _data(self, fila: Settings) -> dict:
        try:
            datos = json.loads(fila.data or "{}")
        except ValueError:
            datos = {}
        return datos if isinstance(datos, dict) else {}

    def payroll(self) -> dict:
        seccion = self._data(self._fila()).get(self.SECCION)
        return dict(seccion) if isinstance(seccion, dict) else {}

    def save_payroll(self, config: dict) -> None:
        fila = self._fila()
        datos = self._data(fila)
        datos[self.SECCION] = config
        fila.data = json.dumps(datos, ensure_ascii=False)
        self._db.flush()
