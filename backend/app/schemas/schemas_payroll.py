"""Planilla: lo que entra y lo que sale (F12).

Sin frases, como el resto del API (RN-30): `payer`, `concept`, `kind` y
`status` son datos, y la pantalla arma la oración con su catálogo.

**Los valores cerrados —la periodicidad de una jornada, el tipo de una acción,
la causa de una baja— llegan como texto y los revisa el dominio**, no un
`Literal`: así el «no» sale con su código (`invalid_schedule`,
`invalid_action`) y no como el 422 genérico de un cuerpo mal formado, que la
pantalla no sabe explicar. La plata entra como `Decimal` y sale como `float`,
igual que en el resto de los esquemas.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------- tasas


class PayrollRateOut(BaseModel):
    """Una tasa que rige, con su fuente y cuándo se comprobó (RN-67)."""

    concept: str
    #: 'employee' | 'employer' | 'rule'.
    payer: str
    #: Una fracción (0.055 es el 5,5 %), un número de días o un monto, según el
    #: concepto.
    value: float
    valid_from: date
    valid_to: date | None = None
    source: str
    verified_at: date
    #: Más de seis meses sin comprobar: pudo salir un decreto y nadie lo cargó.
    stale: bool


class TaxBracketOut(BaseModel):
    lower: float
    #: Nulo en el último tramo, que no tiene techo.
    upper: float | None = None
    rate: float
    valid_from: date
    source: str
    verified_at: date


class TaxCreditOut(BaseModel):
    #: 'child' | 'spouse'.
    concept: str
    amount: float
    valid_from: date
    source: str


class SeveranceOut(BaseModel):
    years_from: float
    years_to: float | None = None
    #: Por debajo del año, días en total; desde el año, días por año.
    days: float
    source: str


class PayrollRatesOut(BaseModel):
    """Lo que rige a una fecha (`GET /payroll/rates?on=`, T-1204)."""

    on: date
    country: str
    rates: list[PayrollRateOut]
    brackets: list[TaxBracketOut]
    credits: list[TaxCreditOut]
    severance: list[SeveranceOut]
    #: `concepto:pagador` de las cargas que faltan a esa fecha. Con alguna, una
    #: corrida de ese corte no se puede calcular (`rates_missing_for_date`).
    missing: list[str]
    #: Alguna tasa o tramo lleva más de seis meses sin comprobarse.
    stale: bool


class PayrollRateIn(BaseModel):
    """Una tasa nueva, que soporte agrega con su vigencia (`PUT /support/payroll/rates`).

    No hay forma de editar una existente: la que cambia entra como otra fila,
    posterior a la última del mismo concepto (RN-67).
    """

    country: Literal["CR"] = "CR"
    concept: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    payer: str
    value: Decimal
    valid_from: date
    #: La norma o la URL. Sin fuente no es un dato, es un rumor.
    source: str = Field(min_length=5, max_length=255)


class TaxBracketIn(BaseModel):
    lower: Decimal
    upper: Decimal | None = None
    rate: Decimal


class TaxBracketsIn(BaseModel):
    """El juego de tramos y créditos del año siguiente, entero (T-1221).

    Entero y con una sola vigencia porque el decreto lo publica así, y porque
    `GET /payroll/rates?on=` devuelve el juego más reciente que rige: medio
    juego nuevo taparía la mitad del viejo.
    """

    country: Literal["CR"] = "CR"
    valid_from: date
    brackets: list[TaxBracketIn]
    child_credit: Decimal
    spouse_credit: Decimal
    source: str = Field(min_length=5, max_length=255)


class TaxBracketsOut(BaseModel):
    valid_from: date
    brackets: list[TaxBracketOut]
    credits: list[TaxCreditOut]


# ----------------------------------------------------- configuración (T-1217)


class PayrollSettingsOut(BaseModel):
    """Los datos patronales: el número de la CCSS y si el INA está exento."""

    employer_number: str | None = None
    ina_exempt: bool = False


class PayrollSettingsIn(BaseModel):
    employer_number: str | None = None
    ina_exempt: bool = False


class ScheduleIn(BaseModel):
    """Una jornada (RN-94). De los tres datos de corte se manda el de su
    periodicidad y solo ese; `hours_per_day` en blanco toma las de su clase."""

    name: str = Field(min_length=1, max_length=80)
    frequency: str
    shift: str = "day"
    hours_per_day: Decimal | None = None
    workdays_per_week: int = 6
    rest_day_paid: bool = True
    first_cut_day: int | None = None
    cut_weekday: int | None = None
    series_start: date | None = None


class ScheduleUpdate(BaseModel):
    """Lo que se puede cambiar. Con corridas pagadas, la periodicidad y los
    cortes no (RF-83): se crea otra jornada."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    frequency: str | None = None
    shift: str | None = None
    hours_per_day: Decimal | None = None
    workdays_per_week: int | None = None
    rest_day_paid: bool | None = None
    first_cut_day: int | None = None
    cut_weekday: int | None = None
    series_start: date | None = None
    is_active: bool | None = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    frequency: str
    shift: str
    hours_per_day: float
    workdays_per_week: int
    rest_day_paid: bool
    first_cut_day: int | None = None
    cut_weekday: int | None = None
    series_start: date | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class PositionIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    ccss_code: str = Field(max_length=10)
    ins_code: str = Field(max_length=10)


class PositionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    ccss_code: str | None = Field(default=None, max_length=10)
    ins_code: str | None = Field(default=None, max_length=10)
    is_active: bool | None = None


class PositionOut(BaseModel):
    id: int
    name: str
    ccss_code: str
    ins_code: str
    is_active: bool

    model_config = {"from_attributes": True}


class PolicyIn(BaseModel):
    number: str = Field(min_length=1, max_length=40)
    #: La prima que fija el INS, como fracción: el 1,46 % es 0.0146.
    rt_rate: Decimal
    is_default: bool = False


class PolicyUpdate(BaseModel):
    rt_rate: Decimal | None = None
    is_default: bool | None = None


class PolicyOut(BaseModel):
    id: int
    number: str
    rt_rate: float
    is_default: bool

    model_config = {"from_attributes": True}


# --------------------------------------------------- empleados (T-1205)


class ContractOut(BaseModel):
    id: int
    employee_id: int
    schedule_id: int
    position_id: int
    ins_policy_id: int | None = None
    valid_from: date
    valid_to: date | None = None
    #: El salario del periodo de su jornada (RN-94).
    period_salary: float
    solidarista_rate: float | None = None

    model_config = {"from_attributes": True}


class EmployeeContractIn(BaseModel):
    """El contrato que viene con el alta (RF-55). Rige desde el ingreso, así
    que no lleva fecha: la pone `hired_on`."""

    schedule_id: int
    position_id: int
    ins_policy_id: int | None = None
    period_salary: Decimal
    solidarista_rate: Decimal | None = None


class EmployeeIn(BaseModel):
    """Lo que piden los archivos de la CCSS y del INS (RN-72)."""

    identification_type: str
    identification: str = Field(min_length=1, max_length=30)
    first_name: str = Field(min_length=1, max_length=60)
    last_name_1: str = Field(min_length=1, max_length=40)
    last_name_2: str | None = Field(default=None, max_length=40)
    insured_number: str | None = Field(default=None, max_length=25)
    birth_date: date
    gender: str
    marital_status: str
    nationality: str = "CR"
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    is_pensioner: bool = False
    iban: str | None = Field(default=None, max_length=34)
    hired_on: date
    dependent_children: int = 0
    spouse_credit: bool = False
    #: La cuenta del POS, si es la misma persona (RN-72).
    user_id: int | None = None
    #: El contrato, si se da en el alta. Sin él, va después por `/contracts`.
    contract: EmployeeContractIn | None = None


