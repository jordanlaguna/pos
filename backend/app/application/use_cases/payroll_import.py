"""Importar la planilla de quien viene de otro sistema (RN-97, RF-86, T-1220).

Una sola puerta con ensayo: las filas llegan ya leídas del Excel por el POS, se
revisan **todas** con las mismas reglas del dominio que usa el formulario
—`check_position`, `check_employee`, `check_contract`, `check_action`— y la
respuesta dice fila por fila qué le pasa a cada una. Con `dry_run` eso es todo:
la vista previa de la pantalla es esta respuesta, y la validación vive en un
solo lugar. Sin `dry_run`, o entra todo en una transacción o no entra nada: una
fila con error tumba la escritura entera, porque media planilla importada es
peor que ninguna.

Lo que entra:

- **Puestos**, con sus dos códigos. Uno que ya existe con ese nombre se reutiliza.
- **Empleados** con su contrato —jornada, puesto y póliza por nombre— y, si
  traen, sus días de vacaciones a la fecha de corte de la importación.
- **Devengado** por mes, para el aguinaldo y el promedio de la liquidación.
- **Deducciones** recurrentes con lo que les queda: entran como acciones con
  origen `import` y el saldo como lo pactado, que es lo que falta por cobrar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.ports.clock import Clock
from app.application.ports.payroll import (
    ActionRepository,
    EmployeeRepository,
    ImportRepository,
    OpeningRepository,
    VacationRepository,
)
from app.application.ports.repositories import UnitOfWork
from app.domain.errors import (
    DomainError,
    InvalidAction,
    InvalidContract,
    InvalidEmployee,
    InvalidPayrollSettings,
)
from app.domain.money import Money
from app.domain.payroll_actions import CHILD_SUPPORT, DEDUCTION, GARNISHMENT, Action, check_action
from app.domain.payroll_benefits import VACATION_OPENING, month_of
from app.domain.payroll_staff import ContractData, EmployeeData, check_contract, check_employee, check_position

IMPORTED = "import"
DEDUCTION_KINDS = frozenset({DEDUCTION, CHILD_SUPPORT, GARNISHMENT})

POSITIONS = "positions"
EMPLOYEES = "employees"
EARNINGS = "earnings"
DEDUCTIONS = "deductions"


# ------------------------------------------------------------------ las filas


@dataclass(frozen=True)
class PositionRow:
    row: int
    name: str
    ccss_code: str
    ins_code: str


@dataclass(frozen=True)
class EmployeeRow:
    row: int
    identification_type: str
    identification: str
    first_name: str
    last_name_1: str
    birth_date: date
    gender: str
    marital_status: str
    nationality: str
    hired_on: date
    schedule: str
    position: str
    period_salary: Money
    last_name_2: str | None = None
    insured_number: str | None = None
    email: str | None = None
    phone: str | None = None
    iban: str | None = None
    is_pensioner: bool = False
    dependent_children: int = 0
    spouse_credit: bool = False
    policy: str | None = None
    solidarista_rate: Decimal | None = None
    #: Desde cuándo rige el contrato; sin dato, desde el ingreso.
    contract_from: date | None = None
    #: Los días hábiles de vacaciones que trae a la fecha de la importación.
    vacation_days: Decimal | None = None


@dataclass(frozen=True)
class EarningRow:
    row: int
    identification: str
    #: Cualquier día del mes; se guarda el primero.
    month: date
    gross: Money


@dataclass(frozen=True)
class DeductionRow:
    row: int
    identification: str
    kind: str
    amount: Money
    starts_on: date
    #: Lo que le queda por cobrar (RN-92). Nulo: sin tope.
    balance: Money | None = None
    ends_on: date | None = None
    is_recurring: bool = True
    memo: str | None = None


@dataclass(frozen=True)
class ImportRequest:
    #: La fecha a la que están los saldos de apertura.
    as_of: date
    positions: tuple[PositionRow, ...] = ()
    employees: tuple[EmployeeRow, ...] = ()
    earnings: tuple[EarningRow, ...] = ()
    deductions: tuple[DeductionRow, ...] = ()


@dataclass(frozen=True)
class RowError:
    """Qué le pasa a una fila: el mismo código y los mismos datos que daría el
    formulario, para que la pantalla arme la misma frase."""

    sheet: str
    row: int
    code: str
    field: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ImportResult:
    dry_run: bool
    errors: tuple[RowError, ...]
    positions: int
    employees: int
    earnings: int
    deductions: int

    @property
    def ok(self) -> bool:
        return not self.errors


class ImportHasErrors(DomainError):
    """Se pidió escribir con filas malas: no se escribió nada (RN-97)."""

    def __init__(self, errors: tuple[RowError, ...]) -> None:
        super().__init__(f"{len(errors)} filas con error")
        self.errors = errors


# -------------------------------------------------------------- el caso de uso


class ImportPayroll:
    def __init__(
        self,
        *,
        catalog: ImportRepository,
        employees: EmployeeRepository,
        actions: ActionRepository,
        vacations: VacationRepository,
        opening: OpeningRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._catalog = catalog
        self._employees = employees
        self._actions = actions
        self._vacations = vacations
        self._opening = opening
        self._uow = uow
        self._clock = clock

    def __call__(self, request: ImportRequest, *, dry_run: bool, user_id: int) -> ImportResult:
        errores = self._validate(request)
        nuevos_puestos = sum(1 for p in request.positions if self._catalog.position_by_name(p.name.strip()) is None)
        resultado = ImportResult(
            dry_run=dry_run,
            errors=tuple(errores),
            positions=nuevos_puestos,
            employees=len(request.employees),
            earnings=len(request.earnings),
            deductions=len(request.deductions),
        )
        if dry_run:
            return resultado
        if errores:
            raise ImportHasErrors(tuple(errores))
        with self._uow:
            self._write(request, user_id)
            self._uow.commit()
        return resultado

    # ------------------------------------------------------------ revisar

    def _validate(self, request: ImportRequest) -> list[RowError]:
        errores: list[RowError] = []
        puestos_del_archivo: dict[str, PositionRow] = {}
        for fila in request.positions:
            nombre = fila.name.strip()
            try:
                check_position(nombre, fila.ccss_code.strip(), fila.ins_code.strip())
            except InvalidPayrollSettings as e:
                errores.append(RowError(POSITIONS, fila.row, "invalid_payroll_settings", e.field, e.reason))
                continue
            if nombre in puestos_del_archivo:
                errores.append(RowError(POSITIONS, fila.row, "payroll_name_taken", "name", "duplicate"))
                continue
            puestos_del_archivo[nombre] = fila

        cedulas: dict[str, EmployeeRow] = {}
        for fila in request.employees:
            cedula = fila.identification.strip()
            try:
                check_employee(
                    EmployeeData(
                        identification_type=fila.identification_type,
                        identification=cedula,
                        first_name=fila.first_name,
                        last_name_1=fila.last_name_1,
                        birth_date=fila.birth_date,
                        gender=fila.gender,
                        marital_status=fila.marital_status,
                        nationality=fila.nationality,
                        hired_on=fila.hired_on,
                        last_name_2=fila.last_name_2,
                        email=fila.email,
                        iban=fila.iban,
                        dependent_children=fila.dependent_children,
                    )
                )
            except InvalidEmployee as e:
                errores.append(RowError(EMPLOYEES, fila.row, "invalid_employee", e.field, e.reason))
                continue
            if cedula in cedulas or self._catalog.employee_by_identification(cedula) is not None:
                errores.append(RowError(EMPLOYEES, fila.row, "employee_identification_taken", "identification", "duplicate"))
                continue
            if fila.vacation_days is not None and fila.vacation_days < 0:
                errores.append(RowError(EMPLOYEES, fila.row, "invalid_employee", "vacation_days", "negative"))
                continue
            jornada = self._catalog.schedule_by_name(fila.schedule.strip())
            if jornada is None:
                errores.append(RowError(EMPLOYEES, fila.row, "schedule_not_found", "schedule"))
                continue
            puesto = self._catalog.position_by_name(fila.position.strip())
            activo = puesto[1] if puesto is not None else fila.position.strip() in puestos_del_archivo
            if puesto is None and fila.position.strip() not in puestos_del_archivo:
                errores.append(RowError(EMPLOYEES, fila.row, "position_not_found", "position"))
                continue
            if fila.policy and self._catalog.policy_by_number(fila.policy.strip()) is None:
                errores.append(RowError(EMPLOYEES, fila.row, "policy_not_found", "policy"))
                continue
            try:
                check_contract(
                    ContractData(fila.contract_from or fila.hired_on, fila.period_salary, fila.solidarista_rate),
                    hired_on=fila.hired_on,
                    previous_from=None,
                    schedule_active=bool(jornada.is_active),
                    position_active=activo,
                )
            except InvalidContract as e:
                errores.append(RowError(EMPLOYEES, fila.row, "invalid_contract", e.field, e.reason))
                continue
            cedulas[cedula] = fila

        def conocida(cedula: str) -> bool:
            return cedula in cedulas or self._catalog.employee_by_identification(cedula) is not None

        meses: set[tuple[str, date]] = set()
        for fila in request.earnings:
            cedula = fila.identification.strip()
            if not conocida(cedula):
                errores.append(RowError(EARNINGS, fila.row, "employee_not_found", "identification"))
                continue
            if fila.gross.is_negative:
                errores.append(RowError(EARNINGS, fila.row, "invalid_employee", "gross", "negative"))
                continue
            clave = (cedula, month_of(fila.month))
            if clave in meses:
                errores.append(RowError(EARNINGS, fila.row, "invalid_employee", "month", "duplicate"))
                continue
            meses.add(clave)

        for fila in request.deductions:
            cedula = fila.identification.strip()
            if not conocida(cedula):
                errores.append(RowError(DEDUCTIONS, fila.row, "employee_not_found", "identification"))
                continue
            if fila.kind not in DEDUCTION_KINDS:
                errores.append(RowError(DEDUCTIONS, fila.row, "invalid_action", "kind", "unknown"))
                continue
            try:
                check_action(self._action(fila))
            except InvalidAction as e:
                errores.append(RowError(DEDUCTIONS, fila.row, "invalid_action", e.field, e.reason))
        return errores

    @staticmethod
    def _action(fila: DeductionRow) -> Action:
        # El embargo no es recurrente por elección (RN-92): se aplica hasta agotar
        # su saldo. Una deducción o una pensión sí lo son, si lo dicen.
        return Action(
            kind=fila.kind,
            starts_on=fila.starts_on,
            ends_on=fila.ends_on,
            amount=fila.amount,
            total_amount=fila.balance,
            is_recurring=fila.is_recurring and fila.kind != GARNISHMENT,
        )

    # ----------------------------------------------------------- escribir

    def _write(self, request: ImportRequest, user_id: int) -> None:
        ahora = self._clock.now()
        for fila in request.positions:
            if self._catalog.position_by_name(fila.name.strip()) is None:
                self._catalog.add_position(
                    name=fila.name.strip(), ccss_code=fila.ccss_code.strip(), ins_code=fila.ins_code.strip()
                )

        ids: dict[str, int] = {}
        for fila in request.employees:
            cedula = fila.identification.strip()
            jornada = self._catalog.schedule_by_name(fila.schedule.strip())
            puesto = self._catalog.position_by_name(fila.position.strip())
            assert jornada is not None and puesto is not None
            poliza = self._catalog.policy_by_number(fila.policy.strip()) if fila.policy else None
            empleado = self._catalog.add_employee(
                identification_type=fila.identification_type,
                identification=cedula,
                first_name=fila.first_name.strip(),
                last_name_1=fila.last_name_1.strip(),
                last_name_2=fila.last_name_2.strip() if fila.last_name_2 else None,
                insured_number=fila.insured_number,
                birth_date=fila.birth_date,
                gender=fila.gender,
                marital_status=fila.marital_status,
                nationality=fila.nationality,
                phone=fila.phone,
                email=fila.email,
                is_pensioner=fila.is_pensioner,
                iban=fila.iban,
                hired_on=fila.hired_on,
                dependent_children=fila.dependent_children,
                spouse_credit=fila.spouse_credit,
            )
            ids[cedula] = empleado
            self._employees.add_contract(
                employee_id=empleado,
                schedule_id=jornada.id,
                position_id=puesto[0],
                ins_policy_id=poliza,
                valid_from=fila.contract_from or fila.hired_on,
                period_salary=fila.period_salary,
                solidarista_rate=fila.solidarista_rate,
            )
            if fila.vacation_days:
                self._vacations.add(empleado, kind=VACATION_OPENING, days=fila.vacation_days, on_date=request.as_of)

        def id_de(cedula: str) -> int:
            if cedula in ids:
                return ids[cedula]
            existente = self._catalog.employee_by_identification(cedula)
            assert existente is not None
            return existente

        for fila in request.earnings:
            self._opening.add_earning(
                id_de(fila.identification.strip()), month=month_of(fila.month), gross=fila.gross, by=user_id, at=ahora
            )
        for fila in request.deductions:
            accion = self._action(fila)
            self._actions.add(
                employee_id=id_de(fila.identification.strip()),
                kind=fila.kind,
                starts_on=fila.starts_on,
                ends_on=fila.ends_on,
                hours=None,
                days=None,
                amount=fila.amount.amount,
                total_amount=None if fila.balance is None else fila.balance.amount,
                new_salary=None,
                position_id=None,
                is_recurring=accion.is_recurring,
                memo=fila.memo,
                source=IMPORTED,
                created_by=user_id,
                created_at=ahora,
            )
