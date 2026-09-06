"""
Puertos del catálogo CABYS.

Son dos y no uno a propósito: **el catálogo de Hacienda** y **la caché local**.
La diferencia entre ellos es la que importa —uno depende de que haya internet y
el otro no— y tenerla escrita en el tipo es lo que permite que la regla de RNF-4
viva en el caso de uso y no enterrada en un `try` del adaptador.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.cabys import CabysCode


class CatalogUnavailable(Exception):
    """No se pudo hablar con Hacienda.

    No es un error del usuario ni una regla de negocio: es el estado normal de un
    POS en una LAN sin salida (RNF-4). Quien la atrapa responde desde la caché y
    lo dice; nunca bloquea una venta.
    """


class CabysCatalog(Protocol):
    """El catálogo de Hacienda, por internet."""

    def search(self, text: str, limit: int) -> list[CabysCode]:
        """Busca por texto. Lanza `CatalogUnavailable` si no hay salida."""
        ...

    def by_code(self, code: str) -> CabysCode | None:
        """Un código exacto, o `None` si el catálogo no lo tiene."""
        ...


class CabysCacheRepository(Protocol):
    """Lo que ya se consultó alguna vez. Global, no por compañía.

    El catálogo es del país: la caché es la misma para todos los clientes, y por
    eso `cabys_cache` no lleva `company_id` ni hereda el filtro de `tenancy.py`.
    """

    def search(self, text: str, limit: int) -> list[CabysCode]: ...

    def by_code(self, code: str) -> CabysCode | None: ...

    def remember(self, entries: list[CabysCode], now: datetime) -> None:
        """Guarda o actualiza lo que se acaba de leer de Hacienda."""
        ...

    def updated_at(self, code: str) -> datetime | None:
        """Cuándo se leyó ese código por última vez. Es lo que permite decirle a
        quien busca sin internet desde cuándo es lo que está viendo."""
        ...
