import datetime

from pydantic import BaseModel


class EInvoiceOut(BaseModel):
    """El comprobante numerado de una venta, una devolución o una nota (T-705),
    y desde F7 su recorrido ante Hacienda (T-707).

    Es el contrato que lee `FiscalBlock.svelte` —`EmittedDocument` en el POS—, y
    es el mismo en los tres detalles. Lo del recorrido es opcional porque el
    bloque fiscal no lo necesita y los guiones viejos no lo mandan.
    """

    #: Los 50 dígitos. Se imprime y se entrega en el mostrador (RN-43).
    clave: str
    #: Los 20: sucursal, caja, tipo y secuencia. Es el número del documento.
    consecutive: str
    #: `sandbox` o `production`. Lo de pruebas no tiene efecto fiscal (RN-17).
    environment: str
    #: La actividad con que se declaró, que puede no ser la configurada hoy.
    economic_activity: str | None = None
    #: 1 normal, 2 contingencia, 3 sin internet.
    situation: str

    # ------------------------------------------------- el recorrido (T-707)
    id: int | None = None
    document_type: str | None = None
    #: De dónde nació: 'sale', 'return' o 'note', y el id de ese origen.
    source_type: str | None = None
    source_id: int | None = None
    #: numbered | signed | sent | accepted | rejected | retrying | stopped
    status: str | None = None
    #: Por qué se detuvo (`fe_transmission.STOP_*`).
    stop_reason: str | None = None
    #: Lo que dijo Hacienda o la falla, crudo. En un rechazo, el motivo.
    stop_detail: str | None = None
    #: El `ind-estado` tal cual lo contestó Hacienda.
    hacienda_status: str | None = None
    failures: int = 0
    polls: int = 0
    issued_at: datetime.datetime | None = None
    signed_at: datetime.datetime | None = None
    sent_at: datetime.datetime | None = None
    resolved_at: datetime.datetime | None = None
    last_attempt_at: datetime.datetime | None = None
    next_attempt_at: datetime.datetime | None = None
    #: Si ya hay XML firmado y respuesta que bajar (RF-34).
    has_xml: bool = False
    has_response: bool = False


class DocumentEventOut(BaseModel):
    """Un paso del recorrido con su hora (T-721)."""

    at: datetime.datetime
    #: signed, sent, polled, accepted, rejected, deferred, stopped, resumed, xml_lost
    event: str
    detail: str | None = None


class DocumentFileOut(BaseModel):
    """El expediente: el comprobante, de dónde nació y su bitácora."""

    document: EInvoiceOut
    source_type: str
    source_id: int
    events: list[DocumentEventOut]


class QueueOut(BaseModel):
    """La cola de la compañía (RF-33, RF-35, T-711)."""

    #: Cuántos hay en cada uno de los siete estados.
    counts: dict[str, int]
    #: Lo que la cola todavía mueve: numerado, firmado, enviado, reintentando.
    pending: int
    #: Lo que necesita a una persona, lo más viejo primero.
    stopped: list[EInvoiceOut]
    oldest_pending_at: datetime.datetime | None = None
    #: ok | warning | danger, por la antigüedad de lo pendiente.
    alarm: str
    #: Si el negocio está emitiendo en contingencia (RN-43).
    contingency: bool


class ProductionGateOut(BaseModel):
    """T-713: si se puede pasar a producción y, si no, qué tipos faltan."""

    ready: bool
    missing: list[str]
