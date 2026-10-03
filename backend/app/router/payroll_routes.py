"""Planilla (F12).

Leer no exige el módulo: una compañía que bajó de plan tiene que seguir viendo
sus boletas y sus tasas, que son la prueba de lo pagado (RN-50). Escribir sí lo
exige, ruta por ruta, con `require_module("payroll")`.

**Todo es de administrador**, también leer: la planilla es lo más delicado que
guarda el sistema después del libro —salarios, embargos, incapacidades— y un
cajero no tiene por qué ver lo que gana el de al lado.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.schemas.schemas_payroll import (
    ActionIn,
    ActionOut,
    ActionUpdate,
    CancelIn,
    ContractIn,
    ContractOut,
    EmployeeIn,
    EmployeeOut,
    EmployeeUpdate,
    PayrollRatesOut,
    PayrollSettingsIn,
    PayrollSettingsOut,
    PolicyIn,
    PolicyOut,
    PolicyUpdate,
    PositionIn,
    PositionOut,
    PositionUpdate,
    RunDetailOut,
    RunIn,
    RunOut,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdate,
    SuspendIn,
    TerminatedOut,
    TerminationIn,
)
from app.services import crud_payroll, crud_payroll_rates
from app.utils import clock
from app.utils.auth_dependency import Sesion, get_db, require_admin, require_module

router = APIRouter()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# -------------------------------------------------------------------- tasas


@router.get("/rates", response_model=PayrollRatesOut)
def tasas(
    on: date | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Lo que rige a una fecha —hoy si no se dice—, con su fuente (RF-56, T-1204).

    Son las mismas para todas las compañías: las tablas son del país. Lo que
    cambia de una a otra es la póliza y el solidarista, que viven en lo suyo.
    """
    hoy = clock.today()
    return crud_payroll_rates.vigentes(db, on or hoy, hoy)


# ------------------------------------------------------ configuración (T-1217)


