"""La ficha del producto — adaptador.

Desde T-1502 las reglas están en `app/domain/product.py` y el paso a paso en
`app/application/use_cases/product.py`. Acá queda la traducción a HTTP, en
código y datos, nunca en frases (RN-30), y las lecturas del catálogo.
"""

from sqlalchemy.orm import Session

from app.application.use_cases.product import (
    BranchRequired,
    CategoryCannotHoldProducts,
    CategoryInactive,
    CategoryNotFound,
    DeleteProduct,
    ProductHasMovements,
    ProductHasSales,
    ProductNotFound,
    ProductRequest,
    RegisterProduct,
    UpdateProduct,
)
from app.domain.errors import (
    BarcodeTaken,
    InsufficientStock,
    InvalidTariffHeading,
    StockNotEditable,
)
from app.domain.fe_tax_codes import InvalidTaxCode, suggested_code
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_inventory import SqlAlchemyKardex
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_categories import Category
from app.models.model_product import Product
from app.schemas.schemas_product import ProdcutRegisterSuccess, ProductRegister
from app.services import crud_inventory
from app.utils.api_errors import api_error
from app.utils.tenancy import current_branch


def _categoria_a_http(e):
    """Los tres «no» de RN-6, con el nombre de la categoría para la frase."""
    if isinstance(e, CategoryNotFound):
        return api_error(404, "category_not_found", category_id=e.category_id)
    if isinstance(e, CategoryInactive):
        return api_error(400, "category_inactive", category_id=e.category_id, name=e.name)
    return api_error(
        400,
        "category_needs_subcategory",
        category_id=e.category_id,
        name=e.name,
        children=e.children,
    )


def create_product(db: Session, product: ProductRegister, *, user_id: int):
    caso = RegisterProduct(
        products=SqlAlchemyProductRepository(db),
        categories=SqlAlchemyCategoryRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        # La existencia inicial es una apertura del kárdex (RF-94).
        stock=crud_inventory.mover(db),
    )
    peticion = ProductRequest(
        name=product.name,
        description=product.description,
        price=Money(product.price),
        barcode=product.barcode,
        category_id=product.category_id,
        created_at=product.created_at,
        user_id=user_id,
        # Dónde se abre: la sucursal de la sesión, si la compañía tiene una.
        branch_id=current_branch.get(),
        stock=product.stock,
        cabys_code=product.cabys_code,
        tax_rate=product.tax_rate,
        tax_code=product.tax_code,
        unit_of_measure=product.unit_of_measure,
        tariff_heading=product.tariff_heading,
    )

    try:
        hecho = caso(peticion)
    except BarcodeTaken as e:
        raise api_error(400, "barcode_taken", barcode=e.barcode) from None
    except (CategoryNotFound, CategoryInactive, CategoryCannotHoldProducts) as e:
        raise _categoria_a_http(e) from None
    except InvalidTaxCode as e:
        raise api_error(400, "invalid_tax_code", tax_code=str(e.value)) from None
    except InvalidTariffHeading as e:
        raise api_error(400, "invalid_tariff_heading", tariff_heading=str(e.value)) from None
    except BranchRequired:
        raise api_error(404, "branch_not_found") from None
    except InsufficientStock as e:
        # Una existencia inicial negativa: lo que no hay no se abre.
        raise api_error(
            400,
            "insufficient_stock",
            product_id=e.product_id,
            product=product.name,
            available=e.available,
            requested=e.requested,
        ) from None

    return ProdcutRegisterSuccess(message="product_registered", id_product=hecho.id_product)


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
    caso = UpdateProduct(
        products=SqlAlchemyProductRepository(db),
        categories=SqlAlchemyCategoryRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(id_product, product_data)
    except ProductNotFound:
        # El router responde el 404: es el contrato que ya tenía.
        return None
    except StockNotEditable as e:
        raise api_error(400, "stock_not_editable", product_id=e.product_id) from None
    except BarcodeTaken as e:
        raise api_error(400, "barcode_taken", barcode=e.barcode) from None
    except (CategoryNotFound, CategoryInactive, CategoryCannotHoldProducts) as e:
        raise _categoria_a_http(e) from None
    except InvalidTaxCode as e:
        raise api_error(400, "invalid_tax_code", tax_code=str(e.value)) from None
    except InvalidTariffHeading as e:
        raise api_error(400, "invalid_tariff_heading", tariff_heading=str(e.value)) from None

    return {"message": "product_updated", "id_product": id_product}


def assign_cabys(db: Session, product_ids: list[int], cabys_code: str, tax_rate: float) -> int:
    """Le pone el mismo código CABYS y la misma tarifa a varios productos (RF-20).

    Es para catálogos que ya estaban cargados cuando llegó F5: cientos de
    productos sin clasificar y un puñado de códigos que se repiten.

    **Va en una sola transacción, y si un identificador no resuelve no se aplica
    ninguno.** Medio catálogo clasificado es exactamente el desorden que esta
    función existe para arreglar, y quien lo pidió no tendría cómo saber qué
    mitad quedó hecha.

    Un identificador de otra compañía y uno que no existe se tratan igual —el
    filtro de `tenancy` no lo deja ni aparecer en la consulta— y está bien: para
    quien pregunta no existe. La respuesta es la misma que pedirlo por su ruta.
    """
    unicos = list(dict.fromkeys(product_ids))
    if not unicos:
        return 0

    productos = db.query(Product).filter(Product.id_product.in_(unicos)).all()
    if len(productos) != len(unicos):
        encontrados = {p.id_product for p in productos}
        faltante = next(i for i in unicos if i not in encontrados)
        raise api_error(404, "product_not_found", product_id=faltante)

    # El CABYS trae una tarifa, no un código de Hacienda. Cuando esa tarifa deja
    # **una sola** posibilidad en la nota 8.1 —el 13 % es `08` y no hay otro— se
    # pone, porque no hay nada que elegir. En el 0 % hay tres y la diferencia es
    # el derecho a crédito del cliente, así que se queda sin clasificar y lo
    # elige quien sabe a quién le vende (RN-76).
    codigo = suggested_code(TaxRate(tax_rate))
    for producto in productos:
        producto.cabys_code = cabys_code
        producto.tax_rate = tax_rate
        producto.tax_code = codigo

    db.commit()
    return len(productos)


def delete_product(db: Session, id_product: int):
    caso = DeleteProduct(
        products=SqlAlchemyProductRepository(db),
        kardex=SqlAlchemyKardex(db),
        uow=SqlAlchemyUnitOfWork(db),
    )
    try:
        caso(id_product)
    except ProductNotFound:
        return None
    except ProductHasSales:
        # Para retirarlo de la venta se deja en cero, no se borra.
        raise api_error(400, "product_has_sales") from None
    except ProductHasMovements as e:
        raise api_error(
            400, "product_has_movements", product_id=e.product_id, movements=e.movements
        ) from None
    return {"message": "product_deleted", "id_product": id_product}
