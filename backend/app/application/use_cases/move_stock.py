"""
Mover existencias (F15, plan §15.1).

Es **el único escritor** de existencias, como `api_error` es el único que
construye un «no». Antes había cinco sitios que escribían `products.stock`
—la venta, la devolución, la entrada, su anulación y la ficha— y ninguno
dejaba constancia de cuánto había antes. Desde F15 cada variación pasa por acá
y deja su fila en el kárdex, con la existencia de antes y de después, por
sucursal.

Los candados, siempre en el mismo orden: primero la fila del producto, después
la del nivel. Todo caso de uso que mueve existencias bloquea además **todos los
productos de su documento, en orden de id, antes de tocar ninguno**
(`ProductRepository.lock`); acá se vuelve a pedir el del producto —que no hace
nada si la transacción ya lo tiene— para leer el retrato fresco: el promedio
que la entrada acaba de escribir es el que se anota (RN-98).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.application.ports.inventory import KardexWriter, StockLevelRepository
from app.application.ports.repositories import ProductRepository
from app.domain.errors import DomainError
from app.domain.inventory import Movement, move
from app.domain.money import Money


class ProductMissing(DomainError):
    """Se pidió mover existencias de un producto que no está.

    No es un «no» del negocio sino del programa: quien llama ya comprobó que el
    producto existe y es de esta compañía. Se nombra para que un id equivocado
    no salga como un `KeyError` desde el medio de una transacción.
    """

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no existe")
        self.product_id = product_id


class MoveStock:
    def __init__(
        self,
        *,
        products: ProductRepository,
        levels: StockLevelRepository,
        kardex: KardexWriter,
    ) -> None:
        self._products = products
        self._levels = levels
        self._kardex = kardex

    def __call__(
        self,
        *,
        product_id: int,
        branch_id: int,
        delta: int,
        kind: str,
        unit_cost: Money,
        source_type: str,
        source_id: int,
        user_id: int,
        moved_at: datetime,
        source_line: int | None = None,
        lot_id: int | None = None,
    ) -> Movement:
        # 1. La fila del producto, bloqueada, y de ahí el promedio vigente. La
        #    entrada escribe el costo ANTES de llamar acá (plan §15.1): es lo que
        #    hace que `avg_cost_after` sea el promedio que dejó este movimiento.
        retratos = self._products.lock([product_id])
        if product_id not in retratos:
            raise ProductMissing(product_id)
        producto = retratos[product_id]

        # 2. La fila del nivel, después y nunca antes. La regla la pone el
        #    dominio: lo que no hay no se puede sacar.
        antes, despues = move(product_id, self._levels.lock(product_id, branch_id), delta)
        self._levels.set(product_id, branch_id, despues)

        # 3. La suma de la ficha, atómica en la base. Se mantiene en vez de
        #    borrarla porque la grilla de ventas la lee cinco mil veces al día
        #    (RNF-3) y un SUM por fila no cabe ahí.
        self._levels.add_to_total(product_id, delta)

        movimiento = Movement(
            product_id=product_id,
            branch_id=branch_id,
            kind=kind,
            quantity=delta,
            before_qty=antes,
            after_qty=despues,
            unit_cost=unit_cost,
            avg_cost_after=producto.cost,
            source_type=source_type,
            source_id=source_id,
            source_line=source_line,
            lot_id=lot_id,
            user_id=user_id,
            moved_at=moved_at,
        )
        return replace(movimiento, id=self._kardex.record(movimiento))
