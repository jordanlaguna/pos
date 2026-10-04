"""
El cliente de la recepción de Hacienda, contra un servidor de verdad en la
máquina (T-708, T-709).

No se habla con Hacienda: se levanta la Hacienda de mentira de
`tests/stub_hacienda.py` en un hilo y se comprueba que cada código HTTP se
traduzca a la excepción que RN-41 necesita —lo que se reintenta y lo que
detiene—, que el cuerpo del envío sea el del README §7 y que la consulta
devuelva el veredicto con su respuesta ya decodificada.
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from app.application.ports.transmission import (
    ReceptionForbidden,
    ReceptionRejected,
    ReceptionUnavailable,
    TokenRejected,
    VerdictNotFound,
)
from app.domain.hacienda import HaciendaEndpoints
from app.infrastructure.external.hacienda_reception import HaciendaHttpReception

from .stub_hacienda import Hacienda, recibidas

pytestmark = pytest.mark.integration

CLAVE = "50603102600310170293400100001040000000001159971093"


@pytest.fixture(scope="module")
def hacienda():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Hacienda)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    puerto = servidor.server_address[1]
    yield HaciendaEndpoints(
        api_url=f"http://127.0.0.1:{puerto}/recepcion/v1/",
        idp_url=f"http://127.0.0.1:{puerto}/token",
        client_id="api-stag",
        realm="rut-stag",
    )
    servidor.shutdown()


@pytest.fixture(autouse=True)
def limpia():
    recibidas.clear()
    yield
    recibidas.clear()


def cuerpo(clave: str = CLAVE) -> dict:
    return {
        "clave": clave,
        "fecha": "2026-10-03T00:13:39-06:00",
        "emisor": {"tipoIdentificacion": "02", "numeroIdentificacion": "3101702934"},
        "comprobanteXml": base64.b64encode(b"<TiqueteElectronico/>").decode("ascii"),
    }


class TestElEnvio:
    def test_el_202_vuelve_sin_mas_y_hacienda_lo_tiene(self, hacienda):
        HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo())
        assert CLAVE in recibidas
        assert recibidas[CLAVE]["emisor"]["numeroIdentificacion"] == "3101702934"

    def test_un_400_trae_la_causa_de_la_cabecera(self, hacienda):
        with pytest.raises(ReceptionRejected) as e:
            HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo(CLAVE[:-2] + "00"))
        assert e.value.cause == "El XML no cumple con la estructura"

    def test_la_clave_repetida_es_un_400(self, hacienda):
        HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo())
        with pytest.raises(ReceptionRejected) as e:
            HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo())
        assert e.value.cause == "clave duplicada"

    def test_sin_token_es_un_401(self, hacienda):
        with pytest.raises(TokenRejected):
            HaciendaHttpReception().submit(hacienda, token="", payload=cuerpo())

    def test_una_hacienda_que_no_esta_es_transitorio(self):
        lejos = HaciendaEndpoints(
            api_url="http://127.0.0.1:9/recepcion/v1/", idp_url="x", client_id="c", realm="r"
        )
        with pytest.raises(ReceptionUnavailable):
            HaciendaHttpReception(timeout=2).submit(lejos, token="t", payload=cuerpo())


class TestLaConsulta:
    def test_lo_que_no_mando_es_un_404(self, hacienda):
        with pytest.raises(VerdictNotFound):
            HaciendaHttpReception().status(hacienda, token="t", clave=CLAVE)

    def test_aceptado_con_su_respuesta_decodificada(self, hacienda):
        HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo())
        veredicto = HaciendaHttpReception().status(hacienda, token="t", clave=CLAVE)
        assert veredicto.ind_estado == "aceptado"
        assert veredicto.respuesta_xml is not None
        assert b"<Mensaje>1</Mensaje>" in veredicto.respuesta_xml
        assert CLAVE.encode() in veredicto.respuesta_xml

    def test_rechazado(self, hacienda):
        clave = CLAVE[:-2] + "99"
        HaciendaHttpReception().submit(hacienda, token="t", payload=cuerpo(clave))
        veredicto = HaciendaHttpReception().status(hacienda, token="t", clave=clave)
        assert veredicto.ind_estado == "rechazado"
        assert b"<Mensaje>3</Mensaje>" in (veredicto.respuesta_xml or b"")

    def test_sin_token_es_un_401(self, hacienda):
        with pytest.raises(TokenRejected):
            HaciendaHttpReception().status(hacienda, token="", clave=CLAVE)


class TestLoQueNoEsHacienda:
    """Las traducciones que el stub no produce, con un servidor mínimo propio."""

    @staticmethod
    def _servidor(codigo: int, cuerpo: bytes = b"{}", cabeceras: dict | None = None):
        from http.server import BaseHTTPRequestHandler

        class Fijo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self):
                # Leer el cuerpo antes de contestar. Sin esto, a un POST se le
                # contestaba y se cerraba con su cuerpo sin leer, y a veces el
                # cliente recibía la conexión cortada en vez del código: la
                # prueba del 400 fallaba una de cada tantas corridas.
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(codigo)
                for k, v in (cabeceras or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            do_GET = _responder
            do_POST = _responder

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Fijo)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        puerto = servidor.server_address[1]
        return servidor, HaciendaEndpoints(
            api_url=f"http://127.0.0.1:{puerto}/recepcion/v1", idp_url="x", client_id="c", realm="r"
        )

    def test_un_403_se_detiene_con_el_cuerpo(self):
        # Lo que contesta el Gateway de AWS a una ruta que no existe: sin el
        # cuerpo se confunde con unas credenciales sin permiso.
        gateway = b'{"message":"Invalid key=value pair (missing equal-sign) in Authorization header"}'
        servidor, destino = self._servidor(403, gateway)
        try:
            with pytest.raises(ReceptionForbidden) as envio:
                HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
            assert "Invalid key=value pair" in envio.value.cause
            with pytest.raises(ReceptionForbidden):
                HaciendaHttpReception().status(destino, token="t", clave=CLAVE)
        finally:
            servidor.shutdown()

    def test_un_500_y_un_429_se_reintentan(self):
        for codigo in (500, 429):
            servidor, destino = self._servidor(codigo, b"mantenimiento")
            try:
                with pytest.raises(ReceptionUnavailable) as e:
                    HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
                assert e.value.detail == "mantenimiento"
                with pytest.raises(ReceptionUnavailable):
                    HaciendaHttpReception().status(destino, token="t", clave=CLAVE)
            finally:
                servidor.shutdown()

    def test_un_400_sin_cabecera_usa_el_cuerpo(self):
        servidor, destino = self._servidor(400, b"firma invalida")
        try:
            with pytest.raises(ReceptionRejected) as e:
                HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
            assert e.value.cause == "firma invalida"
        finally:
            servidor.shutdown()

    def test_un_400_sin_nada_dice_el_codigo(self):
        servidor, destino = self._servidor(400, b"")
        try:
            with pytest.raises(ReceptionRejected) as e:
                HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
            assert e.value.cause == "HTTP 400"
        finally:
            servidor.shutdown()

    def test_un_200_al_enviar_tambien_vale(self):
        servidor, destino = self._servidor(200)
        try:
            HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
        finally:
            servidor.shutdown()

    def test_un_204_al_enviar_no_es_un_recibido(self):
        servidor, destino = self._servidor(204, b"")
        try:
            with pytest.raises(ReceptionUnavailable):
                HaciendaHttpReception().submit(destino, token="t", payload=cuerpo())
        finally:
            servidor.shutdown()

    def test_una_consulta_que_no_es_json(self):
        servidor, destino = self._servidor(200, b"<html>mantenimiento</html>")
        try:
            with pytest.raises(ReceptionUnavailable):
                HaciendaHttpReception().status(destino, token="t", clave=CLAVE)
        finally:
            servidor.shutdown()

    def test_una_consulta_que_es_una_lista(self):
        servidor, destino = self._servidor(200, b"[]")
        try:
            with pytest.raises(ReceptionUnavailable):
                HaciendaHttpReception().status(destino, token="t", clave=CLAVE)
        finally:
            servidor.shutdown()

    def test_una_respuesta_xml_que_no_es_base64(self):
        cuerpo_malo = json.dumps({"ind-estado": "aceptado", "respuesta-xml": "no*es*base64"}).encode()
        servidor, destino = self._servidor(200, cuerpo_malo)
        try:
            with pytest.raises(ReceptionUnavailable):
                HaciendaHttpReception().status(destino, token="t", clave=CLAVE)
        finally:
            servidor.shutdown()
