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

from typing import Protocol

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
