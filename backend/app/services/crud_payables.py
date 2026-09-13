"""Cuentas por pagar (F10, T-1012, RF-44).

**El saldo no se guarda**: el de una compra es su total menos sus abonos y el de
un proveedor es la suma de los de sus compras (RN-55). Un saldo guardado es un
número más que hay que mantener cuadrado, y el día que se descuadre nadie va a
saber cuál de los dos miente.

Como `crud_report.py`, **el filtro por compañía va escrito a mano**: esta
consulta pide un `SUM` agrupado y no carga entidades, así que el filtro
automático de `app/utils/tenancy.py` no la alcanza. Si mañana se agrega otra,
tiene que llevarlo también: no hay red debajo.

La aritmética no está acá. `remaining_balance` y `aging_bucket` viven en
`app/domain/purchases.py`, donde se prueban sin base y sin reloj.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.money import Money
from app.domain.purchases import TRAMOS, aging_bucket, remaining_balance
from app.models.model_stock_entry import StockEntry
from app.models.model_supplier import Supplier, SupplierPayment
from app.utils import clock
from app.utils.tenancy import compania_actual

#: Los cuatro tramos, de menor a mayor. El 0 es «por vencer o vencida hace
#: menos de 30 días» y el 90, «más de 90». Se devuelven **siempre los cuatro**,
#: aunque vayan en cero: una tabla que cambia de columnas según los datos se lee
#: distinto cada vez, y el que falta es justo el que uno querría ver vacío.
BUCKETS: tuple[int, ...] = (0, *TRAMOS)


def payables(db: Session, supplier_id: int | None = None) -> dict:
    """Lo que se le debe a cada proveedor, compra por compra.

    Solo entran las compras **aplicadas** —anular revierte la cuenta por pagar
    (RN-57), y como el saldo es implícito, basta con dejarlas fuera de acá— y
    solo las que tienen saldo: una pagada ya no es una cuenta por pagar.
    """
    hoy = clock.today()
    pagado = func.coalesce(func.sum(SupplierPayment.amount), 0)

    filas = (
        db.query(
            StockEntry.id,
            StockEntry.document_number,
            StockEntry.document_date,
            StockEntry.due_date,
            StockEntry.total_cost,
            StockEntry.supplier_id,
            Supplier.name,
            pagado,
        )
        .join(Supplier, Supplier.id == StockEntry.supplier_id)
        .outerjoin(SupplierPayment, SupplierPayment.entry_id == StockEntry.id)
        .filter(
            StockEntry.company_id == compania_actual(),
            Supplier.company_id == compania_actual(),
            StockEntry.status == "aplicada",
            StockEntry.supplier_id.isnot(None),
            *([StockEntry.supplier_id == supplier_id] if supplier_id else []),
        )
        .group_by(
            StockEntry.id,
            StockEntry.document_number,
            StockEntry.document_date,
            StockEntry.due_date,
            StockEntry.total_cost,
            StockEntry.supplier_id,
            Supplier.name,
        )
        .order_by(StockEntry.due_date, StockEntry.id)
        .all()
    )

    proveedores: dict[int, dict] = {}
    por_tramo = dict.fromkeys(BUCKETS, Money.zero())
    total = Money.zero()

    for fila in filas:
        saldo = remaining_balance(Money(fila.total_cost), [Money(fila[7])])
        if saldo.is_zero:
            continue

        tramo = aging_bucket(fila.due_date, hoy)
        proveedor = proveedores.setdefault(
            fila.supplier_id,
            {"supplier_id": fila.supplier_id, "name": fila.name, "balance": Money.zero(),
             "purchases": []},
        )
        proveedor["purchases"].append(
            {
                "entry_id": fila.id,
                "document_number": fila.document_number,
                "document_date": fila.document_date,
                "due_date": fila.due_date,
                "total": Money(fila.total_cost).as_float(),
                "paid": Money(fila[7]).as_float(),
                "balance": saldo.as_float(),
                "bucket": tramo,
                # Días de atraso, negativos si todavía no vence. Lo calcula acá
                # y no la pantalla porque el día de hoy lo pone el servidor,
                # igual que la hora de una venta: el reloj del cliente puede
                # estar en cualquier fecha.
                "days_overdue": _atraso(fila.due_date, hoy),
            }
        )
        proveedor["balance"] = proveedor["balance"] + saldo
        por_tramo[tramo] = por_tramo[tramo] + saldo
        total = total + saldo

    lista = sorted(proveedores.values(), key=lambda p: p["balance"].amount, reverse=True)
    for proveedor in lista:
        proveedor["balance"] = proveedor["balance"].as_float()

    return {
        "as_of": hoy.isoformat(),
        "total": total.as_float(),
        "by_bucket": [
            {"bucket": tramo, "balance": por_tramo[tramo].as_float()} for tramo in BUCKETS
        ],
        "suppliers": lista,
    }


def _atraso(due_date: date | None, hoy: date) -> int | None:
    """Días de atraso. `None` si no vence —una compra de contado sin pagar—."""
    return (hoy - due_date).days if due_date else None
