"""
Las notas: cuándo hay, qué referencian y con qué motivo (RN-89, T-725).

**Una nota siempre referencia un comprobante emitido**, y lo que decide si hay
nota es ese comprobante, no la configuración de hoy. Devolver algo de una venta
que salió como tiquete o factura emite una nota de crédito aunque después se
haya apagado la facturación; devolver algo de una venta que no fue comprobante
no emite nada, porque no hay qué referenciar.

**El motivo lo pone el flujo, no el cajero.** Es el código de referencia del
catálogo de Hacienda (`docs/hacienda/costa-rica/casos-de-emision.md`), y de él
este sistema usa por ahora dos:

- `06` **devolución de mercancía**, entera o parcial;
- `01` **anula**, que solo existe entero y solo sobre un comprobante que todavía
  no tiene devoluciones.

Anular y devolver todo reponen lo mismo y reembolsan lo mismo; lo que cambia es
lo que se le dice a Hacienda: «este comprobante no debió existir» contra «la
venta existió y la mercadería volvió».

**Las notas por monto** (T-726) no mueven mercadería, mueven plata: la ND se
cobra y la NC se reembolsa en el momento, porque sin venta a crédito no hay saldo
del cliente donde dejarlas. Ajustan líneas de la venta con el motivo `02`,
corrige monto; lo demás está en `AMOUNT_NOTE_REASONS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import (
    AnnulAfterReturn,
    AnnulMustBeFull,
    CreditExceedsLine,
    InvalidNoteAmount,
    InvalidNoteReason,
    InvalidNoteType,
    NoteNeedsDocument,
)
from .fe_document_type import CREDIT_NOTE, DEBIT_NOTE
from .money import Money
from .tax import TaxRate

#: El catálogo de códigos de referencia de Hacienda, completo. El `03` no está:
#: el catálogo lo salta.
ANNULS: Final = "01"
CORRECTS_AMOUNT: Final = "02"
REFERS_TO_OTHER: Final = "04"
REPLACES_CONTINGENCY: Final = "05"
GOODS_RETURN: Final = "06"
REPLACES_DOCUMENT: Final = "07"
ENDORSED_INVOICE: Final = "08"
FINANCIAL_CREDIT: Final = "09"
FINANCIAL_DEBIT: Final = "10"
NON_RESIDENT_SUPPLIER: Final = "11"
LATER_EXEMPTION: Final = "12"
OTHER: Final = "99"

REFERENCE_CODES: Final = (
    ANNULS,
    CORRECTS_AMOUNT,
    REFERS_TO_OTHER,
    REPLACES_CONTINGENCY,
    GOODS_RETURN,
    REPLACES_DOCUMENT,
    ENDORSED_INVOICE,
    FINANCIAL_CREDIT,
    FINANCIAL_DEBIT,
    NON_RESIDENT_SUPPLIER,
    LATER_EXEMPTION,
    OTHER,
)


@dataclass(frozen=True)
class Note:
    """El tipo de la nota y el motivo con que referencia al original."""

    document_type: str
    reference_code: str


def credit_note_for_return(sale_document_type: str | None, *, annul: bool) -> Note | None:
    """La nota de crédito de una devolución, o nada si la venta no fue comprobante."""
    if sale_document_type is None:
        return None
    return Note(CREDIT_NOTE, ANNULS if annul else GOODS_RETURN)


def check_annul(
    sale_id: int,
    *,
    sold: dict[int, int],
    already_returned: dict[int, int],
    requested: dict[int, int],
) -> None:
    """Anular es devolver **todo**, y solo lo que nunca se devolvió.

    Las cantidades van por producto y ya sumadas: una línea pedida dos veces
    cuenta una sola.
    """
    if any(cantidad > 0 for cantidad in already_returned.values()):
        raise AnnulAfterReturn(sale_id)
    vendido = {producto: cantidad for producto, cantidad in sold.items() if cantidad > 0}
    if requested != vendido:
        raise AnnulMustBeFull(sale_id)


# ------------------------------------------------------- notas por monto

#: Los motivos que cada nota por monto admite en un mostrador de contado.
#:
#: Solo `02`, corrige monto. Las financieras —`10` en la ND, `09` en la NC— son
#: intereses y descuentos por pronto pago, que solo existen con venta a crédito
#: (T-729). La NC por exoneración posterior —`12`— devuelve solo impuesto y lleva
#: la exoneración en la línea: es su propia tarea (T-732).
AMOUNT_NOTE_REASONS: Final = {
    DEBIT_NOTE: (CORRECTS_AMOUNT,),
    CREDIT_NOTE: (CORRECTS_AMOUNT,),
}


def check_amount_note(
    document_type: object, reference_code: object, *, sale_document_type: str | None
) -> Note:
    """La nota por monto que se pidió, si se puede emitir sobre esa venta.

    La venta manda primero: sin comprobante no hay nota posible, sea cual sea el
    tipo que se pidió.
    """
    if sale_document_type is None:
        raise NoteNeedsDocument()
    if document_type not in AMOUNT_NOTE_REASONS:
        raise InvalidNoteType(document_type)
    if reference_code not in AMOUNT_NOTE_REASONS[document_type]:
        raise InvalidNoteReason(document_type, reference_code)
    return Note(str(document_type), str(reference_code))


@dataclass(frozen=True)
class NoteLine:
    """Una línea de la nota: a qué producto de la venta, cuánto y con qué tarifa."""

    product_id: int
    subtotal: Money
    tax: Money
    tax_rate: TaxRate

    @property
    def total(self) -> Money:
        return self.subtotal + self.tax


def split_amount(product_id: int, amount: Money, rate: TaxRate) -> NoteLine:
    """El monto que se cobra o se devuelve, partido en base e impuesto.

    Se escribe **con impuesto** porque es lo que pasa de mano en mano. La base es
    el monto entre uno más la tarifa; el impuesto, la tarifa sobre la base —la
    misma cuenta que una línea de venta—. El total puede quedar un céntimo por
    encima o por debajo de lo escrito, y el que vale es el que sale de acá: es el
    que cuadra con su base y su tarifa.
    """
    if not amount.is_positive:
        raise InvalidNoteAmount(product_id)
    base = Money(amount.amount / (1 + rate.value))
    return NoteLine(product_id=product_id, subtotal=base, tax=rate.apply(base), tax_rate=rate)


def credit_available(
    *, charged: Money, debited: Money, returned: Money, credited: Money
) -> Money:
    """Lo que queda de una línea para acreditarle.

    Lo cobrado, más lo que le subieron las ND, menos lo devuelto, menos las NC
    anteriores. Todo con impuesto: es plata que salió o entró de verdad.
    """
    return charged + debited - returned - credited


def check_credit(product_id: int, requested: Money, available: Money) -> None:
    """Una NC no reembolsa más de lo que queda de la línea."""
    if requested > available:
        raise CreditExceedsLine(product_id, available, requested)


__all__ = [
    "AMOUNT_NOTE_REASONS",
    "ANNULS",
    "CORRECTS_AMOUNT",
    "ENDORSED_INVOICE",
    "FINANCIAL_CREDIT",
    "FINANCIAL_DEBIT",
    "GOODS_RETURN",
    "LATER_EXEMPTION",
    "NON_RESIDENT_SUPPLIER",
    "Note",
    "NoteLine",
    "OTHER",
    "REFERENCE_CODES",
    "REFERS_TO_OTHER",
    "REPLACES_CONTINGENCY",
    "REPLACES_DOCUMENT",
    "check_amount_note",
    "check_annul",
    "check_credit",
    "credit_available",
    "credit_note_for_return",
    "split_amount",
]
