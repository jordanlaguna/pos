from decimal import Decimal

import pytest

from app.domain.errors import InvalidTaxRate
from app.domain.money import Money
from app.domain.tax import TaxRate

IVA = TaxRate("0.13")


class TestConstruccion:
    def test_acepta_las_formas_razonables(self):
        assert TaxRate("0.13") == TaxRate(0.13) == TaxRate(Decimal("0.13"))

    def test_desde_porcentaje(self):
        assert TaxRate.percent(13) == IVA
        assert TaxRate.percent("4.5") == TaxRate("0.045")

    def test_cero_es_valido(self):
        # Hay productos exentos; una tasa de cero no es un error.
        assert TaxRate.zero() == TaxRate(0)
        assert TaxRate.zero().apply(Money(1000)) == Money.zero()

    def test_uno_es_valido(self):
        assert TaxRate(1).apply(Money(1000)) == Money(1000)

    @pytest.mark.parametrize("malo", [13, -0.01, 1.01, 100, "13"])
    def test_rechaza_lo_que_esta_fuera_de_0_a_1(self, malo):
        # El error caro: escribir 13 en vez de 0,13 multiplica la factura por 14.
        with pytest.raises(InvalidTaxRate):
            TaxRate(malo)

    @pytest.mark.parametrize("malo", [None, [], object(), "abc", float("nan"), True])
    def test_rechaza_lo_que_no_es_un_numero(self, malo):
        with pytest.raises(InvalidTaxRate):
            TaxRate(malo)

    def test_percent_tambien_valida(self):
        with pytest.raises(InvalidTaxRate):
            TaxRate.percent(200)
        with pytest.raises(InvalidTaxRate):
            TaxRate.percent("abc")

    def test_el_error_lleva_el_valor(self):
        with pytest.raises(InvalidTaxRate) as e:
            TaxRate(13)
        assert e.value.value == 13


class TestAplicar:
    def test_el_impuesto_de_un_monto(self):
        assert IVA.apply(Money(4350)) == Money(565.5)
        assert IVA.apply(Money(5700)) == Money(741)
        assert IVA.apply(Money(5130)) == Money(666.9)

    def test_el_monto_con_impuesto(self):
        assert IVA.add_to(Money(4350)) == Money(4915.5)
        assert IVA.add_to(Money(1450)) == Money(1638.5)

    def test_se_lee_como_porcentaje(self):
        assert IVA.as_percent == Decimal(13)
        assert str(IVA) == "13 %"
        assert str(TaxRate("0.045")) == "4.5 %"

    def test_se_ordenan(self):
        assert TaxRate("0.02") < IVA


class TestDeUnaVenta:
    """La regla de las devoluciones: se reembolsa con la tasa de SU venta."""

    def test_reconstruye_la_tasa_de_los_montos(self):
        assert TaxRate.of_sale(Money(4350), Money(565.5), default=TaxRate.zero()) == IVA

    def test_una_venta_cobrada_al_5_por_ciento_devuelve_al_5(self):
        tasa = TaxRate.of_sale(Money(1000), Money(50), default=IVA)
        assert tasa == TaxRate("0.05")
        assert tasa.add_to(Money(1000)) == Money(1050)

    def test_una_venta_exenta_devuelve_sin_impuesto(self):
        assert TaxRate.of_sale(Money(1000), Money.zero(), default=IVA) == TaxRate.zero()

    def test_sin_subtotal_usa_la_de_referencia(self):
        # Una venta regalada, o una fila a medias: no hay nada que dividir.
        assert TaxRate.of_sale(Money.zero(), Money.zero(), default=IVA) == IVA
        assert TaxRate.of_sale(Money(-10), Money(1), default=IVA) == IVA

    def test_subir_el_iva_no_cambia_lo_que_se_reembolsa(self):
        vendida_al_13 = TaxRate.of_sale(Money(1000), Money(130), default=TaxRate("0.15"))
        assert vendida_al_13.add_to(Money(1000)) == Money(1130)
