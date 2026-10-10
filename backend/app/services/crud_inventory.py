"""El kárdex y las existencias por sucursal — adaptador (F15, T-1502).

Acá se arma `MoveStock` con sus adaptadores de SQLAlchemy —es lo que la venta,
la devolución, la entrada y la ficha reciben— y se leen el kárdex y los
niveles para las pantallas. Nada de reglas: están en `domain/inventory.py`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.move_stock import MoveStock
from app.application.use_cases.stock_count import (
    ApplyStockCount,
    CountAlreadyOpen,
    CountCategoryNotFound,
    CountHasNoLines,
    CountNotFound,
    CountNotOpen,
    DiscardStockCount,
    OpenCountRequest,
    OpenStockCount,
    ProductNotFoundInCount,
    RecordCountLine,
)
from app.application.use_cases.stock_exit import (
    CancelStockExit,
    EmptyExit,
    ExitCancelled,
    ExitNotFound,
    ExitRequest,
    MissingVoidReason,
    ProductNotFoundInExit,
    ReasonNotFound,
    RegisterStockExit,
    RequestedExitLine,
)
from app.domain.errors import (
    InsufficientStock,
    InvalidQuantity,
    OutsideCountScope,
    ReasonInactive,
    ReasonIsSystem,
)
from app.domain.inventory import Movement, check_reason_deactivatable, count_difference
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_inventory import (
    SqlAlchemyKardex,
    SqlAlchemyStockCountRepository,
    SqlAlchemyStockExitRepository,
    SqlAlchemyStockLevelRepository,
    SqlAlchemyStockReasonRepository,
)
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_categories import Category
from app.models.model_inventory import (
    StockCount,
    StockCountLine,
    StockExit,
    StockExitDetail,
    StockReason,
)
from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_user import User
from app.services import crud_accounting, crud_membership
from app.utils.api_errors import api_error
from app.utils.tenancy import sucursal_actual


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


# ----------------------------------------------------- los motivos (RN-99)


def _motivo(fila: StockReason) -> dict:
    return {
        "id": fila.id,
        "code": fila.code,
        "name": fila.name,
        "is_system": bool(fila.is_system),
        "is_active": bool(fila.is_active),
    }


def reasons(db: Session) -> list[dict]:
    """Todos, apagados incluidos: la pantalla los muestra y las salidas viejas los nombran."""
    return [_motivo(f) for f in db.query(StockReason).order_by(StockReason.id).all()]


def create_reason(db: Session, payload) -> dict:
    codigo = payload.code.strip()
    if db.query(StockReason).filter(StockReason.code == codigo).first() is not None:
        raise api_error(400, "reason_code_taken", reason_code=codigo)
    fila = StockReason(code=codigo, name=payload.name.strip(), is_system=False, is_active=True)
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return _motivo(fila)


def update_reason(db: Session, reason_id: int, payload) -> dict:
    fila = db.query(StockReason).filter(StockReason.id == reason_id).first()
    if fila is None:
        raise api_error(404, "reason_not_found", reason_id=reason_id)
    if payload.is_active is False:
        # El de la toma física no se apaga (RN-100): la regla es del dominio.
        try:
            check_reason_deactivatable(fila.id, is_system=bool(fila.is_system))
        except ReasonIsSystem:
            raise api_error(400, "reason_is_system", reason_id=reason_id) from None
    if payload.name is not None:
        fila.name = payload.name.strip()
    if payload.is_active is not None:
        fila.is_active = payload.is_active
    db.commit()
    db.refresh(fila)
    return _motivo(fila)


# ----------------------------------------------------- las salidas (RN-99)


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


def serialize_exit(db: Session, salida: StockExit) -> dict:
    detalles = (
        db.query(StockExitDetail)
        .filter(StockExitDetail.exit_id == salida.id)
        .order_by(StockExitDetail.id)
        .all()
    )
    nombres = {
        p.id_product: p.name
        for p in db.query(Product)
        .filter(Product.id_product.in_([d.product_id for d in detalles] or [0]))
        .all()
    }
    motivo = db.query(StockReason).filter(StockReason.id == salida.reason_id).first()
    return {
        "id": salida.id,
        "branch_id": salida.branch_id,
        "reason_id": salida.reason_id,
        "reason_code": motivo.code if motivo else "",
        "reason_name": motivo.name if motivo else "",
        "user_id": salida.user_id,
        "user_name": _user_name(db, salida.user_id),
        "created_at": salida.created_at,
        "notes": salida.notes,
        "status": salida.status,
        "total_cost": _money(salida.total_cost),
        "items_count": sum(d.quantity for d in detalles),
        "voided_at": salida.voided_at,
        "void_reason": salida.void_reason,
        "lines": [
            {
                "id_product": d.product_id,
                "name": nombres.get(d.product_id, f"#{d.product_id}"),
                "quantity": d.quantity,
                "unit_cost": _money(d.unit_cost),
                "subtotal": _money(Decimal(str(d.unit_cost)) * d.quantity),
                "lot_id": d.lot_id,
            }
            for d in detalles
        ],
    }


def exits(db: Session, limit: int = 200) -> list[dict]:
    filas = (
        db.query(StockExit)
        .order_by(StockExit.created_at.desc(), StockExit.id.desc())
        .limit(limit)
        .all()
    )
    return [serialize_exit(db, f) for f in filas]


def create_exit(db: Session, payload, *, user_id: int) -> dict:
    productos = SqlAlchemyProductRepository(db)
    caso = RegisterStockExit(
        products=productos,
        reasons=SqlAlchemyStockReasonRepository(db),
        exits=SqlAlchemyStockExitRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        stock=mover(db),
        # Del inventario al gasto, en la misma transacción (RN-59).
        ledger=crud_accounting.libro(db, user_id=user_id),
    )
    peticion = ExitRequest(
        reason_id=payload.reason_id,
        user_id=user_id,
        # De dónde sale: la sucursal de la sesión (RN-14, RN-102).
        branch_id=sucursal_actual(),
        notes=(payload.notes or "").strip() or None,
        lines=[RequestedExitLine(l.id_product, l.quantity, l.lot_id) for l in payload.lines],
    )

    try:
        hecha = caso(peticion)
    except EmptyExit:
        raise api_error(400, "empty_exit") from None
    except InvalidQuantity:
        # El dominio no dice qué línea: la interfaz conoce el orden en que llegaron.
        indice = next(
            (
                i
                for i, l in enumerate(payload.lines, start=1)
                if not l.id_product or l.quantity <= 0
            ),
            None,
        )
        raise api_error(400, "invalid_exit_line", line=indice) from None
    except ReasonNotFound as e:
        raise api_error(404, "reason_not_found", reason_id=e.reason_id) from None
    except ReasonInactive as e:
        raise api_error(400, "reason_inactive", reason_id=e.reason_id) from None
    except ReasonIsSystem as e:
        raise api_error(400, "reason_is_system", reason_id=e.reason_id) from None
    except ProductNotFoundInExit as e:
        raise api_error(404, "product_not_found", product_id=e.product_id) from None
    except InsufficientStock as e:
        producto = productos.get(e.product_id)
        raise api_error(
            400,
            "insufficient_stock",
            product_id=e.product_id,
            product=producto.name if producto else None,
            available=e.available,
            requested=e.requested,
        ) from None
    except HTTPException:
        raise

    return {
        "message": "exit_registered",
        "id_exit": hecha.id_exit,
        "units": hecha.units,
        "total_cost": hecha.total_cost.as_float(),
    }


def cancel_exit(
    db: Session, exit_id: int, *, user_id: int, company_id: int, reason: str
) -> dict:
    """Anula una salida, con su bitácora en la misma transacción."""
    uow = SqlAlchemyUnitOfWork(db)
    caso = CancelStockExit(
        products=SqlAlchemyProductRepository(db),
        exits=SqlAlchemyStockExitRepository(db),
        uow=uow,
        clock=SystemClock(),
        stock=mover(db),
        ledger=crud_accounting.libro(db, user_id=user_id),
    )
    motivo = (reason or "").strip()

    try:
        with uow:
            anulada = caso.apply(exit_id, user_id=user_id, reason=motivo)
            crud_membership.registrar(
                db,
                user_id=user_id,
                company_id=company_id,
                accion="anular_salida",
                # Identificadores y el motivo que escribió la persona (RN-30).
                detalle=f"salida {exit_id}, {anulada.units_returned} u, motivo: {motivo}",
                ip=None,
            )
            uow.commit()
    except MissingVoidReason:
        raise api_error(400, "void_reason_required") from None
    except ExitNotFound:
        raise api_error(404, "exit_not_found", exit_id=exit_id) from None
    except ExitCancelled:
        raise api_error(400, "exit_cancelled", exit_id=exit_id) from None
    except HTTPException:
        raise

    return {
        "message": "exit_voided",
        "id_exit": exit_id,
        "units_returned": anulada.units_returned,
    }


# -------------------------------------------------- la toma física (RN-100)


def _nombres(db: Session, product_ids: list[int]) -> dict[int, str]:
    if not product_ids:
        return {}
    return {
        p.id_product: p.name
        for p in db.query(Product).filter(Product.id_product.in_(product_ids)).all()
    }


def serialize_count(db: Session, toma: StockCount, *, with_lines: bool = True) -> dict:
    lineas = (
        db.query(StockCountLine)
        .filter(StockCountLine.count_id == toma.id)
        .order_by(StockCountLine.id)
        .all()
    )
    nombres = _nombres(db, [l.product_id for l in lineas]) if with_lines else {}
    categoria = (
        db.query(Category).filter(Category.id == toma.category_id).first()
        if toma.category_id is not None
        else None
    )
    return {
        "id": toma.id,
        "branch_id": toma.branch_id,
        "category_id": toma.category_id,
        "category_name": categoria.name if categoria else None,
        "status": toma.status,
        "opened_by": toma.opened_by,
        "opened_at": toma.opened_at,
        "closed_by": toma.closed_by,
        "closed_at": toma.closed_at,
        "notes": toma.notes,
        "lines_count": len(lineas),
        "lines": [
            {
                "id_product": l.product_id,
                "name": nombres.get(l.product_id, f"#{l.product_id}"),
                "lot_id": l.lot_id,
                "system_qty": l.system_qty,
                "counted_qty": l.counted_qty,
                "difference": count_difference(l.system_qty, l.counted_qty),
                "counted_at": l.counted_at,
                "counted_by": l.counted_by,
            }
            for l in lineas
        ]
        if with_lines
        else [],
    }


def counts(db: Session, limit: int = 200) -> list[dict]:
    filas = (
        db.query(StockCount)
        .order_by(StockCount.opened_at.desc(), StockCount.id.desc())
        .limit(limit)
        .all()
    )
    return [serialize_count(db, f, with_lines=False) for f in filas]


def get_count(db: Session, count_id: int) -> dict:
    fila = db.query(StockCount).filter(StockCount.id == count_id).first()
    if fila is None:
        raise api_error(404, "count_not_found", count_id=count_id)
    return serialize_count(db, fila)


def _tomas(db: Session) -> SqlAlchemyStockCountRepository:
    return SqlAlchemyStockCountRepository(db)


def open_count(db: Session, payload, *, user_id: int) -> dict:
    caso = OpenStockCount(
        categories=SqlAlchemyCategoryRepository(db),
        counts=_tomas(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    try:
        abierta = caso(
            OpenCountRequest(
                branch_id=sucursal_actual(),
                category_id=payload.category_id,
                user_id=user_id,
                notes=(payload.notes or "").strip() or None,
            )
        )
    except CountCategoryNotFound as e:
        raise api_error(404, "category_not_found", category_id=e.category_id) from None
    except CountAlreadyOpen as e:
        raise api_error(
            409,
            "count_already_open",
            count_id=e.count_id,
            branch_id=e.branch_id,
            category_id=e.category_id,
        ) from None
    return {"message": "count_opened", "id_count": abierta.id_count}


def _toma_a_http(e):
    if isinstance(e, CountNotFound):
        return api_error(404, "count_not_found", count_id=e.count_id)
    return api_error(400, "count_not_open", count_id=e.count_id, status=e.status)


def count_line(db: Session, count_id: int, payload, *, user_id: int) -> dict:
    caso = RecordCountLine(
        products=SqlAlchemyProductRepository(db),
        categories=SqlAlchemyCategoryRepository(db),
        counts=_tomas(db),
        levels=SqlAlchemyStockLevelRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )
    try:
        contada = caso(
            count_id,
            product_id=payload.id_product,
            counted_qty=payload.counted_qty,
            user_id=user_id,
            lot_id=payload.lot_id,
        )
    except (CountNotFound, CountNotOpen) as e:
        raise _toma_a_http(e) from None
    except ProductNotFoundInCount as e:
        raise api_error(404, "product_not_found", product_id=e.product_id) from None
    except OutsideCountScope as e:
        raise api_error(
            400,
            "count_outside_scope",
            product_id=e.product_id,
            category_id=e.category_id,
            scope_category_id=e.scope_category_id,
        ) from None
    except HTTPException:
        raise
    return {
        "message": "count_line_recorded",
        "id_product": contada.product_id,
        "system_qty": contada.system_qty,
        "counted_qty": contada.counted_qty,
        "difference": contada.difference,
    }


def apply_count(db: Session, count_id: int, *, user_id: int, company_id: int) -> dict:
    """Aplica la toma, con su bitácora en la misma transacción."""
    productos = SqlAlchemyProductRepository(db)
    uow = SqlAlchemyUnitOfWork(db)
    caso = ApplyStockCount(
        products=productos,
        counts=_tomas(db),
        uow=uow,
        clock=SystemClock(),
        stock=mover(db),
        ledger=crud_accounting.libro(db, user_id=user_id),
    )
    try:
        with uow:
            aplicada = caso.apply(count_id, user_id=user_id)
            crud_membership.registrar(
                db,
                user_id=user_id,
                company_id=company_id,
                accion="aplicar_toma",
                detalle=f"toma {count_id}, {aplicada.adjustments} ajustes, "
                f"{aplicada.difference_cost.as_float()}",
                ip=None,
            )
            uow.commit()
    except (CountNotFound, CountNotOpen) as e:
        raise _toma_a_http(e) from None
    except CountHasNoLines:
        raise api_error(400, "count_has_no_lines", count_id=count_id) from None
    except InsufficientStock as e:
        # Se vendió más de lo que la toma iba a quitar: se vuelve a contar.
        producto = productos.get(e.product_id)
        raise api_error(
            400,
            "insufficient_stock",
            product_id=e.product_id,
            product=producto.name if producto else None,
            available=e.available,
            requested=e.requested,
        ) from None
    except HTTPException:
        raise
    return {
        "message": "count_applied",
        "id_count": count_id,
        "adjustments": aplicada.adjustments,
        "difference_cost": aplicada.difference_cost.as_float(),
    }


def discard_count(db: Session, count_id: int, *, user_id: int, company_id: int) -> dict:
    uow = SqlAlchemyUnitOfWork(db)
    caso = DiscardStockCount(counts=_tomas(db), uow=uow, clock=SystemClock())
    try:
        with uow:
            caso.apply(count_id, user_id=user_id)
            crud_membership.registrar(
                db,
                user_id=user_id,
                company_id=company_id,
                accion="descartar_toma",
                detalle=f"toma {count_id}",
                ip=None,
            )
            uow.commit()
    except (CountNotFound, CountNotOpen) as e:
        raise _toma_a_http(e) from None
    except HTTPException:
        raise
    return {"message": "count_discarded", "id_count": count_id}
