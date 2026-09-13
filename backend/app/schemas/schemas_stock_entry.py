from pydantic import BaseModel
import datetime


class NewProduct(BaseModel):
    """Producto que no existía y hay que dar de alta junto con la entrada."""

    name: str
    description: str | None = None
    barcode: str
    # Precio de VENTA. El costo va en la línea; son cosas distintas y el backend
    # no lo deduce solo porque el margen lo decide el negocio.
    price: float
    category_id: int


class EntryLineInput(BaseModel):
    # Uno de los dos: producto existente o producto a crear.
    id_product: int | None = None
    new_product: NewProduct | None = None
    quantity: int
    unit_cost: float = 0
    # El impuesto **del documento del proveedor** (RN-53, F10), en porcentaje:
    # 13 y no 0,13, que es como lo dice la factura. En cero cuando la entrada no
    # viene de una: el crédito fiscal es lo que se pagó, y sin factura no hay.
    tax_rate: float = 0
    tax_amount: float = 0


class StockEntryCreate(BaseModel):
    user_id: int
    supplier: str | None = None
    document_number: str | None = None
    # 'manual' | 'excel' | 'xml'
    source: str = "manual"
    notes: str | None = None
    lines: list[EntryLineInput]

    # ------------------------------------------------------- compra (F10)
    #
    # Sin `supplier_id` esto sigue siendo una entrada y nada de lo de abajo se
    # usa (RN-52): no genera cuenta por pagar ni crédito fiscal.
    supplier_id: int | None = None
    document_key: str | None = None
    document_date: datetime.date | None = None
    # 'cash' | 'credit'
    payment_terms: str = "cash"
    # Los días de plazo. Sin ellos se usa el habitual del proveedor, que es lo
    # que evita teclear «30» en cada factura del mismo mayorista.
    payment_terms_days: int | None = None

    # `payment_terms` dice CUÁNDO se paga y esto CÓMO. Sin método, una compra de
    # contado queda con saldo y se abona desde cuentas por pagar: inventarle uno
    # sería adivinar de dónde salió la plata, y si adivina «efectivo» descuadra
    # un arqueo (RN-56).
    payment_method: str | None = None
    # El motivo del movimiento de caja, armado por el POS (RN-30).
    payment_reason: str = ""


class EntryCancel(BaseModel):
    """El motivo de una anulación (RF-46).

    Opcional acá y obligatorio en el servicio cuando la entrada es una compra:
    la pantalla de entradas nunca lo pidió y exigirlo en el esquema la rompería.
    """

    reason: str | None = None


class EntryLineResponse(BaseModel):
    id_product: int
    name: str
    quantity: int
    unit_cost: float
    subtotal: float
    #: En porcentaje, como lo dice el documento (RN-53).
    tax_rate: float = 0
    tax_amount: float = 0


class StockEntryResponse(BaseModel):
    id: int
    document_number: str | None = None
    supplier: str | None = None
    source: str
    user_id: int
    user_name: str | None = None
    created_at: datetime.datetime
    notes: str | None = None
    status: str
    total_cost: float
    items_count: int
    lines: list[EntryLineResponse] = []

    # Lo que hace de esto una compra (F10). Todo en nulo o en cero es una
    # entrada de las de siempre.
    supplier_id: int | None = None
    document_key: str | None = None
    document_date: datetime.date | None = None
    payment_terms: str = "cash"
    due_date: datetime.date | None = None
    subtotal: float = 0
    tax: float = 0

    model_config = {"from_attributes": True}


class StockEntrySuccess(BaseModel):
    message: str
    id_entry: int
    products_created: int
    units_added: int
    #: El abono de una compra de contado, cuando se dijo cómo se pagó.
    id_payment: int | None = None