class EmployeeUpdate(BaseModel):
    identification_type: str | None = None
    identification: str | None = Field(default=None, min_length=1, max_length=30)
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name_1: str | None = Field(default=None, min_length=1, max_length=40)
    last_name_2: str | None = Field(default=None, max_length=40)
    insured_number: str | None = Field(default=None, max_length=25)
    birth_date: date | None = None
    gender: str | None = None
    marital_status: str | None = None
    nationality: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    is_pensioner: bool | None = None
    iban: str | None = Field(default=None, max_length=34)
    hired_on: date | None = None
    dependent_children: int | None = None
    spouse_credit: bool | None = None
    user_id: int | None = None


class EmployeeOut(BaseModel):
    id: int
    user_id: int | None = None
    identification_type: str
    identification: str
    first_name: str
    last_name_1: str
    last_name_2: str | None = None
    insured_number: str | None = None
    birth_date: date
    gender: str
    marital_status: str
    nationality: str
    phone: str | None = None
    email: str | None = None
    is_pensioner: bool
    iban: str | None = None
    hired_on: date
    terminated_on: date | None = None
    termination_cause: str | None = None
    dependent_children: int
    spouse_credit: bool
    is_active: bool
    #: El contrato vigente, o el último si ya salió. Nulo si nunca tuvo.
    contract: ContractOut | None = None


class TerminationIn(BaseModel):
    terminated_on: date
    #: Una de las cinco causas de RN-71.
    cause: str


class TerminatedOut(BaseModel):
    employee: EmployeeOut
    #: La liquidación, en borrador (RF-61).
    settlement_run_id: int


class ContractIn(BaseModel):
    employee_id: int
    schedule_id: int
    position_id: int
    ins_policy_id: int | None = None
    valid_from: date
    period_salary: Decimal
    solidarista_rate: Decimal | None = None


# -------------------------------------------- acciones de personal (T-1218)


class ActionIn(BaseModel):
    """Una acción (RN-90). Qué campos lleva depende del tipo, y lo dice el dominio."""

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
    memo: str | None = Field(default=None, max_length=160)


class ActionUpdate(BaseModel):
    """Lo editable de una acción que nadie aplicó. Ni el empleado ni el tipo."""

    starts_on: date
    ends_on: date | None = None
    hours: Decimal | None = None
    days: Decimal | None = None
    amount: Decimal | None = None
    total_amount: Decimal | None = None
    is_recurring: bool = False
    memo: str | None = Field(default=None, max_length=160)


class CancelIn(BaseModel):
    memo: str | None = Field(default=None, max_length=160)


class SuspendIn(BaseModel):
    reason: str = Field(min_length=3, max_length=160)


class AppliedOut(BaseModel):
    """Lo que una corrida aprobada o pagada aplicó de la acción, con sus fechas."""

    run_id: int
    run_status: str
    period_from: date
    period_to: date
    concept: str
    payer: str
    amount: float
    quantity: float | None = None
    applied_from: date | None = None
    applied_to: date | None = None


class ActionOut(BaseModel):
    id: int
    employee_id: int
    kind: str
    starts_on: date
    ends_on: date | None = None
    hours: float | None = None
    days: float | None = None
    amount: float | None = None
    total_amount: float | None = None
    new_salary: float | None = None
    position_id: int | None = None
    is_recurring: bool
    memo: str | None = None
    cancels_action_id: int | None = None
    #: La anulación que la dejó sin efecto, si hay (RN-91).
    cancelled_by: int | None = None
    suspended_at: datetime | None = None
    suspended_by: int | None = None
    suspension_reason: str | None = None
    source: str
    created_by: int
    created_at: datetime
    applied: list[AppliedOut]
    #: Lo aplicado en corridas aprobadas o pagadas. El saldo es lo pactado menos
    #: esto, nunca una columna (RN-92); nulo si no hay tope.
    applied_total: float
    balance: float | None = None


# --------------------------------------------------------- corridas (T-1206)


