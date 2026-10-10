"""
La toma física: abrir, contar, aplicar y descartar (F15, RN-100).

Se abre por sucursal, entera o acotada a una categoría —una raíz incluye a sus
hijas—. Cada línea guarda **lo que decía el sistema en el momento de contar**
y lo que se contó; la diferencia es entre esos dos, y lo que se venda entre
contar y aplicar no la contamina porque ya quedó en el kárdex por su lado. Al
aplicar, cada diferencia se vuelve un ajuste con el motivo del sistema «toma
física», y la suma valorada deja **un** asiento: al gasto si faltó, al ingreso
si sobró. La aplicada queda cerrada; la abierta se puede descartar sin tocar
nada.

En una sucursal no pueden coexistir dos abiertas que compartan productos: la
segunda contaría contra lo que la primera va a cambiar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.ports.clock import Clock
from app.application.ports.inventory import StockCountRepository, StockLevelRepository
from app.application.ports.ledger import Ledger, NullLedger
from app.application.ports.repositories import (
    CategoryRepository,
    ProductRepository,
    UnitOfWork,
)
from app.application.use_cases.move_stock import MoveStock
from app.domain.errors import DomainError
from app.domain.inventory import (
    COUNT,
    COUNT_APPLIED,
    COUNT_DISCARDED,
    COUNT_OPEN,
    CountScope,
    check_count_scope,
    check_counted_quantity,
    count_difference,
    scopes_overlap,
)
from app.domain.ledger import StockCountDocument
from app.domain.money import Money


class CountNotFound(DomainError):
    def __init__(self, count_id: int) -> None:
        super().__init__(f"la toma {count_id} no existe")
        self.count_id = count_id


class CountNotOpen(DomainError):
    """Ya se aplicó o se descartó: ninguna de las dos se vuelve a abrir."""

    def __init__(self, count_id: int, status: str) -> None:
        super().__init__(f"la toma {count_id} está {status}")
        self.count_id = count_id
        self.status = status


class CountAlreadyOpen(DomainError):
    """Hay otra abierta en la sucursal que comparte productos con esta (RN-100)."""

    def __init__(self, count_id: int, branch_id: int, category_id: int | None) -> None:
        super().__init__(f"la toma {count_id} ya está abierta en la sucursal {branch_id}")
        self.count_id = count_id
        self.branch_id = branch_id
        self.category_id = category_id


class CountCategoryNotFound(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"la categoría {category_id} no existe")
        self.category_id = category_id


class CountHasNoLines(DomainError):
    """Aplicar una toma sin contar nada no ajusta nada: se descarta, no se aplica."""

    def __init__(self, count_id: int) -> None:
        super().__init__(f"la toma {count_id} no tiene líneas")
        self.count_id = count_id


class ProductNotFoundInCount(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


@dataclass(frozen=True)
class OpenCountRequest:
    #: Dónde se cuenta (RN-102): la sucursal de la sesión.
    branch_id: int
    #: Nulo es toda la sucursal.
    category_id: int | None
    user_id: int
    notes: str | None = None


@dataclass(frozen=True)
class OpenedCount:
    id_count: int


class OpenStockCount:
    def __init__(
        self,
        *,
        categories: CategoryRepository,
        counts: StockCountRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._categories = categories
        self._counts = counts
        self._uow = uow
        self._clock = clock

    def __call__(self, request: OpenCountRequest) -> OpenedCount:
        if request.category_id is not None and self._categories.get(request.category_id) is None:
            raise CountCategoryNotFound(request.category_id)

        # Con otra abierta que comparta productos, no (RN-100).
        nueva = CountScope(request.branch_id, request.category_id)
        arbol = self._categories.tree()
        for abierta in self._counts.open_in_branch(request.branch_id):
            if scopes_overlap(CountScope(abierta.branch_id, abierta.category_id), nueva, arbol):
                raise CountAlreadyOpen(abierta.id, abierta.branch_id, abierta.category_id)

        with self._uow:
            id_count = self._counts.add(
                branch_id=request.branch_id,
                category_id=request.category_id,
                opened_by=request.user_id,
                opened_at=self._clock.now(),
                notes=request.notes,
            )
            self._uow.commit()
        return OpenedCount(id_count=id_count)


@dataclass(frozen=True)
class RecordedLine:
    product_id: int
    system_qty: int
    counted_qty: int
    difference: int


class RecordCountLine:
    """Contar un producto: lo que decía el sistema se lee **en ese momento**,
    bajo el candado del nivel, y se guarda junto a lo contado."""

    def __init__(
        self,
        *,
        products: ProductRepository,
        categories: CategoryRepository,
        counts: StockCountRepository,
        levels: StockLevelRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._products = products
        self._categories = categories
        self._counts = counts
        self._levels = levels
        self._uow = uow
        self._clock = clock

    def __call__(
        self,
        count_id: int,
        *,
        product_id: int,
        counted_qty: int,
        user_id: int,
        lot_id: int | None = None,
    ) -> RecordedLine:
        check_counted_quantity(counted_qty)
        toma = self._counts.get(count_id)
        if toma is None:
            raise CountNotFound(count_id)
        if toma.status != COUNT_OPEN:
            raise CountNotOpen(count_id, toma.status)

        arbol = self._categories.tree()
        with self._uow:
            retratos = self._products.lock([product_id])
            if product_id not in retratos:
                raise ProductNotFoundInCount(product_id)
            check_count_scope(
                CountScope(toma.branch_id, toma.category_id),
                product_id,
                retratos[product_id].category_id,
                arbol,
            )
            # Lo que decía el sistema AL CONTAR (RN-100), con la fila del nivel
            # bloqueada: ni una venta a mitad de lectura lo cambia.
            sistema = self._levels.lock(product_id, toma.branch_id)
            self._counts.record_line(
                count_id,
                product_id=product_id,
                lot_id=lot_id,
                system_qty=sistema,
                counted_qty=counted_qty,
                counted_at=self._clock.now(),
                counted_by=user_id,
            )
            self._uow.commit()

        return RecordedLine(
            product_id=product_id,
            system_qty=sistema,
            counted_qty=counted_qty,
            difference=count_difference(sistema, counted_qty),
        )


@dataclass(frozen=True)
class AppliedCount:
    id_count: int
    #: Cuántas líneas dejaron movimiento: las que cuadraron no.
    adjustments: int
    #: La suma de las diferencias valoradas, con signo. Es lo que asienta.
    difference_cost: Money


class ApplyStockCount:
    """Cada diferencia pasa a ser un ajuste en el kárdex, y la suma, un asiento.

    Si entre contar y aplicar se vendió más de lo que la toma iba a quitar —se
    contaron 8 donde había 10 y después se vendieron 9—, el ajuste dejaría la
    existencia bajo cero y `MoveStock` lo rechaza: la toma entera se revierte y
    hay que volver a contar ese producto, que es lo honesto.
    """

    def __init__(
        self,
        *,
        products: ProductRepository,
        counts: StockCountRepository,
        uow: UnitOfWork,
        clock: Clock,
        stock: MoveStock,
        ledger: Ledger | None = None,
    ) -> None:
        self._products = products
        self._counts = counts
        self._uow = uow
        self._clock = clock
        self._stock = stock
        self._ledger = ledger or NullLedger()

    def __call__(self, count_id: int, *, user_id: int) -> AppliedCount:
        with self._uow:
            aplicada = self.apply(count_id, user_id=user_id)
            self._uow.commit()
        return aplicada

    def apply(self, count_id: int, *, user_id: int) -> AppliedCount:
        """La aplicación comprobada y escrita, **sin confirmar**, para que la
        bitácora entre en la misma transacción."""
        toma = self._counts.get(count_id)
        if toma is None:
            raise CountNotFound(count_id)
        if toma.status != COUNT_OPEN:
            raise CountNotOpen(count_id, toma.status)
        lineas = self._counts.lines_of(count_id)
        if not lineas:
            raise CountHasNoLines(count_id)

        momento = self._clock.now()
        # Todos de una y en orden de id (plan §15.1); los productos de una toma
        # no se pueden haber borrado: las líneas los sostienen.
        retratos = self._products.lock([linea.product_id for linea in lineas])

        total = Money.zero()
        ajustes = 0
        for indice, linea in enumerate(lineas, start=1):
            diferencia = count_difference(linea.system_qty, linea.counted_qty)
            if diferencia == 0:
                continue
            # Al promedio del momento, como una salida (RN-100).
            costo = retratos[linea.product_id].cost
            self._stock(
                product_id=linea.product_id,
                branch_id=toma.branch_id,
                delta=diferencia,
                kind=COUNT,
                unit_cost=costo,
                source_type="stock_count",
                source_id=count_id,
                source_line=indice,
                lot_id=linea.lot_id,
                user_id=user_id,
                moved_at=momento,
            )
            total = total + costo * diferencia
            ajustes += 1

        self._counts.close(count_id, status=COUNT_APPLIED, closed_by=user_id, closed_at=momento)
        # Un asiento por la suma (RN-100), dentro de la misma transacción.
        self._ledger.record_stock_count(StockCountDocument(id=count_id, date=momento.date()), total)
        return AppliedCount(id_count=count_id, adjustments=ajustes, difference_cost=total)


@dataclass(frozen=True)
class DiscardedCount:
    id_count: int


class DiscardStockCount:
    """Descartar una abierta: solo cambia el estado, no toca nada."""

    def __init__(self, *, counts: StockCountRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._counts = counts
        self._uow = uow
        self._clock = clock

    def __call__(self, count_id: int, *, user_id: int) -> DiscardedCount:
        with self._uow:
            descartada = self.apply(count_id, user_id=user_id)
            self._uow.commit()
        return descartada

    def apply(self, count_id: int, *, user_id: int) -> DiscardedCount:
        toma = self._counts.get(count_id)
        if toma is None:
            raise CountNotFound(count_id)
        if toma.status != COUNT_OPEN:
            raise CountNotOpen(count_id, toma.status)
        self._counts.close(
            count_id, status=COUNT_DISCARDED, closed_by=user_id, closed_at=self._clock.now()
        )
        return DiscardedCount(id_count=count_id)
