from pydantic import BaseModel
import datetime


class ReturnItemInput(BaseModel):
    id_product: int
    quantity: int


class ReturnCreate(BaseModel):
    sale_id: int
    user_id: int
    reason: str
    items: list[ReturnItemInput]


class ReturnItemResponse(BaseModel):
    id_product: int
    name: str
    quantity: int
    price: float
    subtotal: float


class ReturnResponse(BaseModel):
    id: int
    sale_id: int
    sale_number: str
    user_id: int
    user_name: str | None = None
    created_at: datetime.datetime
    reason: str
    total: float
    # True cuando ya no queda ninguna unidad de la venta por devolver.
    is_full: bool
    items: list[ReturnItemResponse] = []

    model_config = {"from_attributes": True}


class ReturnCreateSuccess(BaseModel):
    message: str
    id_return: int
    total: float
