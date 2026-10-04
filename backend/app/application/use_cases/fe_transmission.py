"""
El recorrido del comprobante hasta Hacienda, paso por paso (T-707 a T-713).

Tres pasos —firmar, enviar, consultar— y lo que los rodea: la cola que los
ejecuta cuando les toca, el reintento a mano de lo detenido, el resumen que ve
la pantalla y la puerta de producción. Las reglas de cuándo y cuánto están en
`domain/fe_transmission.py`; acá se las aplica a los puertos.

**Cada paso es una transacción propia.** El trabajador puede morir entre dos
pasos —se reinició la VM— y lo que quedó escrito tiene que alcanzar para
retomar: por eso el XML firmado se guarda **antes** de marcar el documento como
firmado, y el envío se marca **después** del 202. Si se muere en medio, el paso
se repite y el almacén dice que ya tenía el XML (se escribe una vez, plan §7.3).

**Lo que no se toca.** Un documento firmado no se vuelve a firmar: la firma
cubre unos bytes y el comprobante son esos bytes (RN-44). Si al retomar el XML
ya está en el almacén, se usa ese, aunque el paso de firmar se hubiera cortado
antes de anotarlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.application.ports.clock import Clock
from app.application.ports.documents import (
    DocumentAlreadyStored,
    DocumentNotFound,
    DocumentStore,
    StorageUnavailable,
)
from app.application.ports.fe_credentials import FeCredentialsRepository, FeCredentialsSnapshot
from app.application.ports.fe_documents import (
    ComprobanteSource,
    DocumentEvent,
    DocumentSnapshot,
    DocumentUpdate,
    QueueCounts,
    TransmissionRepository,
)
from app.application.ports.repositories import UnitOfWork
from app.application.ports.secrets import SecretBox
from app.application.ports.signing import (
    CertificateParser,
    DocumentSigner,
    InvalidCertificate,
    SigningKeyMissing,
    SigningUnavailable,
)
from app.application.ports.transmission import (
    CredentialsRejected,
    HaciendaIdp,
    HaciendaReception,
    IdpUnreachable,
    ReceptionForbidden,
    ReceptionRejected,
    ReceptionUnavailable,
    TokenRejected,
    Verdict,
    VerdictNotFound,
)
from app.domain import fe_transmission as recorrido
from app.domain.errors import DocumentNotStopped, DomainError, UnknownDocument
from app.domain.fe_documents import GOV_RESPONSE, SIGNED_PAYLOAD, DocumentRef
from app.domain.fe_signature import InvalidSignatureInput, sign_document
from app.domain.fe_xml import ComprobanteInvalido, construir
from app.domain.hacienda import SANDBOX, HaciendaEndpoints

# Los nombres de los eventos de la bitácora del documento. Son códigos: la
# pantalla pone la frase.
EVENT_SIGNED = "signed"
EVENT_SENT = "sent"
EVENT_POLLED = "polled"
EVENT_ACCEPTED = "accepted"
EVENT_REJECTED = "rejected"
EVENT_DEFERRED = "deferred"
EVENT_STOPPED = "stopped"
EVENT_RESUMED = "resumed"
EVENT_XML_LOST = "xml_lost"
EVENTS = (
    EVENT_SIGNED,
    EVENT_SENT,
    EVENT_POLLED,
    EVENT_ACCEPTED,
    EVENT_REJECTED,
    EVENT_DEFERRED,
    EVENT_STOPPED,
    EVENT_RESUMED,
    EVENT_XML_LOST,
)

#: Cuánto del detalle crudo se conserva. Es para que una persona lo lea, no
#: para archivar la respuesta: esa va entera al almacén.
DETAIL_MAX = 500


@dataclass(frozen=True)
class TransmissionDeps:
    """Todo lo que los pasos necesitan, armado una vez por compañía."""

    documents: TransmissionRepository
    source: ComprobanteSource
    credentials: FeCredentialsRepository
    certificates: CertificateParser
    signer: DocumentSigner
    store: DocumentStore
    idp: HaciendaIdp
    reception: HaciendaReception
    secrets: SecretBox
    endpoints: Callable[[str], HaciendaEndpoints]
    clock: Clock
    uow: UnitOfWork
    company_id: int


def _detalle(valor: object) -> str:
    texto = str(valor or "").strip()
    return texto[:DETAIL_MAX]


class _Paso:
    """Lo común a los tres pasos: escribir el desenlace y su evento."""

    def __init__(self, deps: TransmissionDeps) -> None:
        self._d = deps

    def _escribir(
        self, doc: DocumentSnapshot, cambio: DocumentUpdate, evento: str, detalle: str = ""
    ) -> DocumentSnapshot:
        with self._d.uow:
            actual = self._d.documents.update(doc.id, cambio)
            self._d.documents.add_event(
                doc.id, DocumentEvent(at=self._d.clock.now(), event=evento, detail=detalle)
            )
            self._d.uow.commit()
        return actual

    def _detener(self, doc: DocumentSnapshot, motivo: str, detalle: str = "") -> DocumentSnapshot:
        ahora = self._d.clock.now()
        detalle = _detalle(detalle)
        return self._escribir(
            doc,
            DocumentUpdate(
                status=recorrido.STOPPED,
                stop_reason=motivo,
                stop_detail=detalle or None,
                last_attempt_at=ahora,
                next_attempt_at=None,
            ),
            EVENT_STOPPED,
            motivo if not detalle else f"{motivo}: {detalle}",
        )

    def _diferir(
        self, doc: DocumentSnapshot, detalle: str = "", *, hacienda: bool = False
    ) -> DocumentSnapshot:
        """Una falla transitoria: más tarde, o detenido si ya son 72 horas.

        `hacienda` dice si el que no contestó fue Hacienda o su IdP. Solo eso se
        anota en `unreachable_at`, que es lo que mira la situación «sin
        internet» (RN-43): Vault sellado o el almacén caído son nuestros, y
        declararlos ante Hacienda sería un rechazo.
        """
        ahora = self._d.clock.now()
        fallas = doc.failures + 1
        primera = doc.first_failure_at or ahora
        desenlace, proximo = recorrido.after_transient_failure(
            failures=fallas, first_failure_at=primera, now=ahora, detail=detalle
        )
        if desenlace.state == recorrido.STOPPED:
            return self._detener(doc, desenlace.reason or recorrido.STOP_RETRIES_EXHAUSTED, detalle)
        return self._escribir(
            doc,
            DocumentUpdate(
                status=recorrido.RETRYING,
                failures=fallas,
                first_failure_at=primera,
                last_attempt_at=ahora,
                next_attempt_at=proximo,
                stop_detail=_detalle(detalle) or None,
                **({"unreachable_at": ahora} if hacienda else {}),
            ),
            EVENT_DEFERRED,
            _detalle(detalle),
        )

    def _credenciales(self, doc: DocumentSnapshot) -> FeCredentialsSnapshot | None:
        return self._d.credentials.get(doc.environment)

    def _token(self, doc: DocumentSnapshot, credenciales: FeCredentialsSnapshot) -> str:
        contrasena = self._d.secrets.decrypt(
            credenciales.atv_password_encrypted or "",
            company_id=self._d.company_id,
            environment=doc.environment,
        )
        return self._d.idp.token(
            self._d.endpoints(doc.environment),
            user=credenciales.atv_user or "",
            password=contrasena,
        )


class SignDocument(_Paso):
    """numerado → firmado. Arma el XML, lo firma con la llave de Vault y lo
    guarda **antes** de anotarlo (RN-44)."""

    def __call__(self, doc: DocumentSnapshot) -> DocumentSnapshot:
        ahora = self._d.clock.now()
        credenciales = self._credenciales(doc)
        if credenciales is None or not credenciales.certificate_pem:
            return self._detener(doc, recorrido.STOP_CERTIFICATE_MISSING)
        if credenciales.expires_at is not None and credenciales.expires_at <= ahora:
            return self._detener(
                doc, recorrido.STOP_CERTIFICATE_EXPIRED, credenciales.expires_at.isoformat()
            )

        ref = DocumentRef(self._d.company_id, doc.environment, SIGNED_PAYLOAD, doc.clave)
        try:
            if not self._d.store.exists(ref):
                firmado = self._firmar(doc, credenciales.certificate_pem, ahora)
                if firmado is None:
                    # `_firmar` ya escribió por qué se detuvo.
                    return self._d.documents.get(doc.id) or doc
                self._d.store.put(ref, firmado)
        except DocumentAlreadyStored:
            # Otro proceso lo guardó entre el `exists` y el `put`: es el mismo
            # documento y vale el que llegó primero.
            pass
        except (SigningUnavailable, StorageUnavailable) as exc:
            return self._diferir(doc, str(exc))

        return self._escribir(
            doc,
            DocumentUpdate(
                status=recorrido.SIGNED,
                signed_at=ahora,
                xml_key=ref.key,
                failures=0,
                first_failure_at=None,
                last_attempt_at=ahora,
                next_attempt_at=ahora,
                stop_reason=None,
                stop_detail=None,
            ),
            EVENT_SIGNED,
        )

    def _firmar(self, doc: DocumentSnapshot, pem: str, ahora: datetime) -> bytes | None:
        """Los bytes firmados, o nada si el documento se detuvo acá."""
        try:
            comprobante = self._d.source.comprobante(doc)
            xml = construir(comprobante)
            certificado = self._d.certificates.facts(pem)
        except (ComprobanteInvalido, DomainError, InvalidSignatureInput) as exc:
            self._detener(doc, recorrido.STOP_DOCUMENT_INVALID, _motivo(exc))
            return None
        except InvalidCertificate as exc:
            self._detener(doc, recorrido.STOP_CERTIFICATE_MISSING, exc.reason)
            return None

        def firma(digest: bytes) -> bytes:
            return self._d.signer.sign(
                digest, company_id=self._d.company_id, environment=doc.environment
            )

        try:
            return sign_document(xml, certificate=certificado, signed_at=ahora, sign=firma)
        except SigningKeyMissing:
            self._detener(doc, recorrido.STOP_CERTIFICATE_MISSING, "key")
            return None


def _motivo(exc: Exception) -> str:
    """El código que trae el error del dominio, sin la frase.

    `ComprobanteInvalido` y los errores del dominio llevan el código aparte de
    la frase; se prefiere eso. Lo demás, sus argumentos o su clase.
    """
    codigo = getattr(exc, "code", None)
    if isinstance(codigo, str) and codigo:
        detalle = getattr(exc, "detail", "")
        return f"{codigo}:{detalle}" if detalle not in (None, "") else codigo
    partes = [str(a) for a in getattr(exc, "args", ()) if a not in (None, "")]
    return ":".join(partes) if partes else exc.__class__.__name__


class SubmitDocument(_Paso):
    """firmado → enviado. Pide el token, manda el XML y espera el 202."""

    def __call__(self, doc: DocumentSnapshot) -> DocumentSnapshot:
        ahora = self._d.clock.now()
        credenciales = self._credenciales(doc)
        if (
            credenciales is None
            or not credenciales.atv_user
            or not credenciales.atv_password_encrypted
        ):
            return self._detener(doc, recorrido.STOP_CREDENTIALS_MISSING)

        ref = DocumentRef(self._d.company_id, doc.environment, SIGNED_PAYLOAD, doc.clave)
        try:
            firmado = self._d.store.get(ref)
        except DocumentNotFound:
            # El almacén no tiene lo que la fila dice que firmó. Se vuelve a
            # firmar, y queda anotado: no es normal.
            return self._escribir(
                doc,
                DocumentUpdate(status=recorrido.NUMBERED, xml_key=None, signed_at=None, next_attempt_at=ahora),
                EVENT_XML_LOST,
                ref.key,
            )
        except StorageUnavailable as exc:
            return self._diferir(doc, str(exc))

        try:
            partes = recorrido.document_parties(firmado)
        except recorrido.InvalidHaciendaMessage as exc:
            return self._detener(doc, recorrido.STOP_DOCUMENT_INVALID, _motivo(exc))
        cuerpo = recorrido.reception_payload(
            clave=doc.clave,
            fecha=partes.fecha,
            emisor=partes.emisor,
            receptor=partes.receptor,
            signed_xml=firmado,
        )
        destino = self._d.endpoints(doc.environment)
        try:
            token = self._token(doc, credenciales)
            try:
                self._d.reception.submit(destino, token=token, payload=cuerpo)
            except TokenRejected:
                # Venció entre pedirlo y usarlo. Una vez más, con uno nuevo.
                token = self._token(doc, credenciales)
                self._d.reception.submit(destino, token=token, payload=cuerpo)
        except CredentialsRejected:
            return self._detener(doc, recorrido.STOP_CREDENTIALS_REJECTED)
        except ReceptionRejected as exc:
            return self._detener(doc, recorrido.STOP_RECEPTION_REJECTED, exc.cause)
        except ReceptionForbidden as exc:
            return self._detener(doc, recorrido.STOP_FORBIDDEN, exc.cause)
        except (IdpUnreachable, ReceptionUnavailable, TokenRejected) as exc:
            return self._diferir(doc, str(exc), hacienda=True)

        return self._escribir(
            doc,
            DocumentUpdate(
                status=recorrido.SENT,
                sent_at=ahora,
                polls=0,
                failures=0,
                first_failure_at=None,
                last_attempt_at=ahora,
                next_attempt_at=ahora + recorrido.poll_delay(0),
                hacienda_status=recorrido.IND_RECIBIDO,
                stop_reason=None,
                stop_detail=None,
            ),
            EVENT_SENT,
        )


class PollVerdict(_Paso):
    """enviado → aceptado | rechazado, o enviado otra vez más tarde (RN-40)."""

    def __call__(self, doc: DocumentSnapshot) -> DocumentSnapshot:
        ahora = self._d.clock.now()
        credenciales = self._credenciales(doc)
        if (
            credenciales is None
            or not credenciales.atv_user
            or not credenciales.atv_password_encrypted
        ):
            return self._detener(doc, recorrido.STOP_CREDENTIALS_MISSING)

        destino = self._d.endpoints(doc.environment)
        consultas = doc.polls + 1
        try:
            token = self._token(doc, credenciales)
            try:
                veredicto = self._d.reception.status(destino, token=token, clave=doc.clave)
            except TokenRejected:
                token = self._token(doc, credenciales)
                veredicto = self._d.reception.status(destino, token=token, clave=doc.clave)
        except VerdictNotFound:
            # Todavía no la registra: pasa en los segundos que siguen al 202.
            veredicto = Verdict(recorrido.IND_RECIBIDO)
        except CredentialsRejected:
            return self._detener(doc, recorrido.STOP_CREDENTIALS_REJECTED)
        except (IdpUnreachable, ReceptionUnavailable, TokenRejected) as exc:
            return self._diferir(doc, str(exc), hacienda=True)

        desenlace, proximo = recorrido.after_verdict(
            veredicto.ind_estado, sent_at=doc.sent_at, polls=consultas, now=ahora
        )
        if desenlace.state in recorrido.FINAL:
            return self._resolver(doc, veredicto, desenlace.state, consultas, ahora)
        if desenlace.state == recorrido.STOPPED:
            return self._detener(doc, desenlace.reason or recorrido.STOP_HACIENDA_ERROR, desenlace.detail)
        return self._escribir(
            doc,
            DocumentUpdate(
                polls=consultas,
                last_attempt_at=ahora,
                next_attempt_at=proximo,
                hacienda_status=desenlace.detail or veredicto.ind_estado,
            ),
            EVENT_POLLED,
            veredicto.ind_estado,
        )

    def _resolver(
        self,
        doc: DocumentSnapshot,
        veredicto: Verdict,
        estado: str,
        consultas: int,
        ahora: datetime,
    ) -> DocumentSnapshot:
        """Guarda la respuesta firmada de Hacienda y cierra el recorrido."""
        llave: str | None = None
        detalle = ""
        if veredicto.respuesta_xml:
            ref = DocumentRef(self._d.company_id, doc.environment, GOV_RESPONSE, doc.clave)
            try:
                self._d.store.put(ref, veredicto.respuesta_xml)
            except DocumentAlreadyStored:
                pass
            except StorageUnavailable as exc:
                # El veredicto sigue ahí; sin la respuesta archivada no se cierra
                # (RN-44). Se vuelve a consultar más tarde.
                return self._diferir(doc, str(exc))
            llave = ref.key
            try:
                detalle = recorrido.parse_hacienda_message(veredicto.respuesta_xml).detalle
            except recorrido.InvalidHaciendaMessage:
                detalle = ""
        evento = EVENT_ACCEPTED if estado == recorrido.ACCEPTED else EVENT_REJECTED
        return self._escribir(
            doc,
            DocumentUpdate(
                status=estado,
                polls=consultas,
                resolved_at=ahora,
                last_attempt_at=ahora,
                next_attempt_at=None,
                hacienda_status=veredicto.ind_estado,
                response_key=llave,
                stop_reason=None,
                stop_detail=_detalle(detalle) or None,
            ),
            evento,
            _detalle(detalle),
        )


class ProcessDue:
    """La cola: lo que ya le toca, paso por paso, en orden de antigüedad.

    Firmar y enviar van seguidos en el mismo turno cuando los dos salen bien:
    el cajero está esperando ver «enviado», no «firmado». Lo que falla espera
    su cadencia.
    """

    def __init__(
        self, documents: TransmissionRepository, clock: Clock, *, sign: SignDocument, submit: SubmitDocument, poll: PollVerdict
    ) -> None:
        self._documents = documents
        self._clock = clock
        self._sign = sign
        self._submit = submit
        self._poll = poll

    def __call__(self, *, limit: int = 20) -> int:
        atendidos = 0
        for doc in self._documents.due(self._clock.now(), limit=limit):
            self.step(doc)
            atendidos += 1
        return atendidos

    def step(self, doc: DocumentSnapshot) -> DocumentSnapshot:
        paso = recorrido.next_step(doc.status, sent=doc.sent, signed=doc.signed)
        if paso == recorrido.SIGN:
            doc = self._sign(doc)
            if doc.status == recorrido.SIGNED:
                doc = self._submit(doc)
            return doc
        if paso == recorrido.SUBMIT:
            return self._submit(doc)
        if paso == recorrido.POLL:
            return self._poll(doc)
        return doc


class RetryDocument:
    """RF-36: una persona reintenta lo detenido, después de arreglar la causa.

    Vuelve el documento al paso en que estaba —a firmar, a enviar o a
    consultar, según las huellas— y lo deja para el próximo turno de la cola.
    Lo que no está detenido no se toca (`DocumentNotStopped`).
    """

    def __init__(self, documents: TransmissionRepository, clock: Clock, uow: UnitOfWork) -> None:
        self._documents = documents
        self._clock = clock
        self._uow = uow

    def __call__(self, document_id: int, *, user_id: int) -> DocumentSnapshot:
        doc = self._documents.get(document_id)
        if doc is None:
            raise UnknownDocument(document_id)
        if doc.status != recorrido.STOPPED:
            raise DocumentNotStopped(document_id, doc.status)
        ahora = self._clock.now()
        with self._uow:
            actual = self._documents.update(
                document_id,
                DocumentUpdate(
                    status=recorrido.resume_state(sent=doc.sent, signed=doc.signed),
                    failures=0,
                    first_failure_at=None,
                    next_attempt_at=ahora,
                    stop_reason=None,
                    stop_detail=None,
                ),
            )
            self._documents.add_event(
                document_id, DocumentEvent(at=ahora, event=EVENT_RESUMED, detail=f"user:{user_id}")
            )
            self._uow.commit()
        return actual


@dataclass(frozen=True)
class QueueReport:
    """Lo que la pantalla de facturas necesita de la cola (RF-33, RF-35, T-711)."""

    counts: dict[str, int]
    pending: int
    stopped: list[DocumentSnapshot]
    oldest_pending_at: datetime | None
    alarm: str
    contingency: bool


class QueueSummary:
    def __init__(self, documents: TransmissionRepository, clock: Clock) -> None:
        self._documents = documents
        self._clock = clock

    def __call__(self) -> QueueReport:
        ahora = self._clock.now()
        cuenta: QueueCounts = self._documents.counts()
        salud = self._documents.health()
        pendientes = sum(cuenta.by_status.get(e, 0) for e in recorrido.PENDING)
        return QueueReport(
            counts=dict(cuenta.by_status),
            pending=pendientes,
            stopped=self._documents.stopped(),
            oldest_pending_at=cuenta.oldest_pending_at,
            alarm=recorrido.queue_alarm(cuenta.oldest_pending_at, ahora),
            contingency=recorrido.in_contingency(
                last_transient_failure_at=salud.last_transient_failure_at,
                last_success_at=salud.last_success_at,
                now=ahora,
            ),
        )


class ObservedContingency:
    """Cumple `ContingencyMode` con lo que la cola observó (RN-43)."""

    def __init__(self, documents: TransmissionRepository, clock: Clock) -> None:
        self._documents = documents
        self._clock = clock

    def active(self) -> bool:
        salud = self._documents.health()
        return recorrido.in_contingency(
            last_transient_failure_at=salud.last_transient_failure_at,
            last_success_at=salud.last_success_at,
            now=self._clock.now(),
        )


class ProductionGate:
    """T-713, RN-46: qué falta ver aceptado en pruebas para pasar a producción."""

    def __init__(self, documents: TransmissionRepository) -> None:
        self._documents = documents

    def missing(self) -> tuple[str, ...]:
        return recorrido.production_gate(self._documents.accepted_by_type(SANDBOX))
