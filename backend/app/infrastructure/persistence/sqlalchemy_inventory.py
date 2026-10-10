"""
Los niveles y el kárdex sobre SQLAlchemy (F15, T-1502).

Acá vive la parte delicada del plan §15.1: que la fila del nivel **nazca con el
candado** y que la suma de la ficha se mantenga **en la base**, no en Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.domain.inventory import ExitLine, Movement
from app.domain.money import Money
from app.models.model_inventory import (
    StockCount,
    StockCountLine,
    StockExit,
    StockExitDetail,
    StockLevel,
    StockMovement,
    StockReason,
)
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

    def count_for(self, product_id: int) -> int:
        # Con `func.count`, que sí pasa por el filtro de compañía (test_tenancy).
        return (
            self._db.query(func.count(StockMovement.id))
            .filter(StockMovement.product_id == product_id)
            .scalar()
        )


# ----------------------------------------------------- las salidas (RN-99)


@dataclass(frozen=True)
class ReasonData:
    """Un motivo visto desde la salida. Cumple `ReasonSnapshot`."""

    id: int
    code: str
    name: str
    is_system: bool
    is_active: bool


class SqlAlchemyStockReasonRepository:
    """Cumple `StockReasonRepository`. El filtro por compañía lo pone la sesión."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, reason_id: int) -> ReasonData | None:
        fila = self._db.query(StockReason).filter(StockReason.id == reason_id).first()
        if fila is None:
            return None
        return ReasonData(
            id=fila.id,
            code=fila.code,
            name=fila.name,
            is_system=bool(fila.is_system),
            is_active=bool(fila.is_active),
        )


@dataclass(frozen=True)
class ExitData:
    """Una salida guardada. Cumple `ExitSnapshot`."""

    id: int
    branch_id: int
    reason_id: int
    status: str
    total_cost: Money


@dataclass(frozen=True)
class ExitLineData:
    """Una línea guardada. Cumple `ExitLineSnapshot`."""

    product_id: int
    quantity: int
    unit_cost: Money
    lot_id: int | None


class SqlAlchemyStockExitRepository:
    """Cumple `StockExitRepository`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, exit_id: int) -> ExitData | None:
        fila = self._db.query(StockExit).filter(StockExit.id == exit_id).first()
        if fila is None:
            return None
        return ExitData(
            id=fila.id,
            branch_id=fila.branch_id,
            reason_id=fila.reason_id,
            status=fila.status,
            total_cost=Money(fila.total_cost),
        )

    def add(
        self,
        *,
        branch_id: int,
        reason_id: int,
        user_id: int,
        notes: str | None,
        total_cost: Money,
        created_at: datetime,
        lines: list[ExitLine],
    ) -> int:
        salida = StockExit(
            branch_id=branch_id,
            reason_id=reason_id,
            user_id=user_id,
            created_at=created_at,
            notes=notes,
            status="applied",
            total_cost=total_cost.amount,
        )
        self._db.add(salida)
        # `flush` y no `commit`: el id sin cerrar la transacción, como la venta.
        self._db.flush()
        for linea in lines:
            self._db.add(
                StockExitDetail(
                    exit_id=salida.id,
                    product_id=linea.product_id,
                    quantity=linea.quantity,
                    unit_cost=linea.unit_cost.amount,
                    lot_id=linea.lot_id,
                )
            )
        return salida.id

    def lines_of(self, exit_id: int) -> list[ExitLineData]:
        filas = (
            self._db.query(StockExitDetail)
            .filter(StockExitDetail.exit_id == exit_id)
            .order_by(StockExitDetail.id)
            .all()
        )
        return [
            ExitLineData(
                product_id=fila.product_id,
                quantity=fila.quantity,
                unit_cost=Money(fila.unit_cost),
                lot_id=fila.lot_id,
            )
            for fila in filas
        ]

    def mark_voided(self, exit_id: int, *, voided_at: datetime, reason: str) -> None:
        salida = self._db.query(StockExit).filter(StockExit.id == exit_id).one()
        salida.status = "voided"
        salida.voided_at = voided_at
        salida.void_reason = reason


# -------------------------------------------------- la toma física (RN-100)


@dataclass(frozen=True)
class CountData:
    """Una toma guardada. Cumple `CountSnapshot`."""

    id: int
    branch_id: int
    category_id: int | None
    status: str


@dataclass(frozen=True)
class CountLineData:
    """Una línea contada. Cumple `CountLineSnapshot`."""

    product_id: int
    lot_id: int | None
    system_qty: int
    counted_qty: int


def _a_toma(fila: StockCount) -> CountData:
    return CountData(
        id=fila.id, branch_id=fila.branch_id, category_id=fila.category_id, status=fila.status
    )


class SqlAlchemyStockCountRepository:
    """Cumple `StockCountRepository`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, count_id: int) -> CountData | None:
        fila = self._db.query(StockCount).filter(StockCount.id == count_id).first()
        return _a_toma(fila) if fila else None

    def open_in_branch(self, branch_id: int) -> list[CountData]:
        filas = (
            self._db.query(StockCount)
            .filter(StockCount.branch_id == branch_id, StockCount.status == "open")
            .order_by(StockCount.id)
            .all()
        )
        return [_a_toma(fila) for fila in filas]

    def add(
        self,
        *,
        branch_id: int,
        category_id: int | None,
        opened_by: int,
        opened_at: datetime,
        notes: str | None,
    ) -> int:
        toma = StockCount(
            branch_id=branch_id,
            category_id=category_id,
            status="open",
            opened_by=opened_by,
            opened_at=opened_at,
            notes=notes,
        )
        self._db.add(toma)
        self._db.flush()
        return toma.id

    def lines_of(self, count_id: int) -> list[CountLineData]:
        filas = (
            self._db.query(StockCountLine)
            .filter(StockCountLine.count_id == count_id)
            .order_by(StockCountLine.id)
            .all()
        )
        return [
            CountLineData(
                product_id=fila.product_id,
                lot_id=fila.lot_id,
                system_qty=fila.system_qty,
                counted_qty=fila.counted_qty,
            )
            for fila in filas
        ]

    def record_line(
        self,
        count_id: int,
        *,
        product_id: int,
        lot_id: int | None,
        system_qty: int,
        counted_qty: int,
        counted_at: datetime,
        counted_by: int,
    ) -> None:
        # Reemplaza si ya se contó el (producto, lote): es lo que `uq_stock_count_lines`
        # sostiene, con `lot_key` para que «sin lote» cuente como un lote más.
        consulta = self._db.query(StockCountLine).filter(
            StockCountLine.count_id == count_id, StockCountLine.product_id == product_id
        )
        consulta = (
            consulta.filter(StockCountLine.lot_id.is_(None))
            if lot_id is None
            else consulta.filter(StockCountLine.lot_id == lot_id)
        )
        fila = consulta.first()
        if fila is None:
            fila = StockCountLine(count_id=count_id, product_id=product_id, lot_id=lot_id)
            self._db.add(fila)
        fila.system_qty = system_qty
        fila.counted_qty = counted_qty
        fila.counted_at = counted_at
        fila.counted_by = counted_by
        self._db.flush()

    def close(self, count_id: int, *, status: str, closed_by: int, closed_at: datetime) -> None:
        toma = self._db.query(StockCount).filter(StockCount.id == count_id).one()
        toma.status = status
        toma.closed_by = closed_by
        toma.closed_at = closed_at
