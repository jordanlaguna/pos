"""El libro (T-1102, RN-58 a RN-63).

La tabla de casos de plan §13.3, con las cifras de los invariantes. Sin base, sin
reloj y sin red: entra el hecho, salen las líneas.

El caso que fija todo lo demás es el de siempre —3 × 1 450 al 13 %— y por eso
está primero. Si alguna vez cambia, lo que cambió es el sistema, no la prueba.
"""

from datetime import date

import pytest

from app.domain.errors import EntryNotBalanced, InvalidEntryLine, PeriodClosed
from app.domain.ledger import (
    AUTO,
    BANK,
    CARDS_RECEIVABLE,
    CASH,
    CASH_CLOSE,
    CASH_MOVEMENT,
    CASH_OVER,
    CASH_SHORT,
    CLOSED,
    COGS,
    COUNTERPART,
    INVENTORY,
    PAYABLES,
    PURCHASE,
    RECEIVABLE,
    RETURN,
    SALE,
    SALES_RETURNS,
    SUPPLIER_PAYMENT,
    UNCLASSIFIED,
    VAT_CREDIT,
    VAT_PAYABLE,
    AccountMap,
    ClosedSession,
    DrawerMovement,
    JournalEntry,
    Line,
    Period,
    PurchasedDocument,
    PurchasedLine,
    ReturnDocument,
    SoldDocument,
    SoldLine,
    SupplierPaymentRef,
    assert_open,
    post_cash_close,
    post_cash_movement,
    post_purchase,
    post_return,
    post_sale,
    post_supplier_payment,
    sales_role,
)
from app.domain.money import Money
from app.domain.tax import TaxRate

TRECE = TaxRate.percent(13)
DOS = TaxRate.percent(2)
CERO = TaxRate.zero()

HOY = date(2026, 9, 12)

#: Un mapeo completo, con un id distinto por papel para poder afirmar sobre
#: cuentas y no sobre posiciones. El 999 es «por clasificar».
POR_CLASIFICAR = 999

CUENTAS = {
    (SALE, CASH): 101,
    (SALE, CARDS_RECEIVABLE): 103,
    (SALE, BANK): 102,
    (SALE, sales_role(TRECE)): 411,
    (SALE, sales_role(DOS)): 413,
    (SALE, sales_role(CERO)): 415,
    (SALE, VAT_PAYABLE): 212,
    (SALE, COGS): 511,
    (SALE, INVENTORY): 121,
    (RETURN, SALES_RETURNS): 421,
    (RETURN, VAT_PAYABLE): 212,
    (RETURN, CASH): 101,
    (RETURN, COGS): 511,
    (RETURN, INVENTORY): 121,
    (CASH_CLOSE, CASH): 101,
    (CASH_CLOSE, CASH_OVER): 491,
    (CASH_CLOSE, CASH_SHORT): 691,
    (CASH_MOVEMENT, CASH): 101,
    (PURCHASE, INVENTORY): 121,
    (PURCHASE, VAT_CREDIT): 105,
    (PURCHASE, PAYABLES): 211,
    (SUPPLIER_PAYMENT, PAYABLES): 211,
    (SUPPLIER_PAYMENT, CASH): 101,
    (SUPPLIER_PAYMENT, BANK): 102,
}

MAPEO = AccountMap(accounts=CUENTAS, unclassified=POR_CLASIFICAR)

#: Un mapeo vacío: todo cae en «por clasificar». Es el peor caso de RN-59 y el
#: que tiene que seguir dejando asientos que balancean.
VACIO = AccountMap(accounts={}, unclassified=POR_CLASIFICAR)


def debitos(asiento: JournalEntry) -> dict[int, Money]:
    """Cuánto se debitó a cada cuenta. Suma, porque una cuenta puede repetirse."""
    salida: dict[int, Money] = {}
    for linea in asiento.lines:
        if linea.debit.is_positive:
            salida[linea.account_id] = salida.get(linea.account_id, Money.zero()) + linea.debit
    return salida


def creditos(asiento: JournalEntry) -> dict[int, Money]:
    salida: dict[int, Money] = {}
    for linea in asiento.lines:
        if linea.credit.is_positive:
            salida[linea.account_id] = salida.get(linea.account_id, Money.zero()) + linea.credit
    return salida


# ------------------------------------------------------------------ la línea


