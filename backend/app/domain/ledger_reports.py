"""Los libros: sumar el asiento hasta que sea un estado (F11, RF-53, RF-54).

Cuatro funciones puras sobre líneas ya escritas. No consultan nada: quien las
llama decide **qué** líneas entran —las del mes, las del año, las de una
cuenta— y estas solo suman. Esa frontera es la que permite que el balance de
comprobación de un periodo y el acumulado de toda la vida sean la misma función
llamada dos veces.

La única regla de contabilidad que hay acá es la de los signos, y es esta: el
activo, el costo y el gasto crecen con el débito; el pasivo, el patrimonio y el
ingreso, con el crédito (`DEBIT_KINDS`). De ahí salen los tres estados.

**Las devoluciones no necesitan un caso aparte.** «Devoluciones sobre ventas» es
una cuenta de ingreso con saldo deudor, así que restar sus débitos de los
créditos del grupo deja el ingreso neto sin que ninguna función sepa que existen.

El borrador del D-104 es el que no sale del libro: recibe los desgloses por
tarifa de ventas y de compras, que son los mismos que ya calculan RF-21 y RF-45.
Es RN-65 tomada al pie de la letra —«una consulta sobre eso, no un cálculo aparte
que pueda discrepar»—: si el D-104 sumara el libro por su cuenta, tendríamos dos
números para el mismo impuesto y una tarde por delante para averiguar cuál vale.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .ledger import DEBIT_KINDS
from .money import Money
from .tax import TaxRate


@dataclass(frozen=True)
class PostedLine:
    """Una línea ya escrita, con la cuenta que tocó.

    Trae `code`, `name` y `kind` porque un reporte se lee por cuenta y no por
    id, y porque así la función no necesita ir a buscarlos: quien arma la lista
    ya hizo esa consulta.
    """

    account_id: int
    code: str
    name: str
    kind: str
    debit: Money
    credit: Money


@dataclass(frozen=True)
class AccountBalance:
    """Lo que movió una cuenta y con qué saldo quedó."""

    account_id: int
    code: str
    name: str
    kind: str
    debits: Money
    credits: Money

    @property
    def balance(self) -> Money:
        """El saldo **en su signo natural**.

        Positivo significa «lo que esta cuenta normalmente tiene»: un activo con
        saldo 4 915,50 tiene esa plata, y un pasivo con saldo 113 000 debe esa
        plata. Un negativo es una anomalía que se ve —caja en rojo, un ingreso
        con saldo deudor— y no un signo que haya que interpretar cuenta por
        cuenta.
        """
        if self.kind in DEBIT_KINDS:
            return self.debits - self.credits
        return self.credits - self.debits


@dataclass(frozen=True)
class TrialBalance:
    """El balance de comprobación: toda cuenta con su débito y su crédito."""

    rows: tuple[AccountBalance, ...]
    debits: Money
    credits: Money

    @property
    def is_balanced(self) -> bool:
        """Siempre verdadero si el libro está sano, y por eso se comprueba.

        Cada asiento cuadra por construcción (RN-58), así que la suma de todos
        también. Que esto dé falso significa que alguien escribió en la base sin
        pasar por el dominio.
        """
        return self.debits == self.credits

    def of_kinds(self, *kinds: str) -> tuple[AccountBalance, ...]:
        return tuple(fila for fila in self.rows if fila.kind in kinds)

    def total_of(self, *kinds: str) -> Money:
        return Money.sum(fila.balance for fila in self.of_kinds(*kinds))


def trial_balance(lines: Sequence[PostedLine]) -> TrialBalance:
    """Suma las líneas por cuenta, ordenadas por código.

    Por código y no por id: el código es lo que el contador lee y lo que ordena
    el catálogo —1.1.01 antes que 2.1.01—, y el id es el orden en que se
    crearon las cuentas, que no significa nada para nadie.
    """
    acumulado: dict[int, list] = {}
    for linea in lines:
        fila = acumulado.get(linea.account_id)
        if fila is None:
            acumulado[linea.account_id] = [linea, Money.zero(), Money.zero()]
            fila = acumulado[linea.account_id]
        fila[1] = fila[1] + linea.debit
        fila[2] = fila[2] + linea.credit

    filas = tuple(
        AccountBalance(
            account_id=linea.account_id,
            code=linea.code,
            name=linea.name,
            kind=linea.kind,
            debits=debitos,
            credits=creditos,
        )
        for linea, debitos, creditos in sorted(
            acumulado.values(), key=lambda fila: fila[0].code
        )
    )

    return TrialBalance(
        rows=filas,
        debits=Money.sum(fila.debits for fila in filas),
        credits=Money.sum(fila.credits for fila in filas),
    )


@dataclass(frozen=True)
class IncomeStatement:
    """El estado de resultados del periodo que se le haya dado."""

    income: Money
    cost: Money
    expense: Money
    rows: tuple[AccountBalance, ...]

    @property
    def gross_profit(self) -> Money:
        """Ingresos menos costo de ventas. Es el margen del negocio, antes de lo
        que cuesta tener las puertas abiertas."""
        return self.income - self.cost

    @property
    def result(self) -> Money:
        """La utilidad o la pérdida. Negativo es pérdida."""
        return self.income - self.cost - self.expense


def income_statement(balance: TrialBalance) -> IncomeStatement:
    """Ingresos − costo − gastos, de un balance de comprobación ya sumado.

    Se alimenta del balance y no de las líneas a propósito: los dos estados
    tienen que salir de la **misma** suma o pueden discrepar, y entonces el
    resultado del estado de resultados no sería el que el balance general usa
    para cuadrar.
    """
    return IncomeStatement(
        income=balance.total_of("income"),
        cost=balance.total_of("cost"),
        expense=balance.total_of("expense"),
        rows=balance.of_kinds("income", "cost", "expense"),
    )


@dataclass(frozen=True)
class BalanceSheet:
    """El balance general."""

    assets: Money
    liabilities: Money
    equity: Money
    #: El resultado del periodo, que todavía **no** está en el patrimonio: se
    #: capitaliza al cierre del ejercicio, no al de cada mes. Por eso entra en la
    #: igualdad por separado.
    result: Money
    rows: tuple[AccountBalance, ...]

    @property
    def is_balanced(self) -> bool:
        """Activo = pasivo + patrimonio + resultado. La ecuación contable."""
        return self.assets == self.liabilities + self.equity + self.result


def balance_sheet(balance: TrialBalance) -> BalanceSheet:
    """Activo, pasivo, patrimonio y el resultado que todavía no se capitalizó."""
    return BalanceSheet(
        assets=balance.total_of("asset"),
        liabilities=balance.total_of("liability"),
        equity=balance.total_of("equity"),
        result=income_statement(balance).result,
        rows=balance.of_kinds("asset", "liability", "equity"),
    )


# ------------------------------------------------------------------- el D-104


@dataclass(frozen=True)
class RateAmount:
    """Base e impuesto de una tarifa, como ya los dan RF-21 y RF-45."""

    rate: TaxRate
    base: Money
    tax: Money


@dataclass(frozen=True)
class VatRateLine:
    """Una tarifa en el borrador: lo que se cobró contra lo que se pagó."""

    rate: TaxRate
    sales_base: Money
    debit: Money
    purchases_base: Money
    credit: Money

    @property
    def balance(self) -> Money:
        return self.debit - self.credit


@dataclass(frozen=True)
class VatDraft:
    """El borrador del D-104 de un mes (RF-54, RN-65)."""

    lines: tuple[VatRateLine, ...]
    debit: Money
    credit: Money

    @property
    def balance(self) -> Money:
        """Débito − crédito. **Positivo se paga; negativo queda a favor.**"""
        return self.debit - self.credit

    @property
    def is_in_favor(self) -> bool:
        return self.balance.is_negative


def vat_draft(
    sales_by_rate: Sequence[RateAmount], purchases_by_rate: Sequence[RateAmount]
) -> VatDraft:
    """Débito fiscal menos crédito fiscal, tarifa por tarifa.

        ventas 4 350,00 al 13 % → débito   565,50
        compras 100 000 al 13 % → crédito 13 000,00
                                          ─────────
                                   saldo a favor 12 434,50

    Las tarifas se cruzan y no se suman de un lado y del otro: una compra al 1 %
    no acredita contra una venta al 13 % en la declaración, y verlas en la misma
    fila es lo que deja mirar si el negocio está comprando a una tarifa y
    vendiendo a otra.

    El **total** sí es la suma de todas, porque el D-104 se paga de una sola vez.
    """
    tarifas = sorted({fila.rate for fila in (*sales_by_rate, *purchases_by_rate)})

    ventas = {fila.rate: fila for fila in sales_by_rate}
    compras = {fila.rate: fila for fila in purchases_by_rate}
    vacio = RateAmount(rate=TaxRate.zero(), base=Money.zero(), tax=Money.zero())

    filas = tuple(
        VatRateLine(
            rate=tarifa,
            sales_base=ventas.get(tarifa, vacio).base,
            debit=ventas.get(tarifa, vacio).tax,
            purchases_base=compras.get(tarifa, vacio).base,
            credit=compras.get(tarifa, vacio).tax,
        )
        for tarifa in tarifas
    )

    return VatDraft(
        lines=filas,
        debit=Money.sum(fila.debit for fila in filas),
        credit=Money.sum(fila.credit for fila in filas),
    )