class RunIn(BaseModel):
    schedule_id: int
    #: Un corte de la jornada; el periodo sale de él (RN-94).
    cut_date: date
    pay_date: date | None = None


class AguinaldoIn(BaseModel):
    """La corrida de aguinaldo de un año (RF-59): del 1 de diciembre anterior al
    30 de noviembre. Sin fecha de pago, el 20 de diciembre (Ley 2412)."""

    year: int = Field(ge=2000, le=2100)
    pay_date: date | None = None


class ItemOut(BaseModel):
    """Un rubro congelado: base, tasa y monto (RN-66)."""

    concept: str
    #: 'earning' | 'employee' | 'employer'.
    payer: str
    base: float
    rate: float | None = None
    amount: float
    action_id: int | None = None
    quantity: float | None = None
    applied_from: date | None = None
    applied_to: date | None = None


class LineOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    contract_id: int
    gross: float
    employee_deductions: float
    income_tax: float
    other_deductions: float
    net: float
    employer_charges: float
    items: list[ItemOut]


class RunOut(BaseModel):
    id: int
    #: 'regular' | 'aguinaldo' | 'settlement' | 'adjustment'.
    kind: str
    schedule_id: int | None = None
    schedule_name: str | None = None
    period_from: date
    period_to: date
    pay_date: date
    #: 'draft' | 'approved' | 'paid' (RN-68).
    status: str
    #: La pagada que este ajuste corrige (RF-63).
    adjusts_run_id: int | None = None
    journal_entry_id: int | None = None
    employees: int
    gross: float
    net: float
    employer_charges: float
    created_at: datetime
    approved_at: datetime | None = None
    paid_at: datetime | None = None


class RunDetailOut(RunOut):
    lines: list[LineOut]


# ------------------------------------------------------- vacaciones (T-1209)


class VacationMovementOut(BaseModel):
    id: int
    #: 'opening' | 'accrual' | 'taken' | 'paid'.
    kind: str
    #: Con signo: lo acumulado suma y lo disfrutado resta; una anulación de
    #: vacaciones es un disfrute negativo.
    days: float
    on_date: date
    run_id: int | None = None
    action_id: int | None = None


class VacationsOut(BaseModel):
    """El saldo de un empleado y de dónde sale (RF-60, RN-70)."""

    employee_id: int
    balance: float
    movements: list[VacationMovementOut]


# ----------------------------------------------------------- boleta (T-1207)


class PayslipRunOut(BaseModel):
    id: int
    kind: str
    period_from: date
    period_to: date
    pay_date: date
    status: str
    paid_at: datetime | None = None
    adjusts_run_id: int | None = None


class PayslipEmployeeOut(BaseModel):
    id: int
    first_name: str
    last_name_1: str
    last_name_2: str | None = None
    identification_type: str
    identification: str
    insured_number: str | None = None
    hired_on: date
    terminated_on: date | None = None
    iban: str | None = None
    position_name: str | None = None
    schedule_name: str | None = None
    frequency: str | None = None
    period_salary: float | None = None


class PayslipLineOut(BaseModel):
    gross: float
    employee_deductions: float
    income_tax: float
    other_deductions: float
    net: float
    employer_charges: float


class PayslipItemOut(ItemOut):
    #: De qué acción salió el rubro, para rotularlo (RN-90).
    action_kind: str | None = None
    action_memo: str | None = None


class PayslipOut(BaseModel):
    """La boleta de un empleado en una corrida, armada de los rubros congelados
    (RF-58, RN-66). La plantilla la imprime en el idioma del documento."""

    run: PayslipRunOut
    employer_number: str | None = None
    employee: PayslipEmployeeOut
    line: PayslipLineOut
    items: list[PayslipItemOut]


# ------------------------------------------------------- importación (T-1220)


class ImportPositionIn(BaseModel):
    row: int
    name: str
    ccss_code: str
    ins_code: str


