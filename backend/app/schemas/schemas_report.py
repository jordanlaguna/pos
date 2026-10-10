from pydantic import BaseModel


class ReportSummary(BaseModel):
    # {"from": "2026-07-17", "to": "2026-08-15"}
    range: dict
    sales_count: int
    gross_total: float
    returns_total: float
    # Las notas por monto del periodo (T-726): la ND suma a lo vendido y la NC
    # resta, como una devolución.
    debit_notes_total: float = 0
    credit_notes_total: float = 0
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


class LowStockBranch(BaseModel):
    """Cuánto hay de un producto en una sucursal (RF-90)."""

    branch_id: int
    name: str
    quantity: int


class LowStockProduct(BaseModel):
    id_product: int
    name: str
    barcode: str | None = None
    #: La existencia total, la suma de las sucursales.
    stock: int
    category_id: int
    #: El mínimo propio (RN-101); nulo usa el general.
    min_stock: int | None = None
    #: El que se aplicó: el propio o el general.
    threshold: int | None = None
    branches: list[LowStockBranch] = []


class SalesRateLine(BaseModel):
    """Una tarifa en el débito fiscal del periodo (RN-65).

    Las devoluciones van **aparte y no restadas**: sumadas en silencio, la cifra
    dejaría de coincidir con el desglose de ventas y nadie sabría por qué. El
    neto viaja ya calculado para que el POS no lo vuelva a restar.
    """

    #: Entre 0 y 1 —0,13 y no 13—, como se congela en `sale_details`.
    tax_rate: float
    base: float
    tax: float
    returns_base: float = 0
    returns_tax: float = 0
    net_base: float = 0
    net_tax: float = 0


class SalesByRateReport(BaseModel):
    date_from: str
    date_to: str
    by_rate: list[SalesRateLine] = []
    tax: float = 0
    returns_tax: float = 0
    net_tax: float = 0
