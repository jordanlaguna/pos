"""
Los puertos del inventario (F15, plan §15.4).

Tres razones de cambio, tres puertos: dónde está cada cosa (`StockLevelRepository`),
qué pasó (`KardexWriter`) y leerlo (`KardexReader`). El kárdex es la bitácora;
el nivel es la caché que la bitácora mantiene, y los dos se escriben en la
misma transacción. Quién los escribe es uno solo: `MoveStock`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.inventory import ExitLine, Movement
from app.domain.money import Money


class StockLevelRepository(Protocol):
    """La existencia de cada producto en cada sucursal (RN-102)."""

    def lock(self, product_id: int, branch_id: int) -> int:
        """Bloquea la fila del nivel y devuelve la cantidad que tiene.

        **La fila nace con el candado**: si no existe, se crea en cero antes de
        bloquearla, de modo que dos primeras entradas simultáneas al mismo
        (producto, sucursal) no mueren en la clave única sino que una espera a
        la otra (plan §15.1). Se llama DESPUÉS de bloquear la fila del producto,
        siempre en ese orden.
        """
        ...

    def set(self, product_id: int, branch_id: int, quantity: int) -> None:
        """Escribe la cantidad que dejó el movimiento. Solo `MoveStock` la llama."""
        ...

    def levels_of(self, product_id: int) -> dict[int, int]:
        """`{sucursal: cantidad}` de un producto. Sin fila es cero, y no sale."""
        ...

    def levels_in(self, branch_id: int) -> dict[int, int]:
        """`{producto: cantidad}` de una sucursal."""
        ...

    def add_to_total(self, product_id: int, delta: int) -> None:
        """Mantiene `products.stock` como la suma de las sucursales.

        **Atómico en la base** —`UPDATE … SET stock = stock + :delta`—, nunca
        «leer, sumar, escribir»: en `REPEATABLE READ` la segunda transacción no
        ve lo que la primera acaba de confirmar y escribiría una suma vieja.
        """
        ...


class KardexWriter(Protocol):
    def record(self, movement: Movement) -> int:
        """Anota el movimiento y devuelve su identificador. Nunca se edita ni se borra."""
        ...


class KardexReader(Protocol):
    def of_product(
        self,
        product_id: int,
        *,
        branch_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Movement]:
        """Los movimientos de un producto, del más reciente al más viejo (RF-87)."""
        ...

    def of_source(self, source_type: str, source_id: int) -> list[Movement]:
        """Lo que dejó un documento, en el orden en que se anotó.

        Es lo que la devolución y la anulación de una entrada leen para revertir
        por lote en orden inverso (RN-104), y lo que enlaza la venta con su
        kárdex en pantalla.
        """
        ...

    def count_for(self, product_id: int) -> int:
        """Cuántas filas tiene un producto. Con alguna, no se borra: se desactiva."""
        ...


class ReasonSnapshot(Protocol):
    """Lo que la salida necesita saber de su motivo (RN-99)."""

    id: int
    code: str
    name: str
    is_system: bool
    is_active: bool


class StockReasonRepository(Protocol):
    def get(self, reason_id: int) -> ReasonSnapshot | None:
        """El motivo con ese id **en esta compañía**, o nulo."""
        ...


class ExitLineSnapshot(Protocol):
    """Una línea de una salida ya guardada, para revertirla al anular."""

    product_id: int
    quantity: int
    #: El promedio al salir (RN-99): es a lo que se repone.
    unit_cost: Money
    lot_id: int | None


class ExitSnapshot(Protocol):
    id: int
    branch_id: int
    reason_id: int
    #: 'applied' | 'voided'
    status: str
    total_cost: Money


class StockExitRepository(Protocol):
    def get(self, exit_id: int) -> ExitSnapshot | None: ...

    def add(
        self,
        *,
        branch_id: int,
        reason_id: int,
        user_id: int,
        notes: str | None,
        total_cost: Money,
        created_at: datetime,
        lines: list[ExitLine],
    ) -> int:
        """Guarda la salida con sus líneas y devuelve su identificador."""
        ...

    def lines_of(self, exit_id: int) -> list[ExitLineSnapshot]: ...

    def mark_voided(self, exit_id: int, *, voided_at: datetime, reason: str) -> None:
        """Una salida no se edita: se anula con motivo (RN-99)."""
        ...


class CountSnapshot(Protocol):
    """Una toma física (RN-100): dónde, qué y en qué estado."""

    id: int
    branch_id: int
    #: Nulo es toda la sucursal; una raíz incluye a sus hijas.
    category_id: int | None
    #: 'open' | 'applied' | 'discarded'
    status: str


class CountLineSnapshot(Protocol):
    product_id: int
    lot_id: int | None
    #: Lo que decía el sistema AL CONTAR.
    system_qty: int
    counted_qty: int


class StockCountRepository(Protocol):
    def get(self, count_id: int) -> CountSnapshot | None: ...

    def open_in_branch(self, branch_id: int) -> list[CountSnapshot]:
        """Las abiertas de esa sucursal: con ellas se decide si cabe otra."""
        ...

    def add(
        self,
        *,
        branch_id: int,
        category_id: int | None,
        opened_by: int,
        opened_at: datetime,
        notes: str | None,
    ) -> int: ...

    def lines_of(self, count_id: int) -> list[CountLineSnapshot]: ...

    def record_line(
        self,
        count_id: int,
        *,
        product_id: int,
        lot_id: int | None,
        system_qty: int,
        counted_qty: int,
        counted_at: datetime,
        counted_by: int,
    ) -> None:
        """Guarda lo contado. Si el (producto, lote) ya se contó, lo reemplaza:
        volver a contar es corregir, no sumar."""
        ...

    def close(self, count_id: int, *, status: str, closed_by: int, closed_at: datetime) -> None:
        """Aplicada o descartada: ninguna de las dos se vuelve a abrir."""
        ...


class NullKardex:
    """El kárdex que no anota nada.

    Para las pruebas que no miran el inventario, como `NullLedger` para las que
    no miran el libro. En producción no existe: toda variación de existencia
    deja su fila (RN-98).
    """

    def record(self, movement: Movement) -> int:
        return 0
