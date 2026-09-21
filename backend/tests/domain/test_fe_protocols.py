"""
El protocolo de comprador (T-719, RF-70, RN-80).

**La verificación de T-719 es la última clase**: los protocolos relevados en
`docs/…/protocolos-especiales-matriz.md` se expresan como datos, sin tocar
código. Los tres que hay acá son los tres que tienen forma distinta —Walmart en
`Otros/OtroTexto`, el ICE en `InformacionReferencia`, el BCCR en
`OtroContenido`—; los demás son uno de esos tres con otro código.

Lo otro que se prueba es RN-80 por los dos lados: que un dato que falta **no se
inventa** y que tampoco se calla.
"""

from __future__ import annotations

import pytest

from app.domain.errors import DomainError
from app.domain.fe_protocols import (
    EN_OTRO_CONTENIDO,
    EN_OTRO_TEXTO,
    EN_REFERENCIA,
    Entrada,
    InvalidProtocol,
    armar,
)

FECHA = "2026-09-20T10:00:00-06:00"

#: Walmart, del instructivo de Gosocket: tres datos en `Otros/OtroTexto`, cada
#: uno con su código.
WALMART = (
    Entrada(EN_OTRO_TEXTO, "{codigo_proveedor}", codigo="WMNumeroVendedor"),
    Entrada(EN_OTRO_TEXTO, "{gln}", codigo="WMEnviarGLN"),
    Entrada(EN_OTRO_TEXTO, "{orden_compra}", codigo="WMNumeroOrden"),
)

#: El ICE: la orden de compra va como **referencia**, no en el nodo comercial.
ICE = (
    Entrada(
        EN_REFERENCIA,
        "MM-{orden_compra}",
        tipo_documento="99",
        codigo_referencia="99",
        razon="Orden de compra del ICE",
    ),
)

#: El BCCR: un `OtroContenido` con pares nombre=valor.
BCCR = (
    Entrada(
        EN_OTRO_CONTENIDO,
        "BCCR_ORDEN_PEDIDO={orden_compra}",
        codigo="BCCR_ORDEN_PEDIDO",
    ),
)


class TestLosTresFormatos:
    def test_el_de_Walmart_son_tres_OtroTexto_con_su_codigo(self):
        armado = armar(
            WALMART,
            {"codigo_proveedor": "123456", "gln": "7441000000008", "orden_compra": "OC-99"},
        )

        assert armado.faltantes == ()
        assert [(o.codigo, o.texto, o.elemento) for o in armado.otros] == [
            ("WMNumeroVendedor", "123456", "OtroTexto"),
            ("WMEnviarGLN", "7441000000008", "OtroTexto"),
            ("WMNumeroOrden", "OC-99", "OtroTexto"),
        ]

    def test_el_del_ICE_es_una_referencia_con_su_prefijo(self):
        armado = armar(ICE, {"orden_compra": "450001234"}, fecha=FECHA)

        assert armado.otros == ()
        referencia = armado.referencias[0]
        assert referencia.numero == "MM-450001234"
        assert (referencia.tipo_documento, referencia.codigo) == ("99", "99")
        assert referencia.fecha == FECHA
        assert referencia.razon == "Orden de compra del ICE"

    def test_el_del_BCCR_es_un_OtroContenido_con_pares(self):
        armado = armar(BCCR, {"orden_compra": "4200005460"})

        assert armado.otros[0].elemento == "OtroContenido"
        assert armado.otros[0].texto == "BCCR_ORDEN_PEDIDO=4200005460"

    def test_un_texto_sin_marcadores_es_una_constante(self):
        """Hay protocolos que solo piden una etiqueta fija."""
        armado = armar((Entrada(EN_OTRO_TEXTO, "Agrupamiento FEBN-0001"),), {})
        assert armado.otros[0].texto == "Agrupamiento FEBN-0001"
        assert armado.otros[0].codigo == ""


