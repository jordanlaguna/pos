"""El kárdex, sin base (T-1502, RN-98)."""

from __future__ import annotations

from datetime import datetime

import pytest

from dataclasses import dataclass

from app.domain.errors import (
    InsufficientStock,
    InvalidQuantity,
    InvalidStockMovementKind,
    InvalidStockSource,
    ReasonInactive,
    ReasonIsSystem,
)
from app.domain.inventory import (
    COUNT_REASON,
    DEFAULT_REASONS,
    KINDS,
    SALE,
    SOURCE_TYPES,
    ExitLine,
    Movement,
    check_exit_reason,
    check_kind,
    check_reason_deactivatable,
    check_source_type,
    exit_total,
    exit_units,
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


# ------------------------------------------------------------- la salida


@dataclass
class Motivo:
    id: int
    is_active: bool = True
    is_system: bool = False


class TestElMotivo:
    def test_toda_compania_nace_con_seis_y_solo_el_de_la_toma_es_del_sistema(self):
        assert len(DEFAULT_REASONS) == 6
        del_sistema = [codigo for codigo, _, es in DEFAULT_REASONS if es]
        assert del_sistema == [COUNT_REASON]
        assert len({codigo for codigo, _, _ in DEFAULT_REASONS}) == 6

    def test_uno_activo_de_la_compania_sirve(self):
        check_exit_reason(Motivo(1))

    def test_uno_apagado_no(self):
        with pytest.raises(ReasonInactive) as error:
            check_exit_reason(Motivo(3, is_active=False))
        assert error.value.reason_id == 3

    def test_el_de_la_toma_no_se_elige_en_una_salida(self):
        with pytest.raises(ReasonIsSystem):
            check_exit_reason(Motivo(4, is_system=True))

    def test_el_de_la_toma_tampoco_se_desactiva(self):
        check_reason_deactivatable(1, is_system=False)
        with pytest.raises(ReasonIsSystem) as error:
            check_reason_deactivatable(4, is_system=True)
        assert error.value.reason_id == 4


class TestLaLineaDeSalida:
    def test_vale_lo_que_sale_por_lo_que_cuesta(self):
        linea = ExitLine(ARROZ, 3, Money(900))
        assert linea.subtotal == Money(2700)
        assert linea.lot_id is None

    def test_el_total_y_las_unidades_suman_las_lineas(self):
        lineas = [ExitLine(ARROZ, 3, Money(900)), ExitLine(2, 1, Money.zero())]
        assert exit_total(lineas) == Money(2700)
        assert exit_units(lineas) == 4

    @pytest.mark.parametrize("cantidad", [0, -1, True, 1.5])
    def test_una_cantidad_sin_sentido(self, cantidad):
        with pytest.raises(InvalidQuantity):
            ExitLine(ARROZ, cantidad, Money(900))

    def test_un_costo_negativo_tampoco(self):
        with pytest.raises(InvalidQuantity):
            ExitLine(ARROZ, 1, Money(-1))
