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

    #: El código de tarifa de Hacienda (RN-76). `None` es «no está clasificado
    #: para factura electrónica»: del porcentaje no se vuelve al código, así que
    #: acá no se deduce nada. Se congela en la línea tal como venga.
    tax_code: str | None

    #: Lo que cuesta, que no es lo que vale (RN-54). Promedio ponderado móvil.
    #: Cero en los productos anteriores a F10 y en los que nunca se compraron:
    #: de esos no se sabe cuánto costaron, y la primera compra lo establece.
    cost: Money

    #: El CABYS y la unidad de medida del comprobante (RN-86). Se congelan en la
    #: línea como la tarifa: la factura reimpresa dice con qué se vendió.
    cabys_code: str | None
    unit_of_measure: str | None

    #: La partida arancelaria (RF-78, T-727): lo que una mercancía necesita
    #: para salir en una factura de exportación. `None` es «no tiene», y eso
    #: solo es un problema el día que se le venda a alguien del extranjero.
    tariff_heading: str | None

    #: Dónde cuelga (RN-6). La edición de la ficha pregunta si cambió, y solo
    #: entonces vuelve a comprobar la categoría (T-1502).
    category_id: int


class CategorySnapshot(Protocol):
    """Lo que la ficha necesita saber de una categoría para colgar un producto."""

    id: int
    name: str
    is_active: bool
    #: Las hijas en circulación (RN-6): con alguna, la raíz ya no recibe productos.
    active_children: int


class CategoryRepository(Protocol):
    def get(self, category_id: int) -> CategorySnapshot | None:
        """La categoría con ese id **en esta compañía**, o nulo."""
        ...


class ProductRepository(Protocol):
    def get(self, product_id: int) -> ProductSnapshot | None: ...

    def get_by_barcode(self, barcode: str) -> ProductSnapshot | None: ...

    def lock(self, product_ids: list[int]) -> dict[int, ProductSnapshot]:
        """
        Trae los productos y **los bloquea** hasta que termine la transacción.

        Es lo que impide que dos cajas vendan la última unidad a la vez. Devuelve
        solo los que existen; el caso de uso decide qué hacer con los que faltan.

        Desde F15 lo llama **todo** documento que mueve existencias —la venta,
        la entrada, su anulación, la salida, el traslado, la toma— con todos sus
        productos de una vez, antes de tocar ninguno, y el adaptador los toma
        **en orden de id**: una entrada [B, A] y una venta [A, B] que bloquearan
        en el orden en que vienen se esperarían la una a la otra (plan §15.1).
        Se llamaba `lock_for_sale`; un solo método para todos los caminos es lo
        que hace que el orden sea uno.

        Ya no existe `adjust_stock`: las existencias las mueve `MoveStock`, que
        deja el kárdex, y nadie más (RN-98).
        """
        ...

    def update_cost(self, product_id: int, cost: Money) -> None:
        """Fija el costo del producto (RN-54).

        Lo calcula el dominio —`weighted_average_cost`— y acá solo se guarda:
        el promedio ponderado es una regla y no una consulta.
        """
        ...

    def barcode_taken(self, barcode: str, *, except_product_id: int | None = None) -> bool:
        """Si ya hay un producto con ese código. Al editar se excluye a sí mismo."""
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
        cabys_code: str | None = None,
        tax_rate: float | None = None,
        tax_code: str | None = None,
        unit_of_measure: str | None = None,
        tariff_heading: str | None = None,
    ) -> int:
        """Da de alta un producto **sin existencias** y devuelve su id.

        Sin existencias a propósito: las pone la entrada de mercadería que lo
        está creando —o la apertura de la ficha (RF-94)—, en el mismo
        movimiento y por la misma vía que las de cualquier otro producto. Lo
        de clasificación (RN-9, RN-76, T-727) llega ya resuelto por el dominio;
        `unit_of_measure` en nulo deja el valor por omisión de la base.
        """
        ...

    def update(self, product_id: int, changes: dict) -> None:
        """Escribe los cambios que `domain/product.clean_changes` dejó pasar."""
        ...

    def delete(self, product_id: int) -> None: ...

    def has_sales(self, product_id: int) -> bool:
        """Si alguna venta lo nombra: borrarlo dejaría facturas apuntando a nada."""
        ...


class SupplierSnapshot(Protocol):
    """Lo justo para comprarle, y desde T-728 quién es ante Hacienda."""

    """Lo que la aplicación necesita saber de un proveedor para comprarle."""

    id: int
    name: str
    is_active: bool
    payment_terms_days: int
    #: El tipo de identificación de Hacienda (T-728): un `06`, no contribuyente,
    #: es a quien se le emite la factura de compra. `None` es «sin tipo», que
    #: es el proveedor informal al que no se le pidió cédula. La cédula va con
    #: él: la factura de compra lo lleva como emisor, y sin ella no se numera.
    identification_type: str | None
    identification: str | None


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
        #: A qué sucursal entró (F15, RN-102). Lo llena el router desde el
        #: `bid` de la sesión —la aplicación no lee el `ContextVar`—, y es
        #: donde la anulación repone, aunque la sesión que anula sea otra.
        branch_id: int,
        #: Lo que convierte la entrada en compra (F10, RN-52). Todo en nulo es
        #: una entrada de las de siempre.
        supplier_id: int | None = None,
        document_key: str | None = None,
        document_date: date | None = None,
        payment_terms: str = "cash",
        due_date: date | None = None,
        subtotal: Money | None = None,
        tax: Money | None = None,
        #: '08' cuando la compra sale como factura electrónica de compra (T-728).
        document_type: str | None = None,
    ) -> int: ...

    def lines_of(self, entry_id: int) -> list:
        """Las líneas de una entrada, para poder revertirlas al anular."""
        ...

    def mark_cancelled(self, entry_id: int) -> None: ...


