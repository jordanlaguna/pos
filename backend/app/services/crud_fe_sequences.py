"""El arranque de las series de quien viene de otro sistema (T-616, RF-32, RN-36 a RN-38).

Casi ningún negocio llega en cero: viene de otro sistema y su numeración tiene
que seguir, porque un consecutivo repetido lo rechaza Hacienda. Acá se dice el
**último consecutivo emitido** de cada serie —una por caja y por tipo de
comprobante, en el ambiente en uso— y la siguiente sale con uno más.

La regla vive en el dominio (`fe_key.check_sequence_start`): solo sube, y una
serie con la que el sistema ya emitió es suya y no se mueve a mano. Lo que hace
este archivo es leer y escribir la fila, y dejar el cambio en bitácora (RN-38).
"""

from __future__ import annotations

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.domain.errors import InvalidSequenceStart, SequenceCannotGoDown, SequenceInUse
from app.domain.fe_key import check_sequence_start
from app.models.model_company import Branch, Terminal
from app.models.model_fe import FeDocument, FeSequence
from app.services import crud_membership
from app.services.crud_settings import get_document_types, get_einvoicing_environment
from app.utils import clock
from app.utils.api_errors import api_error
from app.utils.tenancy import compania_actual


def _ultimo(db: Session, terminal: Terminal, document_type: str, environment: str) -> int:
    fila = (
        db.query(FeSequence)
        .filter(
            FeSequence.branch_id == terminal.branch_id,
            FeSequence.terminal_id == terminal.id,
            FeSequence.document_type == document_type,
            FeSequence.environment == environment,
        )
        .first()
    )
    return int(fila.last_number) if fila else 0


def _emitio(db: Session, terminal: Terminal, document_type: str, environment: str) -> bool:
    """¿Ya numeró este sistema algún comprobante con esta serie?"""
    return (
        db.query(FeDocument.id)
        .filter(
            FeDocument.branch_id == terminal.branch_id,
            FeDocument.terminal_id == terminal.id,
            FeDocument.document_type == document_type,
            FeDocument.environment == environment,
        )
        .first()
        is not None
    )


def series(db: Session) -> dict:
    """Las series de la compañía: cada caja activa por cada tipo encendido."""
    ambiente = get_einvoicing_environment(db)
    tipos = sorted(get_document_types(db))
    cajas = (
        db.query(Terminal, Branch)
        .join(Branch, Branch.id == Terminal.branch_id)
        .filter(Terminal.activa.is_(True), Branch.activa.is_(True))
        .order_by(Branch.codigo, Terminal.codigo)
        .all()
    )
    return {
        "environment": ambiente,
        "items": [
            {
                "terminal_id": caja.id,
                "branch_code": sucursal.codigo,
                "branch_name": sucursal.nombre,
                "terminal_code": caja.codigo,
                "terminal_name": caja.nombre,
                "document_type": tipo,
                "last_number": _ultimo(db, caja, tipo, ambiente),
                "in_use": _emitio(db, caja, tipo, ambiente),
            }
            for caja, sucursal in cajas
            for tipo in tipos
        ],
    }


def arrancar(db: Session, datos, *, user_id: int, ip: str | None) -> dict:
    """`PUT /fe/sequences`: el último consecutivo de una serie (RN-36 a RN-38)."""
    ambiente = get_einvoicing_environment(db)
    if datos.document_type not in get_document_types(db):
        raise api_error(400, "invalid_sale_document_type", document_type=datos.document_type)
    fila = (
        db.query(Terminal, Branch)
        .join(Branch, Branch.id == Terminal.branch_id)
        .filter(Terminal.id == datos.terminal_id)
        .first()
    )
    if fila is None:
        raise api_error(404, "terminal_not_found", terminal_id=datos.terminal_id)
    caja, sucursal = fila

    antes = _ultimo(db, caja, datos.document_type, ambiente)
    try:
        nuevo = check_sequence_start(
            document_type=datos.document_type,
            current=antes,
            requested=datos.last_number,
            emitted=_emitio(db, caja, datos.document_type, ambiente),
        )
    except InvalidSequenceStart as e:
        raise api_error(400, "invalid_sequence_start", value=str(e.value)) from None
    except SequenceInUse as e:
        raise api_error(409, "sequence_in_use", document_type=e.document_type) from None
    except SequenceCannotGoDown as e:
        raise api_error(
            409, "sequence_cannot_go_down", current=e.current, requested=e.requested
        ) from None

    ahora = clock.now()
    db.execute(
        mysql_insert(FeSequence.__table__)
        .values(
            company_id=compania_actual(),
            branch_id=caja.branch_id,
            terminal_id=caja.id,
            document_type=datos.document_type,
            environment=ambiente,
            last_number=nuevo,
            updated_at=ahora,
            updated_by=user_id,
        )
        .on_duplicate_key_update(last_number=nuevo, updated_at=ahora, updated_by=user_id)
    )
    crud_membership.registrar(
        db,
        user_id=user_id,
        company_id=compania_actual(),
        accion="serie_arranque",
        detalle=(
            f"{datos.document_type} {sucursal.codigo}-{caja.codigo} ({ambiente}): {antes} → {nuevo}"
        ),
        ip=ip,
    )
    db.commit()
    return {
        "terminal_id": caja.id,
        "document_type": datos.document_type,
        "environment": ambiente,
        "last_number": nuevo,
    }
