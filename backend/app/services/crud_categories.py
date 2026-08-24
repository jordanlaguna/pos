"""Categorías: el adaptador entre el árbol del catálogo y HTTP (F4).

Las reglas viven en `app/domain/categories.py` —puras, probadas sin base—. Acá
está lo que necesita la base: contar hermanas, hijas y productos, y traducir
cada «no» del dominio a un código de estado. Es la misma división que en
`crud_stock_entry.py`.

Las cuentas van con `func.count(...)` y con el `company_id` escrito a mano. No
es estilo: el `count` de `Query` envuelve la consulta en una subconsulta donde el
criterio de compañía no entra, y una consulta agregada tampoco pasa por el
filtro automático de `tenancy.py` —no tiene entidades que filtrar—. Contar mal
acá sería contar las categorías de todas las compañías para decidir si esta
puede borrar una. Lo vigila `tests/test_tenancy.py`.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.categories import (
    check_can_become_child,
    check_can_delete,
    check_can_hold_products,
    check_can_nest,
    check_not_itself,
    next_order,
    renumber,
)
from app.domain.errors import (
    CategoryHasChildren,
    CategoryInUse,
    CategoryIsItsOwnParent,
    CategoryNeedsSubcategory,
    CategoryTooDeep,
)
from app.models.model_categories import Category
from app.models.model_product import Product
from app.schemas.schemas_categories import AddCategories, CategoryRegister, CategoryUpdate
from app.utils.api_errors import api_error
from app.utils.tenancy import compania_actual


# ------------------------------------------------------------------- lecturas

def get_all_categories(db: Session) -> list[Category]:
    """El árbol entero, activas e inactivas.

    Van las dos porque cada pantalla necesita otra cosa: la grilla de ventas
    muestra solo las activas, y el inventario tiene que poder nombrar la
    categoría de un producto —que puede estar desactivada— y volver a
    activarla. Un endpoint por caso serían dos endpoints que se desincronizan.

    El orden llega hecho: primero las raíces (`parent_key` = 0) y después cada
    rama junta, cada una en el orden que eligió el dueño.
    """
    return (
        db.query(Category)
        .order_by(Category.parent_key, Category.sort_order, Category.id)
        .all()
    )


def por_id(db: Session, category_id: int) -> Category | None:
    """Una categoría de esta compañía. El filtro lo pone `tenancy.py`."""
    return db.query(Category).filter(Category.id == category_id).first()


def _hijas(db: Session, category_id: int) -> int:
    return (
        db.query(func.count(Category.id))
        .filter(
            Category.company_id == compania_actual(),
            Category.parent_id == category_id,
        )
        .scalar()
        or 0
    )


def _hijas_activas(db: Session, category_id: int) -> int:
    """Las hijas que siguen en circulación.

    Es la cuenta que mira RN-6 y no la de arriba: una raíz a la que le
    desactivaron su única subcategoría vuelve a ser una hoja y vuelve a recibir
    productos. Con las desactivadas contadas, esa rama no tendría dónde poner
    nada. Borrar sí cuenta todas: una hija desactivada sigue siendo una fila.
    """
    return (
        db.query(func.count(Category.id))
        .filter(
            Category.company_id == compania_actual(),
            Category.parent_id == category_id,
            Category.is_active.is_(True),
        )
        .scalar()
        or 0
    )


def _productos(db: Session, category_id: int) -> int:
    return (
        db.query(func.count(Product.id_product))
        .filter(
            Product.company_id == compania_actual(),
            Product.category_id == category_id,
        )
        .scalar()
        or 0
    )


def _hermanas(db: Session, parent_id: int | None) -> list[Category]:
    """Las categorías que comparten madre, en orden. Las raíces son hermanas."""
    consulta = db.query(Category)
    consulta = (
        consulta.filter(Category.parent_id.is_(None))
        if parent_id is None
        else consulta.filter(Category.parent_id == parent_id)
    )
    return consulta.order_by(Category.sort_order, Category.id).all()


def _nombre_tomado(
    db: Session, parent_id: int | None, name: str, excepto: int | None = None
) -> bool:
    """¿Ya hay una hermana con ese nombre?

    Lo comprueba el UNIQUE de la tabla igual; esto es para poder responder con
    un código y el nombre en vez de con un 500 de integridad. La comparación la
    hace MySQL con la colación de la tabla, que ignora tildes y mayúsculas, así
    que «Lácteos» y «lacteos» chocan igual que en el índice.
    """
    return any(
        hermana.name == name and hermana.id != excepto
        for hermana in _hermanas(db, parent_id)
    )


# ------------------------------------------------------------------ escrituras

def create_category(db: Session, category: CategoryRegister) -> AddCategories:
    """Una categoría nueva, raíz o subcategoría.

    Nace activa y al final de sus hermanas: quien la crea la ve donde la puso,
    y de ahí la mueve si quiere.
    """
    parent_id = category.parent_id
    if parent_id is not None:
        madre = por_id(db, parent_id)
        if madre is None:
            raise api_error(404, "category_not_found", category_id=parent_id)
        try:
            check_can_nest(parent_id, parent_is_root=madre.parent_id is None)
        except CategoryTooDeep:
            raise api_error(400, "category_too_deep", category_id=parent_id) from None

    if _nombre_tomado(db, parent_id, category.name):
        raise api_error(400, "category_name_taken", name=category.name)

    fila = Category(
        name=category.name,
        parent_id=parent_id,
        sort_order=next_order([h.sort_order for h in _hermanas(db, parent_id)]),
        is_active=True,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return AddCategories(id=fila.id, name=fila.name, parent_id=fila.parent_id)


def update_category(
    db: Session, category_id: int, cambios: CategoryUpdate
) -> Category:
    """Renombrar, mover de madre o activar y desactivar (RF-13, RF-14).

    Los tres en un endpoint porque los tres son «esta categoría ahora es así», y
    porque mover y renombrar comparten la comprobación del nombre repetido: al
    mudarse, el nombre que era libre entre sus hermanas anteriores puede estar
    tomado entre las nuevas.

    **Mover no toca los productos** (RF-14): siguen colgados de la misma
    subcategoría, que es la que se mudó. Es la razón de que el producto apunte a
    la categoría y no a la rama.
    """
    fila = por_id(db, category_id)
    if fila is None:
        raise api_error(404, "category_not_found", category_id=category_id)

    campos = cambios.model_fields_set
    # `parent_id` en nulo es «pasa a ser raíz», y omitido es «no se toca». Sin
    # distinguirlos, renombrar una subcategoría la promovería a raíz sin que
    # nadie lo pidiera.
    se_mueve = "parent_id" in campos and cambios.parent_id != fila.parent_id
    nueva_madre = cambios.parent_id if se_mueve else fila.parent_id
    nombre = cambios.name if "name" in campos and cambios.name else fila.name

    if se_mueve:
        try:
            check_not_itself(category_id, cambios.parent_id)
        except CategoryIsItsOwnParent:
            raise api_error(400, "category_self_parent", category_id=category_id) from None

        if nueva_madre is not None:
            madre = por_id(db, nueva_madre)
            if madre is None:
                raise api_error(404, "category_not_found", category_id=nueva_madre)
            try:
                check_can_nest(nueva_madre, parent_is_root=madre.parent_id is None)
            except CategoryTooDeep:
                raise api_error(400, "category_too_deep", category_id=nueva_madre) from None
            try:
                check_can_become_child(category_id, _hijas(db, category_id))
            except CategoryHasChildren as e:
                raise api_error(
                    400, "category_has_children", category_id=category_id, children=e.children
                ) from None

    if (nombre != fila.name or se_mueve) and _nombre_tomado(
        db, nueva_madre, nombre, excepto=category_id
    ):
        raise api_error(400, "category_name_taken", name=nombre)

    fila.name = nombre
    if se_mueve:
        fila.parent_id = nueva_madre
        # El orden anterior pertenecía a la numeración de la madre anterior.
        fila.sort_order = next_order([h.sort_order for h in _hermanas(db, nueva_madre)])
    if "is_active" in campos and cambios.is_active is not None:
        # Desactivar una raíz esconde su rama entera sin tocar ninguna hija: al
        # volver a activarla, la rama vuelve como estaba.
        fila.is_active = cambios.is_active

    db.commit()
    db.refresh(fila)
    return fila


def delete_category(db: Session, category_id: int) -> None:
    """Borrar solo lo que no arrastra nada (RN-7).

    Con productos o con hijas no se borra: se desactiva, que es lo que dice el
    código del error para que el POS pueda ofrecerlo.
    """
    fila = por_id(db, category_id)
    if fila is None:
        raise api_error(404, "category_not_found", category_id=category_id)

    try:
        check_can_delete(category_id, _productos(db, category_id), _hijas(db, category_id))
    except CategoryInUse as e:
        raise api_error(
            409,
            "category_in_use",
            category_id=category_id,
            products=e.products,
            children=e.children,
        ) from None

    db.delete(fila)
    db.commit()


def reorder(db: Session, parent_id: int | None, ids: list[int]) -> list[Category]:
    """El orden que eligió el dueño, para un grupo de hermanas (RF-13).

    Se exige la lista **completa** de hermanas. Con una parcial, las que
    faltaran conservarían su número viejo y quedarían empatadas con las
    renumeradas: el orden dejaría de estar definido y la grilla lo mostraría
    distinto según lo que devuelva la base. El POS ya tiene la lista entera en
    pantalla, así que mandarla no le cuesta nada.
    """
    hermanas = _hermanas(db, parent_id)
    if sorted(ids) != sorted(h.id for h in hermanas):
        raise api_error(
            400,
            "category_reorder_incomplete",
            expected=[h.id for h in hermanas],
            received=ids,
        )

    posiciones = dict(renumber(ids))
    for hermana in hermanas:
        hermana.sort_order = posiciones[hermana.id]
    db.commit()
    return _hermanas(db, parent_id)


# ------------------------------------------------------- lo que usa el catálogo

def check_category_for_product(db: Session, category_id: int) -> Category:
    """La categoría donde se va a colgar un producto (RN-6).

    La pide `crud_product` al crear y al mover un producto. Dos «no» y el porqué
    de cada uno:

    * **Con hijas activas, no.** El producto iría a una raíz que en la grilla de
      ventas ya no muestra productos propios, sino fichas: no aparecería en
      ninguna. Se cuentan las **activas** por lo que explica
      `check_can_hold_products`: si no, una rama con todas sus subcategorías
      retiradas se queda sin ningún sitio donde poner un producto.
    * **Desactivada, tampoco.** Es una categoría que el dueño sacó de
      circulación; colgarle un producto nuevo lo esconde. Los que ya estaban
      colgados se quedan —desactivar no mueve nada—, pero eso es distinto de
      dejar entrar uno nuevo.
    """
    fila = por_id(db, category_id)
    if fila is None:
        raise api_error(404, "category_not_found", category_id=category_id)
    if not fila.is_active:
        raise api_error(400, "category_inactive", category_id=category_id, name=fila.name)
    try:
        check_can_hold_products(category_id, _hijas_activas(db, category_id))
    except CategoryNeedsSubcategory as e:
        raise api_error(
            400,
            "category_needs_subcategory",
            category_id=category_id,
            name=fila.name,
            children=e.children,
        ) from None
    return fila
