import pytest

from app.domain.cash import (
    MOVEMENT_TYPES,
    CashCount,
    check_movement,
    check_opening,
    difference,
    expected_amount,
)
from app.domain.errors import InsufficientCash, InvalidMovement
from app.domain.money import Money


def conteo(apertura=0, ventas=0, entradas=0, salidas=0, devoluciones=0):
    return CashCount(
        opening=Money(apertura),
        cash_sales=Money(ventas),
        movements_in=Money(entradas),
        movements_out=Money(salidas),
        returns=Money(devoluciones),
    )


class TestEsperado:
    def test_el_invariante_de_progress_json(self):
        # 50 000 + 4 915,50 − 1 638,50 = 53 277,00
        assert expected_amount(
            conteo(apertura=50000, ventas=4915.5, devoluciones=1638.5)
        ) == Money(53277)

    def test_una_caja_recien_abierta_tiene_su_fondo(self):
        assert expected_amount(conteo(apertura=50000)) == Money(50000)

    def test_entradas_suman_y_salidas_restan(self):
        assert expected_amount(conteo(apertura=1000, entradas=500, salidas=200)) == Money(1300)

    def test_una_caja_vacia(self):
        assert expected_amount(conteo()) == Money.zero()

    def test_las_devoluciones_salen_de_la_gaveta(self):
        assert expected_amount(conteo(apertura=1000, devoluciones=1638.5)) == Money("-638.50")


class TestDiferencia:
    def test_faltante(self):
        # Contando 53 000 sobre 53 277 esperados.
        assert difference(Money(53000), Money(53277)) == Money(-277)

    def test_sobrante(self):
        assert difference(Money(53500), Money(53277)) == Money(223)

    def test_cuadra(self):
        assert difference(Money(53277), Money(53277)).is_zero


class TestMovimientos:
    def test_una_entrada_valida(self):
        check_movement("entrada", Money(500), "fondo adicional", Money(1000))

    def test_una_salida_dentro_de_lo_disponible(self):
        check_movement("salida", Money(500), "pago a proveedor", Money(1000))
        check_movement("salida", Money(1000), "vaciar caja", Money(1000))

    def test_no_se_saca_mas_de_lo_que_hay(self):
        # Sin esto el esperado queda negativo y el arqueo deja de significar nada.
        with pytest.raises(InsufficientCash) as e:
            check_movement("salida", Money(1500), "de más", Money(1000))
        assert e.value.available == Money(1000)

    def test_sacar_de_mas_solo_aplica_a_las_salidas(self):
        check_movement("entrada", Money(99999), "depósito", Money(0))

    @pytest.mark.parametrize("tipo", ["deposito", "", "ENTRADA", None])
    def test_rechaza_tipos_desconocidos(self, tipo):
        with pytest.raises(InvalidMovement):
            check_movement(tipo, Money(100), "motivo", Money(1000))

    @pytest.mark.parametrize("monto", [0, -100])
    def test_rechaza_montos_que_no_son_positivos(self, monto):
        with pytest.raises(InvalidMovement):
            check_movement("entrada", Money(monto), "motivo", Money(1000))

    @pytest.mark.parametrize("motivo", ["", "   ", None])
    def test_exige_motivo(self, motivo):
        # Un movimiento sin motivo es plata que se movió y nadie sabe por qué.
        with pytest.raises(InvalidMovement):
            check_movement("entrada", Money(100), motivo, Money(1000))

    def test_los_dos_tipos_son_los_que_dice_la_constante(self):
        assert MOVEMENT_TYPES == ("entrada", "salida")


class TestApertura:
    def test_cero_vale(self):
        check_opening(Money.zero())

    def test_un_fondo_normal(self):
        check_opening(Money(50000))

    def test_negativo_no(self):
        with pytest.raises(InvalidMovement):
            check_opening(Money(-1))
