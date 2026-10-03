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

from app.application.ports.payroll import CalculatedLine, StoredLine
from app.domain.ledger import PaidPayroll
from app.domain.money import Money
from app.domain.payroll import EARNING, PayItem, Rate, TaxBracket, TaxCredits
from app.domain.payroll_actions import TAXABLE
from app.domain.payroll_benefits import EARNED_CONCEPTS, SeveranceBracket
from app.domain.payroll_calendar import Period
from app.domain.payroll_files import Employer, WorkerAction, WorkerMonth, month_period
from app.models.model_payroll import (
    Employee,
    EmploymentContract,
    IncomeTaxBracket,
    IncomeTaxCredit,
    InsPolicy,
    PayrollOpeningEarning,
    PayrollRate,
    PayrollRun,
    PayrollRunItem,
    PayrollRunLine,
    PersonnelAction,
    Position,
    VacationMovement,
    WorkSchedule,
)
from app.models.model_payroll import SeveranceBracket as FilaDeCesantia
from app.models.model_company import Company
from app.models.model_settings import Settings
from app.utils.tenancy import compania_actual

APROBADA_O_PAGADA = ("approved", "paid")
#: Las corridas que llevan salario: la regular y el ajuste que la corrige. El
#: aguinaldo y la liquidación no son salario del mes.
CON_SALARIO = ("regular", "adjustment")


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

    def _tocan(self, period: Period):
        return self._db.query(EmploymentContract).filter(
            EmploymentContract.valid_from <= period.ends_on,
            (EmploymentContract.valid_to.is_(None)) | (EmploymentContract.valid_to >= period.starts_on),
        )

    def contracts_in(self, schedule_id: int, period: Period) -> list[EmploymentContract]:
        return (
            self._tocan(period)
            .filter(EmploymentContract.schedule_id == schedule_id)
            .order_by(EmploymentContract.employee_id, EmploymentContract.valid_from)
            .all()
        )

    def contracts_between(self, period: Period) -> list[EmploymentContract]:
        return self._tocan(period).order_by(EmploymentContract.employee_id, EmploymentContract.valid_from).all()

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

    def find_run(self, *, schedule_id: int | None, period_to: date, kind: str) -> PayrollRun | None:
        consulta = self._db.query(PayrollRun).filter(PayrollRun.period_to == period_to, PayrollRun.kind == kind)
        if schedule_id is None:
            consulta = consulta.filter(PayrollRun.schedule_id.is_(None))
        else:
            consulta = consulta.filter(PayrollRun.schedule_id == schedule_id)
        return consulta.first()

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
    ) -> PayrollRun:
        corrida = PayrollRun(
            kind=kind,
            schedule_id=schedule_id,
            period_from=period_from,
            period_to=period_to,
            pay_date=pay_date,
            status="draft",
            adjusts_run_id=adjusts_run_id,
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

    @staticmethod
    def _rubro(i: PayrollRunItem) -> PayItem:
        return PayItem(
            i.concept,
            i.payer,
            Money(i.base),
            None if i.rate is None else Decimal(i.rate),
            Money(i.amount),
            action_id=i.action_id,
            quantity=None if i.quantity is None else Decimal(i.quantity),
            applied_from=i.applied_from,
            applied_to=i.applied_to,
        )

    def lines(self, run_id: int) -> list[StoredLine]:
        return [
            StoredLine(
                id=l.id,
                employee_id=l.employee_id,
                contract_id=l.contract_id,
                gross=Money(l.gross),
                employee_deductions=Money(l.employee_deductions),
                income_tax=Money(l.income_tax),
                other_deductions=Money(l.other_deductions),
                net=Money(l.net),
                employer_charges=Money(l.employer_charges),
                items=tuple(self._rubro(i) for i in self.items_of(l.id)),
            )
            for l in self.lines_of(run_id)
        ]

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

    def paid_earnings(self, employee_id: int, period: Period) -> list[tuple[date, Money]]:
        filas = (
            self._db.query(PayrollRunLine, PayrollRun)
            .join(PayrollRun, PayrollRun.id == PayrollRunLine.run_id)
            .filter(
                PayrollRunLine.employee_id == employee_id,
                PayrollRun.kind.in_(CON_SALARIO),
                PayrollRun.status == "paid",
                PayrollRun.period_to >= period.starts_on,
                PayrollRun.period_to <= period.ends_on,
            )
            .order_by(PayrollRun.period_to, PayrollRun.id)
            .all()
        )
        return [
            (
                corrida.period_to,
                Money.sum(
                    Money(i.amount) for i in self.items_of(linea.id) if i.payer == EARNING and i.concept in EARNED_CONCEPTS
                ),
            )
            for linea, corrida in filas
        ]

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
                PayrollRun.kind.in_(CON_SALARIO),
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

    def severance_at(self, on: date, country: str) -> list[SeveranceBracket]:
        """La tabla más reciente que rige: todas las filas de la misma vigencia."""
        filas = [
            f
            for f in self._db.query(FilaDeCesantia).filter(FilaDeCesantia.country == country).all()
            if f.valid_from <= on
        ]
        if not filas:
            return []
        ultima = max(f.valid_from for f in filas)
        return [
            SeveranceBracket(
                Decimal(f.years_from),
                None if f.years_to is None else Decimal(f.years_to),
                Decimal(f.days),
            )
            for f in sorted((f for f in filas if f.valid_from == ultima), key=lambda f: f.years_from)
        ]


class SqlAlchemyVacationRepository:
    """Los movimientos de vacaciones (RN-70). El saldo lo suma el dominio."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def movements(self, employee_id: int) -> list[VacationMovement]:
        return (
            self._db.query(VacationMovement)
            .filter(VacationMovement.employee_id == employee_id)
            .order_by(VacationMovement.on_date, VacationMovement.id)
            .all()
        )

    def add(
        self,
        employee_id: int,
        *,
        kind: str,
        days: Decimal,
        on_date: date,
        run_id: int | None = None,
        action_id: int | None = None,
    ) -> int:
        fila = VacationMovement(
            employee_id=employee_id, kind=kind, days=days, on_date=on_date, run_id=run_id, action_id=action_id
        )
        self._db.add(fila)
        self._db.flush()
        return fila.id

    def update_for_action(self, action_id: int, *, days: Decimal, on_date: date) -> None:
        fila = self._db.query(VacationMovement).filter(VacationMovement.action_id == action_id).first()
        fila.days = days
        fila.on_date = on_date
        self._db.flush()


class SqlAlchemyImportRepository:
    """Lo que la importación busca por nombre y da de alta (RN-97, T-1220)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def position_by_name(self, name: str) -> tuple[int, bool] | None:
        puesto = self._db.query(Position).filter(Position.name == name).first()
        return None if puesto is None else (puesto.id, bool(puesto.is_active))

    def add_position(self, *, name: str, ccss_code: str, ins_code: str) -> int:
        puesto = Position(name=name, ccss_code=ccss_code, ins_code=ins_code, is_active=True)
        self._db.add(puesto)
        self._db.flush()
        return puesto.id

    def schedule_by_name(self, name: str) -> WorkSchedule | None:
        return self._db.query(WorkSchedule).filter(WorkSchedule.name == name).first()

    def policy_by_number(self, number: str) -> int | None:
        poliza = self._db.query(InsPolicy).filter(InsPolicy.number == number).first()
        return None if poliza is None else poliza.id

    def employee_by_identification(self, identification: str) -> int | None:
        empleado = self._db.query(Employee).filter(Employee.identification == identification).first()
        return None if empleado is None else empleado.id

    def add_employee(self, **fields: object) -> int:
        empleado = Employee(**fields, is_active=True)
        self._db.add(empleado)
        self._db.flush()
        return empleado.id


class SqlAlchemyOpeningRepository:
    """Lo devengado antes de VentaSys, mes a mes (RN-97)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def earnings(self, employee_id: int, period: Period) -> list[tuple[date, Money]]:
        filas = (
            self._db.query(PayrollOpeningEarning)
            .filter(
                PayrollOpeningEarning.employee_id == employee_id,
                PayrollOpeningEarning.period_month >= period.starts_on,
                PayrollOpeningEarning.period_month <= period.ends_on,
            )
            .order_by(PayrollOpeningEarning.period_month)
            .all()
        )
        return [(f.period_month, Money(f.gross)) for f in filas]

    def add_earning(self, employee_id: int, *, month: date, gross: Money, by: int, at: datetime) -> None:
        self._db.add(
            PayrollOpeningEarning(
                employee_id=employee_id, period_month=month, gross=gross.amount, imported_by=by, imported_at=at
            )
        )
        self._db.flush()


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


class SqlAlchemyPayrollReports:
    """Lo que un mes pagado sabe de cada trabajador (RN-96, T-1211, T-1219).

    Un modelo de lectura: junta las líneas de las corridas pagadas del mes con
    la ficha, el último contrato de esas líneas y las acciones del mes, en la
    forma que formatea `domain/payroll_files.py`.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._runs = SqlAlchemyPayrollRepository(db)

    def policy_number(self, policy_id: int) -> str | None:
        poliza = self._db.query(InsPolicy).filter(InsPolicy.id == policy_id).first()
        return None if poliza is None else poliza.number

    def employer(self) -> Employer:
        from app.domain.hacienda import identification_type_for

        company = self._db.get(Company, compania_actual())
        identificacion = (company.identificacion or "").strip() if company else ""
        tipo = (company.identification_type if company else None) or (
            identification_type_for(identificacion) if identificacion else None
        )
        fila = self._db.query(Settings).first()
        try:
            datos = json.loads(fila.data or "{}") if fila is not None else {}
        except ValueError:
            datos = {}
        datos = datos if isinstance(datos, dict) else {}
        negocio = datos.get("business") or datos.get("negocio") or {}
        negocio = negocio if isinstance(negocio, dict) else {}
        planilla = datos.get("payroll") if isinstance(datos.get("payroll"), dict) else {}

        def dato(*claves: str) -> str | None:
            for clave in claves:
                valor = negocio.get(clave)
                if isinstance(valor, str) and valor.strip():
                    return valor.strip()
            return None

        return Employer(
            identification_type=tipo,
            identification=identificacion or None,
            employer_number=planilla.get("employer_number") or None,
            phone=dato("phone", "telefono"),
            email=dato("email", "correo"),
            address=dato("address", "direccion"),
        )

    def month(self, year: int, month: int) -> list[WorkerMonth]:
        periodo = month_period(year, month)
        corridas = (
            self._db.query(PayrollRun)
            .filter(
                PayrollRun.kind.in_(CON_SALARIO),
                PayrollRun.status == "paid",
                PayrollRun.period_to >= periodo.starts_on,
                PayrollRun.period_to <= periodo.ends_on,
            )
            .order_by(PayrollRun.period_to, PayrollRun.id)
            .all()
        )
        rubros: dict[int, list[PayItem]] = {}
        contrato_de: dict[int, int] = {}
        for corrida in corridas:
            for linea in self._runs.lines_of(corrida.id):
                rubros.setdefault(linea.employee_id, []).extend(self._runs._rubro(i) for i in self._runs.items_of(linea.id))
                contrato_de[linea.employee_id] = linea.contract_id
        if not rubros:
            return []

        por_omision = self._db.query(InsPolicy).filter(InsPolicy.is_default.is_(True)).first()
        salida: list[WorkerMonth] = []
        for empleado in self._db.query(Employee).filter(Employee.id.in_(list(rubros))).all():
            contrato = self._db.query(EmploymentContract).filter(EmploymentContract.id == contrato_de[empleado.id]).first()
            puesto = self._db.query(Position).filter(Position.id == contrato.position_id).first()
            jornada = self._db.query(WorkSchedule).filter(WorkSchedule.id == contrato.schedule_id).first()
            poliza = (
                self._db.query(InsPolicy).filter(InsPolicy.id == contrato.ins_policy_id).first()
                if contrato.ins_policy_id is not None
                else por_omision
            )
            acciones = []
            for a in (
                self._db.query(PersonnelAction)
                .filter(
                    PersonnelAction.employee_id == empleado.id,
                    PersonnelAction.cancels_action_id.is_(None),
                    PersonnelAction.starts_on >= periodo.starts_on,
                    PersonnelAction.starts_on <= periodo.ends_on,
                )
                .order_by(PersonnelAction.starts_on, PersonnelAction.id)
                .all()
            ):
                nuevo = None
                if a.position_id is not None:
                    cambio = self._db.query(Position).filter(Position.id == a.position_id).first()
                    nuevo = cambio.ccss_code if cambio is not None else None
                acciones.append(WorkerAction(a.kind, a.starts_on, a.ends_on, nuevo))
            salida.append(
                WorkerMonth(
                    employee_id=empleado.id,
                    identification_type=empleado.identification_type,
                    identification=empleado.identification,
                    insured_number=empleado.insured_number,
                    first_name=empleado.first_name,
                    last_name_1=empleado.last_name_1,
                    last_name_2=empleado.last_name_2,
                    hired_on=empleado.hired_on,
                    terminated_on=empleado.terminated_on,
                    termination_cause=empleado.termination_cause,
                    ccss_code=puesto.ccss_code if puesto is not None else None,
                    ins_code=puesto.ins_code if puesto is not None else None,
                    policy_id=poliza.id if poliza is not None else None,
                    policy_number=poliza.number if poliza is not None else None,
                    shift=jornada.shift if jornada is not None else "day",
                    hours_per_day=Decimal(jornada.hours_per_day) if jornada is not None else Decimal(8),
                    items=tuple(rubros[empleado.id]),
                    actions=tuple(acciones),
                )
            )
        return sorted(salida, key=lambda w: (w.last_name_1, w.first_name, w.employee_id))
