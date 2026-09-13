"""Los libros (T-1103, RF-53, RF-54, RN-65).

La comprobación que importa no es que cada función sume: es que las tres salgan
del **mismo** libro y la ecuación contable cierre. Por eso el escenario no está
escrito a mano fila por fila —así se podría cuadrar por casualidad— sino armado
con los `post_*` de `domain/ledger.py`, que es lo que el sistema va a escribir de
verdad.
"""

from datetime import date

from app.domain.ledger import (
    AccountMap,
    ClosedSession,
    JournalEntry,
    Line,
    OPENING,
    PurchasedDocument,
    PurchasedLine,
    SoldDocument,
    SoldLine,
    SupplierPaymentRef,
    post_cash_close,
    post_purchase,
    post_sale,
    post_supplier_payment,
    sales_role,
)
from app.domain.ledger import (
    CASH,
    CASH_CLOSE,
    CASH_SHORT,
    COGS,
    INVENTORY,
    PAYABLES,
    PURCHASE,
    SALE,
    SUPPLIER_PAYMENT,
    VAT_CREDIT,
    VAT_PAYABLE,
)
from app.domain.ledger_reports import (
    PostedLine,
    RateAmount,
    balance_sheet,
    income_statement,
    trial_balance,
    vat_draft,
)
from app.domain.money import Money
from app.domain.tax import TaxRate

TRECE = TaxRate.percent(13)
UNO = TaxRate.percent(1)
HOY = date(2026, 9, 12)

#: El catálogo de la plantilla «comercio», con los códigos de plan §13.8.
CATALOGO: dict[int, tuple[str, str, str]] = {
    101: ("1.1.01", "Caja", "asset"),
    105: ("1.1.05", "IVA crédito fiscal", "asset"),
    121: ("1.2.01", "Inventario", "asset"),
    211: ("2.1.01", "Proveedores", "liability"),
    212: ("2.1.02", "IVA por pagar", "liability"),
    311: ("3.1.01", "Capital", "equity"),
    411: ("4.1.01", "Ventas 13 %", "income"),
    511: ("5.1.01", "Costo de ventas", "cost"),
    691: ("6.9.01", "Faltantes de caja", "expense"),
}

MAPEO = AccountMap(
    accounts={
        (SALE, CASH): 101,
        (SALE, sales_role(TRECE)): 411,
        (SALE, VAT_PAYABLE): 212,
        (SALE, COGS): 511,
        (SALE, INVENTORY): 121,
        (PURCHASE, INVENTORY): 121,
        (PURCHASE, VAT_CREDIT): 105,
        (PURCHASE, PAYABLES): 211,
        (SUPPLIER_PAYMENT, PAYABLES): 211,
        (SUPPLIER_PAYMENT, CASH): 101,
        (CASH_CLOSE, CASH): 101,
        (CASH_CLOSE, CASH_SHORT): 691,
    },
    unclassified=999,
)


def asentado(*asientos: JournalEntry) -> list[PostedLine]:
    """Los asientos, vueltos líneas con su cuenta. Es lo que hará el adaptador."""
    salida = []
    for asiento in asientos:
        for linea in asiento.lines:
            codigo, nombre, tipo = CATALOGO[linea.account_id]
            salida.append(
                PostedLine(
                    account_id=linea.account_id,
                    code=codigo,
                    name=nombre,
                    kind=tipo,
                    debit=linea.debit,
                    credit=linea.credit,
                )
            )
    return salida


def el_mes() -> list[PostedLine]:
    """Un mes con los asientos de la tabla de plan §13.3.

    Apertura, la venta del invariante, la compra a crédito, el abono y un cierre
    de caja con faltante.
    """
    apertura = JournalEntry(
        kind=OPENING,
        entry_date=date(2026, 9, 1),
        description="saldos iniciales",
        lines=(
            Line.debit_of(101, Money(100000)),
            Line.debit_of(121, Money(50000)),
            Line.credit_of(311, Money(150000)),
        ),
    )
    venta = post_sale(
        SoldDocument(id=1, date=HOY, payment_method="Efectivo"),
        [SoldLine(Money(4350), Money("565.50"), TRECE, quantity=3, unit_cost=Money(900))],
        MAPEO,
    )
    compra = post_purchase(
        PurchasedDocument(id=1, date=HOY),
        [PurchasedLine(Money(100000), Money(13000), TRECE)],
        MAPEO,
    )
    abono = post_supplier_payment(
        SupplierPaymentRef(id=1, date=HOY, amount=Money(50000), method="cash"), MAPEO
    )
    cierre = post_cash_close(
        ClosedSession(id=1, date=HOY), Money("53277.00"), Money(53000), MAPEO
    )

    return asentado(apertura, venta, compra, abono, cierre)


def saldo(balance, codigo: str) -> Money:
    return next(fila.balance for fila in balance.rows if fila.code == codigo)


