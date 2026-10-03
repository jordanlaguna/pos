"""
Quién le pide un token al IdP de Hacienda (T-612, RF-31).

**Es un puerto y no una llamada suelta por tres razones distintas**, y la
tercera es la que lo hace obligatorio:

1. Se prueba sin red. Los tres desenlaces de RF-31 se ejercitan con un doble;
   contra el IdP de verdad, «credenciales malas» se puede reproducir y «Hacienda
   caída» no.
2. Plan §7.2 deja abierta la ruta de emisión. Si la transmisión termina pasando
   por un proveedor autorizado, cambia el adaptador y no el caso de uso.
3. Y el motivo de hoy: el adaptador manda **la contraseña en claro** al IdP,
   porque Hacienda usa `grant_type=password`. Que eso viva detrás de una
   frontera declarada es lo que permite mirar en un solo archivo por dónde sale.

LOS TRES DESENLACES SON TRES Y NO DOS
-------------------------------------

`CredentialsRejected` e `IdpUnreachable` son excepciones distintas porque RF-31
lo exige y porque confundirlas hace daño de verdad: decirle a un cliente que su
contraseña está mal el día que Hacienda está en mantenimiento lo lleva a rotar
una credencial buena —y rotarla en ATV no es un clic—. El éxito, que es el
tercero, no necesita excepción: devuelve el token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from app.domain.hacienda import HaciendaEndpoints


class CredentialsRejected(Exception):
    """El IdP contestó, y dijo que no.

    Es un desenlace **normal** de la comprobación, no una avería: el usuario o
    la contraseña de ATV están mal, o la cuenta no está habilitada para ese
    ambiente. Quien lo recibe sabe qué hacer.
    """


class IdpUnreachable(Exception):
    """No se pudo preguntar: red, DNS, TLS, tiempo de espera, un 5xx.

    **No es `CredentialsRejected`.** Es RNF-4 aplicado acá: lo que necesita
    internet degrada con aviso, y el aviso tiene que decir que no se pudo
    comprobar — no que las credenciales no sirven.
    """


class HaciendaIdp(Protocol):
    """Cambia usuario y contraseña por un token de acceso."""

    def token(
        self, endpoints: HaciendaEndpoints, *, user: str, password: str
    ) -> str:
        """El `access_token`, o una de las dos excepciones de arriba.

        Recibe los `endpoints` en vez de deducirlos: quién es Hacienda lo decide
        `domain/hacienda.py` en un solo sitio (T-613), y un adaptador que lo
        resolviera por su cuenta sería el segundo.

        Devuelve el token aunque T-612 lo tire: F7 lo va a necesitar para
        transmitir, y un puerto que devolviera `bool` habría que cambiarlo
        entonces. Comprobar es pedir un token y no usarlo — que es justo lo que
        hace que la comprobación no emita nada.
        """
        ...


# --------------------------------------------------------------- la recepción
#
# La segunda mitad de hablar con Hacienda (T-709, T-708): entregarle el XML
# firmado y preguntarle qué decidió. Las excepciones distinguen lo que RN-41
# obliga a distinguir —lo que se reintenta de lo que detiene—, y el caso de uso
# no mira códigos HTTP: mira cuál de estas le llegó.


class ReceptionUnavailable(Exception):
    """No se pudo preguntar: red, tiempo de espera, un 5xx, un 429.

    Es transitorio y se reintenta con la cadencia del reenvío. Lleva el texto
    crudo de lo que pasó, para la bitácora del documento; nadie lo traduce.
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


class ReceptionRejected(Exception):
    """Hacienda contestó al envío que **no**, antes de procesarlo (400).

    Estructura, clave duplicada, firma que no abre: son fallas del documento o
    nuestras, y se detienen en el primer intento. `cause` es la cabecera
    `X-Error-Cause` o el cuerpo, tal cual: es lo que una persona va a leer para
    saber qué arreglar.
    """

    def __init__(self, cause: str = "") -> None:
        super().__init__(cause)
        self.cause = cause


class ReceptionForbidden(Exception):
    """403: las credenciales valen, pero no para este emisor. Se detiene.

    `cause` es lo que contestó el servidor, como en `ReceptionRejected`: un 403
    no siempre es de Hacienda. El Gateway que tiene delante contesta 403 a una
    ruta que no existe, y sin el texto la pantalla culpaba a las credenciales
    (2026-10-03).
    """

    def __init__(self, cause: str = "") -> None:
        super().__init__(cause)
        self.cause = cause


class TokenRejected(Exception):
    """401 en la recepción: el token venció entre pedirlo y usarlo.

    No es `CredentialsRejected` —el IdP sí lo dio— y no detiene nada: se pide
    otro y se vuelve a intentar una vez.
    """


class VerdictNotFound(Exception):
    """404 al consultar: Hacienda todavía no registra esa clave.

    Pasa en los segundos que siguen al 202, y la cadencia del veredicto ya lo
    contempla: se vuelve a preguntar más tarde.
    """


@dataclass(frozen=True)
class Verdict:
    """Lo que devuelve `GET /recepcion/{clave}` (README §8).

    `ind_estado` es la palabra de Hacienda tal cual —`recibido`, `procesando`,
    `aceptado`, `rechazado`, `error`—; qué significa cada una lo decide
    `domain/fe_transmission.py`. `respuesta_xml` es el `MensajeHacienda` ya
    decodificado del base64, o nada si todavía no lo hay.
    """

    ind_estado: str
    respuesta_xml: bytes | None = None


class HaciendaReception(Protocol):
    """La API de recepción de comprobantes, en los dos recursos que se usan."""

    def submit(
        self, endpoints: HaciendaEndpoints, *, token: str, payload: Mapping[str, object]
    ) -> None:
        """`POST /recepcion`. Vuelve sin más con el 202; si no, una de arriba.

        `payload` lo arma `domain/fe_transmission.reception_payload`: acá no se
        decide qué lleva el cuerpo, solo se manda.
        """
        ...

    def status(self, endpoints: HaciendaEndpoints, *, token: str, clave: str) -> Verdict:
        """`GET /recepcion/{clave}`, o `VerdictNotFound`, `TokenRejected`,
        `ReceptionUnavailable`."""
        ...
