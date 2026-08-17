"""Registro de ventas — adaptador.

La lógica se mudó a `app/application/use_cases/register_sale.py`. Lo que queda
acá es la traducción entre HTTP y el caso de uso: armar los puertos a partir de
la sesión de SQLAlchemy y convertir los «no» del dominio en códigos de estado.

Los mensajes son los mismos que antes, palabra por palabra: los ve el cajero y
los fijan las pruebas de caracterización.
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

    except DuplicateSaleNumber:
        raise HTTPException(
            status_code=400, detail="Ya existe una venta con este número de venta."
        ) from None
    except EmptySale:
        raise HTTPException(
            status_code=400, detail="La venta debe contener al menos un producto."
        ) from None
    except InvalidQuantity:
        # El mensaje nombra el producto que venía mal, como antes.
        malo = next(
            (l for l in sale.products if not l.id_product or l.stock <= 0), None
        )
        raise HTTPException(
            status_code=400,
            detail=f"Producto ID {malo.id_product if malo else None} no válido o cantidad insuficiente.",
        ) from None
    except ProductNotFound as e:
        raise HTTPException(
            status_code=404, detail=f"Producto ID {e.product_id} no encontrado."
        ) from None
    except ProductWithoutPrice as e:
        raise HTTPException(
            status_code=400,
            detail=f"El producto ID {e.product_id} no tiene un precio definido.",
        ) from None
    except InsufficientStock as e:
        producto = productos.get(e.product_id)
        nombre = producto.name if producto else f"el producto {e.product_id}"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Stock insuficiente para {nombre}: "
                f"quedan {e.available} y se piden {e.requested}."
            ),
        ) from None
    except TotalsMismatch as e:
        # Se dicen las dos cifras: quien lo lea tiene que poder ver cuál está
        # mal sin abrir la base.
        raise HTTPException(
            status_code=400,
            detail=(
                f"El {e.campo} no coincide con el que calcula el servidor: "
                f"la caja dice {e.declarado} y el servidor {e.calculado}. "
                f"Recargá el catálogo: los precios pueden haber cambiado."
            ),
        ) from None
    except InsufficientPayment as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El efectivo recibido ({e.received}) no puede ser menor "
                f"al total de la venta ({e.total})."
            ),
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        # Cualquier otro fallo ya revirtió dentro de la unidad de trabajo.
        raise HTTPException(status_code=500, detail=f"Error al registrar la venta: {exc}")

    return SaleRegisterSuccess(
        message="Venta registrada exitosamente", id_sale=resultado.id_sale
    )


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
