from pydantic import BaseModel
import datetime

class ProductRegister(BaseModel):
    # Product attributes
    name: str
    description: str
    price: float
    stock: int
    barcode: str
    created_at: datetime.datetime
    category_id: int

class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None
    barcode: str | None = None
    created_at: datetime.datetime | None = None
    category_id: int | None = None
class ProductResponse(BaseModel):
    id_product: int
    name: str
    description: str
    price: float
    stock: int
    barcode: str
    created_at: datetime.datetime
    category_id: int

    model_config = {
        "from_attributes": True
    }

class ProductUpdateResponse(BaseModel):
    message: str
    id_product: int
class ProdcutRegisterSuccess(BaseModel):
    message: str
    id_product: int

    model_config = {
        "from_attributes": True
    }