@router.get("/settings", response_model=PayrollSettingsOut)
def configuracion(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.configuracion(db)


@router.put("/settings", response_model=PayrollSettingsOut)
def guardar_configuracion(
    payload: PayrollSettingsIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """El número patronal de la CCSS y si el INA está exento (RF-56)."""
    return crud_payroll.guardar_configuracion(
        db, employer_number=payload.employer_number, ina_exempt=payload.ina_exempt
    )


@router.get("/schedules", response_model=list[ScheduleOut])
def jornadas(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.jornadas(db)


@router.post("/schedules", response_model=ScheduleOut)
def crear_jornada(
    payload: ScheduleIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Una jornada: periodicidad, clase, horas y cortes (RF-83, RN-94)."""
    return crud_payroll.crear_jornada(db, payload)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def actualizar_jornada(
    schedule_id: int,
    payload: ScheduleUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Con corridas pagadas, la periodicidad y los cortes no se tocan (`schedule_locked`)."""
    return crud_payroll.actualizar_jornada(db, schedule_id, payload)


@router.get("/positions", response_model=list[PositionOut])
def puestos(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.puestos(db)


@router.post("/positions", response_model=PositionOut)
def crear_puesto(
    payload: PositionIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Un puesto con su código de la CCSS y el del INS (RF-84, RN-95)."""
    return crud_payroll.crear_puesto(db, payload)


@router.put("/positions/{position_id}", response_model=PositionOut)
def actualizar_puesto(
    position_id: int,
    payload: PositionUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    return crud_payroll.actualizar_puesto(db, position_id, payload)


@router.get("/policies", response_model=list[PolicyOut])
def polizas(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.polizas(db)


@router.post("/policies", response_model=PolicyOut)
def crear_poliza(
    payload: PolicyIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Una póliza de riesgos del trabajo con su prima. La primera queda por omisión."""
    return crud_payroll.crear_poliza(db, payload)


@router.put("/policies/{policy_id}", response_model=PolicyOut)
def actualizar_poliza(
    policy_id: int,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    return crud_payroll.actualizar_poliza(db, policy_id, payload)


# ---------------------------------------------------------- empleados (T-1205)


@router.get("/employees", response_model=list[EmployeeOut])
def empleados(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Todos, con su contrato vigente; los que salieron, con su fecha y causa."""
    return crud_payroll.empleados(db)


@router.post("/employees", response_model=EmployeeOut)
def crear_empleado(
    payload: EmployeeIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """El alta, con lo que piden la CCSS y el INS (RF-55, RN-72). Sin contrato
    todavía: ese va por `POST /payroll/contracts`."""
    return crud_payroll.crear_empleado(db, payload)


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def empleado(employee_id: int, db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.empleado(db, employee_id)


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
def actualizar_empleado(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    return crud_payroll.actualizar_empleado(db, employee_id, payload)


@router.post("/employees/{employee_id}/terminate", response_model=TerminatedOut)
def dar_de_baja(
    employee_id: int,
    payload: TerminationIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """La baja: fecha y causa, el contrato cerrado, la acción en el historial y
    la liquidación en borrador (RF-55, RF-61)."""
    return crud_payroll.dar_de_baja(db, employee_id, payload, user_id=admin.user.id_user)


@router.get("/employees/{employee_id}/actions", response_model=list[ActionOut])
def historial(employee_id: int, db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """El historial: cada acción con lo que aplicó cada corrida y su saldo (RF-82)."""
    return crud_payroll.historial(db, employee_id)


@router.get("/contracts", response_model=list[ContractOut])
def contratos(
    employee: int = Query(...),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_payroll.contratos(db, employee)


@router.post("/contracts", response_model=ContractOut)
def crear_contrato(
    payload: ContractIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """El contrato: jornada, puesto, póliza y salario del periodo (RN-94). Uno
    nuevo cierra el anterior el día antes."""
    return crud_payroll.crear_contrato(db, payload)


# ------------------------------------------------- acciones de personal (T-1218)


@router.post("/actions", response_model=ActionOut)
def registrar_accion(
    payload: ActionIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Una acción en el empleado (RF-82, RN-90). La corrida que le toque la toma."""
    return crud_payroll.registrar_accion(db, payload, user_id=admin.user.id_user)


@router.put("/actions/{action_id}", response_model=ActionOut)
def editar_accion(
    action_id: int,
    payload: ActionUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Solo la que ninguna corrida aplicó; la aplicada se anula (RN-91)."""
    return crud_payroll.editar_accion(db, action_id, payload)


@router.post("/actions/{action_id}/cancel", response_model=ActionOut)
def anular_accion(
    action_id: int,
    payload: CancelIn | None = None,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Anula con otra acción que la referencia; la corrida siguiente la revierte (RN-91)."""
    return crud_payroll.anular_accion(
        db, action_id, user_id=admin.user.id_user, memo=payload.memo if payload else None
    )


@router.post("/actions/{action_id}/suspend", response_model=ActionOut)
def suspender_accion(
    action_id: int,
    payload: SuspendIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Suspende una deducción recurrente, con motivo (RN-92)."""
    return crud_payroll.suspender_accion(db, action_id, user_id=admin.user.id_user, reason=payload.reason)


# ---------------------------------------------------------- corridas (T-1206)


@router.get("/runs", response_model=list[RunOut])
def corridas(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    return crud_payroll.corridas(db)


@router.post("/runs", response_model=RunDetailOut)
def crear_corrida(
    payload: RunIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Una corrida regular de una jornada y un corte (RF-57, RN-94)."""
    return crud_payroll.crear_corrida(db, payload, user_id=admin.user.id_user)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def corrida(run_id: int, db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Las líneas y los rubros congelados (RN-66)."""
    return crud_payroll.corrida(db, run_id)


@router.post("/runs/{run_id}/calculate", response_model=RunDetailOut)
def calcular(
    run_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Toma las acciones del periodo y escribe líneas y rubros: el congelamiento."""
    return crud_payroll.calcular(db, run_id)


@router.post("/runs/{run_id}/approve", response_model=RunDetailOut)
def aprobar(
    run_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    return crud_payroll.aprobar(db, run_id, user_id=admin.user.id_user)


@router.post("/runs/{run_id}/pay", response_model=RunDetailOut)
def pagar(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("payroll")),
):
    """Pagada, con fecha del servidor, bitácora y el asiento si hay libro (RN-68, RN-75)."""
    return crud_payroll.pagar(db, run_id, sesion=admin, ip=_ip(request))
