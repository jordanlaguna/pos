"""El impuesto ya no es configuración (QA-05).

Hasta el 2026-10-03 la configuración guardaba «la tasa del negocio» y la venta
la usaba de respaldo para los productos sin tarifa propia. Con la tarifa por
CABYS ese campo solo servía para equivocarse, y el usuario decidió quitarlo: el
respaldo es la general del IVA (`domain.tax.GENERAL_RATE`) y lo que llegue como
impuesto se descarta al guardar. Esto prueba la función pura que lo descarta;
el recorrido por el API está en `test_error_codes.py::TestConfiguracion`.
"""

from __future__ import annotations

import pytest

from app.domain.tax import GENERAL_RATE, TaxRate
from app.services.crud_settings import sin_impuesto


class TestSeDescarta:
    @pytest.mark.parametrize(
        "datos",
        [
            pytest.param({"tax": {"name": "IVA", "rate": 0.10}}, id="forma nueva"),
            pytest.param({"impuesto": {"nombre": "IVA", "tasa": 0.07}}, id="forma vieja"),
            pytest.param({"tax": {"rate": 5}, "impuesto": {"tasa": "mucho"}}, id="las dos, malas"),
        ],
    )
    def test_lo_que_venga_como_impuesto(self, datos):
        assert sin_impuesto({**datos, "currency": {"code": "CRC"}}) == {"currency": {"code": "CRC"}}

    def test_lo_demas_queda_como_estaba(self):
        datos = {"business": {"name": "La Esquina"}, "eInvoicing": {"enabled": True}}
        assert sin_impuesto(datos) == datos

    def test_no_toca_lo_que_recibe(self):
        datos = {"tax": {"rate": 0.13}}
        sin_impuesto(datos)
        assert datos == {"tax": {"rate": 0.13}}


def test_la_general_del_iva_es_el_13():
    assert GENERAL_RATE == TaxRate("0.13")
