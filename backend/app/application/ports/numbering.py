"""
La numeración de los comprobantes (T-704, T-705, plan §7.2 «La numeración»).

Tres puertos y no uno, porque son tres cosas que cambian por razones distintas:

* **`IssuerRepository`**: quién emite y contra qué ambiente. Cambia cuando soporte
  corrige la cédula o el negocio pasa a producción.
* **`DocumentNumbering`**: el contador y el registro del comprobante numerado.
  Es lo único que necesita un bloqueo de fila.
* **`SecurityCodes`**: los ocho dígitos al azar del final de la clave. En las
  pruebas tienen que ser predecibles, y en producción no.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Issuer:
    """El emisor, tal como está **hoy**.

    `identification` es la de `companies` (RN-45), nula si soporte no la cargó.
    `environment` es `sandbox` o `production`, y pruebas cuando nadie eligió
    ninguno: suponer producción sería suponer efecto fiscal donde no lo hay.
    """

    identification: str | None
    environment: str
    economic_activity: str | None = None


@dataclass(frozen=True)
class Office:
    """Los códigos de la sucursal y de la caja de la sesión, con sus ceros."""

    branch_code: str
    terminal_code: str


@dataclass(frozen=True)
class NumberedDocument:
    """Un comprobante con número y clave, listo para guardarse.

    `source_type` y `source_id` dicen de dónde nació: la venta, la devolución o
    la nota. El comprobante vive aparte de ellas porque una misma venta puede
    tener más de uno a lo largo de su vida: uno rechazado se corrige emitiendo
    otro con consecutivo nuevo, no reescribiendo este.
    """

    source_type: str
    source_id: int
    document_type: str
    environment: str
    sequence: int
    consecutive: str
    clave: str
    situation: str
    economic_activity: str | None
    issued_at: datetime


class IssuerRepository(Protocol):
    def issuer(self) -> Issuer: ...


class DocumentNumbering(Protocol):
    def office(self) -> Office:
        """La sucursal y la caja de la petición. Las fija la sesión (T-614)."""
        ...

    def last_sequence(self, *, document_type: str, environment: str) -> int:
        """La última secuencia de esta serie, **bloqueando la fila**.

        La serie son cinco dimensiones —compañía, sucursal, caja, tipo y
        ambiente— y la fila queda bloqueada hasta que confirme la transacción de
        quien llama: dos cajas que cobran a la vez esperan una a la otra en vez
        de sacar el mismo número. Cero si la serie no empezó.
        """
        ...

    def save_sequence(self, *, document_type: str, environment: str, value: int) -> None:
        """Deja `value` como la última. No confirma: va con el documento."""
        ...

    def record(self, document: NumberedDocument) -> None:
        """Guarda el comprobante numerado. No confirma: va con el documento."""
        ...


class SecurityCodes(Protocol):
    def new(self) -> str:
        """Ocho dígitos. Los genera el sistema del emisor (nota 3, inciso h)."""
        ...
