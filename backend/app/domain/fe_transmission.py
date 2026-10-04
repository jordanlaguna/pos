"""
El recorrido de un comprobante hasta Hacienda (T-707 a T-713, plan §7.2).

    numerado ──> firmado ──> enviado ──> aceptado
                    │            │
                    │            └──> rechazado        (respuesta final)
                    │
                    └──> reintentando ──> detenido     (necesita a una persona)

Acá viven las **reglas** del recorrido y nada de su mecánica: qué estado sigue a
cuál, cada cuánto se insiste, qué falla se reintenta y cuál detiene, cuándo el
negocio está en contingencia y qué hace falta para pasar a producción. Son
funciones sobre fechas y cadenas, y por eso se prueban sin base ni red.

DOS CICLOS, NO UNO (RN-40, RN-41)
---------------------------------

* **El veredicto** se consulta después del 202: 10 s, 30 s, 1, 2 y 5 minutos,
  y de ahí cada 5 minutos. Hacienda resuelve en segundos en condiciones
  normales; con la cadencia del reenvío una venta ya aceptada se vería
  «pendiente» cinco minutos en la caja.
* **El reenvío** es para cuando no se pudo alcanzar a Hacienda: 5, 15 y 30
  minutos, 1, 2, 4, 8, 16 y 24 horas, hasta 72 horas desde la primera falla.

Y **solo lo transitorio se reintenta**. Un rechazo es una respuesta. Un
certificado vencido o unas credenciales que Hacienda no acepta son fallas
nuestras: se detienen en el primer intento, porque reintentar tres días para
llegar a la misma conclusión es demorar el aviso tres días.

Agotar los reintentos tampoco es rendirse (RN-42): el documento pasa a
`detenido`, sigue siendo transmitible a mano y su antigüedad se ve.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Mapping

from .errors import DomainError

# ------------------------------------------------------------------- estados

NUMBERED: Final = "numbered"
SIGNED: Final = "signed"
SENT: Final = "sent"
ACCEPTED: Final = "accepted"
REJECTED: Final = "rejected"
RETRYING: Final = "retrying"
STOPPED: Final = "stopped"

STATES: Final = (NUMBERED, SIGNED, SENT, ACCEPTED, REJECTED, RETRYING, STOPPED)

#: Lo que la cola mueve sola. `retrying` cuenta: es un numerado, firmado o
#: enviado que espera su próximo intento.
PENDING: Final = (NUMBERED, SIGNED, SENT, RETRYING)

#: Lo que Hacienda ya contestó. No se toca más: un rechazo se corrige emitiendo
#: otro comprobante, con otra clave (plan §7.2).
FINAL: Final = (ACCEPTED, REJECTED)

# ---------------------------------------------------------------- los pasos

SIGN: Final = "sign"
SUBMIT: Final = "submit"
POLL: Final = "poll"
STEPS: Final = (SIGN, SUBMIT, POLL)

# ---------------------------------------------------------- por qué se detuvo

STOP_CERTIFICATE_MISSING: Final = "certificate_missing"
STOP_CERTIFICATE_EXPIRED: Final = "certificate_expired"
STOP_CREDENTIALS_MISSING: Final = "credentials_missing"
STOP_CREDENTIALS_REJECTED: Final = "credentials_rejected"
STOP_DOCUMENT_INVALID: Final = "document_invalid"
STOP_RECEPTION_REJECTED: Final = "reception_rejected"
STOP_FORBIDDEN: Final = "forbidden"
STOP_HACIENDA_ERROR: Final = "hacienda_error"
STOP_RETRIES_EXHAUSTED: Final = "retries_exhausted"
STOP_NO_VERDICT: Final = "no_verdict"

STOP_REASONS: Final = (
    STOP_CERTIFICATE_MISSING,
    STOP_CERTIFICATE_EXPIRED,
    STOP_CREDENTIALS_MISSING,
    STOP_CREDENTIALS_REJECTED,
    STOP_DOCUMENT_INVALID,
    STOP_RECEPTION_REJECTED,
    STOP_FORBIDDEN,
    STOP_HACIENDA_ERROR,
    STOP_RETRIES_EXHAUSTED,
    STOP_NO_VERDICT,
)

# ------------------------------------------------------- lo que dice Hacienda

IND_RECIBIDO: Final = "recibido"
IND_PROCESANDO: Final = "procesando"
IND_ACEPTADO: Final = "aceptado"
IND_RECHAZADO: Final = "rechazado"
IND_ERROR: Final = "error"

#: Hacienda recibió y todavía está decidiendo.
IND_EN_PROCESO: Final = (IND_RECIBIDO, IND_PROCESANDO)

#: `Mensaje` del `MensajeHacienda`: 1 aceptado, 3 rechazado. No hay más.
MENSAJE_ACEPTADO: Final = "1"
MENSAJE_RECHAZADO: Final = "3"


class InvalidTransition(DomainError):
    """Se pidió un paso que el estado no admite. `state` y `step` lo dicen."""

    def __init__(self, state: str, step: str) -> None:
        super().__init__(state, step)
        self.state = state
        self.step = step


class InvalidHaciendaMessage(DomainError):
    """La respuesta de Hacienda no es un `MensajeHacienda` que se entienda."""


# ----------------------------------------------------------------- el camino


def next_step(state: str, *, sent: bool, signed: bool) -> str | None:
    """Qué le toca a un documento en ese estado, o nada si ya terminó.

    `retrying` no dice por sí solo en qué paso falló: lo dicen las huellas que
    dejó —si ya se envió se consulta, si ya se firmó se envía, si no se firma—.
    `detenido` tampoco se mueve solo: lo mueve una persona (RN-42).
    """
    if state in FINAL or state == STOPPED:
        return None
    if state == NUMBERED:
        return SIGN
    if state == SIGNED:
        return SUBMIT
    if state == SENT:
        return POLL
    if state == RETRYING:
        if sent:
            return POLL
        return SUBMIT if signed else SIGN
    raise InvalidTransition(state, "next")


def resume_state(*, sent: bool, signed: bool) -> str:
    """A qué estado vuelve un detenido cuando alguien lo reintenta a mano."""
    if sent:
        return SENT
    return SIGNED if signed else NUMBERED


# ------------------------------------------------------------- las cadencias

#: Consulta del veredicto después del 202 (README §8). En segundos.
POLL_DELAYS: Final = (10, 30, 60, 120, 300)

#: Reenvío cuando no se alcanzó a Hacienda. En minutos.
RESEND_DELAYS: Final = (5, 15, 30, 60, 120, 240, 480, 960, 1440)

#: Cuánto se insiste solo antes de detener y avisar. Las dos esperas son
#: largas a propósito: Hacienda pide diseñar para ventanas de mantenimiento de
#: horas, y el plazo de contingencia es de días.
RESEND_HORIZON: Final = timedelta(hours=72)
VERDICT_HORIZON: Final = timedelta(hours=72)


def poll_delay(polls: int) -> timedelta:
    """Cuánto esperar antes de la consulta número `polls + 1`."""
    indice = min(max(polls, 0), len(POLL_DELAYS) - 1)
    return timedelta(seconds=POLL_DELAYS[indice])


def resend_delay(failures: int) -> timedelta:
    """Cuánto esperar después de la falla transitoria número `failures`."""
    indice = min(max(failures, 1), len(RESEND_DELAYS)) - 1
    return timedelta(minutes=RESEND_DELAYS[indice])


def resend_exhausted(first_failure_at: datetime | None, now: datetime) -> bool:
    """Si ya pasaron las 72 horas desde que empezó a fallar."""
    return first_failure_at is not None and now - first_failure_at >= RESEND_HORIZON


def verdict_overdue(sent_at: datetime | None, now: datetime) -> bool:
    """Si Hacienda lleva demasiado sin decidir sobre algo que recibió."""
    return sent_at is not None and now - sent_at >= VERDICT_HORIZON


# --------------------------------------------------------- qué falla detiene


@dataclass(frozen=True)
class Outcome:
    """Lo que un paso dejó: siguió, se reintentará, o se detuvo y por qué."""

    state: str
    reason: str | None = None
    detail: str = ""


def after_transient_failure(
    *, failures: int, first_failure_at: datetime | None, now: datetime, detail: str = ""
) -> tuple[Outcome, datetime | None]:
    """Reintentar más tarde, o detener si ya se insistió 72 horas (RN-42).

    Devuelve el desenlace y la hora del próximo intento (ninguna si se detuvo).
    """
    if resend_exhausted(first_failure_at, now):
        return Outcome(STOPPED, STOP_RETRIES_EXHAUSTED, detail), None
    return Outcome(RETRYING, None, detail), now + resend_delay(failures)


def after_verdict(ind_estado: str, *, sent_at: datetime | None, polls: int, now: datetime) -> tuple[Outcome, datetime | None]:
    """Qué hacer con lo que Hacienda contestó a la consulta."""
    estado = (ind_estado or "").strip().lower()
    if estado == IND_ACEPTADO:
        return Outcome(ACCEPTED), None
    if estado == IND_RECHAZADO:
        return Outcome(REJECTED), None
    if estado in IND_EN_PROCESO:
        if verdict_overdue(sent_at, now):
            return Outcome(STOPPED, STOP_NO_VERDICT, estado), None
        return Outcome(SENT, None, estado), now + poll_delay(polls)
    # «error» y cualquier cosa que no se entienda: Hacienda no pudo decidir.
    # No es un rechazo —no hay motivo que leer— y no se sabe si va a cambiar,
    # así que lo mira una persona.
    return Outcome(STOPPED, STOP_HACIENDA_ERROR, estado), None


# ------------------------------------------------------------ la contingencia

#: Una falla más vieja que esto ya no dice nada del presente.
CONTINGENCY_WINDOW: Final = timedelta(hours=24)


def in_contingency(
    *,
    last_transient_failure_at: datetime | None,
    last_success_at: datetime | None,
    now: datetime,
) -> bool:
    """RN-43: el negocio está en contingencia por un hecho observado.

    Lo observado es que la última vez que se intentó alcanzar a Hacienda no se
    pudo, y desde entonces no se volvió a poder. Una falla seguida de un éxito
    no cuenta, y una falla de hace más de un día tampoco: emitir «sin internet»
    con Hacienda arriba es causa de rechazo, así que la duda se resuelve hacia
    lo normal.
    """
    if last_transient_failure_at is None:
        return False
    if now - last_transient_failure_at > CONTINGENCY_WINDOW:
        return False
    return last_success_at is None or last_success_at < last_transient_failure_at


# ------------------------------------------------- la antigüedad de la cola

ALARM_OK: Final = "ok"
ALARM_WARNING: Final = "warning"
ALARM_DANGER: Final = "danger"

#: A las 24 horas algo anda mal; a los cinco días el plazo de contingencia
#: —unos ocho días hábiles, y Hacienda rechaza pasados los 30— ya se ve venir.
QUEUE_WARNING_AFTER: Final = timedelta(hours=24)
QUEUE_DANGER_AFTER: Final = timedelta(days=5)


def queue_alarm(oldest_pending_at: datetime | None, now: datetime) -> str:
    """T-711: qué tan vieja es la cola, en tres niveles."""
    if oldest_pending_at is None:
        return ALARM_OK
    edad = now - oldest_pending_at
    if edad >= QUEUE_DANGER_AFTER:
        return ALARM_DANGER
    if edad >= QUEUE_WARNING_AFTER:
        return ALARM_WARNING
    return ALARM_OK


# ------------------------------------------------- la puerta de producción

#: Lo que Hacienda exige haber emitido **y visto aceptado** en pruebas antes
#: de producción (README §12, RN-46): una factura, un tiquete y una nota de
#: crédito.
REQUIRED_FOR_PRODUCTION: Final = ("01", "04", "03")


def production_gate(accepted_by_type: Mapping[str, int]) -> tuple[str, ...]:
    """Qué tipos faltan por ver aceptados en pruebas. Vacío es «puede pasar»."""
    return tuple(t for t in REQUIRED_FOR_PRODUCTION if accepted_by_type.get(t, 0) <= 0)


# ------------------------------------------------- lo que Hacienda contesta


@dataclass(frozen=True)
class HaciendaMessage:
    """El `MensajeHacienda`, en lo que importa: aceptó o no, y por qué."""

    mensaje: str
    detalle: str

    @property
    def accepted(self) -> bool:
        return self.mensaje == MENSAJE_ACEPTADO


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_hacienda_message(xml: bytes) -> HaciendaMessage:
    """Lee `Mensaje` y `DetalleMensaje` sin atarse al espacio de nombres.

    El XSD solo enumera `1` y `3` y deja el detalle como texto libre (README
    §11), así que no hay más que leer: el motivo de un rechazo se le muestra a
    la persona tal cual.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise InvalidHaciendaMessage("malformed") from exc
    campos = {_local(nodo.tag): (nodo.text or "").strip() for nodo in raiz.iter()}
    mensaje = campos.get("Mensaje", "")
    if mensaje not in (MENSAJE_ACEPTADO, MENSAJE_RECHAZADO):
        raise InvalidHaciendaMessage("mensaje")
    return HaciendaMessage(mensaje=mensaje, detalle=campos.get("DetalleMensaje", ""))