class TestLaLinea:
    def test_un_debito_es_una_linea(self):
        linea = Line.debit_of(101, Money(100), memo=CASH)
        assert linea.debit == Money(100)
        assert linea.credit == Money.zero()
        assert linea.memo == CASH

    def test_un_credito_tambien(self):
        linea = Line.credit_of(212, Money(13), tax_rate=TRECE)
        assert linea.credit == Money(13)
        assert linea.tax_rate == TRECE

    def test_no_puede_tener_las_dos_columnas(self):
        # Es la regla de las dos columnas, y la vigila el dominio y no un CHECK.
        with pytest.raises(InvalidEntryLine) as fallo:
            Line(account_id=101, debit=Money(10), credit=Money(10))
        assert fallo.value.code == "both_sides"

    def test_no_puede_estar_vacia(self):
        with pytest.raises(InvalidEntryLine) as fallo:
            Line(account_id=101)
        assert fallo.value.code == "empty"

    @pytest.mark.parametrize(
        "lado", [{"debit": Money(-1)}, {"credit": Money(-1)}], ids=["débito", "crédito"]
    )
    def test_no_puede_ser_negativa(self, lado):
        # Un crédito negativo es un débito escrito al revés, y dos formas de
        # decir lo mismo vuelven ilegible el mayor.
        with pytest.raises(InvalidEntryLine) as fallo:
            Line(account_id=101, **lado)
        assert fallo.value.code == "negative"


# ----------------------------------------------------------------- el asiento


class TestElAsiento:
    def test_uno_desbalanceado_no_se_puede_construir(self):
        # RN-58: no es un asiento con un error, no existe.
        with pytest.raises(EntryNotBalanced) as fallo:
            JournalEntry(
                kind=AUTO,
                entry_date=HOY,
                lines=(Line.debit_of(101, Money(100)), Line.credit_of(411, Money(90))),
            )
        assert fallo.value.debits == "100.00"
        assert fallo.value.credits == "90.00"

    def test_uno_sin_lineas_tampoco(self):
        with pytest.raises(InvalidEntryLine) as fallo:
            JournalEntry(kind=AUTO, entry_date=HOY, lines=())
        assert fallo.value.code == "no_lines"

    def test_las_lineas_quedan_en_tupla_aunque_llegue_una_lista(self):
        # Que sea inmutable no es adorno: el adaptador lo recorre para escribir y
        # nadie tiene por qué poder agregarle una línea después de que cuadró.
        asiento = JournalEntry(
            kind=AUTO,
            entry_date=HOY,
            lines=[Line.debit_of(101, Money(10)), Line.credit_of(411, Money(10))],
        )
        assert isinstance(asiento.lines, tuple)

    def test_el_total_es_un_solo_numero(self):
        asiento = JournalEntry(
            kind=AUTO,
            entry_date=HOY,
            lines=(Line.debit_of(101, Money(10)), Line.credit_of(411, Money(10))),
        )
        assert asiento.total == Money(10) == asiento.debits == asiento.credits


# -------------------------------------------------------------------- ventas


def venta_del_invariante() -> tuple[SoldDocument, list[SoldLine]]:
    """3 × 1 450 al 13 %, en efectivo, con costo unitario 900."""
    return (
        SoldDocument(id=1, date=HOY, payment_method="Efectivo"),
        [
            SoldLine(
                subtotal=Money(4350),
                tax=Money("565.50"),
                tax_rate=TRECE,
                quantity=3,
                unit_cost=Money(900),
            )
        ],
    )


