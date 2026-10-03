"""La numeración armada con sus adaptadores, y cómo se lee un comprobante numerado.

Las dos mitades en un solo sitio para que la venta, la devolución y la nota no
repitan cómo se conecta ni cómo se publica: el contrato de `einvoice` es el
mismo en los tres detalles, y es el que imprime `FiscalBlock.svelte`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.use_cases.number_document import NumberDocument
from app.infrastructure.persistence.sqlalchemy_numbering import (
    RandomSecurityCodes,
    SqlAlchemyDocumentNumbering,
    SqlAlchemyIssuerRepository,
)
from app.models.model_fe import FeDocument
from app.services import crud_fe_documents


def numerador(db: Session) -> NumberDocument:
    return NumberDocument(
        issuer=SqlAlchemyIssuerRepository(db),
        numbering=SqlAlchemyDocumentNumbering(db),
        security_codes=RandomSecurityCodes(),
        # El dígito de situación sale de lo que la cola observó (RN-43).
        contingency=crud_fe_documents.contingencia(db),
    )


def comprobante_de(db: Session, source_type: str, source_id: int) -> dict | None:
    """El comprobante vigente de un origen, con la forma de `EmittedDocument`.

    El vigente es el último: si uno se rechaza, el que lo reemplaza es otro con
    clave nueva (plan §7.2). Nulo si el origen nunca se numeró —una venta sin
    facturación electrónica, o una de antes de T-705—.
    """
    fila = (
        db.query(FeDocument)
        .filter(FeDocument.source_type == source_type, FeDocument.source_id == source_id)
        .order_by(FeDocument.id.desc())
        .first()
    )
    if fila is None:
        return None
    # La clave y el consecutivo de T-705, y encima el recorrido de T-707: en qué
    # estado está, por qué se detuvo y si ya hay XML y respuesta que bajar.
    return crud_fe_documents.documento_out(crud_fe_documents.repositorio(db).get(fila.id))


def clave_de(db: Session, source_type: str, source_id: int) -> str | None:
    """Solo la clave. Es lo que una nota imprime del comprobante que modifica."""
    comprobante = comprobante_de(db, source_type, source_id)
    return comprobante["clave"] if comprobante else None
