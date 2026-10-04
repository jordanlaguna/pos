"""
Los comprobantes numerados vistos desde el recorrido (T-707 a T-713).

`fe_documents` nació en T-705 con la clave y el consecutivo; el recorrido le
cuelga el estado, las huellas de cada paso y las referencias a lo archivado.
Este puerto es lo que la cola y la pantalla necesitan de esa tabla, y nada de
cómo está guardada.

**Compañía implícita.** Como el resto de los repositorios, cada instancia habla
de la compañía del contexto (`tenancy.py`). El trabajador, que corre fuera de
una petición, abre un contexto por compañía antes de pedir nada: sin eso la
primera lectura lanza `SinCompania` (T-708).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.fe_xml import Comprobante


@dataclass(frozen=True)
class DocumentSnapshot:
    """Un comprobante con su recorrido, tal como está ahora."""

    id: int
    company_id: int
    source_type: str
    source_id: int
    document_type: str
    environment: str
    clave: str
    consecutive: str
    situation: str
    issued_at: datetime
    status: str
    #: La actividad con que se declaró; el XML la lleva.
    economic_activity: str | None = None
    #: Fallas transitorias seguidas desde el último éxito; vuelve a cero al
    #: avanzar un paso.
    failures: int = 0
    #: Consultas del veredicto hechas desde el envío.
    polls: int = 0
    first_failure_at: datetime | None = None
    last_attempt_at: datetime | None = None
    #: La última vez que Hacienda o su IdP no contestaron por este documento.
    #: Solo eso cuenta para la situación «sin internet» (RN-43): Vault sellado o
    #: el almacén caído son fallas nuestras y no cambian la clave.
    unreachable_at: datetime | None = None
    next_attempt_at: datetime | None = None
    signed_at: datetime | None = None
    sent_at: datetime | None = None
    resolved_at: datetime | None = None
    stop_reason: str | None = None
    stop_detail: str | None = None
    hacienda_status: str | None = None
    #: Dónde quedó el XML firmado y la respuesta, en el almacén (plan §7.3).
    xml_key: str | None = None
    response_key: str | None = None

    @property
    def signed(self) -> bool:
        return self.xml_key is not None

    @property
    def sent(self) -> bool:
        return self.sent_at is not None


@dataclass(frozen=True)
class DocumentEvent:
    """Un paso del recorrido, con su hora. Es lo que la pantalla enseña."""

    at: datetime
    event: str
    detail: str = ""


class Unset:
    """El valor que significa «este campo no se toca» en `DocumentUpdate`."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET = Unset()


@dataclass(frozen=True)
class DocumentUpdate:
    """Lo que un paso quiere escribir. Lo que no se nombra no se toca.

    `UNSET` distingue «dejalo como está» de «ponelo en nulo»: un paso que
    avanza borra el motivo de detención (`stop_reason=None`), y uno que solo
    falla no toca el `signed_at`.
    """

    status: object = UNSET
    failures: object = UNSET
    polls: object = UNSET
    first_failure_at: object = UNSET
    last_attempt_at: object = UNSET
    unreachable_at: object = UNSET
    next_attempt_at: object = UNSET
    signed_at: object = UNSET
    sent_at: object = UNSET
    resolved_at: object = UNSET
    stop_reason: object = UNSET
    stop_detail: object = UNSET
    hacienda_status: object = UNSET
    xml_key: object = UNSET
    response_key: object = UNSET

    def fields(self) -> dict[str, object]:
        """Solo lo que se nombró."""
        return {
            campo: valor
            for campo, valor in self.__dict__.items()
            if not isinstance(valor, Unset)
        }


@dataclass(frozen=True)
class TransmissionHealth:
    """Lo observado de las transmisiones recientes, para RN-43."""

    last_transient_failure_at: datetime | None
    last_success_at: datetime | None


@dataclass(frozen=True)
class QueueCounts:
    by_status: dict[str, int]
    oldest_pending_at: datetime | None


class TransmissionRepository(Protocol):
    """`fe_documents` y `fe_document_events`, para la cola y la pantalla."""

    def get(self, document_id: int) -> DocumentSnapshot | None: ...

    def latest_for(self, source_type: str, source_id: int) -> DocumentSnapshot | None:
        """El comprobante vigente de un origen: el último."""
        ...

    def due(self, now: datetime, *, limit: int) -> list[DocumentSnapshot]:
        """Lo pendiente cuyo próximo intento ya llegó, lo más viejo primero."""
        ...

    def update(self, document_id: int, change: DocumentUpdate) -> DocumentSnapshot:
        """Escribe los campos nombrados y devuelve el documento como quedó."""
        ...

    def add_event(self, document_id: int, event: DocumentEvent) -> None: ...

    def events(self, document_id: int) -> list[DocumentEvent]:
        """En orden, del primero al último."""
        ...

    def health(self) -> TransmissionHealth: ...

    def stopped(self) -> list[DocumentSnapshot]:
        """Lo detenido, lo más viejo primero (RF-35)."""
        ...

    def counts(self) -> QueueCounts: ...

    def accepted_by_type(self, environment: str) -> dict[str, int]:
        """Cuántos aceptados hay de cada tipo en ese ambiente (T-713)."""
        ...


class ComprobanteSource(Protocol):
    """Arma el comprobante de dominio desde su origen: la venta, la devolución
    o la nota, con el emisor y el receptor como están guardados."""

    def comprobante(self, document: DocumentSnapshot) -> Comprobante:
        """El `Comprobante` listo para `fe_xml.construir`, o `ComprobanteInvalido`
        si a los datos les falta algo que el XML exige."""
        ...


class ContingencyMode(Protocol):
    """Si el negocio está hoy en contingencia (RN-43)."""

    def active(self) -> bool: ...
