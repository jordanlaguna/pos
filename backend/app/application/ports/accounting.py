"""Los datos de contabilidad, dichos desde adentro (T-1107).

Tres repositorios y la configuración. Igual que el resto de los puertos, cada
método es una pregunta en el idioma del negocio: `by_code`, no un `SELECT`.

El libro en sí **no** está acá: vive en `ports/ledger.py`, porque escribir un
asiento no es guardar una fila sino traducir un hecho, y esa diferencia es la que
permite que `RegisterSale` no sepa que la contabilidad existe.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.domain.ledger import Line


class AccountSnapshot(Protocol):
    """Lo que la aplicación necesita saber de una cuenta."""

    id: int
    code: str
    name: str
    kind: str
    parent_id: int | None
    #: La usa el mapeo: no se borra ni se desactiva (RN-64).
    is_system: bool
    is_active: bool


class AccountRepository(Protocol):
    def all(self) -> list[AccountSnapshot]:
        """El catálogo entero, activas e inactivas.

        Entero y no paginado a propósito: son unas decenas de filas, se leen
        juntas para armar el árbol, y quien activa necesita saber cuáles ya
        están para no duplicar códigos.
        """
        ...

    def create(
        self,
        *,
        code: str,
        name: str,
        kind: str,
        parent_id: int | None,
        is_system: bool,
    ) -> int: ...


class MappingRepository(Protocol):
    def all(self) -> list[tuple[str, str, int]]:
        """`(evento, papel, id de cuenta)` de todo el mapeo."""
        ...

    def set(self, *, event: str, role: str, account_id: int) -> None:
        """Asigna la cuenta de ese papel, creando la fila o cambiándola."""
        ...


class PeriodSnapshot(Protocol):
    id: int
    year: int
    month: int
    #: 'open' | 'closed'
    status: str


class PeriodRepository(Protocol):
    def get(self, year: int, month: int) -> PeriodSnapshot | None: ...

    def create(self, year: int, month: int) -> PeriodSnapshot:
        """Crea el mes, abierto."""
        ...


class JournalSnapshot(Protocol):
    id: int
    entry_date: date
    kind: str


class JournalRepository(Protocol):
    def get(self, entry_id: int) -> JournalSnapshot | None: ...

    def lines_of(self, entry_id: int) -> list[Line]:
        """Las líneas del asiento, ya como valores del dominio.

        Devuelve `Line` y no filas de SQLAlchemy porque quien las usa es una
        función pura —la reclasificación—, y darle filas la ataría a la base.
        """
        ...


class AccountingSettings(Protocol):
    """La sección `accounting` de la configuración de la compañía.

    Vive en el JSON de `settings` y no en una tabla propia porque es
    configuración del negocio, como la moneda: qué plantilla se sembró, desde
    cuándo se llevan libros y si están activos.
    """

    def accounting(self) -> dict: ...

    def save_accounting(self, config: dict) -> None: ...
