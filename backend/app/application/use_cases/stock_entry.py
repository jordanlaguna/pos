"""
Recibir mercadería y anular una recepción.

La entrada puede traer productos que **todavía no existen** —es lo normal al
leer el XML de una factura de proveedor—, así que este caso de uso crea
productos además de mover inventario. Todo dentro de la misma transacción: si la
línea 7 falla, el producto que creó la línea 3 tampoco queda.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.repositories import (
    ProductRepository,
    StockEntryRepository,
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
from app.domain.stock_entry import (
    EntryLine,
    check_cancellable,
    check_source,
    entry_total,
    entry_units,
)


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


@dataclass(frozen=True)
class EntryRequest:
    document_number: str | None
    supplier: str | None
    source: str
    user_id: int
    notes: str | None
    lines: list[RequestedEntryLine]


@dataclass(frozen=True)
class RegisteredEntry:
    id_entry: int
    products_created: int
    units_added: int
    total_cost: Money


class RegisterStockEntry:
    def __init__(
        self,
        *,
        products: ProductRepository,
        entries: StockEntryRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._products = products
        self._entries = entries
        self._uow = uow
        self._clock = clock

    def __call__(self, request: EntryRequest) -> RegisteredEntry:
        if not request.lines:
            raise EmptyEntry()
        check_source(request.source)

        # Una misma factura cargada dos veces duplica el inventario en silencio,
        # que es justo el error que este caso de uso tiene que hacer imposible.
        # Solo cuentan las aplicadas: una anulada libera su número, que es como
        # se repite una carga que salió mal.
        if request.document_number:
            if self._entries.applied_with_document(request.document_number) is not None:
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
                    )
                )

            total = entry_total(lineas)
            id_entry = self._entries.add(
                document_number=request.document_number,
                supplier=request.supplier,
                source=request.source,
                user_id=request.user_id,
                notes=request.notes,
                total_cost=total,
                created_at=ahora,
                lines=lineas,
            )
            for linea in lineas:
                self._products.adjust_stock(linea.product_id, +linea.quantity)

            self._uow.commit()

        return RegisteredEntry(
            id_entry=id_entry,
            products_created=creados,
            units_added=entry_units(lineas),
            total_cost=total,
        )


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
