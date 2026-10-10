"""
Los niveles y el kárdex sobre SQLAlchemy (F15, T-1502).

Acá vive la parte delicada del plan §15.1: que la fila del nivel **nazca con el
candado** y que la suma de la ficha se mantenga **en la base**, no en Python.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.domain.inventory import Movement
from app.domain.money import Money
from app.models.model_inventory import StockLevel, StockMovement
from app.models.model_product import Product
from app.utils.tenancy import compania_actual


class SqlAlchemyStockLevelRepository:
    """Cumple `StockLevelRepository`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def lock(self, product_id: int, branch_id: int) -> int:
        """`INSERT … ON DUPLICATE KEY UPDATE` y después `SELECT … FOR UPDATE`.

        Dos primeras entradas simultáneas al mismo (producto, sucursal) no
        mueren en `uq_stock_levels`: la segunda espera a la primera en el
        INSERT, que ya toma el candado de la fila duplicada. Se llama después de
        bloquear `products`, siempre (plan §15.1).

        La compañía va escrita: es un INSERT de Core y el sellado automático
        solo alcanza al ORM.
        """
        nace = mysql_insert(StockLevel).values(
            company_id=compania_actual(),
            product_id=product_id,
            branch_id=branch_id,
            quantity=0,
        )
        self._db.execute(nace.on_duplicate_key_update(quantity=StockLevel.quantity))
        return self._fila(product_id, branch_id, bloqueada=True).quantity

    def set(self, product_id: int, branch_id: int, quantity: int) -> None:
        self._fila(product_id, branch_id).quantity = quantity

    def levels_of(self, product_id: int) -> dict[int, int]:
        filas = self._db.query(StockLevel).filter(StockLevel.product_id == product_id).all()
        return {fila.branch_id: fila.quantity for fila in filas}

    def levels_in(self, branch_id: int) -> dict[int, int]:
        filas = self._db.query(StockLevel).filter(StockLevel.branch_id == branch_id).all()
        return {fila.product_id: fila.quantity for fila in filas}

    def add_to_total(self, product_id: int, delta: int) -> None:
        """`UPDATE products SET stock = stock + :delta`, atómico en la fila.

        Leer, sumar y escribir sería el error clásico de `REPEATABLE READ`: la
        segunda transacción no ve lo que la primera acaba de confirmar. El
        `company_id` va escrito porque los UPDATE del ORM no pasan por el
        filtro automático (plan §3.3); `fetch` deja al día la fila que la
        sesión tenga cargada.
        """
        self._db.execute(
            update(Product)
            .where(Product.id_product == product_id, Product.company_id == compania_actual())
            .values(stock=Product.stock + delta)
            .execution_options(synchronize_session="fetch")
        )

    def _fila(self, product_id: int, branch_id: int, *, bloqueada: bool = False) -> StockLevel:
        consulta = self._db.query(StockLevel).filter(
            StockLevel.product_id == product_id, StockLevel.branch_id == branch_id
        )
        if bloqueada:
            consulta = consulta.with_for_update()
        return consulta.one()


def _a_movimiento(fila: StockMovement) -> Movement:
    return Movement(
        id=fila.id,
        product_id=fila.product_id,
        branch_id=fila.branch_id,
        kind=fila.kind,
        quantity=fila.quantity,
        before_qty=fila.before_qty,
        after_qty=fila.after_qty,
        unit_cost=Money(fila.unit_cost),
        avg_cost_after=Money(fila.avg_cost_after),
        lot_id=fila.lot_id,
        source_type=fila.source_type,
        source_id=fila.source_id,
        source_line=fila.source_line,
        user_id=fila.user_id,
        moved_at=fila.moved_at,
    )


class SqlAlchemyKardex:
    """Cumple `KardexWriter` y `KardexReader`. Una tabla, los dos lados."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(self, movement: Movement) -> int:
        fila = StockMovement(
            product_id=movement.product_id,
            branch_id=movement.branch_id,
            kind=movement.kind,
            quantity=movement.quantity,
            before_qty=movement.before_qty,
            after_qty=movement.after_qty,
            unit_cost=movement.unit_cost.amount,
            avg_cost_after=movement.avg_cost_after.amount,
            lot_id=movement.lot_id,
            source_type=movement.source_type,
            source_id=movement.source_id,
            source_line=movement.source_line,
            user_id=movement.user_id,
            moved_at=movement.moved_at,
        )
        self._db.add(fila)
        # `flush` y no `commit`: el id sin cerrar la transacción, como la venta.
        self._db.flush()
        return fila.id

    def of_product(
        self,
        product_id: int,
        *,
        branch_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Movement]:
        consulta = self._db.query(StockMovement).filter(StockMovement.product_id == product_id)
        if branch_id is not None:
            consulta = consulta.filter(StockMovement.branch_id == branch_id)
        if since is not None:
            consulta = consulta.filter(StockMovement.moved_at >= since)
        if until is not None:
            consulta = consulta.filter(StockMovement.moved_at <= until)
        # Del más reciente al más viejo; el id desempata dos del mismo segundo.
        filas = consulta.order_by(StockMovement.moved_at.desc(), StockMovement.id.desc()).all()
        return [_a_movimiento(fila) for fila in filas]

    def of_source(self, source_type: str, source_id: int) -> list[Movement]:
        filas = (
            self._db.query(StockMovement)
            .filter(
                StockMovement.source_type == source_type, StockMovement.source_id == source_id
            )
            .order_by(StockMovement.id)
            .all()
        )
        return [_a_movimiento(fila) for fila in filas]