class TestLoQueFaltaNoSeInventa:
    def test_una_entrada_sin_su_dato_no_se_emite(self):
        """RN-80: `WMNumeroOrden` vacío es un dato falso, no un dato menos."""
        armado = armar(WALMART, {"codigo_proveedor": "123456", "gln": "7441000000008"})

        assert [o.codigo for o in armado.otros] == ["WMNumeroVendedor", "WMEnviarGLN"]
        assert armado.faltantes == ("orden_compra",)

    def test_y_tampoco_se_calla(self):
        """Callarlo sería emitir una factura que el comprador va a rechazar."""
        assert armar(WALMART, {}).faltantes == ("codigo_proveedor", "gln", "orden_compra")

    def test_un_dato_en_blanco_cuenta_como_ausente(self):
        armado = armar(BCCR, {"orden_compra": "   "})
        assert (armado.otros, armado.faltantes) == ((), ("orden_compra",))

    def test_los_faltantes_no_se_repiten(self):
        dos_veces = (
            Entrada(EN_OTRO_TEXTO, "{orden_compra}", codigo="A"),
            Entrada(EN_OTRO_TEXTO, "OC {orden_compra}", codigo="B"),
        )
        assert armar(dos_veces, {}).faltantes == ("orden_compra",)

    def test_los_espacios_de_alrededor_del_dato_se_recortan(self):
        armado = armar(BCCR, {"orden_compra": " 4200005460 "})
        assert armado.otros[0].texto == "BCCR_ORDEN_PEDIDO=4200005460"

    def test_sin_entradas_no_aporta_nada(self):
        armado = armar((), {"orden_compra": "OC-1"})
        assert (armado.otros, armado.referencias, armado.faltantes) == ((), (), ())


class TestLoQueNoSePuedeGuardar:
    def test_un_marcador_que_no_existe(self):
        """Un dedazo no se puede descubrir con el cliente esperando la factura."""
        with pytest.raises(InvalidProtocol) as e:
            Entrada(EN_OTRO_TEXTO, "{orden_de_compra}")
        assert (e.value.code, e.value.value) == ("unknown_placeholder", "orden_de_compra")
        assert isinstance(e.value, DomainError)

    def test_un_destino_que_no_existe(self):
        """No hay un cuarto sitio: el complemento anidado lo rechaza Hacienda."""
        with pytest.raises(InvalidProtocol) as e:
            Entrada("complemento", "{gln}")
        assert e.value.code == "unknown_destination"

    @pytest.mark.parametrize("vacia", ["", "   "])
    def test_una_plantilla_vacia(self, vacia):
        with pytest.raises(InvalidProtocol) as e:
            Entrada(EN_OTRO_TEXTO, vacia)
        assert e.value.code == "empty_template"

    def test_una_referencia_sin_tipo_de_documento(self):
        with pytest.raises(InvalidProtocol) as e:
            Entrada(EN_REFERENCIA, "{orden_compra}")
        assert e.value.code == "reference_without_type"


class TestHastaElXML:
    """Que lo armado entre en el comprobante tal cual, sin adaptadores."""

    def test_los_otros_y_las_referencias_salen_en_el_XML(self):
        from decimal import Decimal

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

        armado = armar(
            WALMART + ICE,
            {
                "codigo_proveedor": "123456",
                "gln": "7441000000008",
                "orden_compra": "450001234",
            },
            fecha=FECHA,
        )
        xml = construir(
            Comprobante(
                tipo="01",
                clave="5" * 50,
                consecutivo="0" * 20,
                fecha=FECHA,
                emisor=Parte(
                    "La Esquina S.A.",
                    Identificacion("02", "3101123456"),
                    Ubicacion("1", "01", "07", "Del parque 100 m sur"),
                    correo="fe@laesquina.cr",
                ),
                receptor=Parte("Walmart de México y Centroamérica", Identificacion("02", "3101000001")),
                proveedor_sistemas="3101702934",
                actividad_emisor="4711.1",
                condicion_venta="01",
                medios_pago=(MedioPago("01", Decimal("1130")),),
                otros=armado.otros,
                referencias=armado.referencias,
                lineas=(
                    Linea(
                        numero=1,
                        cabys="0111100000000",
                        unidad="Unid",
                        detalle="Arroz",
                        precio_unitario=Decimal("1000"),
                        impuestos=(Impuesto(codigo_tarifa="08", tarifa=Decimal("13")),),
                    ),
                ),
            )
        )

        assert '<OtroTexto codigo="WMNumeroVendedor">123456</OtroTexto>' in xml
        assert "<Numero>MM-450001234</Numero>" in xml
