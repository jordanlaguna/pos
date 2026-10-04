"""
El recorrido del comprobante, sin Vault, sin MinIO y sin Hacienda (T-707 a T-713).

Cada paso con sus desenlaces: lo que avanza, lo que espera y lo que detiene
(RN-41), y que cada uno deje su huella en la bitácora. La firma es la de verdad
—`FakeDocumentSigner` firma con una llave en memoria— porque lo que se guarda
tiene que ser un XML que verifique, no unos bytes cualquiera.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import serialization

from app.application.ports.documents import DocumentAlreadyStored, DocumentNotFound, StorageUnavailable
from app.application.ports.fe_documents import UNSET, DocumentUpdate, TransmissionHealth, Unset
from app.application.ports.signing import InvalidCertificate, SigningUnavailable
from app.application.ports.transmission import (
    CredentialsRejected,
    IdpUnreachable,
    ReceptionForbidden,
    ReceptionRejected,
    ReceptionUnavailable,
    TokenRejected,
    Verdict,
    VerdictNotFound,
)
from app.application.use_cases.fe_transmission import (
    EVENT_ACCEPTED,
    EVENT_DEFERRED,
    EVENT_POLLED,
    EVENT_REJECTED,
    EVENT_RESUMED,
    EVENT_SENT,
    EVENT_SIGNED,
    EVENT_STOPPED,
    EVENT_XML_LOST,
    ObservedContingency,
    PollVerdict,
    ProcessDue,
    ProductionGate,
    QueueSummary,
    RetryDocument,
    SignDocument,
    SubmitDocument,
    TransmissionDeps,
    _motivo,
)
from app.domain import fe_transmission as r
from app.domain.errors import DocumentNotStopped, InvalidLocation, UnknownDocument
from app.domain.fe_signature import signature_parts
from app.domain.fe_xml import ComprobanteInvalido, MedioPago
from app.domain.hacienda import endpoints
from app.infrastructure.clock import FixedClock
from tests.domain.test_fe_signature import CERTIFICADO, DATOS, LLAVE, verifica
from tests.domain.test_fe_xml import comprobante

from .fakes import (
    FakeCertificateParser,
    FakeComprobanteSource,
    FakeDocumentSigner,
    FakeDocumentStore,
    FakeFeCredentialsRepository,
    FakeHaciendaIdp,
    FakeHaciendaReception,
    FakeSecretBox,
    FakeTransmissionRepository,
    FakeUnitOfWork,
    FilaDeCredenciales,
    documento,
)

AHORA = datetime(2026, 10, 3, 12, 0, 0)
PEM = CERTIFICADO.public_bytes(serialization.Encoding.PEM).decode("ascii")
PKCS8 = LLAVE.private_bytes(
    serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
)
TIQUETE = comprobante(tipo="04", receptor=None, medios_pago=(MedioPago("01", Decimal("1130")),))
RESPUESTA = (
    b'<MensajeHacienda xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda">'
    b"<Mensaje>{m}</Mensaje><DetalleMensaje>{d}</DetalleMensaje></MensajeHacienda>"
)


def respuesta(mensaje: str, detalle: str = "") -> bytes:
    return RESPUESTA.replace(b"{m}", mensaje.encode()).replace(b"{d}", detalle.encode())


def credenciales(**cambios) -> FilaDeCredenciales:
    base = dict(
        environment="sandbox",
        certificate_pem=PEM,
        certificate_name="SWS",
        expires_at=AHORA + timedelta(days=365),
        atv_user="cpj-3101702934@stag.comprobanteselectronicos.go.cr",
        atv_password_encrypted=FakeSecretBox().encrypt("secreta", company_id=1, environment="sandbox"),
    )
    return FilaDeCredenciales(**{**base, **cambios})


class Mundo:
    """Los adaptadores en memoria, armados una vez por prueba."""

    def __init__(self, *docs, cuando=AHORA, filas=None, fuente=None, recepcion=None, idp=None, parser=None):
        self.docs = FakeTransmissionRepository(docs or (documento(),))
        self.store = FakeDocumentStore()
        self.signer = FakeDocumentSigner()
        self.signer.import_key(PKCS8, company_id=1, environment="sandbox")
        self.recepcion = recepcion or FakeHaciendaReception()
        self.idp = idp or FakeHaciendaIdp()
        self.uow = FakeUnitOfWork()
        self.reloj = FixedClock(cuando)
        self.deps = TransmissionDeps(
            documents=self.docs,
            source=fuente or FakeComprobanteSource(TIQUETE),
            credentials=FakeFeCredentialsRepository(filas if filas is not None else [credenciales()]),
            certificates=parser or FakeCertificateParser(DATOS),
            signer=self.signer,
            store=self.store,
            idp=self.idp,
            reception=self.recepcion,
            secrets=FakeSecretBox(),
            endpoints=endpoints,
            clock=self.reloj,
            uow=self.uow,
            company_id=1,
        )

    def firmar(self, doc=None):
        return SignDocument(self.deps)(doc or self.docs.get(1))

    def enviar(self, doc=None):
        return SubmitDocument(self.deps)(doc or self.docs.get(1))

    def consultar(self, doc=None):
        return PollVerdict(self.deps)(doc or self.docs.get(1))

    def eventos(self, id_=1):
        return [e.event for e in self.docs.events(id_)]

    def xml_ref(self):
        from app.domain.fe_documents import SIGNED_PAYLOAD, DocumentRef

        return DocumentRef(1, "sandbox", SIGNED_PAYLOAD, documento().clave)


# ------------------------------------------------------------------ firmar


class TestFirmar:
    def test_firma_guarda_y_pasa_a_firmado(self):
        m = Mundo()
        doc = m.firmar()
        assert doc.status == r.SIGNED
        assert doc.signed_at == AHORA and doc.next_attempt_at == AHORA
        assert doc.xml_key == m.xml_ref().key
        assert doc.failures == 0 and doc.stop_reason is None
        assert m.eventos() == [EVENT_SIGNED]
        # Y lo guardado es un XML que verifica con el certificado.
        assert verifica(signature_parts(m.store.get(m.xml_ref())))
        assert m.uow.committed is True

    def test_lo_que_ya_estaba_en_el_almacen_no_se_vuelve_a_firmar(self):
        m = Mundo()
        m.store.put(m.xml_ref(), b"<ya-firmado/>")
        doc = m.firmar()
        assert doc.status == r.SIGNED
        assert m.store.get(m.xml_ref()) == b"<ya-firmado/>"
        assert m.deps.source.pedidos == []

    def test_sin_certificado_se_detiene(self):
        m = Mundo(filas=[credenciales(certificate_pem=None)])
        doc = m.firmar()
        assert (doc.status, doc.stop_reason) == (r.STOPPED, r.STOP_CERTIFICATE_MISSING)
        assert doc.next_attempt_at is None
        assert m.eventos() == [EVENT_STOPPED]

    def test_sin_fila_de_credenciales_tambien(self):
        m = Mundo(filas=[])
        assert m.firmar().stop_reason == r.STOP_CERTIFICATE_MISSING

    def test_un_certificado_vencido_se_detiene_en_el_primer_intento(self):
        m = Mundo(filas=[credenciales(expires_at=AHORA - timedelta(days=1))])
        doc = m.firmar()
        assert (doc.status, doc.stop_reason) == (r.STOPPED, r.STOP_CERTIFICATE_EXPIRED)
        assert doc.stop_detail and doc.stop_detail.startswith("2026-10-02")

    def test_un_comprobante_al_que_le_falta_algo_se_detiene_y_dice_que(self):
        m = Mundo(fuente=FakeComprobanteSource(falla=ComprobanteInvalido("linea_sin_cabys", 2)))
        doc = m.firmar()
        assert (doc.status, doc.stop_reason) == (r.STOPPED, r.STOP_DOCUMENT_INVALID)
        assert doc.stop_detail == "linea_sin_cabys:2"
        assert m.eventos() == [EVENT_STOPPED]

    def test_un_error_del_dominio_al_armarlo_tambien(self):
        m = Mundo(fuente=FakeComprobanteSource(falla=InvalidLocation("province", "required", None)))
        doc = m.firmar()
        assert doc.stop_reason == r.STOP_DOCUMENT_INVALID
        assert "province" in (doc.stop_detail or "")

    def test_un_pem_ilegible_es_un_certificado_que_falta(self):
        m = Mundo(parser=FakeCertificateParser(falla=InvalidCertificate("unreadable")))
        doc = m.firmar()
        assert (doc.stop_reason, doc.stop_detail) == (r.STOP_CERTIFICATE_MISSING, "unreadable")

    def test_sin_llave_en_vault_es_un_certificado_que_falta(self):
        m = Mundo()
        m.signer.forget_key(company_id=1, environment="sandbox")
        doc = m.firmar()
        assert (doc.stop_reason, doc.stop_detail) == (r.STOP_CERTIFICATE_MISSING, "key")

    def test_vault_sellado_espera_y_reintenta(self):
        m = Mundo()

        def sellado(*a, **k):
            raise SigningUnavailable("sealed")

        m.signer.sign = sellado  # type: ignore[method-assign]
        doc = m.firmar()
        assert doc.status == r.RETRYING
        assert doc.failures == 1 and doc.first_failure_at == AHORA
        assert doc.next_attempt_at == AHORA + timedelta(minutes=5)
        assert doc.stop_detail == "sealed"
        assert m.eventos() == [EVENT_DEFERRED]
        # Es nuestra, no de Hacienda: no cuenta para la situación «sin internet».
        assert doc.unreachable_at is None

    def test_el_almacen_caido_espera_y_reintenta(self):
        m = Mundo()

        def caido(ref, content):
            raise StorageUnavailable("minio")

        m.store.put = caido  # type: ignore[method-assign]
        doc = m.firmar()
        assert doc.status == r.RETRYING
        # El almacén es nuestro: no cuenta para la situación «sin internet».
        assert doc.unreachable_at is None

    def test_dos_procesos_firmando_a_la_vez_valen_el_primero(self):
        m = Mundo()

        def ya_estaba(ref, content):
            raise DocumentAlreadyStored(ref.key)

        m.store.put = ya_estaba  # type: ignore[method-assign]
        assert m.firmar().status == r.SIGNED

    def test_a_las_72_horas_de_fallas_se_detiene(self):
        m = Mundo(documento(status=r.RETRYING, failures=9, first_failure_at=AHORA - timedelta(hours=72)))

        def sellado(*a, **k):
            raise SigningUnavailable("sealed")

        m.signer.sign = sellado  # type: ignore[method-assign]
        doc = m.firmar()
        assert (doc.status, doc.stop_reason) == (r.STOPPED, r.STOP_RETRIES_EXHAUSTED)


# ------------------------------------------------------------------- enviar


def firmado_en(m: Mundo):
    """Deja el documento firmado y devuelve la instantánea."""
    return m.firmar()


class TestEnviar:
    def test_envia_y_queda_esperando_el_veredicto(self):
        m = Mundo()
        firmado_en(m)
        doc = m.enviar()
        assert doc.status == r.SENT
        assert doc.sent_at == AHORA and doc.polls == 0
        assert doc.next_attempt_at == AHORA + timedelta(seconds=10)
        assert doc.hacienda_status == r.IND_RECIBIDO
        assert m.eventos() == [EVENT_SIGNED, EVENT_SENT]
        cuerpo = m.recepcion.payloads[0]
        assert cuerpo["clave"] == documento().clave
        assert cuerpo["emisor"] == {"tipoIdentificacion": "02", "numeroIdentificacion": "3101123456"}
        assert "receptor" not in cuerpo
        assert base64.b64decode(cuerpo["comprobanteXml"]) == m.store.get(m.xml_ref())
        assert m.recepcion.tokens == ["tok-123"]

    def test_sin_usuario_de_atv_se_detiene(self):
        m = Mundo(filas=[credenciales(atv_user=None)])
        firmado_en(m)
        assert m.enviar().stop_reason == r.STOP_CREDENTIALS_MISSING

    def test_sin_contrasena_tambien(self):
        m = Mundo(filas=[credenciales(atv_password_encrypted=None)])
        firmado_en(m)
        assert m.enviar().stop_reason == r.STOP_CREDENTIALS_MISSING

    def test_si_el_almacen_perdio_el_xml_se_vuelve_a_firmar(self):
        m = Mundo()
        doc = firmado_en(m)
        m.store.contenido.clear()
        despues = m.enviar(doc)
        assert (despues.status, despues.xml_key, despues.signed_at) == (r.NUMBERED, None, None)
        assert m.eventos()[-1] == EVENT_XML_LOST

    def test_el_almacen_caido_espera(self):
        m = Mundo()
        doc = firmado_en(m)

        def caido(ref):
            raise StorageUnavailable("minio")

        m.store.get = caido  # type: ignore[method-assign]
        assert m.enviar(doc).status == r.RETRYING

    def test_un_xml_sin_emisor_se_detiene(self):
        m = Mundo()
        doc = firmado_en(m)
        m.store.contenido[m.xml_ref().key] = b"<x/>"
        assert m.enviar(doc).stop_reason == r.STOP_DOCUMENT_INVALID

    def test_credenciales_que_hacienda_no_acepta_detienen(self):
        m = Mundo(idp=FakeHaciendaIdp(falla=CredentialsRejected()))
        firmado_en(m)
        assert m.enviar().stop_reason == r.STOP_CREDENTIALS_REJECTED

    def test_el_idp_caido_espera(self):
        m = Mundo(idp=FakeHaciendaIdp(falla=IdpUnreachable()))
        firmado_en(m)
        doc = m.enviar()
        assert doc.status == r.RETRYING and doc.next_attempt_at == AHORA + timedelta(minutes=5)
        # Esta sí es de Hacienda, y queda anotada para RN-43.
        assert doc.unreachable_at == AHORA

    def test_un_400_se_detiene_con_lo_que_dijo_hacienda(self):
        m = Mundo(recepcion=FakeHaciendaReception(envios=[ReceptionRejected("clave duplicada")]))
        firmado_en(m)
        doc = m.enviar()
        assert (doc.stop_reason, doc.stop_detail) == (r.STOP_RECEPTION_REJECTED, "clave duplicada")

    def test_un_403_se_detiene_con_lo_que_dijo_el_servidor(self):
        m = Mundo(recepcion=FakeHaciendaReception(envios=[ReceptionForbidden("IncompleteSignatureException")]))
        firmado_en(m)
        doc = m.enviar()
        assert (doc.stop_reason, doc.stop_detail) == (r.STOP_FORBIDDEN, "IncompleteSignatureException")

    def test_hacienda_caida_espera(self):
        m = Mundo(recepcion=FakeHaciendaReception(envios=[ReceptionUnavailable("502")]))
        firmado_en(m)
        doc = m.enviar()
        assert (doc.status, doc.stop_detail) == (r.RETRYING, "502")
        assert doc.unreachable_at == AHORA

    def test_un_token_vencido_se_pide_otra_vez(self):
        m = Mundo(recepcion=FakeHaciendaReception(envios=[TokenRejected(), None]))
        firmado_en(m)
        assert m.enviar().status == r.SENT
        assert len(m.recepcion.payloads) == 2

    def test_dos_tokens_vencidos_seguidos_esperan(self):
        m = Mundo(recepcion=FakeHaciendaReception(envios=[TokenRejected(), TokenRejected()]))
        firmado_en(m)
        assert m.enviar().status == r.RETRYING


# ---------------------------------------------------------------- consultar


def enviado(**cambios):
    base = dict(
        status=r.SENT,
        xml_key="1/sandbox/signed-payload/2026/10/x.xml",
        signed_at=AHORA - timedelta(minutes=1),
        sent_at=AHORA - timedelta(seconds=30),
        next_attempt_at=AHORA,
    )
    return documento(**{**base, **cambios})


class TestConsultar:
    def test_aceptado_guarda_la_respuesta_y_cierra(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado", respuesta("1", "ok"))]))
        doc = m.consultar()
        assert doc.status == r.ACCEPTED
        assert doc.resolved_at == AHORA and doc.polls == 1 and doc.next_attempt_at is None
        assert doc.hacienda_status == "aceptado" and doc.stop_detail == "ok"
        assert doc.response_key and doc.response_key.endswith(f"/{documento().clave}.xml")
        assert m.eventos() == [EVENT_ACCEPTED]
        assert m.recepcion.claves == [documento().clave]

    def test_rechazado_cierra_con_el_motivo(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("rechazado", respuesta("3", "Firma inválida"))]))
        doc = m.consultar()
        assert (doc.status, doc.stop_detail) == (r.REJECTED, "Firma inválida")
        assert m.eventos() == [EVENT_REJECTED]

    def test_aceptado_sin_respuesta_cierra_igual(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado", None)]))
        doc = m.consultar()
        assert doc.status == r.ACCEPTED and doc.response_key is None

    def test_una_respuesta_que_no_se_entiende_no_impide_cerrar(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado", b"<raro/>")]))
        doc = m.consultar()
        assert doc.status == r.ACCEPTED and doc.stop_detail is None

    def test_en_proceso_vuelve_a_preguntar_mas_tarde(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("procesando")]))
        doc = m.consultar()
        assert doc.status == r.SENT and doc.polls == 1
        assert doc.next_attempt_at == AHORA + timedelta(seconds=30)
        assert doc.hacienda_status == "procesando"
        assert m.eventos() == [EVENT_POLLED]

    def test_un_404_es_todavia_no(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[VerdictNotFound()]))
        doc = m.consultar()
        assert doc.status == r.SENT and doc.hacienda_status == r.IND_RECIBIDO

    def test_tres_dias_sin_veredicto_es_para_una_persona(self):
        m = Mundo(
            enviado(sent_at=AHORA - timedelta(hours=72), polls=800),
            recepcion=FakeHaciendaReception(consultas=[Verdict("procesando")]),
        )
        doc = m.consultar()
        assert (doc.status, doc.stop_reason) == (r.STOPPED, r.STOP_NO_VERDICT)

    def test_error_de_hacienda_es_para_una_persona(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("error")]))
        doc = m.consultar()
        assert (doc.status, doc.stop_reason, doc.stop_detail) == (r.STOPPED, r.STOP_HACIENDA_ERROR, "error")

    def test_sin_credenciales_se_detiene(self):
        m = Mundo(enviado(), filas=[credenciales(atv_user=None)])
        assert m.consultar().stop_reason == r.STOP_CREDENTIALS_MISSING

    def test_credenciales_rechazadas_detienen(self):
        m = Mundo(enviado(), idp=FakeHaciendaIdp(falla=CredentialsRejected()))
        assert m.consultar().stop_reason == r.STOP_CREDENTIALS_REJECTED

    def test_hacienda_caida_espera(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[ReceptionUnavailable("503")]))
        doc = m.consultar()
        assert doc.status == r.RETRYING
        assert doc.unreachable_at == AHORA

    def test_un_token_vencido_se_pide_otra_vez(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[TokenRejected(), Verdict("aceptado")]))
        assert m.consultar().status == r.ACCEPTED
        assert len(m.recepcion.claves) == 2

    def test_la_respuesta_ya_guardada_no_estorba(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado", respuesta("1"))]))
        from app.domain.fe_documents import GOV_RESPONSE, DocumentRef

        m.store.put(DocumentRef(1, "sandbox", GOV_RESPONSE, documento().clave), respuesta("1"))
        assert m.consultar().status == r.ACCEPTED

    def test_sin_almacen_el_veredicto_espera(self):
        m = Mundo(enviado(), recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado", respuesta("1"))]))

        def caido(ref, content):
            raise StorageUnavailable("minio")

        m.store.put = caido  # type: ignore[method-assign]
        doc = m.consultar()
        assert doc.status == r.RETRYING


# --------------------------------------------------------------------- la cola


class TestLaCola:
    def test_firma_y_envia_en_el_mismo_turno(self):
        m = Mundo()
        cola = ProcessDue(m.docs, m.reloj, sign=SignDocument(m.deps), submit=SubmitDocument(m.deps), poll=PollVerdict(m.deps))
        assert cola() == 1
        assert m.docs.get(1).status == r.SENT
        assert m.eventos() == [EVENT_SIGNED, EVENT_SENT]

    def test_si_firmar_se_detiene_no_envia(self):
        m = Mundo(filas=[credenciales(certificate_pem=None)])
        cola = ProcessDue(m.docs, m.reloj, sign=SignDocument(m.deps), submit=SubmitDocument(m.deps), poll=PollVerdict(m.deps))
        cola()
        assert m.docs.get(1).status == r.STOPPED and m.recepcion.payloads == []

    def test_lo_firmado_se_envia_y_lo_enviado_se_consulta(self):
        m = Mundo(
            documento(id=1, status=r.SIGNED, xml_key="k", signed_at=AHORA, next_attempt_at=AHORA),
            enviado(id=2),
            recepcion=FakeHaciendaReception(consultas=[Verdict("aceptado")]),
        )
        m.store.put(m.xml_ref(), m.store.contenido.get("x", b"") or SignDocument(m.deps)._firmar(documento(), PEM, AHORA))
        cola = ProcessDue(m.docs, m.reloj, sign=SignDocument(m.deps), submit=SubmitDocument(m.deps), poll=PollVerdict(m.deps))
        assert cola() == 2
        assert m.docs.get(1).status == r.SENT
        assert m.docs.get(2).status == r.ACCEPTED

    def test_lo_que_no_le_toca_todavia_no_se_toca(self):
        m = Mundo(documento(next_attempt_at=AHORA + timedelta(minutes=1)))
        cola = ProcessDue(m.docs, m.reloj, sign=SignDocument(m.deps), submit=SubmitDocument(m.deps), poll=PollVerdict(m.deps))
        assert cola() == 0

    def test_lo_terminado_no_se_mueve(self):
        m = Mundo(documento(status=r.ACCEPTED))
        cola = ProcessDue(m.docs, m.reloj, sign=SignDocument(m.deps), submit=SubmitDocument(m.deps), poll=PollVerdict(m.deps))
        assert cola.step(m.docs.get(1)).status == r.ACCEPTED


class TestReintentarAMano:
    def _caso(self, m: Mundo):
        return RetryDocument(m.docs, m.reloj, m.uow)

    def test_vuelve_al_paso_que_le_tocaba(self):
        m = Mundo(documento(status=r.STOPPED, stop_reason=r.STOP_FORBIDDEN, stop_detail="x", xml_key="k", failures=3))
        doc = self._caso(m)(1, user_id=7)
        assert doc.status == r.SIGNED
        assert doc.stop_reason is None and doc.stop_detail is None and doc.failures == 0
        assert doc.next_attempt_at == AHORA
        eventos = m.docs.events(1)
        assert eventos[-1].event == EVENT_RESUMED and eventos[-1].detail == "user:7"

    def test_lo_enviado_vuelve_a_consultarse(self):
        m = Mundo(documento(status=r.STOPPED, xml_key="k", sent_at=AHORA - timedelta(days=4)))
        assert self._caso(m)(1, user_id=1).status == r.SENT

    def test_lo_sin_firmar_vuelve_a_firmarse(self):
        m = Mundo(documento(status=r.STOPPED, stop_reason=r.STOP_CERTIFICATE_MISSING))
        assert self._caso(m)(1, user_id=1).status == r.NUMBERED

    def test_lo_que_no_esta_detenido_no_se_toca(self):
        m = Mundo(documento(status=r.SENT, sent_at=AHORA))
        with pytest.raises(DocumentNotStopped) as e:
            self._caso(m)(1, user_id=1)
        assert (e.value.document_id, e.value.status) == (1, r.SENT)

    def test_lo_que_no_existe(self):
        m = Mundo()
        with pytest.raises(UnknownDocument) as e:
            self._caso(m)(99, user_id=1)
        assert e.value.document_id == 99


class TestLoQueVeLaPantalla:
    def test_el_resumen_de_la_cola(self):
        m = Mundo(
            documento(id=1, status=r.STOPPED, stop_reason=r.STOP_FORBIDDEN, issued_at=AHORA - timedelta(days=6)),
            documento(id=2, status=r.RETRYING, issued_at=AHORA - timedelta(hours=30)),
            documento(id=3, status=r.ACCEPTED),
        )
        m.docs.salud = TransmissionHealth(last_transient_failure_at=AHORA - timedelta(minutes=5), last_success_at=None)
        informe = QueueSummary(m.docs, m.reloj)()
        assert informe.counts == {r.STOPPED: 1, r.RETRYING: 1, r.ACCEPTED: 1}
        assert informe.pending == 1
        assert [d.id for d in informe.stopped] == [1]
        assert informe.oldest_pending_at == AHORA - timedelta(hours=30)
        assert informe.alarm == r.ALARM_WARNING
        assert informe.contingency is True

    def test_la_contingencia_observada(self):
        m = Mundo()
        assert ObservedContingency(m.docs, m.reloj).active() is False
        m.docs.salud = TransmissionHealth(AHORA - timedelta(minutes=1), None)
        assert ObservedContingency(m.docs, m.reloj).active() is True

    def test_la_puerta_de_produccion_cuenta_aceptados_en_pruebas(self):
        m = Mundo(
            documento(id=1, document_type="01", status=r.ACCEPTED),
            documento(id=2, document_type="04", status=r.ACCEPTED),
            documento(id=3, document_type="03", status=r.SENT, sent_at=AHORA),
            documento(id=4, document_type="03", status=r.ACCEPTED, environment="production"),
        )
        assert ProductionGate(m.docs).missing() == ("03",)


class TestLoPequeno:
    def test_el_motivo_de_un_error(self):
        assert _motivo(ComprobanteInvalido("x", 2)) == "x:2"
        assert _motivo(ComprobanteInvalido("solo_codigo")) == "solo_codigo"
        assert _motivo(ValueError("a", 1)) == "a:1"
        assert _motivo(ValueError()) == "ValueError"

    def test_lo_que_no_se_nombra_no_se_toca(self):
        assert DocumentUpdate().fields() == {}
        assert DocumentUpdate(status="sent", stop_reason=None).fields() == {"status": "sent", "stop_reason": None}
        assert repr(UNSET) == "UNSET" and isinstance(UNSET, Unset)

    def test_las_huellas_del_documento(self):
        assert documento().signed is False and documento().sent is False
        assert documento(xml_key="k").signed and documento(sent_at=AHORA).sent
