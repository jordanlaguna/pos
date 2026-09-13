"""
En qué estado están las credenciales de una compañía (T-604, T-606, T-610).

Son dos cosas distintas que hacen falta las dos, y el módulo existe para que esa
frase viva en un solo sitio: **el certificado firma y las credenciales de ATV
transmiten**, y con una sola no se emite. Una pantalla que dedujera eso por su
cuenta sería una segunda definición de «listo».

**El vencimiento se mide contra el reloj del puerto y con la hora puesta.** La
columna es `DATETIME` y no `DATE` a propósito (plan §7.1): el `notAfter` de un
certificado tiene hora, y uno que vence a las 10:00 no sirve a las 11:00.
Redondear a días haría que el sistema dijera que sirve durante catorce horas en
que no sirve — y esas catorce horas son un día de facturación entero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from .hacienda import check_environment

#: Cuánto antes se avisa. Un mes es lo que tarda ATV en emitir uno nuevo más el
#: tiempo de que alguien en el negocio se entere y actúe.
WARNING_DAYS: Final = 30

#: Los cuatro estados de un certificado, de peor a mejor.
MISSING: Final = "missing"
EXPIRED: Final = "expired"
EXPIRING: Final = "expiring"
VALID: Final = "valid"

CERTIFICATE_STATES: Final = (MISSING, EXPIRED, EXPIRING, VALID)


def days_left(expires_at: datetime | None, now: datetime) -> int | None:
    """Días enteros hasta el vencimiento. Negativo si ya pasó, `None` si no hay.

    Se trunca hacia abajo con signo —lo que hace `timedelta.days`— así que un
    certificado que vence en veintitrés horas devuelve **0** y no 1. Es lo
    correcto: lo que queda no alcanza para un día más de trabajo.
    """
    if expires_at is None:
        return None
    return (expires_at - now).days


def certificate_status(expires_at: datetime | None, now: datetime) -> str:
    """`missing`, `expired`, `expiring` o `valid`."""
    if expires_at is None:
        return MISSING
    if expires_at <= now:
        return EXPIRED
    return EXPIRING if days_left(expires_at, now) <= WARNING_DAYS else VALID


@dataclass(frozen=True)
class EnvironmentStatus:
    """Lo que la pantalla muestra de un ambiente, ya decidido acá.

    **No lleva el archivo, ni el PIN, ni la contraseña**, y no es un descuido:
    no existe ningún camino que los devuelva (RF-23, RN-16). El PIN además ya no
    se guarda en ninguna parte desde que la llave vive en Vault.
    """

    environment: str
    certificate_name: str | None
    expires_at: datetime | None
    days_left: int | None
    certificate_status: str
    uploaded_at: datetime | None
    #: Identificador, no secreto: se muestra. Sin verlo, nadie puede comprobar
    #: que escribió el que era (RN-16).
    atv_user: str | None
    atv_configured: bool
    atv_verified_at: datetime | None

    @property
    def certificate_configured(self) -> bool:
        return self.certificate_status != MISSING

    @property
    def ready(self) -> bool:
        """Si con esto se puede emitir.

        Las tres condiciones juntas, y la tercera es la que se olvida: un
        certificado **vencido** está configurado y no sirve. Una pantalla que
        mostrara «certificado ✓ · ATV ✓» sin mirar la fecha diría que todo está
        listo el día que dejó de estarlo.
        """
        return (
            self.certificate_status in (VALID, EXPIRING)
            and self.atv_configured
        )


def environment_status(
    *,
    environment: str,
    now: datetime,
    certificate_name: str | None = None,
    expires_at: datetime | None = None,
    uploaded_at: datetime | None = None,
    atv_user: str | None = None,
    atv_configured: bool = False,
    atv_verified_at: datetime | None = None,
) -> EnvironmentStatus:
    """El estado de un ambiente, con o sin fila en la base.

    **Sin fila también hay estado**, y por eso los argumentos tienen omisión: un
    ambiente que nunca se configuró existe igual y la pantalla tiene que poder
    decir qué le falta. Devolver `None` obligaría a quien llama a inventar el
    caso vacío, que es donde se pierde la mitad de RF-30.
    """
    return EnvironmentStatus(
        environment=check_environment(environment),
        certificate_name=certificate_name,
        expires_at=expires_at,
        days_left=days_left(expires_at, now),
        certificate_status=certificate_status(expires_at, now),
        uploaded_at=uploaded_at,
        atv_user=atv_user,
        atv_configured=atv_configured,
        atv_verified_at=atv_verified_at,
    )
