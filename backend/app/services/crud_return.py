"""Devoluciones: revierten una venta, total o parcialmente, y reponen el stock."""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_user import User
from app.services.crud_settings import get_tax_rate


def _money(value) -> float:
    return float(round(Decimal(str(value or 0)), 2))


def _user_name(db: Session, user_id: int) -> str | None:
    row = (
        db.query(Person.name, Person.lastName)
        .join(User, User.id_person == Person.id_person)
        .filter(User.id_user == user_id)
        .first()
    )
    return f"{row[0]} {row[1]}".strip() if row else None


def _sale_tax_rate(db: Session, sale) -> Decimal:
    """Tasa de impuesto con la que se cobró ESTA venta.

    Se deduce de la venta misma (tax / subtotal) y no de la configuración
    vigente. Si el negocio cambia la tasa mañana, la devolución de una venta de
    hoy tiene que reembolsar lo que se cobró hoy; con la tasa actual se
    devolvería de más o de menos y el arqueo cerraría con una diferencia que
    nadie sabría explicar.

    La configuración solo entra como respaldo, para ventas viejas guardadas sin
    desglose (subtotal en cero), que es como quedaron las del WinForms.
    """
    subtotal = Decimal(str(sale.subtotal or 0))
    tax = Decimal(str(sale.tax or 0))
    if subtotal > 0:
        return (tax / subtotal).quantize(Decimal("0.000001"))
    return get_tax_rate(db)


def _returned_quantities(db: Session, sale_id: int) -> dict[int, int]:
    """Unidades ya devueltas por producto, para no devolver dos veces lo mismo."""
    rows = (
        db.query(ReturnDetail.product_id, ReturnDetail.quantity)
        .join(Return, Return.id == ReturnDetail.return_id)
        .filter(Return.sale_id == sale_id)
        .all()
    )
    totals: dict[int, int] = {}
    for product_id, quantity in rows:
        totals[product_id] = totals.get(product_id, 0) + quantity
    return totals


def _is_full(db: Session, sale_id: int) -> bool:
    """True si no queda ninguna unidad de la venta por devolver."""
    sold = db.query(SaleDetail).filter(SaleDetail.sale_id == sale_id).all()
    returned = _returned_quantities(db, sale_id)
    return all(returned.get(d.product_id, 0) >= d.quantity for d in sold)


def serialize(db: Session, record: Return) -> dict:
    sale = db.query(Sale).filter(Sale.id == record.sale_id).first()
    details = db.query(ReturnDetail).filter(ReturnDetail.return_id == record.id).all()

    items = []
    for detail in details:
        product = db.query(Product).filter(Product.id_product == detail.product_id).first()
        items.append(
            {
                "id_product": detail.product_id,
                "name": product.name if product else f"Producto #{detail.product_id}",
                "quantity": detail.quantity,
                "price": _money(detail.unit_price),
                "subtotal": _money(detail.subtotal),
            }
        )

    return {
        "id": record.id,
        "sale_id": record.sale_id,
        "sale_number": sale.sale_number if sale else "",
        "user_id": record.user_id,
        "user_name": _user_name(db, record.user_id),
        "created_at": record.created_at,
        "reason": record.reason,
        "total": _money(record.total),
        "is_full": _is_full(db, record.sale_id),
        "items": items,
    }


def create_return(db: Session, payload) -> dict:
    sale = db.query(Sale).filter(Sale.id == payload.sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Debe indicar al menos un producto a devolver.")
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Indique el motivo de la devolución.")

    sold = {
        d.product_id: d for d in db.query(SaleDetail).filter(SaleDetail.sale_id == sale.id).all()
    }
    already = _returned_quantities(db, sale.id)

    # Se valida TODO antes de escribir: o entra la devolución completa, o ninguna.
    validated = []
    for item in payload.items:
        detail = sold.get(item.id_product)
        if not detail:
            raise HTTPException(
                status_code=400,
                detail=f"El producto ID {item.id_product} no pertenece a esta venta.",
            )
        if item.quantity <= 0:
            raise HTTPException(
                status_code=400, detail=f"Cantidad inválida para el producto ID {item.id_product}."
            )

        remaining = detail.quantity - already.get(item.id_product, 0)
        if item.quantity > remaining:
            product = db.query(Product).filter(Product.id_product == item.id_product).first()
            name = product.name if product else f"producto ID {item.id_product}"
            raise HTTPException(
                status_code=400,
                detail=f"Solo quedan {remaining} unidades por devolver de {name}.",
            )

        unit_price = Decimal(str(detail.unit_price))
        validated.append(
            {
                "product_id": item.id_product,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": (unit_price * item.quantity).quantize(Decimal("0.01")),
            }
        )

    net_subtotal = sum((v["subtotal"] for v in validated), Decimal(0))
    total = (net_subtotal * (Decimal(1) + _sale_tax_rate(db, sale))).quantize(Decimal("0.01"))

    try:
        record = Return(
            sale_id=sale.id,
            user_id=payload.user_id,
            created_at=datetime.now(),
            reason=payload.reason.strip(),
            total=total,
        )
        db.add(record)
        db.flush()  # asigna record.id sin cerrar la transacción

        for value in validated:
            db.add(
                ReturnDetail(
                    return_id=record.id,
                    product_id=value["product_id"],
                    quantity=value["quantity"],
                    unit_price=value["unit_price"],
                    subtotal=value["subtotal"],
                )
            )
            # El stock vuelve al inventario: esto es lo que el sistema no hacía.
            product = db.query(Product).filter(Product.id_product == value["product_id"]).first()
            if product:
                product.stock += value["quantity"]

        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en base de datos: {exc}")

    return {
        "message": "Devolución registrada exitosamente",
        "id_return": record.id,
        "total": _money(total),
    }
