from pydantic import BaseModel
import datetime


class ProductSale(BaseModel):
    id_product: int
    # `stock` es la CANTIDAD vendida, no el inventario. El nombre viene del
    # cliente WinForms original y se conserva para no romper compatibilidad.
    stock: int


class SaleRegister(BaseModel):
    sale_number: str
    # Opcional: las ventas de contado no llevan cliente asociado.
    client_id: int | None = None
    user_id: int
    total: float
    subtotal: float
    tax: float
    payment_method: str
    cash_received: float
    change_given: float
    # Se acepta por compatibilidad con el cliente WinForms, pero se IGNORA: la
    # hora de la venta la sella el servidor. Ver crud_sale.create_sale().
    created_at: datetime.datetime | None = None
    products: list[ProductSale]


class SalesList(BaseModel):
    id: int
    sale_number: str
    client_id: int | None = None
    user_id: int
    total: float
    subtotal: float
    tax: float
    payment_method: str
    cash_received: float
    change_given: float
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class SaleItem(BaseModel):
    id_product: int
    name: str
    quantity: int
    price: float
    subtotal: float


class SaleDetailResponse(SalesList):
    """Venta con sus líneas. La necesitan la factura y las devoluciones."""

    client_name: str | None = None
    user_name: str | None = None
    returned: bool = False
    items: list[SaleItem] = []


class SaleRegisterSuccess(BaseModel):
    message: str
    id_sale: int

    model_config = {"from_attributes": True}
