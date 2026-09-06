from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.domain.cabys import InvalidCabysCode, normalize_code
from app.domain.errors import InvalidTaxRate
from app.domain.tax import TaxRate
from app.models.model_product import Product
from app.models.model_user import User
from app.schemas.schemas_product import (
    CabysAssignment,
    CabysAssignmentResult,
    ProdcutRegisterSuccess,
    ProductRegister,
    ProductResponse,
    ProductUpdate,
    ProductUpdateResponse,
)
from app.services import crud_product
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user, require_admin

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
    admin: Sesion = Depends(require_admin),
):
    existing = db.query(Product).filter(Product.barcode == product.barcode).first()
    if existing:
        raise api_error(400, "barcode_taken", barcode=product.barcode)
    return crud_product.create_product(db=db, product=product)


# Los cajeros necesitan leer el catálogo para vender: solo escribir es de admin.
@router.get("/products_list", response_model=List[ProductResponse])
def get_all_products(
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
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
            cabys_code=product.cabys_code,
            # Sale como número para el POS: la base lo guarda con seis
            # decimales y `Decimal` no viaja en JSON.
            tax_rate=float(product.tax_rate) if product.tax_rate is not None else None,
            unit_of_measure=product.unit_of_measure,
        )
        for product, _category in products
    ]


@router.get("/product/{term}", response_model=ProductResponse)
def get_product_by_barcode(
    term: str,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Búsqueda del lector: código de barras exacto y, si no, nombre exacto."""
    product = crud_product.get_product_by_barcode(db=db, term=term)
    if not product:
        # Lo buscado va como dato: es lo único que identifica al producto que no
        # se encontró, y sin eso la frase queda hablando de «el producto» a secas.
        raise api_error(404, "product_not_found", product=term)
    return product


@router.get("/search/{name}", response_model=List[ProductResponse])
def search_products_by_name(
    name: str,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
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
    admin: Sesion = Depends(require_admin),
):
    # `exclude_unset` y no `.dict()`: es lo que distingue «no mandé este campo»
    # de «ponelo en nulo». Sin eso los dos llegan como None y son indistinguibles,
    # y `tax_rate` en nulo es un valor —«la tasa configurada»— y no una omisión
    # (RN-9). Lo que sí se puede vaciar lo decide `crud_product.VACIABLES`.
    updated = crud_product.update_product_information(
        db=db, id_product=id_product, product_data=product_data.model_dump(exclude_unset=True)
    )
    if not updated:
        raise api_error(404, "product_not_found", product_id=id_product)
    return updated


@router.put("/assign_cabys", response_model=CabysAssignmentResult)
def assign_cabys(
    payload: CabysAssignment,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Clasifica varios productos de una vez (RF-20).

    Los identificadores van en el cuerpo y no en la ruta porque son muchos. Eso
    no los hace menos ajenos: el filtro de compañía es el mismo, y pedir uno que
    no es de la sesión responde 404 igual que pedirlo por su ruta.

    El código y la tarifa se validan **con el dominio** —trece dígitos, tarifa
    entre 0 y 1— antes de tocar nada. `13` en vez de `0.13` multiplicaría la
    factura por catorce, y en un lote lo haría en cien productos a la vez.
    """
    try:
        codigo = normalize_code(payload.cabys_code)
    except InvalidCabysCode as e:
        raise api_error(400, "cabys_invalid_code", value=str(e.value), reason=e.code) from None

    try:
        tarifa = TaxRate(payload.tax_rate)
    except InvalidTaxRate:
        raise api_error(400, "tax_rate_out_of_range", value=payload.tax_rate) from None

    actualizados = crud_product.assign_cabys(
        db=db,
        product_ids=payload.product_ids,
        cabys_code=codigo,
        tax_rate=float(tarifa.value),
    )
    return CabysAssignmentResult(message="cabys_assigned", updated=actualizados)


@router.delete("/delete_product/{id_product}", response_model=ProductUpdateResponse)
def delete_product(
    id_product: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    deleted = crud_product.delete_product(db=db, id_product=id_product)
    if not deleted:
        raise api_error(404, "product_not_found", product_id=id_product)
    return deleted
