"""Registro de ventas — adaptador.

La lógica se mudó a `app/application/use_cases/register_sale.py`. Lo que queda
acá es la traducción entre HTTP y el caso de uso: armar los puertos a partir de
la sesión de SQLAlchemy y convertir los «no» del dominio en códigos de estado.

Lo que sale de acá es un código y sus datos, nunca una frase (RN-30): la escribe
el POS, que es el único que sabe en qué idioma la va a leer el cajero.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.register_sale import (
    ProductNotFound,
    ProductWithoutPrice,
    RegisterSale,
    RequestedLine,
    SaleRequest,
)
from app.domain.errors import (
    DuplicateSaleNumber,
    EmptySale,
    InsufficientPayment,
    InsufficientStock,
    InvalidQuantity,
    TotalsMismatch,
)
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyProductRepository,
    SqlAlchemySaleRepository,
    SqlAlchemySettingsRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_product import Product
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.schemas.schemas_sales import SaleRegister, SaleRegisterSuccess
from app.utils.api_errors import api_error


def create_sale(db: Session, sale: SaleRegister) -> SaleRegisterSuccess:
    productos = SqlAlchemyProductRepository(db)
    caso = RegisterSale(
        products=productos,
        sales=SqlAlchemySaleRepository(db),
        settings=SqlAlchemySettingsRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )

    peticion = SaleRequest(
        sale_number=sale.sale_number,
        client_id=sale.client_id,
        user_id=sale.user_id,
        subtotal=Money(sale.subtotal),
        tax=Money(sale.tax),
        total=Money(sale.total),
        payment_method=sale.payment_method,
        cash_received=Money(sale.cash_received),
        change_given=Money(sale.change_given),
        # `stock` es la CANTIDAD vendida, no el inventario. El nombre viene del
        # cliente WinForms y se conserva en el contrato del API.
        lines=[RequestedLine(l.id_product, l.stock) for l in sale.products],
    )

    try:
        resultado = caso(peticion)

    except DuplicateSaleNumber as e:
        raise api_error(400, "duplicate_sale_number", sale_number=e.sale_number) from None
    except EmptySale:
        raise api_error(400, "empty_sale") from None
    except InvalidQuantity:
        # El dominio rechaza el valor pero no dice qué línea venía mal: eso lo
        # sabe la interfaz, que es la que conoce el orden en que llegaron.
        malo = next(
            (l for l in sale.products if not l.id_product or l.stock <= 0), None
        )
        raise api_error(
            400, "invalid_sale_line", product_id=malo.id_product if malo else None
        ) from None
    except ProductNotFound as e:
        raise api_error(404, "product_not_found", product_id=e.product_id) from None
    except ProductWithoutPrice as e:
        raise api_error(400, "product_without_price", product_id=e.product_id) from None
    except InsufficientStock as e:
        # El nombre del producto es un dato, no una frase: sin él el cajero
        # tendría que buscar qué producto es el ID 47.
        producto = productos.get(e.product_id)
        raise api_error(
            400,
            "insufficient_stock",
            product_id=e.product_id,
            product=producto.name if producto else None,
            available=e.available,
            requested=e.requested,
        ) from None
    except TotalsMismatch as e:
        # Van las dos cifras: quien lo lea tiene que poder ver cuál está mal sin
        # abrir la base.
        raise api_error(
            400,
            "totals_mismatch",
            field=e.campo,
            declared=e.declarado.as_float(),
            computed=e.calculado.as_float(),
        ) from None
    except InsufficientPayment as e:
        # Cifras, no texto ya formateado: el símbolo de moneda y los separadores
        # los pone el POS, que es el que sabe la moneda configurada.
        raise api_error(
            400,
            "insufficient_payment",
            received=e.received.as_float(),
            total=e.total.as_float(),
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        # Cualquier otro fallo ya revirtió dentro de la unidad de trabajo. El
        # texto de la excepción va como dato para el registro, no para mostrar.
        raise api_error(500, "sale_failed", cause=str(exc))

    return SaleRegisterSuccess(message="sale_registered", id_sale=resultado.id_sale)


def get_all_sales(db: Session):
    return db.query(Sale).order_by(Sale.created_at.desc()).all()


def get_sale_detail(db: Session, sale_id: int) -> dict | None:
    """Venta con sus líneas. Es lo que necesitan la factura y las devoluciones."""
    from app.models.model_client import Client
    from app.models.model_person import Person
    from app.models.model_return import Return
    from app.models.model_user import User

    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        return None

    details = db.query(SaleDetail).filter(SaleDetail.sale_id == sale.id).all()
    items = []
    for detail in details:
        product = db.query(Product).filter(Product.id_product == detail.product_id).first()
        items.append(
            {
                "id_product": detail.product_id,
                "name": product.name if product else f"Producto #{detail.product_id}",
                "quantity": detail.quantity,
                "price": float(detail.unit_price),
                "subtotal": float(detail.subtotal),
                # Lo que se COBRÓ en esta línea, con su tarifa y su redondeo
                # (RN-12). Es lo que necesita el desglose del documento (RF-21):
                # se imprime lo cobrado, no una recuperación del cálculo.
                #
                # En nulo para las ventas anteriores a la migración 006, que
                # llevan una sola tarifa; ahí el documento la deduce del
                # encabezado, que para ellas es exacto.
                "tax_rate": float(detail.tax_rate) if detail.tax_rate is not None else None,
                "tax_amount": (
                    float(detail.tax_amount) if detail.tax_amount is not None else None
                ),
            }
        )

    client_name = None
    if sale.client_id:
        client = db.query(Client).filter(Client.id_client == sale.client_id).first()
        if client:
            client_name = f"{client.name} {client.last_name}".strip()

    user_name = None
    row = (
        db.query(Person.name, Person.lastName)
        .join(User, User.id_person == Person.id_person)
        .filter(User.id_user == sale.user_id)
        .first()
    )
    if row:
        user_name = f"{row[0]} {row[1]}".strip()

    returned = db.query(Return).filter(Return.sale_id == sale.id).first() is not None

    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "client_id": sale.client_id,
        "user_id": sale.user_id,
        "total": float(sale.total),
        "subtotal": float(sale.subtotal),
        "tax": float(sale.tax),
        "payment_method": sale.payment_method,
        "cash_received": float(sale.cash_received),
        "change_given": float(sale.change_given),
        "created_at": sale.created_at,
        "client_name": client_name,
        "user_name": user_name,
        "returned": returned,
        "items": items,
    }
