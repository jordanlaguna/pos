"""Lo que el kárdex y las existencias devuelven (F15, RF-87)."""

from datetime import datetime

from pydantic import BaseModel, Field


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


# ----------------------------------------------------- los motivos (RN-99)


class StockReasonCreate(BaseModel):
    #: Único por compañía. En inglés o en lo que la compañía quiera: es suyo.
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)


class StockReasonUpdate(BaseModel):
    """Se renombra y se apaga; no se borra, porque las salidas viejas lo nombran."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None


class StockReasonOut(BaseModel):
    id: int
    code: str
    name: str
    #: El de la toma física (RN-100): no se elige en una salida ni se desactiva.
    is_system: bool
    is_active: bool


# ----------------------------------------------------- las salidas (RN-99)


class ExitLineInput(BaseModel):
    id_product: int
    quantity: int
    #: RN-104; llega con T-1507. Nulo es «sin lote».
    lot_id: int | None = None


class StockExitCreate(BaseModel):
    reason_id: int
    notes: str | None = Field(default=None, max_length=255)
    lines: list[ExitLineInput]


class ExitCancel(BaseModel):
    """El motivo de la anulación: obligatorio siempre (RN-99)."""

    reason: str = Field(min_length=1, max_length=255)


class ExitLineOut(BaseModel):
    id_product: int
    name: str
    quantity: int
    #: El promedio al salir (RN-99).
    unit_cost: float
    subtotal: float
    lot_id: int | None = None


class StockExitOut(BaseModel):
    id: int
    branch_id: int
    reason_id: int
    reason_code: str
    reason_name: str
    user_id: int
    user_name: str | None = None
    created_at: datetime
    notes: str | None = None
    #: 'applied' | 'voided'
    status: str
    total_cost: float
    items_count: int
    voided_at: datetime | None = None
    void_reason: str | None = None
    lines: list[ExitLineOut] = []


class StockExitSuccess(BaseModel):
    message: str
    id_exit: int
    units: int
    total_cost: float


class ExitCancelSuccess(BaseModel):
    message: str
    id_exit: int
    units_returned: int
