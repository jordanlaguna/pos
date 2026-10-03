"""
Las notas por monto, sin base de datos (RF-77, T-726).

La ND se cobra y la NC se reembolsa en el momento —lo decidió el usuario el
2026-09-26—. Lo que importa es de plata: que la NC no reembolse más de lo que
queda de la línea, que la devolución y la anulación no reembolsen dos veces lo
que ya reembolsó una nota, que el arqueo del turno las cuente, y que el asiento
vaya dentro de la transacción.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.application.use_cases.cash_session import BuildSessionReport
from app.application.use_cases.register_note import (
    EmptyNote,
    NoteLineNotInSale,
    NoteRequest,
    NoteWithoutReason,
    RegisterAmountNote,
    RequestedNoteLine,
)
from app.application.use_cases.register_return import (
    RegisterReturn,
    RequestedReturnLine,
    ReturnRequest,
    SaleNotFound,
)
from app.domain.errors import (
    AnnulAfterNote,
    CreditExceedsLine,
    DocumentTypeNotEnabled,
    InvalidNoteReason,
    InvalidSalePaymentMethod,
    NoteNeedsDocument,
    ReturnAfterCreditNote,
)
from app.domain.fe_document_type import CREDIT_NOTE, DEBIT_NOTE, INVOICE, TICKET
from app.domain.money import Money
from app.domain.sale import SaleLine
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeCashRepository,
    FakeNoteRepository,
    FakeProduct,
    FakeProductRepository,
    FakeReturnRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeUnitOfWork,
)
from .test_libro import LibroEspia

AHORA = datetime(2026, 9, 26, 15, 0, 0)
TRECE = TaxRate("0.13")
UNO = TaxRate("0.01")
ADMIN = 1


class Mundo:
    """Una venta de 2 arroces a ₡1 000 al 13 % y 1 café a ₡4 250 al 1 %."""

    def __init__(self, *, tipo: str | None = TICKET, encendidos=None) -> None:
        self.ventas = FakeSaleRepository()
        self.devoluciones = FakeReturnRepository()
        self.notas = FakeNoteRepository()
        self.caja = FakeCashRepository()
        self.libro = LibroEspia()
        self.uow = FakeUnitOfWork()
        self.reloj = FixedClock(AHORA)
        self.ajustes = FakeSettingsRepository(einvoicing=True, **({"document_types": encendidos} if encendidos else {})
        )
        self.productos = FakeProductRepository(
            [FakeProduct(1, "Arroz", Money(1000), stock=10), FakeProduct(2, "Café", Money(4250), stock=10)]
        )
        lineas = [
            SaleLine(product_id=1, unit_price=Money(1000), quantity=2, tax_rate=TRECE),
            SaleLine(product_id=2, unit_price=Money(4250), quantity=1, tax_rate=UNO),
        ]
        self.id_venta = self.ventas.add(
            sale_number="2026",
            client_id=None,
            user_id=ADMIN,
            subtotal=Money(6250),
            tax=Money("302.50"),
            total=Money("6552.50"),
            payment_method="Efectivo",
            cash_received=Money("6552.50"),
            change_given=Money(0),
            created_at=AHORA - timedelta(minutes=30),
            lines=lineas,
            document_type=tipo,
        )

    def nota(self) -> RegisterAmountNote:
        return RegisterAmountNote(
            sales=self.ventas,
            returns=self.devoluciones,
            notes=self.notas,
            settings=self.ajustes,
            uow=self.uow,
            clock=self.reloj,
            ledger=self.libro,
        )

    def devolucion(self) -> RegisterReturn:
        return RegisterReturn(
            sales=self.ventas,
            returns=self.devoluciones,
            notes=self.notas,
            products=self.productos,
            uow=self.uow,
            clock=self.reloj,
        )

    def turno(self):
        return BuildSessionReport(
            sales=self.ventas,
            returns=self.devoluciones,
            notes=self.notas,
            cash=self.caja,
            clock=self.reloj,
        )(
            session_id=1,
            user_id=ADMIN,
            opening=Money(10000),
            opened_at=AHORA - timedelta(hours=1),
            closed_at=None,
            counted=None,
        )


def pedir(mundo: Mundo, tipo: str, lineas, **cambios) -> NoteRequest:
    base = dict(
        sale_id=mundo.id_venta,
        user_id=ADMIN,
        document_type=tipo,
        reference_code="02",
        reason="se cobró mal el precio",
        lines=[RequestedNoteLine(producto, Money(monto)) for producto, monto in lineas],
        payment_method="Efectivo" if tipo == DEBIT_NOTE else None,
    )
    base.update(cambios)
    return NoteRequest(**base)


class TestLaNotaDeDebito:
    def test_se_cobra_con_su_medio_y_hereda_la_tarifa_de_la_linea(self):
        mundo = Mundo()
        hecha = mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))

        assert (hecha.document_type, hecha.reference_code) == (DEBIT_NOTE, "02")
        assert (hecha.subtotal, hecha.tax, hecha.total) == (Money(1000), Money(130), Money(1130))
        guardada = mundo.notas.notas[0]
        assert guardada.payment_method == "Efectivo"
        assert guardada.lines[0].tax_rate == TRECE
        assert mundo.uow.committed

    def test_con_tarifas_mezcladas_cada_linea_lleva_la_suya(self):
        mundo = Mundo()
        hecha = mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 113), (2, 101)]))
        tarifas = {l.product_id: l.tax_rate for l in hecha.lines}
        assert tarifas == {1: TRECE, 2: UNO}
        assert hecha.total == Money(214)

    def test_la_misma_linea_dos_veces_es_una_con_los_montos_sumados(self):
        mundo = Mundo()
        hecha = mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 565), (1, 565)]))
        assert len(hecha.lines) == 1
        assert hecha.total == Money(1130)

    def test_sin_medio_de_pago_valido_no_se_cobra(self):
        mundo = Mundo()
        with pytest.raises(InvalidSalePaymentMethod):
            mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)], payment_method="Cheque"))
        assert mundo.notas.notas == []

    def test_apagada_en_configuracion_no_se_emite(self):
        mundo = Mundo(encendidos=frozenset({TICKET, INVOICE, CREDIT_NOTE}))
        with pytest.raises(DocumentTypeNotEnabled):
            mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))

    def test_se_asienta_como_una_venta_sin_costo_dentro_de_la_transaccion(self):
        mundo = Mundo()
        hecha = mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))

        [(_, documento, lineas)] = mundo.libro.de("debit_note")
        assert (documento.id, documento.payment_method) == (hecha.id_note, "Efectivo")
        assert lineas[0].unit_cost is None
        assert mundo.libro.de("sale") == []


class TestLaNotaDeCreditoPorMonto:
    def test_se_reembolsa_de_la_gaveta_y_no_lleva_medio(self):
        mundo = Mundo()
        hecha = mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 565)]))

        assert hecha.document_type == CREDIT_NOTE
        assert mundo.notas.notas[0].payment_method is None
        [(_, documento, lineas)] = mundo.libro.de("credit_note")
        assert documento.id == hecha.id_note
        assert lineas[0].unit_cost is None

    def test_puede_acreditar_hasta_lo_que_se_cobro_y_no_mas(self):
        mundo = Mundo()
        # Dos arroces a ₡1 130 con impuesto: ₡2 260.
        mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 2260)]))
        with pytest.raises(CreditExceedsLine) as error:
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 1)]))
        assert error.value.available == Money(0)

    def test_lo_devuelto_y_las_nc_anteriores_bajan_lo_que_queda(self):
        mundo = Mundo()
        mundo.devolucion()(
            ReturnRequest(
                sale_id=mundo.id_venta,
                user_id=ADMIN,
                reason="no era",
                lines=[RequestedReturnLine(1, 1)],
            )
        )
        mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 130)]))
        # Quedan 2 260 − 1 130 − 130 = 1 000.
        with pytest.raises(CreditExceedsLine) as error:
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 1001)]))
        assert error.value.available == Money(1000)

    def test_una_nd_anterior_sube_lo_que_se_puede_acreditar(self):
        mundo = Mundo()
        mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))
        hecha = mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 3390)]))
        assert hecha.total == Money(3390)


class TestLoQueNoSeEmite:
    def test_sobre_una_venta_sin_comprobante(self):
        mundo = Mundo(tipo=None)
        with pytest.raises(NoteNeedsDocument):
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)]))

    def test_sobre_una_venta_que_no_existe(self):
        mundo = Mundo()
        with pytest.raises(SaleNotFound):
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)], sale_id=999))

    def test_con_un_motivo_que_un_mostrador_no_emite(self):
        mundo = Mundo()
        with pytest.raises(InvalidNoteReason):
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)], reference_code="09"))

    @pytest.mark.parametrize("motivo", ["", "   "])
    def test_sin_decir_por_que(self, motivo):
        mundo = Mundo()
        with pytest.raises(NoteWithoutReason):
            mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)], reason=motivo))

    def test_sin_lineas(self):
        mundo = Mundo()
        with pytest.raises(EmptyNote):
            mundo.nota()(pedir(mundo, CREDIT_NOTE, []))

    def test_sobre_un_producto_que_la_venta_no_llevaba(self):
        mundo = Mundo()
        with pytest.raises(NoteLineNotInSale) as error:
            mundo.nota()(pedir(mundo, DEBIT_NOTE, [(9, 100)]))
        assert error.value.product_id == 9
        assert mundo.notas.notas == []


class TestLaDevolucionDespuesDeUnaNota:
    """Sin esto la misma plata se reembolsaría dos veces."""

    def devolver(self, mundo: Mundo, lineas, **cambios):
        return mundo.devolucion()(
            ReturnRequest(
                sale_id=mundo.id_venta,
                user_id=ADMIN,
                reason="no era",
                lines=[RequestedReturnLine(p, c) for p, c in lineas],
                **cambios,
            )
        )

    def test_la_linea_con_nc_por_monto_ya_no_se_devuelve(self):
        mundo = Mundo()
        mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)]))
        with pytest.raises(ReturnAfterCreditNote) as error:
            self.devolver(mundo, [(1, 1)])
        assert error.value.product_id == 1

    def test_las_demas_lineas_si(self):
        mundo = Mundo()
        mundo.nota()(pedir(mundo, CREDIT_NOTE, [(1, 100)]))
        assert self.devolver(mundo, [(2, 1)]).total == Money("4292.50")

    def test_una_nd_no_impide_devolver(self):
        mundo = Mundo()
        mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 113)]))
        assert self.devolver(mundo, [(1, 1)]).total == Money(1130)

    def test_una_venta_con_notas_no_se_anula(self):
        mundo = Mundo()
        mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 113)]))
        with pytest.raises(AnnulAfterNote):
            self.devolver(mundo, [(1, 2), (2, 1)], annul=True)


class TestElArqueoDelTurno:
    def test_la_nd_en_efectivo_sube_el_esperado_y_la_nc_lo_baja(self):
        mundo = Mundo()
        antes = mundo.turno().expected
        mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))
        mundo.nota()(pedir(mundo, CREDIT_NOTE, [(2, 101)]))

        turno = mundo.turno()
        assert turno.expected == antes + Money(1130) - Money(101)
        assert (turno.debit_notes_total, turno.debit_notes_cash) == (Money(1130), Money(1130))
        assert turno.credit_notes_total == Money(101)

    def test_la_nd_con_tarjeta_se_cuenta_pero_no_entra_a_la_gaveta(self):
        mundo = Mundo()
        antes = mundo.turno().expected
        mundo.nota()(
            pedir(mundo, DEBIT_NOTE, [(1, 1130)], payment_method="Tarjeta de crédito")
        )
        turno = mundo.turno()
        assert turno.expected == antes
        assert (turno.debit_notes_total, turno.debit_notes_cash) == (Money(1130), Money(0))

    def test_las_notas_no_son_ventas(self):
        # El corte Z las muestra en su renglón, no mezcladas con lo vendido.
        mundo = Mundo()
        mundo.nota()(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))
        turno = mundo.turno()
        assert turno.sales_count == 1
        assert turno.sales_total == Money("6552.50")