def decode_response(respuesta_xml: str | None) -> bytes | None:
    """El `respuesta-xml` viene en base64; vacío es «todavía no hay»."""
    if not respuesta_xml:
        return None
    try:
        return base64.b64decode(respuesta_xml, validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidHaciendaMessage("base64") from exc


# ------------------------------------------------- lo que se le manda


@dataclass(frozen=True)
class Party:
    tipo: str
    numero: str


def reception_payload(
    *,
    clave: str,
    fecha: str,
    emisor: Party,
    receptor: Party | None,
    signed_xml: bytes,
) -> dict[str, object]:
    """El cuerpo del `POST /recepcion` (README §7). El XML va en base64.

    `receptor` solo cuando el comprobante lo lleva: un tiquete no tiene, y
    mandar uno vacío es un rechazo de estructura.
    """
    cuerpo: dict[str, object] = {
        "clave": clave,
        "fecha": fecha,
        "emisor": {"tipoIdentificacion": emisor.tipo, "numeroIdentificacion": emisor.numero},
        "comprobanteXml": base64.b64encode(signed_xml).decode("ascii"),
    }
    if receptor is not None:
        cuerpo["receptor"] = {
            "tipoIdentificacion": receptor.tipo,
            "numeroIdentificacion": receptor.numero,
        }
    return cuerpo


def _find(raiz: ET.Element, *camino: str) -> str:
    nodo = raiz
    for nombre in camino:
        siguiente = next((h for h in nodo if _local(h.tag) == nombre), None)
        if siguiente is None:
            return ""
        nodo = siguiente
    return (nodo.text or "").strip()


@dataclass(frozen=True)
class DocumentParties:
    """Lo que el cuerpo del envío repite del XML: la fecha y las dos partes."""

    fecha: str
    emisor: Party
    receptor: Party | None


def document_parties(xml: bytes) -> DocumentParties:
    """Saca del XML firmado lo que el `POST /recepcion` pide aparte.

    Se lee del XML y no de la base para que el cuerpo y el documento digan
    exactamente lo mismo: es lo que Hacienda cruza.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise InvalidHaciendaMessage("malformed") from exc
    fecha = _find(raiz, "FechaEmision")
    emisor = Party(
        _find(raiz, "Emisor", "Identificacion", "Tipo"),
        _find(raiz, "Emisor", "Identificacion", "Numero"),
    )
    if not fecha or not emisor.tipo or not emisor.numero:
        raise InvalidHaciendaMessage("emisor")
    tipo_receptor = _find(raiz, "Receptor", "Identificacion", "Tipo")
    numero_receptor = _find(raiz, "Receptor", "Identificacion", "Numero")
    receptor = Party(tipo_receptor, numero_receptor) if tipo_receptor and numero_receptor else None
    return DocumentParties(fecha=fecha, emisor=emisor, receptor=receptor)
