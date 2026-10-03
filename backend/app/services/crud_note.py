"""Notas por monto — adaptador (RF-77, T-726).

La ND y la NC que no mueven mercadería. Las reglas están en
`app/domain/fe_notes.py` y el paso a paso en
`app/application/use_cases/register_note.py`; acá queda la traducción a HTTP, en
código y datos, nunca en frases (RN-30).
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.register_note import (
    EmptyNote,
    NoteLineNotInSale,
    NoteRequest,
    NoteWithoutReason,
    RegisterAmountNote,
    RequestedNoteLine,
)
from app.application.use_cases.register_return import SaleNotFound
from app.domain.errors import (
    CreditExceedsLine,
    DocumentTypeNotEnabled,
    InvalidAmount,
    InvalidNoteAmount,
    InvalidNoteReason,
    InvalidNoteType,
    InvalidSalePaymentMethod,
    IssuerIdentificationRequired,
    NoteNeedsDocument,
)
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyNoteRepository,
    SqlAlchemyReturnRepository,
    SqlAlchemySaleRepository,
    SqlAlchemySettingsRepository,
    SqlAlchemyUnitOfWork,
)
from app.models.model_note import SaleNote, SaleNoteLine
from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_sales import Sale
from app.models.model_user import User
from app.schemas.schemas_note import NoteCreate
from app.services import crud_accounting, crud_numbering
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


def serialize(db: Session, nota: SaleNote) -> dict:
    venta = db.query(Sale).filter(Sale.id == nota.sale_id).first()
    lineas = db.query(SaleNoteLine).filter(SaleNoteLine.note_id == nota.id).all()
    items = []
    for linea in lineas:
        producto = db.query(Product).filter(Product.id_product == linea.product_id).first()
        items.append(
            {
                "id_product": linea.product_id,
                "name": producto.name if producto else f"Producto #{linea.product_id}",
                "subtotal": _money(linea.subtotal),
                "tax_rate": float(linea.tax_rate),
                "tax_amount": _money(linea.tax_amount),
                "tax_code": linea.tax_code,
                "cabys_code": linea.cabys_code,
                "unit_of_measure": linea.unit_of_measure,
            }
        )
    return {
        "id": nota.id,
        "sale_id": nota.sale_id,
        "sale_number": venta.sale_number if venta else "",
        "user_id": nota.user_id,
        "user_name": _user_name(db, nota.user_id),
        "created_at": nota.created_at,
        "document_type": nota.document_type,
        "reference_code": nota.reference_code,
        "reason": nota.reason,
        "payment_method": nota.payment_method,
        "subtotal": _money(nota.subtotal),
        "tax": _money(nota.tax),
        "total": _money(nota.total),
        "items": items,
        # Lo que la nota impresa dice del original (RN-89).
        "sale_document_type": venta.document_type if venta else None,
        "sale_created_at": venta.created_at if venta else None,
        "sale_client_id": venta.client_id if venta else None,
        # La nota numerada, y la clave del original (T-705).
        "einvoice": crud_numbering.comprobante_de(db, "note", nota.id),
        "sale_clave": crud_numbering.clave_de(db, "sale", nota.sale_id),
    }


def create_note(db: Session, payload: NoteCreate, *, user_id: int) -> dict:
    caso = RegisterAmountNote(
        sales=SqlAlchemySaleRepository(db),
        returns=SqlAlchemyReturnRepository(db),
        notes=SqlAlchemyNoteRepository(db),
        settings=SqlAlchemySettingsRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        ledger=crud_accounting.libro(db, user_id=user_id),
        numbering=crud_numbering.numerador(db),
    )

    try:
        peticion = NoteRequest(
            sale_id=payload.sale_id,
            user_id=user_id,
            document_type=payload.document_type,
            reference_code=payload.reference_code,
            reason=payload.reason,
            lines=[RequestedNoteLine(i.id_product, Money(i.amount)) for i in payload.items],
            payment_method=payload.payment_method,
        )
        resultado = caso(peticion)

    except SaleNotFound:
        raise api_error(404, "sale_not_found") from None
    except NoteNeedsDocument:
        raise api_error(400, "note_needs_document", sale_id=payload.sale_id) from None
    except InvalidNoteType as e:
        raise api_error(400, "invalid_note_type", document_type=str(e.document_type)) from None
    except InvalidNoteReason as e:
        raise api_error(
            400,
            "invalid_note_reason",
            document_type=str(e.document_type),
            reference_code=str(e.reference_code),
        ) from None
    except DocumentTypeNotEnabled as e:
        raise api_error(400, "document_type_not_enabled", document_type=e.document_type) from None
    except NoteWithoutReason:
        raise api_error(400, "note_reason_required") from None
    except IssuerIdentificationRequired as e:
        # La compañía emite y no tiene cédula de emisor, o la que tiene no cabe
        # en la clave (RN-45). Lo arregla soporte, no quien cobra.
        raise api_error(409, "issuer_identification_required", reason=e.reason) from None
    except InvalidSalePaymentMethod as e:
        raise api_error(400, "invalid_sale_payment_method", method=str(e.method)) from None
    except EmptyNote:
        raise api_error(400, "empty_note") from None
    except NoteLineNotInSale as e:
        raise api_error(400, "note_line_not_in_sale", product_id=e.product_id) from None
    except (InvalidNoteAmount, InvalidAmount) as e:
        raise api_error(
            400, "invalid_note_amount", product_id=getattr(e, "product_id", None)
        ) from None
    except CreditExceedsLine as e:
        raise api_error(
            400,
            "credit_exceeds_line",
            product_id=e.product_id,
            available=Money(e.available).as_float(),
            requested=Money(e.requested).as_float(),
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise api_error(500, "note_failed", cause=str(exc))

    return {
        "message": "note_registered",
        "id_note": resultado.id_note,
        "document_type": resultado.document_type,
        "total": resultado.total.as_float(),
    }
