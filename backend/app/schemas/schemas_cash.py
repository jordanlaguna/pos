from pydantic import BaseModel
import datetime


class CashOpen(BaseModel):
    user_id: int
    opening_amount: float = 0
    notes: str | None = None


class CashClose(BaseModel):
    user_id: int
    closing_amount: float
    notes: str | None = None


class MovementCreate(BaseModel):
    user_id: int
    # 'entrada' | 'salida'
    type: str
    amount: float
    reason: str


class MovementResponse(BaseModel):
    id: int
    session_id: int
    type: str
    amount: float
    reason: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class PaymentBreakdown(BaseModel):
    payment_method: str
    count: int
    total: float


class CashSessionReport(BaseModel):
    """Estado completo de un turno: lo que se muestra en pantalla y lo que se
    imprime como corte Z."""

    id: int
    user_id: int
    user_name: str | None = None
    opened_at: datetime.datetime
    closed_at: datetime.datetime | None = None
    opening_amount: float
    closing_amount: float | None = None
    # Apertura + ventas en efectivo + entradas − salidas − devoluciones.
    expected_amount: float
    # closing_amount − expected_amount. Negativo = faltante.
    difference: float | None = None
    status: str
    notes: str | None = None

    movements: list[MovementResponse] = []
    sales_count: int = 0
    sales_total: float = 0
    by_payment_method: list[PaymentBreakdown] = []
    cash_sales: float = 0
    movements_in: float = 0
    movements_out: float = 0
    returns_total: float = 0
