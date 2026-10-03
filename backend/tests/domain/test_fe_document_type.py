"""
Los siete comprobantes, cuáles emite cada compañía y cuál sale de una venta
(RN-85, RN-88).

La que importa de la venta es la factura sin receptor: es el caso del
supermercado, el cliente de contado al que el sistema le imprimía «Factura
electrónica». La que importa de la configuración es que ninguna lista guardada
deje al negocio sin poder vender.
"""

from __future__ import annotations

import pytest

from app.domain.errors import (
    DocumentTypeNotEnabled,
    InvalidSaleDocumentType,
    InvoiceNeedsReceiver,
)
from app.domain.fe_document_type import (
    ALL_TYPES,
    ALWAYS_ON,
    AVAILABLE,
    COUNTER_TYPES,
    CREDIT_NOTE,
    DEBIT_NOTE,
    DEFAULT_ENABLED,
    EXPORT_INVOICE,
    INVOICE,
    PAYMENT_RECEIPT,
    PURCHASE_INVOICE,
    TICKET,
    document_type_for,
    enabled_types,
    suggested_type,
)
from app.domain.hacienda import RAICES

TODOS = DEFAULT_ENABLED
SOLO_FACTURA = frozenset({INVOICE, CREDIT_NOTE})
SOLO_TIQUETE = frozenset({TICKET, CREDIT_NOTE})


class TestLosSiete:
    def test_son_los_del_anexo_con_su_codigo(self):
        assert {
            TICKET: "TiqueteElectronico",
            INVOICE: "FacturaElectronica",
            EXPORT_INVOICE: "FacturaElectronicaExportacion",
            CREDIT_NOTE: "NotaCreditoElectronica",
            DEBIT_NOTE: "NotaDebitoElectronica",
            PURCHASE_INVOICE: "FacturaElectronicaCompra",
            PAYMENT_RECEIPT: "ReciboElectronicoPago",
        } == {codigo: RAICES[codigo] for codigo in ALL_TYPES}

    def test_de_una_venta_salen_la_factura_y_el_tiquete(self):
        assert COUNTER_TYPES == (INVOICE, TICKET)

    def test_hoy_tienen_flujo_los_de_venta_y_la_nota_de_credito(self):
        # La ND entra con T-726, la FEE con T-727, la FEC con T-728, el REP con
        # T-729. Si esta prueba cambia es porque llegó uno de esos flujos.
        assert AVAILABLE == {TICKET, INVOICE, CREDIT_NOTE}

    def test_la_nota_de_credito_no_se_apaga(self):
        assert ALWAYS_ON == {CREDIT_NOTE}

    def test_de_fabrica_los_cuatro_de_la_certificacion(self):
        assert DEFAULT_ENABLED == {TICKET, INVOICE, CREDIT_NOTE, DEBIT_NOTE}


class TestLoQueEmiteLaCompania:
    """RN-88: se sanea al leer, nunca lanza, y nunca deja sin poder vender."""

    @pytest.mark.parametrize("guardado", [None, "01,04", {"01": True}, 7])
    def test_sin_lista_es_la_de_fabrica(self, guardado):
        assert enabled_types(guardado) == DEFAULT_ENABLED

    def test_respeta_lo_que_se_eligio(self):
        assert enabled_types(["01", "03"]) == {INVOICE, CREDIT_NOTE}

    def test_la_nota_de_credito_se_agrega_si_falta(self):
        assert enabled_types(["04"]) == {TICKET, CREDIT_NOTE}

    def test_tira_lo_que_no_es_de_hacienda(self):
        assert enabled_types(["04", "FE", "99", 4]) == {TICKET, CREDIT_NOTE}

    @pytest.mark.parametrize("guardado", [[], ["03"], ["02", "09"], ["FE"]])
    def test_sin_tiquete_ni_factura_vuelve_a_la_de_fabrica(self, guardado):
        # Una fila escrita a mano no puede dejar al negocio sin poder cobrar.
        assert enabled_types(guardado) == DEFAULT_ENABLED

    def test_guarda_lo_que_todavia_no_tiene_flujo(self):
        # La preferencia se conserva: el día que llegue el flujo, ya está.
        assert DEBIT_NOTE in enabled_types(["04", "02"])


class TestLaSugerencia:
    def test_sin_cliente_tiquete(self):
        assert suggested_type(has_receiver=False, enabled=TODOS) == TICKET

    def test_con_cliente_factura(self):
        assert suggested_type(has_receiver=True, enabled=TODOS) == INVOICE

    def test_con_cliente_y_la_factura_apagada_tiquete(self):
        assert suggested_type(has_receiver=True, enabled=SOLO_TIQUETE) == TICKET

    def test_con_el_tiquete_apagado_factura_aunque_no_haya_cliente(self):
        # Y la venta va a necesitar cliente: eso lo dice document_type_for.
        assert suggested_type(has_receiver=False, enabled=SOLO_FACTURA) == INVOICE


def tipo(pedido, *, activa=True, encendidos=TODOS, cliente=False):
    return document_type_for(
        pedido, einvoicing=activa, enabled=encendidos, has_receiver=cliente
    )


class TestConLaFacturacionActiva:
    def test_sin_pedir_nada_sale_la_sugerencia(self):
        # Una pantalla abierta antes de activar la facturación no manda tipo.
        assert tipo(None) == TICKET
        assert tipo(None, cliente=True) == INVOICE

    def test_el_cajero_puede_dejar_en_tiquete_a_un_cliente(self):
        assert tipo(TICKET, cliente=True) == TICKET

    def test_la_factura_con_cliente_sale(self):
        assert tipo(INVOICE, cliente=True) == INVOICE

    def test_la_factura_sin_cliente_no(self):
        with pytest.raises(InvoiceNeedsReceiver):
            tipo(INVOICE)

    def test_solo_factura_y_sin_cliente_la_venta_necesita_cliente(self):
        # La distribuidora que apagó el tiquete: sin cliente no hay qué emitir.
        with pytest.raises(InvoiceNeedsReceiver):
            tipo(None, encendidos=SOLO_FACTURA)

    @pytest.mark.parametrize(
        "pedido, encendidos", [(TICKET, SOLO_FACTURA), (INVOICE, SOLO_TIQUETE)]
    )
    def test_un_tipo_apagado_no(self, pedido, encendidos):
        with pytest.raises(DocumentTypeNotEnabled) as e:
            tipo(pedido, encendidos=encendidos, cliente=True)
        assert e.value.document_type == pedido


class TestConLaFacturacionApagada:
    @pytest.mark.parametrize("pedido", [None, INVOICE, TICKET])
    def test_la_venta_no_lleva_tipo(self, pedido):
        """Aunque se lo pidan: el dueño pudo apagarla con la caja abierta."""
        assert tipo(pedido, activa=False) is None

    def test_ni_la_factura_sin_cliente_se_rechaza(self):
        # No hay comprobante que emitir, así que no hay receptor que exigir.
        assert tipo(INVOICE, activa=False) is None


@pytest.mark.parametrize("malo", ["03", "1", "", "FE", 1, 4])
@pytest.mark.parametrize("activa", [True, False])
def test_un_tipo_que_el_mostrador_no_emite_se_rechaza_siempre(malo, activa):
    """Esté o no activa la facturación: es un cliente roto, no una preferencia."""
    with pytest.raises(InvalidSaleDocumentType) as e:
        tipo(malo, activa=activa, cliente=True)
    assert e.value.document_type == malo