class TestElBalanceDeComprobacion:
    def test_los_dos_lados_suman_lo_mismo(self):
        # Cada asiento cuadra por construcción, así que la suma de todos también.
        balance = trial_balance(el_mes())

        assert balance.is_balanced
        assert balance.debits == balance.credits

    def test_una_cuenta_junta_todo_lo_que_la_tocó(self):
        # La caja la mueven cuatro asientos: 100 000 + 4 915,50 − 50 000 − 277.
        balance = trial_balance(el_mes())

        assert saldo(balance, "1.1.01") == Money("54638.50")

    def test_va_ordenado_por_codigo_y_no_por_id(self):
        # El código es lo que el contador lee; el id es el orden en que alguien
        # creó las cuentas, que no significa nada para nadie.
        balance = trial_balance(el_mes())

        assert [fila.code for fila in balance.rows] == sorted(
            fila.code for fila in balance.rows
        )

    def test_el_saldo_va_en_el_signo_natural_de_su_tipo(self):
        balance = trial_balance(el_mes())

        # El activo con lo que tiene, el pasivo con lo que debe: los dos en
        # positivo, sin que haya que interpretar el signo cuenta por cuenta.
        assert saldo(balance, "1.2.01") == Money(147300)
        assert saldo(balance, "2.1.01") == Money(63000)

    def test_sin_lineas_no_hay_nada_que_comprobar(self):
        balance = trial_balance([])

        assert balance.rows == ()
        assert balance.is_balanced

    def test_un_libro_manipulado_se_delata(self):
        # `is_balanced` es la prueba de que nadie escribió saltándose el dominio.
        suelta = [
            PostedLine(101, "1.1.01", "Caja", "asset", Money(10), Money.zero()),
        ]

        assert not trial_balance(suelta).is_balanced


class TestElEstadoDeResultados:
    def test_las_tres_cifras_del_mes(self):
        estado = income_statement(trial_balance(el_mes()))

        assert estado.income == Money(4350)
        assert estado.cost == Money(2700)
        assert estado.expense == Money(277)

    def test_el_margen_bruto_es_antes_de_los_gastos(self):
        estado = income_statement(trial_balance(el_mes()))

        assert estado.gross_profit == Money(1650)

    def test_el_resultado_resta_las_tres(self):
        estado = income_statement(trial_balance(el_mes()))

        assert estado.result == Money(1373)

    def test_una_devolucion_rebaja_el_ingreso_sin_caso_aparte(self):
        # «Devoluciones sobre ventas» es una cuenta de ingreso con saldo deudor,
        # así que el neto sale solo.
        lineas = [
            PostedLine(411, "4.1.01", "Ventas 13 %", "income", Money.zero(), Money(4350)),
            PostedLine(421, "4.2.01", "Devoluciones", "income", Money(1450), Money.zero()),
        ]

        assert income_statement(trial_balance(lineas)).income == Money(2900)

    def test_solo_lleva_las_cuentas_de_resultado(self):
        estado = income_statement(trial_balance(el_mes()))

        assert {fila.kind for fila in estado.rows} == {"income", "cost", "expense"}

    def test_un_mes_con_mas_gasto_que_ingreso_da_perdida(self):
        lineas = [
            PostedLine(411, "4.1.01", "Ventas", "income", Money.zero(), Money(1000)),
            PostedLine(691, "6.9.01", "Faltantes", "expense", Money(1500), Money.zero()),
        ]

        assert income_statement(trial_balance(lineas)).result == Money(-500)


class TestElBalanceGeneral:
    def test_la_ecuacion_contable_cierra(self):
        # Activo = pasivo + patrimonio + resultado. Es la verificación de T-1103.
        general = balance_sheet(trial_balance(el_mes()))

        assert general.is_balanced
        assert general.assets == Money("214938.50")
        assert general.liabilities == Money("63565.50")
        assert general.equity == Money(150000)
        assert general.result == Money(1373)

    def test_el_resultado_entra_aparte_y_no_dentro_del_patrimonio(self):
        # Se capitaliza al cierre del ejercicio, no al de cada mes.
        general = balance_sheet(trial_balance(el_mes()))

        assert general.equity == Money(150000)
        assert general.assets != general.liabilities + general.equity

    def test_no_lleva_las_cuentas_de_resultado(self):
        general = balance_sheet(trial_balance(el_mes()))

        assert {fila.kind for fila in general.rows} == {"asset", "liability", "equity"}


class TestElBorradorDelD104:
    def test_el_ejemplo_del_plan_da_saldo_a_favor(self):
        borrador = vat_draft(
            [RateAmount(TRECE, Money(4350), Money("565.50"))],
            [RateAmount(TRECE, Money(100000), Money(13000))],
        )

        assert borrador.debit == Money("565.50")
        assert borrador.credit == Money(13000)
        assert borrador.balance == Money("-12434.50")
        assert borrador.is_in_favor

    def test_mas_debito_que_credito_se_paga(self):
        borrador = vat_draft(
            [RateAmount(TRECE, Money(100000), Money(13000))],
            [RateAmount(TRECE, Money(10000), Money(1300))],
        )

        assert borrador.balance == Money(11700)
        assert not borrador.is_in_favor

    def test_las_tarifas_se_cruzan_en_la_misma_fila(self):
        # Una compra al 1 % no acredita contra una venta al 13 % en la
        # declaración, y verlas juntas es lo que deja mirar si el negocio compra
        # a una tarifa y vende a otra.
        borrador = vat_draft(
            [RateAmount(TRECE, Money(1000), Money(130))],
            [RateAmount(UNO, Money(500), Money(5))],
        )

        assert [fila.rate for fila in borrador.lines] == [UNO, TRECE]
        del_uno, del_trece = borrador.lines
        assert (del_uno.debit, del_uno.credit) == (Money.zero(), Money(5))
        assert (del_trece.debit, del_trece.credit) == (Money(130), Money.zero())

    def test_la_fila_lleva_las_dos_bases(self):
        borrador = vat_draft(
            [RateAmount(TRECE, Money(4350), Money("565.50"))],
            [RateAmount(TRECE, Money(100000), Money(13000))],
        )

        fila = borrador.lines[0]
        assert fila.sales_base == Money(4350)
        assert fila.purchases_base == Money(100000)
        assert fila.balance == Money("-12434.50")

    def test_un_mes_sin_movimiento_no_es_un_error(self):
        borrador = vat_draft([], [])

        assert borrador.lines == ()
        assert borrador.balance == Money.zero()
        assert not borrador.is_in_favor
