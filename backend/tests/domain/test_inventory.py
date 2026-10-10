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


# --------------------------------------------------------- la toma física

from app.domain.inventory import (  # noqa: E402
    COUNT_APPLIED,
    COUNT_DISCARDED,
    COUNT_OPEN,
    CountScope,
    check_count_scope,
    check_counted_quantity,
    count_difference,
    scope_includes,
    scopes_overlap,
)
from app.domain.errors import OutsideCountScope  # noqa: E402

ABARROTES, BEBIDAS, CERVEZAS, VINOS, YAMAHA = 1, 2, 3, 4, 5
#: Dos niveles (RN-5): Bebidas tiene a Cervezas y Vinos; las demás son raíces.
ARBOL = {ABARROTES: None, BEBIDAS: None, CERVEZAS: BEBIDAS, VINOS: BEBIDAS, YAMAHA: None}


class TestLaDiferencia:
    def test_contar_de_menos_es_negativa(self):
        assert count_difference(10, 8) == -2

    def test_contar_de_mas_es_positiva(self):
        assert count_difference(10, 12) == 2

    def test_cuadrar_es_cero(self):
        assert count_difference(10, 10) == 0

    @pytest.mark.parametrize("contado", [-1, 1.5, True, "8"])
    def test_lo_contado_es_un_entero_de_cero_para_arriba(self, contado):
        with pytest.raises(InvalidQuantity):
            count_difference(10, contado)
        with pytest.raises(InvalidQuantity):
            check_counted_quantity(contado)

    def test_cero_contado_vale(self):
        assert count_difference(3, 0) == -3

    def test_los_estados_son_tres(self):
        assert (COUNT_OPEN, COUNT_APPLIED, COUNT_DISCARDED) == ("open", "applied", "discarded")


class TestElAlcance:
    def test_toda_la_sucursal_incluye_todo(self):
        assert scope_includes(CountScope(1), YAMAHA, ARBOL)

    def test_una_categoria_se_incluye_a_si_misma_y_a_sus_hijas(self):
        bebidas = CountScope(1, BEBIDAS)
        assert scope_includes(bebidas, BEBIDAS, ARBOL)
        assert scope_includes(bebidas, CERVEZAS, ARBOL)
        assert not scope_includes(bebidas, YAMAHA, ARBOL)

    def test_una_hija_no_incluye_a_su_madre_ni_a_su_hermana(self):
        cervezas = CountScope(1, CERVEZAS)
        assert not scope_includes(cervezas, BEBIDAS, ARBOL)
        assert not scope_includes(cervezas, VINOS, ARBOL)

    def test_contar_fuera_del_alcance_es_un_error(self):
        check_count_scope(CountScope(1, BEBIDAS), 7, CERVEZAS, ARBOL)
        with pytest.raises(OutsideCountScope) as error:
            check_count_scope(CountScope(1, ABARROTES), 7, CERVEZAS, ARBOL)
        assert (error.value.product_id, error.value.category_id, error.value.scope_category_id) == (
            7, CERVEZAS, ABARROTES,
        )


class TestDosTomasALaVez:
    def test_toda_la_sucursal_choca_con_cualquiera(self):
        assert scopes_overlap(CountScope(1), CountScope(1, YAMAHA), ARBOL)
        assert scopes_overlap(CountScope(1, YAMAHA), CountScope(1), ARBOL)
        assert scopes_overlap(CountScope(1), CountScope(1), ARBOL)

    def test_la_raiz_choca_con_su_hija_en_los_dos_sentidos(self):
        assert scopes_overlap(CountScope(1, BEBIDAS), CountScope(1, CERVEZAS), ARBOL)
        assert scopes_overlap(CountScope(1, CERVEZAS), CountScope(1, BEBIDAS), ARBOL)

    def test_dos_hojas_distintas_no(self):
        assert not scopes_overlap(CountScope(1, CERVEZAS), CountScope(1, VINOS), ARBOL)
        assert not scopes_overlap(CountScope(1, ABARROTES), CountScope(1, YAMAHA), ARBOL)

    def test_la_misma_categoria_si(self):
        assert scopes_overlap(CountScope(1, ABARROTES), CountScope(1, ABARROTES), ARBOL)

    def test_otra_sucursal_nunca(self):
        assert not scopes_overlap(CountScope(1), CountScope(2), ARBOL)
