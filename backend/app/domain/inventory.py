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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .errors import (
    InsufficientStock,
    InvalidQuantity,
    InvalidStockMovementKind,
    InvalidStockSource,
    OutsideCountScope,
    ReasonInactive,
    ReasonIsSystem,
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


# ------------------------------------------------------ la salida (RN-99)
#
# Mercadería que deja el inventario sin venderse, con un motivo de un catálogo
# de la compañía. Una salida sin motivo no existe.

#: El motivo del sistema que usa la toma física (RN-100): viene con la
#: compañía, no se desactiva y no se elige en una salida —lo pone la toma—.
COUNT_REASON = "count"

#: Los motivos con los que nace toda compañía: (código, nombre, de sistema).
#: Los nombres son **datos de la compañía**, como las cuentas de la plantilla:
#: los escribe y los cambia ella, y por eso no pasan por los catálogos del POS.
DEFAULT_REASONS: tuple[tuple[str, str, bool], ...] = (
    ("shrinkage", "Merma", False),
    ("damage", "Daño", False),
    ("expired", "Vencido", False),
    ("internal_use", "Consumo interno", False),
    ("sample", "Muestra", False),
    (COUNT_REASON, "Toma física", True),
)


def check_exit_reason(reason) -> None:
    """Si con ese motivo se puede dar una salida (RN-99, RN-100).

    `reason` trae `id`, `is_active` e `is_system`. Un motivo apagado no vale, y
    el de la toma física tampoco: ese lo pone la toma al aplicar sus diferencias.
    """
    if not reason.is_active:
        raise ReasonInactive(reason.id)
    if reason.is_system:
        raise ReasonIsSystem(reason.id)


def check_reason_deactivatable(reason_id: int, *, is_system: bool) -> None:
    """El motivo del sistema no se desactiva (RN-100): la toma lo necesita."""
    if is_system:
        raise ReasonIsSystem(reason_id)


@dataclass(frozen=True)
class ExitLine:
    """Un producto que sale, valorado **al promedio del momento** (RN-99)."""

    product_id: int
    quantity: int
    unit_cost: Money
    #: RN-104; nulo es «sin lote», elegido a propósito.
    lot_id: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidQuantity(self.quantity)
        if self.quantity <= 0:
            raise InvalidQuantity(self.quantity)
        if self.unit_cost.is_negative:
            raise InvalidQuantity(self.unit_cost)

    @property
    def subtotal(self) -> Money:
        return self.unit_cost * self.quantity


def exit_total(lines: list[ExitLine]) -> Money:
    """Lo que sale del inventario, en plata: es lo que el asiento lleva al gasto."""
    return Money.sum(line.subtotal for line in lines)


def exit_units(lines: list[ExitLine]) -> int:
    return sum(line.quantity for line in lines)


# ------------------------------------------------ la toma física (RN-100)
#
# Contar lo que hay y ajustar la diferencia contra lo que decía el sistema **al
# contar**. Lo que se venda entre contar y aplicar no la contamina: ya quedó en
# el kárdex por su lado.

COUNT_OPEN = "open"
COUNT_APPLIED = "applied"
COUNT_DISCARDED = "discarded"


@dataclass(frozen=True)
class CountScope:
    """Qué cuenta una toma: una sucursal entera, o una categoría con sus hijas.

    `category_id` en nulo es toda la sucursal. El árbol tiene dos niveles
    (RN-5), así que «con sus hijas» es una sola pregunta: ¿su madre es esta?
    """

    branch_id: int
    category_id: int | None = None


def scope_includes(scope: CountScope, category_id: int, tree: Mapping[int, int | None]) -> bool:
    """Si una categoría cae dentro del alcance: toda la sucursal, la misma, o su raíz.

    `tree` es `{categoría: madre}`, con `None` en las raíces.
    """
    if scope.category_id is None:
        return True
    if category_id == scope.category_id:
        return True
    return tree.get(category_id) == scope.category_id


def scopes_overlap(a: CountScope, b: CountScope, tree: Mapping[int, int | None]) -> bool:
    """Si dos tomas contarían los mismos productos (RN-100).

    En una sucursal no pueden coexistir dos abiertas que compartan productos:
    una de toda la sucursal bloquea cualquier otra, una de una raíz bloquea las
    de sus hijas y viceversa, y dos hijas distintas no se estorban. La segunda
    contaría contra lo que la primera va a cambiar.
    """
    if a.branch_id != b.branch_id:
        return False
    if a.category_id is None or b.category_id is None:
        return True
    return scope_includes(a, b.category_id, tree) or scope_includes(b, a.category_id, tree)


def check_count_scope(
    scope: CountScope, product_id: int, category_id: int, tree: Mapping[int, int | None]
) -> None:
    """Contar un producto fuera de lo que la toma cubre es un error, no un dato."""
    if not scope_includes(scope, category_id, tree):
        raise OutsideCountScope(product_id, category_id, scope.category_id)


def check_counted_quantity(counted_qty: object) -> None:
    """Lo contado es un entero de cero para arriba: en el estante no hay medias
    unidades ni cantidades negativas."""
    if isinstance(counted_qty, bool) or not isinstance(counted_qty, int) or counted_qty < 0:
        raise InvalidQuantity(counted_qty)


def count_difference(system_qty: int, counted_qty: int) -> int:
    """Lo contado menos lo que decía el sistema al contar, con signo (RN-100).

        10 contadas 8  → −2    (faltante: sale como una salida)
        10 contadas 12 → +2    (sobrante)
        10 contadas 10 →  0    (no deja movimiento)
    """
    check_counted_quantity(counted_qty)
    return counted_qty - system_qty
