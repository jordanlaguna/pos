"""Devoluciones — adaptador.

Revierten una venta, total o parcialmente, y reponen el stock. Las reglas están
en `app/domain/returns.py` y el paso a paso en
`app/application/use_cases/register_return.py`; acá queda la traducción a HTTP,
con los mismos mensajes que antes.
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.register_return import (
    EmptyReturn,
    MissingReason,
    RegisterReturn,
    RequestedReturnLine,
    ReturnRequest,
    SaleNotFound,
)
from app.domain.errors import ExcessiveReturn, InvalidQuantity, NotSoldInThisSale
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyProductRepository,
    SqlAlchemyReturnRepository,
    SqlAlchemySaleRepository,
    SqlAlchemySettingsRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_user import User


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
    caso = RegisterReturn(
        sales=SqlAlchemySaleRepository(db),
        returns=SqlAlchemyReturnRepository(db),
        products=SqlAlchemyProductRepository(db),
        settings=SqlAlchemySettingsRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    peticion = ReturnRequest(
        sale_id=payload.sale_id,
        user_id=payload.user_id,
        reason=payload.reason or "",
        lines=[RequestedReturnLine(i.id_product, i.quantity) for i in (payload.items or [])],
    )

    try:
        resultado = caso(peticion)

    except SaleNotFound:
        raise HTTPException(status_code=404, detail="Venta no encontrada") from None
    except EmptyReturn:
        raise HTTPException(
            status_code=400, detail="Debe indicar al menos un producto a devolver."
        ) from None
    except MissingReason:
        raise HTTPException(
            status_code=400, detail="Indique el motivo de la devolución."
        ) from None
    except NotSoldInThisSale as e:
        raise HTTPException(
            status_code=400,
            detail=f"El producto ID {e.product_id} no pertenece a esta venta.",
        ) from None
    except InvalidQuantity:
        malo = next((i for i in payload.items if i.quantity <= 0), None)
        raise HTTPException(
            status_code=400,
            detail=f"Cantidad inválida para el producto ID {malo.id_product if malo else None}.",
        ) from None
    except ExcessiveReturn as e:
        product = db.query(Product).filter(Product.id_product == e.product_id).first()
        name = product.name if product else f"producto ID {e.product_id}"
        raise HTTPException(
            status_code=400,
            detail=f"Solo quedan {e.remaining} unidades por devolver de {name}.",
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al registrar la devolución: {exc}")

    return {
        "message": "Devolución registrada exitosamente",
        "id_return": resultado.id_return,
        "total": resultado.total.as_float(),
    }
