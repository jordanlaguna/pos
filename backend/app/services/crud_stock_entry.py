"""Entradas de mercadería — adaptador.

Las reglas están en `app/domain/stock_entry.py` y el paso a paso en
`app/application/use_cases/stock_entry.py`. Acá queda la traducción a HTTP, en
código y datos, nunca en frases (RN-30).
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.stock_entry import (
    CancelStockEntry,
    EmptyEntry,
    EntryNotFound,
    EntryRequest,
    MissingBarcode,
    NewProduct,
    ProductNotFoundInEntry,
    RegisterStockEntry,
    RequestedEntryLine,
    SupplierInactive,
    SupplierNotFound,
)
from app.domain.errors import (
    AlreadyCancelled,
    BarcodeTaken,
    CannotCancel,
    DuplicateDocument,
    InvalidQuantity,
    InvalidSource,
    LineWithoutProduct,
)
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyProductRepository,
    SqlAlchemyStockEntryRepository,
    SqlAlchemySupplierRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_stock_entry import StockEntry, StockEntryDetail
from app.models.model_user import User
from app.services import crud_categories
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
    productos = SqlAlchemyProductRepository(db)
    entradas = SqlAlchemyStockEntryRepository(db)
    caso = RegisterStockEntry(
        products=productos,
        entries=entradas,
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        suppliers=SqlAlchemySupplierRepository(db),
    )

    # RN-6, también acá: la entrada de mercadería crea productos, así que sin
    # esto el archivo del proveedor sería la puerta por la que entran productos
    # colgados de una raíz que ya solo muestra fichas. Se comprueba una vez por
    # categoría distinta y no una por línea: una factura de cien renglones suele
    # traer dos o tres.
    for categoria in {
        l.new_product.category_id for l in (payload.lines or []) if l.new_product
    }:
        crud_categories.check_category_for_product(db, categoria)

    peticion = EntryRequest(
        document_number=payload.document_number,
        supplier=payload.supplier,
        source=payload.source,
        user_id=payload.user_id,
        notes=payload.notes,
        supplier_id=payload.supplier_id,
        document_key=payload.document_key,
        document_date=payload.document_date,
        payment_terms=payload.payment_terms,
        payment_terms_days=payload.payment_terms_days,
        lines=[
            RequestedEntryLine(
                quantity=l.quantity,
                unit_cost=Money(l.unit_cost),
                product_id=l.id_product,
                # La factura la dice en porcentaje y el dominio la guarda entre
                # 0 y 1. La conversión va acá, en el borde, que es donde viven
                # las unidades de quien nos habla.
                tax_rate=TaxRate.percent(l.tax_rate),
                tax_amount=Money(l.tax_amount),
                new_product=(
                    NewProduct(
                        name=l.new_product.name,
                        description=l.new_product.description,
                        price=Money(l.new_product.price),
                        barcode=l.new_product.barcode or "",
                        category_id=l.new_product.category_id,
                    )
                    if l.new_product
                    else None
                ),
            )
            for l in (payload.lines or [])
        ],
    )

    try:
        resultado = caso(peticion)

    except EmptyEntry:
        raise api_error(400, "empty_entry") from None
    except InvalidSource:
        raise api_error(400, "invalid_entry_source") from None
    except DuplicateDocument as e:
        # La fecha de la que ya estaba: es lo que deja repetir la carga a
        # sabiendas, anulando primero la anterior. Va en ISO y sin formato: el
        # día y el mes no van en el mismo orden en todos los idiomas.
        previa = entradas.applied_with_document(e.document_number, payload.supplier_id)
        raise api_error(
            400,
            "duplicate_document",
            document_number=e.document_number,
            loaded_at=previa.created_at.isoformat(),
        ) from None
    except SupplierNotFound as e:
        raise api_error(404, "supplier_not_found", supplier_id=e.supplier_id) from None
    except SupplierInactive as e:
        raise api_error(400, "supplier_inactive", name=e.name) from None
    except InvalidQuantity:
        raise api_error(400, "invalid_entry_line", line=_linea_mala(payload)) from None
    except ProductNotFoundInEntry as e:
        raise api_error(404, "entry_product_not_found", product_id=e.product_id) from None
    except MissingBarcode as e:
        raise api_error(400, "entry_missing_barcode", line=e.index) from None
    except BarcodeTaken as e:
        raise api_error(400, "barcode_taken", barcode=e.barcode) from None
    except LineWithoutProduct as e:
        raise api_error(400, "entry_line_without_product", line=e.index) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise api_error(500, "entry_failed", cause=str(exc))

    return {
        "message": "entry_registered",
        "id_entry": resultado.id_entry,
        "products_created": resultado.products_created,
        "units_added": resultado.units_added,
    }


def _linea_mala(payload) -> int:
    """Número de la primera línea con cantidad o costo inválidos.

    El dominio rechaza el valor pero no sabe en qué posición venía: el número de
    línea es cosa de la interfaz, que es la que conoce el orden en que llegaron.
    """
    for indice, linea in enumerate(payload.lines or [], start=1):
        if linea.quantity <= 0 or linea.unit_cost < 0:
            return indice
    return 1


def cancel_entry(db: Session, entry_id: int) -> dict:
    productos = SqlAlchemyProductRepository(db)
    caso = CancelStockEntry(
        products=productos,
        entries=SqlAlchemyStockEntryRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
    )

    try:
        caso(entry_id)
    except EntryNotFound:
        raise api_error(404, "entry_not_found") from None
    except AlreadyCancelled:
        raise api_error(400, "entry_already_cancelled") from None
    except CannotCancel as e:
        producto = productos.get(e.product_id)
        raise api_error(
            400,
            "entry_cannot_cancel",
            product_id=e.product_id,
            product=producto.name if producto else None,
            available=e.available,
            added=e.added,
        ) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise api_error(500, "entry_cancel_failed", cause=str(exc))

    return {"message": "entry_cancelled", "id_entry": entry_id}
