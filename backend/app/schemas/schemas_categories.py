from pydantic import BaseModel, Field


class CategoryRegister(BaseModel):
    """Alta de categoría. Sin `parent_id` nace raíz; con él, subcategoría."""

    name: str
    parent_id: int | None = None


class AddCategories(BaseModel):
    """Lo que devuelve el alta. El nombre viene del código heredado."""

    id: int
    name: str
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    """Renombrar, mover o activar. Lo que no venga, no se toca.

    La diferencia entre **omitir** `parent_id` y mandarlo **en nulo** es la que
    separa «no me interesa la madre» de «pasala a raíz», y se lee con
    `model_fields_set`. Sin distinguirlas, renombrar una subcategoría la
    promovería a raíz sin que nadie lo pidiera.
    """

    name: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


class CategoryReorder(BaseModel):
    """El orden de un grupo de hermanas, de la primera a la última.

    `parent_id` en nulo son las raíces. `ids` tiene que traerlas **todas**: ver
    el porqué en `crud_categories.reorder`.
    """

    parent_id: int | None = None
    ids: list[int] = Field(min_length=1)


class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}
