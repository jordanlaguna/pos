"""
El IVA devuelto de los servicios de salud (T-718, RF-68, RN-79).

La verificación de T-718 es la primera clase: **una venta de servicios médicos
cobrada con tarjeta lo declara; la misma cobrada en efectivo, no.** El resto es
el prorrateo, que es la parte que se olvida y la que Hacienda rechaza.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.fe_payment_methods import CARD, CASH, SINPE, code_for
from app.domain.fe_vat_refund import (
    Payment,
    TaxedLine,
    card_share,
    is_health_service,
    vat_refund,
)

#: El del ejemplo real de `docs/…/protocolos/`: consulta médica.
CONSULTA = TaxedLine(cabys="9310100000100", tax=Decimal("4000"))
ARROZ = TaxedLine(cabys="0111100000000", tax=Decimal("130"))


class TestQueCABYSEsSalud:
    @pytest.mark.parametrize("codigo", ["9310100000100", "9312000000000", "931"])
    def test_el_grupo_931_es_servicio_de_salud(self, codigo):
        assert is_health_service(codigo)

    @pytest.mark.parametrize(
        "codigo",
        [
            "9320000000000",  # atención residencial
            "9330000000000",  # asistencia social
            "0111100000000",  # arroz
            "",
            None,
            931,
        ],
    )
    def test_y_lo_demas_no(self, codigo):
        """`932` y `933` son atención residencial y asistencia social.

        Están en la misma división 93 y no son el servicio médico del que habla
        la ley, así que tomarse la división entera declararía IVA devuelto de
        más —y eso Hacienda lo rechaza—.
        """
        assert not is_health_service(codigo)


class TestLaVerificacionDeT718:
    def test_servicios_medicos_con_tarjeta_lo_declaran(self):
        devuelto = vat_refund([CONSULTA], [Payment(CARD, Decimal("104000"))])
        assert devuelto == Decimal("4000.00000")

    def test_y_los_mismos_en_efectivo_no(self):
        assert vat_refund([CONSULTA], [Payment(CASH, Decimal("104000"))]) == Decimal(0)

    def test_una_venta_que_no_es_de_salud_tampoco(self):
        assert vat_refund([ARROZ], [Payment(CARD, Decimal("1130"))]) == Decimal(0)

    def test_solo_cuenta_el_impuesto_de_las_lineas_de_salud(self):
        """En la misma factura pueden ir una consulta y una caja de gasas."""
        devuelto = vat_refund([CONSULTA, ARROZ], [Payment(CARD, Decimal("105130"))])
        assert devuelto == Decimal("4000.00000")


class TestElProrrateo:
    def test_la_mitad_en_tarjeta_devuelve_la_mitad(self):
        """El campo es el impuesto pagado **en tarjeta**, no el de las líneas.

        Declararlo entero cuando se pagó la mitad en efectivo es un rechazo.
        """
        devuelto = vat_refund(
            [CONSULTA],
            [Payment(CASH, Decimal("52000")), Payment(CARD, Decimal("52000"))],
        )
        assert devuelto == Decimal("2000.00000")

    def test_un_tercio_en_tarjeta_devuelve_un_tercio(self):
        devuelto = vat_refund(
            [CONSULTA],
            [Payment(CASH, Decimal("2")), Payment(CARD, Decimal("1"))],
        )
        assert devuelto == Decimal("1333.33333")

    def test_sin_pagos_no_se_devuelve_nada(self):
        """Una venta a crédito no se pagó con tarjeta: se pagará.

        Con qué, lo dirá el recibo electrónico de pago.
        """
        assert vat_refund([CONSULTA], []) == Decimal(0)
        assert card_share([]) == Decimal(0)

    def test_ni_con_pagos_en_cero(self):
        assert card_share([Payment(CARD, Decimal(0))]) == Decimal(0)

    def test_el_pago_movil_no_es_tarjeta(self):
        """SINPE MÓVIL es su propio código. La devolución es de la tarjeta."""
        assert vat_refund([CONSULTA], [Payment(SINPE, Decimal("104000"))]) == Decimal(0)


class TestHastaElXML:
    """La verificación de T-718 dicha entera: de la venta al comprobante.

    Las dos mitades por separado ya están probadas; esto comprueba que se
    encuentran, que es donde se pierden las reglas.
    """

    @staticmethod
    def _comprobante(medio: str, devuelto: Decimal) -> str:
        from app.domain.fe_xml import (
            Comprobante,
            Identificacion,
            Impuesto,
            Linea,
            MedioPago,
            Parte,
            Ubicacion,
            construir,
        )

        return construir(
            Comprobante(
                tipo="01",
                clave="5" * 50,
                consecutivo="0" * 20,
                fecha="2026-09-20T10:00:00-06:00",
                emisor=Parte(
                    "Clínica del Este S.A.",
                    Identificacion("02", "3101123456"),
                    Ubicacion("1", "01", "07", "Del parque 100 m sur"),
                    correo="fe@clinica.cr",
                ),
                receptor=Parte("Ana Castro", Identificacion("01", "115670987")),
                proveedor_sistemas="3101702934",
                actividad_emisor="8690.9",
                condicion_venta="01",
                medios_pago=(MedioPago(medio, Decimal("104000")),),
                iva_devuelto=devuelto,
                lineas=(
                    Linea(
                        numero=1,
                        cabys=CONSULTA.cabys,
                        unidad="Os",
                        detalle="Consulta médica",
                        precio_unitario=Decimal("100000"),
                        impuestos=(Impuesto(codigo_tarifa="04", tarifa=Decimal("4")),),
                    ),
                ),
            )
        )

    def test_con_tarjeta_el_comprobante_lo_declara_y_lo_resta(self):
        pagos = [Payment(CARD, Decimal("104000"))]
        xml = self._comprobante(CARD, vat_refund([CONSULTA], pagos))

        assert "<TotalIVADevuelto>4000.00000</TotalIVADevuelto>" in xml
        # Y por eso el total es el servicio, no el servicio más el impuesto.
        assert "<TotalComprobante>100000.00000</TotalComprobante>" in xml

    def test_en_efectivo_no_lo_declara_y_el_total_lleva_el_impuesto(self):
        pagos = [Payment(CASH, Decimal("104000"))]
        xml = self._comprobante(CASH, vat_refund([CONSULTA], pagos))

        assert "TotalIVADevuelto" not in xml
        assert "<TotalComprobante>104000.00000</TotalComprobante>" in xml


class TestElMapeoDeMediosDePago:
    @pytest.mark.parametrize(
        "guardado, codigo",
        [
            ("Efectivo", "01"),
            ("Tarjeta de crédito", "02"),
            ("Transferencia bancaria", "04"),
            ("Pago móvil", "06"),
        ],
    )
    def test_cada_medio_del_POS_tiene_su_codigo(self, guardado, codigo):
        assert code_for(guardado) == codigo