class TestLaVenta:
    def test_el_asiento_del_plan(self):
        venta, lineas = venta_del_invariante()
        asiento = post_sale(venta, lineas, MAPEO)

        assert asiento is not None
        assert debitos(asiento) == {101: Money("4915.50"), 511: Money(2700)}
        assert creditos(asiento) == {
            411: Money(4350),
            212: Money("565.50"),
            121: Money(2700),
        }
        # 7 615,50 por lado, que es la cifra del invariante.
        assert asiento.total == Money("7615.50")

    def test_queda_atada_a_su_venta(self):
        venta, lineas = venta_del_invariante()
        asiento = post_sale(venta, lineas, MAPEO)

        assert asiento.kind == AUTO
        assert asiento.source_type == "sale"
        assert asiento.source_id == 1
        assert asiento.entry_date == HOY
        # La descripción es el código del evento: la frase la arma el POS (RN-30).
        assert asiento.description == SALE

    def test_la_linea_de_iva_lleva_su_tarifa(self):
        # Es lo que deja el débito fiscal por tarifa a la vista en el libro.
        venta, lineas = venta_del_invariante()
        asiento = post_sale(venta, lineas, MAPEO)

        iva = [linea for linea in asiento.lines if linea.memo == VAT_PAYABLE]
        assert [linea.tax_rate for linea in iva] == [TRECE]

    def test_la_tarjeta_va_por_su_bruto_a_tarjetas_por_cobrar(self):
        # La comisión y la retención se asientan cuando el banco liquida.
        venta, lineas = venta_del_invariante()
        con_tarjeta = SoldDocument(id=2, date=HOY, payment_method="Tarjeta de crédito")
        asiento = post_sale(con_tarjeta, lineas, MAPEO)

        assert debitos(asiento)[103] == Money("4915.50")

    def test_la_transferencia_y_el_pago_movil_van_al_banco(self):
        venta, lineas = venta_del_invariante()
        for metodo in ("Transferencia bancaria", "Pago móvil"):
            asiento = post_sale(
                SoldDocument(id=3, date=HOY, payment_method=metodo), lineas, MAPEO
            )
            assert debitos(asiento)[102] == Money("4915.50")

    def test_tarifas_mezcladas_dan_una_linea_de_ingreso_por_tarifa(self):
        venta = SoldDocument(id=4, date=HOY, payment_method="Efectivo")
        lineas = [
            SoldLine(Money(1000), Money(130), TRECE, quantity=1),
            SoldLine(Money(500), Money(10), DOS, quantity=1),
            SoldLine(Money(300), Money.zero(), CERO, quantity=1),
        ]
        asiento = post_sale(venta, lineas, MAPEO)

        assert creditos(asiento) == {
            411: Money(1000),
            413: Money(500),
            415: Money(300),
            212: Money(140),
        }
        assert debitos(asiento) == {101: Money(1940)}

    def test_el_iva_se_asienta_por_tarifa_y_no_junto(self):
        venta = SoldDocument(id=5, date=HOY, payment_method="Efectivo")
        lineas = [
            SoldLine(Money(1000), Money(130), TRECE, quantity=1),
            SoldLine(Money(500), Money(10), DOS, quantity=1),
        ]
        asiento = post_sale(venta, lineas, MAPEO)

        iva = sorted(
            (linea.tax_rate, linea.credit) for linea in asiento.lines if linea.memo == VAT_PAYABLE
        )
        assert iva == [(DOS, Money(10)), (TRECE, Money(130))]

    def test_una_linea_sin_costo_no_asienta_costo_ni_inventario(self):
        # NULL es «no se sabe». Inventar un cero inflaría la utilidad del mes.
        venta = SoldDocument(id=6, date=HOY, payment_method="Efectivo")
        lineas = [SoldLine(Money(1000), Money(130), TRECE, quantity=1, unit_cost=None)]
        asiento = post_sale(venta, lineas, MAPEO)

        assert 511 not in debitos(asiento)
        assert 121 not in creditos(asiento)
        assert asiento.total == Money(1130)

    def test_con_costos_mezclados_asienta_solo_los_que_se_saben(self):
        venta = SoldDocument(id=7, date=HOY, payment_method="Efectivo")
        lineas = [
            SoldLine(Money(1000), Money(130), TRECE, quantity=2, unit_cost=Money(300)),
            SoldLine(Money(500), Money(65), TRECE, quantity=1, unit_cost=None),
        ]
        asiento = post_sale(venta, lineas, MAPEO)

        assert debitos(asiento)[511] == Money(600)

    def test_un_metodo_desconocido_cae_en_por_clasificar(self):
        # Una venta vieja, una fila escrita a mano. No detiene nada (RN-59).
        venta, lineas = venta_del_invariante()
        rara = SoldDocument(id=8, date=HOY, payment_method="Bitcoin")
        asiento = post_sale(rara, lineas, MAPEO)

        assert debitos(asiento)[POR_CLASIFICAR] == Money("4915.50")
        assert asiento.debits == asiento.credits

    def test_sin_mapeo_todo_cae_en_por_clasificar_y_el_asiento_existe(self):
        # El corazón de RN-59: con el mapeo vacío la venta se confirma igual.
        venta, lineas = venta_del_invariante()
        asiento = post_sale(venta, lineas, VACIO)

        assert {linea.account_id for linea in asiento.lines} == {POR_CLASIFICAR}
        assert asiento.total == Money("7615.50")

    def test_el_memo_dice_que_papel_falta(self):
        # Sin esto, la pantalla de «por clasificar» diría cuánto y no qué.
        venta, lineas = venta_del_invariante()
        asiento = post_sale(venta, lineas, VACIO)

        assert {linea.memo for linea in asiento.lines} == {
            CASH,
            sales_role(TRECE),
            VAT_PAYABLE,
            COGS,
            INVENTORY,
        }

    def test_una_linea_regalada_no_deja_linea_de_ingreso(self):
        venta = SoldDocument(id=9, date=HOY, payment_method="Efectivo")
        lineas = [
            SoldLine(Money(1000), Money(130), TRECE, quantity=1),
            SoldLine(Money.zero(), Money.zero(), CERO, quantity=1),
        ]
        asiento = post_sale(venta, lineas, MAPEO)

        assert 415 not in creditos(asiento)

    def test_una_venta_de_cero_sin_costo_no_deja_asiento(self):
        venta = SoldDocument(id=10, date=HOY, payment_method="Efectivo")
        lineas = [SoldLine(Money.zero(), Money.zero(), CERO, quantity=1)]

        assert post_sale(venta, lineas, MAPEO) is None


