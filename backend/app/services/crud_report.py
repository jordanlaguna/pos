"""Agregaciones para el panel de reportes.

Todo se resuelve con SQL agregado en vez de traer las filas y sumarlas en
Python: con unos meses de operación son decenas de miles de ventas.

**Acá el filtro por compañía va escrito a mano** (T-209). El automático de
`app/utils/tenancy.py` inyecta el criterio en las consultas que *cargan
entidades*; estas no cargan ninguna —piden `COUNT`, `SUM`, `DATE`— y por eso
quedan fuera de su alcance. Es el límite conocido que plan §3.3 anota como
riesgo, y un reporte que se lo saltara sumaría las ventas de todas las
compañías en una cifra que se ve perfectamente normal.

Cada consulta de este módulo lleva su `company_id ==` visible. Si mañana se
agrega otra, tiene que llevarlo también: no hay red debajo.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_stock_entry import StockEntry, StockEntryDetail
from app.utils import clock
from app.utils.tenancy import compania_actual


def _money(value) -> float:
    return float(round(Decimal(str(value or 0)), 2))


def parse_range(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime, str, str]:
    """Convierte `YYYY-MM-DD` en un rango [00:00:00, 23:59:59] inclusive."""
    today = clock.today()
    to_date = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else today
    from_date = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else to_date

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    start = datetime.combine(from_date, datetime.min.time())
    end = datetime.combine(to_date, datetime.max.time())
    return start, end, from_date.isoformat(), to_date.isoformat()


def _sales_totals(db: Session, start: datetime, end: datetime) -> tuple[int, Decimal, Decimal]:
    row = (
        db.query(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), 0),
            func.coalesce(func.sum(Sale.tax), 0),
        )
        .filter(
            Sale.company_id == compania_actual(),
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .one()
    )
    return int(row[0]), Decimal(str(row[1])), Decimal(str(row[2]))


def summary(db: Session, date_from: str | None, date_to: str | None) -> dict:
    start, end, iso_from, iso_to = parse_range(date_from, date_to)

    count, gross, tax = _sales_totals(db, start, end)

    returns_total = Decimal(
        str(
            db.query(func.coalesce(func.sum(Return.total), 0))
            .filter(
                Return.company_id == compania_actual(),
                Return.created_at >= start,
                Return.created_at <= end,
            )
            .scalar()
        )
    )

    items_sold = (
        db.query(func.coalesce(func.sum(SaleDetail.quantity), 0))
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .filter(
            Sale.company_id == compania_actual(),
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .scalar()
    )

    # Periodo anterior de la misma duración, para el porcentaje de variación.
    span = end - start
    previous_start = start - span - timedelta(microseconds=1)
    previous_end = start - timedelta(microseconds=1)
    _, previous_gross, _ = _sales_totals(db, previous_start, previous_end)

    return {
        "range": {"from": iso_from, "to": iso_to},
        "sales_count": count,
        "gross_total": _money(gross),
        "returns_total": _money(returns_total),
        "net_total": _money(gross - returns_total),
        "tax_total": _money(tax),
        "average_ticket": _money(gross / count) if count else 0.0,
        "items_sold": int(items_sold or 0),
        "previous_net_total": _money(previous_gross),
    }


def top_products(db: Session, date_from: str | None, date_to: str | None, limit: int = 8) -> list[dict]:
    start, end, _, _ = parse_range(date_from, date_to)

    rows = (
        db.query(
            SaleDetail.product_id,
            Product.name,
            func.sum(SaleDetail.quantity).label("quantity"),
            func.sum(SaleDetail.subtotal).label("total"),
        )
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .join(Product, Product.id_product == SaleDetail.product_id)
        .filter(
            Sale.company_id == compania_actual(),
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .group_by(SaleDetail.product_id, Product.name)
        .order_by(func.sum(SaleDetail.subtotal).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id_product": row[0],
            "name": row[1],
            "quantity": int(row[2] or 0),
            "total": _money(row[3]),
        }
        for row in rows
    ]


def sales_by_day(db: Session, date_from: str | None, date_to: str | None) -> list[dict]:
    start, end, iso_from, iso_to = parse_range(date_from, date_to)

    rows = (
        db.query(
            func.date(Sale.created_at).label("day"),
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), 0),
        )
        .filter(
            Sale.company_id == compania_actual(),
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .group_by(func.date(Sale.created_at))
        .all()
    )

    found = {str(row[0]): {"sales_count": int(row[1]), "total": _money(row[2])} for row in rows}

    # Se rellenan los días sin ventas: si no, el gráfico dibuja huecos y engaña.
    result = []
    cursor = datetime.strptime(iso_from, "%Y-%m-%d").date()
    last = datetime.strptime(iso_to, "%Y-%m-%d").date()
    while cursor <= last:
        key = cursor.isoformat()
        entry = found.get(key, {"sales_count": 0, "total": 0.0})
        result.append({"day": key, **entry})
        cursor += timedelta(days=1)

    return result


def by_payment_method(db: Session, date_from: str | None, date_to: str | None) -> list[dict]:
    start, end, _, _ = parse_range(date_from, date_to)

    rows = (
        db.query(
            Sale.payment_method,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), 0),
        )
        .filter(
            Sale.company_id == compania_actual(),
            Sale.created_at >= start,
            Sale.created_at <= end,
        )
        .group_by(Sale.payment_method)
        .order_by(func.sum(Sale.total).desc())
        .all()
    )

    return [
        {"payment_method": row[0], "count": int(row[1]), "total": _money(row[2])} for row in rows
    ]


def purchases_by_rate(db: Session, date_from: str | None, date_to: str | None) -> dict:
    """El crédito fiscal del periodo, desglosado por tarifa (RF-45).

    Es la mitad de compras del D-104, y por eso son **tres** los filtros que no
    se pueden mover:

    1. Solo compras: una entrada sin proveedor no tiene documento que respalde
       un crédito fiscal, aunque haya movido inventario (RN-52).
    2. Solo aplicadas: el crédito de una compra anulada no existe.
    3. Por **fecha del documento**, no de carga. Una factura del 28 que se
       digita el 3 es IVA de setiembre, y contarla en octubre desplaza la
       declaración de dos meses a la vez. Para las que no traen fecha —una
       entrada vieja— se usa la de carga, que es lo único que hay.

    El desglose se agrupa por la tarifa **del documento** y no por la del
    producto: es lo que se pagó, que es lo que se acredita (RN-53).
    """
    start, end, desde, hasta = parse_range(date_from, date_to)
    del_documento = func.coalesce(
        StockEntry.document_date, func.date(StockEntry.created_at)
    )

    rows = (
        db.query(
            StockEntryDetail.tax_rate,
            func.coalesce(func.sum(StockEntryDetail.subtotal), 0),
            func.coalesce(func.sum(StockEntryDetail.tax_amount), 0),
        )
        .join(StockEntry, StockEntry.id == StockEntryDetail.entry_id)
        .filter(
            StockEntry.company_id == compania_actual(),
            StockEntry.status == "aplicada",
            StockEntry.supplier_id.isnot(None),
            del_documento >= start.date(),
            del_documento <= end.date(),
        )
        .group_by(StockEntryDetail.tax_rate)
        .order_by(StockEntryDetail.tax_rate)
        .all()
    )

    por_tarifa = [
        {"tax_rate": float(row[0] or 0), "base": _money(row[1]), "tax": _money(row[2])}
        for row in rows
    ]
    base = _money(sum(Decimal(str(r["base"])) for r in por_tarifa))
    impuesto = _money(sum(Decimal(str(r["tax"])) for r in por_tarifa))

    return {
        "date_from": desde,
        "date_to": hasta,
        "subtotal": base,
        "tax": impuesto,
        "total": _money(Decimal(str(base)) + Decimal(str(impuesto))),
        "by_rate": por_tarifa,
    }


def sales_by_rate(db: Session, date_from: str | None, date_to: str | None) -> dict:
    """El débito fiscal del periodo, desglosado por tarifa (RN-65).

    Es la otra mitad del D-104 y el espejo de `purchases_by_rate`. Sale de
    `sale_details`, que guarda la tarifa **congelada** de cada línea (RN-12), y
    no de la configurada hoy: si el dueño cambia el IVA, lo que se declara del
    mes pasado sigue siendo lo que se cobró.

    Las devoluciones van **aparte y no restadas**. Sumadas en silencio, la cifra
    dejaría de coincidir con el desglose de ventas del periodo y nadie sabría por
    qué; separadas, el contador ve las dos y el neto, que es como se llena la
    declaración.

    El `company_id` va escrito a mano en las dos consultas: son agregadas, y el
    filtro automático no entra en una subconsulta de `SUM` (plan §3.3).
    """
    start, end, desde, hasta = parse_range(date_from, date_to)

    def por_tarifa(detalle, cabecera, enlace) -> dict:
        filas = (
            db.query(
                detalle.tax_rate,
                func.coalesce(func.sum(detalle.subtotal), 0),
                func.coalesce(func.sum(detalle.tax_amount), 0),
            )
            .join(cabecera, enlace)
            .filter(
                cabecera.company_id == compania_actual(),
                cabecera.created_at >= start,
                cabecera.created_at <= end,
            )
            .group_by(detalle.tax_rate)
            .all()
        )
        return {
            float(fila[0] or 0): (_money(fila[1]), _money(fila[2])) for fila in filas
        }

    ventas = por_tarifa(SaleDetail, Sale, Sale.id == SaleDetail.sale_id)
    devoluciones = por_tarifa(
        ReturnDetail, Return, Return.id == ReturnDetail.return_id
    )

    lineas = []
    for tarifa in sorted(set(ventas) | set(devoluciones)):
        base, impuesto = ventas.get(tarifa, (0.0, 0.0))
        base_dev, impuesto_dev = devoluciones.get(tarifa, (0.0, 0.0))
        lineas.append(
            {
                "tax_rate": tarifa,
                "base": base,
                "tax": impuesto,
                "returns_base": base_dev,
                "returns_tax": impuesto_dev,
                "net_base": _money(Decimal(str(base)) - Decimal(str(base_dev))),
                "net_tax": _money(Decimal(str(impuesto)) - Decimal(str(impuesto_dev))),
            }
        )

    return {
        "date_from": desde,
        "date_to": hasta,
        "by_rate": lineas,
        "tax": _money(sum(Decimal(str(l["tax"])) for l in lineas)),
        "returns_tax": _money(sum(Decimal(str(l["returns_tax"])) for l in lineas)),
        "net_tax": _money(sum(Decimal(str(l["net_tax"])) for l in lineas)),
    }


def low_stock(db: Session, threshold: int = 10) -> list[Product]:
    return (
        db.query(Product)
        .filter(Product.company_id == compania_actual(), Product.stock <= threshold)
        .order_by(Product.stock.asc())
        .all()
    )
