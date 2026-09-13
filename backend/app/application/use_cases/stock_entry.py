"""
Recibir mercadería y anular una recepción.

La entrada puede traer productos que **todavía no existen** —es lo normal al
leer el XML de una factura de proveedor—, así que este caso de uso crea
productos además de mover inventario. Todo dentro de la misma transacción: si la
línea 7 falla, el producto que creó la línea 3 tampoco queda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.application.ports.clock import Clock
from app.application.ports.repositories import (
    ProductRepository,
    StockEntryRepository,
    SupplierRepository,
    UnitOfWork,
)
from app.domain.errors import (
    AlreadyCancelled,
    BarcodeTaken,
    DomainError,
    DuplicateDocument,
    LineWithoutProduct,
)
from app.domain.money import Money
from app.domain.purchases import due_date as fecha_de_vencimiento
from app.domain.purchases import weighted_average_cost
from app.domain.stock_entry import (
    EntryLine,
    check_cancellable,
    check_source,
    entry_tax,
    entry_total,
    entry_units,
)
from app.domain.tax import TaxRate


class EntryNotFound(DomainError):
    def __init__(self, entry_id: int) -> None:
        super().__init__(f"la entrada {entry_id} no existe")
        self.entry_id = entry_id


class EmptyEntry(DomainError):
    def __init__(self) -> None:
        super().__init__("la entrada no tiene líneas")


class ProductNotFoundInEntry(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


class MissingBarcode(DomainError):
    def __init__(self, index: int) -> None:
        super().__init__(f"la línea {index} crea un producto sin código de barras")
        self.index = index


class SupplierNotFound(DomainError):
    def __init__(self, supplier_id: int) -> None:
        super().__init__(f"el proveedor {supplier_id} no existe")
        self.supplier_id = supplier_id


class SupplierInactive(DomainError):
    """Se quiso comprarle a un proveedor desactivado (RF-41).

    No se reactiva solo: desactivarlo fue una decisión, y una compra nueva a
    nombre de alguien con quien se dejó de trabajar suele ser un proveedor mal
    elegido en la lista.
    """

    def __init__(self, supplier_id: int, name: str) -> None:
        super().__init__(f"el proveedor {name} está desactivado")
        self.supplier_id = supplier_id
        self.name = name


@dataclass(frozen=True)
class NewProduct:
    name: str
    description: str | None
    price: Money
    barcode: str
    category_id: int


@dataclass(frozen=True)
class RequestedEntryLine:
    """Una línea: o apunta a un producto que existe, o trae uno para crear."""

    quantity: int
    unit_cost: Money
    product_id: int | None = None
    new_product: NewProduct | None = None
    #: El impuesto **del documento del proveedor** (RN-53). En cero cuando la
    #: entrada no viene de una factura electrónica.
    tax_rate: TaxRate = field(default_factory=TaxRate.zero)
    tax_amount: Money = field(default_factory=Money.zero)


@dataclass(frozen=True)
class EntryRequest:
    document_number: str | None
    supplier: str | None
    source: str
    user_id: int
    notes: str | None
    lines: list[RequestedEntryLine]

    # ------------------------------------------------------- compra (F10)
    #
    # Sin `supplier_id` esto es una entrada de las de siempre y nada de lo de
    # abajo se usa (RN-52): no genera cuenta por pagar ni crédito fiscal.
    supplier_id: int | None = None
    document_key: str | None = None
    #: La del documento, que no es la de carga. El vencimiento se cuenta desde
    #: acá, porque es lo que el proveedor va a cobrar.
    document_date: date | None = None
    #: 'cash' | 'credit'. Cualquier otra cosa se trata como contado, igual que
    #: en el lector de XML: no se inventa una deuda que nadie va a cobrar.
    payment_terms: str = "cash"
    #: Los días de plazo. Si no vienen, se usa el habitual del proveedor.
    payment_terms_days: int | None = None


@dataclass(frozen=True)
class RegisteredEntry:
    id_entry: int
    products_created: int
    units_added: int
    total_cost: Money
    #: Lo que hace de esto una compra. `total_cost` sigue siendo subtotal más
    #: impuesto, como antes de F10.
    subtotal: Money = Money.zero()
    tax: Money = Money.zero()
    due_date: date | None = None


class RegisterStockEntry:
    def __init__(
        self,
        *,
        products: ProductRepository,
        entries: StockEntryRepository,
        uow: UnitOfWork,
        clock: Clock,
        suppliers: SupplierRepository | None = None,
    ) -> None:
        self._products = products
        self._entries = entries
        self._uow = uow
        self._clock = clock
        # Opcional a propósito: una entrada sin proveedor no lo necesita, y las
        # pruebas de lo que ya existía no tienen que aprender un puerto nuevo.
        self._suppliers = suppliers

    def __call__(self, request: EntryRequest) -> RegisteredEntry:
        if not request.lines:
            raise EmptyEntry()
        check_source(request.source)

        proveedor = self._proveedor(request)

        # Una misma factura cargada dos veces duplica el inventario en silencio,
        # que es justo el error que este caso de uso tiene que hacer imposible.
        # Solo cuentan las aplicadas: una anulada libera su número, que es como
        # se repite una carga que salió mal.
        #
        # Desde F10 se compara **por proveedor**: la factura 1234 de un
        # mayorista no tiene nada que ver con la 1234 de otro, y compararlas
        # rechazaría una compra legítima.
        if request.document_number:
            repetida = self._entries.applied_with_document(
                request.document_number, request.supplier_id
            )
            if repetida is not None:
                raise DuplicateDocument(request.document_number)

        ahora = self._clock.now()

        with self._uow:
            lineas: list[EntryLine] = []
            creados = 0

            for indice, pedida in enumerate(request.lines, start=1):
                if pedida.product_id:
                    if self._products.get(pedida.product_id) is None:
                        raise ProductNotFoundInEntry(pedida.product_id)
                    product_id = pedida.product_id

                elif pedida.new_product is not None:
                    nuevo = pedida.new_product
                    codigo = (nuevo.barcode or "").strip()
                    if not codigo:
                        raise MissingBarcode(indice)
                    if self._products.barcode_taken(codigo):
                        raise BarcodeTaken(codigo)

                    product_id = self._products.create(
                        name=nuevo.name,
                        description=nuevo.description or nuevo.name,
                        price=nuevo.price,
                        barcode=codigo,
                        category_id=nuevo.category_id,
                        created_at=ahora,
                    )
                    creados += 1

                else:
                    raise LineWithoutProduct(indice)

                # El constructor valida cantidad y costo. El número de línea para
                # el mensaje lo pone quien traduce a HTTP, que es el que sabe en
                # qué orden venían.
                lineas.append(
                    EntryLine(
                        product_id=product_id,
                        quantity=pedida.quantity,
                        unit_cost=pedida.unit_cost,
                        tax_rate=pedida.tax_rate,
                        tax_amount=pedida.tax_amount,
                    )
                )

            subtotal = entry_total(lineas)
            impuesto = entry_tax(lineas)
            total = subtotal + impuesto
            vence = self._vencimiento(request, proveedor, ahora.date())

            id_entry = self._entries.add(
                document_number=request.document_number,
                # El nombre se copia aunque haya `supplier_id`: así la compra lo
                # recuerda si después se desactiva al proveedor o se le corrige
                # la razón social.
                supplier=request.supplier or (proveedor.name if proveedor else None),
                source=request.source,
                user_id=request.user_id,
                notes=request.notes,
                total_cost=total,
                created_at=ahora,
                lines=lineas,
                supplier_id=request.supplier_id,
                document_key=request.document_key,
                document_date=request.document_date,
                payment_terms="credit" if vence else "cash",
                due_date=vence,
                subtotal=subtotal,
                tax=impuesto,
            )

            # El costo **antes** que el stock, y las dos cosas en el mismo paso
            # por línea: si un producto aparece dos veces en la misma factura, el
            # segundo promedio tiene que ver las existencias que dejó el primero.
            #
            # Sin comprobar que el producto exista, a diferencia de la anulación:
            # acá o se validó arriba o se acaba de crear. Un `if` de más sería
            # una rama que ninguna prueba puede alcanzar, y eso es lo que la
            # cobertura al 100 % existe para no dejar pasar.
            for linea in lineas:
                producto = self._products.get(linea.product_id)
                self._products.update_cost(
                    linea.product_id,
                    weighted_average_cost(
                        producto.stock, producto.cost, linea.quantity, linea.unit_cost
                    ),
                )
                self._products.adjust_stock(linea.product_id, +linea.quantity)

            self._uow.commit()

        return RegisteredEntry(
            id_entry=id_entry,
            products_created=creados,
            units_added=entry_units(lineas),
            total_cost=total,
            subtotal=subtotal,
            tax=impuesto,
            due_date=vence,
        )

    # ------------------------------------------------------------- compra

    def _proveedor(self, request: EntryRequest):
        """El proveedor de la compra, comprobado. `None` si es una entrada."""
        if request.supplier_id is None or self._suppliers is None:
            return None

        proveedor = self._suppliers.get(request.supplier_id)
        if proveedor is None:
            raise SupplierNotFound(request.supplier_id)
        if not proveedor.is_active:
            raise SupplierInactive(proveedor.id, proveedor.name)
        return proveedor

    def _vencimiento(self, request: EntryRequest, proveedor, hoy: date) -> date | None:
        """Cuándo vence, o `None` si es de contado.

        El plazo sale de la compra si lo trae, y si no del habitual del
        proveedor: es lo que evita teclear «30» en cada factura del mismo
        mayorista. Un plazo de cero días es contado aunque digan crédito —una
        deuda que vence el mismo día no es una deuda—.
        """
        if proveedor is None or request.payment_terms != "credit":
            return None

        dias = (
            request.payment_terms_days
            if request.payment_terms_days is not None
            else proveedor.payment_terms_days
        )
        if not dias or dias <= 0:
            return None
        return fecha_de_vencimiento(request.document_date or hoy, dias)


class CancelStockEntry:
    """
    Anula una recepción y devuelve el stock.

    Se comprueba **todo** antes de tocar nada: si una sola línea no se puede
    revertir —porque parte ya se vendió— no se revierte ninguna. Revertir a
    medias dejaría un inventario peor que el que había.
    """

    def __init__(
        self,
        *,
        products: ProductRepository,
        entries: StockEntryRepository,
        uow: UnitOfWork,
    ) -> None:
        self._products = products
        self._entries = entries
        self._uow = uow

    def __call__(self, entry_id: int) -> int:
        entrada = self._entries.get(entry_id)
        if entrada is None:
            raise EntryNotFound(entry_id)
        if entrada.status == "anulada":
            raise AlreadyCancelled(entry_id)

        lineas = self._entries.lines_of(entry_id)

        for linea in lineas:
            producto = self._products.get(linea.product_id)
            # Si el producto ya no existe no hay stock que devolver, y tampoco
            # hay nada que impida anular.
            if producto is not None:
                check_cancellable(linea.product_id, producto.stock, linea.quantity)

        with self._uow:
            for linea in lineas:
                if self._products.get(linea.product_id) is not None:
                    self._products.adjust_stock(linea.product_id, -linea.quantity)
            self._entries.mark_cancelled(entry_id)
            self._uow.commit()

        return entry_id
