"""
El catálogo de códigos de tarifa (nota 8.1, T-715, RN-76).

Lo que hay que probar no es la tabla —esa se lee— sino **las dos asimetrías**:
que de un código siempre sale una tarifa y que de una tarifa no siempre sale un
código, y que los transitorios no se proponen nunca.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import DomainError
from app.domain.fe_tax_codes import (
    purchase_line_code,
    CODES,
    GENERAL,
    ONLY_IN_NOTES,
    InvalidTaxCode,
    check_code,
    codes_for,
    only_in_notes,
    rate_for,
    suggested_code,
)
from app.domain.tax import TaxRate


class TestElCatalogo:
    def test_son_los_once_de_la_nota_8_1(self):
        assert list(CODES) == [
            "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11",
        ]

    @pytest.mark.parametrize(
        "codigo, porcentaje",
        [
            ("01", "0"),
            ("02", "1"),
            ("03", "2"),
            ("04", "4"),
            ("05", "0"),
            ("06", "4"),
            ("07", "8"),
            ("08", "13"),
            ("09", "0.5"),
            ("10", "0"),
            ("11", "0"),
        ],
    )
    def test_cada_codigo_da_su_tarifa(self, codigo, porcentaje):
        assert rate_for(codigo) == TaxRate.percent(Decimal(porcentaje))

    def test_la_general_es_la_08(self):
        assert rate_for(GENERAL) == TaxRate.percent(13)

    def test_los_transitorios_son_tres(self):
        assert ONLY_IN_NOTES == ("05", "06", "07")
        assert only_in_notes("06") is True
        assert only_in_notes("04") is False


class TestLoQueNoSeAcepta:
    @pytest.mark.parametrize("malo", ["", "8", "12", "00", "ocho", None, 8, 8.0])
    def test_un_codigo_que_no_esta_en_la_nota(self, malo):
        """El `"8"` sin cero no se corrige: puede ser un dedazo."""
        with pytest.raises(InvalidTaxCode) as e:
            check_code(malo)
        assert e.value.value == malo
        assert isinstance(e.value, DomainError)

    def test_los_espacios_de_alrededor_se_perdonan(self):
        assert check_code("  08 ") == "08"


class TestDeLaTarifaAlCodigo:
    @pytest.mark.parametrize(
        "porcentaje, codigo",
        [("13", "08"), ("4", "04"), ("2", "03"), ("1", "02"), ("0.5", "09")],
    )
    def test_cuando_hay_uno_solo_se_propone(self, porcentaje, codigo):
        assert suggested_code(TaxRate.percent(Decimal(porcentaje))) == codigo

    def test_el_cero_no_se_deduce(self):
        """RN-76: entre el 01, el 10 y el 11 no decide la aritmética.

        El 01 da derecho a crédito pleno y el 11 no da ninguno. Proponer uno
        sería elegirle a quien factura el derecho de su cliente.
        """
        assert codes_for(TaxRate.zero()) == ("01", "05", "10", "11")
        assert suggested_code(TaxRate.zero()) is None

    def test_el_ocho_por_ciento_tampoco(self):
        """Solo existe como transitorio, y un transitorio no se propone."""
        assert codes_for(TaxRate.percent(8)) == ("07",)
        assert suggested_code(TaxRate.percent(8)) is None

    def test_una_tarifa_que_no_existe_no_tiene_codigo(self):
        assert codes_for(TaxRate.percent(7)) == ()
        assert suggested_code(TaxRate.percent(7)) is None

    def test_el_cuatro_por_ciento_tiene_dos_pero_uno_es_transitorio(self):
        assert codes_for(TaxRate.percent(4)) == ("04", "06")
        assert suggested_code(TaxRate.percent(4)) == "04"


class TestElCodigoDeLaLineaDeCompra:
    """T-728, RN-53: la tarifa es la del documento del proveedor; el código, el
    del producto si dice esa tarifa, y si no el que se propone para ella."""

    def test_el_del_producto_si_dice_la_misma_tarifa(self):
        assert purchase_line_code("08", TaxRate.percent(13)) == "08"
        # Entre los tres del 0 %, el del producto decide.
        assert purchase_line_code("10", TaxRate.percent(0)) == "10"

    def test_si_el_producto_dice_otra_tarifa_manda_la_del_documento(self):
        assert purchase_line_code("08", TaxRate.percent(1)) == "02"
        assert purchase_line_code("10", TaxRate.percent(13)) == "08"

    @pytest.mark.parametrize("sin", [None, "", "99", 8])
    def test_sin_codigo_del_producto_el_que_se_propone(self, sin):
        assert purchase_line_code(sin, TaxRate.percent(13)) == "08"
        # Y en el 0 % nadie adivina el derecho a crédito.
        assert purchase_line_code(sin, TaxRate.percent(0)) is None
