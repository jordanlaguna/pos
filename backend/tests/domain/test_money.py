from decimal import Decimal

import pytest

from app.domain.errors import InvalidAmount
from app.domain.money import CENTS, Money


class TestConstruccion:
    def test_acepta_entero_texto_decimal_y_float(self):
        assert Money(1450) == Money("1450") == Money(Decimal("1450")) == Money(1450.0)

    def test_normaliza_a_dos_decimales(self):
        assert Money("1450.000").amount == Decimal("1450.00")
        assert str(Money(1450)) == "1450.00"

    def test_dos_montos_que_valen_lo_mismo_son_iguales(self):
        # Sin normalizar al construir, Decimal('1450') != Decimal('1450.00').
        assert Money("1450") == Money("1450.00")
        assert len({Money(1450), Money("1450.000")}) == 1

    def test_un_float_no_arrastra_su_expansion_binaria(self):
        # Decimal(0.1) da 0.1000000000000000055511151231257827...
        assert Money(0.1).amount == Decimal("0.10")

    def test_envuelve_a_otro_Money_sin_cambiarlo(self):
        assert Money(Money(1450)) == Money(1450)

    def test_cero(self):
        assert Money.zero() == Money(0)
        assert Money.zero().is_zero

    @pytest.mark.parametrize(
        "malo", ["", "  ", "abc", None, [], {}, object(), float("nan"), float("inf")]
    )
    def test_rechaza_lo_que_no_es_un_monto(self, malo):
        with pytest.raises(InvalidAmount):
            Money(malo)

    def test_rechaza_booleanos(self):
        # True es 1 en Python. Un booleano donde va plata es un error de quien
        # llama, no un colón.
        with pytest.raises(InvalidAmount):
            Money(True)

    def test_el_error_lleva_el_valor_que_lo_causo(self):
        with pytest.raises(InvalidAmount) as e:
            Money("abc")
        assert e.value.value == "abc"

    def test_un_Decimal_no_finito(self):
        with pytest.raises(InvalidAmount):
            Money(Decimal("NaN"))


class TestAritmetica:
    def test_suma_y_resta(self):
        assert Money(1450) + Money(4250) == Money(5700)
        assert Money(5000) - Money(4915.5) == Money(84.5)

    def test_opera_contra_numeros_sueltos(self):
        assert Money(1450) + 50 == Money(1500)
        assert Money(1450) - "450" == Money(1000)

    def test_multiplica_por_una_cantidad(self):
        assert Money(1450) * 3 == Money(4350)
        assert 3 * Money(1450) == Money(4350)

    def test_multiplica_por_una_tasa(self):
        assert Money(4350) * Decimal("0.13") == Money(565.5)

    def test_no_se_multiplica_plata_por_plata(self):
        with pytest.raises(InvalidAmount):
            Money(1450) * Money(3)

    def test_negativo_y_absoluto(self):
        assert -Money(277) == Money(-277)
        assert abs(Money(-277)) == Money(277)

    def test_no_acumula_centavos_fantasma(self):
        # Es el motivo entero de que este módulo exista.
        assert Money("0.1") + Money("0.2") == Money("0.3")
        assert Money.sum([Money("0.1")] * 10) == Money(1)

    def test_suma_de_una_lista_vacia(self):
        assert Money.sum([]) == Money.zero()

    def test_redondea_en_cada_paso_y_no_al_final(self):
        # Tres líneas de 0,335: 0,34 cada una da 1,02; al final daría 1,01.
        assert Money.sum([Money("0.335")] * 3) == Money("1.02")


class TestPreguntas:
    def test_signo(self):
        assert Money(1).is_positive and not Money(1).is_negative
        assert Money(-1).is_negative and not Money(-1).is_positive
        assert Money(0).is_zero
        assert not Money(0).is_positive
        assert not Money(0).is_negative

    def test_se_ordenan(self):
        assert Money(100) < Money(200)
        assert max([Money(100), Money(300), Money(200)]) == Money(300)


class TestSalida:
    def test_as_float_para_la_frontera(self):
        assert Money("4915.50").as_float() == 4915.5
        assert isinstance(Money(1450).as_float(), float)

    def test_texto_con_dos_decimales_siempre(self):
        assert str(Money(1450)) == "1450.00"
        assert str(Money("-277")) == "-277.00"


class TestRedondeo:
    def test_el_paso_es_de_un_centavo(self):
        assert CENTS == Decimal("0.01")

    def test_el_empate_se_aleja_del_cero(self):
        """
        ROUND_HALF_UP, el redondeo comercial: es lo que hacía el WinForms con
        `.ToString("0.00")` y lo que hace el POS. Hasta el 2026-08-16 este
        backend usaba el bancario —`ROUND_HALF_EVEN`, el valor por omisión de
        Python que nadie eligió— y daba 2,66 donde la pantalla decía 2,67.
        """
        assert Money("2.665") == Money("2.67")
        assert Money("2.675") == Money("2.68")
        assert Money("1.005") == Money("1.01")
        assert Money("0.125") == Money("0.13")

    def test_y_tambien_en_los_negativos(self):
        # Alejarse del cero, no «hacia arriba»: −2,665 va a −2,67, no a −2,66.
        assert Money("-2.665") == Money("-2.67")
        assert Money("-1.005") == Money("-1.01")

    def test_no_es_el_redondeo_bancario(self):
        # Con ROUND_HALF_EVEN, 2,665 daría 2,66 por ser par el dígito anterior.
        assert Money("2.665") != Money("2.66")
