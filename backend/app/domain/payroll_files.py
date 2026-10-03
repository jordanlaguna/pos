"""Los archivos del mes: la planilla para el INS, el informe para la CCSS y el
resumen de renta retenida (RN-96, RF-62, RF-85, T-1211, T-1219).

Los tres se arman de lo mismo: las corridas **pagadas** cuyo corte cae en el
mes, con sus rubros congelados y las fechas de cada acción que aplicaron. Lo
que no se pagó no se declara, y lo que se declara es exactamente lo que dice la
boleta (RN-66): un archivo que no coincide con lo pagado lo cobra la institución
con recargos.

El INS (RT-Virtual)
-------------------
`ins_file` escribe el archivo de texto de ancho fijo que RT-Virtual recibe,
versión **V08D**: tres líneas de encabezado —póliza, patrono, correo y
domicilio— y una línea por trabajador con su identificación, nombre, salario,
días, horas, jornada, observación y código de ocupación. El trazado está en
`docs/ins/README.md`, con su procedencia: la herramienta pública que reproduce
la plantilla del INS y la charla oficial sobre los tipos de identificación.
**Falta cotejarlo contra la opción «Estructura del archivo» dentro de
RT-Virtual**, que pide la sesión de la póliza; hasta entonces, un rechazo del
INS se corrige acá y no en la planilla.

La CCSS (SICERE)
----------------
`ccss_report` no escribe un archivo de texto: la CCSS publica el formulario de
Autogestión —con el que presenta la planilla el 98 % de los patronos— y no el
trazado del archivo de grandes clientes. El informe trae, por trabajador,
exactamente lo que ese formulario pide: identificación, ocupación, jornada,
salario del mes y cada movimiento con sus fechas —inclusión, exclusión,
incapacidad por SEM, INS o maternidad, permiso con o sin goce, cambio de
ocupación—. Lo dice `docs/ccss/README.md`.

Nada de acá conoce la base de datos: recibe `WorkerMonth`, que es lo que un mes
pagado sabe de un trabajador, y devuelve texto y filas.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

from .errors import ExportDataIncomplete
from .money import Money
from .payroll import EARNING, EMPLOYEE, PayItem
from .payroll_actions import (
    BASE,
    CONTRIBUTORY,
    MATERNITY,
    PAID_LEAVE,
    POSITION_CHANGE,
    SICK_LEAVE_CCSS,
    SICK_LEAVE_INS,
    TAXABLE,
    UNPAID_LEAVE,
)
from .payroll_benefits import EARNED_CONCEPTS
from .payroll_calendar import Period
from .payroll_staff import NUMERIC_IDENTIFICATIONS

INCOME_TAX = "income_tax"


# ------------------------------------------------------------- lo que entra


@dataclass(frozen=True)
class WorkerAction:
    """Una acción del empleado que toca el mes, con sus fechas (RN-90)."""

    kind: str
    starts_on: date
    ends_on: date | None = None
    #: En un cambio de puesto, el código de ocupación de la CCSS del nuevo.
    new_ccss_code: str | None = None


@dataclass(frozen=True)
class WorkerMonth:
    """Lo que un mes pagado sabe de un trabajador."""

    employee_id: int
    identification_type: str
    identification: str
    insured_number: str | None
    first_name: str
    last_name_1: str
    last_name_2: str | None
    hired_on: date
    terminated_on: date | None
    termination_cause: str | None
    #: Del puesto del último contrato que tocó el mes.
    ccss_code: str | None
    ins_code: str | None
    #: La póliza efectiva: la del contrato o la de la compañía por omisión.
    policy_id: int | None
    policy_number: str | None
    shift: str
    hours_per_day: Decimal
    #: Los rubros de las corridas pagadas con corte en el mes (regulares y ajustes).
    items: tuple[PayItem, ...]
    actions: tuple[WorkerAction, ...]

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name_1, self.last_name_2) if p)


@dataclass(frozen=True)
class Employer:
    """Lo que los encabezados piden de la compañía."""

    #: El tipo de Hacienda ('01' física, '02' jurídica, '03' DIMEX, '04' NITE).
    identification_type: str | None
    identification: str | None
    employer_number: str | None
    phone: str | None
    email: str | None
    address: str | None


def month_period(year: int, month: int) -> Period:
    return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))


# ------------------------------------------------------------ lo que falta

NATIONAL = "national"


def missing_for_ccss(worker: WorkerMonth) -> tuple[str, ...]:
    """Lo que el formulario de la CCSS no acepta en blanco."""
    faltan = []
    if worker.identification_type != NATIONAL and not worker.insured_number:
        faltan.append("insured_number")
    if not worker.ccss_code:
        faltan.append("ccss_code")
    return tuple(faltan)


def missing_for_ins(worker: WorkerMonth) -> tuple[str, ...]:
    faltan = []
    if worker.identification_type != NATIONAL and not worker.insured_number:
        faltan.append("insured_number")
    if not worker.ins_code:
        faltan.append("ins_code")
    if worker.policy_id is None:
        faltan.append("policy")
    return tuple(faltan)


def check_complete(
    workers: Iterable[WorkerMonth],
    *,
    per_worker,
    company: Sequence[tuple[str, object]],
) -> None:
    """`ExportDataIncomplete` con todo lo que falta, de una vez (RN-96).

    `per_worker` es `missing_for_ccss` o `missing_for_ins`; `company`, pares
    `(campo, valor)` de la compañía que no pueden estar vacíos. Se junta todo
    antes de fallar para que la pantalla lo liste completo y no de uno en uno.
    """
    faltantes = tuple((w.employee_id, campos) for w in workers for campos in (per_worker(w),) if campos)
    de_la_compania = tuple(campo for campo, valor in company if not valor)
    if faltantes or de_la_compania:
        raise ExportDataIncomplete(faltantes, de_la_compania)


# ------------------------------------------------------------- las sumas


def earned(items: Iterable[PayItem], concepts: frozenset[str]) -> Money:
    return Money.sum(i.amount for i in items if i.payer == EARNING and i.concept in concepts)


def days_paid(items: Iterable[PayItem]) -> Decimal:
    """Los días que pagó el salario base en el mes: la suma de sus cantidades."""
    return sum((Decimal(i.quantity) for i in items if i.concept == BASE and i.payer == EARNING and i.quantity), Decimal(0))


def withheld(items: Iterable[PayItem]) -> Money:
    return Money.sum(i.amount for i in items if i.payer == EMPLOYEE and i.concept == INCOME_TAX)


def _ranges(items: Iterable[PayItem], kind: str) -> list[tuple[date, date]]:
    """Desde y hasta de lo que se aplicó de cada acción de ese tipo, juntando
    los tramos de una misma acción (una incapacidad que cruzó dos quincenas)."""
    por_accion: dict[int | None, list[tuple[date, date]]] = {}
    for i in items:
        if i.concept != kind or i.payer != EARNING or i.applied_from is None or i.applied_to is None:
            continue
        por_accion.setdefault(i.action_id, []).append((i.applied_from, i.applied_to))
    return sorted((min(d for d, _ in tramos), max(h for _, h in tramos)) for tramos in por_accion.values())


# ------------------------------------------------------------- la CCSS

#: Lo que el formulario de Autogestión llama jornada: diurna de 8, parcial de 4,
#: mixta de 7, vespertina de 7 y nocturna de 6 horas. Se decide por la clase y
#: las horas de la jornada del contrato.
CCSS_SHIFTS = {"day": "diurna", "mixed": "mixta", "night": "nocturna"}
PART_TIME_HOURS = Decimal(4)

#: Los movimientos del informe, por nombre (la pantalla los traduce).
INCLUSION = "inclusion"
EXCLUSION = "exclusion"
SICK_LEAVE_SEM = "sick_leave_sem"
LEAVE_PAID = "leave_paid"
LEAVE_UNPAID = "leave_unpaid"
OCCUPATION_CHANGE = "occupation_change"


@dataclass(frozen=True)
class Movement:
    kind: str
    starts_on: date
    ends_on: date | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CcssRow:
    employee_id: int
    identification: str
    insured_number: str | None
    full_name: str
    ccss_code: str
    shift: str
    salary: Money
    days: Decimal
    movements: tuple[Movement, ...]


@dataclass(frozen=True)
class CcssReport:
    employer_number: str
    period: Period
    rows: tuple[CcssRow, ...]

    @property
    def total_salary(self) -> Money:
        return Money.sum(r.salary for r in self.rows)


def ccss_identification(worker: WorkerMonth) -> str:
    """Como la pide el formulario: la cédula a nueve dígitos, con cero adelante
    si el asiento tiene tres; a los demás, su número de asegurado."""
    if worker.identification_type == NATIONAL:
        return worker.identification.strip().zfill(9)
    return (worker.insured_number or worker.identification).strip()


def ccss_shift(worker: WorkerMonth) -> str:
    if worker.hours_per_day <= PART_TIME_HOURS:
        return "parcial"
    return CCSS_SHIFTS.get(worker.shift, "diurna")


def ccss_movements(worker: WorkerMonth, period: Period) -> tuple[Movement, ...]:
    movimientos: list[Movement] = []
    if worker.hired_on in period:
        movimientos.append(Movement(INCLUSION, worker.hired_on))
    if worker.terminated_on is not None and worker.terminated_on in period:
        movimientos.append(Movement(EXCLUSION, worker.terminated_on, detail=worker.termination_cause))
    for kind, nombre in ((SICK_LEAVE_CCSS, SICK_LEAVE_SEM), (SICK_LEAVE_INS, SICK_LEAVE_INS), (MATERNITY, MATERNITY)):
        for desde, hasta in _ranges(worker.items, kind):
            movimientos.append(Movement(nombre, desde, hasta))
    for kind, nombre in ((PAID_LEAVE, LEAVE_PAID), (UNPAID_LEAVE, LEAVE_UNPAID)):
        for desde, hasta in _ranges(worker.items, kind):
            movimientos.append(Movement(nombre, desde, hasta))
    for accion in worker.actions:
        if accion.kind == POSITION_CHANGE and accion.starts_on in period:
            movimientos.append(Movement(OCCUPATION_CHANGE, accion.starts_on, detail=accion.new_ccss_code))
    return tuple(sorted(movimientos, key=lambda m: (m.starts_on, m.kind)))


def ccss_report(employer: Employer, workers: Sequence[WorkerMonth], period: Period) -> CcssReport:
    """El informe del mes para la CCSS: lo que el formulario de Autogestión pide
    por trabajador. El salario es lo que cotiza (RN-96)."""
    check_complete(workers, per_worker=missing_for_ccss, company=(("employer_number", employer.employer_number),))
    filas = tuple(
        CcssRow(
            employee_id=w.employee_id,
            identification=ccss_identification(w),
            insured_number=w.insured_number,
            full_name=w.full_name,
            ccss_code=w.ccss_code or "",
            shift=ccss_shift(w),
            salary=earned(w.items, CONTRIBUTORY),
            days=days_paid(w.items),
            movements=ccss_movements(w, period),
        )
        for w in sorted(workers, key=lambda w: (w.last_name_1, w.first_name, w.employee_id))
    )
    assert employer.employer_number is not None
    return CcssReport(employer.employer_number, period, filas)


# -------------------------------------------------------------- la renta


@dataclass(frozen=True)
class IncomeTaxRow:
    employee_id: int
    identification: str
    full_name: str
    taxable: Money
    withheld: Money


@dataclass(frozen=True)
class IncomeTaxReport:
    period: Period
    rows: tuple[IncomeTaxRow, ...]

    @property
    def total_taxable(self) -> Money:
        return Money.sum(r.taxable for r in self.rows)

    @property
    def total_withheld(self) -> Money:
        return Money.sum(r.withheld for r in self.rows)


def income_tax_report(workers: Sequence[WorkerMonth], period: Period) -> IncomeTaxReport:
    """La renta retenida del mes: la suma de los rubros `income_tax` de las
    corridas pagadas (RF-62), que es lo que se declara (RN-73)."""
    filas = tuple(
        IncomeTaxRow(w.employee_id, w.identification, w.full_name, earned(w.items, TAXABLE), withheld(w.items))
        for w in sorted(workers, key=lambda w: (w.last_name_1, w.first_name, w.employee_id))
    )
    return IncomeTaxReport(period, filas)


# ---------------------------------------------------------------- el INS

INS_VERSION = "V08D"
INS_MONTHLY = "M"
INS_ENCODING = "iso-8859-1"
INS_LINE_END = "\r\n"

#: El tipo de identificación en la posición 1 del registro: 0 cédula nacional,
#: 6 documento único (DIMEX, NITE), 8 permiso de trabajo, 9 pasaporte.
INS_ID_TYPES = {NATIONAL: "0", "dimex": "6", "nite": "6", "passport": "9", "work_permit": "8"}
#: El del patrono en el encabezado, desde el tipo de Hacienda: 0 física, 2
#: jurídica, 6 DIMEX o NITE.
INS_EMPLOYER_TYPES = {"01": "0", "02": "2", "03": "6", "04": "6"}

#: Jornada: 01 tiempo completo, 02 medio tiempo. Las ocasionales por día u hora
#: (03, 04) no existen en VentaSys: el salario por hora quedó fuera (plan §14.1).
INS_FULL_TIME = "01"
INS_PART_TIME = "02"
INS_FULL_TIME_HOURS = Decimal(6)

#: Observación: 00 ninguna, 01 ingresó, 02 salió, 03 incapacidad de la CCSS,
#: 04 incapacidad del INS, 05 ingresó y salió, 06 permiso sin goce, 07 maternidad.
INS_NONE = "00"
INS_HIRED = "01"
INS_TERMINATED = "02"
INS_SICK_CCSS = "03"
INS_SICK_INS = "04"
INS_HIRED_AND_TERMINATED = "05"
INS_UNPAID_LEAVE = "06"
INS_MATERNITY = "07"

INS_NAME_WIDTH = 15


@dataclass(frozen=True)
class InsFile:
    filename: str
    content: str

    @property
    def encoded(self) -> bytes:
        return self.content.encode(INS_ENCODING, errors="replace")


def _texto(valor: str | None, ancho: int) -> str:
    return (valor or "").upper()[:ancho].ljust(ancho)


def _digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def ins_policy_number(number: str | None) -> str:
    """La póliza a siete dígitos: solo los números, con ceros adelante."""
    return _digitos(number)[-7:].zfill(7)


def ins_shift(worker: WorkerMonth) -> str:
    return INS_FULL_TIME if worker.hours_per_day >= INS_FULL_TIME_HOURS else INS_PART_TIME


def ins_observation(worker: WorkerMonth, period: Period) -> str:
    """Una sola observación por trabajador, la que más pesa."""
    ingreso = worker.hired_on in period
    salida = worker.terminated_on is not None and worker.terminated_on in period
    if ingreso and salida:
        return INS_HIRED_AND_TERMINATED
    if ingreso:
        return INS_HIRED
    if salida:
        return INS_TERMINATED
    if _ranges(worker.items, MATERNITY):
        return INS_MATERNITY
    if _ranges(worker.items, SICK_LEAVE_CCSS):
        return INS_SICK_CCSS
    if _ranges(worker.items, SICK_LEAVE_INS):
        return INS_SICK_INS
    if _ranges(worker.items, UNPAID_LEAVE):
        return INS_UNPAID_LEAVE
    return INS_NONE


def ins_days_and_hours(worker: WorkerMonth) -> tuple[int, int]:
    """Los días que pagó el salario base, enteros y sin pasar del mes, y las
    horas de la jornada por esos días."""
    dias = int(min(days_paid(worker.items), Decimal(31)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    horas = int((Decimal(dias) * worker.hours_per_day).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return dias, horas


def ins_record(worker: WorkerMonth, period: Period) -> str:
    """Una línea del archivo: 114 posiciones de ancho fijo (V08D).

    1 tipo de identificación · 2-20 número · 21-40 número de asegurado (solo
    extranjeros: el de los nacionales es la cédula y no va) · 41-55 nombre ·
    56-70 primer apellido · 71-85 segundo apellido · 86-98 salario con dos
    decimales y ceros adelante · 99-101 días · 102-105 horas · 106-107 jornada
    · 108-109 observación · 110 cero · 111-114 ocupación.
    """
    dias, horas = ins_days_and_hours(worker)
    salario = earned(worker.items, EARNED_CONCEPTS)
    asegurado = "" if worker.identification_type == NATIONAL else (worker.insured_number or "")
    tipo = INS_ID_TYPES.get(worker.identification_type, "0")
    return (
        tipo
        + _texto(worker.identification.strip(), 19)
        + _texto(asegurado, 20)
        + _texto(worker.first_name, INS_NAME_WIDTH)
        + _texto(worker.last_name_1, INS_NAME_WIDTH)
        + _texto(worker.last_name_2 or "...", INS_NAME_WIDTH)
        + f"{max(salario.amount, Decimal(0)):.2f}".zfill(13)
        + f"{dias:03d}"
        + f"{horas:04d}"
        + ins_shift(worker)
        + ins_observation(worker, period)
        + "0"
        + _digitos(worker.ins_code).zfill(4)[-4:]
    )


def ins_header(employer: Employer, policy_number: str, period: Period) -> list[str]:
    """Las tres líneas con que empieza el archivo: la póliza y el patrono, el
    correo y el domicilio."""
    tipo = INS_EMPLOYER_TYPES.get(employer.identification_type or "", "0")
    primera = (
        ins_policy_number(policy_number)
        + INS_MONTHLY
        + f"{period.starts_on.year:04d}"
        + f"{period.starts_on.month:02d}"
        + " "
        + _texto(tipo + _digitos(employer.identification), 20)
        + _digitos(employer.phone)[-8:].zfill(8)
        + "0" * 8
        + " "
        + INS_VERSION
    )
    return [primera, "Email " + (employer.email or "")[:50].ljust(50), "Domicilio " + _texto(employer.address, 171)]


def ins_file(employer: Employer, policy_number: str, workers: Sequence[WorkerMonth], period: Period) -> InsFile:
    """El archivo de una póliza para un mes (RF-85, RN-96).

    `workers` son los de esa póliza. Se revisa antes que a nadie le falte el
    código del INS ni el número de asegurado, y que la compañía tenga cédula.
    """
    check_complete(
        workers,
        per_worker=missing_for_ins,
        company=(("identification", employer.identification), ("policy_number", _digitos(policy_number) or None)),
    )
    lineas = ins_header(employer, policy_number, period) + [
        ins_record(w, period) for w in sorted(workers, key=lambda w: (w.last_name_1, w.first_name, w.employee_id))
    ]
    nombre = f"PL{ins_policy_number(policy_number)}{INS_MONTHLY}{period.starts_on.year:04d}{period.starts_on.month:02d}-{INS_VERSION} (Texto).txt"
    return InsFile(nombre, INS_LINE_END.join(lineas) + INS_LINE_END)
