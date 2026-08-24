"""El árbol del catálogo (F4).

Dos niveles: raíces y subcategorías. «Bebidas → Cervezas», «Yamaha → Llantas».
Acá está solo la aritmética y las reglas —contar hijas o productos es trabajo de
una consulta, y traducir un «no» a un código de estado es del router—.

Las cuatro reglas del spec, y por qué cada una es una función y no un `if` en el
servicio:

* **RN-5**, dos niveles exactos. Se cierra por los dos lados: no se puede colgar
  de una subcategoría, y una categoría con hijas no puede volverse hija. Con
  solo la primera, mover «Bebidas» (que tiene «Cervezas») debajo de «Licores»
  crearía un tercer nivel sin que nadie escribiera nada de tres.
* **RN-6**, el producto va en la hoja. Si la raíz tiene hijas, el producto no
  puede quedar colgado de la raíz: en la grilla de ventas no aparecería en
  ninguna ficha.
* **RN-7**, con productos o con hijas no se borra, se desactiva.
* La profundidad limitada a dos hace imposible un ciclo, **salvo uno**: una
  categoría puesta como madre de sí misma. La foránea no lo impide —una fila
  puede apuntarse a sí misma— así que lo impide `check_not_itself`.

Desactivar una raíz esconde su rama entera y **no toca ninguna hija**: las filas
quedan como están y la grilla, que navega desde las raíces, deja de llegar. Así
volver a activarla devuelve la rama como estaba, en vez de tener que recordar
cuál de las hijas había sido desactivada a mano antes.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.errors import (
    CategoryHasChildren,
    CategoryInUse,
    CategoryIsItsOwnParent,
    CategoryNeedsSubcategory,
    CategoryTooDeep,
)

#: Con qué número empieza el orden. 1 y no 0 porque el orden se muestra y se
#: reordena a mano: «primera» se lee mejor que «cero».
FIRST_ORDER = 1


def check_can_nest(parent_id: int, parent_is_root: bool) -> None:
    """Colgar algo de este padre: solo si el padre es raíz (RN-5)."""
    if not parent_is_root:
        raise CategoryTooDeep(parent_id)


def check_can_become_child(category_id: int, children: int) -> None:
    """Volverse hija: solo si no tiene hijas propias (RN-5).

    Es la otra mitad de la regla, y la que se olvida: mover una raíz con hijas
    debajo de otra raíz crea un tercer nivel sin haber creado ninguna fila.
    """
    if children > 0:
        raise CategoryHasChildren(category_id, children)


def check_not_itself(category_id: int, parent_id: int | None) -> None:
    """Nadie es madre de sí misma.

    Lo único que la foránea no impide: una fila puede referenciar su propia
    clave. Sin esto, «Bebidas» con `parent_id = Bebidas` desaparece de las dos
    listas —no es raíz porque tiene padre, y no es hija de ninguna raíz—.
    """
    if parent_id is not None and parent_id == category_id:
        raise CategoryIsItsOwnParent(category_id)


def check_can_delete(category_id: int, products: int, children: int) -> None:
    """Borrar: solo lo que no arrastra nada (RN-7).

    Con productos o con hijas, la salida es desactivar. El «no» lleva las dos
    cuentas porque la frase las nombra —«tiene 12 productos y 3
    subcategorías»— y porque quien lo lee necesita saber qué mover primero.
    """
    if products > 0 or children > 0:
        raise CategoryInUse(category_id, products, children)


def check_can_hold_products(category_id: int, children: int) -> None:
    """Colgar un producto de esta categoría: solo si es una hoja (RN-6).

    Una raíz sin hijas es una hoja y admite productos; en cuanto tiene hijas,
    los productos van en ellas. Los que ya estaban colgados de la raíz se
    quedan donde están: la regla se aplica al asignar, no hacia atrás, y
    moverlos sería decidir por el dueño en qué subcategoría van.

    **`children` son las hijas activas, no todas.** Es una decisión y no un
    descuido: una raíz a la que le desactivaron su única subcategoría vuelve a
    ser una hoja y vuelve a recibir productos. Contando las desactivadas, esa
    rama quedaría sin ningún sitio donde poner nada —la raíz bloqueada por una
    hija, y la hija fuera de circulación—, y la única salida sería reactivar
    algo que el dueño acaba de retirar a propósito.

    Borrar es distinto y ahí se cuentan **todas** (`check_can_delete`): una hija
    desactivada sigue siendo una fila, y borrar su madre la dejaría huérfana.
    """
    if children > 0:
        raise CategoryNeedsSubcategory(category_id, children)


def next_order(existing: Sequence[int]) -> int:
    """El orden de una categoría nueva: al final de sus hermanas.

    Se mira el máximo y no la cantidad: si había cinco y se borró la tercera,
    quedan cuatro con órdenes 1, 2, 4 y 5, y una nueva con orden 5 empataría
    con la última.
    """
    return max(existing, default=FIRST_ORDER - 1) + 1


def renumber(ids: Sequence[int]) -> list[tuple[int, int]]:
    """El orden que pidió el dueño, convertido en pares (id, orden).

    Se renumera todo de 1 en adelante en vez de intercambiar dos valores: los
    huecos que dejan los borrados y los empates que trae una migración se
    arreglan solos cada vez que alguien reordena.
    """
    return [(id_, FIRST_ORDER + posicion) for posicion, id_ in enumerate(ids)]
