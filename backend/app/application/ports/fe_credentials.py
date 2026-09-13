"""
Las credenciales de Hacienda, dichas desde adentro (T-603, T-604, T-605).

Una fila por compañía y ambiente, y el repositorio la trata como **dos mitades
con vidas separadas**: la de firma y la de transmisión. No es una comodidad del
diseño — es RF-24: reemplazar el certificado no puede tocar las marcas de ATV, y
quitarlo no puede borrar las credenciales de transmisión.

Por eso hay `save_certificate` y `save_atv` en vez de un `save` con todo: con un
método único, cada llamada tendría que acordarse de reenviar la mitad que no
está cambiando, y la primera que se olvidara la borraría.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class FeCredentialsSnapshot(Protocol):
    """La fila, tal como la necesita la aplicación.

    Trae `atv_password_encrypted` porque alguien tiene que poder descifrarla
    para pedir un token (T-612). **No trae el `.p12` ni el PIN** porque no
    existen en la base: la llave privada vive en Vault desde el 2026-09-13.
    """

    environment: str
    certificate_pem: str | None
    certificate_name: str | None
    expires_at: datetime | None
    cert_uploaded_at: datetime | None
    key_custody: str | None
    atv_user: str | None
    atv_password_encrypted: str | None
    atv_updated_at: datetime | None
    atv_verified_at: datetime | None


class FeCredentialsRepository(Protocol):
    def get(self, environment: str) -> FeCredentialsSnapshot | None:
        """La fila de ese ambiente, o `None` si nunca se configuró."""
        ...

    def all(self) -> list[FeCredentialsSnapshot]:
        """Las dos, o las que haya.

        RF-30 pide ver qué le falta a **cada** ambiente, así que la pantalla
        pregunta una vez y no dos: con dos llamadas no podría decir «producción
        está listo, pruebas no» sin que una llegara antes que la otra.
        """
        ...

    def save_certificate(
        self,
        *,
        environment: str,
        certificate_pem: str,
        certificate_name: str,
        expires_at: datetime,
        uploaded_at: datetime,
        uploaded_by: int,
    ) -> None:
        """Guarda la mitad de firma, creando la fila si no estaba.

        No toca ninguna columna de ATV: rotar la contraseña en marzo no puede
        hacer que la pantalla diga que el certificado se subió en marzo.
        """
        ...

    def clear_certificate(self, *, environment: str) -> None:
        """Deja la mitad de firma vacía y **no borra la fila**.

        La fila sobrevive porque la otra mitad puede seguir configurada: quitar
        el certificado no es dar de baja el ambiente.
        """
        ...

    def save_atv(
        self,
        *,
        environment: str,
        user: str,
        password_encrypted: str,
        updated_at: datetime,
        updated_by: int,
    ) -> None:
        """Guarda la mitad de transmisión, creando la fila si no estaba."""
        ...

    def mark_verified(self, *, environment: str, at: datetime) -> None:
        """Anota que el IdP entregó un token con estas credenciales (T-612).

        Es lo que permite decir «verificadas el 3 de septiembre» en vez de
        obligar a probar a ciegas cada vez que alguien abre la pantalla.
        """
        ...
