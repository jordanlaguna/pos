"""Planilla — adaptador HTTP (F12, T-1205, T-1206, T-1217, T-1218).

Dos clases de cosas conviven acá, y a propósito en el mismo módulo:

* **El ABM** de la configuración, las jornadas, los puestos, las pólizas, los
  empleados y los contratos, escrito directo sobre SQLAlchemy con las reglas
  del dominio (`check_schedule`, `check_employee`, `check_contract`…). Es lo
  mismo que hace `crud_office` con las sucursales: un ABM no gana nada con un
  caso de uso.
* **El cableado** de los casos de uso de acciones y corridas, que sí tienen
  reglas: se les arman los adaptadores y se traducen sus «no» a código y datos
  (RN-30). La traducción está en un solo sitio, `traduciendo()`, para que las
  nueve rutas digan lo mismo del mismo error.

Lo que sale son diccionarios con la plata ya en `float`: la frontera es acá.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy.orm import Session

from app.application.use_cases.payroll import (
    ActionAlreadyCancelled,
    ActionAlreadySuspended,
    ActionNotEditable,
    ActionNotFound,
    ActionNotRecurring,
    ActionRequest,
    AdjustRun,
    ApproveRun,
    CalculateRun,
    CancelAction,
    ContractMissing,
    CreateAguinaldoRun,
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
    RunNotPaid,
    ScheduleNotFound,
    SettlementRequiresTermination,
    SuspendAction,
    TerminateEmployee,
    UpdateAction,
    VacationBalanceExceeded,
)
from app.application.use_cases.payroll_exports import (
    ExportCcssReport,
    ExportInsFile,
    IncomeTaxSummary,
    PolicyNotFound,
)
from app.application.use_cases.payroll_import import (
    DeductionRow,
    EarningRow,
    EmployeeRow,
    ImportHasErrors,
    ImportPayroll,
    ImportRequest,
    PositionRow,
)
from app.domain.errors import (
    ExportDataIncomplete,
    InvalidAction,
    InvalidContract,
    InvalidCutDate,
    InvalidEmployee,
    InvalidPayrollSettings,
    InvalidSchedule,
    RatesMissing,
)
from app.domain.money import Money
from app.domain.payroll_benefits import vacation_balance
from app.domain.payroll_calendar import SHIFT_HOURS, Schedule, check_schedule
from app.domain.payroll_staff import (
    ContractData,
    EmployeeData,
    check_contract,
    check_employee,
    check_policy,
    check_position,
    clean_employer_number,
)
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_payroll import (
    SqlAlchemyActionRepository,
    SqlAlchemyEmployeeRepository,
    SqlAlchemyImportRepository,
    SqlAlchemyOpeningRepository,
    SqlAlchemyPayrollReports,
    SqlAlchemyPayrollRepository,
    SqlAlchemyPayrollSettings,
    SqlAlchemyRateTable,
    SqlAlchemyScheduleRepository,
    SqlAlchemyVacationRepository,
)
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyUnitOfWork
from app.models.model_payroll import (
    Employee,
    EmploymentContract,
    InsPolicy,
    PayrollRun,
    Position,
    WorkSchedule,
)
from app.models.model_user import User
from app.services import crud_accounting, crud_membership
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion

UN_DIA = timedelta(days=1)


def _float(valor) -> float | None:
    if valor is None:
        return None
    return float(valor.amount if isinstance(valor, Money) else valor)


@contextmanager
def traduciendo() -> Iterator[None]:
    """Los «no» del dominio y de la aplicación, en código y datos (RN-30).

    Un solo sitio para que las rutas de acciones y corridas digan lo mismo del
    mismo error, y para que agregar un «no» nuevo sea una línea y no nueve.
    """
    try:
        yield
    except EmployeeNotFound as e:
        raise api_error(404, "employee_not_found", employee_id=e.employee_id) from None
    except EmployeeTerminated as e:
        raise api_error(
            409, "employee_terminated", employee_id=e.employee_id, terminated_on=e.terminated_on.isoformat()
        ) from None
    except ContractMissing as e:
        raise api_error(409, "contract_missing", employee_id=e.employee_id) from None
    except ScheduleNotFound as e:
        raise api_error(404, "schedule_not_found", schedule_id=e.schedule_id) from None
    except PositionNotFound as e:
        raise api_error(404, "position_not_found", position_id=e.position_id) from None
    except PolicyNotFound as e:
        raise api_error(404, "policy_not_found", policy_id=e.policy_id) from None
    except ExportDataIncomplete as e:
        raise api_error(
            409,
            "export_data_incomplete",
            missing=[{"employee_id": empleado, "fields": list(campos)} for empleado, campos in e.missing],
            company=list(e.company),
        ) from None
    except ActionNotFound as e:
        raise api_error(404, "action_not_found", action_id=e.action_id) from None
    except ActionNotEditable as e:
        raise api_error(409, "action_not_editable", action_id=e.action_id, reason=e.reason) from None
    except ActionAlreadyCancelled as e:
        raise api_error(409, "action_already_cancelled", action_id=e.action_id) from None
    except ActionNotRecurring as e:
        raise api_error(409, "action_not_recurring", action_id=e.action_id) from None
    except ActionAlreadySuspended as e:
        raise api_error(409, "action_already_suspended", action_id=e.action_id) from None
    except RunNotFound as e:
        raise api_error(404, "run_not_found", run_id=e.run_id) from None
    except RunAlreadyExists as e:
        raise api_error(409, "run_already_exists", run_id=e.run_id) from None
    except RunNotEditable as e:
        raise api_error(409, "run_not_editable", run_id=e.run_id, reason=e.reason) from None
    except RunNotCalculated as e:
        raise api_error(409, "run_not_calculated", run_id=e.run_id) from None
    except RunNotApproved as e:
        raise api_error(409, "run_not_approved", run_id=e.run_id, status=e.status) from None
    except RunAlreadyPaid as e:
        raise api_error(409, "run_already_paid", run_id=e.run_id) from None
    except RunNotPaid as e:
        raise api_error(409, "run_not_paid", run_id=e.run_id, status=e.status) from None
    except SettlementRequiresTermination as e:
        raise api_error(
            409, "settlement_requires_termination", run_id=e.run_id, employee_id=e.employee_id
        ) from None
    except VacationBalanceExceeded as e:
        raise api_error(
            409,
            "vacation_balance_exceeded",
            employee_id=e.employee_id,
            balance=_float(e.balance),
            requested=_float(e.requested),
        ) from None
    except RatesMissing as e:
        raise api_error(409, "rates_missing_for_date", missing=list(e.missing), on=e.on.isoformat()) from None
    except InvalidCutDate as e:
        raise api_error(400, "invalid_cut_date", cut=e.cut.isoformat(), frequency=e.frequency) from None
    except InvalidSchedule as e:
        raise api_error(400, "invalid_schedule", field=e.field, reason=e.reason) from None
    except InvalidAction as e:
        raise api_error(400, "invalid_action", field=e.field, reason=e.reason) from None
    except InvalidContract as e:
        raise api_error(400, "invalid_contract", field=e.field, reason=e.reason) from None
    except InvalidEmployee as e:
        raise api_error(400, "invalid_employee", field=e.field, reason=e.reason) from None
    except InvalidPayrollSettings as e:
        raise api_error(400, "invalid_payroll_settings", field=e.field, reason=e.reason) from None


# ------------------------------------------------------------ configuración


def configuracion(db: Session) -> dict:
    seccion = SqlAlchemyPayrollSettings(db).payroll()
    return {
        "employer_number": seccion.get("employer_number"),
        "ina_exempt": bool(seccion.get("ina_exempt")),
    }


def guardar_configuracion(db: Session, *, employer_number: object, ina_exempt: bool) -> dict:
    """`PUT /payroll/settings`. Su propia puerta: `save_settings` no la toca."""
    with traduciendo():
        numero = clean_employer_number(employer_number)
    SqlAlchemyPayrollSettings(db).save_payroll({"employer_number": numero, "ina_exempt": bool(ina_exempt)})
    db.commit()
    return configuracion(db)


# ----------------------------------------------------------------- jornadas

#: Lo que no se cambia con corridas pagadas (RF-83): la periodicidad y los cortes.
CAMPOS_BLOQUEADOS = ("frequency", "first_cut_day", "cut_weekday", "series_start")


def jornadas(db: Session) -> list[WorkSchedule]:
    return db.query(WorkSchedule).order_by(WorkSchedule.name).all()


def _revisar_jornada(db: Session, jornada: WorkSchedule) -> None:
    with traduciendo():
        check_schedule(
            Schedule(
                frequency=jornada.frequency,
                shift=jornada.shift,
                hours_per_day=Decimal(jornada.hours_per_day),
                rest_day_paid=bool(jornada.rest_day_paid),
                workdays_per_week=int(jornada.workdays_per_week),
                first_cut_day=jornada.first_cut_day,
                cut_weekday=jornada.cut_weekday,
                series_start=jornada.series_start,
            )
        )
    ocupado = db.query(WorkSchedule).filter(WorkSchedule.name == jornada.name, WorkSchedule.id != (jornada.id or 0)).first()
    if ocupado is not None:
        raise api_error(409, "payroll_name_taken", resource="schedules", name=jornada.name)


def crear_jornada(db: Session, datos) -> WorkSchedule:
    horas = datos.hours_per_day
    if horas is None:
        horas = SHIFT_HOURS.get(datos.shift, Decimal(8))
    jornada = WorkSchedule(
        name=datos.name.strip(),
        frequency=datos.frequency,
        shift=datos.shift,
        hours_per_day=horas,
        workdays_per_week=datos.workdays_per_week,
        rest_day_paid=datos.rest_day_paid,
        first_cut_day=datos.first_cut_day,
        cut_weekday=datos.cut_weekday,
        series_start=datos.series_start,
        is_active=True,
    )
    _revisar_jornada(db, jornada)
    db.add(jornada)
    db.commit()
    db.refresh(jornada)
    return jornada


def actualizar_jornada(db: Session, schedule_id: int, datos) -> WorkSchedule:
    jornada = db.query(WorkSchedule).filter(WorkSchedule.id == schedule_id).first()
    if jornada is None:
        raise api_error(404, "schedule_not_found", schedule_id=schedule_id)

    cambios = datos.model_dump(exclude_unset=True)
    toca_cortes = any(
        campo in cambios and cambios[campo] != getattr(jornada, campo) for campo in CAMPOS_BLOQUEADOS
    )
    if toca_cortes and SqlAlchemyScheduleRepository(db).has_paid_runs(schedule_id):
        raise api_error(409, "schedule_locked", schedule_id=schedule_id)

    for campo, valor in cambios.items():
        setattr(jornada, campo, valor.strip() if campo == "name" else valor)
    _revisar_jornada(db, jornada)
    db.commit()
    db.refresh(jornada)
    return jornada


# ------------------------------------------------------------------ puestos


def puestos(db: Session) -> list[Position]:
    return db.query(Position).order_by(Position.name).all()


def _revisar_puesto(db: Session, puesto: Position) -> None:
    with traduciendo():
        check_position(puesto.name, puesto.ccss_code, puesto.ins_code)
    ocupado = db.query(Position).filter(Position.name == puesto.name, Position.id != (puesto.id or 0)).first()
    if ocupado is not None:
        raise api_error(409, "payroll_name_taken", resource="positions", name=puesto.name)


def crear_puesto(db: Session, datos) -> Position:
    puesto = Position(
        name=datos.name.strip(), ccss_code=datos.ccss_code.strip(), ins_code=datos.ins_code.strip(), is_active=True
    )
    _revisar_puesto(db, puesto)
    db.add(puesto)
    db.commit()
    db.refresh(puesto)
    return puesto


def actualizar_puesto(db: Session, position_id: int, datos) -> Position:
    puesto = db.query(Position).filter(Position.id == position_id).first()
    if puesto is None:
        raise api_error(404, "position_not_found", position_id=position_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(puesto, campo, valor.strip() if isinstance(valor, str) else valor)
    _revisar_puesto(db, puesto)
    db.commit()
    db.refresh(puesto)
    return puesto


# ------------------------------------------------------------------ pólizas


def polizas(db: Session) -> list[InsPolicy]:
    return db.query(InsPolicy).order_by(InsPolicy.is_default.desc(), InsPolicy.number).all()


def _hacer_por_omision(db: Session, poliza: InsPolicy) -> None:
    for otra in db.query(InsPolicy).filter(InsPolicy.id != (poliza.id or 0)).all():
        otra.is_default = False
    poliza.is_default = True


def crear_poliza(db: Session, datos) -> InsPolicy:
    numero = datos.number.strip()
    with traduciendo():
        check_policy(numero, Decimal(datos.rt_rate))
    if db.query(InsPolicy).filter(InsPolicy.number == numero).first() is not None:
        raise api_error(409, "payroll_name_taken", resource="policies", name=numero)
    poliza = InsPolicy(number=numero, rt_rate=datos.rt_rate, is_default=False)
    # La primera es la de todos los contratos que no digan otra.
    if datos.is_default or db.query(InsPolicy).first() is None:
        _hacer_por_omision(db, poliza)
    db.add(poliza)
    db.commit()
    db.refresh(poliza)
    return poliza


def actualizar_poliza(db: Session, policy_id: int, datos) -> InsPolicy:
    poliza = db.query(InsPolicy).filter(InsPolicy.id == policy_id).first()
    if poliza is None:
        raise api_error(404, "policy_not_found", policy_id=policy_id)
    if datos.rt_rate is not None:
        with traduciendo():
            check_policy(poliza.number, Decimal(datos.rt_rate))
        poliza.rt_rate = datos.rt_rate
    if datos.is_default:
        _hacer_por_omision(db, poliza)
    db.commit()
    db.refresh(poliza)
    return poliza


# ---------------------------------------------------------------- empleados


def _contrato_out(c: EmploymentContract) -> dict:
    return {
        "id": c.id,
        "employee_id": c.employee_id,
        "schedule_id": c.schedule_id,
        "position_id": c.position_id,
        "ins_policy_id": c.ins_policy_id,
        "valid_from": c.valid_from,
        "valid_to": c.valid_to,
        "period_salary": _float(c.period_salary),
        "solidarista_rate": _float(c.solidarista_rate),
    }


def _empleado_out(db: Session, e: Employee) -> dict:
    contratos = SqlAlchemyEmployeeRepository(db).contracts_of(e.id)
    return {
        "id": e.id,
        "user_id": e.user_id,
        "identification_type": e.identification_type,
        "identification": e.identification,
        "first_name": e.first_name,
        "last_name_1": e.last_name_1,
        "last_name_2": e.last_name_2,
        "insured_number": e.insured_number,
        "birth_date": e.birth_date,
        "gender": e.gender,
        "marital_status": e.marital_status,
        "nationality": e.nationality,
        "phone": e.phone,
        "email": e.email,
        "is_pensioner": bool(e.is_pensioner),
        "iban": e.iban,
        "hired_on": e.hired_on,
        "terminated_on": e.terminated_on,
        "termination_cause": e.termination_cause,
        "dependent_children": e.dependent_children,
        "spouse_credit": bool(e.spouse_credit),
        "is_active": bool(e.is_active),
        "contract": _contrato_out(contratos[-1]) if contratos else None,
    }


def _empleado(db: Session, employee_id: int) -> Employee:
    empleado = db.query(Employee).filter(Employee.id == employee_id).first()
    if empleado is None:
        raise api_error(404, "employee_not_found", employee_id=employee_id)
    return empleado


def _revisar_empleado(db: Session, e: Employee) -> None:
    with traduciendo():
        check_employee(
            EmployeeData(
                identification_type=e.identification_type,
                identification=e.identification,
                first_name=e.first_name,
                last_name_1=e.last_name_1,
                birth_date=e.birth_date,
                gender=e.gender,
                marital_status=e.marital_status,
                nationality=e.nationality,
                hired_on=e.hired_on,
                last_name_2=e.last_name_2,
                email=e.email,
                iban=e.iban,
                dependent_children=int(e.dependent_children),
            )
        )
    e.identification = e.identification.strip()
    ocupada = (
        db.query(Employee).filter(Employee.identification == e.identification, Employee.id != (e.id or 0)).first()
    )
    if ocupada is not None:
        raise api_error(409, "employee_identification_taken", identification=e.identification)
    if e.user_id is not None and db.get(User, e.user_id) is None:
        raise api_error(404, "user_not_found")


def empleados(db: Session) -> list[dict]:
    filas = db.query(Employee).order_by(Employee.last_name_1, Employee.first_name, Employee.id).all()
    return [_empleado_out(db, e) for e in filas]


def empleado(db: Session, employee_id: int) -> dict:
    return _empleado_out(db, _empleado(db, employee_id))


def crear_empleado(db: Session, datos) -> dict:
    """El alta, y su contrato si viene (RF-55): los dos o ninguno. El contrato
    rige desde el ingreso; si no pasa, el `commit` no llega y el empleado
    tampoco queda."""
    e = Employee(**datos.model_dump(exclude={"contract"}), is_active=True)
    _revisar_empleado(db, e)
    db.add(e)
    if datos.contract is not None:
        db.flush()
        c = datos.contract
        _contratar(
            db,
            e,
            schedule_id=c.schedule_id,
            position_id=c.position_id,
            ins_policy_id=c.ins_policy_id,
            valid_from=e.hired_on,
            period_salary=c.period_salary,
            solidarista_rate=c.solidarista_rate,
        )
    db.commit()
    db.refresh(e)
    return _empleado_out(db, e)


def actualizar_empleado(db: Session, employee_id: int, datos) -> dict:
    e = _empleado(db, employee_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(e, campo, valor)
    _revisar_empleado(db, e)
    db.commit()
    db.refresh(e)
    return _empleado_out(db, e)


def dar_de_baja(db: Session, employee_id: int, datos, *, user_id: int) -> dict:
    """`POST /payroll/employees/{id}/terminate` (RF-55, RF-61)."""
    caso = TerminateEmployee(
        employees=SqlAlchemyEmployeeRepository(db),
        actions=SqlAlchemyActionRepository(db),
        runs=SqlAlchemyPayrollRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    with traduciendo():
        liquidacion = caso(employee_id, on=datos.terminated_on, cause=datos.cause, user_id=user_id)
    return {"employee": _empleado_out(db, _empleado(db, employee_id)), "settlement_run_id": liquidacion}


# ---------------------------------------------------------------- contratos


def contratos(db: Session, employee_id: int) -> list[dict]:
    _empleado(db, employee_id)
    return [_contrato_out(c) for c in SqlAlchemyEmployeeRepository(db).contracts_of(employee_id)]


def crear_contrato(db: Session, datos) -> dict:
    """`POST /payroll/contracts`: el primero, o uno nuevo que cierra el anterior."""
    e = _empleado(db, datos.employee_id)
    if e.terminated_on is not None:
        raise api_error(
            409, "employee_terminated", employee_id=e.id, terminated_on=e.terminated_on.isoformat()
        )
    nuevo = _contratar(
        db,
        e,
        schedule_id=datos.schedule_id,
        position_id=datos.position_id,
        ins_policy_id=datos.ins_policy_id,
        valid_from=datos.valid_from,
        period_salary=datos.period_salary,
        solidarista_rate=datos.solidarista_rate,
    )
    db.commit()
    return _contrato_out(db.query(EmploymentContract).filter(EmploymentContract.id == nuevo).first())


def _contratar(
    db: Session,
    e: Employee,
    *,
    schedule_id: int,
    position_id: int,
    ins_policy_id: int | None,
    valid_from: date,
    period_salary: Decimal,
    solidarista_rate: Decimal | None,
) -> int:
    """Revisa y agrega el contrato, sin confirmar: lo usan el alta y el
    contrato suelto, y cada uno confirma lo suyo."""
    jornada = db.query(WorkSchedule).filter(WorkSchedule.id == schedule_id).first()
    if jornada is None:
        raise api_error(404, "schedule_not_found", schedule_id=schedule_id)
    puesto = db.query(Position).filter(Position.id == position_id).first()
    if puesto is None:
        raise api_error(404, "position_not_found", position_id=position_id)
    if ins_policy_id is not None:
        if db.query(InsPolicy).filter(InsPolicy.id == ins_policy_id).first() is None:
            raise api_error(404, "policy_not_found", policy_id=ins_policy_id)

    repo = SqlAlchemyEmployeeRepository(db)
    previos = repo.contracts_of(e.id)
    ultimo = previos[-1] if previos else None
    # El nuevo tiene que empezar después del último, abierto o cerrado: con uno
    # cerrado, después de su fin; con uno abierto, después de su inicio, porque
    # este lo cierra el día antes.
    tope = None
    if ultimo is not None:
        tope = ultimo.valid_to if ultimo.valid_to is not None else ultimo.valid_from

    with traduciendo():
        check_contract(
            ContractData(valid_from, Money(period_salary), solidarista_rate),
            hired_on=e.hired_on,
            previous_from=tope,
            schedule_active=bool(jornada.is_active),
            position_active=bool(puesto.is_active),
        )
    if ultimo is not None and ultimo.valid_to is None:
        repo.close_contract(ultimo.id, valid_to=valid_from - UN_DIA)
    return repo.add_contract(
        employee_id=e.id,
        schedule_id=schedule_id,
        position_id=position_id,
        ins_policy_id=ins_policy_id,
        valid_from=valid_from,
        period_salary=Money(period_salary),
        solidarista_rate=solidarista_rate,
    )


# ------------------------------------------------------- acciones de personal


def _money(valor: Decimal | None) -> Money | None:
    return None if valor is None else Money(valor)


def _accion_out(repo: SqlAlchemyActionRepository, a, hermanas) -> dict:
    aplicados = repo.applied(a.id)
    aplicado = Money.sum(Money(i.amount) for i in aplicados)
    return {
        "id": a.id,
        "employee_id": a.employee_id,
        "kind": a.kind,
        "starts_on": a.starts_on,
        "ends_on": a.ends_on,
        "hours": _float(a.hours),
        "days": _float(a.days),
        "amount": _float(a.amount),
        "total_amount": _float(a.total_amount),
        "new_salary": _float(a.new_salary),
        "position_id": a.position_id,
        "is_recurring": bool(a.is_recurring),
        "memo": a.memo,
        "cancels_action_id": a.cancels_action_id,
        "cancelled_by": next((h.id for h in hermanas if h.cancels_action_id == a.id), None),
        "suspended_at": a.suspended_at,
        "suspended_by": a.suspended_by,
        "suspension_reason": a.suspension_reason,
        "source": a.source,
        "created_by": a.created_by,
        "created_at": a.created_at,
        "applied": [
            {
                "run_id": i.run_id,
                "run_status": i.run_status,
                "period_from": i.period_from,
                "period_to": i.period_to,
                "concept": i.concept,
                "payer": i.payer,
                "amount": _float(i.amount),
                "quantity": _float(i.quantity),
                "applied_from": i.applied_from,
                "applied_to": i.applied_to,
            }
            for i in aplicados
        ],
        "applied_total": _float(aplicado),
        "balance": None if a.total_amount is None else _float(Money(a.total_amount) - aplicado),
    }


def _una_accion(db: Session, action_id: int) -> dict:
    repo = SqlAlchemyActionRepository(db)
    a = repo.get(action_id)
    if a is None:
        raise api_error(404, "action_not_found", action_id=action_id)
    return _accion_out(repo, a, repo.for_employee(a.employee_id))


def historial(db: Session, employee_id: int) -> list[dict]:
    """`GET /payroll/employees/{id}/actions`: cada acción con lo que aplicó cada
    corrida y su saldo (RF-82)."""
    _empleado(db, employee_id)
    repo = SqlAlchemyActionRepository(db)
    acciones = repo.for_employee(employee_id)
    return [_accion_out(repo, a, acciones) for a in acciones]


def _pedido(datos, *, employee_id: int, kind: str) -> ActionRequest:
    return ActionRequest(
        employee_id=employee_id,
        kind=kind,
        starts_on=datos.starts_on,
        ends_on=datos.ends_on,
        hours=datos.hours,
        days=datos.days,
        amount=_money(datos.amount),
        total_amount=_money(datos.total_amount),
        new_salary=_money(getattr(datos, "new_salary", None)),
        position_id=getattr(datos, "position_id", None),
        is_recurring=bool(datos.is_recurring),
        memo=datos.memo,
    )


def registrar_accion(db: Session, datos, *, user_id: int) -> dict:
    caso = RegisterAction(
        employees=SqlAlchemyEmployeeRepository(db),
        actions=SqlAlchemyActionRepository(db),
        vacations=SqlAlchemyVacationRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    with traduciendo():
        nueva = caso(_pedido(datos, employee_id=datos.employee_id, kind=datos.kind), user_id=user_id)
    return _una_accion(db, nueva)


def editar_accion(db: Session, action_id: int, datos) -> dict:
    caso = UpdateAction(
        actions=SqlAlchemyActionRepository(db), vacations=SqlAlchemyVacationRepository(db), uow=SqlAlchemyUnitOfWork(db)
    )
    with traduciendo():
        caso(action_id, _pedido(datos, employee_id=0, kind=""))
    return _una_accion(db, action_id)


def anular_accion(db: Session, action_id: int, *, user_id: int, memo: str | None) -> dict:
    caso = CancelAction(
        actions=SqlAlchemyActionRepository(db),
        vacations=SqlAlchemyVacationRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    with traduciendo():
        nueva = caso(action_id, user_id=user_id, memo=memo)
    return _una_accion(db, nueva)


def suspender_accion(db: Session, action_id: int, *, user_id: int, reason: str) -> dict:
    caso = SuspendAction(actions=SqlAlchemyActionRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock())
    with traduciendo():
        caso(action_id, user_id=user_id, reason=reason)
    return _una_accion(db, action_id)


# ----------------------------------------------------------------- corridas


def _nombre(e: Employee | None) -> str:
    if e is None:
        return ""
    return " ".join(p for p in (e.first_name, e.last_name_1, e.last_name_2) if p)


def _corrida_out(db: Session, corrida: PayrollRun, *, con_lineas: bool) -> dict:
    repo = SqlAlchemyPayrollRepository(db)
    lineas = repo.lines_of(corrida.id)
    jornada = (
        db.query(WorkSchedule).filter(WorkSchedule.id == corrida.schedule_id).first()
        if corrida.schedule_id is not None
        else None
    )
    salida = {
        "id": corrida.id,
        "kind": corrida.kind,
        "schedule_id": corrida.schedule_id,
        "schedule_name": jornada.name if jornada is not None else None,
        "period_from": corrida.period_from,
        "period_to": corrida.period_to,
        "pay_date": corrida.pay_date,
        "status": corrida.status,
        "adjusts_run_id": corrida.adjusts_run_id,
        "journal_entry_id": corrida.journal_entry_id,
        "employees": len(lineas),
        "gross": _float(Money.sum(Money(l.gross) for l in lineas)),
        "net": _float(Money.sum(Money(l.net) for l in lineas)),
        "employer_charges": _float(Money.sum(Money(l.employer_charges) for l in lineas)),
        "created_at": corrida.created_at,
        "approved_at": corrida.approved_at,
        "paid_at": corrida.paid_at,
    }
    if not con_lineas:
        return salida

    nombres = {
        e.id: _nombre(e)
        for e in db.query(Employee).filter(Employee.id.in_([l.employee_id for l in lineas] or [0])).all()
    }
    salida["lines"] = [
        {
            "id": l.id,
            "employee_id": l.employee_id,
            "employee_name": nombres.get(l.employee_id, ""),
            "contract_id": l.contract_id,
            "gross": _float(l.gross),
            "employee_deductions": _float(l.employee_deductions),
            "income_tax": _float(l.income_tax),
            "other_deductions": _float(l.other_deductions),
            "net": _float(l.net),
            "employer_charges": _float(l.employer_charges),
            "items": [
                {
                    "concept": i.concept,
                    "payer": i.payer,
                    "base": _float(i.base),
                    "rate": _float(i.rate),
                    "amount": _float(i.amount),
                    "action_id": i.action_id,
                    "quantity": _float(i.quantity),
                    "applied_from": i.applied_from,
                    "applied_to": i.applied_to,
                }
                for i in repo.items_of(l.id)
            ],
        }
        for l in lineas
    ]
    return salida


def _corrida(db: Session, run_id: int) -> PayrollRun:
    corrida = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if corrida is None:
        raise api_error(404, "run_not_found", run_id=run_id)
    return corrida


def corridas(db: Session) -> list[dict]:
    filas = db.query(PayrollRun).order_by(PayrollRun.period_to.desc(), PayrollRun.id.desc()).all()
    return [_corrida_out(db, c, con_lineas=False) for c in filas]


def corrida(db: Session, run_id: int) -> dict:
    return _corrida_out(db, _corrida(db, run_id), con_lineas=True)


def crear_corrida(db: Session, datos, *, user_id: int) -> dict:
    caso = CreateRun(
        runs=SqlAlchemyPayrollRepository(db),
        schedules=SqlAlchemyScheduleRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    with traduciendo():
        nueva = caso(datos.schedule_id, datos.cut_date, pay_date=datos.pay_date, user_id=user_id)
    return _corrida_out(db, _corrida(db, nueva.id), con_lineas=True)


def calcular(db: Session, run_id: int) -> dict:
    caso = CalculateRun(
        runs=SqlAlchemyPayrollRepository(db),
        schedules=SqlAlchemyScheduleRepository(db),
        employees=SqlAlchemyEmployeeRepository(db),
        actions=SqlAlchemyActionRepository(db),
        rates=SqlAlchemyRateTable(db),
        settings=SqlAlchemyPayrollSettings(db),
        vacations=SqlAlchemyVacationRepository(db),
        opening=SqlAlchemyOpeningRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
    )
    with traduciendo():
        caso(run_id)
    return corrida(db, run_id)


def aprobar(db: Session, run_id: int, *, user_id: int) -> dict:
    caso = ApproveRun(runs=SqlAlchemyPayrollRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock())
    with traduciendo():
        caso(run_id, user_id=user_id)
    return corrida(db, run_id)


def pagar(db: Session, run_id: int, *, sesion: Sesion, ip: str | None) -> dict:
    """`POST /payroll/runs/{id}/pay` (RN-68, RN-75). Queda en bitácora, en la
    misma transacción que el pago: la anotación entra antes y el caso de uso
    confirma las dos, o revierte las dos."""
    repo = SqlAlchemyPayrollRepository(db)
    fila = repo.get_run(run_id)
    if fila is not None and fila.status == "approved":
        crud_membership.registrar(
            db,
            user_id=sesion.user.id_user,
            company_id=sesion.company_id,
            accion="planilla_pagada",
            detalle=f"corrida {run_id} ({fila.period_from.isoformat()} a {fila.period_to.isoformat()})",
            ip=ip,
        )
    caso = PayRun(
        runs=repo,
        ledger=crud_accounting.libro(db, user_id=sesion.user.id_user),
        vacations=SqlAlchemyVacationRepository(db),
        schedules=SqlAlchemyScheduleRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    with traduciendo():
        caso(run_id, user_id=sesion.user.id_user)
    return corrida(db, run_id)


def crear_aguinaldo(db: Session, datos, *, user_id: int) -> dict:
    """`POST /payroll/runs/aguinaldo` (RF-59, RN-69): la del año, para toda la compañía."""
    caso = CreateAguinaldoRun(runs=SqlAlchemyPayrollRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock())
    with traduciendo():
        nueva = caso(datos.year, pay_date=datos.pay_date, user_id=user_id)
    return _corrida_out(db, _corrida(db, nueva.id), con_lineas=True)


def ajustar(db: Session, run_id: int, *, user_id: int) -> dict:
    """`POST /payroll/runs/{id}/adjust` (RF-63, RN-68): el ajuste nace vacío y
    referenciando a la pagada; calcularlo escribe la diferencia."""
    caso = AdjustRun(runs=SqlAlchemyPayrollRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock())
    with traduciendo():
        nueva = caso(run_id, user_id=user_id)
    return _corrida_out(db, _corrida(db, nueva.id), con_lineas=True)


# --------------------------------------------------------------- vacaciones


def vacaciones(db: Session, employee_id: int) -> dict:
    """`GET /payroll/vacations/{employee}` (RF-60, RN-70): el saldo es la suma."""
    _empleado(db, employee_id)
    movimientos = SqlAlchemyVacationRepository(db).movements(employee_id)
    return {
        "employee_id": employee_id,
        "balance": _float(vacation_balance((m.kind, m.days) for m in movimientos)),
        "movements": [
            {
                "id": m.id,
                "kind": m.kind,
                "days": _float(m.days),
                "on_date": m.on_date,
                "run_id": m.run_id,
                "action_id": m.action_id,
            }
            for m in movimientos
        ],
    }


# ------------------------------------------------------------------- boleta


def boleta(db: Session, run_id: int, employee_id: int) -> dict:
    """`GET /payroll/runs/{id}/payslips/{employee}` (RF-58, RN-66).

    Todo sale de los rubros congelados; acá solo se les pone nombre a las cosas
    —el puesto, la jornada, de qué acción salió cada rubro— para que la boleta
    los pueda imprimir sin volver a preguntar.
    """
    corrida_ = _corrida(db, run_id)
    repo = SqlAlchemyPayrollRepository(db)
    linea = next((l for l in repo.lines_of(run_id) if l.employee_id == employee_id), None)
    if linea is None:
        raise api_error(404, "employee_not_found", employee_id=employee_id)
    e = _empleado(db, employee_id)
    contrato = db.query(EmploymentContract).filter(EmploymentContract.id == linea.contract_id).first()
    puesto = db.query(Position).filter(Position.id == contrato.position_id).first() if contrato else None
    jornada = db.query(WorkSchedule).filter(WorkSchedule.id == contrato.schedule_id).first() if contrato else None
    acciones = {a.id: a for a in SqlAlchemyActionRepository(db).for_employee(employee_id)}
    return {
        "run": {
            "id": corrida_.id,
            "kind": corrida_.kind,
            "period_from": corrida_.period_from,
            "period_to": corrida_.period_to,
            "pay_date": corrida_.pay_date,
            "status": corrida_.status,
            "paid_at": corrida_.paid_at,
            "adjusts_run_id": corrida_.adjusts_run_id,
        },
        "employer_number": configuracion(db)["employer_number"],
        "employee": {
            "id": e.id,
            "first_name": e.first_name,
            "last_name_1": e.last_name_1,
            "last_name_2": e.last_name_2,
            "identification_type": e.identification_type,
            "identification": e.identification,
            "insured_number": e.insured_number,
            "hired_on": e.hired_on,
            "terminated_on": e.terminated_on,
            "iban": e.iban,
            "position_name": puesto.name if puesto is not None else None,
            "schedule_name": jornada.name if jornada is not None else None,
            "frequency": jornada.frequency if jornada is not None else None,
            "period_salary": _float(contrato.period_salary) if contrato is not None else None,
        },
        "line": {
            "gross": _float(linea.gross),
            "employee_deductions": _float(linea.employee_deductions),
            "income_tax": _float(linea.income_tax),
            "other_deductions": _float(linea.other_deductions),
            "net": _float(linea.net),
            "employer_charges": _float(linea.employer_charges),
        },
        "items": [
            {
                "concept": i.concept,
                "payer": i.payer,
                "base": _float(i.base),
                "rate": _float(i.rate),
                "amount": _float(i.amount),
                "action_id": i.action_id,
                "action_kind": acciones[i.action_id].kind if i.action_id in acciones else None,
                "action_memo": acciones[i.action_id].memo if i.action_id in acciones else None,
                "quantity": _float(i.quantity),
                "applied_from": i.applied_from,
                "applied_to": i.applied_to,
            }
            for i in repo.items_of(linea.id)
        ],
    }


# ------------------------------------------------------------ importación


def _error_de_fila(e) -> dict:
    return {"sheet": e.sheet, "row": e.row, "code": e.code, "field": e.field, "reason": e.reason}


def importar(db: Session, datos, *, dry_run: bool, user_id: int) -> dict:
    """`POST /payroll/import?dry_run=` (RF-86, RN-97).

    Las filas vienen ya leídas del Excel por el POS. Con `dry_run` se revisan y
    se responde fila por fila; sin él, entra todo o no entra nada.
    """
    pedido = ImportRequest(
        as_of=datos.as_of,
        positions=tuple(PositionRow(**p.model_dump()) for p in datos.positions),
        employees=tuple(
            EmployeeRow(**{**e.model_dump(exclude={"period_salary"}), "period_salary": Money(e.period_salary)})
            for e in datos.employees
        ),
        earnings=tuple(
            EarningRow(row=e.row, identification=e.identification, month=e.month, gross=Money(e.gross))
            for e in datos.earnings
        ),
        deductions=tuple(
            DeductionRow(
                **{
                    **d.model_dump(exclude={"amount", "balance"}),
                    "amount": Money(d.amount),
                    "balance": None if d.balance is None else Money(d.balance),
                }
            )
            for d in datos.deductions
        ),
    )
    caso = ImportPayroll(
        catalog=SqlAlchemyImportRepository(db),
        employees=SqlAlchemyEmployeeRepository(db),
        actions=SqlAlchemyActionRepository(db),
        vacations=SqlAlchemyVacationRepository(db),
        opening=SqlAlchemyOpeningRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    try:
        resultado = caso(pedido, dry_run=dry_run, user_id=user_id)
    except ImportHasErrors as e:
        raise api_error(400, "import_has_errors", errors=[_error_de_fila(x) for x in e.errors]) from None
    return {
        "dry_run": resultado.dry_run,
        "ok": resultado.ok,
        "errors": [_error_de_fila(x) for x in resultado.errors],
        "positions": resultado.positions,
        "employees": resultado.employees,
        "earnings": resultado.earnings,
        "deductions": resultado.deductions,
    }


# ------------------------------------------------------- los archivos del mes


def informe_ccss(db: Session, year: int, month: int) -> dict:
    """`GET /payroll/exports/ccss` (RF-62, RN-96): lo que pide el formulario de
    Autogestión de la CCSS, por trabajador y con cada movimiento fechado."""
    with traduciendo():
        informe = ExportCcssReport(reports=SqlAlchemyPayrollReports(db))(year, month)
    return {
        "employer_number": informe.employer_number,
        "period_from": informe.period.starts_on,
        "period_to": informe.period.ends_on,
        "total_salary": _float(informe.total_salary),
        "rows": [
            {
                "employee_id": r.employee_id,
                "identification": r.identification,
                "insured_number": r.insured_number,
                "full_name": r.full_name,
                "ccss_code": r.ccss_code,
                "shift": r.shift,
                "salary": _float(r.salary),
                "days": _float(r.days),
                "movements": [
                    {"kind": m.kind, "starts_on": m.starts_on, "ends_on": m.ends_on, "detail": m.detail}
                    for m in r.movements
                ],
            }
            for r in informe.rows
        ],
    }


def archivo_ins(db: Session, year: int, month: int, policy_id: int):
    """`GET /payroll/exports/ins` (RF-85): el archivo de texto de una póliza."""
    with traduciendo():
        return ExportInsFile(reports=SqlAlchemyPayrollReports(db))(year, month, policy_id)


def resumen_renta(db: Session, year: int, month: int) -> dict:
    """`GET /payroll/exports/income-tax` (RF-62, RN-73): la renta retenida del mes."""
    resumen = IncomeTaxSummary(reports=SqlAlchemyPayrollReports(db))(year, month)
    return {
        "period_from": resumen.period.starts_on,
        "period_to": resumen.period.ends_on,
        "total_taxable": _float(resumen.total_taxable),
        "total_withheld": _float(resumen.total_withheld),
        "rows": [
            {
                "employee_id": r.employee_id,
                "identification": r.identification,
                "full_name": r.full_name,
                "taxable": _float(r.taxable),
                "withheld": _float(r.withheld),
            }
            for r in resumen.rows
        ],
    }
