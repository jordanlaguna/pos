"""Aguinaldo, vacaciones y liquidación (RN-69, RN-70, RN-71, T-1203).

Lo que se le debe al empleado además del salario. Las tres cosas se calculan
sobre lo **devengado** —corridas pagadas y, si la compañía viene de otro
sistema, sus saldos de apertura (RN-97)—, y por eso reciben montos y no
corridas: de dónde salen es asunto del caso de uso.

Las fuentes
-----------
- Aguinaldo: Ley 2412. Lo devengado del 1 de diciembre al 30 de noviembre,
  entre doce. Sin cargas ni renta.
- Vacaciones: art. 153 del Código de Trabajo. Dos semanas por cada cincuenta
  de trabajo continuo —doce días hábiles en semana de seis, diez en semana de
  cinco— y, si el contrato termina antes, **al menos un día por mes**.
- Preaviso: art. 28. Una semana después de tres meses, quince días después de
  seis, un mes después de un año.
- Cesantía: art. 29, con la tabla de días por año que se siembra con su
  vigencia (`severance_table`), y **nunca más de los últimos ocho años**.
- La base de las dos: art. 30, el promedio de los últimos seis meses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

from .money import Money
from .payroll import EARNING, PayItem
from .payroll_actions import TAXABLE
from .payroll_calendar import Period

RESIGNATION = "resignation"
DISMISSAL_WITH_CAUSE = "dismissal_with_cause"
DISMISSAL_WITHOUT_CAUSE = "dismissal_without_cause"
MUTUAL = "mutual"
END_OF_CONTRACT = "end_of_contract"

TERMINATION_CAUSES: tuple[str, ...] = (
    RESIGNATION,
    DISMISSAL_WITH_CAUSE,
    DISMISSAL_WITHOUT_CAUSE,
    MUTUAL,
    END_OF_CONTRACT,
)

#: Las causas por las que la ley debe preaviso y cesantía. Las demás cobran solo
#: los proporcionales (RN-71).
OWES_NOTICE_AND_SEVERANCE = frozenset({DISMISSAL_WITHOUT_CAUSE})

#: Cesantía: nunca más que los últimos ocho años (art. 29).
SEVERANCE_CAP_YEARS = Decimal(8)

#: Vacaciones: dos semanas por cada cincuenta (art. 153).
VACATION_WEEKS = Decimal(2)
VACATION_CYCLE_DAYS = Decimal(350)

DAYS_IN_MONTH = Decimal(30)

#: Los rubros que dejan el aguinaldo y la liquidación. Son devengos sin cargas
#: ni renta: el aguinaldo está exento (Ley 2412) y el preaviso y la cesantía son
#: indemnizaciones, no salario.
AGUINALDO = "aguinaldo"
NOTICE = "notice"
SEVERANCE = "severance"
VACATION_PAYOUT = "vacation_payout"

#: Lo que cuenta como **salario devengado** para el aguinaldo y para el promedio
#: de la liquidación: lo mismo que paga renta. El subsidio de una incapacidad
#: no es salario (MTSS, DAJ-AE-201-12) y por eso no entra; la ausencia sin goce
#: entra en negativo porque rebaja lo ganado.
EARNED_CONCEPTS = TAXABLE

#: Los movimientos de vacaciones (RN-70). El saldo es su suma con signo: lo de
#: apertura y lo acumulado suman; lo disfrutado y lo pagado restan.
VACATION_OPENING = "opening"
VACATION_ACCRUAL = "accrual"
VACATION_TAKEN = "taken"
VACATION_PAID = "paid"
VACATION_KINDS: tuple[str, ...] = (VACATION_OPENING, VACATION_ACCRUAL, VACATION_TAKEN, VACATION_PAID)
_VACATION_SIGN = {VACATION_OPENING: 1, VACATION_ACCRUAL: 1, VACATION_TAKEN: -1, VACATION_PAID: -1}


def aguinaldo_period(year: int) -> Period:
    """Del 1 de diciembre del año anterior al 30 de noviembre."""
    return Period(date(year - 1, 12, 1), date(year, 11, 30))


def aguinaldo(earned: Iterable[Money]) -> Money:
    """Lo devengado en el periodo, entre doce (RN-69).

    `earned` son los montos que cuentan —lo ganado en cada corrida pagada y
    cada mes de apertura—; sumarlos aparte o juntos da lo mismo, y es lo que
    permite que quien migró a mitad de año cobre su aguinaldo entero.
    """
    return Money(Money.sum(earned).amount / 12)


def aguinaldo_item(amount: Money, *, earned: Money | None = None) -> PayItem:
    """El único rubro de una corrida de aguinaldo: sin CCSS y sin renta.

    La base es lo devengado que lo respalda (RF-59), para que la boleta diga de
    dónde salió; si no se da, el monto mismo.
    """
    return PayItem(AGUINALDO, EARNING, amount if earned is None else earned, None, amount)


def aguinaldo_period_containing(day: date) -> Period:
    """El periodo de aguinaldo en que cae un día: el que cierra el 30 de noviembre
    siguiente. Un día de diciembre ya es del aguinaldo del año que viene."""
    return aguinaldo_period(day.year + 1 if day.month == 12 else day.year)


def month_of(day: date) -> date:
    """El primer día del mes de una fecha, que es como se guarda un mes de apertura."""
    return day.replace(day=1)


def _previous_month(first_day: date) -> date:
    return (first_day - timedelta(days=1)).replace(day=1)


def average_window(terminated_on: date) -> Period:
    """Los seis meses calendario **anteriores** al de la salida (art. 30).

    El mes de la salida no entra: está incompleto, y promediarlo rebajaría la
    liquidación de quien se fue el día cinco.
    """
    primero = month_of(terminated_on)
    desde = primero
    for _ in range(6):
        desde = _previous_month(desde)
    return Period(desde, primero - timedelta(days=1))


def by_month(earned: Iterable[tuple[date, Money]]) -> list[Money]:
    """Lo devengado agrupado por mes calendario, del más viejo al más nuevo.

    Recibe pares `(fecha, monto)` —el corte de una corrida pagada o el mes de
    apertura— y devuelve un monto por mes **con algo**: un mes sin corridas no
    es un mes de cero, es un mes que no cuenta (`average_salary` promedia los
    que haya).
    """
    meses: dict[date, Money] = {}
    for dia, monto in earned:
        mes = month_of(dia)
        meses[mes] = meses.get(mes, Money.zero()) + monto
    return [meses[m] for m in sorted(meses)]


def calendar_days(start: date, end: date) -> int:
    """Los días de calendario entre dos fechas, las dos incluidas."""
    return max(0, (end - start).days + 1)


def vacation_balance(movements: Iterable[tuple[str, Decimal]]) -> Decimal:
    """El saldo de vacaciones: la suma de los movimientos con su signo (RN-70).

    Nunca es una columna: lo de apertura y lo acumulado suman, lo disfrutado y
    lo pagado restan. Un tipo que no existe revienta, porque sería un movimiento
    que nadie sabe si suma o resta.
    """
    saldo = Decimal(0)
    for kind, days in movements:
        saldo += _VACATION_SIGN[kind] * Decimal(days)
    return saldo


def settlement_vacation_days(hired_on: date, terminated_on: date, *, earned: Decimal, used: Decimal) -> Decimal:
    """Los días que se liquidan al salir: lo ganado menos lo disfrutado o pagado.

    Si la persona no llegó a las cincuenta semanas, lo ganado tiene el piso de
    un día por mes del art. 153 (`proportional_vacation`); después del primer
    ciclo lo acumulado ya lo supera y el piso no aplica, porque se contaría
    toda la antigüedad y no lo que queda. Nunca negativo.
    """
    ganados = earned
    if calendar_days(hired_on, terminated_on) < VACATION_CYCLE_DAYS:
        ganados = proportional_vacation(hired_on, terminated_on, earned)
    quedan = ganados - used
    return max(Decimal(0), quedan).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def vacation_accrual(days_worked: int, workdays_per_week: int = 6) -> Decimal:
    """Los días hábiles ganados por los días trabajados (art. 153).

    350 días —cincuenta semanas— dan dos semanas: doce días hábiles en una
    semana de seis y diez en una de cinco. Proporcional, a dos decimales.
    """
    ganados = Decimal(days_worked) * VACATION_WEEKS * workdays_per_week / VACATION_CYCLE_DAYS
    return ganados.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def months_between(start: date, end: date) -> int:
    """Meses completos trabajados, contando el día de ingreso y el de salida.

    Del 10 de enero al 9 de abril son tres meses —el 9 de abril se completa el
    tercero— y del 1 de enero al 30 de abril, cuatro. Se cuenta hasta el día
    siguiente a la salida, que es cuando el mes está entero.
    """
    tope = end + timedelta(days=1)
    meses = (tope.year - start.year) * 12 + (tope.month - start.month)
    if tope.day < start.day:
        meses -= 1
    return max(0, meses)


def proportional_vacation(start: date, end: date, earned: Decimal) -> Decimal:
    """Al terminar antes de las cincuenta semanas: lo ganado, o un día por mes
    trabajado si eso es más. Es el mínimo del art. 153, y en una semana de cinco
    días le gana a lo acumulado."""
    return max(earned, Decimal(months_between(start, end)))


def notice_days(months: int) -> int:
    """El preaviso del art. 28, en días de salario."""
    if months < 3:
        return 0
    if months < 6:
        return 7
    if months < 12:
        return 15
    return 30


@dataclass(frozen=True)
class SeveranceBracket:
    """Una fila de la tabla del art. 29.

    Por debajo del año, `days` es el total —siete de tres a seis meses, catorce
    de seis a doce—; desde el año, son días **por año** trabajado.
    """

    years_from: Decimal
    years_to: Decimal | None
    days: Decimal


def severance_years(months: int) -> int:
    """Los años que cuenta la cesantía: «por año laborado o fracción superior a
    seis meses» (art. 29). Dos años y siete meses son tres; dos y seis, dos."""
    anos, resto = divmod(months, 12)
    return anos + (1 if resto > 6 else 0)


def severance_days(months: int, table: Sequence[SeveranceBracket]) -> Decimal:
    """Los días de cesantía por la antigüedad (art. 29), topados a ocho años.

    Menos de tres meses no dan nada; de tres a seis, siete días; de seis a doce,
    catorce. Desde el año, los días por año de la fila que corresponde a los
    años contados, por esos años, y nunca más que ocho.
    """
    if months < 3:
        return Decimal(0)
    if months < 12:
        # De tres a seis meses cae en la fila de 0,25 años; de siete a once, en la de 0,5.
        clave = Decimal("0.25") if months <= 6 else Decimal("0.5")
        return _fila(table, clave).days
    anos = Decimal(severance_years(months))
    return _fila(table, anos).days * min(anos, SEVERANCE_CAP_YEARS)


def _fila(table: Sequence[SeveranceBracket], years: Decimal) -> SeveranceBracket:
    return next(f for f in table if f.years_from <= years and (f.years_to is None or years < f.years_to))


def average_salary(last_months: Sequence[Money]) -> Money:
    """El promedio de los últimos seis meses —o de los que haya— (art. 30).

    Recibe los meses del más viejo al más nuevo, pagados o de apertura, y toma
    los últimos seis.
    """
    meses = list(last_months)[-6:]
    if not meses:
        return Money.zero()
    return Money(Money.sum(meses).amount / len(meses))


@dataclass(frozen=True)
class SettlementInput:
    """Lo que la liquidación necesita saber del empleado."""

    cause: str
    hired_on: date
    terminated_on: date
    #: El promedio mensual de los últimos seis meses.
    average_monthly: Money
    #: Los días hábiles de vacaciones sin disfrutar, ya con el mínimo aplicado.
    vacation_days: Decimal
    #: Lo devengado desde el 1 de diciembre, para el aguinaldo proporcional.
    aguinaldo_earned: Money


def settlement(data: SettlementInput, table: Sequence[SeveranceBracket]) -> tuple[PayItem, ...]:
    """Los rubros de la liquidación según la causa (RN-71).

    Vacaciones y aguinaldo proporcionales, siempre. Preaviso y cesantía, solo
    cuando la ley los debe. El día vale el promedio mensual entre treinta.
    """
    diario = data.average_monthly.amount / DAYS_IN_MONTH
    rubros: list[PayItem] = []

    def rubro(concept: str, dias: Decimal) -> None:
        rubros.append(PayItem(concept, EARNING, Money(diario), None, Money(dias * diario), quantity=dias))

    if data.cause in OWES_NOTICE_AND_SEVERANCE:
        rubro(NOTICE, Decimal(notice_days(months_between(data.hired_on, data.terminated_on))))
        rubro(SEVERANCE, severance_days(months_between(data.hired_on, data.terminated_on), table))
    if data.vacation_days:
        rubro(VACATION_PAYOUT, data.vacation_days)
    rubros.append(aguinaldo_item(aguinaldo([data.aguinaldo_earned]), earned=data.aguinaldo_earned))
    return tuple(rubros)
