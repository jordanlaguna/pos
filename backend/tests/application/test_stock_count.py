"""
La toma física, sin base (T-1503, RN-100).

Lo que importa: que `system_qty` sea lo que decía el sistema **al contar** y
no al aplicar, que dos tomas que comparten productos no coexistan, que contar
fuera del alcance sea un error, y que aplicar deje un ajuste por diferencia y
un solo asiento por la suma.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.stock_count import (
    ApplyStockCount,
    CountAlreadyOpen,
    CountCategoryNotFound,
    CountHasNoLines,
    CountNotFound,
    CountNotOpen,
    DiscardStockCount,
    OpenCountRequest,
    OpenStockCount,
    ProductNotFoundInCount,
    RecordCountLine,
)
from app.domain.errors import InsufficientStock, InvalidQuantity, OutsideCountScope
from app.domain.inventory import COUNT
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import (
    SUCURSAL,
    FakeCategory,
    FakeCategoryRepository,
    FakeProduct,
    FakeProductRepository,
    FakeStockCountRepository,
    FakeUnitOfWork,
    mover,
)

MOMENTO = datetime(2026, 10, 10, 9, 0, 0)
ARROZ, CAFE, LLANTA = 1, 2, 3
ABARROTES, BEBIDAS, CERVEZAS, YAMAHA = 1, 2, 3, 4
OTRA_SUCURSAL = 2


class LibroQueAnota:
    def __init__(self) -> None:
        self.tomas: list = []

    def record_stock_count(self, count, difference):
        self.tomas.append((count, difference))


@pytest.fixture
def catalogo():
    return FakeProductRepository(
        [
            FakeProduct(ARROZ, "Arroz 1 kg", Money(1450), stock=10, cost=Money(900), category_id=ABARROTES),
            FakeProduct(CAFE, "Cerveza", Money(1200), stock=5, cost=Money(600), category_id=CERVEZAS),
            FakeProduct(LLANTA, "Llanta", Money(45000), stock=2, category_id=YAMAHA),
        ]
    )


@pytest.fixture
def categorias():
    return FakeCategoryRepository(
        [
            FakeCategory(ABARROTES, "Abarrotes"),
            FakeCategory(BEBIDAS, "Bebidas", active_children=1),
            FakeCategory(CERVEZAS, "Cervezas", parent_id=BEBIDAS),
            FakeCategory(YAMAHA, "Yamaha"),
        ]
    )


@pytest.fixture
def mundo(catalogo, categorias):
    tomas = FakeStockCountRepository()
    mueve, niveles, kardex = mover(catalogo)
    libro = LibroQueAnota()
    uow = FakeUnitOfWork()
    reloj = FixedClock(MOMENTO)
    abrir = OpenStockCount(categories=categorias, counts=tomas, uow=uow, clock=reloj)
    contar = RecordCountLine(
        products=catalogo, categories=categorias, counts=tomas, levels=niveles, uow=uow, clock=reloj
    )
    aplicar = ApplyStockCount(
        products=catalogo, counts=tomas, uow=uow, clock=reloj, stock=mueve, ledger=libro
    )
    descartar = DiscardStockCount(counts=tomas, uow=uow, clock=reloj)
    return abrir, contar, aplicar, descartar, catalogo, tomas, kardex, libro, mueve


def abrir_en(abrir, categoria=None, sucursal=SUCURSAL, **cambios):
    base = dict(branch_id=sucursal, category_id=categoria, user_id=1, notes=None)
    base.update(cambios)
    return abrir(OpenCountRequest(**base)).id_count


class TestAbrir:
    def test_de_toda_la_sucursal(self, mundo):
        abrir, _, _, _, _, tomas, _, _, _ = mundo
        toma = abrir_en(abrir)
        fila = tomas.get(toma)
        assert (fila.branch_id, fila.category_id, fila.status) == (SUCURSAL, None, "open")
        assert fila.opened_by == 1 and fila.opened_at == MOMENTO

    def test_de_una_categoria_que_no_existe(self, mundo):
        abrir, _, _, _, _, tomas, _, _, _ = mundo
        with pytest.raises(CountCategoryNotFound):
            abrir_en(abrir, categoria=99)
        assert tomas.tomas == []

    def test_con_otra_de_toda_la_sucursal_abierta_no_cabe_ninguna(self, mundo):
        abrir, _, _, _, _, _, _, _, _ = mundo
        primera = abrir_en(abrir)
        with pytest.raises(CountAlreadyOpen) as error:
            abrir_en(abrir, categoria=YAMAHA)
        assert (error.value.count_id, error.value.branch_id, error.value.category_id) == (
            primera, SUCURSAL, None,
        )

    def test_una_raiz_bloquea_a_sus_hijas_y_viceversa(self, mundo):
        abrir, _, _, descartar, _, _, _, _, _ = mundo
        raiz = abrir_en(abrir, categoria=BEBIDAS)
        with pytest.raises(CountAlreadyOpen) as error:
            abrir_en(abrir, categoria=CERVEZAS)
        assert error.value.category_id == BEBIDAS
        descartar(raiz, user_id=1)

        abrir_en(abrir, categoria=CERVEZAS)
        with pytest.raises(CountAlreadyOpen):
            abrir_en(abrir, categoria=BEBIDAS)

    def test_dos_categorias_distintas_no_se_estorban(self, mundo):
        abrir, _, _, _, _, tomas, _, _, _ = mundo
        abrir_en(abrir, categoria=ABARROTES)
        abrir_en(abrir, categoria=YAMAHA)
        assert len(tomas.open_in_branch(SUCURSAL)) == 2

    def test_la_misma_categoria_dos_veces_no(self, mundo):
        abrir, _, _, _, _, _, _, _, _ = mundo
        abrir_en(abrir, categoria=ABARROTES)
        with pytest.raises(CountAlreadyOpen):
            abrir_en(abrir, categoria=ABARROTES)

    def test_otra_sucursal_no_estorba(self, mundo):
        abrir, _, _, _, _, tomas, _, _, _ = mundo
        abrir_en(abrir)
        abrir_en(abrir, sucursal=OTRA_SUCURSAL)
        assert len(tomas.tomas) == 2

    def test_una_cerrada_ya_no_bloquea(self, mundo):
        abrir, _, _, descartar, _, _, _, _, _ = mundo
        descartar(abrir_en(abrir), user_id=1)
        abrir_en(abrir)


class TestContar:
    def test_guarda_lo_que_decia_el_sistema_al_contar(self, mundo):
        abrir, contar, _, _, _, tomas, _, _, _ = mundo
        toma = abrir_en(abrir)
        contada = contar(toma, product_id=ARROZ, counted_qty=8, user_id=2)

        assert (contada.system_qty, contada.counted_qty, contada.difference) == (10, 8, -2)
        [linea] = tomas.lines_of(toma)
        assert (linea.system_qty, linea.counted_qty, linea.counted_by) == (10, 8, 2)
        assert linea.counted_at == MOMENTO and linea.lot_id is None

    def test_volver_a_contar_reemplaza(self, mundo):
        abrir, contar, _, _, _, tomas, _, _, _ = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)
        contar(toma, product_id=ARROZ, counted_qty=9, user_id=1)
        [linea] = tomas.lines_of(toma)
        assert linea.counted_qty == 9

    def test_una_toma_de_la_raiz_acepta_sus_hijas(self, mundo):
        abrir, contar, _, _, _, _, _, _, _ = mundo
        toma = abrir_en(abrir, categoria=BEBIDAS)
        assert contar(toma, product_id=CAFE, counted_qty=5, user_id=1).difference == 0

    def test_fuera_del_alcance_es_un_error(self, mundo):
        abrir, contar, _, _, _, tomas, _, _, _ = mundo
        toma = abrir_en(abrir, categoria=ABARROTES)
        with pytest.raises(OutsideCountScope) as error:
            contar(toma, product_id=LLANTA, counted_qty=1, user_id=1)
        assert (error.value.product_id, error.value.category_id, error.value.scope_category_id) == (
            LLANTA, YAMAHA, ABARROTES,
        )
        assert tomas.lines_of(toma) == []

    def test_un_producto_que_no_existe(self, mundo):
        abrir, contar, _, _, _, _, _, _, _ = mundo
        toma = abrir_en(abrir)
        with pytest.raises(ProductNotFoundInCount):
            contar(toma, product_id=99, counted_qty=1, user_id=1)

    @pytest.mark.parametrize("contado", [-1, 1.5, True])
    def test_lo_contado_es_un_entero_de_cero_para_arriba(self, mundo, contado):
        abrir, contar, _, _, _, _, _, _, _ = mundo
        toma = abrir_en(abrir)
        with pytest.raises(InvalidQuantity):
            contar(toma, product_id=ARROZ, counted_qty=contado, user_id=1)

    def test_en_una_que_no_existe_o_no_esta_abierta(self, mundo):
        abrir, contar, _, descartar, _, _, _, _, _ = mundo
        with pytest.raises(CountNotFound):
            contar(99, product_id=ARROZ, counted_qty=1, user_id=1)
        toma = abrir_en(abrir)
        descartar(toma, user_id=1)
        with pytest.raises(CountNotOpen) as error:
            contar(toma, product_id=ARROZ, counted_qty=1, user_id=1)
        assert error.value.status == "discarded"


class TestAplicar:
    def test_cada_diferencia_deja_su_ajuste_y_la_suma_su_asiento(self, mundo):
        abrir, contar, aplicar, _, catalogo, tomas, kardex, libro, _ = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)   # −2 × 900
        contar(toma, product_id=CAFE, counted_qty=6, user_id=1)    # +1 × 600
        contar(toma, product_id=LLANTA, counted_qty=2, user_id=1)  # cuadra

        aplicada = aplicar(toma, user_id=3)

        assert aplicada.adjustments == 2
        assert aplicada.difference_cost == Money(-1200)
        assert catalogo.get(ARROZ).stock == 8 and catalogo.get(CAFE).stock == 6
        filas = kardex.of_source("stock_count", toma)
        assert [(f.kind, f.product_id, f.quantity, f.before_qty, f.after_qty, f.unit_cost, f.source_line)
                for f in filas] == [
            (COUNT, ARROZ, -2, 10, 8, Money(900), 1),
            (COUNT, CAFE, 1, 5, 6, Money(600), 2),
        ]
        assert all(f.user_id == 3 and f.moved_at == MOMENTO for f in filas)
        fila = tomas.get(toma)
        assert (fila.status, fila.closed_by, fila.closed_at) == ("applied", 3, MOMENTO)
        [(documento, diferencia)] = libro.tomas
        assert documento.id == toma and diferencia == Money(-1200)

    def test_vender_entre_contar_y_aplicar_no_cambia_el_ajuste(self, mundo):
        """La verificación de T-1503: la diferencia es contra lo que decía el
        sistema al contar, y lo vendido ya quedó en el kárdex por su lado."""
        abrir, contar, aplicar, _, catalogo, _, kardex, _, mueve = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)
        mueve(product_id=ARROZ, branch_id=SUCURSAL, delta=-1, kind="sale", unit_cost=Money(900),
              source_type="sale", source_id=50, user_id=1, moved_at=MOMENTO)

        aplicar(toma, user_id=1)

        [ajuste] = kardex.of_source("stock_count", toma)
        assert (ajuste.quantity, ajuste.before_qty, ajuste.after_qty) == (-2, 9, 7)
        assert catalogo.get(ARROZ).stock == 7

    def test_una_toma_que_cuadro_no_deja_asiento(self, mundo):
        abrir, contar, aplicar, _, _, _, kardex, libro, _ = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=10, user_id=1)
        aplicada = aplicar(toma, user_id=1)
        assert aplicada.adjustments == 0 and aplicada.difference_cost == Money.zero()
        assert kardex.of_source("stock_count", toma) == []
        [(_, diferencia)] = libro.tomas
        assert diferencia == Money.zero()

    def test_sin_lineas_no_se_aplica(self, mundo):
        abrir, _, aplicar, _, _, tomas, _, _, _ = mundo
        toma = abrir_en(abrir)
        with pytest.raises(CountHasNoLines):
            aplicar(toma, user_id=1)
        assert tomas.get(toma).status == "open"

    def test_si_se_vendio_mas_de_lo_que_la_toma_quita_se_vuelve_a_contar(self, mundo):
        abrir, contar, aplicar, _, _, tomas, _, _, mueve = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)   # −2
        mueve(product_id=ARROZ, branch_id=SUCURSAL, delta=-9, kind="sale", unit_cost=Money(900),
              source_type="sale", source_id=50, user_id=1, moved_at=MOMENTO)
        with pytest.raises(InsufficientStock):
            aplicar(toma, user_id=1)
        assert tomas.get(toma).status == "open"

    def test_no_se_aplica_dos_veces(self, mundo):
        abrir, contar, aplicar, _, _, _, _, _, _ = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)
        aplicar(toma, user_id=1)
        with pytest.raises(CountNotOpen):
            aplicar(toma, user_id=1)
        with pytest.raises(CountNotFound):
            aplicar(99, user_id=1)

    def test_sin_libro_tambien(self, catalogo, categorias):
        tomas = FakeStockCountRepository()
        mueve, niveles, _ = mover(catalogo)
        abrir = OpenStockCount(categories=categorias, counts=tomas, uow=FakeUnitOfWork(), clock=FixedClock(MOMENTO))
        contar = RecordCountLine(products=catalogo, categories=categorias, counts=tomas, levels=niveles,
                                 uow=FakeUnitOfWork(), clock=FixedClock(MOMENTO))
        aplicar = ApplyStockCount(products=catalogo, counts=tomas, uow=FakeUnitOfWork(),
                                  clock=FixedClock(MOMENTO), stock=mueve)
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)
        assert aplicar(toma, user_id=1).adjustments == 1


class TestDescartar:
    def test_no_toca_nada(self, mundo):
        abrir, contar, _, descartar, catalogo, tomas, kardex, _, _ = mundo
        toma = abrir_en(abrir)
        contar(toma, product_id=ARROZ, counted_qty=8, user_id=1)
        descartar(toma, user_id=4)
        fila = tomas.get(toma)
        assert (fila.status, fila.closed_by, fila.closed_at) == ("discarded", 4, MOMENTO)
        assert catalogo.get(ARROZ).stock == 10 and kardex.movimientos == []

    def test_una_que_no_existe_o_ya_cerro(self, mundo):
        abrir, _, _, descartar, _, _, _, _, _ = mundo
        with pytest.raises(CountNotFound):
            descartar(99, user_id=1)
        toma = abrir_en(abrir)
        descartar(toma, user_id=1)
        with pytest.raises(CountNotOpen):
            descartar(toma, user_id=1)
