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

from datetime import date, datetime
from typing import Protocol

from app.domain.money import Money
from app.domain.tax import TaxRate


class ProductSnapshot(Protocol):
    """Lo que la aplicación necesita saber de un producto para vender."""

    id_product: int
    name: str
    price: Money
    stock: int

    #: La tarifa de ESTE producto (RN-9). `None` es «la configurada del
    #: negocio», que es lo que tienen todos los productos anteriores a F5 y los
    #: que nadie ha clasificado. El caso de uso la resuelve antes de calcular:
    #: lo que se guarda en la línea es siempre una tarifa concreta, nunca un
    #: nulo, porque la de la venta no puede depender de lo que esté configurado
    #: el día que alguien devuelva (RN-12).
    tax_rate: TaxRate | None

    #: Lo que cuesta, que no es lo que vale (RN-54). Promedio ponderado móvil.
    #: Cero en los productos anteriores a F10 y en los que nunca se compraron:
    #: de esos no se sabe cuánto costaron, y la primera compra lo establece.
    cost: Money


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

    def update_cost(self, product_id: int, cost: Money) -> None:
        """Fija el costo del producto (RN-54).

        Lo calcula el dominio —`weighted_average_cost`— y acá solo se guarda:
        el promedio ponderado es una regla y no una consulta.
        """
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


class SupplierSnapshot(Protocol):
    """Lo que la aplicación necesita saber de un proveedor para comprarle."""

    id: int
    name: str
    is_active: bool
    payment_terms_days: int


class SupplierRepository(Protocol):
    def get(self, supplier_id: int) -> SupplierSnapshot | None: ...


class SupplierPaymentRepository(Protocol):
    """Los abonos de una compra (RN-55).

    No guarda saldos: el de una compra es su total menos sus abonos y el de un
    proveedor es la suma de los de sus compras. Un saldo guardado es un número
    más que hay que mantener cuadrado, y el día que se descuadre nadie sabrá
    cuál de los dos miente.
    """

    def amounts_for(self, entry_id: int) -> list[Money]:
        """Lo abonado a esa compra, monto por monto."""
        ...

    def add(
        self,
        *,
        supplier_id: int,
        entry_id: int,
        amount: Money,
        method: str,
        reference: str | None,
        cash_movement_id: int | None,
        user_id: int,
        paid_at: datetime,
    ) -> int: ...


class StockEntryRepository(Protocol):
    def get(self, entry_id: int): ...

    def applied_with_document(self, document_number: str, supplier_id: int | None = None):
        """La entrada **aplicada** que ya usó ese número de documento, si la hay.

        Solo las aplicadas: una anulada libera su número, que es como se repite
        una carga que salió mal.

        Desde F10 el número es único **por proveedor** y no por compañía: dos
        mayoristas distintos numeran sus facturas cada uno desde el uno, y la
        1234 de uno no tiene nada que ver con la 1234 del otro. Sin proveedor
        —una entrada que no es compra— se compara contra las que tampoco lo
        tienen.
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
        #: Lo que convierte la entrada en compra (F10, RN-52). Todo en nulo es
        #: una entrada de las de siempre.
        supplier_id: int | None = None,
        document_key: str | None = None,
        document_date: date | None = None,
        payment_terms: str = "cash",
        due_date: date | None = None,
        subtotal: Money | None = None,
        tax: Money | None = None,
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

    def sold_tax_rates(self, sale_id: int) -> dict[int, TaxRate]:
        """La tarifa **congelada** de cada línea, para las que la tengan.

        Solo las ventas posteriores a la migración 006 la traen. Para las
        anteriores el diccionario viene vacío o incompleto y quien llama cae al
        cociente del encabezado, que en ellas es exacto porque llevan una sola
        tarifa (RN-12).
        """
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
        #: Desde F5 se guarda el desglose y no solo el total: con tarifas
        #: mezcladas el impuesto no se puede deducir del total.
        subtotal: Money,
        tax: Money,
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
