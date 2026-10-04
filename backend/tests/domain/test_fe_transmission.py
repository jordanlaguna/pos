"""
Las reglas del recorrido, sin base ni red (T-707 a T-713, RN-39 a RN-43, RN-46).
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

import pytest

from app.domain import fe_transmission as t
from app.domain.fe_transmission import (
    ACCEPTED,
    NUMBERED,
    POLL,
    REJECTED,
    RETRYING,
    SENT,
    SIGN,
    SIGNED,
    STOPPED,
    SUBMIT,
    InvalidHaciendaMessage,
    InvalidTransition,
    Party,
)

AHORA = datetime(2026, 10, 3, 12, 0, 0)


class TestElCamino:
    @pytest.mark.parametrize(
        "estado, enviado, firmado, paso",
        [
            (NUMBERED, False, False, SIGN),
            (SIGNED, False, True, SUBMIT),
            (SENT, True, True, POLL),
            (RETRYING, False, False, SIGN),
            (RETRYING, False, True, SUBMIT),
            (RETRYING, True, True, POLL),
            (ACCEPTED, True, True, None),
            (REJECTED, True, True, None),
            (STOPPED, False, False, None),
        ],
    )
    def test_que_le_toca_a_cada_estado(self, estado, enviado, firmado, paso):
        assert t.next_step(estado, sent=enviado, signed=firmado) == paso

    def test_un_estado_que_no_existe_no_tiene_paso(self):
        with pytest.raises(InvalidTransition) as e:
            t.next_step("volando", sent=False, signed=False)
        assert (e.value.state, e.value.step) == ("volando", "next")

    @pytest.mark.parametrize(
        "enviado, firmado, estado",
        [(True, True, SENT), (False, True, SIGNED), (False, False, NUMBERED)],
    )
    def test_a_donde_vuelve_un_detenido(self, enviado, firmado, estado):
        assert t.resume_state(sent=enviado, signed=firmado) == estado

    def test_los_estados_y_los_motivos_son_listas_cerradas(self):
        assert set(t.PENDING) < set(t.STATES)
        assert set(t.FINAL) < set(t.STATES)
        assert len(set(t.STOP_REASONS)) == len(t.STOP_REASONS) == 10


class TestLasCadencias:
    def test_el_veredicto_se_consulta_cada_vez_mas_tarde_y_se_queda_en_cinco_minutos(self):
        assert [t.poll_delay(n).total_seconds() for n in range(7)] == [10, 30, 60, 120, 300, 300, 300]
        assert t.poll_delay(-3) == timedelta(seconds=10)

    def test_el_reenvio_espera_mas_cada_vez_hasta_un_dia(self):
        minutos = [t.resend_delay(n).total_seconds() / 60 for n in range(1, 12)]
        assert minutos == [5, 15, 30, 60, 120, 240, 480, 960, 1440, 1440, 1440]
        assert t.resend_delay(0) == timedelta(minutes=5)

    def test_los_horizontes(self):
        assert not t.resend_exhausted(None, AHORA)
        assert not t.resend_exhausted(AHORA - timedelta(hours=71), AHORA)
        assert t.resend_exhausted(AHORA - timedelta(hours=72), AHORA)
        assert not t.verdict_overdue(None, AHORA)
        assert t.verdict_overdue(AHORA - timedelta(hours=72), AHORA)


class TestQueFallaDetiene:
    def test_una_falla_transitoria_espera_su_turno(self):
        desenlace, proximo = t.after_transient_failure(
            failures=2, first_failure_at=AHORA - timedelta(hours=1), now=AHORA, detail="timeout"
        )
        assert desenlace == t.Outcome(RETRYING, None, "timeout")
        assert proximo == AHORA + timedelta(minutes=15)

    def test_a_las_72_horas_se_detiene_y_lo_dice(self):
        desenlace, proximo = t.after_transient_failure(
            failures=9, first_failure_at=AHORA - timedelta(hours=72), now=AHORA
        )
        assert desenlace.state == STOPPED
        assert desenlace.reason == t.STOP_RETRIES_EXHAUSTED
        assert proximo is None


class TestElVeredicto:
    def test_aceptado(self):
        assert t.after_verdict("aceptado", sent_at=AHORA, polls=1, now=AHORA) == (t.Outcome(ACCEPTED), None)

    def test_rechazado_es_una_respuesta_final(self):
        assert t.after_verdict(" Rechazado ", sent_at=AHORA, polls=1, now=AHORA) == (t.Outcome(REJECTED), None)

    @pytest.mark.parametrize("estado", ["recibido", "procesando"])
    def test_en_proceso_se_vuelve_a_preguntar(self, estado):
        desenlace, proximo = t.after_verdict(estado, sent_at=AHORA - timedelta(minutes=1), polls=1, now=AHORA)
        assert desenlace == t.Outcome(SENT, None, estado)
        assert proximo == AHORA + timedelta(seconds=30)

    def test_en_proceso_tres_dias_es_para_una_persona(self):
        desenlace, proximo = t.after_verdict("procesando", sent_at=AHORA - timedelta(hours=72), polls=50, now=AHORA)
        assert (desenlace.state, desenlace.reason) == (STOPPED, t.STOP_NO_VERDICT)
        assert proximo is None

    @pytest.mark.parametrize("estado", ["error", "", "algo-nuevo"])
    def test_lo_que_no_se_entiende_se_detiene(self, estado):
        desenlace, _ = t.after_verdict(estado, sent_at=AHORA, polls=1, now=AHORA)
        assert (desenlace.state, desenlace.reason) == (STOPPED, t.STOP_HACIENDA_ERROR)


class TestLaContingencia:
    def test_sin_fallas_no_hay_contingencia(self):
        assert not t.in_contingency(last_transient_failure_at=None, last_success_at=None, now=AHORA)

    def test_la_ultima_falla_sin_exito_despues_es_contingencia(self):
        assert t.in_contingency(
            last_transient_failure_at=AHORA - timedelta(minutes=5), last_success_at=None, now=AHORA
        )
        assert t.in_contingency(
            last_transient_failure_at=AHORA - timedelta(minutes=5),
            last_success_at=AHORA - timedelta(hours=1),
            now=AHORA,
        )

    def test_un_exito_despues_de_la_falla_la_termina(self):
        assert not t.in_contingency(
            last_transient_failure_at=AHORA - timedelta(hours=1),
            last_success_at=AHORA - timedelta(minutes=5),
            now=AHORA,
        )

    def test_una_falla_de_ayer_ya_no_dice_nada(self):
        assert not t.in_contingency(
            last_transient_failure_at=AHORA - timedelta(hours=25), last_success_at=None, now=AHORA
        )


class TestLaAlarma:
    def test_los_tres_niveles(self):
        assert t.queue_alarm(None, AHORA) == t.ALARM_OK
        assert t.queue_alarm(AHORA - timedelta(hours=23), AHORA) == t.ALARM_OK
        assert t.queue_alarm(AHORA - timedelta(hours=24), AHORA) == t.ALARM_WARNING
        assert t.queue_alarm(AHORA - timedelta(days=5), AHORA) == t.ALARM_DANGER


class TestLaPuertaDeProduccion:
    def test_dice_cual_falta(self):
        assert t.production_gate({}) == ("01", "04", "03")
        assert t.production_gate({"01": 2, "04": 1}) == ("03",)
        assert t.production_gate({"01": 1, "04": 1, "03": 1, "02": 0}) == ()
        assert t.production_gate({"01": 0, "04": 1, "03": 1}) == ("01",)


MENSAJE = """<?xml version="1.0" encoding="utf-8"?>
<MensajeHacienda xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda">
  <Clave>50603102600310170293400100001040000000001159971093</Clave>
  <NombreEmisor>SWS</NombreEmisor>
  <Mensaje>{mensaje}</Mensaje>
  <DetalleMensaje>{detalle}</DetalleMensaje>
