"""El código CABYS y su tarifa (T-501, RN-11)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.cabys import (
    CabysCode,
    InvalidCabysCode,
    differs_from_official,
    normalize_code,
)
from app.domain.tax import TaxRate

IVA = TaxRate(Decimal("0.13"))
MEDICAMENTO = TaxRate(Decimal("0.02"))


class TestNormalizeCode:
    def test_trece_digitos_pasan(self):
        assert normalize_code("2312000000300") == "2312000000300"

    def test_se_recortan_los_espacios_de_alrededor(self):
        """Quien lo pega de una hoja de cálculo los arrastra."""
        assert normalize_code("  2312000000300 \n") == "2312000000300"

    def test_los_ceros_a_la_izquierda_se_conservan(self):
        """No es un número: es un identificador. `0012...` no es `12...`."""
        assert normalize_code("0012000000300") == "0012000000300"

    @pytest.mark.parametrize(
        "malo, razon",
        [
            pytest.param("", "empty", id="vacío"),
            pytest.param("   ", "empty", id="solo espacios"),
            pytest.param("231200000030", "bad_length", id="doce dígitos"),
            pytest.param("23120000003000", "bad_length", id="catorce dígitos"),
            pytest.param("2312-000000300", "not_digits", id="con guion"),
            pytest.param("231200000030A", "not_digits", id="con letra"),
            pytest.param("2312 00000 0300", "not_digits", id="con espacio adentro"),
        ],
    )
    def test_lo_que_el_catalogo_no_podria_tener(self, malo, razon):
        with pytest.raises(InvalidCabysCode) as e:
            normalize_code(malo)
        assert e.value.code == razon

    def test_no_rellena_con_ceros_un_codigo_corto(self):
        """Adivinar cuál era es peor que rechazarlo: doce dígitos no son trece a
        los que les falta algo, son un código mal copiado."""
        with pytest.raises(InvalidCabysCode):
            normalize_code("231200000030")

    @pytest.mark.parametrize("malo", [None, 2312000000300, ["2312000000300"]])
    def test_lo_que_ni_siquiera_es_texto(self, malo):
        with pytest.raises(InvalidCabysCode):
            normalize_code(malo)


class TestCabysCode:
    def test_normaliza_al_construirse(self):
        entrada = CabysCode(" 2312000000300 ", "Harina de arroz", IVA)
        assert entrada.code == "2312000000300"

    def test_un_codigo_malo_no_llega_a_existir(self):
        with pytest.raises(InvalidCabysCode):
            CabysCode("abc", "Lo que sea", IVA)

    def test_dos_iguales_son_iguales(self):
        """Es un valor, no una entidad: se compara por lo que dice."""
        uno = CabysCode("2312000000300", "Harina de arroz", IVA)
        otro = CabysCode("2312000000300", "Harina de arroz", IVA)
        assert uno == otro


class TestDifiereDeLaOficial:
    def test_la_misma_no_difiere(self):
        assert differs_from_official(IVA, IVA) is False

    def test_otra_difiere(self):
        """RN-11: se puede cambiar —hay exoneraciones— pero se avisa."""
        assert differs_from_official(MEDICAMENTO, IVA) is True

    def test_el_cero_es_una_tarifa_y_no_una_ausencia(self):
        assert differs_from_official(TaxRate.zero(), IVA) is True
        assert differs_from_official(TaxRate.zero(), TaxRate.zero()) is False
