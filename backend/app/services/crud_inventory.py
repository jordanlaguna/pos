"""El kárdex y las existencias por sucursal — adaptador (F15, T-1502).

Acá se arma `MoveStock` con sus adaptadores de SQLAlchemy —es lo que la venta,
la devolución, la entrada y la ficha reciben— y se leen el kárdex y los
niveles para las pantallas. Nada de reglas: están en `domain/inventory.py`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.application.use_cases.move_stock import MoveStock
from app.domain.inventory import Movement
from app.infrastructure.persistence.sqlalchemy_inventory import (
    SqlAlchemyKardex,
    SqlAlchemyStockLevelRepository,
)
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyProductRepository


def mover(db: Session) -> MoveStock:
    """El único escritor de existencias, sobre esta sesión."""
    return MoveStock(
        products=SqlAlchemyProductRepository(db),
        levels=SqlAlchemyStockLevelRepository(db),
        kardex=SqlAlchemyKardex(db),
    )


def _serializar(movimiento: Movement) -> dict:
    return {
        "id": movimiento.id,
        "product_id": movimiento.product_id,
        "branch_id": movimiento.branch_id,
        "kind": movimiento.kind,
        "quantity": movimiento.quantity,
        "before_qty": movimiento.before_qty,
        "after_qty": movimiento.after_qty,
        "unit_cost": movimiento.unit_cost.as_float(),
        "avg_cost_after": movimiento.avg_cost_after.as_float(),
        "lot_id": movimiento.lot_id,
        "source_type": movimiento.source_type,
        "source_id": movimiento.source_id,
        "source_line": movimiento.source_line,
        "user_id": movimiento.user_id,
        "moved_at": movimiento.moved_at,
    }


def kardex(
    db: Session,
    *,
    product_id: int | None,
    branch_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
) -> list[dict]:
    """Los movimientos de un producto (RF-87), o los que dejó un documento.

    Con producto, filtrados por sucursal y periodo y del más reciente al más
    viejo; con documento, en el orden en que se anotaron. Las dos cosas a la
    vez acotan la primera a la segunda, que es lo que pregunta la línea de una
    venta. Sin ninguna de las dos no hay qué listar: lo decide la ruta.
    """
    lector = SqlAlchemyKardex(db)
    if product_id is None:
        movimientos = lector.of_source(source_type, source_id)
    else:
        movimientos = lector.of_product(product_id, branch_id=branch_id, since=since, until=until)
        if source_type is not None and source_id is not None:
            movimientos = [
                m for m in movimientos if m.source_type == source_type and m.source_id == source_id
            ]
    return [_serializar(m) for m in movimientos]


def niveles(
    db: Session, *, product_id: int | None = None, branch_id: int | None = None
) -> list[dict]:
    """La existencia por sucursal de un producto, o la de una sucursal entera."""
    repo = SqlAlchemyStockLevelRepository(db)
    if product_id is not None:
        return [
            {"product_id": product_id, "branch_id": sucursal, "quantity": cantidad}
            for sucursal, cantidad in sorted(repo.levels_of(product_id).items())
        ]
    return [
        {"product_id": producto, "branch_id": branch_id, "quantity": cantidad}
        for producto, cantidad in sorted(repo.levels_in(branch_id).items())
    ]
