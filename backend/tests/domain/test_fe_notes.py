"""
Las notas: la de crédito de una devolución (RN-89, T-725) y las notas por monto
(T-726).

Lo que importa es que la nota la decide **el comprobante original** y no la
configuración de hoy, que anular sea todo o nada, y que una NC por monto no
reembolse más de lo que queda de la línea.
"""

from __future__ import annotations

import pytest

from app.domain.errors import (
    AnnulAfterReturn,
    AnnulMustBeFull,
    CreditExceedsLine,
    InvalidNoteAmount,
    InvalidNoteReason,
    InvalidNoteType,
    NoteNeedsDocument,
)
from app.domain.fe_document_type import CREDIT_NOTE, INVOICE, TICKET
from app.domain.fe_notes import (
    AMOUNT_NOTE_REASONS,
    ANNULS,
    CORRECTS_AMOUNT,
    FINANCIAL_CREDIT,
    FINANCIAL_DEBIT,
    GOODS_RETURN,
    LATER_EXEMPTION,
    REFERENCE_CODES,
    Note,
    check_amount_note,
    check_annul,
    check_credit,
    credit_available,
    credit_note_for_return,
    split_amount,
)
from app.domain.money import Money
from app.domain.tax import TaxRate


def test_el_catalogo_de_hacienda_salta_el_03():
    assert "03" not in REFERENCE_CODES
    assert len(REFERENCE_CODES) == 12
    assert (ANNULS, GOODS_RETURN) == ("01", "06")


class TestLaNotaDeUnaDevolucion:
    @pytest.mark.parametrize("original", [TICKET, INVOICE])
    def test_devolver_de_un_comprobante_es_devolucion_de_mercancia(self, original):
        assert credit_note_for_return(original, annul=False) == Note(CREDIT_NOTE, GOODS_RETURN)

    def test_anular_es_anular(self):
        assert credit_note_for_return(TICKET, annul=True) == Note(CREDIT_NOTE, ANNULS)

    @pytest.mark.parametrize("anular", [True, False])
    def test_una_venta_que_no_fue_comprobante_no_tiene_nota(self, anular):
        # No hay qué referenciar.
        assert credit_note_for_return(None, annul=anular) is None


class TestAnular:
    VENDIDO = {1: 3, 2: 1}

    def test_todo_lo_vendido_y_nada_devuelto_se_puede(self):
        check_annul(7, sold=self.VENDIDO, already_returned={}, requested={1: 3, 2: 1})

    def test_una_venta_con_devoluciones_ya_no_se_anula(self):
        with pytest.raises(AnnulAfterReturn) as e:
            check_annul(7, sold=self.VENDIDO, already_returned={2: 1}, requested={1: 3})
        assert e.value.sale_id == 7

    def test_una_devolucion_registrada_en_cero_no_cuenta(self):
        check_annul(7, sold=self.VENDIDO, already_returned={2: 0}, requested={1: 3, 2: 1})

    @pytest.mark.parametrize("pedido", [{1: 3}, {1: 2, 2: 1}, {1: 3, 2: 1, 9: 1}])
    def test_anular_es_devolverla_entera(self, pedido):
        with pytest.raises(AnnulMustBeFull):
            check_annul(7, sold=self.VENDIDO, already_returned={}, requested=pedido)

    def test_una_linea_vendida_en_cero_no_hay_que_devolverla(self):
        check_annul(7, sold={1: 3, 2: 0}, already_returned={}, requested={1: 3})


# ------------------------------------------------------- notas por monto (T-726)

TRECE = TaxRate("0.13")


class TestLaNotaPorMonto:
    def test_corregir_el_monto_con_una_nd_o_una_nc(self):
        for tipo in ("02", "03"):
            nota = check_amount_note(tipo, CORRECTS_AMOUNT, sale_document_type="01")
            assert (nota.document_type, nota.reference_code) == (tipo, "02")

    def test_sin_comprobante_no_hay_nota_aunque_el_tipo_sea_bueno(self):
        # La venta manda primero: no hay qué referenciar.
        with pytest.raises(NoteNeedsDocument):
            check_amount_note("02", "02", sale_document_type=None)

    @pytest.mark.parametrize("tipo", ["01", "04", "99", None])
    def test_solo_nd_y_nc(self, tipo):
        with pytest.raises(InvalidNoteType):
            check_amount_note(tipo, "02", sale_document_type="04")

    @pytest.mark.parametrize(
        "tipo, motivo",
        [
            # Las financieras son de la venta a crédito (T-729).
            ("02", FINANCIAL_DEBIT),
            ("03", FINANCIAL_CREDIT),
            # La exoneración posterior es su propia tarea (T-732).
            ("03", LATER_EXEMPTION),
            # Devolver mercadería o anular es la devolución, no una nota por monto.
            ("03", "06"),
            ("03", "01"),
        ],
    )
    def test_los_motivos_que_un_mostrador_de_contado_no_emite(self, tipo, motivo):
        with pytest.raises(InvalidNoteReason):
            check_amount_note(tipo, motivo, sale_document_type="01")

    def test_hoy_es_un_solo_motivo_para_cada_una(self):
        assert AMOUNT_NOTE_REASONS == {"02": ("02",), "03": ("02",)}


class TestPartirElMonto:
    def test_el_monto_trae_el_impuesto_adentro(self):
        linea = split_amount(7, Money(1130), TRECE)
        assert (linea.subtotal, linea.tax, linea.total) == (Money(1000), Money(130), Money(1130))
        assert linea.tax_rate == TRECE

    def test_puede_quedar_un_centimo_arriba_y_el_que_vale_es_ese(self):
        # 500 / 1,13 = 442,477… → 442,48 y 57,52: justo 500. Con 100 queda 88,50 +
        # 11,51 = 100,01, que es el que cuadra con su base y su tarifa.
        assert split_amount(1, Money(500), TRECE).total == Money(500)
        cien = split_amount(1, Money(100), TRECE)
        assert (cien.subtotal, cien.tax, cien.total) == (Money("88.50"), Money("11.51"), Money("100.01"))

    def test_una_tarifa_en_cero_es_todo_base(self):
        linea = split_amount(1, Money(250), TaxRate.zero())
        assert (linea.subtotal, linea.tax) == (Money(250), Money(0))

    @pytest.mark.parametrize("monto", [Money(0), Money(-5)])
    def test_el_monto_tiene_que_ser_positivo(self, monto):
        with pytest.raises(InvalidNoteAmount) as error:
            split_amount(4, monto, TRECE)
        assert error.value.product_id == 4


class TestLoQueQuedaDeLaLinea:
    def test_lo_cobrado_mas_las_nd_menos_lo_devuelto_y_las_nc(self):
        assert credit_available(
            charged=Money(2260), debited=Money(113), returned=Money(1130), credited=Money(200)
        ) == Money(1043)

    def test_se_puede_acreditar_hasta_lo_que_queda_y_no_mas(self):
        check_credit(1, Money(1043), Money(1043))
        with pytest.raises(CreditExceedsLine) as error:
            check_credit(1, Money("1043.01"), Money(1043))
        assert (error.value.product_id, error.value.available) == (1, Money(1043))

