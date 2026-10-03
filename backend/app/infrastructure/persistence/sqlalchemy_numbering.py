"""
Los adaptadores de la numeración (T-704, T-705): el emisor, el contador y el
registro del comprobante numerado.

**El bloqueo es de la fila de la serie.** `last_sequence` la crea si no existe
y la deja bloqueada hasta que confirme la transacción de quien llama —la de la
venta—. Dos cajas de la misma serie se esperan una a la otra; dos series
distintas no se estorban, porque cada una es su fila.

La fila se crea con `INSERT … ON DUPLICATE KEY UPDATE` y no con `INSERT IGNORE`:
el `IGNORE` convierte en advertencia **cualquier** error, también una foránea
rota, y la serie quedaría sin crearse sin que nadie se entere.
"""

from __future__ import annotations

import secrets

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.application.ports.numbering import Issuer, NumberedDocument, Office
from app.domain.fe_key import SECURITY_CODE_DIGITS
from app.models.model_company import Branch, Company, Terminal
from app.domain.fe_transmission import NUMBERED
from app.models.model_fe import FeDocument, FeSequence
from app.utils import clock
from app.utils.tenancy import compania_actual, sucursal_actual, terminal_actual


class SqlAlchemyIssuerRepository:
    """La cédula de `companies` (RN-45) y el ambiente y la actividad de la
    configuración. Cumple `IssuerRepository`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def issuer(self) -> Issuer:
        from app.services.crud_settings import get_economic_activity, get_einvoicing_environment

        # `companies` no lleva el filtro por compañía —es la raíz—, así que se
        # pide por la llave de la sesión y no hay forma de leer la de otra.
        company = self._db.get(Company, compania_actual())
        return Issuer(
            identification=company.identificacion if company else None,
            environment=get_einvoicing_environment(self._db),
            economic_activity=get_economic_activity(self._db),
        )


class SqlAlchemyDocumentNumbering:
    """El contador en `fe_sequences` y los comprobantes en `fe_documents`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def office(self) -> Office:
        sucursal = self._db.query(Branch).filter(Branch.id == sucursal_actual()).first()
        terminal = self._db.query(Terminal).filter(Terminal.id == terminal_actual()).first()
        # Vacíos y no una excepción propia: `BranchCode("")` ya rechaza con su
        # motivo. Una sesión sin oficina no llega a vender —la venta también
        # guarda las dos—, así que esto es un estado roto y no un caso de uso.
        return Office(
            branch_code=sucursal.codigo if sucursal else "",
            terminal_code=terminal.codigo if terminal else "",
        )

    def _serie(self, document_type: str, environment: str):
        return self._db.query(FeSequence).filter(
            FeSequence.branch_id == sucursal_actual(),
            FeSequence.terminal_id == terminal_actual(),
            FeSequence.document_type == document_type,
            FeSequence.environment == environment,
        )

    def last_sequence(self, *, document_type: str, environment: str) -> int:
        tabla = FeSequence.__table__
        alta = (
            mysql_insert(tabla)
            .values(
                company_id=compania_actual(),
                branch_id=sucursal_actual(),
                terminal_id=terminal_actual(),
                document_type=document_type,
                environment=environment,
                last_number=0,
            )
            # Si ya existe, no cambia nada, pero deja la fila bloqueada igual.
            .on_duplicate_key_update(last_number=tabla.c.last_number)
        )
        self._db.execute(alta)
        fila = self._serie(document_type, environment).with_for_update().one()
        return int(fila.last_number)

    def save_sequence(self, *, document_type: str, environment: str, value: int) -> None:
        fila = self._serie(document_type, environment).with_for_update().one()
        fila.last_number = value
        fila.updated_at = clock.now()

    def record(self, document: NumberedDocument) -> None:
        self._db.add(
            FeDocument(
                company_id=compania_actual(),
                source_type=document.source_type,
                source_id=document.source_id,
                document_type=document.document_type,
                environment=document.environment,
                branch_id=sucursal_actual(),
                terminal_id=terminal_actual(),
                sequence_number=document.sequence,
                consecutive=document.consecutive,
                clave=document.clave,
                situation=document.situation,
                economic_activity=document.economic_activity,
                issued_at=document.issued_at,
                # Nace en la cola (F7): numerado y con el primer paso ya debido,
                # para que el trabajador lo firme y lo envíe en su próximo turno.
                status=NUMBERED,
                next_attempt_at=document.issued_at,
            )
        )
        # `flush` para que un consecutivo o una clave repetidos salten acá, con
        # la transacción todavía abierta, y no en el `commit`.
        self._db.flush()


class RandomSecurityCodes:
    """Ocho dígitos de `secrets`, no de `random`: el código de seguridad es lo
    que impide adivinar la clave de un comprobante ajeno a partir de la propia."""

    def new(self) -> str:
        return f"{secrets.randbelow(10**SECURITY_CODE_DIGITS):0{SECURITY_CODE_DIGITS}d}"
