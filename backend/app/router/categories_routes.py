from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_categories import Category
from app.models.model_user import User
from app.schemas.schemas_categories import AddCategories, CategoryRegister, CategoryResponse
from app.services.crud_categories import create_category, get_all_categories
from app.utils.auth_dependency import get_current_user, require_admin

router = APIRouter()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register_category", response_model=AddCategories)
def register_category(
    category: CategoryRegister,
    db: Session = Depends(get_db_session),
    admin: User = Depends(require_admin),
):
    existing = db.query(Category).filter(Category.name == category.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Categoría ya registrada con este nombre.")
    return create_category(db=db, category=category)


# El cajero necesita leerlas para filtrar la grilla de productos.
@router.get("/categories_list", response_model=list[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db_session),
    current: User = Depends(get_current_user),
):
    return get_all_categories(db=db)
