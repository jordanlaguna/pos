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


class StockEntryCreate(BaseModel):
    user_id: int
    supplier: str | None = None
    document_number: str | None = None
    # 'manual' | 'excel' | 'xml'
    source: str = "manual"
    notes: str | None = None
    lines: list[EntryLineInput]


class EntryLineResponse(BaseModel):
    id_product: int
    name: str
    quantity: int
    unit_cost: float
    subtotal: float


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

    model_config = {"from_attributes": True}


class StockEntrySuccess(BaseModel):
    message: str
    id_entry: int
    products_created: int
    units_added: int