# --------------------------------------------------------------- devoluciones


class TestLaDevolucion:
    def test_es_la_venta_al_reves(self):
        # Una unidad de la venta del invariante: 1 450 + 188,50.
        devolucion = ReturnDocument(id=1, date=HOY)
        lineas = [
            SoldLine(
                subtotal=Money(1450),
                tax=Money("188.50"),
                tax_rate=TRECE,
                quantity=1,
                unit_cost=Money(900),
            )
        ]
        asiento = post_return(devolucion, lineas, MAPEO)

        assert debitos(asiento) == {
            421: Money(1450),
            212: Money("188.50"),
            121: Money(900),
        }
        assert creditos(asiento) == {101: Money("1638.50"), 511: Money(900)}
        assert asiento.source_type == "return"

    def test_usa_la_tarifa_de_su_venta(self):
        # RN-12: se reembolsa con la tasa con la que se cobró, no con la de hoy.
        devolucion = ReturnDocument(id=2, date=HOY)
        lineas = [SoldLine(Money(1000), Money(20), DOS, quantity=1)]
        asiento = post_return(devolucion, lineas, MAPEO)

        iva = [linea for linea in asiento.lines if linea.memo == VAT_PAYABLE]
        assert iva[0].tax_rate == DOS
        assert iva[0].debit == Money(20)

    def test_el_reembolso_sale_de_la_gaveta(self):
        # Tiene que coincidir con `expected_amount`, que resta TODAS las
        # devoluciones del efectivo esperado. Si no, el turno y el libro
        # dejarían de decir lo mismo.
        devolucion = ReturnDocument(id=3, date=HOY)
        lineas = [SoldLine(Money(1000), Money(130), TRECE, quantity=1)]
        asiento = post_return(devolucion, lineas, MAPEO)

        assert creditos(asiento) == {101: Money(1130)}

    def test_la_base_va_a_su_propia_cuenta_y_no_rebaja_la_de_ingresos(self):
        devolucion = ReturnDocument(id=4, date=HOY)
        lineas = [SoldLine(Money(1000), Money(130), TRECE, quantity=1)]
        asiento = post_return(devolucion, lineas, MAPEO)

        assert 421 in debitos(asiento)
        assert 411 not in creditos(asiento)

    def test_sin_costo_no_devuelve_inventario(self):
        devolucion = ReturnDocument(id=5, date=HOY)
        lineas = [SoldLine(Money(1000), Money(130), TRECE, quantity=1, unit_cost=None)]
        asiento = post_return(devolucion, lineas, MAPEO)

        assert 121 not in debitos(asiento)

    def test_una_devolucion_de_cero_no_deja_asiento(self):
        devolucion = ReturnDocument(id=6, date=HOY)
        lineas = [SoldLine(Money.zero(), Money.zero(), CERO, quantity=1)]

        assert post_return(devolucion, lineas, MAPEO) is None


# ------------------------------------------------------------- cierre de caja


