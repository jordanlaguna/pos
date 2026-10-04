"""Planilla (T-1201, F12, migración 019).

Quince tablas, de dos clases.

**Cuatro son del país**, no de una compañía: las tasas de la CCSS, los tramos y
los créditos de la renta y la tabla de cesantía (RN-67). No heredan
`TenantMixin`, como `cabys_cache`: son las mismas para todos los patronos, las
siembra la plataforma y las mantiene soporte. Que no lo hereden significa que
sus consultas no llevan filtro automático, y está bien porque no hay dato de
nadie: son normas publicadas, con su fuente.

**Las once restantes son de la compañía.** La planilla es lo más delicado que
guarda el sistema después del libro —salarios, embargos, incapacidades— y no
hay una sola consulta que deba cruzarla con la de otra.

Dos ideas sostienen el modelo:

- **La acción de personal es la fuente** (RN-90). `PersonnelAction` vive en el
  empleado, con sus fechas; la corrida la toma y deja en `PayrollRunItem` el
  tramo que aplicó. Lo que una acción ya aplicó es la suma de sus rubros en
  corridas pagadas: de ahí salen el saldo de un préstamo (RN-92) y las fechas
  de cada incapacidad del archivo de la CCSS.
- **La corrida se congela** (RN-66). Cada rubro guarda su base, su tasa y su
  monto, y la boleta se reimprime de ahí, nunca recalculando.
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin

# ------------------------------------------------------------ del país


class PayrollRate(Base):
    """Una tasa, un número de días o un monto, con su vigencia y su fuente.

    El concepto dice qué es `value`: 0.0550 es un 5,50 % de la CCSS; 3 son los
    días de incapacidad que paga el patrono; y el salario mínimo inembargable de
    RN-93 es un monto. Por eso la columna es (14,4) y no la (9,4) de una tasa.

    Una tasa nueva es una fila con `valid_from`, nunca un UPDATE de la vigente:
    una corrida pagada tiene que poder saber qué regía cuando se calculó.
    """

    __tablename__ = "payroll_rates"

    __table_args__ = (
        UniqueConstraint("country", "concept", "payer", "valid_from", name="uq_payroll_rates"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(CHAR(2), nullable=False)
    concept = Column(String(40), nullable=False)
    #: 'employee' | 'employer' | 'rule'.
    payer = Column(String(8), nullable=False)
    value = Column(Numeric(14, 4), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    #: La norma o la URL de donde salió la cifra.
    source = Column(String(255), nullable=False)
    #: Cuándo alguien la comprobó contra la fuente. Con más de seis meses, la
    #: pantalla avisa (T-1204).
    verified_at = Column(Date, nullable=False)


class IncomeTaxBracket(Base):
    """Un tramo mensual del impuesto al salario (RN-73)."""

    __tablename__ = "income_tax_brackets"

    __table_args__ = (
        UniqueConstraint("country", "valid_from", "lower_bound", name="uq_income_tax_brackets"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(CHAR(2), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    lower_bound = Column(Numeric(12, 2), nullable=False)
    #: NULL en el último tramo, que no tiene techo.
    upper_bound = Column(Numeric(12, 2), nullable=True)
    rate = Column(Numeric(5, 4), nullable=False)
    source = Column(String(255), nullable=False)
    verified_at = Column(Date, nullable=False)


class IncomeTaxCredit(Base):
    """El crédito fiscal mensual por hijo o por cónyuge."""

    __tablename__ = "income_tax_credits"

    __table_args__ = (
        UniqueConstraint("country", "concept", "valid_from", name="uq_income_tax_credits"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(CHAR(2), nullable=False)
    #: 'child' | 'spouse'.
    concept = Column(String(20), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    source = Column(String(255), nullable=False)
    verified_at = Column(Date, nullable=False)


class SeveranceBracket(Base):
    """Días de cesantía por antigüedad (art. 29), con su tope (RN-71)."""

    __tablename__ = "severance_table"

    __table_args__ = (
        UniqueConstraint("country", "valid_from", "years_from", name="uq_severance_table"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(CHAR(2), nullable=False)
    valid_from = Column(Date, nullable=False)
    #: 0.25 son tres meses.
    years_from = Column(Numeric(4, 2), nullable=False)
    years_to = Column(Numeric(4, 2), nullable=True)
    days = Column(Numeric(5, 2), nullable=False)
    source = Column(String(255), nullable=False)


# ------------------------------------------------------- de la compañía


class WorkSchedule(TenantMixin, Base):
    """Una jornada: cómo y cuándo se le paga a un grupo de empleados (RN-94).

    Es de la compañía y no del contrato porque es del grupo: los cajeros
    quincenales cortan todos el mismo día. Una corrida es de una jornada y de un
    corte válido para ella, y el periodo sale del corte.

    De los tres campos de corte se usa uno, según la periodicidad: el día en que
    corta la primera quincena, el día de la semana, o el primer día de la serie
    bisemanal. La mensual corta a fin de mes y no necesita ninguno.
    """

    __tablename__ = "work_schedules"

    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_work_schedules_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    #: 'monthly' | 'semimonthly' (quincenal) | 'biweekly' (bisemanal) | 'weekly'.
    #: Quincenal es *semimonthly* y no *biweekly*: dos veces al mes no es cada
    #: dos semanas, y la diferencia son dos pagos al año.
    frequency = Column(String(12), nullable=False)
    #: 'day' | 'mixed' | 'night' (art. 136).
    shift = Column(String(8), nullable=False)
    hours_per_day = Column(Numeric(4, 2), nullable=False)
    #: Seis o cinco: dos semanas de vacaciones son doce días hábiles o diez
    #: (art. 153).
    workdays_per_week = Column(SmallInteger, nullable=False, default=6, server_default=text("6"))
    #: El día de descanso se paga en los establecimientos comerciales (art. 152).
    rest_day_paid = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    first_cut_day = Column(SmallInteger, nullable=True)
    #: 0 = lunes … 6 = domingo, como `date.weekday()`.
    cut_weekday = Column(SmallInteger, nullable=True)
    series_start = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class Position(TenantMixin, Base):
    """Un puesto, con su código de ocupación de la CCSS y el del INS (RN-95)."""

    __tablename__ = "positions"

    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_positions_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    ccss_code = Column(String(4), nullable=False)
    ins_code = Column(String(5), nullable=False)
    #: Un puesto con empleados no se borra: se desactiva.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class InsPolicy(TenantMixin, Base):
    """Una póliza de riesgos del trabajo del INS, con su prima.

    Tabla y no un dato de la configuración porque una compañía puede tener más de
    una: la tienda y la cuadrilla de construcción pagan primas distintas, y el
    INS recibe un archivo por póliza (RN-96).
    """

    __tablename__ = "ins_policies"

    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_ins_policies_number"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(String(20), nullable=False)
    rt_rate = Column(Numeric(6, 4), nullable=False)
    #: La que toma un contrato que no dice otra.
    is_default = Column(Boolean, nullable=False, default=False, server_default=text("0"))


class Employee(TenantMixin, Base):
    """Un empleado. No es un usuario, aunque puede enlazarse a uno (RN-72).

    Lleva lo que piden los archivos de la CCSS y del INS: el nombre y los dos
    apellidos por separado, el nacimiento, el género, el estado civil, la
    nacionalidad y si es pensionado.

    Un ex empleado no se borra: queda con su fecha y su causa de baja, que es lo
    que la liquidación y la planilla de la CCSS necesitan.
    """

    __tablename__ = "employees"

    __table_args__ = (
        # La misma persona no entra dos veces en la planilla de una compañía; sí
        # puede estar en la de otra.
        UniqueConstraint("company_id", "identification", name="uq_employees_identification"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=True)
    #: 'national' | 'dimex' | 'nite' | 'passport' | 'work_permit'. Palabras y no
    #: códigos: Hacienda, la CCSS y el INS numeran distinto, y cada archivo
    #: traduce a los suyos.
    identification_type = Column(String(12), nullable=False)
    identification = Column(String(30), nullable=False)
    first_name = Column(String(60), nullable=False)
    last_name_1 = Column(String(40), nullable=False)
    #: Hay quien tiene uno solo.
    last_name_2 = Column(String(40), nullable=True)
    #: El número de asegurado de la CCSS. En un nacional, la cédula.
    insured_number = Column(String(25), nullable=True)
    birth_date = Column(Date, nullable=False)
    #: 'F' | 'M'.
    gender = Column(CHAR(1), nullable=False)
    #: 'single' | 'married' | 'divorced' | 'widowed' | 'separated' |
    #: 'free_union' | 'unknown'.
    marital_status = Column(String(10), nullable=False)
    #: ISO 3166, dos letras.
    nationality = Column(CHAR(2), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(120), nullable=True)
    #: Un pensionado cotiza distinto a la CCSS.
    is_pensioner = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    iban = Column(String(34), nullable=True)
    hired_on = Column(Date, nullable=False)
    terminated_on = Column(Date, nullable=True)
    #: 'resignation' | 'dismissal_with_cause' | 'dismissal_without_cause' |
    #: 'mutual' | 'end_of_contract'.
    termination_cause = Column(String(30), nullable=True)
    #: Para el crédito fiscal de la renta.
    dependent_children = Column(SmallInteger, nullable=False, default=0, server_default=text("0"))
    spouse_credit = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class EmploymentContract(TenantMixin, Base):
    """El contrato vigente de un empleado entre dos fechas.

    Un aumento cierra el contrato y abre otro: así una corrida de marzo lee el
    salario de marzo aunque hoy sea otro. El salario es el del periodo de su
    jornada —«₡150 000 por semana»— y el mensual se deriva (RN-94).
    """

    __tablename__ = "employment_contracts"

    __table_args__ = (
        Index("idx_employment_contracts_employee", "employee_id", "valid_from"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("work_schedules.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    #: NULL: la póliza por omisión de la compañía.
    ins_policy_id = Column(Integer, ForeignKey("ins_policies.id"), nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    period_salary = Column(Numeric(12, 2), nullable=False)
    #: El aporte obrero a la asociación solidarista, si hay.
    solidarista_rate = Column(Numeric(5, 4), nullable=True)


class PayrollRun(TenantMixin, Base):
    """Una corrida: un cálculo de planilla para un periodo (RN-66, RN-68).

    El periodo sale del corte de su jornada, y aun así se guarda: la corrida se
    congela, y si mañana cambian los cortes de la jornada la de hoy tiene que
    seguir diciendo qué pagó.
    """

    __tablename__ = "payroll_runs"

    __table_args__ = (Index("idx_payroll_runs_period", "company_id", "period_from", "kind"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    #: 'regular' | 'aguinaldo' | 'settlement' | 'adjustment'.
    kind = Column(String(12), nullable=False)
    #: Las regulares y sus ajustes. El aguinaldo y la liquidación no son de una
    #: jornada.
    schedule_id = Column(Integer, ForeignKey("work_schedules.id"), nullable=True)
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    pay_date = Column(Date, nullable=False)
    #: 'draft' | 'approved' | 'paid' (RN-68). Pagada no se edita.
    status = Column(String(10), nullable=False, default="draft", server_default="draft")
    adjusts_run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=True)
    #: El asiento, si la compañía tiene contabilidad (RN-75).
    journal_entry_id = Column(Integer, nullable=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    paid_by = Column(Integer, nullable=True)
    paid_at = Column(DateTime, nullable=True)


class PayrollRunLine(TenantMixin, Base):
    """Un empleado en una corrida: los totales que suman sus rubros."""

    __tablename__ = "payroll_run_lines"

    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payroll_run_lines"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("employment_contracts.id"), nullable=False)
    gross = Column(Numeric(12, 2), nullable=False)
    employee_deductions = Column(Numeric(12, 2), nullable=False)
    income_tax = Column(Numeric(12, 2), nullable=False)
    #: Pensión alimentaria, embargo, préstamos: lo que no es de la CCSS ni de
    #: Hacienda.
    other_deductions = Column(Numeric(12, 2), nullable=False)
    net = Column(Numeric(12, 2), nullable=False)
    employer_charges = Column(Numeric(12, 2), nullable=False)


class PersonnelAction(TenantMixin, Base):
    """Lo que cambia el pago o la situación de un empleado (RN-90).

    Vive en el empleado, no en la corrida: cada corrida toma las que se cruzan
    con su periodo, y una que cruza dos se parte por el calendario.

    Una acción aplicada en una corrida pagada no se edita ni se borra: se anula
    con otra que la referencia en `cancels_action_id` (RN-91). Una recurrente se
    suspende, con quién, cuándo y por qué (RN-92).

    Qué campos usa depende del tipo: `hours` las extras, `days` las ausencias,
    `amount` la bonificación o la cuota de una deducción, `total_amount` lo
    pactado de un préstamo, `new_salary` el aumento y `position_id` el cambio de
    puesto. El dominio sabe cuáles pide cada uno.
    """

    __tablename__ = "personnel_actions"

    __table_args__ = (Index("idx_personnel_actions_employee", "employee_id", "starts_on"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    #: Uno de los dieciséis de RN-90 (`domain/payroll_actions.ACTION_KINDS`).
    kind = Column(String(20), nullable=False)
    starts_on = Column(Date, nullable=False)
    #: NULL: una recurrente sin fecha final.
    ends_on = Column(Date, nullable=True)
    hours = Column(Numeric(8, 2), nullable=True)
    days = Column(Numeric(6, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    #: Lo pactado (RN-92). NULL: sin tope.
    total_amount = Column(Numeric(12, 2), nullable=True)
    new_salary = Column(Numeric(12, 2), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    is_recurring = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    memo = Column(String(160), nullable=True)
    cancels_action_id = Column(Integer, ForeignKey("personnel_actions.id"), nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    suspended_by = Column(Integer, nullable=True)
    suspension_reason = Column(String(160), nullable=True)
    #: 'manual' | 'import' | 'system' (la baja la registra el sistema).
    source = Column(String(8), nullable=False, default="manual", server_default="manual")
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class PayrollRunItem(TenantMixin, Base):
    """Un rubro de una línea: **esto es el congelamiento** (RN-66).

    Guarda la base, la tasa y el monto, así que la boleta se reimprime leyendo
    esta tabla y nunca recalculando.

    Si el rubro sale de una acción, dice de cuál y qué tramo aplicó. Las fechas
    son las de la acción y no las de la corrida: una retroactiva (RN-91) las trae
    de un periodo ya pagado, y el archivo de la CCSS las pide así.
    """

    __tablename__ = "payroll_run_items"

    __table_args__ = (
        Index("idx_payroll_run_items_line", "line_id"),
        Index("idx_payroll_run_items_action", "action_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("payroll_run_lines.id"), nullable=False)
    concept = Column(String(40), nullable=False)
    #: 'earning' | 'employee' | 'employer'.
    payer = Column(String(8), nullable=False)
    base = Column(Numeric(12, 2), nullable=False)
    #: NULL en los montos fijos: una deducción de ₡20 000 no tiene tasa.
    rate = Column(Numeric(9, 4), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    action_id = Column(Integer, ForeignKey("personnel_actions.id"), nullable=True)
    #: Horas o días de ese tramo.
    quantity = Column(Numeric(8, 2), nullable=True)
    applied_from = Column(Date, nullable=True)
    applied_to = Column(Date, nullable=True)


class VacationMovement(TenantMixin, Base):
    """Un movimiento de vacaciones. El saldo es la suma, nunca una columna (RN-70)."""

    __tablename__ = "vacation_movements"

    __table_args__ = (Index("idx_vacation_movements_employee", "employee_id", "on_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    #: 'accrual' | 'taken' | 'paid' | 'opening'.
    kind = Column(String(10), nullable=False)
    days = Column(Numeric(6, 2), nullable=False)
    on_date = Column(Date, nullable=False)
    run_id = Column(Integer, nullable=True)
    #: El disfrute sale de una acción `vacation`.
    action_id = Column(Integer, nullable=True)


class PayrollOpeningEarning(TenantMixin, Base):
    """Lo devengado antes de VentaSys, un mes por fila (RN-97).

    El aguinaldo suma los meses de su periodo y la liquidación promedia los
    últimos seis: una sola tabla sirve a los dos, y quien migra a mitad de año
    no pierde lo que ya ganó.
    """

    __tablename__ = "payroll_opening_earnings"

    __table_args__ = (
        UniqueConstraint("employee_id", "period_month", name="uq_payroll_opening_earnings"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    #: El primer día del mes.
    period_month = Column(Date, nullable=False)
    gross = Column(Numeric(12, 2), nullable=False)
    imported_by = Column(Integer, nullable=False)
    imported_at = Column(DateTime, nullable=False)
