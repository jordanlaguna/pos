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

from app.domain.inventory import Movement


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


class NullKardex:
    """El kárdex que no anota nada.

    Para las pruebas que no miran el inventario, como `NullLedger` para las que
    no miran el libro. En producción no existe: toda variación de existencia
    deja su fila (RN-98).
    """

    def record(self, movement: Movement) -> int:
        return 0
