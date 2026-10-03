"""Acciones de personal: qué pide cada una y qué le hace a la boleta (T-1216).

Una acción vive en el empleado y no en la corrida (RN-90). La corrida pregunta
dos cosas: **qué tramo** de cada acción le toca —`portions`, que reparte una
incapacidad larga entre los periodos que cruza— y **qué rubros** deja ese tramo
—`action_items`—. Las deducciones se piden aparte (`deduction_due`) porque no
dependen de fechas sino de que sigan vigentes y les quede saldo (RN-92), y se
aplican al final, en orden y sin dejar el neto negativo (RN-93).

El mes comercial
----------------
En mensual y quincenal el mes paga treinta días, tenga los que tenga (decreto
de salarios mínimos, art. 7). Una ausencia se cuenta igual: si el tramo llega
al último día de un mes de 31, ese día no se cuenta; si llega al de un febrero
de 28, se cuentan dos más. Así una segunda quincena entera son quince días en
enero y en febrero, y ninguna ausencia rebaja más que el salario del periodo
(RN-94).

Qué cotiza y qué paga renta
---------------------------
Lo que se recibe durante una incapacidad **es un subsidio y no un salario**:
no lleva cargas sociales, ni renta, ni otros rebajos, y no cuenta para el
aguinaldo. Lo dice el MTSS en el criterio DAJ-AE-201-12, con la Sala Segunda
(votos 476-2004 y 622-2010), y vale también para los primeros tres días que
paga el patrono. La licencia de maternidad es la excepción: el art. 95 manda
cotizar sobre la **totalidad** del salario durante la licencia, así que ni el
rebajo ni la mitad que paga el patrono tocan la base de la CCSS.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from .errors import InvalidAction
from .money import Money
from .payroll import EARNING, PayItem, RateSet
from .payroll_calendar import (
    MONTHLY,
    MONTHLY_FACTOR,
    SEMIMONTHLY,
    Period,
    Schedule,
    cut_on_or_after,
    day_value,
    hour_value,
    monthly_equivalent,
    paid_days,
    period_for,
)

OVERTIME = "overtime"
DOUBLE_TIME = "double_time"
BONUS = "bonus"
SICK_LEAVE_CCSS = "sick_leave_ccss"
SICK_LEAVE_INS = "sick_leave_ins"
MATERNITY = "maternity"
PAID_LEAVE = "paid_leave"
UNPAID_LEAVE = "unpaid_leave"
ABSENCE = "absence"
VACATION = "vacation"
DEDUCTION = "deduction"
CHILD_SUPPORT = "child_support"
GARNISHMENT = "garnishment"
RAISE = "raise"
POSITION_CHANGE = "position_change"
TERMINATION = "termination"

#: Los dieciséis de RN-90. La lista es cerrada: cada tipo tiene su efecto en el
#: cálculo y en los archivos de la CCSS y del INS.
ACTION_KINDS: tuple[str, ...] = (
    OVERTIME,
    DOUBLE_TIME,
    BONUS,
    SICK_LEAVE_CCSS,
    SICK_LEAVE_INS,
    MATERNITY,
    PAID_LEAVE,
    UNPAID_LEAVE,
    ABSENCE,
    VACATION,
    DEDUCTION,
    CHILD_SUPPORT,
    GARNISHMENT,
    RAISE,
    POSITION_CHANGE,
    TERMINATION,
)

#: Las que pasan en un día: se aplican enteras en el periodo que lo contiene.
SINGLE_DAY_KINDS = frozenset({OVERTIME, DOUBLE_TIME, BONUS, RAISE, POSITION_CHANGE, TERMINATION})
#: Las que ocupan un rango de fechas: se reparten entre los periodos que cruzan.
RANGE_KINDS = frozenset({SICK_LEAVE_CCSS, SICK_LEAVE_INS, MATERNITY, PAID_LEAVE, UNPAID_LEAVE, ABSENCE, VACATION})
#: Las que se descuentan del neto, en este orden (RN-93).
DEDUCTION_ORDER: tuple[str, ...] = (CHILD_SUPPORT, GARNISHMENT, DEDUCTION)

#: Tiempo y medio (art. 139) y doble (arts. 148–149, feriado o descanso trabajado).
OVERTIME_FACTOR = Decimal("1.5")
DOUBLE_TIME_FACTOR = Decimal(2)

#: El rubro que deja cada ausencia en la boleta, y el que paga el patrono
#: mientras dura. Los tres pares de parámetros son reglas con vigencia (RN-67).
SUBSIDIES: dict[str, tuple[str, str, str]] = {
    # (rubro del patrono, días que paga, porcentaje que paga)
    SICK_LEAVE_CCSS: ("sick_leave_subsidy", "sick_leave_employer_days", "sick_leave_employer_rate"),
    SICK_LEAVE_INS: ("ins_subsidy", "ins_employer_days", "ins_employer_rate"),
}
MATERNITY_PAY = "maternity_pay"
MATERNITY_RATE = "maternity_employer_rate"

#: Lo que cotiza a la CCSS. El subsidio de una incapacidad no es salario, y la
#: maternidad cotiza sobre el salario entero (art. 95): ni su rebajo ni lo que
#: paga el patrono mueven la base.
CONTRIBUTORY = frozenset({"base", OVERTIME, DOUBLE_TIME, BONUS, SICK_LEAVE_CCSS, SICK_LEAVE_INS, UNPAID_LEAVE, ABSENCE})
#: Lo que paga renta: lo que cotiza y, en la maternidad, lo que de verdad paga el
#: patrono —la mitad de la CCSS no pasa por la planilla—.
TAXABLE = CONTRIBUTORY | {MATERNITY, MATERNITY_PAY}

#: Lo que pide cada tipo, además de su fecha de inicio.
_NEEDS: dict[str, tuple[str, ...]] = {
    OVERTIME: ("hours",),
    DOUBLE_TIME: ("hours",),
    BONUS: ("amount",),
    VACATION: ("ends_on", "days"),
    DEDUCTION: ("amount",),
    CHILD_SUPPORT: ("amount",),
    GARNISHMENT: ("total_amount",),
    RAISE: ("new_salary",),
    POSITION_CHANGE: ("position_id",),
}


@dataclass(frozen=True)
class Action:
    """Una fila de `personnel_actions`, con lo que el cálculo necesita."""

    kind: str
    starts_on: date
    ends_on: date | None = None
    hours: Decimal | None = None
    days: Decimal | None = None
    amount: Money | None = None
    total_amount: Money | None = None
    new_salary: Money | None = None
    position_id: int | None = None
    is_recurring: bool = False
    #: Desde qué día deja de aplicarse una recurrente suspendida.
    suspended_on: date | None = None
    id: int | None = None


def check_action(action: Action) -> None:
    """Lanza `InvalidAction` si a la acción le falta o le sobra algo."""
    if action.kind not in ACTION_KINDS:
        raise InvalidAction("kind", "unknown", action.kind)

    pide = _NEEDS.get(action.kind, ())
    if action.kind in RANGE_KINDS:
        pide = tuple(dict.fromkeys(("ends_on",) + pide))
    for campo in pide:
        if getattr(action, campo) is None:
            raise InvalidAction(campo, "required")

    for campo in ("hours", "days", "amount", "total_amount", "new_salary"):
        valor = getattr(action, campo)
        numero = valor.amount if isinstance(valor, Money) else valor
        if numero is not None and numero <= 0:
            raise InvalidAction(campo, "not_positive", numero)

    if action.kind in SINGLE_DAY_KINDS and action.ends_on not in (None, action.starts_on):
        raise InvalidAction("ends_on", "single_day", action.ends_on)
    if action.ends_on is not None and action.ends_on < action.starts_on:
        raise InvalidAction("ends_on", "before_start", action.ends_on)
    if action.kind == VACATION:
        assert action.ends_on is not None and action.days is not None
        if action.days > (action.ends_on - action.starts_on).days + 1:
            raise InvalidAction("days", "too_many", action.days)
    if action.is_recurring and action.kind not in (DEDUCTION, CHILD_SUPPORT):
        # Un embargo no es recurrente por elección: se aplica hasta agotar su
        # saldo, que es lo que lo define.
        raise InvalidAction("is_recurring", "not_allowed")


# ------------------------------------------------------------- los tramos


@dataclass(frozen=True)
class Portion:
    """El pedazo de una acción que cae en un periodo."""

    applied_from: date
    applied_to: date
    #: Los días que cuenta el tramo, en mes comercial si la jornada lo es.
    days: Decimal
    #: Cuántos días de la acción pasaron antes de este tramo. Los primeros días
    #: de una incapacidad los paga el patrono, y hay que saber si ya pasaron.
    offset: int


def _last_day(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def counted_days(schedule: Schedule, start: date, end: date) -> Decimal:
    """Los días que cuenta un tramo dentro de un solo periodo (RN-94).

    En mensual y quincenal, mes comercial: cada fin de mes que el tramo cruza
    suma o resta lo que le falta o le sobra para treinta. En semanal y
    bisemanal, días de calendario. En los dos casos, nunca más que los días que
    paga el periodo.
    """
    dias = (end - start).days + 1
    if schedule.frequency in (MONTHLY, SEMIMONTHLY):
        dia = start
        while dia <= end:
            fin_de_mes = _last_day(dia)
            if fin_de_mes <= end:
                dias += 30 - fin_de_mes.day
            dia = fin_de_mes + timedelta(days=1)
    return Decimal(max(0, min(dias, paid_days(schedule))))


def portions(action: Action, schedule: Schedule, first_unapplied: date, period: Period) -> tuple[Portion, ...]:
    """Los tramos de la acción que esta corrida tiene que aplicar.

    Desde el primer día que ninguna corrida aplicó hasta el fin del periodo. Si
    la acción cae en un periodo ya pagado —la incapacidad que llegó tarde—, sus
    tramos salen con sus fechas originales, uno por cada periodo que cruza
    (RN-91): la corrida pagada no se toca y esta los recoge.
    """
    if action.kind in SINGLE_DAY_KINDS:
        if first_unapplied <= action.starts_on <= period.ends_on:
            return (Portion(action.starts_on, action.starts_on, Decimal(0), 0),)
        return ()

    assert action.ends_on is not None
    desde = max(action.starts_on, first_unapplied)
    hasta = min(action.ends_on, period.ends_on)
    tramos = []
    while desde <= hasta:
        suyo = period_for(schedule, cut_on_or_after(schedule, desde))
        fin = min(hasta, suyo.ends_on)
        tramos.append(Portion(desde, fin, counted_days(schedule, desde, fin), (desde - action.starts_on).days))
        desde = fin + timedelta(days=1)
    return tuple(tramos)


def _item(action: Action, portion: Portion, concept: str, base: Decimal, rate: Decimal | None, amount: Decimal, quantity: Decimal) -> PayItem:
    return PayItem(
        concept,
        EARNING,
        Money(base),
        rate,
        Money(amount),
        action_id=action.id,
        quantity=quantity,
        applied_from=portion.applied_from,
        applied_to=portion.applied_to,
    )


def action_items(
    action: Action,
    portion: Portion,
    period_salary: Money,
    schedule: Schedule,
    rates: RateSet,
    *,
    extends_previous: bool = False,
) -> tuple[PayItem, ...]:
    """Los rubros que deja un tramo en la boleta.

    Todo tramo aplicado deja al menos un rubro, aunque sea de cero —un permiso
    con goce no cambia el pago—: es lo que dice que esta corrida lo aplicó, y el
    archivo de la CCSS necesita sus fechas.

    `extends_previous` es una incapacidad que prolonga a otra sin interrupción:
    los primeros días que paga el patrono ya se pagaron en la anterior.
    """
    kind = action.kind
    if kind in (OVERTIME, DOUBLE_TIME):
        assert action.hours is not None
        hora = hour_value(period_salary, schedule)
        factor = OVERTIME_FACTOR if kind == OVERTIME else DOUBLE_TIME_FACTOR
        return (_item(action, portion, kind, hora, factor, action.hours * hora * factor, action.hours),)
    if kind == BONUS:
        assert action.amount is not None
        return (_item(action, portion, kind, action.amount.amount, None, action.amount.amount, Decimal(1)),)
    if kind not in RANGE_KINDS:
        # Aumento, cambio de puesto y baja cambian el contrato, no la boleta.
        return ()

    dia = day_value(period_salary, schedule)
    if kind in (PAID_LEAVE, VACATION):
        return (_item(action, portion, kind, dia, None, Decimal(0), portion.days),)

    rubros = [_item(action, portion, kind, dia, None, -portion.days * dia, portion.days)]
    if kind in SUBSIDIES:
        concepto, dias_regla, tasa_regla = SUBSIDIES[kind]
        dias_patrono = Decimal(0) if extends_previous else rates.rule(dias_regla)
        pagados = max(Decimal(0), min(dias_patrono - portion.offset, portion.days))
        if pagados:
            tasa = rates.rule(tasa_regla)
            rubros.append(_item(action, portion, concepto, dia, tasa, pagados * dia * tasa, pagados))
    elif kind == MATERNITY:
        tasa = rates.rule(MATERNITY_RATE)
        rubros.append(_item(action, portion, MATERNITY_PAY, dia, tasa, portion.days * dia * tasa, portion.days))
    return tuple(rubros)


def contribution_base(items: Iterable[PayItem]) -> Money:
    """Lo que cotiza a la CCSS de lo ganado en la corrida. Nunca negativo."""
    base = Money.sum(i.amount for i in items if i.payer == EARNING and i.concept in CONTRIBUTORY)
    return Money.zero() if base.is_negative else base


def taxable_base(items: Iterable[PayItem]) -> Money:
    """Lo que paga renta de lo ganado en la corrida. Nunca negativo."""
    base = Money.sum(i.amount for i in items if i.payer == EARNING and i.concept in TAXABLE)
    return Money.zero() if base.is_negative else base


# ----------------------------------------------------------- deducciones


def remaining_balance(total: Money, applied: Money) -> Money:
    """Lo que le queda a una deducción con tope: lo pactado menos lo aplicado (RN-92)."""
    queda = total - applied
    return Money.zero() if queda.is_negative else queda


def is_active(action: Action, period: Period) -> bool:
    """¿Sigue vigente en este periodo? Empezó, no terminó y no se suspendió antes."""
    if action.starts_on > period.ends_on:
        return False
    if action.ends_on is not None and action.ends_on < period.starts_on:
        return False
    return action.suspended_on is None or action.suspended_on > period.ends_on


def deduction_due(action: Action, period: Period, *, applied: Money, applied_before: bool) -> Money:
    """Cuánto pide una deducción en esta corrida, antes de ver si cabe.

    Una que no es recurrente se aplica una vez. Una recurrente, en cada corrida
    mientras esté vigente y le quede saldo. Cero es «no pide nada».
    """
    if action.kind not in (DEDUCTION, CHILD_SUPPORT):
        raise InvalidAction("kind", "not_allowed", action.kind)
    if not is_active(action, period) or (applied_before and not action.is_recurring):
        return Money.zero()
    assert action.amount is not None
    if action.total_amount is None:
        return action.amount
    return min(action.amount, remaining_balance(action.total_amount, applied))


def garnishment_amount(net_month: Money, unseizable: Money) -> Money:
    """Lo embargable de un salario mensual, art. 172 del Código de Trabajo (RN-93).

    El «salario» del artículo es el líquido, una vez rebajadas las cuotas de ley.
    Es inembargable hasta el menor salario mensual del decreto de salarios
    mínimos; de ahí hasta el triple se embarga un octavo, y del resto un cuarto.

    Es **un tope por salario, no por embargo**: «aunque se tratare de causas
    diferentes, no podrá embargarse respecto a un mismo sueldo sino únicamente
    la parte que fuere embargable». Dos embargos se reparten este monto.
    """
    if net_month <= unseizable:
        return Money.zero()
    triple = unseizable * 3
    if net_month <= triple:
        return (net_month - unseizable) * Decimal("0.125")
    return (triple - unseizable) * Decimal("0.125") + (net_month - triple) * Decimal("0.25")


def garnishment_capacity(net: Money, frequency: str, unseizable: Money) -> Money:
    """Lo embargable en esta corrida: lo del mes, repartido entre sus periodos.

    El art. 172 habla de salario mensual; una quincena lleva la mitad de lo que
    se embargaría al mes, y una semana, doce cincuentaidosavos.
    """
    del_mes = garnishment_amount(monthly_equivalent(net, frequency), unseizable)
    return Money(del_mes.amount / MONTHLY_FACTOR[frequency])


#: «Todo salario será embargable hasta en un cincuenta por ciento como pensión
#: alimenticia» (art. 172).
CHILD_SUPPORT_CAP = Decimal("0.5")


def child_support_capacity(net: Money) -> Money:
    """Lo máximo que las pensiones alimentarias pueden tomar de este neto."""
    return Money.zero() if net.is_negative else net * CHILD_SUPPORT_CAP


def apply_deductions(net: Money, wanted: Sequence[Money]) -> tuple[Money, ...]:
    """Aplica lo pedido, en orden, sin dejar el neto negativo (RN-93).

    Devuelve lo que se aplicó de cada una. La que no cabe entera se aplica en
    parte, y la que viene detrás, en nada: su saldo lo arrastra a la corrida
    siguiente. No se inventa una deuda del empleado.
    """
    disponible = Money.zero() if net.is_negative else net
    aplicado = []
    for pedido in wanted:
        cabe = min(pedido, disponible)
        aplicado.append(cabe)
        disponible = disponible - cabe
    return tuple(aplicado)


def deduction_order(action: Action) -> tuple[int, date, int]:
    """El orden de RN-93, y dentro de cada tipo, la más vieja primero."""
    return (DEDUCTION_ORDER.index(action.kind), action.starts_on, action.id or 0)


# ------------------------------------------------------------ el salario base


def base_item(period_salary: Money, schedule: Schedule, period: Period, active: Period) -> PayItem | None:
    """El salario del periodo: entero si el contrato lo cubre, proporcional si no.

    `active` es el tramo en que el contrato rige **y** la persona está empleada:
    desde el mayor entre el ingreso y el inicio del contrato hasta el menor
    entre la baja y el fin del contrato. Si no toca el periodo no hay rubro;
    si lo cubre entero, el salario sale tal cual, sin pasar por el valor del
    día, para que la quincena sea exactamente la mitad del mes (RN-94). Si lo
    cubre en parte —quien entró el 20 o salió el 10— se pagan los días que
    cuenta el tramo, en mes comercial, al valor del día del decreto.
    """
    desde = max(period.starts_on, active.starts_on)
    hasta = min(period.ends_on, active.ends_on)
    if desde > hasta:
        return None
    if desde == period.starts_on and hasta == period.ends_on:
        return PayItem(
            "base",
            EARNING,
            period_salary,
            None,
            period_salary,
            quantity=Decimal(paid_days(schedule)),
            applied_from=desde,
            applied_to=hasta,
        )
    dias = counted_days(schedule, desde, hasta)
    dia = day_value(period_salary, schedule)
    return PayItem(
        "base",
        EARNING,
        Money(dia),
        None,
        Money(dias * dia),
        quantity=dias,
        applied_from=desde,
        applied_to=hasta,
    )