class ClientSnapshot(Protocol):
    """Lo que la venta necesita saber del receptor: quién es ante Hacienda."""

    id_client: int
    #: `05` es el extranjero no domiciliado, y es lo que decide que la venta
    #: salga como factura de exportación (RN-87, T-727). `None` es «no se
    #: sabe», que es un cliente del país mientras nadie diga otra cosa.
    identification_type: str | None
    #: Las otras señas extranjeras del receptor de una exportación (RF-78).
    foreign_address: str | None


class ClientRepository(Protocol):
    def get(self, client_id: int) -> ClientSnapshot | None:
        """El cliente con ese id **en esta compañía**, o nulo.

        La foránea de `sales.client_id` no sabe de compañías: sin esta pregunta,
        una venta podía colgar del cliente de otro negocio, y una factura
        electrónica habría salido a nombre de un receptor que no es de quien la
        emite (RN-85). Desde T-727 devuelve al cliente y no solo si existe: su
        identificación decide el comprobante.
        """
        ...


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
        #: Dónde se cobró (RN-14). Del `bid` de la sesión, nunca del cliente;
        #: desde F15 es también de dónde se descuenta (RN-102).
        branch_id: int,
        #: `'01'` factura, `'04'` tiquete, nulo sin facturación electrónica
        #: (RN-85). Lo decide el dominio antes de llegar acá.
        document_type: str | None = None,
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

    def sold_costs(self, sale_id: int) -> dict[int, Money]:
        """El costo **congelado** de cada línea, para las que lo tengan (RN-63).

        Lo necesita el asiento de la devolución: devolver mercadería la repone al
        inventario por lo que costó **cuando se vendió**, no por lo que cuesta
        hoy. Con el costo de hoy, devolver algo comprado más caro después
        inventaría utilidad de la nada.

        Las líneas sin costo no salen en el diccionario: son las ventas
        anteriores a F11 y los productos que nunca se compraron, y para esas el
        asiento simplemente no lleva el par costo / inventario.
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
        #: Dónde se devuelve, que no tiene por qué ser donde se vendió: la
        #: mercadería se repone en esta sucursal (RN-102).
        branch_id: int,
        #: La nota de crédito (RN-89): `'03'` y el motivo de Hacienda, o los dos
        #: nulos cuando la venta no fue comprobante. Lo decide `fe_notes`.
        document_type: str | None = None,
        reference_code: str | None = None,
    ) -> int: ...

    def total_in_window(self, user_id: int, start: datetime, end: datetime) -> Money:
        """Lo devuelto en la ventana de un turno: sale de la gaveta."""
        ...


class NoteRepository(Protocol):
    """Las notas por monto (RF-77, T-726): las que no mueven mercadería."""

    def adjustments(self, sale_id: int) -> dict[int, tuple[Money, Money]]:
        """Lo que las notas le **sumaron** (ND) y le **restaron** (NC) a cada
        línea de la venta, con impuesto: `{producto: (sumado, restado)}`.

        Sin notas, vacío. Lo usan la NC —para no reembolsar más de lo que queda—
        y la devolución —que no puede devolver una línea que ya tiene NC—.
        """
        ...

    def add(
        self,
        *,
        sale_id: int,
        user_id: int,
        document_type: str,
        reference_code: str,
        reason: str,
        #: Cómo se cobró la ND; nulo en la NC, que sale de la gaveta.
        payment_method: str | None,
        subtotal: Money,
        tax: Money,
        total: Money,
        created_at: datetime,
        lines: list,
    ) -> int:
        """Guarda la nota con sus líneas. El CABYS, la unidad y el código de
        tarifa de cada una son los de la línea de la venta (RN-86)."""
        ...

    def in_window(self, user_id: int, start: datetime, end: datetime) -> list:
        """Las notas de un cajero entre dos marcas, cada una con su
        `document_type`, su `payment_method` y su `total`. Es cómo entran al
        arqueo del turno."""
        ...


class SettingsRepository(Protocol):
    # Ya no tiene `tax_rate` (QA-05): la tarifa de respaldo es la general del
    # IVA, `domain.tax.GENERAL_RATE`, y no se configura.

    def einvoicing_enabled(self) -> bool:
        """Si la compañía factura electrónicamente.

        Decide si la venta lleva tipo de comprobante (RN-85). Se lee al cobrar y
        no se congela en ningún lado más que en la venta misma: lo que cambia
        cuando alguien la apaga son las ventas siguientes, no las anteriores.
        """
        ...

    def document_types(self) -> frozenset[str]:
        """Los comprobantes que la compañía emite, ya saneados (RN-88).

        Nunca vacío ni sin algo con qué vender: lo garantiza
        `fe_document_type.enabled_types`, que es por donde tiene que pasar.
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
