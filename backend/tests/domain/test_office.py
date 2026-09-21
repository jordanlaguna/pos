"""Los códigos de sucursal y de terminal (T-608b, RN-15)."""

import pytest

from app.domain.errors import InvalidOfficeCode
from app.domain.office import BRANCH_DIGITS, TERMINAL_DIGITS, BranchCode, TerminalCode


class TestSeRellenaConCeros:
    """Lo que pide la tarea: «1» se guarda como «001»."""

    def test_la_sucursal(self):
        assert str(BranchCode("1")) == "001"

    def test_la_terminal(self):
        assert str(TerminalCode("1")) == "00001"

    def test_un_numero_tambien_sirve(self):
        # Quien lo escribe piensa en el número, no en la tira de texto.
        assert str(BranchCode(7)) == "007"

    def test_el_que_ya_viene_completo_no_se_toca(self):
        assert str(BranchCode("042")) == "042"
        assert str(TerminalCode("00123")) == "00123"

    def test_los_espacios_de_los_bordes_se_recortan(self):
        assert str(BranchCode("  5 ")) == "005"

    def test_rellenar_es_lo_que_evita_dos_filas_para_la_misma_caja(self):
        # El UNIQUE es sobre el texto, así que sin normalizar, «1» y «001»
        # serían dos sucursales distintas con el mismo número en el comprobante.
        assert BranchCode("1") == BranchCode("001")
        assert BranchCode("1") == BranchCode(1)


class TestLoQueNoSeGuarda:
    """Lo otro que pide la tarea: «abc» no se guarda."""

    @pytest.mark.parametrize("malo", ["abc", "00a", "1-2", "1 2", "٣۴"[:1] + "x"])
    def test_lo_que_no_son_digitos(self, malo):
        with pytest.raises(InvalidOfficeCode) as e:
            BranchCode(malo)
        assert e.value.code == "not_digits"

    @pytest.mark.parametrize("vacio", ["", "   "])
    def test_vacio(self, vacio):
        with pytest.raises(InvalidOfficeCode) as e:
            BranchCode(vacio)
        assert e.value.code == "empty"

    @pytest.mark.parametrize("malo", [None, 3.5, ["1"]])
    def test_lo_que_ni_siquiera_es_un_codigo(self, malo):
        with pytest.raises(InvalidOfficeCode) as e:
            BranchCode(malo)
        assert e.value.code == "not_text"

    def test_un_booleano_no_es_un_uno(self):
        # `True` es un `int` en Python y daría «001» sin este control.
        with pytest.raises(InvalidOfficeCode) as e:
            BranchCode(True)
        assert e.value.code == "not_text"

    def test_lo_que_no_cabe(self):
        with pytest.raises(InvalidOfficeCode) as e:
            BranchCode("1234")
        assert e.value.code == "too_long"
        # El «no» dice cuántos dígitos había: es lo único que le explica a quien
        # escribió de más cuánto le sobra.
        assert e.value.digits == BRANCH_DIGITS

    def test_recortar_en_silencio_seria_cambiarle_el_numero_a_alguien(self):
        # «1234» no se guarda como «234». Es el defecto que este tipo existe
        # para no tener: dos cajas distintas con el mismo código.
        with pytest.raises(InvalidOfficeCode):
            BranchCode("1234")

    def test_la_terminal_admite_mas_pero_tampoco_infinito(self):
        assert str(TerminalCode("99999")) == "99999"
        with pytest.raises(InvalidOfficeCode) as e:
            TerminalCode("100000")
        assert (e.value.code, e.value.digits) == ("too_long", TERMINAL_DIGITS)


class TestLosCerosDeMasNoEstorban:
    def test_ceros_a_la_izquierda_de_sobra_caben_si_el_numero_cabe(self):
        # «00001» con tres dígitos es 1, y 1 cabe. Se miden los dígitos
        # significativos, no la longitud del texto que alguien pegó.
        assert str(BranchCode("00001")) == "001"

    def test_el_cero_es_un_codigo(self):
        # No es «vacío»: hay sistemas que numeran la casa matriz como 000.
        assert str(BranchCode("0")) == "000"
        assert str(BranchCode("000")) == "000"


class TestSeComparanYSeOrdenan:
    def test_dos_iguales_son_iguales(self):
        assert BranchCode("003") == BranchCode("3")

    def test_se_ordenan_por_su_texto(self):
        assert sorted([BranchCode("010"), BranchCode("2")]) == [
            BranchCode("002"),
            BranchCode("010"),
        ]

    def test_una_sucursal_no_es_una_terminal(self):
        # Los dos son tres y cinco dígitos por una razón, y confundirlos pone el
        # número en el tramo equivocado de la clave.
        assert BranchCode("001") != TerminalCode("00001")
