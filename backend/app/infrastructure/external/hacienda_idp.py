"""
El IdP de Hacienda, por HTTP (T-612, RF-31).

Hacienda autentica con Keycloak y `grant_type=password`: se manda el usuario de
ATV y su contraseña al endpoint del token y vuelve un `access_token`. No hay
forma de comprobar unas credenciales sin pedir un token, y por eso **comprobar
es pedir uno y tirarlo** — lo que no hace es emitir ningún documento, que es lo
que RF-31 pide.

Se usa `urllib` y no un cliente HTTP nuevo, igual que el adaptador de CABYS y el
de Vault: es un POST con tiempo de espera, y el proyecto acota sus dependencias
a propósito —fue `passlib` lo que rompió una instalación entera—.

**Acá no está escrito quién es Hacienda.** Las URLs, el realm y el `client_id`
llegan como parámetro desde `domain/hacienda.py`, que es el único sitio donde se
nombran (T-613); hay una prueba que tumba `pytest` si aparecen en cualquier otro
archivo. Lo que sí vive acá es de dónde salen los *overrides* del despliegue:
leer variables de entorno es infraestructura, y por eso la derivación pura se
puede probar sin tocar el entorno.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from app.application.ports.transmission import CredentialsRejected, IdpUnreachable
from app.domain.hacienda import OVERRIDABLE, HaciendaEndpoints, endpoints

#: Más largo que el de CABYS y más corto que el de Vault. Quien espera esto es
#: una persona que acaba de tocar «probar la conexión», así que tiene que
#: contestar; pero al otro lado hay un Keycloak ajeno, y cinco segundos darían
#: «no se pudo comprobar» las mañanas en que Hacienda va lenta — que es
#: exactamente el desenlace que no hay que dar de más.
TIMEOUT_SECONDS = 15

#: Prefijo de las variables que un despliegue puede usar para mover a Hacienda
#: de sitio sin esperar una versión: `FE_HACIENDA_API_URL`, `FE_HACIENDA_REALM`…
#: La lista de qué se puede cambiar la manda el dominio (`OVERRIDABLE`), no este
#: módulo: una segunda lista acá sería la forma de que un campo nuevo quedara
#: sin poder configurarse y nadie lo notara.
ENV_PREFIX = "FE_HACIENDA_"

#: Con quién se presenta el adaptador.
#:
#: **Hace falta.** El IdP de Hacienda está detrás de Cloudflare, que tiene
#: baneada la firma por omisión de `urllib` —`Python-urllib/3.x`— y contesta
#: **403 con «Error 1010: browser_signature_banned»** sin que la petición llegue
#: nunca a Keycloak. Comprobado en vivo el 2026-09-19: la misma petición, con
#: credenciales buenas, da 403 sin esta cabecera y 200 con ella.
#:
#: Se puede mover desde el despliegue por lo mismo que las URLs: el día que
#: Cloudflare banee también esta firma, la salida no puede ser esperar una
#: versión.
USER_AGENT = "VentaSys/1.0 (+facturacion electronica)"

#: El único `error` que significa «el usuario o la contraseña no sirven».
#:
#: **Se mira el cuerpo y no el código**, y esa es la lección cara de este
#: módulo. Antes la decisión era `exc.code in (400, 401, 403)`, y un 403 puede
#: venir del Keycloak de Hacienda o del Cloudflare que tiene delante: significan
#: cosas opuestas y se confundían. El resultado fue el error que RF-31 existe
#: para no cometer —«Hacienda rechazó su contraseña» cuando Hacienda ni se había
#: enterado—, y encima el caso de uso borra la verificación anterior al recibir
#: un rechazo, así que un bloqueo de Cloudflare tiraba una comprobación buena.
#:
#: Los demás `error` de Keycloak tampoco entran: `invalid_client` y
#: `unsupported_grant_type` son configuración **nuestra**, y mandar a alguien a
#: rotar su contraseña en ATV por un `client_id` mal escrito es la misma falta.
#:
#: Ante la duda se elige «no se pudo comprobar». Equivocarse hacia ese lado
#: cuesta reintentar; hacia el otro, que alguien cambie una credencial que
#: estaba bien.
_RECHAZO = "invalid_grant"


def user_agent() -> str:
    """El de arriba, o el que diga el despliegue.

    Se lee **al llamar** y no al importar, por lo mismo que `endpoints_for`: una
    constante resuelta en el arranque deja el valor del proceso congelado y no
    hay forma de moverlo sin reiniciar —ni de probarlo—.
    """
    return os.getenv(f"{ENV_PREFIX}USER_AGENT", "").strip() or USER_AGENT


def endpoints_for(environment: str) -> HaciendaEndpoints:
    """Dónde vive Hacienda para ese ambiente, con lo que diga el entorno.

    Los valores publicados son los de fábrica y el `.env` solo los pisa si trae
    algo: una variable declarada y vacía —lo normal en un `.env` copiado del
    ejemplo— no cuenta, y de eso se encarga el dominio.
    """
    return endpoints(
        environment,
        {campo: os.getenv(f"{ENV_PREFIX}{campo.upper()}", "") for campo in OVERRIDABLE},
    )


class HaciendaKeycloakIdp:
    """Cumple `HaciendaIdp` contra el Keycloak de Hacienda."""

    def token(
        self, endpoints: HaciendaEndpoints, *, user: str, password: str
    ) -> str:
        cuerpo = urllib.parse.urlencode(
            {
                "client_id": endpoints.client_id,
                "grant_type": "password",
                "username": user,
                "password": password,
            }
        ).encode("utf-8")

        peticion = urllib.request.Request(
            endpoints.idp_url,
            data=cuerpo,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                # Sin esto, Cloudflare no deja pasar la petición. Ver `USER_AGENT`.
                "User-Agent": user_agent(),
            },
        )

        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT_SECONDS) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if _lo_dijo_keycloak(exc):
                # El texto de Keycloak NO se propaga: viene en inglés (RN-30) y
                # además distingue «usuario desconocido» de «contraseña mala»,
                # que es justo lo que no conviene contarle a quien esté
                # probando cuentas. Para quien opera, las dos son la misma
                # tarea: volver a escribir las credenciales.
                raise CredentialsRejected(f"el IdP respondió {exc.code}") from exc
            # Todo lo demás es «no se pudo comprobar», no «no sirven»: un 500 de
            # Hacienda, un 403 del Cloudflare que tiene delante, un `invalid_client`
            # que es culpa nuestra. Es la distinción que pide RF-31 y la que evita
            # que alguien rote en ATV una credencial que está bien.
            raise IdpUnreachable(f"el IdP respondió {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001 — red, DNS, TLS, JSON partido
            raise IdpUnreachable(str(exc)) from exc

        token = datos.get("access_token") if isinstance(datos, dict) else None
        if not token:
            # Un 200 sin token es un intermediario —un portal cautivo, un proxy
            # que devuelve HTML— y no una negativa de Hacienda. Va como
            # inalcanzable, que es lo que de verdad pasó.
            raise IdpUnreachable("el IdP contestó 200 sin access_token")
        return str(token)


def _lo_dijo_keycloak(exc: urllib.error.HTTPError) -> bool:
    """¿La negativa la escribió Keycloak, y dice que las credenciales no sirven?

    Es una pregunta sobre el **cuerpo**. Keycloak contesta un JSON con `error`;
    Cloudflare, una página o un JSON con otra forma. Sin el `error` correcto no
    hay manera de afirmar que Hacienda miró las credenciales, y afirmarlo de más
    es lo que manda a alguien a rotar una contraseña buena.

    Un cuerpo ilegible —HTML, vacío, cortado— responde que no, que es el lado
    seguro: «no se pudo comprobar».
    """
    try:
        cuerpo = json.loads(exc.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — no es JSON, o no hay cuerpo que leer
        return False
    return isinstance(cuerpo, dict) and cuerpo.get("error") == _RECHAZO


def hacienda_idp() -> HaciendaKeycloakIdp:
    return HaciendaKeycloakIdp()
