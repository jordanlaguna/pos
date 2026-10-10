"""Lo que el kárdex y las existencias devuelven (F15, RF-87)."""

from datetime import datetime

from pydantic import BaseModel


class StockMovementOut(BaseModel):
    """Una fila del kárdex, tal como la ve la pantalla."""

    id: int
    product_id: int
    branch_id: int
    #: Uno de `domain/inventory.KINDS`. La frase la arma el POS.
    kind: str
    #: Con signo: negativo baja.
    quantity: int
    before_qty: int
    after_qty: int
    unit_cost: float
    avg_cost_after: float
    lot_id: int | None = None
    source_type: str
    source_id: int
    source_line: int | None = None
    user_id: int
    moved_at: datetime


class StockLevelOut(BaseModel):
    product_id: int
    branch_id: int
    quantity: int
