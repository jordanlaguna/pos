"""Lógica del turno de caja."""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.model_cash import CashMovement, CashSession
from app.models.model_person import Person
from app.models.model_return import Return
from app.models.model_sales import Sale
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


def build_report(db: Session, session: CashSession) -> dict:
    """Arma el estado completo del turno.

    Las ventas se atribuyen por ventana de tiempo: las del mismo cajero entre la
    apertura y el cierre (o ahora, si sigue abierta). Por eso `sales.created_at`
    tiene que ser DATETIME — con DATE todas las del día caerían en el mismo
    instante y no habría forma de separar turnos.
    """

    start = session.opened_at
    end = session.closed_at or datetime.now()

    sales = (
        db.query(Sale)
        .filter(
            Sale.user_id == session.user_id,
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .all()
    )

    movements = (
        db.query(CashMovement)
        .filter(CashMovement.session_id == session.id)
        .order_by(CashMovement.created_at)
        .all()
    )

    returns_total = (
        db.query(func.coalesce(func.sum(Return.total), 0))
        .filter(
            Return.user_id == session.user_id,
            Return.created_at >= start,
            Return.created_at <= end,
        )
        .scalar()
    )

    by_method: dict[str, dict] = {}
    for sale in sales:
        entry = by_method.setdefault(
            sale.payment_method, {"payment_method": sale.payment_method, "count": 0, "total": Decimal(0)}
        )
        entry["count"] += 1
        entry["total"] += Decimal(str(sale.total))

    # Solo el efectivo pasa por la gaveta: tarjeta y transferencia no la afectan.
    cash_sales = sum(
        (Decimal(str(s.total)) for s in sales if s.payment_method == "Efectivo"),
        Decimal(0),
    )
    movements_in = sum(
        (Decimal(str(m.amount)) for m in movements if m.type == "entrada"), Decimal(0)
    )
    movements_out = sum(
        (Decimal(str(m.amount)) for m in movements if m.type == "salida"), Decimal(0)
    )

    expected = (
        Decimal(str(session.opening_amount))
        + cash_sales
        + movements_in
        - movements_out
        - Decimal(str(returns_total or 0))
    )

    difference = None
    if session.closing_amount is not None:
        difference = _money(Decimal(str(session.closing_amount)) - expected)

    return {
        "id": session.id,
        "user_id": session.user_id,
        "user_name": _user_name(db, session.user_id),
        "opened_at": session.opened_at,
        "closed_at": session.closed_at,
        "opening_amount": _money(session.opening_amount),
        "closing_amount": _money(session.closing_amount) if session.closing_amount is not None else None,
        "expected_amount": _money(expected),
        "difference": difference,
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
        "sales_count": len(sales),
        "sales_total": _money(sum((Decimal(str(s.total)) for s in sales), Decimal(0))),
        "by_payment_method": [
            {"payment_method": v["payment_method"], "count": v["count"], "total": _money(v["total"])}
            for v in sorted(by_method.values(), key=lambda x: x["total"], reverse=True)
        ],
        "cash_sales": _money(cash_sales),
        "movements_in": _money(movements_in),
        "movements_out": _money(movements_out),
        "returns_total": _money(returns_total),
    }


def open_session(db: Session, user_id: int, opening_amount: float, notes: str | None) -> dict:
    if get_open_session(db, user_id):
        raise HTTPException(status_code=400, detail="Ya existe una caja abierta para este usuario.")
    if opening_amount < 0:
        raise HTTPException(status_code=400, detail="El monto de apertura no puede ser negativo.")

    session = CashSession(
        user_id=user_id,
        opened_at=datetime.now(),
        opening_amount=opening_amount,
        status="abierta",
        notes=notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return build_report(db, session)


def add_movement(db: Session, user_id: int, type_: str, amount: float, reason: str) -> dict:
    if type_ not in ("entrada", "salida"):
        raise HTTPException(status_code=400, detail="El tipo de movimiento debe ser 'entrada' o 'salida'.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor que cero.")
    if not reason or not reason.strip():
        raise HTTPException(status_code=400, detail="Indique el motivo del movimiento.")

    session = get_open_session(db, user_id)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="No hay una caja abierta. Abra la caja antes de registrar movimientos.",
        )

    # No se puede sacar más efectivo del que hay: la gaveta no queda en negativo.
    if type_ == "salida":
        available = build_report(db, session)["expected_amount"]
        if amount > available:
            raise HTTPException(
                status_code=400,
                detail=f"No hay suficiente efectivo en caja. Disponible: {available:.2f}.",
            )

    movement = CashMovement(
        session_id=session.id,
        type=type_,
        amount=amount,
        reason=reason.strip(),
        created_at=datetime.now(),
    )
    db.add(movement)
    db.commit()
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
    session = get_open_session(db, user_id)
    if not session:
        raise HTTPException(status_code=400, detail="No hay una caja abierta para este usuario.")
    if closing_amount < 0:
        raise HTTPException(status_code=400, detail="El monto contado no puede ser negativo.")

    session.closing_amount = closing_amount
    session.closed_at = datetime.now()
    session.status = "cerrada"
    if notes:
        session.notes = notes

    db.commit()
    db.refresh(session)
    return build_report(db, session)
