"""Devoluciones — adaptador.

Revierten una venta, total o parcialmente, y reponen el stock. Las reglas están
en `app/domain/returns.py` y el paso a paso en
`app/application/use_cases/register_return.py`; acá queda la traducción a HTTP,
en código y datos, nunca en frases (RN-30).
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
from app.utils.api_errors import api_error


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
        # El desglose que la 006 empezó a guardar (T-509b). Con una sola tarifa
        # el impuesto se podía deducir del total; con tarifas mezcladas no hay
        # de dónde, así que se guarda y —por eso mismo— se devuelve.
        #
        # En nulo para las devoluciones anteriores a esa migración: ahí el total
        # es lo único que se registró, y decir un subtotal inventado sería peor
        # que decir que no se sabe.
        "subtotal": _money(record.subtotal) if record.subtotal is not None else None,
        "tax": _money(record.tax) if record.tax is not None else None,
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
        ledger=crud_accounting.libro(db, user_id=payload.user_id),
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
        raise api_error(404, "sale_not_found") from None
    except EmptyReturn:
        raise api_error(400, "empty_return") from None
    except MissingReason:
        raise api_error(400, "missing_return_reason") from None
    except NotSoldInThisSale as e:
        raise api_error(400, "not_sold_in_this_sale", product_id=e.product_id) from None
    except InvalidQuantity:
        malo = next((i for i in payload.items if i.quantity <= 0), None)
        raise api_error(
            400, "invalid_return_quantity", product_id=malo.id_product if malo else None
        ) from None
    except ExcessiveReturn as e:
        product = db.query(Product).filter(Product.id_product == e.product_id).first()
        raise api_error(
            400,
            "excessive_return",
            product_id=e.product_id,
            product=product.name if product else None,
            remaining=e.remaining,
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise api_error(500, "return_failed", cause=str(exc))

    return {
        "message": "return_registered",
        "id_return": resultado.id_return,
        "total": resultado.total.as_float(),
    }
