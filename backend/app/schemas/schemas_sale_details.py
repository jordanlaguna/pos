from pydantic import BaseModel
from decimal import Decimal

class SaleDetailCreate(BaseModel):
    product_id: int
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
class SaleDetailResponse(SaleDetailCreate):
    id: int
    sale_id: int

    model_config = {
        "from_attributes": True
    }
