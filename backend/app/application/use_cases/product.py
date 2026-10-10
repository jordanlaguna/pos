"""
La ficha del producto: dar de alta, editar y borrar (F15, T-1502).

Vivía en `crud_product.py` y pasa a la aplicación por una razón que no es de
capas: desde F15 **el alta mueve existencias** —la existencia inicial del
formulario es un movimiento de apertura en el kárdex (RF-94)— y ninguna
existencia se mueve fuera de un caso de uso. Lo demás —el código de barras
repetido, la categoría donde se cuelga, la tarifa que sale del código, la
partida arancelaria— se muda tal cual, con las pruebas de caracterización que
ya tenía por HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.ports.clock import Clock
from app.application.ports.inventory import KardexReader
from app.application.ports.repositories import (
    CategoryRepository,
    ProductRepository,
    UnitOfWork,
)
from app.application.use_cases.move_stock import MoveStock
from app.domain.categories import check_can_hold_products
from app.domain.errors import BarcodeTaken, CategoryNeedsSubcategory, DomainError
from app.domain.fe_export import check_tariff_heading
from app.domain.inventory import OPENING
from app.domain.money import Money
from app.domain.product import clean_changes, resolve_tax


class ProductNotFound(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


class CategoryNotFound(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"la categoría {category_id} no existe")
        self.category_id = category_id


class CategoryInactive(DomainError):
    """Una categoría que el dueño sacó de circulación: colgarle un producto nuevo
    lo esconde. Los que ya estaban se quedan; eso es distinto de dejar entrar uno."""

    def __init__(self, category_id: int, name: str) -> None:
        super().__init__(f"la categoría {name} está desactivada")
        self.category_id = category_id
        self.name = name


class CategoryCannotHoldProducts(DomainError):
    """RN-6, con el nombre de la categoría para que la frase lo diga."""

    def __init__(self, category_id: int, name: str, children: int) -> None:
        super().__init__(f"la categoría {name} tiene {children} subcategorías")
        self.category_id = category_id
        self.name = name
        self.children = children


class ProductHasSales(DomainError):
    """Borrar un producto ya vendido dejaría facturas apuntando a la nada."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} ya tiene ventas")
        self.product_id = product_id


class ProductHasMovements(DomainError):
    """Un producto con kárdex no se borra (F15): la foránea lo impediría de todos
    modos, con un 500. Se deja en cero y se retira."""

    def __init__(self, product_id: int, movements: int) -> None:
        super().__init__(f"el producto {product_id} tiene {movements} movimientos")
        self.product_id = product_id
        self.movements = movements


class BranchRequired(DomainError):
    """Sin sucursal activa no hay dónde abrir la existencia inicial."""

    def __init__(self) -> None:
        super().__init__("no hay sucursal donde abrir la existencia")


@dataclass(frozen=True)
class ProductRequest:
    name: str
    description: str | None
    price: Money
    barcode: str
    category_id: int
    created_at: datetime
    user_id: int
    #: Dónde se abre la existencia inicial (RF-94): la sucursal de la sesión.
    #: Nulo cuando la compañía no tiene ninguna, que solo estorba con stock.
    branch_id: int | None
    stock: int = 0
    cabys_code: str | None = None
    #: Entre 0 y 1; nulo es «la tasa configurada» (RN-9). Con `tax_code` se ignora.
    tax_rate: float | None = None
    tax_code: str | None = None
    unit_of_measure: str | None = None
    tariff_heading: str | None = None


@dataclass(frozen=True)
class RegisteredProduct:
    id_product: int


def _categoria_para_colgar(categories: CategoryRepository, category_id: int) -> None:
    """RN-6: el producto va en la hoja del árbol, y la hoja tiene que estar activa."""
    categoria = categories.get(category_id)
    if categoria is None:
        raise CategoryNotFound(category_id)
    if not categoria.is_active:
        raise CategoryInactive(category_id, categoria.name)
    try:
        check_can_hold_products(category_id, categoria.active_children)
    except CategoryNeedsSubcategory as e:
        raise CategoryCannotHoldProducts(category_id, categoria.name, e.children) from None