class TestElCierreDeCaja:
    def test_el_faltante_del_plan(self):
        # 53 000 contado contra 53 277,00 esperados.
        asiento = post_cash_close(
            ClosedSession(id=1, date=HOY), Money("53277.00"), Money(53000), MAPEO
        )

        assert debitos(asiento) == {691: Money(277)}
        assert creditos(asiento) == {101: Money(277)}
        assert asiento.source_type == "cash_session"

    def test_el_sobrante_va_al_otro_lado(self):
        asiento = post_cash_close(
            ClosedSession(id=2, date=HOY), Money(53000), Money("53100.00"), MAPEO
        )

        assert debitos(asiento) == {101: Money(100)}
        assert creditos(asiento) == {491: Money(100)}

    def test_un_turno_cuadrado_no_deja_asiento(self):
        # No pasó nada que anotar: lo que entró y salió ya lo asentaron la venta
        # y el movimiento.
        assert (
            post_cash_close(ClosedSession(id=3, date=HOY), Money(53000), Money(53000), MAPEO)
            is None
        )


# --------------------------------------------------------- movimientos de caja


class TestElMovimientoDeCaja:
    def test_una_entrada_va_contra_por_clasificar(self):
        # El sistema sabe que entraron 5 000, no de dónde salieron.
        movimiento = DrawerMovement(id=1, date=HOY, type="entrada", amount=Money(5000))
        asiento = post_cash_movement(movimiento, MAPEO)

        assert debitos(asiento) == {101: Money(5000)}
        assert creditos(asiento) == {POR_CLASIFICAR: Money(5000)}
        assert asiento.source_type == "cash_movement"

    def test_una_salida_va_al_reves(self):
        movimiento = DrawerMovement(id=2, date=HOY, type="salida", amount=Money(3000))
        asiento = post_cash_movement(movimiento, MAPEO)

        assert debitos(asiento) == {POR_CLASIFICAR: Money(3000)}
        assert creditos(asiento) == {101: Money(3000)}

    def test_la_contrapartida_se_puede_mapear(self):
        # Queda sin mapear por omisión, pero si el contador le asigna cuenta, se
        # usa: no está clavada en 1.9.99.
        con_contra = AccountMap(
            accounts={**CUENTAS, (CASH_MOVEMENT, COUNTERPART): 692},
            unclassified=POR_CLASIFICAR,
        )
        movimiento = DrawerMovement(id=3, date=HOY, type="salida", amount=Money(3000))

        assert debitos(post_cash_movement(movimiento, con_contra)) == {692: Money(3000)}

    def test_la_salida_de_un_abono_no_deja_asiento(self):
        # El abono ya asienta esa plata; las dos juntas la contarían dos veces.
        movimiento = DrawerMovement(
            id=4, date=HOY, type="salida", amount=Money(50000), from_supplier_payment=True
        )

        assert post_cash_movement(movimiento, MAPEO) is None

    def test_un_movimiento_de_cero_no_deja_asiento(self):
        movimiento = DrawerMovement(id=5, date=HOY, type="entrada", amount=Money.zero())

        assert post_cash_movement(movimiento, MAPEO) is None


# -------------------------------------------------------------------- compras


class TestLaCompra:
    def test_la_compra_a_credito(self):
        compra = PurchasedDocument(id=1, date=HOY)
        lineas = [PurchasedLine(Money(100000), Money(13000), TRECE)]
        asiento = post_purchase(compra, lineas, MAPEO)

        assert debitos(asiento) == {121: Money(100000), 105: Money(13000)}
        assert creditos(asiento) == {211: Money(113000)}
        assert asiento.source_type == "stock_entry"

    def test_la_de_contado_tambien_va_contra_proveedores(self):
        # Y no contra caja: desde F10 la de contado crea su propio abono, y el
        # abono ya asienta proveedores contra caja. Cargar caja acá la contaría
        # dos veces.
        compra = PurchasedDocument(id=2, date=HOY)
        lineas = [PurchasedLine(Money(10000), Money(1300), TRECE)]
        asiento = post_purchase(compra, lineas, MAPEO)

        assert creditos(asiento) == {211: Money(11300)}
        assert 101 not in creditos(asiento)

    def test_el_credito_fiscal_va_por_tarifa(self):
        # RN-53: el impuesto es el del documento del proveedor, y por tarifa.
        compra = PurchasedDocument(id=3, date=HOY)
        lineas = [
            PurchasedLine(Money(10000), Money(1300), TRECE),
            PurchasedLine(Money(5000), Money(100), DOS),
        ]
        asiento = post_purchase(compra, lineas, MAPEO)

        iva = sorted(
            (linea.tax_rate, linea.debit) for linea in asiento.lines if linea.memo == VAT_CREDIT
        )
        assert iva == [(DOS, Money(100)), (TRECE, Money(1300))]
        assert creditos(asiento) == {211: Money(16400)}

    def test_una_compra_exenta_no_deja_linea_de_iva(self):
        compra = PurchasedDocument(id=4, date=HOY)
        lineas = [PurchasedLine(Money(8000), Money.zero(), CERO)]
        asiento = post_purchase(compra, lineas, MAPEO)

        assert debitos(asiento) == {121: Money(8000)}
        assert creditos(asiento) == {211: Money(8000)}

    def test_una_compra_de_cero_no_deja_asiento(self):
        compra = PurchasedDocument(id=5, date=HOY)

        assert post_purchase(compra, [], MAPEO) is None


