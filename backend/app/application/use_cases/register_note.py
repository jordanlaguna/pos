"""
Emitir una nota por monto sobre un comprobante (RF-77, T-726).

Es la nota que no mueve mercadería: le sube el monto a una línea (ND) o se lo
baja (NC), con el motivo `02`, corrige monto. **La plata se mueve en el
momento** —lo decidió el usuario el 2026-09-26—: la ND se cobra con su medio de
pago y la NC se reembolsa de la gaveta, como una devolución. Sin venta a crédito
no hay saldo del cliente donde dejarlas.

Tiene la forma de la devolución, a propósito: se valida todo, se escribe al
final, el asiento va dentro de la misma transacción (RN-59), y la tarifa de cada
línea es **la de su venta** (RN-12), no la configurada hoy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.numbering import NumberedDocument
from app.application.use_cases.number_document import SOURCE_NOTE, NumberDocument
from app.application.ports.repositories import (
    NoteRepository,
    ReturnRepository,
    SaleRepository,
    SettingsRepository,
    UnitOfWork,
)
from app.application.use_cases.register_return import SaleNotFound
from app.domain.errors import DocumentTypeNotEnabled, DomainError
from app.domain.fe_document_type import CREDIT_NOTE, DEBIT_NOTE
from app.domain.fe_notes import (
    NoteLine,
    check_amount_note,
    check_credit,
    credit_available,
    split_amount,
)
from app.domain.ledger import ReturnDocument, SoldDocument, SoldLine
from app.domain.money import Money
from app.domain.sale import check_payment_method
from app.domain.tax import TaxRate


class EmptyNote(DomainError):
    def __init__(self) -> None:
        super().__init__("la nota no ajusta ninguna línea")


class NoteWithoutReason(DomainError):
    def __init__(self) -> None:
        super().__init__("hace falta el motivo de la nota")


class NoteLineNotInSale(DomainError):
    """Una línea de la nota sobre un producto que la venta no llevaba."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"la venta no llevaba el producto {product_id}")
        self.product_id = product_id


@dataclass(frozen=True)
class RequestedNoteLine:
    product_id: int
    #: Lo que se cobra o se devuelve por esa línea, **con impuesto**.
    amount: Money


@dataclass(frozen=True)
class NoteRequest:
    sale_id: int
    user_id: int
    #: `'02'` nota de débito o `'03'` nota de crédito.
    document_type: str
    #: El motivo de Hacienda. Hoy solo `'02'`, corrige monto.
    reference_code: str
    reason: str
    lines: list[RequestedNoteLine]
    #: Cómo se cobra la ND. La NC no lo lleva: sale de la gaveta.
    payment_method: str | None = None


@dataclass(frozen=True)
class RegisteredNote:
    id_note: int
    document_type: str
    reference_code: str
    subtotal: Money
    tax: Money
    total: Money
    lines: list[NoteLine]
    #: La nota numerada (T-704, T-705). Nula solo sin numeración conectada.
    einvoice: NumberedDocument | None = None


