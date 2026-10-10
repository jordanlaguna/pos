"""La ficha del producto, sin base (T-1502)."""

from __future__ import annotations

import pytest

from app.domain.errors import StockNotEditable
from app.domain.fe_tax_codes import InvalidTaxCode
from app.domain.product import CLEARABLE, clean_changes, resolve_tax


class TestElCodigoMandaSobreLaTarifa:
    def test_con_codigo_la_tarifa_sale_de_el(self):
        assert resolve_tax("08", 0.04) == ("08", 0.13)

    def test_sin_codigo_manda_lo_que_venga_incluido_el_nulo(self):
        assert resolve_tax(None, 0.04) == (None, 0.04)
        assert resolve_tax("", None) == (None, None)

    def test_un_codigo_que_no_existe(self):
        with pytest.raises(InvalidTaxCode):
            resolve_tax("99", None)


class TestLoQueCambiaUnPutParcial:
    def test_un_nulo_es_no_lo_mande(self):
        assert clean_changes(1, {"name": None, "price": 1200}) == {"price": 1200}

    def test_en_las_vaciables_el_nulo_es_el_valor(self):
        assert clean_changes(1, {"tax_rate": None, "cabys_code": None}) == {
            "tax_rate": None,
            "cabys_code": None,
        }

    def test_y_la_cadena_vacia_tambien(self):
        assert clean_changes(1, {"tax_code": "", "name": ""}) == {"tax_code": None, "name": ""}

    def test_son_cinco(self):
        # El mínimo entró en F15 (RN-101): vaciarlo es volver al general.
        assert CLEARABLE == {"cabys_code", "tax_rate", "tax_code", "tariff_heading", "min_stock"}

    def test_la_existencia_no_se_edita(self):
        with pytest.raises(StockNotEditable) as error:
            clean_changes(7, {"stock": 99})
        assert error.value.product_id == 7

    def test_un_stock_en_nulo_es_no_lo_mande(self):
        assert clean_changes(7, {"stock": None, "price": 5}) == {"price": 5}
