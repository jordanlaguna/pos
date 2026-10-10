"""
La ficha del producto, sin base (T-1502).

Lo que se mudó de `crud_product.py` con sus reglas de siempre —código de barras,
categoría, tarifa, partida— y lo nuevo de F15: la existencia inicial es una
apertura del kárdex, la existencia no se edita, y un producto con historia no
se borra.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.product import (
    BranchRequired,
    CategoryCannotHoldProducts,
    CategoryInactive,
    CategoryNotFound,
    DeleteProduct,
    ProductHasMovements,
    ProductHasSales,
    ProductNotFound,
    ProductRequest,
    RegisterProduct,
    UpdateProduct,
)
from app.domain.errors import (
    BarcodeTaken,
    InsufficientStock,
    InvalidTariffHeading,
    MinStockNegative,
    StockNotEditable,
)
from app.domain.fe_tax_codes import InvalidTaxCode
from app.domain.inventory import OPENING
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import (
    SUCURSAL,
    FakeCategory,
    FakeCategoryRepository,
    FakeProduct,
    FakeProductRepository,
    FakeUnitOfWork,
    mover,
)

MOMENTO = datetime(2026, 10, 10, 9, 0, 0)
NACIMIENTO = datetime(2026, 1, 1)
HOJA, APAGADA, RAIZ_CON_HIJAS = 1, 2, 3


@pytest.fixture
def catalogo():
    repo = FakeProductRepository(
        [FakeProduct(1, "Arroz 1 kg", Money(1450), stock=10, category_id=HOJA)]
    )
    repo.codigos = {"7441029001057": 1}
    return repo


@pytest.fixture
def categorias():
    return FakeCategoryRepository(
        [
            FakeCategory(HOJA, "Abarrotes"),
            FakeCategory(APAGADA, "Retirada", is_active=False),
            FakeCategory(RAIZ_CON_HIJAS, "Bebidas", active_children=2),
        ]
    )


@pytest.fixture
def mundo(catalogo, categorias):
    mueve, niveles, kardex = mover(catalogo)
    uow = FakeUnitOfWork()
    alta = RegisterProduct(
        products=catalogo, categories=categorias, uow=uow, clock=FixedClock(MOMENTO), stock=mueve
    )
    editar = UpdateProduct(products=catalogo, categories=categorias, uow=uow)
    borrar = DeleteProduct(products=catalogo, kardex=kardex, uow=uow)
    return alta, editar, borrar, catalogo, kardex, uow


def peticion(**cambios) -> ProductRequest:
    base = dict(
        name="Café molido",
        description="Café",
        price=Money(4250),
        barcode="7441029001064",
        category_id=HOJA,
        created_at=NACIMIENTO,
        user_id=1,
        branch_id=SUCURSAL,
    )
    base.update(cambios)
    return ProductRequest(**base)


class TestDarDeAlta:
    def test_nace_sin_existencia_y_sin_fila_en_el_kardex(self, mundo):
        alta, _, _, catalogo, kardex, uow = mundo
        hecho = alta(peticion())

        nuevo = catalogo.get(hecho.id_product)
        assert nuevo.name == "Café molido" and nuevo.stock == 0
        assert nuevo.category_id == HOJA
        assert kardex.movimientos == [] and uow.committed

    def test_la_existencia_inicial_es_una_apertura(self, mundo):
        alta, _, _, catalogo, kardex, _ = mundo
        hecho = alta(peticion(stock=12))

        assert catalogo.get(hecho.id_product).stock == 12
        [apertura] = kardex.of_source("product", hecho.id_product)
        assert apertura.kind == OPENING
        assert (apertura.before_qty, apertura.quantity, apertura.after_qty) == (0, 12, 12)
        assert apertura.unit_cost == Money.zero() and apertura.branch_id == SUCURSAL
        assert apertura.user_id == 1 and apertura.moved_at == MOMENTO

    def test_con_existencia_pero_sin_sucursal_no_entra(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        with pytest.raises(BranchRequired):
            alta(peticion(stock=3, branch_id=None))
        assert len(catalogo.productos) == 1

    def test_sin_existencia_entra_aunque_no_haya_sucursal(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        alta(peticion(branch_id=None))
        assert len(catalogo.productos) == 2

    def test_una_existencia_negativa_no_se_abre(self, mundo):
        alta, _, _, _, kardex, uow = mundo
        with pytest.raises(InsufficientStock):
            alta(peticion(stock=-1))
        assert kardex.movimientos == [] and uow.rolled_back

    def test_el_codigo_de_tarifa_manda_sobre_la_tarifa(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        hecho = alta(peticion(tax_code="08", tax_rate=0.04))
        assert (catalogo.get(hecho.id_product).tax_code, catalogo.get(hecho.id_product).tax_rate) == (
            "08", 0.13,
        )

    def test_sin_codigo_manda_la_tarifa_del_formulario(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        hecho = alta(peticion(tax_rate=0.04))
        assert (catalogo.get(hecho.id_product).tax_code, catalogo.get(hecho.id_product).tax_rate) == (
            None, 0.04,
        )

    def test_un_codigo_de_tarifa_que_no_existe(self, mundo):
        alta, _, _, _, _, _ = mundo
        with pytest.raises(InvalidTaxCode):
            alta(peticion(tax_code="99"))

    def test_la_partida_se_sanea_o_se_rechaza(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        hecho = alta(peticion(tariff_heading="090111000000"))
        assert catalogo.get(hecho.id_product).tariff_heading == "090111000000"
        with pytest.raises(InvalidTariffHeading):
            alta(peticion(barcode="otro", tariff_heading="12"))

    def test_un_codigo_de_barras_repetido(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        with pytest.raises(BarcodeTaken):
            alta(peticion(barcode="7441029001057"))
        assert len(catalogo.productos) == 1

    def test_la_descripcion_vacia_toma_el_nombre(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        hecho = alta(peticion(description=None))
        assert catalogo.creados[-1][0] == "Café molido"
        assert catalogo.get(hecho.id_product).name == "Café molido"

    @pytest.mark.parametrize(
        "categoria,error",
        [(99, CategoryNotFound), (APAGADA, CategoryInactive), (RAIZ_CON_HIJAS, CategoryCannotHoldProducts)],
    )
    def test_la_categoria_tiene_que_poder_recibirlo(self, mundo, categoria, error):
        alta, _, _, catalogo, _, _ = mundo
        with pytest.raises(error) as excinfo:
            alta(peticion(category_id=categoria))
        assert excinfo.value.category_id == categoria
        assert len(catalogo.productos) == 1

    def test_la_raiz_con_hijas_dice_cuantas_y_como_se_llama(self, mundo):
        alta, _, _, _, _, _ = mundo
        with pytest.raises(CategoryCannotHoldProducts) as error:
            alta(peticion(category_id=RAIZ_CON_HIJAS))
        assert (error.value.name, error.value.children) == ("Bebidas", 2)


    def test_nace_sin_minimo_propio_o_con_el_que_diga(self, mundo):
        alta, _, _, catalogo, _, _ = mundo
        sin = alta(peticion()).id_product
        con = alta(peticion(barcode="7441029001071", min_stock=5)).id_product
        assert catalogo.get(sin).min_stock is None
        assert catalogo.get(con).min_stock == 5

    def test_un_minimo_negativo_no_entra(self, mundo):
        alta, _, _, catalogo, _, uow = mundo
        with pytest.raises(MinStockNegative):
            alta(peticion(min_stock=-1))
        assert not uow.committed and len(catalogo.productos) == 1


class TestEditar:
    def test_escribe_solo_lo_que_vino(self, mundo):
        _, editar, _, catalogo, _, uow = mundo
        editar(1, {"price": Money(1500), "name": None})
        assert catalogo.cambios == [(1, {"price": Money(1500)})]
        assert uow.committed

    def test_la_existencia_no_se_edita(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        with pytest.raises(StockNotEditable):
            editar(1, {"stock": 99, "price": Money(1)})
        assert catalogo.cambios == []

    def test_uno_que_no_existe(self, mundo):
        _, editar, _, _, _, _ = mundo
        with pytest.raises(ProductNotFound):
            editar(99, {"price": Money(1)})

    def test_el_codigo_de_barras_de_otro_no(self, mundo):
        alta, editar, _, _, _, _ = mundo
        otro = alta(peticion()).id_product
        with pytest.raises(BarcodeTaken):
            editar(otro, {"barcode": "7441029001057"})

    def test_el_propio_codigo_de_barras_si(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        editar(1, {"barcode": "7441029001057"})
        assert catalogo.cambios == [(1, {"barcode": "7441029001057"})]

    def test_moverlo_de_categoria_pasa_por_la_regla(self, mundo):
        _, editar, _, _, _, _ = mundo
        with pytest.raises(CategoryCannotHoldProducts):
            editar(1, {"category_id": RAIZ_CON_HIJAS})

    def test_dejarlo_en_su_categoria_no_la_revalida(self, mundo, categorias):
        # La suya se desactivó después: un cambio de precio no puede fallar por eso.
        _, editar, _, catalogo, _, _ = mundo
        categorias.categorias[HOJA].is_active = False
        editar(1, {"category_id": HOJA, "price": Money(1600)})
        assert catalogo.get(1).price == Money(1600)

    def test_el_codigo_de_tarifa_reescribe_la_tarifa(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        editar(1, {"tax_code": "08", "tax_rate": 0.04})
        assert catalogo.cambios == [(1, {"tax_code": "08", "tax_rate": 0.13})]

    def test_vaciar_el_codigo_no_toca_la_tarifa(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        editar(1, {"tax_code": ""})
        assert catalogo.cambios == [(1, {"tax_code": None})]

    def test_el_minimo_se_pone_y_se_quita(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        editar(1, {"min_stock": 4})
        assert catalogo.get(1).min_stock == 4
        # Nulo es un valor, no «no lo mandé»: vuelve al general (RN-101).
        editar(1, {"min_stock": None})
        assert catalogo.get(1).min_stock is None

    def test_un_minimo_negativo_no_se_guarda(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        with pytest.raises(MinStockNegative):
            editar(1, {"min_stock": -3})
        assert catalogo.get(1).min_stock is None

    def test_la_partida_se_sanea_y_vacia_la_quita(self, mundo):
        _, editar, _, catalogo, _, _ = mundo
        editar(1, {"tariff_heading": "090111000000"})
        editar(1, {"tariff_heading": ""})
        assert [c for _, c in catalogo.cambios] == [
            {"tariff_heading": "090111000000"},
            {"tariff_heading": None},
        ]


class TestBorrar:
    def test_uno_sin_historia_se_borra(self, mundo):
        _, _, borrar, catalogo, _, uow = mundo
        borrar(1)
        assert catalogo.borrados == [1] and 1 not in catalogo.productos
        assert uow.committed

    def test_uno_que_no_existe(self, mundo):
        _, _, borrar, _, _, _ = mundo
        with pytest.raises(ProductNotFound):
            borrar(99)

    def test_uno_ya_vendido_no(self, mundo):
        _, _, borrar, catalogo, _, _ = mundo
        catalogo.productos[1].sold = True
        with pytest.raises(ProductHasSales):
            borrar(1)
        assert catalogo.borrados == []

    def test_uno_con_kardex_tampoco_y_dice_cuantas_filas(self, mundo):
        alta, _, borrar, catalogo, _, _ = mundo
        con_apertura = alta(peticion(stock=5)).id_product
        with pytest.raises(ProductHasMovements) as error:
            borrar(con_apertura)
        assert error.value.movements == 1
        assert con_apertura in catalogo.productos
