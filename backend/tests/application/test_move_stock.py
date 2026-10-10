"""
El único escritor de existencias, sin base (T-1502, plan §15.1).

Lo que importa acá es el orden —el producto antes que el nivel, el costo leído
bajo el candado— y que un movimiento que no se puede no deje nada escrito.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.ports.inventory import NullKardex
from app.application.use_cases.move_stock import MoveStock, ProductMissing
from app.domain.errors import InsufficientStock
from app.domain.inventory import ENTRY, SALE
from app.domain.money import Money

from .fakes import FakeKardex, FakeProduct, FakeProductRepository, FakeStockLevelRepository, mover

MOMENTO = datetime(2026, 10, 10, 9, 0, 0)
ARROZ = 1
CAFE = 2
LOCAL_1 = 1
LOCAL_2 = 2


@pytest.fixture
def catalogo():
    return FakeProductRepository(
        [
            FakeProduct(ARROZ, "Arroz 1 kg", Money(1450), stock=10, cost=Money(900)),
            FakeProduct(CAFE, "Café molido", Money(4250), stock=0),
        ]
    )


def venta(mueve, producto=ARROZ, cantidad=3, sucursal=LOCAL_1, **cambios):
    base = dict(
        product_id=producto,
        branch_id=sucursal,
        delta=-cantidad,
        kind=SALE,
        unit_cost=Money(900),
        source_type="sale",
        source_id=50,
        source_line=1,
        user_id=1,
        moved_at=MOMENTO,
    )
    base.update(cambios)
    return mueve(**base)


class TestUnMovimiento:
    def test_deja_la_fila_con_antes_y_despues(self, catalogo):
        mueve, niveles, kardex = mover(catalogo)
        hecho = venta(mueve)

        assert (hecho.before_qty, hecho.quantity, hecho.after_qty) == (10, -3, 7)
        assert hecho.kind == SALE
        assert hecho.source_type == "sale" and hecho.source_id == 50 and hecho.source_line == 1
        assert hecho.moved_at == MOMENTO
        assert kardex.movimientos == [hecho]

    def test_el_id_lo_pone_quien_lo_guarda(self, catalogo):
        mueve, _, _ = mover(catalogo)
        assert venta(mueve).id == 1
        assert venta(mueve).id == 2

    def test_mantiene_el_nivel_y_la_suma_de_la_ficha(self, catalogo):
        mueve, niveles, _ = mover(catalogo)
        venta(mueve)

        assert niveles.levels_of(ARROZ) == {LOCAL_1: 7}
        assert catalogo.get(ARROZ).stock == 7

    def test_el_promedio_anotado_es_el_que_tiene_el_producto_al_moverse(self, catalogo):
        # La entrada escribe el costo ANTES de mover (plan §15.1): lo que se
        # anota es ese, no el de antes de la compra.
        mueve, _, _ = mover(catalogo)
        catalogo.update_cost(ARROZ, Money(1000))

        hecho = venta(mueve, cantidad=5, delta=5, kind=ENTRY, unit_cost=Money(1200),
                      source_type="stock_entry", source_id=9)

        assert hecho.unit_cost == Money(1200)
        assert hecho.avg_cost_after == Money(1000)

    def test_un_producto_sin_costo_anota_cero(self, catalogo):
        mueve, _, _ = mover(catalogo)
        hecho = venta(mueve, producto=CAFE, cantidad=2, delta=2, kind=ENTRY,
                      unit_cost=Money(100), source_type="stock_entry", source_id=9)
        assert hecho.avg_cost_after == Money.zero()


class TestLoQueNoSePuede:
    def test_lo_que_no_hay_no_sale_y_no_queda_nada_escrito(self, catalogo):
        mueve, niveles, kardex = mover(catalogo)

        with pytest.raises(InsufficientStock) as error:
            venta(mueve, cantidad=11)

        assert error.value.available == 10 and error.value.requested == 11
        assert kardex.movimientos == []
        assert niveles.levels_of(ARROZ) == {LOCAL_1: 10}
        assert catalogo.get(ARROZ).stock == 10

    def test_un_producto_que_no_esta(self, catalogo):
        mueve, _, kardex = mover(catalogo)
        with pytest.raises(ProductMissing) as error:
            venta(mueve, producto=99)
        assert error.value.product_id == 99
        assert kardex.movimientos == []


class TestLosCandados:
    def test_el_producto_se_bloquea_antes_que_el_nivel(self, catalogo):
        """Dos órdenes distintos son un abrazo mortal en la caja (plan §15.1)."""
        mueve, niveles, _ = mover(catalogo)
        orden: list[str] = []
        bloquear_producto = catalogo.lock
        bloquear_nivel = niveles.lock
        catalogo.lock = lambda ids: (orden.append("producto"), bloquear_producto(ids))[1]
        niveles.lock = lambda p, b: (orden.append("nivel"), bloquear_nivel(p, b))[1]

        venta(mueve)

        assert orden == ["producto", "nivel"]
        assert catalogo.bloqueados == [[ARROZ]]
        assert niveles.bloqueados == [(ARROZ, LOCAL_1)]


class TestPorSucursal:
    def test_el_antes_y_el_despues_son_de_esa_sucursal(self, catalogo):
        """RN-102: diez en el local 1 no son diez en el local 2."""
        mueve, niveles, _ = mover(catalogo)

        with pytest.raises(InsufficientStock) as error:
            venta(mueve, sucursal=LOCAL_2, cantidad=1)
        assert error.value.available == 0

        entrada = venta(mueve, sucursal=LOCAL_2, cantidad=4, delta=4, kind=ENTRY,
                        source_type="stock_entry", source_id=9)
        assert (entrada.before_qty, entrada.after_qty) == (0, 4)
        # El local 1 no aparece: el doble siembra un nivel cuando alguien lo
        # bloquea, igual que la base crea la fila con el candado (§15.1).
        assert niveles.levels_of(ARROZ) == {LOCAL_2: 4}
        assert niveles.levels_in(LOCAL_2) == {ARROZ: 4}
        # La ficha es la suma de las dos.
        assert catalogo.get(ARROZ).stock == 14
        assert niveles.lock(ARROZ, LOCAL_1) == 10


class TestElKardexNulo:
    def test_no_anota_y_el_movimiento_sale_sin_id(self, catalogo):
        mueve = MoveStock(
            products=catalogo, levels=FakeStockLevelRepository(catalogo), kardex=NullKardex()
        )
        hecho = venta(mueve)
        assert hecho.id == 0
        assert catalogo.get(ARROZ).stock == 7


class TestElKardexDeMentira:
    """El doble lee como va a leer el adaptador: por producto, filtrado, y por origen."""

    def test_por_producto_del_mas_reciente_al_mas_viejo_y_filtrado(self, catalogo):
        mueve, _, kardex = mover(catalogo)
        primero = venta(mueve, moved_at=datetime(2026, 10, 1))
        segundo = venta(mueve, moved_at=datetime(2026, 10, 5), sucursal=LOCAL_2, cantidad=2,
                        delta=2, kind=ENTRY, source_type="stock_entry", source_id=9)

        assert kardex.of_product(ARROZ) == [segundo, primero]
        assert kardex.of_product(ARROZ, branch_id=LOCAL_2) == [segundo]
        assert kardex.of_product(ARROZ, since=datetime(2026, 10, 2)) == [segundo]
        assert kardex.of_product(ARROZ, until=datetime(2026, 10, 2)) == [primero]
        assert kardex.of_product(CAFE) == []

    def test_por_origen_en_el_orden_en_que_se_anoto(self, catalogo):
        mueve, _, kardex = mover(catalogo)
        a = venta(mueve, source_line=1)
        b = venta(mueve, source_line=2)
        venta(mueve, source_id=51)

        assert kardex.of_source("sale", 50) == [a, b]
        assert kardex.of_source("sale", 99) == []

    def test_las_pruebas_pueden_traer_su_propio_kardex(self, catalogo):
        propio = FakeKardex()
        _, _, usado = mover(catalogo, propio)
        assert usado is propio
