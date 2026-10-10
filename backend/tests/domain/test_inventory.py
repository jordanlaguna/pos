"""El kárdex, sin base (T-1502, RN-98)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.errors import (
    InsufficientStock,
    InvalidQuantity,
    InvalidStockMovementKind,
    InvalidStockSource,
)
from app.domain.inventory import (
    KINDS,
    SALE,
    SOURCE_TYPES,
    Movement,
    check_kind,
    check_source_type,
    move,
)
from app.domain.money import Money

ARROZ = 7
MOMENTO = datetime(2026, 10, 10, 9, 0, 0)


class TestMove:
    def test_vender_tres_de_diez_deja_siete(self):
        assert move(ARROZ, 10, -3) == (10, 7)

    def test_entrar_cinco_a_un_producto_en_cero(self):
        assert move(ARROZ, 0, 5) == (0, 5)

    def test_lo_que_no_hay_no_se_puede_sacar(self):
        with pytest.raises(InsufficientStock) as error:
            move(ARROZ, 2, -3)
        assert error.value.product_id == ARROZ
        assert error.value.available == 2
        assert error.value.requested == 3

    def test_sacar_exactamente_lo_que_hay_deja_cero(self):
        assert move(ARROZ, 3, -3) == (3, 0)

    @pytest.mark.parametrize("delta", [0, True, 1.5, "3"])
    def test_mover_nada_o_algo_que_no_es_una_cantidad(self, delta):
        with pytest.raises(InvalidQuantity):
            move(ARROZ, 10, delta)


class TestTipos:
    def test_son_once_y_el_origen_siete(self):
        assert len(KINDS) == 11
        assert len(SOURCE_TYPES) == 7

    def test_un_tipo_que_no_existe(self):
        with pytest.raises(InvalidStockMovementKind) as error:
            check_kind("venta")
        assert error.value.kind == "venta"

    def test_un_origen_que_no_existe(self):
        with pytest.raises(InvalidStockSource) as error:
            check_source_type("ventas")
        assert error.value.source_type == "ventas"


def movimiento(**cambios) -> Movement:
    base = dict(
        product_id=ARROZ,
        branch_id=1,
        kind=SALE,
        quantity=-3,
        before_qty=10,
        after_qty=7,
        unit_cost=Money(900),
        avg_cost_after=Money(900),
        source_type="sale",
        source_id=50,
        user_id=1,
        moved_at=MOMENTO,
    )
    base.update(cambios)
    return Movement(**base)


class TestMovement:
    def test_nace_sin_id_sin_linea_y_sin_lote(self):
        m = movimiento()
        assert (m.id, m.source_line, m.lot_id) == (None, None, None)

    def test_el_antes_y_el_despues_tienen_que_cuadrar(self):
        with pytest.raises(InvalidQuantity):
            movimiento(before_qty=10, quantity=-3, after_qty=8)

    def test_rechaza_un_tipo_que_no_existe(self):
        with pytest.raises(InvalidStockMovementKind):
            movimiento(kind="venta")

    def test_rechaza_un_origen_que_no_existe(self):
        with pytest.raises(InvalidStockSource):
            movimiento(source_type="ventas")
