from sqlalchemy.orm import Session

from app.models.model_categories import Category
from app.models.model_product import Product
from app.models.model_sale_details import SaleDetail
from app.schemas.schemas_product import ProdcutRegisterSuccess, ProductRegister
from app.services.crud_categories import check_category_for_product
from app.utils.api_errors import api_error


def create_product(db: Session, product: ProductRegister):
    # RN-6: el producto va en la hoja del árbol. Con la categoría convertida en
    # raíz de una rama, colgarle un producto lo dejaría fuera de la grilla de
    # ventas —que en una raíz con hijas muestra fichas, no productos—.
    check_category_for_product(db, product.category_id)

    db_product = Product(
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        barcode=product.barcode,
        category_id=product.category_id,
        created_at=product.created_at,
        # F5: la tarifa del producto (RN-9). En nulo significa «la configurada
        # del negocio», que es lo que aplica mientras nadie lo clasifique. La
        # ficha propone la configurada al crear, y eso pasa en el POS: acá se
        # guarda lo que venga, incluido el nulo.
        cabys_code=product.cabys_code,
        tax_rate=product.tax_rate,
        # `unit_of_measure` tiene valor por omisión en la base; mandar None lo
        # dejaría en NULL y la columna es NOT NULL.
        **({"unit_of_measure": product.unit_of_measure} if product.unit_of_measure else {}),
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return ProdcutRegisterSuccess(
        message="product_registered", id_product=db_product.id_product
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


#: Columnas donde el nulo **es un valor**, no «no lo mandé» (F5, RN-9).
#:
#: `tax_rate` en nulo significa «la tasa configurada del negocio»: es lo que
#: tienen los productos que nadie ha clasificado y lo que la migración 006 dejó
#: a propósito, para no congelar en el 13 % un catálogo que nadie tocó. Sin esta
#: lista, clasificar un producto una vez sería una puerta de una sola dirección:
#: el bucle de abajo saltaría el nulo y no habría manera de volver a heredar.
#:
#: En el resto de las columnas la regla contraria es la correcta —`name=None`
#: pondría el nombre en NULL y la columna no lo admite—, y por eso la lista es
#: corta y explícita en vez de al revés.
VACIABLES = {"cabys_code", "tax_rate"}


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
            raise api_error(400, "barcode_taken", barcode=new_barcode)

    # Mover un producto de categoría pasa por la misma regla que crearlo
    # (RN-6). Solo si de verdad cambia: revalidar la que ya tiene haría que un
    # cambio de precio fallara por una categoría que se desactivó después.
    nueva_categoria = product_data.get("category_id")
    if nueva_categoria is not None and nueva_categoria != db_product.category_id:
        check_category_for_product(db, nueva_categoria)

    for key, value in product_data.items():
        if not hasattr(db_product, key):
            continue
        # En casi todo el formulario un nulo significa «no mandé este campo»
        # —eso es lo que hace que un PUT parcial no borre el resto— y por eso se
        # salta. En `VACIABLES` no: ahí el nulo **es** el valor.
        if value is None and key not in VACIABLES:
            continue
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)

    return {
        "message": "product_updated",
        "id_product": db_product.id_product,
    }


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

    for producto in productos:
        producto.cabys_code = cabys_code
        producto.tax_rate = tax_rate

    db.commit()
    return len(productos)


def delete_product(db: Session, id_product: int):
    db_product = db.query(Product).filter(Product.id_product == id_product).first()
    if not db_product:
        return None

    # Borrar un producto ya vendido dejaría facturas apuntando a la nada y
    # rompería los reportes históricos. Para retirarlo de la venta, poné stock 0.
    sold = db.query(SaleDetail).filter(SaleDetail.product_id == id_product).first()
    if sold:
        raise api_error(400, "product_has_sales")

    db.delete(db_product)
    db.commit()
    return {"message": "product_deleted", "id_product": id_product}
