"""
La API de recepción de Hacienda, por HTTP (T-708, T-709, README §7 y §8).

Dos recursos: `POST /recepcion` entrega el XML firmado y `GET /recepcion/{clave}`
pregunta qué decidió. Se les habla con `urllib`, como al IdP y a Vault: son dos
peticiones con tiempo de espera, y el proyecto acota sus dependencias a
propósito.

**Acá no está escrito quién es Hacienda.** La URL base llega en `endpoints`
desde `domain/hacienda.py`, el único sitio que la nombra (T-613).

LO QUE CADA CÓDIGO QUIERE DECIR, Y POR QUÉ IMPORTA
--------------------------------------------------

El caso de uso no mira códigos HTTP: mira cuál excepción le llegó, y RN-41
distingue lo que se reintenta de lo que detiene. Por eso la traducción vive acá
y en un solo sitio:

| Hacienda dice                 | Es                        | Y el recorrido…       |
|-------------------------------|---------------------------|-----------------------|
| 202 al enviar                 | recibido, no aceptado     | pasa a consultar      |
| 200 al consultar              | `ind-estado` y respuesta  | decide con el dominio |
| 400                           | el documento está mal     | se detiene y lo dice  |
| 401                           | el token venció           | pide otro, una vez    |
| 403                           | credenciales sin permiso  | se detiene y lo dice  |
| 404 al consultar              | todavía no la registra    | vuelve a preguntar    |
| 429, 5xx, red, tiempo         | Hacienda no está          | espera y reintenta    |

El 400 trae el porqué en la cabecera `X-Error-Cause`; si no viene, el cuerpo.
Se guarda tal cual: es lo que una persona va a leer para saber qué arreglar, y
no hay catálogo de códigos que traducir (README §11). El 403 también: delante
de Hacienda hay un Gateway de AWS que contesta 403 a una ruta que no existe
(`IncompleteSignatureException`), y sin el cuerpo eso se ve igual que unas
credenciales sin permiso.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Mapping

from app.application.ports.transmission import (
    ReceptionForbidden,
    ReceptionRejected,
    ReceptionUnavailable,
    TokenRejected,
    Verdict,
    VerdictNotFound,
)
from app.domain.fe_transmission import decode_response
from app.domain.hacienda import HaciendaEndpoints

from .hacienda_idp import user_agent

#: Más que el IdP: el envío lleva el XML y Hacienda lo valida en recepción.
#: Nadie espera esto con el cliente enfrente —corre en la cola—, así que puede
#: ser generoso sin costarle a nadie.
TIMEOUT_SECONDS = 30

#: Lo que el README §7 llama «headers obligatorios».
_CABECERAS = {"Content-Type": "application/json", "Accept": "application/json"}


def _url(endpoints: HaciendaEndpoints, recurso: str) -> str:
    base = endpoints.api_url if endpoints.api_url.endswith("/") else endpoints.api_url + "/"
    return urllib.parse.urljoin(base, recurso)


def _causa(exc: urllib.error.HTTPError) -> str:
    """La cabecera `X-Error-Cause`, o el cuerpo, o el código: lo que haya."""
    cabecera = exc.headers.get("X-Error-Cause") if exc.headers else None
    if cabecera:
        return cabecera.strip()
    try:
        cuerpo = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 — leer el cuerpo de un error no puede fallar peor
        cuerpo = ""
    return cuerpo or f"HTTP {exc.code}"


class HaciendaHttpReception:
    """Cumple `HaciendaReception` contra la API REST de Hacienda."""

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def submit(
        self, endpoints: HaciendaEndpoints, *, token: str, payload: Mapping[str, object]
    ) -> None:
        peticion = urllib.request.Request(
            _url(endpoints, "recepcion"),
            data=json.dumps(dict(payload)).encode("utf-8"),
            method="POST",
            headers={
                **_CABECERAS,
                "Authorization": f"Bearer {token}",
                "User-Agent": user_agent(),
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self._timeout) as respuesta:
                codigo = respuesta.status
        except urllib.error.HTTPError as exc:
            self._traducir(exc)
            raise ReceptionUnavailable(_causa(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ReceptionUnavailable(str(exc)) from exc
        # 202 es lo esperado; un 200 también se acepta: Hacienda no promete
        # distinguirlos y los dos quieren decir «lo tengo».
        if codigo not in (200, 202):
            raise ReceptionUnavailable(f"HTTP {codigo}")

    def status(self, endpoints: HaciendaEndpoints, *, token: str, clave: str) -> Verdict:
        peticion = urllib.request.Request(
            _url(endpoints, f"recepcion/{urllib.parse.quote(clave)}"),
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": user_agent(),
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self._timeout) as respuesta:
                crudo = respuesta.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise VerdictNotFound() from exc
            self._traducir(exc)
            raise ReceptionUnavailable(_causa(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ReceptionUnavailable(str(exc)) from exc

        try:
            datos = json.loads(crudo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReceptionUnavailable("respuesta ilegible") from exc
        if not isinstance(datos, dict):
            raise ReceptionUnavailable("respuesta ilegible")
        estado = str(datos.get("ind-estado") or "").strip()
        try:
            respuesta_xml = decode_response(datos.get("respuesta-xml"))
        except Exception as exc:  # noqa: BLE001 — un base64 roto es Hacienda hablando mal
            raise ReceptionUnavailable("respuesta-xml ilegible") from exc
        return Verdict(ind_estado=estado, respuesta_xml=respuesta_xml)

    @staticmethod
    def _traducir(exc: urllib.error.HTTPError) -> None:
        """Lo que detiene o pide otro token. Lo demás lo decide quien llama."""
        if exc.code == 400:
            raise ReceptionRejected(_causa(exc)) from exc
        if exc.code == 401:
            raise TokenRejected() from exc
        if exc.code == 403:
            raise ReceptionForbidden(_causa(exc)) from exc
