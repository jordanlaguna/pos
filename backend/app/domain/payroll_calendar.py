"""El calendario de la planilla: jornadas, cortes y periodos (RN-94, T-1202).

Una corrida es de una jornada y de una fecha de corte, y **el periodo sale del
corte**: nadie lo escribe. Así una quincenal que corta el 14 no puede terminar
pagando del 1 al 15 porque alguien tecleó mal el desde.

Las cuatro periodicidades
-------------------------
- **Mensual**: corta el último día del mes.
- **Quincenal** (*semimonthly*): corta el día `first_cut_day` —del 8 al 15— y
  quince días después, o el último del mes si se pasa. Con el 15, corta el 15 y
  a fin de mes; con el 14, el 14 y el 29, y en febrero el 28. Cada periodo
  empieza el día siguiente al corte anterior.
- **Bisemanal** (*biweekly*): cada catorce días desde `series_start`.
- **Semanal**: el día de la semana `cut_weekday` (0 = lunes).

Quincenal y bisemanal no son lo mismo y el inglés lo complica: *biweekly* es
cada dos semanas —veintiséis pagos al año— y la quincena son dos al mes
—veinticuatro—.

Lo que vale un día
------------------
El decreto de salarios mínimos lo dice en su artículo 7 (el 43633-MTSS, y la
regla se repite cada año): el salario semanal paga **seis días**, salvo en los
establecimientos comerciales, que paga **siete** —el día de descanso va pagado,
art. 152 del Código de Trabajo—; la quincena paga quince y el mes treinta,
«indistintamente de la actividad». De ahí `day_value`. El ERP del que viene
VentaSys lo tiene al revés en su tabla de horas; por eso se leyó el decreto.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .errors import InvalidCutDate, InvalidSchedule
from .money import Money

MONTHLY = "monthly"
SEMIMONTHLY = "semimonthly"
BIWEEKLY = "biweekly"
WEEKLY = "weekly"

FREQUENCIES: tuple[str, ...] = (MONTHLY, SEMIMONTHLY, BIWEEKLY, WEEKLY)

#: Las horas ordinarias por día de cada clase (art. 136): diurna 8, mixta 7,
#: nocturna 6. Son el valor por omisión; una jornada de tiempo parcial escribe
#: las suyas.
SHIFT_HOURS: dict[str, Decimal] = {"day": Decimal(8), "mixed": Decimal(7), "night": Decimal(6)}

#: Cuántas veces cabe el periodo en un mes, para pasar de uno a otro. La semana
#: y la bisemana no caben enteras: 52 y 26 al año, entre doce.
MONTHLY_FACTOR: dict[str, Decimal] = {
    MONTHLY: Decimal(1),
    SEMIMONTHLY: Decimal(2),
    BIWEEKLY: Decimal(26) / Decimal(12),
    WEEKLY: Decimal(52) / Decimal(12),
}

#: Del 8 al 15: la segunda quincena tiene que caber en el mismo mes. Es el rango
#: que traen los sistemas del país y el ERP de origen.
FIRST_CUT_DAYS = range(8, 16)

#: Una jornada acumulativa llega a diez horas (art. 136); doce es el techo con
#: el que nadie puede equivocarse de buena fe.
MAX_HOURS_PER_DAY = Decimal(12)


@dataclass(frozen=True)
class Schedule:
    """Una jornada, tal como la guarda `work_schedules`."""

    frequency: str
    shift: str
    hours_per_day: Decimal
    rest_day_paid: bool = True
    workdays_per_week: int = 6
    first_cut_day: int | None = None
    cut_weekday: int | None = None
    series_start: date | None = None


@dataclass(frozen=True)
class Period:
    """Del primer al último día, los dos incluidos."""

    starts_on: date
    ends_on: date

    def __contains__(self, day: date) -> bool:
        return self.starts_on <= day <= self.ends_on


def check_schedule(schedule: Schedule) -> None:
    """Lanza `InvalidSchedule` si a la jornada le falta o le sobra algo.

    Cada periodicidad pide su dato de corte, y solo ese: una semanal con día de
    corte de quincena es un formulario mal llenado, y adivinar cuál de los dos
    quiso decir es inventar el periodo.
    """
    if schedule.frequency not in FREQUENCIES:
        raise InvalidSchedule("frequency", "unknown", schedule.frequency)
    if schedule.shift not in SHIFT_HOURS:
        raise InvalidSchedule("shift", "unknown", schedule.shift)
    if not Decimal(0) < schedule.hours_per_day <= MAX_HOURS_PER_DAY:
        raise InvalidSchedule("hours_per_day", "out_of_range", schedule.hours_per_day)
    # Siete no: el día de descanso es un derecho (art. 152), no una opción.
    if schedule.workdays_per_week not in range(1, 7):
        raise InvalidSchedule("workdays_per_week", "out_of_range", schedule.workdays_per_week)

    pide = {
        MONTHLY: None,
        SEMIMONTHLY: "first_cut_day",
        BIWEEKLY: "series_start",
        WEEKLY: "cut_weekday",
    }[schedule.frequency]
    for campo in ("first_cut_day", "cut_weekday", "series_start"):
        valor = getattr(schedule, campo)
        if campo == pide and valor is None:
            raise InvalidSchedule(campo, "required")
        if campo != pide and valor is not None:
            raise InvalidSchedule(campo, "unexpected", valor)

    if schedule.first_cut_day is not None and schedule.first_cut_day not in FIRST_CUT_DAYS:
        raise InvalidSchedule("first_cut_day", "out_of_range", schedule.first_cut_day)
    if schedule.cut_weekday is not None and schedule.cut_weekday not in range(7):
        raise InvalidSchedule("cut_weekday", "out_of_range", schedule.cut_weekday)


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _semimonthly_cuts(first_cut_day: int, year: int, month: int) -> tuple[date, date]:
    """Los dos cortes quincenales de un mes."""
    fin = _last_day(year, month)
    primero = date(year, month, first_cut_day)
    # Con el 15, la segunda corta a fin de mes; con otro día, quince después,
    # sin pasarse del mes: el 14 da el 29, y en febrero el 28.
    if first_cut_day == 15:
        return primero, fin
    return primero, date(year, month, min(first_cut_day + 15, fin.day))


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def period_for(schedule: Schedule, cut: date) -> Period:
    """El periodo que cierra `cut`, o `InvalidCutDate` si no es un corte."""
    if schedule.frequency == MONTHLY:
        if cut != _last_day(cut.year, cut.month):
            raise InvalidCutDate(cut, schedule.frequency)
        return Period(cut.replace(day=1), cut)

    if schedule.frequency == SEMIMONTHLY:
        assert schedule.first_cut_day is not None
        primero, segundo = _semimonthly_cuts(schedule.first_cut_day, cut.year, cut.month)
        if cut == segundo:
            return Period(primero + timedelta(days=1), cut)
        if cut == primero:
            anterior = _semimonthly_cuts(schedule.first_cut_day, *_previous_month(cut.year, cut.month))[1]
            return Period(anterior + timedelta(days=1), cut)
        raise InvalidCutDate(cut, schedule.frequency)

    if schedule.frequency == BIWEEKLY:
        assert schedule.series_start is not None
        dias = (cut - schedule.series_start).days
        if dias < 13 or dias % 14 != 13:
            raise InvalidCutDate(cut, schedule.frequency)
        return Period(cut - timedelta(days=13), cut)

    if cut.weekday() != schedule.cut_weekday:
        raise InvalidCutDate(cut, schedule.frequency)
    return Period(cut - timedelta(days=6), cut)


def next_cut(schedule: Schedule, cut: date) -> date:
    """El corte que sigue a `cut`, que ya tiene que ser uno."""
    return cut_on_or_after(schedule, period_for(schedule, cut).ends_on + timedelta(days=1))


def cut_on_or_after(schedule: Schedule, day: date) -> date:
    """El corte del periodo que contiene `day`.

    Es lo que permite repartir una acción larga entre los periodos que cruza,
    incluidos los de antes de la corrida en curso (RN-91).
    """
    if schedule.frequency == MONTHLY:
        return _last_day(day.year, day.month)
    if schedule.frequency == SEMIMONTHLY:
        assert schedule.first_cut_day is not None
        mes = (day.year, day.month)
        candidatos = _semimonthly_cuts(schedule.first_cut_day, *mes) + _semimonthly_cuts(
            schedule.first_cut_day, *_next_month(*mes)
        )
        return next(corte for corte in candidatos if corte >= day)
    if schedule.frequency == BIWEEKLY:
        assert schedule.series_start is not None
        # `//` redondea hacia abajo también con negativos: un día anterior a la
        # serie cae en la bisemana que la precede.
        return schedule.series_start + timedelta(days=14 * ((day - schedule.series_start).days // 14) + 13)
    assert schedule.cut_weekday is not None
    return day + timedelta(days=(schedule.cut_weekday - day.weekday()) % 7)


def closes_month(schedule: Schedule, cut: date) -> bool:
    """¿Es la última corrida del mes? La que liquida la renta (RN-73).

    Una corrida pertenece al mes de su corte, y es la última si el corte
    siguiente ya cae en otro mes.
    """
    siguiente = next_cut(schedule, cut)
    return (siguiente.year, siguiente.month) != (cut.year, cut.month)


def monthly_equivalent(amount: Money, frequency: str) -> Money:
    """Lo que el monto de un periodo vale en un mes: × 1, × 2, × 26/12, × 52/12.

    Sirve para el salario del contrato —que es el del periodo— y para proyectar
    la renta de una corrida que no cierra el mes.
    """
    return amount * MONTHLY_FACTOR[frequency]


def paid_days(schedule: Schedule) -> int:
    """Cuántos días paga el salario de un periodo (decreto de salarios, art. 7)."""
    if schedule.frequency == MONTHLY:
        return 30
    if schedule.frequency == SEMIMONTHLY:
        return 15
    por_semana = 7 if schedule.rest_day_paid else 6
    return por_semana * (2 if schedule.frequency == BIWEEKLY else 1)


def day_value(period_salary: Money, schedule: Schedule) -> Decimal:
    """Lo que vale un día. **Sin redondear**: se redondea el rubro, no la tarifa.

    Redondear el valor del día y después multiplicarlo por los días de una
    incapacidad larga acumula céntimos que nadie ganó.
    """
    return period_salary.amount / paid_days(schedule)


def hour_value(period_salary: Money, schedule: Schedule) -> Decimal:
    """Lo que vale una hora ordinaria: el día entre las horas de la jornada.

    Con un mensual de 600 000 en diurna da 2 500 (÷ 240); en mixta, ÷ 210; en
    nocturna, ÷ 180.
    """
    return day_value(period_salary, schedule) / schedule.hours_per_day
