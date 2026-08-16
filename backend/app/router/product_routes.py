from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_product import Product
from app.models.model_user import User
from app.schemas.schemas_product import (
    ProdcutRegisterSuccess,
    ProductRegister,
    ProductResponse,
    ProductUpdate,
    ProductUpdateResponse,
)
from app.services import crud_product
from app.utils.auth_dependency import get_current_user, require_admin

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/add_product", response_model=ProdcutRegisterSuccess)
def register_product(
    product: ProductRegister,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Product).filter(Product.barcode == product.barcode).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Ya existe un producto con este código de barras."
        )
    return crud_product.create_product(db=db, product=product)


# Los cajeros necesitan leer el catálogo para vender: solo escribir es de admin.
@router.get("/products_list", response_model=List[ProductResponse])
def get_all_products(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    products = crud_product.get_all_products(db=db)
    return [
        ProductResponse(
            id_product=product.id_product,
            name=product.name,
            description=product.description,
            price=product.price,
            stock=product.stock,
            barcode=product.barcode,
            created_at=product.created_at,
            category_id=product.category_id,
        )
        for product, _category in products
    ]


@router.get("/product/{term}", response_model=ProductResponse)
def get_product_by_barcode(
    term: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Búsqueda del lector: código de barras exacto y, si no, nombre exacto."""
    product = crud_product.get_product_by_barcode(db=db, term=term)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


@router.get("/search/{name}", response_model=List[ProductResponse])
def search_products_by_name(
    name: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return (
        db.query(Product)
        .filter(Product.name.ilike(f"%{name}%") | Product.barcode.ilike(f"%{name}%"))
        .limit(20)
        .all()
    )


@router.put("/update_product/{id_product}", response_model=ProductUpdateResponse)
def update_product(
    id_product: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    updated = crud_product.update_product_information(
        db=db, id_product=id_product, product_data=product_data.dict()
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return updated


@router.delete("/delete_product/{id_product}", response_model=ProductUpdateResponse)
def delete_product(
    id_product: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    deleted = crud_product.delete_product(db=db, id_product=id_product)
    if not deleted:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return deleted
