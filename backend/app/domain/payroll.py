"""Sueldos, cargas y renta (RN-66, RN-67, RN-73, T-1202).

Nada de acá conoce un porcentaje. Las fórmulas reciben un `RateSet` resuelto a
la fecha de corte y lo aplican; las cifras son filas con vigencia y fuente
(RN-67). Las pruebas usan un juego inventado a propósito: prueban la aritmética,
no una cifra que vence con el próximo decreto.

**Se redondea por rubro.** Cada cargo es base × tasa redondeado a céntimos, y el
total obrero es la suma de rubros ya redondeados. Es lo que imprime la boleta
—un renglón por rubro— y lo que la suma de la boleta tiene que dar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .errors import InvalidPayrollRate, InvalidTaxBrackets, RateNotNewer, RatesMissing
from .money import Money
from .payroll_calendar import MONTHLY_FACTOR, monthly_equivalent

EMPLOYEE = "employee"
EMPLOYER = "employer"
RULE = "rule"
EARNING = "earning"

#: Lo que la CCSS cobra en Costa Rica, por pagador. Es la **estructura** —qué
#: rubros existen— y no las cifras, que se siembran con su fuente (T-1204). Está
#: acá para que falte una fila no pase callado: sin la del IVM, la boleta saldría
#: sin IVM y cobraría de menos sin que nadie lo notara hasta la CCSS.
#:
#: El Banco Popular cobra dos veces al patrono —la cuota patronal y el aporte de
#: la Ley de Protección al Trabajador— y la LPT suma además el FCL, el ROP y un
#: uno por ciento al INS. Con los diez rubros patronales la suma da el 26,83 % que
#: se publicó para 2026; sin el del INS da 25,83, y así se supo que faltaba.
REQUIRED_CONTRIBUTIONS: dict[str, frozenset[tuple[str, str]]] = {
    "CR": frozenset(
        {
            ("sem", EMPLOYEE),
            ("ivm", EMPLOYEE),
            ("banco_popular", EMPLOYEE),
            ("sem", EMPLOYER),
            ("ivm", EMPLOYER),
            ("banco_popular", EMPLOYER),
            ("banco_popular_lpt", EMPLOYER),
            ("asignaciones_familiares", EMPLOYER),
            ("imas", EMPLOYER),
            ("ina", EMPLOYER),
            ("fcl", EMPLOYER),
            ("rop", EMPLOYER),
            ("ins_lpt", EMPLOYER),
        }
    ),
}

#: El aporte al INA no lo paga el patrono no agrícola con menos de cinco
#: trabajadores permanentes. Lo dice la compañía en su configuración de
#: planilla: es un dato de su inscripción, no algo que el sistema pueda deducir
#: contando empleados.
INA_CONCEPT = "ina"

#: El rubro de riesgos del trabajo. Su tasa no es del país sino de la póliza.
RT_CONCEPT = "rt"


@dataclass(frozen=True)
class Rate:
    """Una fila de `payroll_rates`."""

    concept: str
    payer: str
    value: Decimal
    valid_from: date
    valid_to: date | None = None

    def rules_on(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)


@dataclass(frozen=True)
class RateSet:
    """Las tasas que rigen a una fecha, una por (concepto, pagador)."""

    on: date
    rates: tuple[Rate, ...]

    def contributions(self, payer: str) -> tuple[Rate, ...]:
        """Los rubros de un pagador, en orden de concepto para que la boleta no baile."""
        return tuple(sorted((r for r in self.rates if r.payer == payer), key=lambda r: r.concept))

    def rule(self, concept: str) -> Decimal:
        """Un parámetro —días, un monto—, o `RatesMissing` si no hay.

        Se pide cuando hace falta y no al resolver: una corrida sin
        incapacidades no necesita la regla de incapacidades. Las cargas sí se
        exigen todas al resolver (`rates_at`).
        """
        for r in self.rates:
            if r.payer == RULE and r.concept == concept:
                return r.value
        raise RatesMissing((f"{concept}:{RULE}",), self.on)


def rates_at(rates: Iterable[Rate], on: date, country: str = "CR") -> RateSet:
    """Las tasas que rigen el día `on`.

    Una tasa nueva es una fila con `valid_from`, nunca un UPDATE de la vieja, así
    que dos filas del mismo concepto pueden regir a la vez sobre el papel —la
    vieja no tiene `valid_to`—. Gana la de `valid_from` más reciente: es la que
    alguien insertó para reemplazar a la otra.
    """
    vigentes: dict[tuple[str, str], Rate] = {}
    for r in rates:
        if not r.rules_on(on):
            continue
        clave = (r.concept, r.payer)
        if clave not in vigentes or r.valid_from > vigentes[clave].valid_from:
            vigentes[clave] = r
    faltan = REQUIRED_CONTRIBUTIONS[country] - set(vigentes)
    if faltan:
        raise RatesMissing(tuple(sorted(f"{c}:{p}" for c, p in faltan)), on)
    return RateSet(on, tuple(vigentes[k] for k in sorted(vigentes)))


@dataclass(frozen=True)
class PayItem:
    """Un rubro de la boleta: lo que termina en `payroll_run_items`.

    `payer` es `earning` para lo que se gana —con signo: una ausencia es un
    devengo negativo—, y `employee` o `employer` para las cargas.

    Si sale de una acción de personal, dice de cuál y qué tramo aplicó
    (RN-90): las horas o los días, y desde y hasta.
    """

    concept: str
    payer: str
    base: Money
    rate: Decimal | None
    amount: Money
    action_id: int | None = None
    quantity: Decimal | None = None
    applied_from: date | None = None
    applied_to: date | None = None


def _charges(gross: Money, rates: Iterable[Rate], payer: str) -> tuple[PayItem, ...]:
    return tuple(PayItem(r.concept, payer, gross, r.value, gross * r.value) for r in rates)


def employee_deductions(gross: Money, rates: RateSet) -> tuple[PayItem, ...]:
    """Las cargas obreras sobre el bruto que cotiza, una por rubro."""
    return _charges(gross, rates.contributions(EMPLOYEE), EMPLOYEE)


def employer_charges(
    gross: Money, rates: RateSet, rt_rate: Decimal, *, exempt: frozenset[str] = frozenset()
) -> tuple[PayItem, ...]:
    """Las cargas patronales y la prima de riesgos del trabajo de la póliza.

    `exempt` son los rubros que esta compañía no paga; hoy, solo el INA.
    """
    rt = Rate(RT_CONCEPT, EMPLOYER, rt_rate, rates.on)
    propios = tuple(r for r in rates.contributions(EMPLOYER) if r.concept not in exempt)
    return _charges(gross, propios + (rt,), EMPLOYER)


def total(items: Iterable[PayItem]) -> Money:
    return Money.sum(i.amount for i in items)


# ------------------------------------------------------------------- renta


@dataclass(frozen=True)
class TaxBracket:
    """Un tramo mensual: lo que excede `lower` y no pasa de `upper`, a `rate`."""

    lower: Money
    upper: Money | None
    rate: Decimal


@dataclass(frozen=True)
class TaxCredits:
    """Los créditos mensuales que rigen: por hijo y por cónyuge."""

    child: Money
    spouse: Money

    def for_employee(self, children: int, spouse: bool) -> Money:
        return self.child * children + (self.spouse if spouse else Money.zero())


def income_tax(monthly_taxable: Money, brackets: Iterable[TaxBracket], credits: Money) -> Money:
    """El impuesto al salario de un mes: tramos marginales, menos créditos.

    Marginal: el 15 % de un tramo se cobra solo sobre lo que cae en ese tramo,
    no sobre todo el salario. Los créditos restan del impuesto —no de la base—
    y el resultado nunca es negativo: el crédito no le paga al empleado.
    """
    impuesto = Money.zero()
    for tramo in brackets:
        if monthly_taxable.amount <= tramo.lower.amount:
            continue
        techo = monthly_taxable if tramo.upper is None else min(monthly_taxable, tramo.upper)
        impuesto = impuesto + (techo - tramo.lower) * tramo.rate
    neto = impuesto - credits
    return Money.zero() if neto.is_negative else neto


def income_tax_withholding(
    taxable: Money,
    frequency: str,
    *,
    closes_month: bool,
    month_taxable_before: Money,
    month_withheld_before: Money,
    brackets: Iterable[TaxBracket],
    credits: Money,
) -> Money:
    """Lo que se retiene en esta corrida (RN-73).

    Una corrida que **no** cierra el mes retiene sobre la proyección: lo de este
    periodo llevado a un mes, el impuesto de ese mes, y la parte que le toca al
    periodo. La que **cierra** el mes calcula el impuesto de lo devengado en el
    mes —lo de las corridas anteriores más esta— y retiene la diferencia con lo
    ya retenido. Así el mes cuadra al céntimo con la declaración aunque las
    horas extra de una quincena no sean las de la otra.

    La diferencia puede ser negativa: si la primera quincena retuvo de más, la
    segunda le devuelve al empleado lo que el mes no debía. Es su plata.
    """
    tramos = tuple(brackets)
    if closes_month:
        del_mes = income_tax(month_taxable_before + taxable, tramos, credits)
        return del_mes - month_withheld_before
    proyectado = income_tax(monthly_equivalent(taxable, frequency), tramos, credits)
    return Money(proyectado.amount / MONTHLY_FACTOR[frequency])


# ------------------------------------------------------ mantener las tasas

PAYERS: tuple[str, ...] = (EMPLOYEE, EMPLOYER, RULE)

#: Una tasa que nadie comprobó en seis meses se muestra con aviso (T-1204): un
#: decreto nuevo puede haber salido sin que nadie lo cargara.
STALE_AFTER_DAYS = 183


def is_stale(verified_at: date, today: date) -> bool:
    return (today - verified_at).days > STALE_AFTER_DAYS


def check_new_rate(concept: str, payer: str, value: Decimal, valid_from: date, latest: date | None) -> None:
    """Lo que tiene que cumplir una fila nueva de `payroll_rates`.

    `latest` es el `valid_from` más reciente del mismo concepto y pagador, si
    hay. La nueva tiene que ser posterior: no se edita la vigente ni el pasado.
    """
    if payer not in PAYERS:
        raise InvalidPayrollRate("payer", "unknown", payer)
    if value < 0 or (payer != RULE and value >= 1):
        raise InvalidPayrollRate("value", "out_of_range", value)
    if latest is not None and valid_from <= latest:
        raise RateNotNewer(concept, payer, latest)


# ------------------------------------------- los tramos del año siguiente


def check_tax_brackets(
    brackets: Sequence[tuple[Decimal, Decimal | None, Decimal]],
    credits: Mapping[str, Decimal],
    valid_from: date,
    latest: date | None,
) -> None:
    """Lo que tiene que cumplir un juego nuevo de tramos de renta (RN-73, T-1221).

    `brackets` son `(desde, hasta, tasa)` en el orden en que llegan; `credits`,
    el monto mensual por hijo y por cónyuge. Un juego cubre **todos** los
    salarios: empieza en cero, no deja huecos ni se solapa, y el último tramo
    no tiene techo. Con un hueco, un salario que caiga adentro no paga renta y
    nadie lo nota hasta la declaración.

    Como las tasas, un juego no se edita: el nuevo tiene que ser posterior al
    último que haya (`latest`), que es el que las corridas ya usaron.
    """
    if not brackets:
        raise InvalidTaxBrackets("empty")
    ultimo = len(brackets) - 1
    esperado = Decimal(0)
    for i, (desde, hasta, tasa) in enumerate(brackets):
        if i == 0 and desde != 0:
            raise InvalidTaxBrackets("not_from_zero", 0)
        if desde != esperado:
            raise InvalidTaxBrackets("gap", i)
        if tasa < 0 or tasa >= 1:
            raise InvalidTaxBrackets("rate_out_of_range", i)
        if hasta is None:
            if i != ultimo:
                raise InvalidTaxBrackets("open_end_not_last", i)
            continue
        if hasta <= desde:
            raise InvalidTaxBrackets("empty_range", i)
        if i == ultimo:
            raise InvalidTaxBrackets("no_open_end", i)
        esperado = hasta
    for concepto, monto in credits.items():
        if monto < 0:
            raise InvalidTaxBrackets("credit_negative", None)
    if latest is not None and valid_from <= latest:
        raise RateNotNewer("income_tax_brackets", EMPLOYEE, latest)
