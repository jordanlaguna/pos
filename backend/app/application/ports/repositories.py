"""
Los repositorios, dichos desde adentro.

Cada método es una pregunta que un caso de uso necesita hacerle a los datos,
escrita en el idioma del negocio y no en el de la base: `reserve_stock`, no
`SELECT ... FOR UPDATE`. Que ese bloqueo exista —y que sea lo que impide que dos
cajas vendan la misma última unidad— es asunto del adaptador.

Los tipos que entran y salen son del dominio (`Money`, `SaleLine`) o primitivos.
Ninguna firma menciona una fila de SQLAlchemy: el día que la persistencia cambie,
esta carpeta no se toca.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.money import Money


class ProductSnapshot(Protocol):
    """Lo que la aplicación necesita saber de un producto para vender."""

    id_product: int
    name: str
    price: Money
    stock: int


class ProductRepository(Protocol):
    def get(self, product_id: int) -> ProductSnapshot | None: ...

    def get_by_barcode(self, barcode: str) -> ProductSnapshot | None: ...

    def lock_for_sale(self, product_ids: list[int]) -> dict[int, ProductSnapshot]:
        """
        Trae los productos y **los bloquea** hasta que termine la transacción.

        Es lo que impide que dos cajas vendan la última unidad a la vez. Devuelve
        solo los que existen; el caso de uso decide qué hacer con los que faltan.
        """
        ...

    def adjust_stock(self, product_id: int, delta: int) -> None:
        """Suma o resta existencias. Negativo al vender, positivo al devolver."""
        ...

    def barcode_taken(self, barcode: str) -> bool:
        """Si ya hay un producto con ese código."""
        ...

    def create(
        self,
        *,
        name: str,
        description: str,
        price: Money,
        barcode: str,
        category_id: int,
        created_at: datetime,
    ) -> int:
        """Da de alta un producto **sin existencias** y devuelve su id.

        Sin existencias a propósito: las pone la entrada de mercadería que lo
        está creando, en el mismo movimiento y por la misma vía que las de
        cualquier otro producto.
        """
        ...


class StockEntryRepository(Protocol):
    def get(self, entry_id: int): ...

    def applied_with_document(self, document_number: str):
        """La entrada **aplicada** que ya usó ese número de documento, si la hay.

        Solo las aplicadas: una anulada libera su número, que es como se repite
        una carga que salió mal.
        """
        ...

    def add(
        self,
        *,
        document_number: str | None,
        supplier: str | None,
        source: str,
        user_id: int,
        notes: str | None,
        total_cost: Money,
        created_at: datetime,
        lines: list,
    ) -> int: ...

    def lines_of(self, entry_id: int) -> list:
        """Las líneas de una entrada, para poder revertirlas al anular."""
        ...

    def mark_cancelled(self, entry_id: int) -> None: ...


class SaleRepository(Protocol):
    def add(
        self,
        *,
        sale_number: str,
        client_id: int | None,
        user_id: int,
        subtotal: Money,
        tax: Money,
        total: Money,
        payment_method: str,
        cash_received: Money,
        change_given: Money,
        created_at: datetime,
        lines: list,
    ) -> int:
        """Guarda la venta con sus líneas y devuelve su identificador."""
        ...

    def get(self, sale_id: int): ...

    def exists_with_number(self, sale_number: str) -> bool:
        """Si ya hay una venta con ese número de factura.

        El número es único por diseño: dos ventas con el mismo número son dos
        facturas con el mismo consecutivo, y eso Hacienda no lo perdona.
        """
        ...

    def sold_quantities(self, sale_id: int) -> dict[int, int]:
        """Cuántas unidades de cada producto llevaba la venta."""
        ...

    def sold_prices(self, sale_id: int) -> dict[int, Money]:
        """
        A qué precio se vendió cada producto **en esa venta**.

        Es el precio congelado en la línea, no el del catálogo de hoy: una
        devolución reembolsa lo que se cobró, y el precio pudo cambiar desde
        entonces.
        """
        ...

    def in_window(self, user_id: int, start: datetime, end: datetime) -> list:
        """Ventas de un cajero entre dos marcas. Es cómo se arma un turno."""
        ...


class ReturnRepository(Protocol):
    def returned_quantities(self, sale_id: int) -> dict[int, int]:
        """Cuántas unidades de la venta ya se devolvieron, sumando todas."""
        ...

    def add(
        self,
        *,
        sale_id: int,
        user_id: int,
        reason: str,
        total: Money,
        created_at: datetime,
        lines: list,
    ) -> int: ...

    def total_in_window(self, user_id: int, start: datetime, end: datetime) -> Money:
        """Lo devuelto en la ventana de un turno: sale de la gaveta."""
        ...


class SettingsRepository(Protocol):
    def tax_rate(self) -> object:
        """
        La tasa configurada, como `TaxRate`.

        Es un puerto y no una lectura directa de la tabla porque el caso de uso
        de la venta la necesita para recalcular los totales, y ese cálculo tiene
        que poder probarse sin base de datos.
        """
        ...


class CashRepository(Protocol):
    def open_session(self, user_id: int) -> object | None:
        """El turno abierto de ese cajero, si tiene uno."""
        ...

    def create_session(self, *, user_id: int, opening: Money, opened_at: datetime, notes: str | None) -> object: ...

    def close_session(self, session_id: int, *, counted: Money, closed_at: datetime, notes: str | None) -> object: ...

    def add_movement(
        self, *, session_id: int, type_: str, amount: Money, reason: str, created_at: datetime
    ) -> object: ...

    def movements(self, session_id: int) -> list: ...


class UnitOfWork(Protocol):
    """
    Una transacción.

    Existe porque el defecto 1 fue exactamente esto: la cabecera de la venta se
    confirmaba antes de validar las existencias, y un fallo posterior dejaba una
    factura fantasma sin líneas y sin descontar inventario. O entra todo, o no
    entra nada.
    """

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, *exc) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
