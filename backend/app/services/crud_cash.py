"""Turno de caja — adaptador.

El cálculo y las reglas se mudaron a
`app/application/use_cases/cash_session.py` y `app/domain/cash.py`. Lo que queda
acá es la traducción: armar los puertos desde la sesión de SQLAlchemy, convertir
los «no» del dominio en códigos de estado y darle al JSON la forma que el API ya
tenía. Los mensajes son los mismos de antes, palabra por palabra.
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    CloseCashSession,
    NoOpenSession,
    OpenCashSession,
    SessionAlreadyOpen,
)
from app.domain.errors import InsufficientCash, InvalidMovement
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyCashRepository,
    SqlAlchemyReturnRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_cash import CashSession
from app.models.model_person import Person
from app.models.model_user import User


def _money(value) -> float:
    """Decimal → float con 2 decimales. La API habla JSON, y JSON no tiene Decimal."""
    return float(round(Decimal(str(value or 0)), 2))


def _user_name(db: Session, user_id: int) -> str | None:
    row = (
        db.query(Person.name, Person.lastName)
        .join(User, User.id_person == Person.id_person)
        .filter(User.id_user == user_id)
        .first()
    )
    return f"{row[0]} {row[1]}".strip() if row else None


def get_open_session(db: Session, user_id: int) -> CashSession | None:
    return (
        db.query(CashSession)
        .filter(CashSession.user_id == user_id, CashSession.status == "abierta")
        .first()
    )


def _reporte(db: Session) -> BuildSessionReport:
    return BuildSessionReport(
        sales=SqlAlchemySaleRepository(db),
        returns=SqlAlchemyReturnRepository(db),
        cash=SqlAlchemyCashRepository(db),
        clock=SystemClock(),
    )


def build_report(db: Session, session: CashSession) -> dict:
    """Arma el estado completo del turno, tal como lo espera el API.

    El cálculo se mudó a `application/use_cases/cash_session.py`; acá queda la
    forma del JSON. `_money` en cada cifra porque JSON no tiene Decimal.
    """
    cifras = _reporte(db)(
        session_id=session.id,
        user_id=session.user_id,
        opening=Money(session.opening_amount),
        opened_at=session.opened_at,
        closed_at=session.closed_at,
        counted=Money(session.closing_amount) if session.closing_amount is not None else None,
    )
    movements = SqlAlchemyCashRepository(db).movements(session.id)

    return {
        "id": session.id,
        "user_id": session.user_id,
        "user_name": _user_name(db, session.user_id),
        "opened_at": session.opened_at,
        "closed_at": session.closed_at,
        "opening_amount": _money(session.opening_amount),
        "closing_amount": _money(session.closing_amount) if session.closing_amount is not None else None,
        "expected_amount": cifras.expected.as_float(),
        "difference": cifras.difference.as_float() if cifras.difference is not None else None,
        "status": session.status,
        "notes": session.notes,
        "movements": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "type": m.type,
                "amount": _money(m.amount),
                "reason": m.reason,
                "created_at": m.created_at,
            }
            for m in movements
        ],
        "sales_count": cifras.sales_count,
        "sales_total": cifras.sales_total.as_float(),
        "by_payment_method": [
            {"payment_method": metodo, "count": n, "total": total.as_float()}
            for metodo, n, total in cifras.by_payment_method
        ],
        "cash_sales": cifras.cash_sales.as_float(),
        "movements_in": cifras.movements_in.as_float(),
        "movements_out": cifras.movements_out.as_float(),
        "returns_total": cifras.returns_total.as_float(),
    }


def open_session(db: Session, user_id: int, opening_amount: float, notes: str | None) -> dict:
    caso = OpenCashSession(
        cash=SqlAlchemyCashRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock()
    )
    try:
        session = caso(user_id=user_id, opening=Money(opening_amount), notes=notes)
    except SessionAlreadyOpen:
        raise HTTPException(
            status_code=400, detail="Ya existe una caja abierta para este usuario."
        ) from None
    except InvalidMovement:
        raise HTTPException(
            status_code=400, detail="El monto de apertura no puede ser negativo."
        ) from None

    db.refresh(session)
    return build_report(db, session)


def add_movement(db: Session, user_id: int, type_: str, amount: float, reason: str) -> dict:
    caso = AddCashMovement(
        cash=SqlAlchemyCashRepository(db),
        report=_reporte(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    try:
        movement = caso(user_id=user_id, type_=type_, amount=Money(amount), reason=reason)
    except NoOpenSession:
        raise HTTPException(
            status_code=400,
            detail="No hay una caja abierta. Abra la caja antes de registrar movimientos.",
        ) from None
    except InsufficientCash as e:
        raise HTTPException(
            status_code=400,
            detail=f"No hay suficiente efectivo en caja. Disponible: {e.available}.",
        ) from None
    except InvalidMovement as e:
        mensajes = {
            "el tipo debe ser 'entrada' o 'salida'": "El tipo de movimiento debe ser 'entrada' o 'salida'.",
            "el monto debe ser mayor que cero": "El monto debe ser mayor que cero.",
            "hace falta el motivo del movimiento": "Indique el motivo del movimiento.",
        }
        raise HTTPException(status_code=400, detail=mensajes.get(e.motivo, e.motivo)) from None

    db.refresh(movement)
    return {
        "id": movement.id,
        "session_id": movement.session_id,
        "type": movement.type,
        "amount": _money(movement.amount),
        "reason": movement.reason,
        "created_at": movement.created_at,
    }


def close_session(db: Session, user_id: int, closing_amount: float, notes: str | None) -> dict:
    caso = CloseCashSession(
        cash=SqlAlchemyCashRepository(db), uow=SqlAlchemyUnitOfWork(db), clock=SystemClock()
    )
    try:
        session = caso(user_id=user_id, counted=Money(closing_amount), notes=notes)
    except NoOpenSession:
        raise HTTPException(
            status_code=400, detail="No hay una caja abierta para este usuario."
        ) from None
    except InvalidMovement:
        raise HTTPException(
            status_code=400, detail="El monto contado no puede ser negativo."
        ) from None

    db.refresh(session)
    return build_report(db, session)
