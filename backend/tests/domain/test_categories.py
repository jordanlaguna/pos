"""El árbol del catálogo (T-402, T-403; RN-5 a RN-7)."""

import pytest

from app.domain.categories import (
    FIRST_ORDER,
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


class TestDosNiveles:
    """RN-5, por los dos lados."""

    def test_se_puede_colgar_de_una_raiz(self):
        check_can_nest(parent_id=3, parent_is_root=True)

    def test_no_se_puede_colgar_de_una_subcategoria(self):
        with pytest.raises(CategoryTooDeep) as e:
            check_can_nest(parent_id=7, parent_is_root=False)
        # El id viaja al POS: la frase nombra la categoría que ya es hija.
        assert e.value.parent_id == 7

    def test_una_categoria_sin_hijas_puede_volverse_hija(self):
        check_can_become_child(category_id=4, children=0)

    def test_una_categoria_con_hijas_no_puede_volverse_hija(self):
        # Es la mitad que se olvida: mover «Bebidas» —que tiene «Cervezas»—
        # debajo de «Licores» crea un tercer nivel sin crear ninguna fila.
        with pytest.raises(CategoryHasChildren) as e:
            check_can_become_child(category_id=4, children=3)
        assert (e.value.category_id, e.value.children) == (4, 3)


class TestNadieEsMadreDeSiMisma:
    def test_otra_madre_esta_bien(self):
        check_not_itself(category_id=5, parent_id=2)

    def test_sin_madre_esta_bien(self):
        # Una raíz: `parent_id` en nulo no es un ciclo.
        check_not_itself(category_id=5, parent_id=None)

    def test_ella_misma_no(self):
        # La foránea no lo impide: una fila puede apuntar a su propia clave, y
        # la categoría desaparecería de las dos listas —no es raíz porque tiene
        # madre, y no es hija de ninguna raíz—.
        with pytest.raises(CategoryIsItsOwnParent) as e:
            check_not_itself(category_id=5, parent_id=5)
        assert e.value.category_id == 5


class TestBorrar:
    """RN-7: con productos o con hijas no se borra, se desactiva."""

    def test_vacia_se_borra(self):
        check_can_delete(category_id=9, products=0, children=0)

    def test_con_productos_no(self):
        with pytest.raises(CategoryInUse) as e:
            check_can_delete(category_id=9, products=12, children=0)
        assert (e.value.products, e.value.children) == (12, 0)

    def test_con_hijas_no(self):
        with pytest.raises(CategoryInUse) as e:
            check_can_delete(category_id=9, products=0, children=2)
        assert (e.value.products, e.value.children) == (0, 2)

    def test_el_no_lleva_las_dos_cuentas(self):
        # Quien lo lee necesita saber qué mover antes de volver a intentarlo.
        with pytest.raises(CategoryInUse) as e:
            check_can_delete(category_id=9, products=12, children=2)
        assert (e.value.category_id, e.value.products, e.value.children) == (9, 12, 2)


class TestElProductoVaEnLaHoja:
    """RN-6."""

    def test_una_raiz_sin_hijas_admite_productos(self):
        check_can_hold_products(category_id=1, children=0)

    def test_una_raiz_con_hijas_no(self):
        # En la grilla de ventas el producto no aparecería en ninguna ficha.
        with pytest.raises(CategoryNeedsSubcategory) as e:
            check_can_hold_products(category_id=1, children=4)
        assert (e.value.category_id, e.value.children) == (1, 4)


class TestElOrden:
    def test_la_primera_hermana_abre_la_numeracion(self):
        assert next_order([]) == FIRST_ORDER

    def test_una_nueva_va_al_final(self):
        assert next_order([1, 2, 3]) == 4

    def test_mira_el_maximo_y_no_la_cantidad(self):
        # Con cinco hermanas y la tercera borrada quedan 1, 2, 4 y 5: contar
        # daría 5 y empataría con la última.
        assert next_order([1, 2, 4, 5]) == 6

    def test_reordenar_renumera_desde_uno(self):
        assert renumber([7, 3, 9]) == [(7, 1), (3, 2), (9, 3)]

    def test_reordenar_nada_no_es_un_error(self):
        # Una raíz recién creada, sin hijas todavía.
        assert renumber([]) == []

    def test_renumerar_arregla_huecos_y_empates(self):
        # Es la razón de renumerar todo en vez de intercambiar dos valores: los
        # huecos de los borrados y los empates que trae una migración se
        # arreglan solos cada vez que alguien reordena.
        assert renumber([4, 1, 6, 2]) == [(4, 1), (1, 2), (6, 3), (2, 4)]