class ImportEmployeeIn(BaseModel):
    """Un empleado con su contrato, con la jornada, el puesto y la póliza **por
    nombre**: es lo que trae quien viene de otro sistema."""

    row: int
    identification_type: str
    identification: str
    first_name: str
    last_name_1: str
    last_name_2: str | None = None
    insured_number: str | None = None
    birth_date: date
    gender: str
    marital_status: str
    nationality: str = "CR"
    phone: str | None = None
    email: str | None = None
    is_pensioner: bool = False
    iban: str | None = None
    hired_on: date
    dependent_children: int = 0
    spouse_credit: bool = False
    schedule: str
    position: str
    policy: str | None = None
    period_salary: Decimal
    solidarista_rate: Decimal | None = None
    contract_from: date | None = None
    #: Los días hábiles de vacaciones a la fecha de la importación.
    vacation_days: Decimal | None = None


class ImportEarningIn(BaseModel):
    row: int
    identification: str
    #: Cualquier día del mes.
    month: date
    gross: Decimal


class ImportDeductionIn(BaseModel):
    row: int
    identification: str
    #: 'deduction' | 'child_support' | 'garnishment'.
    kind: str
    amount: Decimal
    #: Lo que le queda por cobrar (RN-92).
    balance: Decimal | None = None
    starts_on: date
    ends_on: date | None = None
    is_recurring: bool = True
    memo: str | None = Field(default=None, max_length=160)


class ImportIn(BaseModel):
    """Las filas ya leídas del Excel (RF-86, RN-97). `as_of` es la fecha a la que
    están los saldos de apertura."""

    as_of: date
    positions: list[ImportPositionIn] = []
    employees: list[ImportEmployeeIn] = []
    earnings: list[ImportEarningIn] = []
    deductions: list[ImportDeductionIn] = []


class RowErrorOut(BaseModel):
    #: 'positions' | 'employees' | 'earnings' | 'deductions'.
    sheet: str
    row: int
    #: El mismo código que daría el formulario; la pantalla arma la misma frase.
    code: str
    field: str | None = None
    reason: str | None = None


class ImportResultOut(BaseModel):
    dry_run: bool
    ok: bool
    errors: list[RowErrorOut]
    #: Lo que entró, o entraría: puestos nuevos, empleados, meses y deducciones.
    positions: int
    employees: int
    earnings: int
    deductions: int


# ------------------------------------------- los archivos del mes (T-1211, T-1219)


class MovementOut(BaseModel):
    """Un movimiento del mes para la CCSS, con sus fechas (RN-96)."""

    #: 'inclusion' | 'exclusion' | 'sick_leave_sem' | 'sick_leave_ins' |
    #: 'maternity' | 'leave_paid' | 'leave_unpaid' | 'occupation_change'.
    kind: str
    starts_on: date
    ends_on: date | None = None
    #: La causa de la exclusión o el código de la ocupación nueva.
    detail: str | None = None


class CcssRowOut(BaseModel):
    employee_id: int
    #: Como la pide el formulario: la cédula a nueve dígitos, o el asegurado.
    identification: str
    insured_number: str | None = None
    full_name: str
    ccss_code: str
    #: 'diurna' | 'parcial' | 'mixta' | 'nocturna'.
    shift: str
    #: Lo que cotiza en el mes.
    salary: float
    days: float
    movements: list[MovementOut]


class CcssReportOut(BaseModel):
    """El informe del mes para la CCSS (RF-62): lo que se teclea en Autogestión."""

    employer_number: str
    period_from: date
    period_to: date
    total_salary: float
    rows: list[CcssRowOut]


class IncomeTaxRowOut(BaseModel):
    employee_id: int
    identification: str
    full_name: str
    taxable: float
    withheld: float


class IncomeTaxReportOut(BaseModel):
    """La renta retenida del mes, insumo de la declaración (RF-62, RN-73)."""

    period_from: date
    period_to: date
    total_taxable: float
    total_withheld: float
    rows: list[IncomeTaxRowOut]
