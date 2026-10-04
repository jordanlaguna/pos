"""
Lo que una venta necesita para salir como factura de exportación (RF-78, T-727):
la partida de cada mercancía, una tarifa que la FEE admita y la dirección del
cliente. Sin base y sin red: entra lo que la venta leyó y sale el error con el
producto que falta.
"""

from __future__ import annotations

import pytest

from app.domain.errors import (
    ExportLineNeedsTariffHeading,
    ExportNeedsForeignAddress,
    ExportTariffNotAllowed,
    InvalidForeignAddress,
    InvalidTariffHeading,
)
from app.domain.fe_export import (
    FOREIGN_ADDRESS_MAX_LENGTH,
    TARIFF_HEADING_LENGTH,
    ExportLine,
    check_export_lines,
    check_foreign_address,
    check_tariff_heading,
    is_merchandise,
    normalize_foreign_address,
)
from app.domain.tax import TaxRate

PARTIDA = "090111000000"
MERCANCIA = "2316100000100"
SERVICIO = "8595400000000"


def linea(**cambios) -> ExportLine:
    base = dict(product_id=7, cabys_code=MERCANCIA, tariff_heading=PARTIDA, tax_code="08")
    base.update(cambios)
    return ExportLine(**base)


class TestLaPartida:
    def test_son_doce_digitos(self):
        assert TARIFF_HEADING_LENGTH == 12
        assert check_tariff_heading(PARTIDA) == PARTIDA

    def test_se_limpia(self):
        assert check_tariff_heading(f"  {PARTIDA} ") == PARTIDA

    @pytest.mark.parametrize("vacia", [None, "", "   "])
    def test_vacia_es_no_tiene(self, vacia):
        assert check_tariff_heading(vacia) is None

    @pytest.mark.parametrize("mala", ["0901110000", "0901110000001", "09011100000A", 90111000000])
    def test_otra_cosa_se_rechaza(self, mala):
        with pytest.raises(InvalidTariffHeading) as e:
            check_tariff_heading(mala)
        assert e.value.value == mala


class TestMercanciaOServicio:
    def test_lo_dice_el_cabys(self):
        assert is_merchandise(MERCANCIA)
        assert not is_merchandise(SERVICIO)

    @pytest.mark.parametrize("sin", [None, ""])
    def test_sin_cabys_es_mercancia(self, sin):
        # Es lo que vende un mostrador, y de todos modos se detiene por el CABYS.
        assert is_merchandise(sin)


class TestLasLineas:
    def test_una_mercancia_con_partida_y_tarifa_general_pasa(self):
        check_export_lines([linea()])

    def test_un_servicio_no_necesita_partida(self):
        check_export_lines([linea(cabys_code=SERVICIO, tariff_heading=None)])

    @pytest.mark.parametrize("sin", [None, ""])
    def test_una_mercancia_sin_partida_dice_cual(self, sin):
        with pytest.raises(ExportLineNeedsTariffHeading) as e:
            check_export_lines([linea(product_id=3), linea(product_id=9, tariff_heading=sin)])
        assert e.value.product_id == 9

    @pytest.mark.parametrize("codigo", ["01", "11"])
    def test_la_tarifa_no_sujeta_no_cabe_en_la_exportacion(self, codigo):
        with pytest.raises(ExportTariffNotAllowed) as e:
            check_export_lines([linea(product_id=4, tax_code=codigo)])
        assert (e.value.product_id, e.value.tax_code) == (4, codigo)

    def test_la_tarifa_se_mira_antes_que_la_partida(self):
        # Las dos faltan; la primera que se dice es la tarifa, que es la que no
        # tiene arreglo en la ficha del producto sin cambiar lo que se vende.
        with pytest.raises(ExportTariffNotAllowed):
            check_export_lines([linea(tax_code="11", tariff_heading=None)])

    def test_sin_codigo_vale_el_que_se_propone_para_la_tarifa(self):
        # Un producto del 13 % sin clasificar lleva el 08, como en el armador.
        assert linea(tax_code=None, tax_rate=TaxRate("0.13")).effective_tax_code == "08"
        check_export_lines([linea(tax_code=None, tax_rate=TaxRate("0.13"))])

    def test_sin_codigo_ni_tarifa_no_se_sabe_y_no_se_dice_nada_aqui(self):
        # Eso lo detiene el armador con «linea_sin_codigo_de_tarifa».
        assert linea(tax_code=None, tax_rate=None).effective_tax_code is None
        check_export_lines([linea(tax_code=None, tax_rate=None)])

    def test_el_cero_por_ciento_sin_codigo_tampoco_se_decide_aqui(self):
        # Entre el 01, el 10 y el 11 no decide la aritmética (fe_tax_codes).
        assert linea(tax_code=None, tax_rate=TaxRate("0")).effective_tax_code is None

    def test_sin_lineas_no_hay_nada_que_decir(self):
        check_export_lines([])


class TestLaDireccion:
    def test_se_limpia_y_se_devuelve(self):
        assert check_foreign_address(5, "  12 Main St, Miami  ") == "12 Main St, Miami"

    def test_mas_larga_que_el_xml_se_rechaza_y_nunca_se_recorta(self):
        # Una sola política del largo: la ficha la rechaza con el código, y el
        # comprobante no recorta lo que la ficha dejó pasar.
        assert FOREIGN_ADDRESS_MAX_LENGTH == 300
        assert normalize_foreign_address("x" * 300) == "x" * 300
        with pytest.raises(InvalidForeignAddress) as e:
            normalize_foreign_address("x" * 301)
        assert (e.value.length, e.value.max_length) == (301, 300)
        with pytest.raises(InvalidForeignAddress):
            check_foreign_address(5, "x" * 400)

    @pytest.mark.parametrize("vacia", [None, "", "   ", 7])
    def test_en_blanco_es_nula_al_guardar(self, vacia):
        assert normalize_foreign_address(vacia) is None

    @pytest.mark.parametrize("sin", [None, "", "  ", 7])
    def test_sin_direccion_dice_de_cual_cliente(self, sin):
        with pytest.raises(ExportNeedsForeignAddress) as e:
            check_foreign_address(5, sin)
        assert e.value.client_id == 5
