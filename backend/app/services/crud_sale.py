"""Registro de ventas.

CORRECCIÓN IMPORTANTE respecto de la versión original
-----------------------------------------------------
La versión anterior hacía `db.commit()` de la cabecera de la venta ANTES de
validar el stock de los productos, y su `except` solo atrapaba `SQLAlchemyError`.
Consecuencia: si un producto no tenía existencias, el `HTTPException` subía sin
pasar por el rollback y **la venta quedaba guardada en la base sin líneas de
detalle y sin descontar inventario**. Cada intento fallido dejaba una factura
fantasma que además cuadraba mal los reportes.

Aquí se valida todo primero y se escribe al final, en una sola transacción:
o entra la venta completa, o no entra nada.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.model_product import Product
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.schemas.schemas_sales import SaleRegister, SaleRegisterSuccess


def create_sale(db: Session, sale: SaleRegister) -> SaleRegisterSuccess:
    if not sale.products:
        raise HTTPException(status_code=400, detail="La venta debe contener al menos un producto.")

    # ---------------------------------------------------------------- validar
    # Nada se escribe todavía. Se bloquean las filas de producto para que dos
    # cajas no puedan vender la última unidad al mismo tiempo.
    validated = []
    for line in sale.products:
        quantity = line.stock
        if not line.id_product or quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Producto ID {line.id_product} no válido o cantidad insuficiente.",
            )

        product = (
            db.query(Product)
            .filter(Product.id_product == line.id_product)
            .with_for_update()
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404, detail=f"Producto ID {line.id_product} no encontrado."
            )
        if product.price is None:
            raise HTTPException(
                status_code=400,
                detail=f"El producto ID {line.id_product} no tiene un precio definido.",
            )
        if product.stock < quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Stock insuficiente para {product.name}: "
                    f"quedan {product.stock} y se piden {quantity}."
                ),
            )

        unit_price = Decimal(str(product.price))
        validated.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": (unit_price * quantity).quantize(Decimal("0.01")),
            }
        )

    # ---------------------------------------------------------------- escribir
    try:
        db_sale = Sale(
            sale_number=sale.sale_number,
            client_id=sale.client_id,
            user_id=sale.user_id,
            total=sale.total,
            subtotal=sale.subtotal,
            tax=sale.tax,
            payment_method=sale.payment_method,
            cash_received=sale.cash_received,
            change_given=sale.change_given,
            # La hora la pone el servidor, no el cliente.
            #
            # El turno de caja se delimita comparando `sales.created_at` contra
            # `cash_sessions.opened_at`, y esa marca la escribe este mismo
            # backend. Si la venta trajera la hora del equipo del cajero, bastaría
            # con que ese reloj fuera unos segundos atrás para que la venta
            # quedara fechada ANTES de la apertura y desapareciera del arqueo, sin
            # ningún error visible. Dos relojes no se pueden comparar; uno sí.
            created_at=datetime.now(),
        )
        db.add(db_sale)
        # flush, no commit: asigna el id sin cerrar la transacción, de modo que
        # un fallo posterior revierta también la cabecera.
        db.flush()

        for value in validated:
            db.add(
                SaleDetail(
                    sale_id=db_sale.id,
                    product_id=value["product"].id_product,
                    quantity=value["quantity"],
                    unit_price=value["unit_price"],
                    subtotal=value["subtotal"],
                )
            )
            value["product"].stock -= value["quantity"]

        db.commit()
        db.refresh(db_sale)

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        # `Exception` y no `SQLAlchemyError`: cualquier fallo debe revertir.
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar la venta: {exc}")

    return SaleRegisterSuccess(message="Venta registrada exitosamente", id_sale=db_sale.id)


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
