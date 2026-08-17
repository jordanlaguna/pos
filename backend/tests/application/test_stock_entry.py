"""
Entradas de mercadería, sin base de datos.

Lo que más importa acá es lo que NO tiene que pasar: que una factura entre dos
veces, que anular deje el inventario en negativo, y que una entrada a medias
deje productos creados sueltos.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.stock_entry import (
    CancelStockEntry,
    EmptyEntry,
    EntryNotFound,
    EntryRequest,
    MissingBarcode,
    NewProduct,
    ProductNotFoundInEntry,
    RegisterStockEntry,
    RequestedEntryLine,
)
from app.domain.errors import (
    AlreadyCancelled,
    BarcodeTaken,
    CannotCancel,
    DuplicateDocument,
    InvalidQuantity,
    InvalidSource,
    LineWithoutProduct,
)
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeProduct,
    FakeProductRepository,
    FakeStockEntryRepository,
    FakeUnitOfWork,
)

MOMENTO = datetime(2026, 8, 16, 9, 0, 0)


@pytest.fixture
def catalogo():
    repo = FakeProductRepository(
        [
            FakeProduct(1, "Arroz 1 kg", Money(1450), stock=110),
            FakeProduct(2, "Café molido", Money(4250), stock=10),
        ]
    )
    repo.codigos = {"7441029001057": 1, "7441029001064": 2}
    return repo


@pytest.fixture
def escenario(catalogo):
    entradas = FakeStockEntryRepository()
    uow = FakeUnitOfWork()
    caso = RegisterStockEntry(
        products=catalogo, entries=entradas, uow=uow, clock=FixedClock(MOMENTO)
    )
    return caso, catalogo, entradas, uow


def entrada(lineas, **cambios):
    base = dict(
        document_number="FE-001",
        supplier="Distribuidora La Central S.A.",
        source="xml",
        user_id=1,
        notes=None,
        lines=lineas,
    )
    base.update(cambios)
    return EntryRequest(**base)


def linea(product_id, cantidad, costo):
    return RequestedEntryLine(
        quantity=cantidad, unit_cost=Money(costo), product_id=product_id
    )


def linea_nueva(nombre, codigo, cantidad, costo, precio=1000):
    return RequestedEntryLine(
        quantity=cantidad,
        unit_cost=Money(costo),
        new_product=NewProduct(
            name=nombre, description=None, price=Money(precio), barcode=codigo, category_id=1
        ),
    )


class TestEntradaBuena:
    def test_suma_las_existencias(self, escenario):
        caso, catalogo, _, _ = escenario
        caso(entrada([linea(1, 24, 1200)]))
        assert catalogo.get(1).stock == 134  # el invariante: 110 -> 134

    def test_devuelve_unidades_y_costo(self, escenario):
        caso, _, _, _ = escenario
        resultado = caso(entrada([linea(1, 24, 1200), linea(2, 18, 3400)]))

        assert resultado.units_added == 42
        # 24 × 1 200 + 18 × 3 400 = 28 800 + 61 200
        assert resultado.total_cost == Money(90000)
        assert resultado.products_created == 0

    def test_crea_los_productos_que_no_existian(self, escenario):
        caso, catalogo, _, _ = escenario
        resultado = caso(entrada([linea_nueva("Atún en lata", "7441029009999", 12, 800)]))

        assert resultado.products_created == 1
        nuevo = catalogo.get(3)
        assert nuevo.name == "Atún en lata"
        # Nace en cero y las unidades se las pone la entrada, por la misma vía
        # que las de cualquier otro producto.
        assert nuevo.stock == 12

    def test_la_hora_la_pone_el_servidor(self, escenario):
        caso, _, entradas, _ = escenario
        caso(entrada([linea(1, 1, 100)]))
        assert entradas.entradas[0].created_at == MOMENTO

    @pytest.mark.parametrize("origen", ["manual", "excel", "xml"])
    def test_los_tres_origenes_valen(self, escenario, origen):
        caso, _, _, _ = escenario
        caso(entrada([linea(1, 1, 100)], source=origen, document_number=None))

    def test_sin_numero_de_documento_tambien(self, escenario):
        # Una carga manual no tiene factura de proveedor.
        caso, _, _, _ = escenario
        caso(entrada([linea(1, 1, 100)], document_number=None, source="manual"))


class TestEntradaRechazada:
    def test_sin_lineas(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(EmptyEntry):
            caso(entrada([]))
        assert entradas.entradas == []

    def test_origen_desconocido(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(InvalidSource):
            caso(entrada([linea(1, 1, 100)], source="whatsapp"))
        assert entradas.entradas == []

    def test_la_misma_factura_no_entra_dos_veces(self, escenario):
        """
        Duplicarla suma el inventario en silencio, y el error solo aparece
        contando físicamente.
        """
        caso, catalogo, entradas, _ = escenario
        caso(entrada([linea(1, 24, 1200)]))

        with pytest.raises(DuplicateDocument) as e:
            caso(entrada([linea(1, 24, 1200)]))

        assert e.value.document_number == "FE-001"
        assert len(entradas.entradas) == 1
        assert catalogo.get(1).stock == 134, "se sumó dos veces"

    def test_una_anulada_libera_su_numero(self, escenario):
        # Es como se repite una carga que salió mal.
        caso, catalogo, entradas, uow = escenario
        caso(entrada([linea(1, 24, 1200)]))
        CancelStockEntry(products=catalogo, entries=entradas, uow=uow)(1)

        caso(entrada([linea(1, 24, 1200)]))
        assert len(entradas.entradas) == 2

    @pytest.mark.parametrize("cantidad", [0, -3])
    def test_cantidad_que_no_tiene_sentido(self, escenario, cantidad):
        caso, _, entradas, _ = escenario
        with pytest.raises(InvalidQuantity):
            caso(entrada([linea(1, cantidad, 100)]))
        assert entradas.entradas == []

    def test_costo_negativo(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(InvalidQuantity):
            caso(entrada([linea(1, 1, -100)]))
        assert entradas.entradas == []

    def test_costo_cero_si_vale(self, escenario):
        # Mercadería de obsequio del proveedor.
        caso, catalogo, _, _ = escenario
        caso(entrada([linea(1, 5, 0)]))
        assert catalogo.get(1).stock == 115

    def test_producto_que_no_existe(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(ProductNotFoundInEntry) as e:
            caso(entrada([linea(99, 1, 100)]))
        assert e.value.product_id == 99
        assert entradas.entradas == []

    def test_producto_nuevo_sin_codigo_de_barras(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(MissingBarcode) as e:
            caso(entrada([linea_nueva("Sin código", "   ", 1, 100)]))
        assert e.value.index == 1
        assert entradas.entradas == []

    def test_codigo_de_barras_ya_usado(self, escenario):
        caso, _, entradas, _ = escenario
        with pytest.raises(BarcodeTaken) as e:
            caso(entrada([linea_nueva("Repetido", "7441029001057", 1, 100)]))
        assert e.value.barcode == "7441029001057"
        assert entradas.entradas == []

    def test_linea_que_no_dice_que_producto(self, escenario):
        caso, _, entradas, _ = escenario
        vacia = RequestedEntryLine(quantity=1, unit_cost=Money(100))
        with pytest.raises(LineWithoutProduct) as e:
            caso(entrada([vacia]))
        assert e.value.index == 1
        assert entradas.entradas == []

    def test_si_falla_una_linea_no_entra_ninguna(self, escenario):
        """Ni siquiera el producto que alcanzó a crear una línea anterior."""
        caso, catalogo, entradas, uow = escenario
        with pytest.raises(ProductNotFoundInEntry):
            caso(
                entrada(
                    [
                        linea(1, 10, 100),
                        linea_nueva("A medias", "7441029008888", 5, 200),
                        linea(99, 1, 100),
                    ]
                )
            )

        assert entradas.entradas == []
        assert catalogo.get(1).stock == 110, "se sumó stock de una entrada que falló"
        assert uow.rolled_back


class TestAnular:
    def _con_entrada(self, escenario):
        caso, catalogo, entradas, uow = escenario
        caso(entrada([linea(1, 24, 1200)]))
        return CancelStockEntry(products=catalogo, entries=entradas, uow=uow), catalogo, entradas

    def test_devuelve_el_stock(self, escenario):
        anular, catalogo, entradas = self._con_entrada(escenario)
        assert catalogo.get(1).stock == 134

        anular(1)
        assert catalogo.get(1).stock == 110
        assert entradas.get(1).status == "anulada"

    def test_no_se_anula_dos_veces(self, escenario):
        anular, _, _ = self._con_entrada(escenario)
        anular(1)
        with pytest.raises(AlreadyCancelled):
            anular(1)

    def test_una_entrada_que_no_existe(self, escenario):
        anular, _, _ = self._con_entrada(escenario)
        with pytest.raises(EntryNotFound):
            anular(999)

    def test_no_se_anula_si_ya_se_vendio(self, escenario):
        """
        Revertir dejaría el inventario en negativo. Se avisa con el producto
        concreto en vez de romper el stock.
        """
        anular, catalogo, entradas = self._con_entrada(escenario)
        catalogo.productos[1].stock = 5  # se vendió casi todo

        with pytest.raises(CannotCancel) as e:
            anular(1)

        assert (e.value.available, e.value.added) == (5, 24)
        assert catalogo.get(1).stock == 5, "se tocó el stock pese al fallo"
        assert entradas.get(1).status == "aplicada"

    def test_se_comprueba_todo_antes_de_tocar_nada(self, escenario):
        # La primera línea se podría revertir; la segunda no. No se revierte
        # ninguna: a medias dejaría un inventario peor que el que había.
        caso, catalogo, entradas, uow = escenario
        caso(entrada([linea(1, 10, 100), linea(2, 8, 200)]))
        catalogo.productos[2].stock = 1

        anular = CancelStockEntry(products=catalogo, entries=entradas, uow=uow)
        with pytest.raises(CannotCancel):
            anular(1)

        assert catalogo.get(1).stock == 120, "se revirtió una línea de una anulación que falló"

    def test_un_producto_borrado_no_impide_anular(self, escenario):
        anular, catalogo, entradas = self._con_entrada(escenario)
        del catalogo.productos[1]

        anular(1)
        assert entradas.get(1).status == "anulada"
