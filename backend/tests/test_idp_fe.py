"""
El adaptador del IdP de Hacienda (T-612, RF-31).

**Contra un Keycloak de mentira levantado acá**, no contra Hacienda. Lo que hay
que probar de este archivo es la **traducción**: qué respuesta HTTP se convierte
en cuál de las dos excepciones, y eso es justo lo que no se puede provocar en
vivo —un 500 de Hacienda hay que esperar a que ocurra—. La consecuencia de
equivocarse es la que RF-31 nombra: un 500 leído como «credenciales malas» manda
a alguien a rotar en ATV una contraseña que estaba bien.

Los tres desenlaces desde arriba —lo que hace el caso de uso con cada uno— se
prueban sin red en `tests/application/test_credenciales_fe.py`.

COMPROBACIÓN EN VIVO, ANOTADA
------------------------------

Como en T-502 con el catálogo de CABYS: la batería **no** sale a internet, así
que queda escrito qué se hizo a mano contra Hacienda y qué se vio.

* **Hecha el 2026-09-19**, con una cuenta de ATV de pruebas real contra
  `idp.comprobanteselectronicos.go.cr`, realm `rut-stag`, cliente `api-stag`.
  Credenciales buenas devuelven `access_token` (1 523 bytes) en menos de dos
  segundos: los 15 s sobran con holgura.

* **Y destapó los dos defectos que esta batería no podía ver**, porque los dos
  viven en el trecho entre nosotros y Keycloak:

  1. **El IdP está detrás de Cloudflare**, que tiene baneada la firma por
     omisión de `urllib` y contesta *403 Error 1010,
     `browser_signature_banned`* sin que la petición llegue a Keycloak. La misma
     llamada, con las mismas credenciales, da 403 sin `User-Agent` y 200 con él.
  2. **La traducción decidía por el código de estado** —`exc.code in (400, 401,
     403)`— y el 403 de Cloudflare entraba como «credenciales rechazadas». Al
     otro lado de la pantalla eso se lee «Hacienda rechazó su contraseña», que
     es exactamente el error que RF-31 existe para no cometer; y el caso de uso,
     al recibir un rechazo, **borra la verificación anterior**, así que un
     bloqueo de Cloudflare tiraba una comprobación buena.

  Ahora decide el cuerpo: solo `{"error": "invalid_grant"}` es un rechazo. Lo
  que enseña es que un servidor de mentira que contesta lo que uno le dijo no
  prueba nada del intermediario que uno no sabía que existía.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from app.application.ports.transmission import CredentialsRejected, IdpUnreachable
from app.domain.hacienda import HaciendaEndpoints
from app.infrastructure.external.hacienda_idp import (
    ENV_PREFIX,
    USER_AGENT,
    HaciendaKeycloakIdp,
    endpoints_for,
    user_agent,
)

#: Lo que Cloudflare contesta cuando no le gusta la firma del cliente. Copiado
#: de lo que se recibió de verdad el 2026-09-19: es JSON válido y **no lleva
#: `error`**, que es justo lo que lo distingue de una negativa de Keycloak.
CLOUDFLARE_1010 = {
    "type": "https://developers.cloudflare.com/…/error-1010/",
    "title": "Error 1010: Access denied",
    "status": 403,
    "detail": "The site owner has blocked access based on your browser's signature.",
    "error_code": 1010,
    "error_name": "browser_signature_banned",
    "error_category": "access_denied",
}

BUENAS = ("cpf-01-1234-5678@x.cr", "la-correcta")


class _Keycloak(BaseHTTPRequestHandler):
    """Contesta lo que diga `servidor.guion`."""

    def do_POST(self):  # noqa: N802 — lo exige BaseHTTPRequestHandler
        largo = int(self.headers.get("Content-Length") or 0)
        self.server.recibido = parse_qs(self.rfile.read(largo).decode("utf-8"))
        # Las cabeceras también: el `User-Agent` es parte del contrato con
        # Hacienda desde que se descubrió el Cloudflare de por medio.
        self.server.cabeceras = dict(self.headers)

        estado, cuerpo = self.server.guion
        crudo = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else b"no es JSON"
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def log_message(self, *a):  # pragma: no cover — silencia el servidor
        pass


@pytest.fixture
def keycloak():
    servidor = HTTPServer(("127.0.0.1", 0), _Keycloak)
    servidor.guion = (200, {"access_token": "tok-abc"})
    servidor.recibido = None
    servidor.cabeceras = {}
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


def endpoints_de(servidor) -> HaciendaEndpoints:
    puerto = servidor.server_address[1]
    return HaciendaEndpoints(
        api_url=f"http://127.0.0.1:{puerto}/api/",
        idp_url=f"http://127.0.0.1:{puerto}/token",
        client_id="api-de-prueba",
        realm="realm-de-prueba",
    )


class TestSirven:
    def test_devuelve_el_token(self, keycloak):
        token = HaciendaKeycloakIdp().token(
            endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
        )
        assert token == "tok-abc"

    def test_manda_lo_que_Keycloak_espera(self, keycloak):
        HaciendaKeycloakIdp().token(
            endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
        )
        assert keycloak.recibido == {
            "client_id": ["api-de-prueba"],
            "grant_type": ["password"],
            "username": [BUENAS[0]],
            "password": [BUENAS[1]],
        }

    def test_el_client_id_sale_de_los_endpoints_y_no_del_adaptador(self, keycloak):
        # T-613: quién es Hacienda se decide en un solo sitio. Si el adaptador
        # lo escribiera, cambiarlo en el dominio no cambiaría nada.
        propios = endpoints_de(keycloak)
        HaciendaKeycloakIdp().token(
            HaciendaEndpoints(
                api_url=propios.api_url,
                idp_url=propios.idp_url,
                client_id="otro-cliente",
                realm=propios.realm,
            ),
            user=BUENAS[0],
            password=BUENAS[1],
        )
        assert keycloak.recibido["client_id"] == ["otro-cliente"]


class TestSePresenta:
    """El `User-Agent`, que hace falta para que la petición llegue.

    Comprobado en vivo: sin él, el Cloudflare que Hacienda tiene delante
    responde 403 y Keycloak no se entera de nada.
    """

    def test_manda_un_User_Agent(self, keycloak):
        HaciendaKeycloakIdp().token(
            endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
        )
        assert keycloak.cabeceras.get("User-Agent") == USER_AGENT

    def test_y_no_el_de_urllib_que_esta_baneado(self, keycloak):
        HaciendaKeycloakIdp().token(
            endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
        )
        assert "Python-urllib" not in keycloak.cabeceras.get("User-Agent", "")

    def test_el_despliegue_lo_puede_cambiar(self, keycloak, monkeypatch):
        # El día que Cloudflare banee también esta firma, la salida no puede ser
        # esperar una versión. Es la misma mitigación que la de las URLs.
        monkeypatch.setenv(f"{ENV_PREFIX}USER_AGENT", "OtroPOS/2.0")
        HaciendaKeycloakIdp().token(
            endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
        )
        assert keycloak.cabeceras["User-Agent"] == "OtroPOS/2.0"

    @pytest.mark.parametrize("vacia", ["", "   "])
    def test_una_variable_vacia_no_lo_borra(self, vacia, monkeypatch):
        # Lo normal en un `.env` copiado del ejemplo. Dejarla ganar devolvería
        # el 403 de Cloudflare, con el diagnóstico más difícil de todos: el que
        # aparece solo en producción.
        monkeypatch.setenv(f"{ENV_PREFIX}USER_AGENT", vacia)
        assert user_agent() == USER_AGENT


class TestNoSirven:
    @pytest.mark.parametrize("estado", [400, 401, 403])
    def test_el_IdP_dice_que_no(self, keycloak, estado):
        """Lo que manda es el cuerpo, no el código.

        Keycloak usa el 400 para `invalid_grant` en unas versiones y el 401 en
        otras, así que el código no distingue nada por sí solo. Lo que sí es
        siempre igual es el `error` del cuerpo.
        """
        keycloak.guion = (estado, {"error": "invalid_grant"})
        with pytest.raises(CredentialsRejected):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password="mal"
            )

    def test_el_texto_de_Keycloak_no_se_propaga(self, keycloak):
        # Viene en inglés (RN-30) y además distingue «usuario desconocido» de
        # «contraseña mala», que es lo que no conviene contarle a quien esté
        # probando cuentas.
        keycloak.guion = (
            401,
            {"error": "invalid_grant", "error_description": "Invalid user credentials"},
        )
        with pytest.raises(CredentialsRejected) as e:
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password="mal"
            )
        assert "Invalid user credentials" not in str(e.value)


class TestNoSePudoComprobar:
    """El tercer desenlace, que es el que no puede confundirse con el segundo."""

    @pytest.mark.parametrize("estado", [500, 502, 503, 504])
    def test_una_averia_de_Hacienda_no_es_una_contrasena_mala(self, keycloak, estado):
        keycloak.guion = (estado, {"error": "internal"})
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )

    def test_el_403_de_Cloudflare_tampoco(self, keycloak):
        """La regresión de lo que pasó de verdad el 2026-09-19.

        Con credenciales **buenas**, el Cloudflare que Hacienda tiene delante
        respondía 403 y el adaptador lo leía como «las rechazaron». Al otro lado
        de la pantalla eso se lee «Hacienda rechazó su contraseña», y quien lo
        lee se va a ATV a cambiar una que estaba perfecta. Encima el caso de uso
        borra la verificación anterior al recibir un rechazo, así que un bloqueo
        de la red tiraba una comprobación buena.

        Es JSON válido y sin `error`, que es lo que hay que saber distinguir.
        """
        keycloak.guion = (403, CLOUDFLARE_1010)
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )

    @pytest.mark.parametrize(
        "error", ["invalid_client", "unauthorized_client", "unsupported_grant_type"]
    )
    def test_un_error_de_configuracion_nuestra_no_es_una_contrasena_mala(
        self, keycloak, error
    ):
        """Los tres son culpa nuestra: un `client_id` mal escrito, un realm que
        no es. Mandar a alguien a rotar su contraseña en ATV por eso es la misma
        falta que el 403 de Cloudflare, con otra cara.
        """
        keycloak.guion = (400, {"error": error})
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )

    def test_un_rechazo_sin_cuerpo_que_leer(self, keycloak):
        # Ante la duda, «no se pudo comprobar»: equivocarse hacia ese lado cuesta
        # reintentar, y hacia el otro, que alguien cambie una credencial buena.
        keycloak.guion = (401, None)
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )

    def test_nadie_escuchando(self, keycloak):
        puerto = keycloak.server_address[1]
        keycloak.shutdown()
        keycloak.server_close()
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                HaciendaEndpoints(
                    api_url="http://127.0.0.1:1/",
                    idp_url=f"http://127.0.0.1:{puerto}/token",
                    client_id="x",
                    realm="y",
                ),
                user=BUENAS[0],
                password=BUENAS[1],
            )

    def test_un_200_que_no_es_JSON(self, keycloak):
        keycloak.guion = (200, None)
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )

    def test_un_200_sin_token_es_un_intermediario_y_no_una_negativa(self, keycloak):
        """Un portal cautivo, un proxy que contesta con su propia página.

        Reportarlo como «no sirven» sería acusar a las credenciales de algo que
        hizo la red.
        """
        keycloak.guion = (200, {"mensaje": "hola"})
        with pytest.raises(IdpUnreachable):
            HaciendaKeycloakIdp().token(
                endpoints_de(keycloak), user=BUENAS[0], password=BUENAS[1]
            )


class TestDeDondeSalenLosEndpoints:
    def test_sin_variables_son_los_publicados(self, monkeypatch):
        from app.domain.hacienda import PRODUCTION, endpoints

        for campo in ("API_URL", "IDP_URL", "CLIENT_ID", "REALM"):
            monkeypatch.delenv(f"{ENV_PREFIX}{campo}", raising=False)
        assert endpoints_for(PRODUCTION) == endpoints(PRODUCTION)

    def test_una_variable_los_mueve(self, monkeypatch):
        from app.domain.hacienda import PRODUCTION

        monkeypatch.setenv(f"{ENV_PREFIX}IDP_URL", "https://tribu.example/token")
        assert endpoints_for(PRODUCTION).idp_url == "https://tribu.example/token"

    def test_una_variable_vacia_no_cuenta(self, monkeypatch):
        """Lo normal en un `.env` copiado del ejemplo.

        Dejarla pisar el valor bueno convertiría el arranque en «no encuentra a
        Hacienda» sin ninguna pista de por qué.
        """
        from app.domain.hacienda import PRODUCTION, endpoints

        monkeypatch.setenv(f"{ENV_PREFIX}IDP_URL", "   ")
        assert endpoints_for(PRODUCTION) == endpoints(PRODUCTION)
