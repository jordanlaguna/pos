import pytest

from app.domain.errors import (
    EmptySale,
    InsufficientPayment,
    InsufficientStock,
    InvalidQuantity,
    TotalsMismatch,
)
from app.domain.money import Money
from app.domain.sale import (
    TOTALS_TOLERANCE,
    SaleLine,
    Totals,
    change_due,
    check_declared_totals,
    check_payment,
    check_stock,
    is_payment_enough,
    sale_totals,
)
from app.domain.tax import TaxRate

IVA = TaxRate("0.13")


def linea(precio, cantidad=1, product_id=1):
    return SaleLine(product_id=product_id, unit_price=Money(precio), quantity=cantidad)


class TestSaleLine:
    def test_el_subtotal_es_precio_por_cantidad(self):
        assert linea(1450, 3).subtotal == Money(4350)

    @pytest.mark.parametrize("mala", [0, -1, 1.5, "3", None, True])
    def test_rechaza_cantidades_que_no_tienen_sentido(self, mala):
        with pytest.raises(InvalidQuantity):
            linea(1450, mala)

    def test_rechaza_un_precio_negativo(self):
        with pytest.raises(InvalidQuantity):
            linea(-1450, 1)

    def test_un_precio_de_cero_si_vale(self):
        # Promociones y artículos de regalo existen.
        assert linea(0, 2).subtotal == Money.zero()


class TestTotales:
    """Las cifras de .specify/progress.json, sin base de datos de por medio."""

    def test_tres_unidades_de_1450(self):
        t = sale_totals([linea(1450, 3)], IVA)
        assert (t.subtotal, t.tax, t.total) == (Money(4350), Money(565.5), Money(4915.5))

    def test_arroz_mas_cafe(self):
        t = sale_totals([linea(1450, 1, 1), linea(4250, 1, 2)], IVA)
        assert (t.subtotal, t.tax, t.total) == (Money(5700), Money(741), Money(6441))

    def test_la_factura_de_ejemplo(self):
        t = sale_totals([linea(1450, 1, 1), linea(950, 1, 2), linea(2730, 1, 3)], IVA)
        assert (t.subtotal, t.tax, t.total) == (Money(5130), Money(666.9), Money(5796.9))

    def test_una_venta_exenta(self):
        t = sale_totals([linea(1450, 2)], TaxRate.zero())
        assert (t.subtotal, t.tax, t.total) == (Money(2900), Money.zero(), Money(2900))

    def test_una_venta_sin_lineas_no_es_una_venta(self):
        with pytest.raises(EmptySale):
            sale_totals([], IVA)

    def test_redondea_linea_por_linea(self):
        # 3 × 0,335 → 0,34 cada una = 1,02. Sumando primero daría 1,01.
        t = sale_totals([linea("0.335", 1, i) for i in range(3)], TaxRate.zero())
        assert t.subtotal == Money("1.02")


class TestVuelto:
    def test_devuelve_la_diferencia(self):
        assert change_due(Money(5000), Money(4915.5)) == Money(84.5)
        assert change_due(Money(10000), Money(6441)) == Money(3559)
        assert change_due(Money(6000), Money(5796.9)) == Money(203.1)

    def test_pago_exacto(self):
        assert change_due(Money(4915.5), Money(4915.5)) == Money.zero()

    def test_nunca_es_negativo(self):
        # Un vuelto en rojo se lee como si el cliente debiera plata.
        assert change_due(Money(1000), Money(4915.5)) == Money.zero()

    def test_quien_decide_si_alcanza_es_otra_funcion(self):
        assert is_payment_enough(Money(5000), Money(4915.5))
        assert is_payment_enough(Money(4915.5), Money(4915.5))
        assert not is_payment_enough(Money(4915), Money(4915.5))


class TestCotejoDeTotales:
    """Lo que declara el POS contra lo que calcula el servidor."""

    calculado = sale_totals([linea(1450, 3)], IVA)

    def test_cuando_coinciden_no_pasa_nada(self):
        check_declared_totals(self.calculado, self.calculado)

    def test_un_centimo_de_diferencia_se_tolera(self):
        # El POS calcula en binario y el servidor en decimal exacto: en los
        # empates a medio céntimo difieren en 0,01 y las dos cifras son buenas.
        assert TOTALS_TOLERANCE == Money("0.01")
        declarado = Totals(
            subtotal=Money(4350), tax=Money("565.51"), total=Money("4915.51")
        )
        check_declared_totals(declarado, self.calculado)

    @pytest.mark.parametrize("campo", ["subtotal", "tax", "total"])
    def test_mas_de_un_centimo_no(self, campo):
        valores = {"subtotal": Money(4350), "tax": Money("565.50"), "total": Money("4915.50")}
        valores[campo] = valores[campo] + Money("0.02")

        with pytest.raises(TotalsMismatch) as e:
            check_declared_totals(Totals(**{"subtotal": valores["subtotal"], "tax": valores["tax"], "total": valores["total"]}), self.calculado)
        assert e.value.campo in ("subtotal", "impuesto", "total")

    def test_se_miran_las_tres_cifras_y_no_solo_el_total(self):
        # Un subtotal y un impuesto que se compensan dan el mismo total y son,
        # aun así, un error.
        declarado = Totals(subtotal=Money(4000), tax=Money("915.50"), total=Money("4915.50"))
        with pytest.raises(TotalsMismatch) as e:
            check_declared_totals(declarado, self.calculado)
        assert e.value.campo == "subtotal"


class TestCotejoDelPago:
    def test_alcanza(self):
        check_payment(Money(5000), Money("4915.50"))
        check_payment(Money("4915.50"), Money("4915.50"))

    def test_no_alcanza(self):
        with pytest.raises(InsufficientPayment) as e:
            check_payment(Money(4915), Money("4915.50"))
        assert e.value.received == Money(4915)


class TestExistencias:
    def test_alcanza(self):
        check_stock(product_id=7, available=10, requested=3)
        check_stock(product_id=7, available=3, requested=3)

    def test_no_alcanza(self):
        with pytest.raises(InsufficientStock) as e:
            check_stock(product_id=7, available=2, requested=5)
        assert (e.value.product_id, e.value.available, e.value.requested) == (7, 2, 5)
