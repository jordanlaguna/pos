"""Entradas de mercadería al inventario."""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_stock_entry import StockEntry, StockEntryDetail
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


def serialize(db: Session, entry: StockEntry) -> dict:
    details = db.query(StockEntryDetail).filter(StockEntryDetail.entry_id == entry.id).all()

    lines = []
    for detail in details:
        product = db.query(Product).filter(Product.id_product == detail.product_id).first()
        lines.append(
            {
                "id_product": detail.product_id,
                "name": product.name if product else f"Producto #{detail.product_id}",
                "quantity": detail.quantity,
                "unit_cost": _money(detail.unit_cost),
                "subtotal": _money(detail.subtotal),
            }
        )

    return {
        "id": entry.id,
        "document_number": entry.document_number,
        "supplier": entry.supplier,
        "source": entry.source,
        "user_id": entry.user_id,
        "user_name": _user_name(db, entry.user_id),
        "created_at": entry.created_at,
        "notes": entry.notes,
        "status": entry.status,
        "total_cost": _money(entry.total_cost),
        "items_count": sum(d.quantity for d in details),
        "lines": lines,
    }


def create_entry(db: Session, payload) -> dict:
    if not payload.lines:
        raise HTTPException(status_code=400, detail="La entrada debe tener al menos una línea.")
    if payload.source not in ("manual", "excel", "xml"):
        raise HTTPException(status_code=400, detail="Origen de la entrada no válido.")

    # Una misma factura cargada dos veces duplica el inventario en silencio, que
    # es justo el error que este módulo tiene que hacer imposible.
    if payload.document_number:
        duplicate = (
            db.query(StockEntry)
            .filter(
                StockEntry.document_number == payload.document_number,
                StockEntry.status == "aplicada",
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"El documento {payload.document_number} ya se cargó "
                    f"el {duplicate.created_at:%d/%m/%Y}. Anulá esa entrada si querés repetirla."
                ),
            )

    # ------------------------------------------------------------- validar
    # Nada se escribe hasta que toda la entrada esté verificada.
    resolved = []
    created_products = 0

    for index, line in enumerate(payload.lines, start=1):
        if line.quantity <= 0:
            raise HTTPException(
                status_code=400, detail=f"La línea {index} tiene una cantidad inválida."
            )
        if line.unit_cost < 0:
            raise HTTPException(
                status_code=400, detail=f"La línea {index} tiene un costo negativo."
            )

        if line.id_product:
            product = db.query(Product).filter(Product.id_product == line.id_product).first()
            if not product:
                raise HTTPException(
                    status_code=404, detail=f"El producto ID {line.id_product} no existe."
                )
            resolved.append({"product": product, "line": line, "created": False})

        elif line.new_product:
            data = line.new_product
            barcode = (data.barcode or "").strip()
            if not barcode:
                raise HTTPException(
                    status_code=400,
                    detail=f"La línea {index} crea un producto sin código de barras.",
                )
            if db.query(Product).filter(Product.barcode == barcode).first():
                raise HTTPException(
                    status_code=400,
                    detail=f"Ya existe un producto con el código de barras {barcode}.",
                )

            product = Product(
                name=data.name,
                description=data.description or data.name,
                price=data.price,
                stock=0,
                barcode=barcode,
                created_at=datetime.now(),
                category_id=data.category_id,
            )
            db.add(product)
            # flush para tener el id sin cerrar la transacción: si algo falla más
            # adelante, el producto tampoco queda creado.
            db.flush()
            created_products += 1
            resolved.append({"product": product, "line": line, "created": True})

        else:
            raise HTTPException(
                status_code=400,
                detail=f"La línea {index} no indica producto existente ni producto a crear.",
            )

    # ------------------------------------------------------------ escribir
    try:
        total = Decimal(0)
        entry = StockEntry(
            document_number=payload.document_number,
            supplier=payload.supplier,
            source=payload.source,
            user_id=payload.user_id,
            created_at=datetime.now(),
            notes=payload.notes,
            status="aplicada",
            total_cost=0,
        )
        db.add(entry)
        db.flush()

        units = 0
        for item in resolved:
            product, line = item["product"], item["line"]
            unit_cost = Decimal(str(line.unit_cost))
            subtotal = (unit_cost * line.quantity).quantize(Decimal("0.01"))
            total += subtotal
            units += line.quantity

            db.add(
                StockEntryDetail(
                    entry_id=entry.id,
                    product_id=product.id_product,
                    quantity=line.quantity,
                    unit_cost=unit_cost,
                    subtotal=subtotal,
                )
            )
            product.stock += line.quantity

        entry.total_cost = total
        db.commit()
        db.refresh(entry)

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar la entrada: {exc}")

    return {
        "message": "Entrada registrada exitosamente",
        "id_entry": entry.id,
        "products_created": created_products,
        "units_added": units,
    }


def cancel_entry(db: Session, entry_id: int) -> dict:
    entry = db.query(StockEntry).filter(StockEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    if entry.status == "anulada":
        raise HTTPException(status_code=400, detail="La entrada ya está anulada.")

    details = db.query(StockEntryDetail).filter(StockEntryDetail.entry_id == entry.id).all()

    # Si parte de esa mercadería ya se vendió, revertir dejaría el stock en
    # negativo. Se avisa con el producto concreto en vez de romper el inventario.
    for detail in details:
        product = db.query(Product).filter(Product.id_product == detail.product_id).first()
        if not product:
            continue
        if product.stock < detail.quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No se puede anular: de {product.name} quedan {product.stock} unidades "
                    f"y la entrada agregó {detail.quantity}. Ajustá el stock a mano."
                ),
            )

    try:
        for detail in details:
            product = db.query(Product).filter(Product.id_product == detail.product_id).first()
            if product:
                product.stock -= detail.quantity
        entry.status = "anulada"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al anular la entrada: {exc}")

    return {"message": "Entrada anulada; el stock volvió atrás", "id_entry": entry.id}