class RegisterProduct:
    def __init__(
        self,
        *,
        products: ProductRepository,
        categories: CategoryRepository,
        uow: UnitOfWork,
        clock: Clock,
        stock: MoveStock,
    ) -> None:
        self._products = products
        self._categories = categories
        self._uow = uow
        self._clock = clock
        self._stock = stock

    def __call__(self, request: ProductRequest) -> RegisteredProduct:
        # Todo lo que puede decir que no, antes de escribir.
        codigo = (request.barcode or "").strip()
        if self._products.barcode_taken(codigo):
            raise BarcodeTaken(codigo)
        _categoria_para_colgar(self._categories, request.category_id)
        tax_code, tax_rate = resolve_tax(request.tax_code, request.tax_rate)
        partida = check_tariff_heading(request.tariff_heading)
        if request.stock and request.branch_id is None:
            raise BranchRequired()

        with self._uow:
            # Nace en cero y la apertura le pone lo suyo, por la misma vía que
            # cualquier otro movimiento: desde F15 nadie escribe `stock` a mano.
            id_product = self._products.create(
                name=request.name,
                description=request.description or request.name,
                price=request.price,
                barcode=codigo,
                category_id=request.category_id,
                created_at=request.created_at,
                cabys_code=request.cabys_code,
                tax_rate=tax_rate,
                tax_code=tax_code,
                unit_of_measure=request.unit_of_measure,
                tariff_heading=partida,
            )
            if request.stock:
                self._stock(
                    product_id=id_product,
                    branch_id=request.branch_id,
                    delta=request.stock,
                    kind=OPENING,
                    # A costo cero: no se conoce hasta la primera compra (RN-54).
                    unit_cost=Money.zero(),
                    source_type="product",
                    source_id=id_product,
                    user_id=request.user_id,
                    moved_at=self._clock.now(),
                )
            self._uow.commit()
        return RegisteredProduct(id_product=id_product)


class UpdateProduct:
    def __init__(
        self,
        *,
        products: ProductRepository,
        categories: CategoryRepository,
        uow: UnitOfWork,
    ) -> None:
        self._products = products
        self._categories = categories
        self._uow = uow

    def __call__(self, product_id: int, changes: dict) -> None:
        producto = self._products.get(product_id)
        if producto is None:
            raise ProductNotFound(product_id)

        cambios = clean_changes(product_id, changes)

        # Un código de barras repetido rompe el escaneo: dos productos distintos
        # responderían al mismo pitido del lector.
        codigo = cambios.get("barcode")
        if codigo and self._products.barcode_taken(codigo, except_product_id=product_id):
            raise BarcodeTaken(codigo)

        # Mover de categoría pasa por la misma regla que crear (RN-6). Solo si
        # de verdad cambia: revalidar la que ya tiene haría que un cambio de
        # precio fallara por una categoría que se desactivó después.
        nueva = cambios.get("category_id")
        if nueva is not None and nueva != producto.category_id:
            _categoria_para_colgar(self._categories, nueva)

        # El código de Hacienda manda sobre la tarifa (RN-76): si viene, la
        # reescribe aunque el formulario haya mandado otra. Vaciarlo **no** toca
        # la tarifa: el producto sigue cobrando lo que cobraba.
        if cambios.get("tax_code"):
            cambios["tax_code"], cambios["tax_rate"] = resolve_tax(cambios["tax_code"], None)
        if "tariff_heading" in cambios:
            cambios["tariff_heading"] = check_tariff_heading(cambios["tariff_heading"])

        with self._uow:
            self._products.update(product_id, cambios)
            self._uow.commit()


class DeleteProduct:
    def __init__(
        self, *, products: ProductRepository, kardex: KardexReader, uow: UnitOfWork
    ) -> None:
        self._products = products
        self._kardex = kardex
        self._uow = uow

    def __call__(self, product_id: int) -> None:
        if self._products.get(product_id) is None:
            raise ProductNotFound(product_id)
        if self._products.has_sales(product_id):
            raise ProductHasSales(product_id)
        movimientos = self._kardex.count_for(product_id)
        if movimientos:
            raise ProductHasMovements(product_id, movimientos)

        with self._uow:
            self._products.delete(product_id)
            self._uow.commit()
