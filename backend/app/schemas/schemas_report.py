from pydantic import BaseModel


class ReportSummary(BaseModel):
    # {"from": "2026-07-17", "to": "2026-08-15"}
    range: dict
    sales_count: int
    gross_total: float
    returns_total: float
    net_total: float
    tax_total: float
    average_ticket: float
    items_sold: int
    # Ventas netas del periodo inmediatamente anterior de igual duración.
    previous_net_total: float


class TopProduct(BaseModel):
    id_product: int
    name: str
    quantity: int
    total: float


class SalesByDay(BaseModel):
    day: str
    sales_count: int
    total: float


class PaymentBreakdown(BaseModel):
    payment_method: str
    count: int
    total: float


class LowStockProduct(BaseModel):
    id_product: int
    name: str
    barcode: str | None = None
    stock: int
    category_id: int

    model_config = {"from_attributes": True}
