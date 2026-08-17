"""
Puertos de seguridad.

Están separados de los repositorios porque cambian por razones distintas:
`bcrypt` se cambia cuando envejece el algoritmo, y el emisor de tokens cuando
cambia la sesión —por ejemplo, cuando el JWT tenga que llevar la compañía (F2)—.

El defecto 6 vive detrás de `PasswordHasher`: `passlib` sin versiones acotadas
hacía que en una máquina recién aprovisionada el registro y el login fallaran
con error 500, sin que nadie tocara el código. Con el puesto de por medio, ese
recambio es un archivo.
"""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool:
        """False si no coincide. **Nunca lanza** por un hash con formato viejo o
        corrupto: un error acá sería un 500 en el login, y el login es lo único
        que separa a un extraño de la caja."""
        ...


class TokenIssuer(Protocol):
    def issue(self, claims: dict) -> str: ...

    def read(self, token: str) -> dict | None:
        """Los datos del token, o None si está vencido, mal firmado o roto."""
        ...