</MensajeHacienda>"""


class TestLoQueHaciendaContesta:
    def test_aceptado_y_rechazado(self):
        ok = t.parse_hacienda_message(MENSAJE.format(mensaje="1", detalle="Comprobante aceptado").encode())
        assert ok.accepted and ok.detalle == "Comprobante aceptado"
        no = t.parse_hacienda_message(MENSAJE.format(mensaje="3", detalle="Firma inválida").encode())
        assert not no.accepted and no.detalle == "Firma inválida"

    def test_lo_que_no_es_un_mensaje(self):
        with pytest.raises(InvalidHaciendaMessage):
            t.parse_hacienda_message(b"<esto no cierra")
        with pytest.raises(InvalidHaciendaMessage):
            t.parse_hacienda_message(MENSAJE.format(mensaje="7", detalle="").encode())

    def test_el_base64_de_la_respuesta(self):
        assert t.decode_response(None) is None
        assert t.decode_response("") is None
        assert t.decode_response(base64.b64encode(b"<x/>").decode()) == b"<x/>"
        with pytest.raises(InvalidHaciendaMessage):
            t.decode_response("no es base64!!")


FIRMADO = b"""<?xml version='1.0' encoding='utf-8'?>
<TiqueteElectronico xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico">
<Clave>5</Clave><FechaEmision>2026-10-03T00:13:39-06:00</FechaEmision>
<Emisor><Nombre>SWS</Nombre><Identificacion><Tipo>02</Tipo><Numero>3101702934</Numero></Identificacion></Emisor>
{receptor}
</TiqueteElectronico>"""


class TestElCuerpoDelEnvio:
    def test_con_y_sin_receptor(self):
        con = t.reception_payload(
            clave="5" * 50,
            fecha="2026-10-03T00:13:39-06:00",
            emisor=Party("02", "3101702934"),
            receptor=Party("01", "115670987"),
            signed_xml=b"<x/>",
        )
        assert con["emisor"] == {"tipoIdentificacion": "02", "numeroIdentificacion": "3101702934"}
        assert con["receptor"] == {"tipoIdentificacion": "01", "numeroIdentificacion": "115670987"}
        assert base64.b64decode(con["comprobanteXml"]) == b"<x/>"
        sin = t.reception_payload(
            clave="5" * 50, fecha="f", emisor=Party("02", "3"), receptor=None, signed_xml=b"<x/>"
        )
        assert "receptor" not in sin

    def test_las_partes_salen_del_xml(self):
        con = t.document_parties(
            FIRMADO.replace(
                b"{receptor}",
                b"<Receptor><Identificacion><Tipo>01</Tipo><Numero>115670987</Numero></Identificacion></Receptor>",
            )
        )
        assert con.fecha == "2026-10-03T00:13:39-06:00"
        assert con.emisor == Party("02", "3101702934")
        assert con.receptor == Party("01", "115670987")
        sin = t.document_parties(FIRMADO.replace(b"{receptor}", b""))
        assert sin.receptor is None

    def test_un_xml_sin_emisor_o_roto_no_se_manda(self):
        with pytest.raises(InvalidHaciendaMessage):
            t.document_parties(b"<roto")
        with pytest.raises(InvalidHaciendaMessage):
            t.document_parties(b"<TiqueteElectronico><Clave>5</Clave></TiqueteElectronico>")
