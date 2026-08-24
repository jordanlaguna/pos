from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.schemas.schemas_categories import (
    AddCategories,
    CategoryRegister,
    CategoryReorder,
    CategoryResponse,
    CategoryUpdate,
)
from app.services import crud_categories
from app.utils.auth_dependency import Sesion, get_current_user, require_admin

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
    admin: Sesion = Depends(require_admin),
):
    return crud_categories.create_category(db=db, category=category)


# El cajero necesita leerlas para filtrar la grilla de productos.
@router.get("/categories_list", response_model=list[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db_session),
    current: Sesion = Depends(get_current_user),
):
    return crud_categories.get_all_categories(db=db)


@router.put("/update_category/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    cambios: CategoryUpdate,
    db: Session = Depends(get_db_session),
    admin: Sesion = Depends(require_admin),
):
    """Renombrar, mover de madre o activar y desactivar."""
    return crud_categories.update_category(db=db, category_id=category_id, cambios=cambios)


@router.put("/reorder", response_model=list[CategoryResponse])
def reorder_categories(
    orden: CategoryReorder,
    db: Session = Depends(get_db_session),
    admin: Sesion = Depends(require_admin),
):
    return crud_categories.reorder(db=db, parent_id=orden.parent_id, ids=orden.ids)


@router.delete("/delete_category/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db_session),
    admin: Sesion = Depends(require_admin),
):
    """Borra solo lo que no arrastra nada; con productos o hijas, 409 (RN-7)."""
    crud_categories.delete_category(db=db, category_id=category_id)