# --------------------------------------------------------- abonos a proveedor


class TestElAbono:
    def test_el_abono_en_efectivo(self):
        abono = SupplierPaymentRef(id=1, date=HOY, amount=Money(50000), method="cash")
        asiento = post_supplier_payment(abono, MAPEO)

        assert debitos(asiento) == {211: Money(50000)}
        assert creditos(asiento) == {101: Money(50000)}
        assert asiento.source_type == "supplier_payment"

    def test_la_transferencia_sale_del_banco(self):
        abono = SupplierPaymentRef(id=2, date=HOY, amount=Money(50000), method="transfer")

        assert creditos(post_supplier_payment(abono, MAPEO)) == {102: Money(50000)}

    def test_otro_medio_cae_en_por_clasificar(self):
        # Suponer banco dejaría el saldo del libro en desacuerdo con el del
        # banco, y eso se descubre semanas después conciliando.
        abono = SupplierPaymentRef(id=3, date=HOY, amount=Money(50000), method="other")
        asiento = post_supplier_payment(abono, MAPEO)

        assert creditos(asiento) == {POR_CLASIFICAR: Money(50000)}
        assert [linea.memo for linea in asiento.lines if linea.credit.is_positive] == [
            UNCLASSIFIED
        ]

    def test_un_abono_de_cero_no_deja_asiento(self):
        abono = SupplierPaymentRef(id=4, date=HOY, amount=Money.zero(), method="cash")

        assert post_supplier_payment(abono, MAPEO) is None


# ---------------------------------------------------------------- el mapeo


class TestElMapeo:
    def test_dice_si_un_papel_tiene_cuenta_propia(self):
        # Lo usa la pantalla del mapeo para pintar en rojo lo que falta antes de
        # que caiga en 1.9.99.
        assert MAPEO.is_mapped(SALE, CASH)
        # 'receivable' —la venta a crédito— todavía no tiene cuenta en este
        # mapeo, y por eso caería en 1.9.99.
        assert not MAPEO.is_mapped(SALE, RECEIVABLE)

    def test_el_papel_de_venta_lleva_la_tarifa_adentro(self):
        assert sales_role(TRECE) == "sales_13"
        assert sales_role(CERO) == "sales_0"
        assert sales_role(TaxRate.percent(1)) == "sales_1"

    def test_una_tarifa_con_decimales_no_se_pierde(self):
        assert sales_role(TaxRate.percent("2.5")) == "sales_2.5"

    def test_el_diez_por_ciento_no_sale_en_notacion_cientifica(self):
        # `Decimal.normalize()` escribe 10 como 1E+1, y el papel habría quedado
        # en 'sales_1E+1': todas las ventas al 10 % a «por clasificar», sin que
        # nada avise.
        assert sales_role(TaxRate.percent(10)) == "sales_10"


# ------------------------------------------------------------------ periodos


class TestElPeriodo:
    def test_un_periodo_abierto_deja_escribir(self):
        assert_open(Period(2026, 9), date(2026, 9, 12))

    def test_uno_cerrado_no(self):
        with pytest.raises(PeriodClosed) as fallo:
            assert_open(Period(2026, 8, CLOSED), date(2026, 8, 31))
        assert (fallo.value.year, fallo.value.month) == (2026, 8)

    def test_un_mes_que_todavia_no_existe_nace_abierto(self):
        # La primera venta de octubre crea el periodo de octubre.
        assert_open(None, date(2026, 10, 1))

    def test_is_closed_lo_dice_sin_comparar_cadenas(self):
        assert Period(2026, 8, CLOSED).is_closed
        assert not Period(2026, 9).is_closed
