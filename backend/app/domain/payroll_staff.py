"""Empleados, contratos, puestos y pólizas: lo que tiene que cumplir cada uno
(RN-72, RN-94, RN-95, RF-55, RF-56, T-1205, T-1217).

Son validaciones y nada más, pero van en el dominio y no en el esquema del API
por dos razones. La primera es que la importación desde Excel (RN-97) entra por
otra puerta y tiene que rechazar exactamente lo mismo que el formulario. La
segunda es que los datos que se revisan acá —el tipo de identificación, el
género, el estado civil, la nacionalidad, los códigos de ocupación— van tal cual
en los archivos de la CCSS y del INS: un dato que pasa mal hoy es un archivo
rechazado dentro de un mes, cuando quien lo escribió ya no se acuerda.

Lo que se revisa es la **forma**, no la verdad: que la cédula sean dígitos, no
que exista. La CCSS la valida contra el padrón; eso no se puede hacer sin red
ni se debe hacer en la caja.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .errors import InvalidContract, InvalidEmployee, InvalidPayrollSettings
from .money import Money
from .payroll_benefits import TERMINATION_CAUSES

#: Palabras y no códigos (plan §14.6): Hacienda, la CCSS y el INS numeran
#: distinto, y cada archivo traduce a los suyos.
IDENTIFICATION_TYPES: tuple[str, ...] = ("national", "dimex", "nite", "passport", "work_permit")
#: Las que son solo dígitos. El pasaporte y el permiso de trabajo llevan letras.
NUMERIC_IDENTIFICATIONS = frozenset({"national", "dimex", "nite"})
GENDERS: tuple[str, ...] = ("F", "M")
MARITAL_STATUSES: tuple[str, ...] = (
    "single",
    "married",
    "divorced",
    "widowed",
    "separated",
    "free_union",
    "unknown",
)

#: Edad mínima para trabajar en Costa Rica (Código de la Niñez, art. 92): a los
#: quince, con régimen especial. Una fecha de nacimiento que da menos es un
#: dedo de más en el año, no un empleado.
MINIMUM_WORKING_AGE = 15

#: El código de ocupación de la CCSS son cuatro dígitos; el del INS, hasta
#: cinco caracteres. Lo que piden los dos archivos (RN-95).
CCSS_CODE = re.compile(r"^\d{4}$")
INS_CODE = re.compile(r"^[0-9A-Za-z]{1,5}$")
#: El número patronal de la CCSS: dígitos con o sin guiones, como lo imprime la
#: planilla del SICERE («2-03101702934-001-001»: tipo, cédula, consecutivo y
#: sucursal). No se asume un largo exacto —personas físicas y jurídicas lo
#: llevan distinto— pero sí que no es texto libre.
EMPLOYER_NUMBER = re.compile(r"^[0-9-]+$")
EMPLOYER_NUMBER_LENGTH = range(9, 26)
#: Un IBAN tiene entre 15 y 34 caracteres y empieza por el país; el de Costa
#: Rica tiene 22. Se revisa la forma, no el dígito verificador.
IBAN = re.compile(r"^[A-Z]{2}\d{2}[0-9A-Z]{11,30}$")
NATIONALITY = re.compile(r"^[A-Z]{2}$")


def _years_between(start: date, end: date) -> int:
    anos = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        anos -= 1
    return anos


@dataclass(frozen=True)
class EmployeeData:
    """Lo que se revisa de un empleado al darlo de alta o editarlo."""

    identification_type: str
    identification: str
    first_name: str
    last_name_1: str
    birth_date: date
    gender: str
    marital_status: str
    nationality: str
    hired_on: date
    last_name_2: str | None = None
    email: str | None = None
    iban: str | None = None
    dependent_children: int = 0


def check_employee(data: EmployeeData) -> None:
    """Lanza `InvalidEmployee` con el campo y el motivo (RN-72)."""
    if data.identification_type not in IDENTIFICATION_TYPES:
        raise InvalidEmployee("identification_type", "unknown", data.identification_type)
    cedula = data.identification.strip()
    if not cedula:
        raise InvalidEmployee("identification", "required")
    if len(cedula) > 30:
        raise InvalidEmployee("identification", "too_long", cedula)
    if data.identification_type in NUMERIC_IDENTIFICATIONS and not cedula.isdigit():
        raise InvalidEmployee("identification", "not_digits", cedula)
    for campo in ("first_name", "last_name_1"):
        if not getattr(data, campo).strip():
            raise InvalidEmployee(campo, "required")
    if data.birth_date > data.hired_on:
        raise InvalidEmployee("birth_date", "in_the_future", data.birth_date)
    if _years_between(data.birth_date, data.hired_on) < MINIMUM_WORKING_AGE:
        raise InvalidEmployee("birth_date", "too_young", data.birth_date)
    if data.gender not in GENDERS:
        raise InvalidEmployee("gender", "unknown", data.gender)
    if data.marital_status not in MARITAL_STATUSES:
        raise InvalidEmployee("marital_status", "unknown", data.marital_status)
    if not NATIONALITY.match(data.nationality):
        raise InvalidEmployee("nationality", "bad_format", data.nationality)
    if data.email is not None and data.email.strip() and "@" not in data.email:
        raise InvalidEmployee("email", "bad_format", data.email)
    if data.iban is not None and data.iban.strip() and not IBAN.match(data.iban.replace(" ", "").upper()):
        raise InvalidEmployee("iban", "bad_format", data.iban)
    if data.dependent_children < 0:
        raise InvalidEmployee("dependent_children", "negative", data.dependent_children)


def check_termination(hired_on: date, terminated_on: date, cause: str) -> None:
    """La baja: una causa de la lista y una fecha que no sea anterior al ingreso."""
    if cause not in TERMINATION_CAUSES:
        raise InvalidEmployee("termination_cause", "unknown", cause)
    if terminated_on < hired_on:
        raise InvalidEmployee("terminated_on", "before_hire", terminated_on)


@dataclass(frozen=True)
class ContractData:
    valid_from: date
    period_salary: Money
    solidarista_rate: Decimal | None = None


def check_contract(
    data: ContractData,
    *,
    hired_on: date,
    previous_from: date | None,
    schedule_active: bool,
    position_active: bool,
) -> None:
    """Lo que tiene que cumplir un contrato nuevo (RN-94).

    `previous_from` es desde cuándo rige el contrato que este cierra, si hay:
    el nuevo tiene que empezar después, porque un aumento cierra el anterior el
    día antes y dos contratos del mismo día dejarían el salario en el aire.
    """
    if not data.period_salary.is_positive:
        raise InvalidContract("period_salary", "not_positive", data.period_salary.amount)
    if data.valid_from < hired_on:
        raise InvalidContract("valid_from", "before_hire", data.valid_from)
    if previous_from is not None and data.valid_from <= previous_from:
        raise InvalidContract("valid_from", "overlaps", data.valid_from)
    if data.solidarista_rate is not None and not Decimal(0) <= data.solidarista_rate < Decimal(1):
        raise InvalidContract("solidarista_rate", "out_of_range", data.solidarista_rate)
    if not schedule_active:
        raise InvalidContract("schedule_id", "inactive")
    if not position_active:
        raise InvalidContract("position_id", "inactive")


def check_position(name: str, ccss_code: str, ins_code: str) -> None:
    """Un puesto con sus dos códigos (RN-95)."""
    if not name.strip():
        raise InvalidPayrollSettings("name", "required")
    if not CCSS_CODE.match(ccss_code.strip()):
        raise InvalidPayrollSettings("ccss_code", "bad_format", ccss_code)
    if not INS_CODE.match(ins_code.strip()):
        raise InvalidPayrollSettings("ins_code", "bad_format", ins_code)


def check_policy(number: str, rt_rate: Decimal) -> None:
    """Una póliza de riesgos del trabajo: su número y su prima, como fracción."""
    if not number.strip():
        raise InvalidPayrollSettings("number", "required")
    if len(number.strip()) > 20:
        raise InvalidPayrollSettings("number", "too_long", number)
    if not Decimal(0) < rt_rate < Decimal(1):
        raise InvalidPayrollSettings("rt_rate", "out_of_range", rt_rate)


def clean_employer_number(value: object) -> str | None:
    """El número patronal limpio, `None` si viene vacío, o el «no» con su motivo.

    Vacío es «todavía no lo tengo»: la compañía que no presenta planilla a la
    CCSS —porque todavía no tiene empleados— no está obligada a saberlo para
    guardar el resto de su configuración. La pantalla de lo que falta (T-1213)
    lo reclama antes de exportar.
    """
    if value is None:
        return None
    texto = str(value).strip()
    if not texto:
        return None
    if not EMPLOYER_NUMBER.match(texto):
        raise InvalidPayrollSettings("employer_number", "bad_format", texto)
    if len(texto) < EMPLOYER_NUMBER_LENGTH.start:
        raise InvalidPayrollSettings("employer_number", "too_short", texto)
    if len(texto) >= EMPLOYER_NUMBER_LENGTH.stop:
        raise InvalidPayrollSettings("employer_number", "too_long", texto)
    return texto
