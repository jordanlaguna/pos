import pytest

from app.domain.errors import ExcessiveReturn, InvalidQuantity, NotSoldInThisSale
from app.domain.money import Money
from app.domain.returns import (
    ReturnLine,
    check_returnable,
    is_fully_returned,
    refund_total,
    remaining_units,
)
from app.domain.tax import TaxRate

IVA = TaxRate("0.13")


class TestReturnLine:
    def test_el_subtotal_es_precio_por_cantidad(self):
        assert ReturnLine(1, Money(1450), 2).subtotal == Money(2900)

    @pytest.mark.parametrize("mala", [0, -1, 1.5, "2", None, True])
    def test_rechaza_cantidades_que_no_tienen_sentido(self, mala):
        with pytest.raises(InvalidQuantity):
            ReturnLine(1, Money(1450), mala)


class TestUnidadesQueQuedan:
    def test_sin_devoluciones_previas_queda_todo(self):
        assert remaining_units(sold=3, already_returned=0) == 3

    def test_con_una_parcial_queda_el_resto(self):
        assert remaining_units(sold=3, already_returned=1) == 2

    def test_devuelto_del_todo(self):
        assert remaining_units(sold=3, already_returned=3) == 0

    def test_nunca_negativo(self):
        # Si por lo que sea hay más devuelto que vendido, quedan cero, no −1.
        assert remaining_units(sold=3, already_returned=5) == 0


class TestSePuedeDevolver:
    vendido = {7: 3, 9: 1}

    def test_lo_que_se_llevo_y_no_ha_devuelto(self):
        check_returnable(7, self.vendido, {}, requested=3)
        check_returnable(9, self.vendido, {}, requested=1)

    def test_lo_que_queda_tras_una_parcial(self):
        check_returnable(7, self.vendido, {7: 1}, requested=2)

    def test_no_se_devuelve_lo_que_la_venta_no_llevaba(self):
        with pytest.raises(NotSoldInThisSale) as e:
            check_returnable(99, self.vendido, {}, requested=1)
        assert e.value.product_id == 99

    def test_no_se_devuelve_mas_de_lo_que_se_llevo(self):
        with pytest.raises(ExcessiveReturn) as e:
            check_returnable(7, self.vendido, {}, requested=4)
        assert (e.value.remaining, e.value.requested) == (3, 4)

    def test_ni_sumando_varias_parciales(self):
        # Es la regla que impide devolver la misma unidad dos veces.
        with pytest.raises(ExcessiveReturn) as e:
            check_returnable(7, self.vendido, {7: 2}, requested=2)
        assert e.value.remaining == 1

    def test_nada_que_devolver(self):
        with pytest.raises(ExcessiveReturn):
            check_returnable(9, self.vendido, {9: 1}, requested=1)


class TestDevueltaDelTodo:
    def test_sin_devoluciones_no(self):
        assert not is_fully_returned({7: 3}, {})

    def test_con_una_parcial_tampoco(self):
        assert not is_fully_returned({7: 3, 9: 1}, {7: 3})

    def test_con_todo_devuelto_si(self):
        assert is_fully_returned({7: 3, 9: 1}, {7: 3, 9: 1})

    def test_con_mas_devuelto_que_vendido_tambien(self):
        assert is_fully_returned({7: 3}, {7: 5})

    def test_una_venta_sin_lineas_cuenta_como_devuelta(self):
        # No queda nada por devolver. Es `all()` sobre vacío, y acá es correcto.
        assert is_fully_returned({}, {})


class TestReembolso:
    def test_el_invariante_de_progress_json(self):
        # Una unidad de 1450 al 13 % → 1 638,50
        assert refund_total([ReturnLine(1, Money(1450), 1)], IVA) == Money(1638.5)

    def test_varias_lineas(self):
        lineas = [ReturnLine(1, Money(1450), 2), ReturnLine(2, Money(950), 1)]
        # (2900 + 950) × 1,13
        assert refund_total(lineas, IVA) == Money("4350.50")

    def test_con_la_tasa_de_su_venta_y_no_con_la_de_hoy(self):
        vendida_al_5 = TaxRate.of_sale(Money(1000), Money(50), default=IVA)
        assert refund_total([ReturnLine(1, Money(1000), 1)], vendida_al_5) == Money(1050)

    def test_una_venta_exenta_se_devuelve_sin_impuesto(self):
        assert refund_total([ReturnLine(1, Money(1000), 1)], TaxRate.zero()) == Money(1000)

    def test_sin_lineas_no_se_devuelve_nada(self):
        assert refund_total([], IVA) == Money.zero()
