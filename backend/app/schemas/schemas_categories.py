from pydantic import BaseModel

# Schemas for categories in a product management system POST
class CategoryRegister(BaseModel):
    name: str


# Schema for the response when registering a category (what the server returns)
class AddCategories(BaseModel):
    id: int
    name: str


# Schema for the response when listing categories
class CategoryResponse(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True
    }
