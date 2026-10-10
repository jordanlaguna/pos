"""
El kárdex (F15, RN-98).

Toda variación de existencia deja un movimiento con la existencia de **antes y
después**, el costo con que se valoró, el promedio del producto después de él y
el documento que lo causó. La existencia de un producto en una sucursal es la
suma de sus movimientos, y si alguna vez el número de la ficha no coincide con
esa suma, el que manda es el kárdex.

Acá no se guarda nada ni se bloquea nada: entra la existencia que había y lo
que se mueve, sale la que queda. Es lo que permite comprobar que 10 − 3 deja 7
y que 2 − 3 no se puede, sin levantar MySQL. Quién toma los candados y en qué
orden es asunto de `MoveStock` (plan §15.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import (
    InsufficientStock,
    InvalidQuantity,
    InvalidStockMovementKind,
    InvalidStockSource,
)
from .money import Money

# ------------------------------------------------------------------- tipos
#
# Los once tipos de movimiento, con el signo que llevan. La anulación de una
# entrada es un movimiento propio con signo contrario, no una edición de lo que
# anuló; y la anulación de una factura se ve como anulación, no como devolución,
# aunque para el costo de ventas las dos resten igual (RN-98).

OPENING = "opening"  # la existencia con la que nace un producto, o la del día de instalar (RN-105)
SALE = "sale"
SALE_VOID = "sale_void"  # la anulación de una factura: una devolución entera (F7)
RETURN = "return"
ENTRY = "entry"
ENTRY_VOID = "entry_void"
EXIT = "exit"  # salida con motivo (RN-99)
EXIT_VOID = "exit_void"
COUNT = "count"  # el ajuste de una toma física (RN-100)
TRANSFER_OUT = "transfer_out"  # las dos mitades de un traslado (RN-102)
TRANSFER_IN = "transfer_in"

KINDS: tuple[str, ...] = (
    OPENING,
    SALE,
    SALE_VOID,
    RETURN,
    ENTRY,
    ENTRY_VOID,
    EXIT,
    EXIT_VOID,
    COUNT,
    TRANSFER_OUT,
    TRANSFER_IN,
)

#: De qué documento viene cada movimiento. `product` es la apertura: no hay
#: documento, el origen es la ficha misma.
SOURCE_TYPES: tuple[str, ...] = (
    "product",
    "sale",
    "return",
    "stock_entry",
    "stock_exit",
    "stock_count",
    "stock_transfer",
)


def check_kind(kind: object) -> None:
    if kind not in KINDS:
        raise InvalidStockMovementKind(kind)


def check_source_type(source_type: object) -> None:
    if source_type not in SOURCE_TYPES:
        raise InvalidStockSource(source_type)


@dataclass(frozen=True)
class Movement:
    """Una fila del kárdex. Nunca se edita ni se borra: lo que cambia es otra fila."""

    product_id: int
    #: En qué sucursal pasó. `before_qty` y `after_qty` son de ESTA sucursal,
    #: no del total del producto (RN-102).
    branch_id: int
    kind: str
    #: Con signo: negativo baja.
    quantity: int
    before_qty: int
    after_qty: int
    #: Con qué se valoró: el promedio del momento para lo que sale o se ajusta,
    #: el de la compra para lo que entra, y el del documento revertido en una
    #: devolución o una anulación (RN-98). Cero es «sin costo»: un producto que
    #: nunca se compró.
    unit_cost: Money
    #: El promedio del producto DESPUÉS de este movimiento. No es `unit_cost`:
    #: en una entrada o una reversión el costo del movimiento no es el promedio,
    #: y sin esta columna no se puede valorar a una fecha pasada (RN-103).
    avg_cost_after: Money
    source_type: str
    source_id: int
    user_id: int
    #: La pone el servidor, nunca el cliente.
    moved_at: datetime
    #: La línea del documento. Una línea con lotes deja varios movimientos, y es
    #: lo que permite devolver por lote sin una columna en la línea (RN-104).
    source_line: int | None = None
    #: RN-104; nulo es «sin lote».
    lot_id: int | None = None
    #: Lo pone quien lo guarda. Nulo mientras no se haya escrito.
    id: int | None = None

    def __post_init__(self) -> None:
        check_kind(self.kind)
        check_source_type(self.source_type)
        # El antes y el después no se declaran: se calculan con `move`. Un
        # movimiento que no cuadre consigo mismo es un error del programa.
        if self.after_qty != self.before_qty + self.quantity:
            raise InvalidQuantity(self.quantity)


# ---------------------------------------------------------------- la regla


def move(product_id: int, before: int, delta: int) -> tuple[int, int]:
    """La existencia de antes y de después de mover `delta` unidades.

    Mover cero no es un movimiento, y una existencia negativa no existe: lo que
    no hay no se puede sacar, ni vendiendo, ni anulando una entrada que ya se
    vendió (RN-98). Es la misma regla que `check_stock` aplica a la venta y
    `check_cancellable` a la anulación, dicha una sola vez para todos los
    documentos que mueven existencias.

        move(7, 10, -3) → (10, 7)
        move(7, 2, -3)  → InsufficientStock: hay 2 y se piden 3
    """
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise InvalidQuantity(delta)
    after = before + delta
    if after < 0:
        raise InsufficientStock(product_id, before, -delta)
    return before, after
