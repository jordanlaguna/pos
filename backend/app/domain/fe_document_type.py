"""
Los siete comprobantes, cuáles emite cada compañía, y cuál sale de una venta
(RN-85, RN-87, RN-88).

**Los siete** tienen su código en el consecutivo y ninguno es una sigla: es el
mismo dato que ocupa las posiciones 9 y 10, así que tener además un `"FE"` sería
tener dos nombres para lo mismo.

**Cada compañía elige cuáles emite** (RN-88). El sistema es para cualquier
negocio: un supermercado no exporta y una distribuidora no emite tiquetes. La
elección vive en la configuración y se **sanea al leer**, no se valida al
guardar: `enabled_types` nunca lanza y nunca devuelve un juego con el que no se
pueda vender, que es la misma política que `mergeSettings` en el POS.

**De una venta** salen dos hoy, y los distingue el receptor. La factura (`01`)
exige uno con nombre e identificación; el tiquete (`04`) no, y por eso es lo que
se le entrega al cliente de contado. Con cliente, la venta sale como factura
salvo que el cajero la deje en tiquete. El tipo se decide **al vender** y queda
en la venta: el consecutivo va por tipo (RN-37) y la clave lo lleva adentro.

Los otros nacen de su propio flujo (RN-87): la nota de crédito, de una
devolución (`fe_notes`); la de débito, de la factura abierta (T-726); la factura
de compra, de una compra (T-728); el recibo de pago, de cobrar una venta a
crédito (T-729). La de exportación sí es una venta y se sumará a
`COUNTER_TYPES` con T-727.
"""

from __future__ import annotations

from typing import Final

from .errors import DocumentTypeNotEnabled, InvalidSaleDocumentType, InvoiceNeedsReceiver

INVOICE: Final = "01"
DEBIT_NOTE: Final = "02"
CREDIT_NOTE: Final = "03"
TICKET: Final = "04"
PURCHASE_INVOICE: Final = "08"
EXPORT_INVOICE: Final = "09"
PAYMENT_RECEIPT: Final = "10"

#: Los siete, en el orden en que se muestran en Configuración: primero lo que
#: se vende, después lo que corrige, al final lo que nace de otro lado.
ALL_TYPES: Final = (
    TICKET,
    INVOICE,
    EXPORT_INVOICE,
    CREDIT_NOTE,
    DEBIT_NOTE,
    PURCHASE_INVOICE,
    PAYMENT_RECEIPT,
)

#: Los que ya tienen un flujo que los emita. **Es una lista y no una casilla**:
#: cuando llegue la ND (T-726) se agrega acá, y en Configuración su casilla
#: empieza a moverse sola. Mover antes la de un tipo sin flujo sería una casilla
#: que promete algo que no pasa (RN-88).
AVAILABLE: Final = frozenset({TICKET, INVOICE, CREDIT_NOTE})

#: Los que no se apagan. Devolver una venta emitida tiene que pasar por una nota
#: de crédito; sin ella, la devolución no tendría respaldo fiscal (RN-88).
ALWAYS_ON: Final = frozenset({CREDIT_NOTE})

#: Con los que nace una compañía: los que Hacienda pide para certificarse y
#: para operar. La ND nace encendida aunque todavía no tenga flujo, para que el
#: día que lo tenga no haya que ir a encenderla.
DEFAULT_ENABLED: Final = frozenset({TICKET, INVOICE, CREDIT_NOTE, DEBIT_NOTE})

#: Los que se emiten al cobrar. La FEE entra con T-727.
COUNTER_TYPES: Final = (INVOICE, TICKET)


def enabled_types(raw: object) -> frozenset[str]:
    """Lo que la compañía emite, a partir de lo guardado, venga como venga.

    Ausente —una compañía que nunca tocó la lista— es la de fábrica. Se tiran
    los códigos que no son de Hacienda, se agrega lo que no se apaga, y si no
    quedó con qué vender —ni tiquete ni factura— se vuelve a la de fábrica: una
    fila escrita a mano no puede dejar al negocio sin poder cobrar.
    """
    if not isinstance(raw, (list, tuple)):
        return DEFAULT_ENABLED
    elegidos = {codigo for codigo in raw if codigo in ALL_TYPES}
    if not elegidos & set(COUNTER_TYPES):
        return DEFAULT_ENABLED
    return frozenset(elegidos | ALWAYS_ON)


def suggested_type(*, has_receiver: bool, enabled: frozenset[str]) -> str:
    """El que se emite si nadie elige otro.

    Con cliente, factura si está encendida; si no, tiquete. Si el tiquete está
    apagado —una distribuidora que solo factura— es factura igual, y la venta
    va a necesitar cliente: eso lo dice `document_type_for`, no esto.
    """
    if has_receiver and INVOICE in enabled:
        return INVOICE
    return TICKET if TICKET in enabled else INVOICE


def document_type_for(
    requested: object,
    *,
    einvoicing: bool,
    enabled: frozenset[str],
    has_receiver: bool,
) -> str | None:
    """El tipo con el que se guarda la venta, o nulo si no lleva.

    El orden importa y cada paso tiene su porqué:

    1. **Un valor desconocido se rechaza siempre**, esté o no activa la
       facturación. Es un cliente roto, no una preferencia.
    2. **Con la facturación apagada, nulo.** Lo pedido se ignora en vez de
       rechazarse: el dueño puede apagarla con una caja abierta, y rechazar la
       venta sería cobrarle el cambio de configuración al cliente del mostrador.
    3. **Sin tipo pedido, la sugerencia**, con lo que la compañía tiene
       encendido. Es lo que manda una pantalla que se abrió antes de activar la
       facturación.
    4. **Un tipo apagado, no** (RN-88). La pantalla no lo ofrece, así que llegar
       acá es una pantalla vieja o un cliente del API.
    5. **Factura sin receptor, no.**
    """
    if requested is not None and requested not in COUNTER_TYPES:
        raise InvalidSaleDocumentType(requested)
    if not einvoicing:
        return None
    if requested is None:
        requested = suggested_type(has_receiver=has_receiver, enabled=enabled)
    elif requested not in enabled:
        raise DocumentTypeNotEnabled(requested)
    if requested == INVOICE and not has_receiver:
        raise InvoiceNeedsReceiver()
    return str(requested)


__all__ = [
    "ALL_TYPES",
    "ALWAYS_ON",
    "AVAILABLE",
    "COUNTER_TYPES",
    "CREDIT_NOTE",
    "DEBIT_NOTE",
    "DEFAULT_ENABLED",
    "EXPORT_INVOICE",
    "INVOICE",
    "PAYMENT_RECEIPT",
    "PURCHASE_INVOICE",
    "TICKET",
    "document_type_for",
    "enabled_types",
    "suggested_type",
]