class RegisterAmountNote:
    def __init__(
        self,
        *,
        sales: SaleRepository,
        returns: ReturnRepository,
        notes: NoteRepository,
        settings: SettingsRepository,
        uow: UnitOfWork,
        clock: Clock,
        ledger: Ledger | None = None,
        numbering: NumberDocument | None = None,
    ) -> None:
        self._sales = sales
        self._returns = returns
        self._notes = notes
        self._settings = settings
        self._uow = uow
        self._clock = clock
        self._ledger = ledger or NullLedger()
        self._numbering = numbering

    def __call__(self, request: NoteRequest) -> RegisteredNote:
        venta = self._sales.get(request.sale_id)
        if venta is None:
            raise SaleNotFound(request.sale_id)

        # La venta y el motivo primero: sobre algo que no fue comprobante no hay
        # nota posible, y eso es lo que hay que decir antes que cualquier monto.
        nota = check_amount_note(
            request.document_type,
            request.reference_code,
            sale_document_type=venta.document_type,
        )
        # La ND se puede apagar en Configuración (RN-88); la NC no, y
        # `document_types` ya la trae siempre.
        if nota.document_type not in self._settings.document_types():
            raise DocumentTypeNotEnabled(nota.document_type)
        if not request.reason or not request.reason.strip():
            raise NoteWithoutReason()

        es_debito = nota.document_type == DEBIT_NOTE
        # La ND se cobra, así que su medio de pago es el conjunto cerrado de la
        # venta (T-1104). La NC sale de la gaveta y no lleva ninguno.
        if es_debito:
            check_payment_method(request.payment_method)
        medio = request.payment_method if es_debito else None

        # Una línea pedida dos veces es una sola, con los montos sumados.
        pedido: dict[int, Money] = {}
        for linea in request.lines:
            pedido[linea.product_id] = pedido.get(linea.product_id, Money.zero()) + linea.amount
        if not pedido:
            raise EmptyNote()

        vendido = self._sales.sold_quantities(request.sale_id)
        precios = self._sales.sold_prices(request.sale_id)
        tarifas = self._sales.sold_tax_rates(request.sale_id)
        devuelto = self._returns.returned_quantities(request.sale_id)
        ajustes = self._notes.adjustments(request.sale_id)
        # La tarifa del encabezado, para las ventas anteriores a la 006, que no la
        # tienen en la línea y llevan una sola (igual que la devolución).
        del_encabezado = TaxRate.of_sale(
            Money(venta.subtotal), Money(venta.tax), default=self._settings.tax_rate()
        )

        lineas: list[NoteLine] = []
        for producto, monto in pedido.items():
            if producto not in vendido:
                raise NoteLineNotInSale(producto)
            tarifa = tarifas.get(producto, del_encabezado)
            linea = split_amount(producto, monto, tarifa)
            if nota.document_type == CREDIT_NOTE:
                # Una NC no reembolsa más de lo que el cliente pagó por la línea.
                sumado, restado = ajustes.get(producto, (Money.zero(), Money.zero()))
                check_credit(
                    producto,
                    linea.total,
                    credit_available(
                        charged=tarifa.add_to(precios[producto] * vendido[producto]),
                        debited=sumado,
                        returned=tarifa.add_to(precios[producto] * devuelto.get(producto, 0)),
                        credited=restado,
                    ),
                )
            lineas.append(linea)

        subtotal = Money.sum(l.subtotal for l in lineas)
        impuesto = Money.sum(l.tax for l in lineas)
        total = Money.sum(l.total for l in lineas)
        # La nota siempre es un comprobante: el emisor antes de la transacción.
        emisor = self._numbering.prepare() if self._numbering is not None else None

        with self._uow:
            # Una sola lectura del reloj para la nota y su asiento.
            momento = self._clock.now()
            id_note = self._notes.add(
                sale_id=request.sale_id,
                user_id=request.user_id,
                document_type=nota.document_type,
                reference_code=nota.reference_code,
                reason=request.reason.strip(),
                payment_method=medio,
                subtotal=subtotal,
                tax=impuesto,
                total=total,
                created_at=momento,
                lines=lineas,
            )
            # Cada nota en su serie —`02` la ND, `03` la NC—, con la nota.
            comprobante = (
                self._numbering.number(
                    emisor,
                    source_type=SOURCE_NOTE,
                    source_id=id_note,
                    document_type=nota.document_type,
                    issued_at=momento,
                )
                if emisor is not None and self._numbering is not None
                else None
            )

            # Sin costo: no hay mercadería, así que no hay par costo / inventario.
            vendidas = [
                SoldLine(subtotal=l.subtotal, tax=l.tax, tax_rate=l.tax_rate, quantity=1)
                for l in lineas
            ]
            if es_debito:
                self._ledger.record_debit_note(
                    SoldDocument(id=id_note, date=momento.date(), payment_method=str(medio)),
                    vendidas,
                )
            else:
                self._ledger.record_credit_note(
                    ReturnDocument(id=id_note, date=momento.date()), vendidas
                )
            self._uow.commit()

        return RegisteredNote(
            id_note=id_note,
            document_type=nota.document_type,
            reference_code=nota.reference_code,
            subtotal=subtotal,
            tax=impuesto,
            total=total,
            lines=lineas,
            einvoice=comprobante,
        )
