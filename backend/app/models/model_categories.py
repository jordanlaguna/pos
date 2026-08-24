from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Category(TenantMixin, Base):
    """Una categoría del catálogo, raíz o subcategoría (F4).

    El árbol tiene dos niveles y no más (RN-5), pero la columna admite un
    tercero: la profundidad la limita el servicio, que se cambia editando una
    función, y no el esquema, que hay que migrar. Un `CHECK` tampoco podría —
    para saber si el padre ya tiene padre hay que mirar otra fila—.
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)

    #: Nulo es una raíz. La foránea de más abajo lleva la compañía adentro.
    parent_id = Column(Integer, nullable=True)

    #: El orden que elige el dueño para la grilla de ventas (RF-13). No se
    #: ordena por nombre: quien vende pone primero lo que más vende.
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))

    #: RN-7: una categoría con productos o con hijas no se borra, se desactiva.
    #: Borrarla dejaría productos apuntando a una fila que no existe.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))

    #: El padre, o 0 si es raíz. Existe solo para que el UNIQUE de abajo sirva:
    #: MySQL no considera iguales dos nulos, así que un índice sobre
    #: `parent_id` a secas deja entrar dos raíces «Bebidas» sin decir nada —el
    #: caso más común—. El mismo hueco que en `products.barcode` es allá una
    #: ventaja y acá un defecto.
    parent_key = Column(Integer, Computed("IFNULL(parent_id, 0)", persisted=True), nullable=False)

    __table_args__ = (
        # Dos hermanas no se llaman igual, y las raíces son hermanas entre sí.
        # La colación de la tabla ignora tildes y mayúsculas, así que «Lácteos»
        # y «lacteos» chocan: conviene en un catálogo que escribe a mano gente
        # distinta.
        UniqueConstraint(
            "company_id", "parent_key", "name", name="uq_categories_company_parent_name"
        ),
        # Existe para que la foránea de abajo pueda apuntar al par. `id` ya es
        # único por sí solo; esto no restringe nada nuevo.
        UniqueConstraint("id", "company_id", name="uq_categories_id_company"),
        # La compañía va DENTRO de la foránea: sin eso, el esquema aceptaría una
        # subcategoría de la compañía A colgada de una raíz de la B. Hoy no puede
        # pasar porque el filtro de `tenancy.py` no deja ni ver esa raíz, pero
        # eso es el cinturón, no el muro. InnoDB no comprueba una foránea
        # compuesta cuando alguna columna es nula, así que las raíces pasan.
        #
        # Sin ON DELETE: queda en RESTRICT, que es RN-7 escrito en el esquema.
        # Con CASCADE, borrar «Bebidas» se llevaría «Cervezas» y sus productos
        # quedarían apuntando al vacío.
        ForeignKeyConstraint(
            ["parent_id", "company_id"],
            ["categories.id", "categories.company_id"],
            name="fk_categories_parent",
        ),
    )
