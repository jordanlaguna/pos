"""
El recorrido del comprobante armado con sus adaptadores, y lo que el API publica
de él (F7, T-707 a T-713, T-721).

Acá se conectan los puertos con Vault, MinIO, el IdP y la recepción de
Hacienda, y se traduce lo que el dominio rechaza a códigos del API. Lo usan dos
clientes: el trabajador de la cola (`workers/fe_worker.py`), que corre fuera de
una petición y abre el contexto de cada compañía, y las rutas de `/fe/documents`
y `/fe/queue`, que corren dentro de una.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.application.use_cases.fe_transmission import (
    ObservedContingency,
    PollVerdict,
    ProcessDue,
    ProductionGate,
    QueueReport,
    QueueSummary,
    RetryDocument,
    SignDocument,
    SubmitDocument,
    TransmissionDeps,
)
from app.application.ports.documents import DocumentNotFound, StorageUnavailable
from app.application.ports.fe_documents import DocumentSnapshot
from app.domain import fe_transmission as recorrido
from app.domain.errors import DocumentNotStopped, UnknownDocument
from app.domain.fe_documents import GOV_RESPONSE, SIGNED_PAYLOAD, DocumentRef
from app.infrastructure.clock import SystemClock
from app.infrastructure.crypto.certificate_facts import X509CertificateParser
from app.infrastructure.crypto.fe_crypto import secret_box
from app.infrastructure.crypto.vault_signer import document_signer
from app.infrastructure.external.hacienda_idp import endpoints_for, hacienda_idp
from app.infrastructure.external.hacienda_reception import HaciendaHttpReception
from app.infrastructure.persistence.sqlalchemy_fe import SqlAlchemyFeCredentialsRepository
from app.infrastructure.persistence.sqlalchemy_fe_documents import (
    SqlAlchemyComprobanteSource,
    SqlAlchemyTransmissionRepository,
)
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyUnitOfWork
from app.infrastructure.storage.s3_documents import document_store
from app.services import crud_membership
from app.utils.api_errors import api_error
from app.utils.tenancy import compania_actual

#: La cédula de quien hace el software, para `ProveedorSistemas`. Sin ella va la
#: del propio emisor, que es lo que traen los comprobantes aceptados.
PROVEEDOR_ENV = "FE_PROVEEDOR_SISTEMAS"


def repositorio(db: Session) -> SqlAlchemyTransmissionRepository:
    return SqlAlchemyTransmissionRepository(db)


def contingencia(db: Session) -> ObservedContingency:
    """Lo que la numeración consulta para el dígito de situación (RN-43)."""
    return ObservedContingency(repositorio(db), SystemClock())


def _deps(db: Session) -> TransmissionDeps:
    return TransmissionDeps(
        documents=repositorio(db),
        source=SqlAlchemyComprobanteSource(db, proveedor_sistemas=os.getenv(PROVEEDOR_ENV)),
        credentials=SqlAlchemyFeCredentialsRepository(db),
        certificates=X509CertificateParser(),
        signer=document_signer(),
        store=document_store(),
        idp=hacienda_idp(),
        reception=HaciendaHttpReception(),
        secrets=secret_box(),
        endpoints=endpoints_for,
        clock=SystemClock(),
        uow=SqlAlchemyUnitOfWork(db),
        company_id=compania_actual(),
    )


def procesar_pendientes(db: Session, *, limit: int = 20) -> int:
    """Un turno de la cola para la compañía del contexto. Cuántos atendió."""
    deps = _deps(db)
    cola = ProcessDue(
        deps.documents,
        deps.clock,
        sign=SignDocument(deps),
        submit=SubmitDocument(deps),
        poll=PollVerdict(deps),
    )
    return cola(limit=limit)


# ------------------------------------------------------------------ salidas


def documento_out(doc: DocumentSnapshot) -> dict:
    """La forma de `einvoice` en los detalles y en el expediente (`EInvoiceOut`)."""
    return {
        "id": doc.id,
        "clave": doc.clave,
        "consecutive": doc.consecutive,
        "environment": doc.environment,
        "economic_activity": doc.economic_activity,
        "situation": doc.situation,
        "document_type": doc.document_type,
        "source_type": doc.source_type,
        "source_id": doc.source_id,
        "status": doc.status,
        "stop_reason": doc.stop_reason,
        "stop_detail": doc.stop_detail,
        "hacienda_status": doc.hacienda_status,
        "failures": doc.failures,
        "polls": doc.polls,
        "issued_at": doc.issued_at,
        "signed_at": doc.signed_at,
        "sent_at": doc.sent_at,
        "resolved_at": doc.resolved_at,
        "last_attempt_at": doc.last_attempt_at,
        "next_attempt_at": doc.next_attempt_at,
        "has_xml": doc.xml_key is not None,
        "has_response": doc.response_key is not None,
    }


def _documento(db: Session, document_id: int) -> DocumentSnapshot:
    doc = repositorio(db).get(document_id)
    if doc is None:
        raise api_error(404, "document_not_found", document_id=document_id)
    return doc


def expediente(db: Session, document_id: int) -> dict:
    """El comprobante con su bitácora: por dónde va y a qué hora pasó cada cosa."""
    doc = _documento(db, document_id)
    eventos = repositorio(db).events(document_id)
    return {
        "document": documento_out(doc),
        "source_type": doc.source_type,
        "source_id": doc.source_id,
        "events": [{"at": e.at, "event": e.event, "detail": e.detail or None} for e in eventos],
    }


def _bytes(db: Session, document_id: int, kind: str, llave_de) -> tuple[bytes, str]:
    doc = _documento(db, document_id)
    llave = llave_de(doc)
    if llave is None and kind == SIGNED_PAYLOAD:
        raise api_error(409, "document_not_signed", document_id=document_id, status=doc.status)
    if llave is None:
        raise api_error(409, "document_not_resolved", document_id=document_id, status=doc.status)
    ref = DocumentRef(doc.company_id, doc.environment, kind, doc.clave)
    try:
        contenido = document_store().get(ref)
    except DocumentNotFound:
        raise api_error(404, "document_file_missing", document_id=document_id, kind=kind) from None
    except StorageUnavailable:
        raise api_error(503, "storage_unavailable") from None
    return contenido, doc.clave


def xml_firmado(db: Session, document_id: int) -> tuple[bytes, str]:
    """El XML tal como se envió, byte por byte (RF-34, RN-44)."""
    contenido, clave = _bytes(db, document_id, SIGNED_PAYLOAD, lambda d: d.xml_key)
    return contenido, f"{clave}.xml"


def respuesta_hacienda(db: Session, document_id: int) -> tuple[bytes, str]:
    """El `MensajeHacienda` firmado por Hacienda, tal como llegó."""
    contenido, clave = _bytes(db, document_id, GOV_RESPONSE, lambda d: d.response_key)
    return contenido, f"{clave}-respuesta.xml"


def reintentar(db: Session, document_id: int, *, user_id: int, company_id: int) -> dict:
    """RF-36: vuelve a la cola lo detenido, con bitácora de quién lo pidió."""
    caso = RetryDocument(repositorio(db), SystemClock(), SqlAlchemyUnitOfWork(db))
    try:
        doc = caso(document_id, user_id=user_id)
    except UnknownDocument:
        raise api_error(404, "document_not_found", document_id=document_id) from None
    except DocumentNotStopped as e:
        raise api_error(409, "document_not_stopped", document_id=document_id, status=e.status) from None
    crud_membership.registrar(
        db,
        user_id=user_id,
        company_id=company_id,
        accion="fe_reintento",
        detalle=f"{doc.clave} ← {doc.stop_reason or 'detenido'}",
        ip=None,
    )
    db.commit()
    return expediente(db, document_id)


def _cola_out(informe: QueueReport) -> dict:
    return {
        "counts": {estado: informe.counts.get(estado, 0) for estado in recorrido.STATES},
        "pending": informe.pending,
        "stopped": [documento_out(d) for d in informe.stopped],
        "oldest_pending_at": informe.oldest_pending_at,
        "alarm": informe.alarm,
        "contingency": informe.contingency,
    }


def cola(db: Session) -> dict:
    """RF-33, RF-35, T-711: cuántos hay en cada estado, lo detenido y la alarma."""
    return _cola_out(QueueSummary(repositorio(db), SystemClock())())


def puerta_de_produccion(db: Session) -> dict:
    """T-713, RN-46: qué falta ver aceptado en pruebas para pasar a producción."""
    faltan = ProductionGate(repositorio(db)).missing()
    return {"ready": not faltan, "missing": list(faltan)}
