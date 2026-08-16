from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.model_categories import Category
from app.models.model_product import Product
from app.models.model_sale_details import SaleDetail
from app.schemas.schemas_product import ProdcutRegisterSuccess, ProductRegister


def create_product(db: Session, product: ProductRegister):
    db_product = Product(
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        barcode=product.barcode,
        category_id=product.category_id,
        created_at=product.created_at,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return ProdcutRegisterSuccess(
        message="Producto registrado exitosamente", id_product=db_product.id_product
    )


def get_all_products(db: Session):
    return (
        db.query(Product, Category)
        .join(Category, Product.category_id == Category.id)
        .all()
    )


def get_product_by_barcode(db: Session, term: str) -> Product | None:
    """Busca por código de barras y, si no hay, por nombre exacto.

    CORRECCIÓN: la versión original filtraba por `Product.name == name`, o sea
    que este endpoint —usado por el lector del punto de venta— nunca encontraba
    nada al escanear un código. Ahora el código manda y el nombre queda como
    respaldo, que es lo que el nombre de la función siempre prometió.
    """
    found = db.query(Product).filter(Product.barcode == term).first()
    if found:
        return found
    return db.query(Product).filter(Product.name == term).first()


def update_product_information(db: Session, id_product: int, product_data: dict):
    db_product = db.query(Product).filter(Product.id_product == id_product).first()
    if not db_product:
        return None

    # Un código de barras repetido rompe el escaneo: dos productos distintos
    # responderían al mismo pitido del lector.
    new_barcode = product_data.get("barcode")
    if new_barcode:
        clash = (
            db.query(Product)
            .filter(Product.barcode == new_barcode, Product.id_product != id_product)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=400, detail="Ya existe otro producto con este código de barras."
            )

    for key, value in product_data.items():
        if value is not None and hasattr(db_product, key):
            setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)

    return {
        "message": "Información del producto actualizada exitosamente",
        "id_product": db_product.id_product,
    }


def delete_product(db: Session, id_product: int):
    db_product = db.query(Product).filter(Product.id_product == id_product).first()
    if not db_product:
        return None

    # Borrar un producto ya vendido dejaría facturas apuntando a la nada y
    # rompería los reportes históricos. Para retirarlo de la venta, poné stock 0.
    sold = db.query(SaleDetail).filter(SaleDetail.product_id == id_product).first()
    if sold:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar: el producto tiene ventas registradas.",
        )

    db.delete(db_product)
    db.commit()
    return {"message": "Producto eliminado exitosamente", "id_product": id_product}
