"""El libro, dicho desde adentro (T-1105, RN-59).

Este puerto existe para que `RegisterSale`, `RegisterReturn`, `CloseCashSession`,
`AddCashMovement`, `RegisterStockEntry` y `PaySupplier` **no sepan si la
contabilidad está activa**. Le cuentan lo que pasó y siguen. Con el módulo
apagado el adaptador es nulo y no hace nada; con el módulo activo escribe el
asiento en la misma sesión de SQLAlchemy, así que el `commit` sigue siendo uno
solo y RN-59 se cumple sin que la venta lo note.

**Recibe el hecho, no el asiento.** El plan lo dibujaba como `post(entry)`, y con
esa firma quien llama tiene que armar el asiento: leer el mapeo de cuentas,
resolver los papeles, conocer «por clasificar». O sea, saber de contabilidad —que
es exactamente lo que este puerto existe para evitar—. Pasando el hecho, el
adaptador es el único que conoce `account_mappings`, y el caso de uso queda igual
de ignorante que antes de F11 (T-1105, 2026-09-12).

Los tipos que entran son los del dominio (`SoldDocument`, `SoldLine`…): valores
que el caso de uso ya tiene en la mano. Ninguna firma menciona una cuenta.

Ninguno devuelve nada. Un asiento que no se pudo escribir **lanza**, y eso tumba
la transacción entera: si el asiento no se puede escribir, la venta no se
confirma (RN-59). Lo que nunca lanza es un mapeo incompleto, porque no existe:
todo papel sin cuenta cae en 1.9.99.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.ledger import (
    ClosedSession,
    DrawerMovement,
    JournalEntry,
    PurchasedDocument,
    PurchasedLine,
    ReturnDocument,
    SoldDocument,
    SoldLine,
    SupplierPaymentRef,
)
from app.domain.errors import DomainError
from app.domain.money import Money


class AccountingNotActive(DomainError):
    """Se quiso escribir en un libro que no está activado.

    En la práctica significa que falta la cuenta «por clasificar», que es la que
    sostiene RN-59. Sin ella un mapeo incompleto **sí** detendría una venta, así
    que es mejor decirlo fuerte y temprano que descubrirlo en el peor momento.
    """

    def __init__(self) -> None:
        super().__init__("la contabilidad no está activada para esta compañía")


class JournalWriter(Protocol):
    """Escribir un asiento **ya armado**.

    Es la mitad del libro que usan los asientos que no salen de ningún evento: la
    apertura, el manual y el de ajuste. Esos los dictó una persona y llegan con
    sus cuentas puestas, así que no hay nada que traducir.

    Devuelve el id, o `None` si no había asiento que escribir —una apertura sin
    saldos, una fecha anterior al arranque de la contabilidad (RN-60)—.
    """

    def post(self, entry: JournalEntry | None) -> int | None: ...


class Ledger(JournalWriter, Protocol):
    """Lo que el libro necesita que le cuenten."""

    def record_sale(self, sale: SoldDocument, lines: Sequence[SoldLine]) -> None: ...

    def record_return(self, ret: ReturnDocument, lines: Sequence[SoldLine]) -> None: ...

    def record_cash_close(
        self, session: ClosedSession, *, expected: Money, counted: Money
    ) -> None:
        """El cierre. Un turno que cuadra no deja asiento, y eso lo decide el
        dominio, no quien llama."""
        ...

    def record_cash_movement(self, mov: DrawerMovement) -> None: ...

    def record_purchase(
        self, entry: PurchasedDocument, lines: Sequence[PurchasedLine]
    ) -> None: ...

    def record_supplier_payment(self, pay: SupplierPaymentRef) -> None: ...


class NullLedger:
    """El libro apagado: no hace nada, y hacerlo no cuesta nada.

    Es el adaptador que usa una compañía sin el módulo de contabilidad, que son
    casi todas. No es un objeto de prueba: es la implementación de producción del
    caso «este negocio no lleva libros acá», y por eso vive en la misma carpeta
    que el puerto y no en `tests/`.

    Que exista es lo que permite que los casos de uso llamen siempre, sin un `if`
    en cada uno. Un `if` por evento serían seis sitios donde olvidarse.
    """

    def post(self, entry: JournalEntry | None) -> int | None:
        return None

    def record_sale(self, sale: SoldDocument, lines: Sequence[SoldLine]) -> None:
        return None

    def record_return(self, ret: ReturnDocument, lines: Sequence[SoldLine]) -> None:
        return None

    def record_cash_close(
        self, session: ClosedSession, *, expected: Money, counted: Money
    ) -> None:
        return None

    def record_cash_movement(self, mov: DrawerMovement) -> None:
        return None

    def record_purchase(
        self, entry: PurchasedDocument, lines: Sequence[PurchasedLine]
    ) -> None:
        return None

    def record_supplier_payment(self, pay: SupplierPaymentRef) -> None:
        return None
