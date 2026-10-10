"""
Registrar una devolución.

Dos reglas mandan, y las dos son de plata:

1. **No se puede devolver más de lo que se llevó**, ni de una vez ni sumando
   varias parciales de la misma venta.
2. **Se reembolsa con la tasa de SU venta**, no con la configurada hoy. Si el
   dueño sube el IVA, lo que se devuelve por algo cobrado antes sigue siendo lo
   que se cobró.

Y una consecuencia que sí se veía en el sistema original: **el stock vuelve al
inventario**. Antes no volvía.

Desde T-725 la devolución de una venta que fue comprobante **es una nota de
crédito** (RN-89), y **anular es una devolución entera con otro motivo**: el
mismo camino, con `annul=True`. Así la plata, el inventario y el asiento de una
anulación son exactamente los de una devolución total, y no una segunda copia.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.numbering import NumberedDocument
from app.application.use_cases.move_stock import MoveStock
from app.application.use_cases.number_document import SOURCE_RETURN, NumberDocument
from app.application.ports.repositories import (
    NoteRepository,
    ProductRepository,
    ReturnRepository,
    SaleRepository,
    UnitOfWork,
)
from app.domain.errors import (
    AnnulAfterNote,
    DomainError,
    InvalidQuantity,
    ReturnAfterCreditNote,
)
from app.domain.fe_notes import check_annul, credit_note_for_return
from app.domain.inventory import RETURN, SALE_VOID
from app.domain.ledger import ReturnDocument, SoldLine
from app.domain.money import Money
from app.domain.returns import (
    ReturnLine,
    check_returnable,
    is_fully_returned,
    refund_totals,
)
from app.domain.tax import GENERAL_RATE, TaxRate


class SaleNotFound(DomainError):
    def __init__(self, sale_id: int) -> None:
        super().__init__(f"la venta {sale_id} no existe")
        self.sale_id = sale_id


class EmptyReturn(DomainError):
    def __init__(self) -> None:
        super().__init__("la devolución no tiene productos")


class MissingReason(DomainError):
    def __init__(self) -> None:
        super().__init__("hace falta el motivo de la devolución")


@dataclass(frozen=True)
class RequestedReturnLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class ReturnRequest:
    sale_id: int
    user_id: int
    reason: str
    lines: list[RequestedReturnLine]
    #: Dónde se devuelve, que no tiene por qué ser donde se vendió: la
    #: mercadería se repone acá (F15, RN-102). Del `bid` de la sesión.
    branch_id: int
    #: Anular el comprobante en vez de devolver mercadería (RN-89). Exige que
    #: la venta no tenga devoluciones y que se devuelva entera.
    annul: bool = False


@dataclass(frozen=True)
class RegisteredReturn:
    id_return: int
    total: Money
    lines: list[ReturnLine]
    is_full: bool
    #: `'03'` y el motivo cuando hubo nota de crédito; nulos cuando no.
    document_type: str | None = None
    reference_code: str | None = None
    #: La nota de crédito numerada, si la hubo (T-704, T-705).
    einvoice: NumberedDocument | None = None


class RegisterReturn:
    def __init__(
        self,
        *,
        sales: SaleRepository,
        returns: ReturnRepository,
        notes: NoteRepository,
        products: ProductRepository,
        uow: UnitOfWork,
        clock: Clock,
        stock: MoveStock,
        ledger: Ledger | None = None,
        numbering: NumberDocument | None = None,
    ) -> None:
        self._sales = sales
        self._returns = returns
        self._notes = notes
        self._products = products
        self._uow = uow
        self._clock = clock
        self._stock = stock
        self._ledger = ledger or NullLedger()
        self._numbering = numbering

    def __call__(self, request: ReturnRequest) -> RegisteredReturn:
        venta = self._sales.get(request.sale_id)
        if venta is None:
            raise SaleNotFound(request.sale_id)
        if not request.lines:
            raise EmptyReturn()
        if not request.reason or not request.reason.strip():
            raise MissingReason()

        vendido = self._sales.sold_quantities(request.sale_id)
        precios = self._sales.sold_prices(request.sale_id)
        tarifas = self._sales.sold_tax_rates(request.sale_id)
        # El costo con el que salió la mercadería (RN-63). Devolverla al
        # inventario por lo que cuesta hoy inventaría utilidad cada vez que el
        # proveedor sube el precio entre la venta y la devolución.
        costos = self._sales.sold_costs(request.sale_id)
        ya_devuelto = self._returns.returned_quantities(request.sale_id)
        # Lo que las notas por monto le cambiaron a cada línea (T-726).
        ajustes = self._notes.adjustments(request.sale_id)

        # Anular es todo o nada (RN-89), y se mira **antes** que las cantidades:
        # anular una venta a medio devolver es «ya tiene devoluciones», no «pidió
        # de más», aunque las dos cosas sean ciertas.
        if request.annul:
            pedido: dict[int, int] = {}
            for linea in request.lines:
                pedido[linea.product_id] = pedido.get(linea.product_id, 0) + linea.quantity
            check_annul(
                request.sale_id, sold=vendido, already_returned=ya_devuelto, requested=pedido
            )
            # Con una ND encima, anular no devolvería lo que se cobró de más; con
            # una NC, devolvería dos veces. Se corrige con otra nota (T-726).
            if ajustes:
                raise AnnulAfterNote(request.sale_id)

        # La tasa del ENCABEZADO de esta venta, reconstruida de sus montos. Desde
        # F5 es solo el respaldo: sirve para las ventas anteriores a la migración
        # 006, que no tienen tarifa en la línea y llevan una sola, así que el
        # cociente la reconstruye exacta. La general del IVA entra un escalón
        # más abajo, para las del WinForms que quedaron sin desglose.
        #
        # **No sirve cuando la venta mezcla tarifas**: ahí `tax / subtotal` es un
        # promedio, y devolver una sola línea con el promedio reembolsa de más o
        # de menos. Por eso lo primero que se mira es la tarifa de la línea.
        del_encabezado = TaxRate.of_sale(
            Money(venta.subtotal), Money(venta.tax), default=GENERAL_RATE
        )

        # Se valida TODO antes de escribir: o entra la devolución completa, o
        # ninguna.
        lineas: list[ReturnLine] = []
        for pedida in request.lines:
            if pedida.quantity <= 0:
                raise InvalidQuantity(pedida.quantity)
            check_returnable(pedida.product_id, vendido, ya_devuelto, pedida.quantity)
            # La devolución reembolsa el precio de la línea; con una NC por monto
            # encima, reembolsaría dos veces la misma plata (T-726).
            _, acreditado = ajustes.get(pedida.product_id, (Money.zero(), Money.zero()))
            if acreditado.is_positive:
                raise ReturnAfterCreditNote(pedida.product_id)
            lineas.append(
                ReturnLine(
                    product_id=pedida.product_id,
                    unit_price=precios[pedida.product_id],
                    quantity=pedida.quantity,
                    # Resuelta acá y nunca nula, igual que en la venta: lo que se
                    # guarda no puede depender de lo que esté configurado el día
                    # que alguien lea esta devolución.
                    tax_rate=tarifas.get(pedida.product_id, del_encabezado),
                )
            )

        totales = refund_totals(lineas, del_encabezado)

        # La nota la decide el comprobante ORIGINAL, no la configuración de hoy:
        # una venta que salió como tiquete emite su nota aunque después se haya
        # apagado la facturación, y una que no fue comprobante no tiene a qué
        # referirse.
        nota = credit_note_for_return(venta.document_type, annul=request.annul)
        # Como en la venta: el emisor antes de la transacción, y solo si hay nota.
        emisor = (
            self._numbering.prepare() if nota is not None and self._numbering is not None else None
        )

        with self._uow:
            # Una sola lectura del reloj para la devolución y su asiento.
            momento = self._clock.now()
            id_return = self._returns.add(
                sale_id=request.sale_id,
                user_id=request.user_id,
                reason=request.reason.strip(),
                subtotal=totales.subtotal,
                tax=totales.tax,
                total=totales.total,
                created_at=momento,
                lines=lineas,
                branch_id=request.branch_id,
                document_type=nota.document_type if nota else None,
                reference_code=nota.reference_code if nota else None,
            )
            # Lo que el sistema original no hacía: reponer. Desde F15 con su
            # fila en el kárdex, **al costo con que salió** (RN-98, RN-63): lo
            # que se vendió a 100 vuelve a 100 aunque hoy el promedio sea 120,
            # porque devolverlo a 120 inventaría utilidad. Una venta anterior a
            # F11 no tiene costo y repone a cero, que es «no se sabe». Anular
            # se ve como anulación, no como devolución.
            for indice, linea in enumerate(lineas, start=1):
                self._stock(
                    product_id=linea.product_id,
                    branch_id=request.branch_id,
                    delta=+linea.quantity,
                    kind=SALE_VOID if request.annul else RETURN,
                    unit_cost=costos.get(linea.product_id, Money.zero()),
                    source_type="return",
                    source_id=id_return,
                    source_line=indice,
                    user_id=request.user_id,
                    moved_at=momento,
                )

            # La NC lleva su propia serie, la `03` (nota 3), y se numera con la
            # devolución: si esto falla, no queda ni la devolución ni el número.
            comprobante = (
                self._numbering.number(
                    emisor,
                    source_type=SOURCE_RETURN,
                    source_id=id_return,
                    document_type=nota.document_type,
                    issued_at=momento,
                )
                if emisor is not None and self._numbering is not None and nota is not None
                else None
            )

            # El inverso de la venta, dentro de la misma transacción (RN-59).
            self._ledger.record_return(
                ReturnDocument(id=id_return, date=momento.date()),
                [
                    SoldLine(
                        subtotal=linea.subtotal,
                        tax=(linea.tax_rate or del_encabezado).apply(linea.subtotal),
                        tax_rate=linea.tax_rate or del_encabezado,
                        quantity=linea.quantity,
                        unit_cost=costos.get(linea.product_id),
                    )
                    for linea in lineas
                ],
            )
            self._uow.commit()

        despues = dict(ya_devuelto)
        for linea in lineas:
            despues[linea.product_id] = despues.get(linea.product_id, 0) + linea.quantity

        return RegisteredReturn(
            id_return=id_return,
            total=totales.total,
            lines=lineas,
            is_full=is_fully_returned(vendido, despues),
            document_type=nota.document_type if nota else None,
            reference_code=nota.reference_code if nota else None,
            einvoice=comprobante,
        )
