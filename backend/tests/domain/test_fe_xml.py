"""
El armador del comprobante 4.4 (T-714 y T-720, RF-65 a RF-71).

**La prueba que vale de verdad es la última**: los siete tipos se validan contra
el XSD oficial de `docs/hacienda/costa-rica/esquemas/`, cada uno contra el suyo.
Las demás comprueban la aritmética y el orden, que es lo que el XSD no dice o
dice tarde; esa comprueba que el resultado es un comprobante de Hacienda y no
algo que se le parece.

Las cifras no son inventadas: salen de los veintitrés comprobantes reales de
`docs/`, que también se validan (los veintitrés pasan) y que son de dónde se
sacó, por ejemplo, que los baldes del resumen van **antes** del descuento.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.fe_xml import (
    ARMABLES,
    PERFILES,
    CodigoComercial,
    Comprobante,
    ComprobanteInvalido,
    Descuento,
    Exoneracion,
    Identificacion,
    Impuesto,
    ImpuestoEspecifico,
    Linea,
    LineaSurtido,
    MedioPago,
    Otro,
    OtroCargo,
    Parte,
    Referencia,
    Ubicacion,
    construir,
)

ESQUEMAS = (
    Path(__file__).resolve().parents[3] / "docs" / "hacienda" / "costa-rica" / "esquemas"
)

#: Un CABYS de servicio (empieza con 8) y uno de mercancía (empieza con 0). La
#: diferencia no es decorativa: decide a qué balde del resumen va la línea.
SERVICIO = "8399000000000"
MERCANCIA = "0111100000000"


def iva(codigo: str = "08", tarifa: str = "13", **cambios) -> Impuesto:
    return Impuesto(codigo_tarifa=codigo, tarifa=Decimal(tarifa), **cambios)


IVA13 = iva()

#: Del emisor el XSD exige **ubicación y correo**; del receptor, ninguno de
#: los dos. Las dos las destapó el validador.
EMISOR = Parte(
    "La Esquina S.A.",
    Identificacion("02", "3101123456"),
    Ubicacion("1", "01", "07", "Del parque 100 m sur"),
    correo="fe@laesquina.cr",
)
RECEPTOR = Parte(
    "Ana Castro",
    Identificacion("01", "115670987"),
    Ubicacion("1", "03", "01", "Curridabat, 200 m sur"),
)
EXONERACION = Exoneracion(
    tipo_documento="08",
    numero_documento="LEY 7210 REGIMEN DE ZONAS FRANCAS",
    nombre_institucion="99",
    nombre_institucion_otros="PROCOMER",
    fecha="2023-01-13T00:00:00-06:00",
    puntos=Decimal("9"),
    articulo=17,
    inciso=1,
)


def linea(**cambios) -> Linea:
    base = dict(
        numero=1,
        cabys=SERVICIO,
        cantidad=Decimal(1),
        unidad="Sp",
        detalle="Servicio",
        precio_unitario=Decimal("1000"),
        impuestos=(IVA13,),
    )
    return Linea(**{**base, **cambios})


def comprobante(**cambios) -> Comprobante:
    base = dict(
        tipo="01",
        clave="5" * 50,
        consecutivo="0" * 20,
        fecha="2026-09-19T14:32:00-06:00",
        emisor=EMISOR,
        receptor=RECEPTOR,
        proveedor_sistemas="3101702934",
        actividad_emisor="4711.1",
        condicion_venta="01",
        lineas=(linea(),),
    )
    return Comprobante(**{**base, **cambios})


def arbol(comp: Comprobante) -> ET.Element:
    return ET.fromstring(construir(comp))


def etiquetas(raiz: ET.Element) -> list[str]:
    return [e.tag.rsplit("}", 1)[-1] for e in raiz.iter()]


def valor(raiz: ET.Element, nombre: str) -> str | None:
    for e in raiz.iter():
        if e.tag.rsplit("}", 1)[-1] == nombre:
            return e.text
    return None


def valores(raiz: ET.Element, nombre: str) -> list[str]:
    return [e.text or "" for e in raiz.iter() if e.tag.rsplit("}", 1)[-1] == nombre]


# --------------------------------------------------------------- lo que niega


class TestLoQueNoSeArma:
    def test_un_tipo_que_no_existe(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(tipo="77"))
        assert e.value.code == "tipo_desconocido"

    def test_sin_lineas(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=()))
        assert e.value.code == "sin_lineas"

    def test_mas_de_cuatro_medios_de_pago(self):
        # El XSD admite cuatro. El quinto no lo rechaza Hacienda: lo rechaza el
        # esquema, y eso se puede ver acá en vez de en la respuesta.
        medios = tuple(MedioPago("01", Decimal(1)) for _ in range(5))
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(medios_pago=medios))
        assert (e.value.code, e.value.detail) == ("demasiados", "MedioPago")

    @pytest.mark.parametrize(
        "campo, cuantos, elemento",
        [
            ("lineas", 1001, "LineaDetalle"),
            ("otros_cargos", 16, "OtrosCargos"),
            ("referencias", 11, "InformacionReferencia"),
        ],
    )
    def test_los_topes_del_XSD(self, campo, cuantos, elemento):
        muchos = {
            "lineas": lambda n: tuple(linea(numero=i + 1) for i in range(n)),
            "otros_cargos": lambda n: tuple(
                OtroCargo("01", "Cargo", Decimal(1)) for _ in range(n)
            ),
            "referencias": lambda n: tuple(
                Referencia("01", "2026-09-19T14:32:00-06:00", numero="1") for _ in range(n)
            ),
        }[campo](cuantos)
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(**{campo: muchos}))
        assert (e.value.code, e.value.detail) == ("demasiados", elemento)

    @pytest.mark.parametrize(
        "campo, elemento",
        [("codigos_comerciales", "CodigoComercial"), ("descuentos", "Descuento")],
    )
    def test_los_topes_de_la_linea(self, campo, elemento):
        muchos = {
            "codigos_comerciales": lambda: tuple(
                CodigoComercial("01", str(i)) for i in range(6)
            ),
            "descuentos": lambda: tuple(Descuento(Decimal(1)) for _ in range(6)),
        }[campo]()
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=(linea(**{campo: muchos}),)))
        assert (e.value.code, e.value.detail) == ("demasiados", elemento)

    def test_mas_de_veinte_pedazos_de_surtido(self):
        pedazo = LineaSurtido(
            MERCANCIA, Decimal(1), "Unid", "Parte", Decimal(10), (IVA13,)
        )
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=(linea(surtido=tuple(pedazo for _ in range(21))),)))
        assert (e.value.code, e.value.detail) == ("demasiados", "LineaDetalleSurtido")

    @pytest.mark.parametrize("condicion", ["02", "08", "10"])
    def test_medio_de_pago_con_venta_a_credito(self, condicion):
        """RN-77. Las tres condiciones de crédito no llevan medio de pago."""
        with pytest.raises(ComprobanteInvalido) as e:
            construir(
                comprobante(
                    condicion_venta=condicion,
                    medios_pago=(MedioPago("01", Decimal(1)),),
                )
            )
        assert e.value.code == "medio_de_pago_en_credito"

    def test_la_condicion_99_sin_su_detalle(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(condicion_venta="99"))
        assert e.value.code == "falta_condicion_venta_otros"

    def test_una_condicion_que_ese_tipo_no_admite(self):
        """La 12 —mercancía no nacionalizada— solo existe en la factura."""
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(tipo="04", condicion_venta="12"))
        assert (e.value.code, e.value.detail) == ("condicion_venta_no_valida", "12")

    def test_sin_proveedor_de_sistemas(self):
        # Es obligatorio en el XSD. Lo destapó el validador.
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(proveedor_sistemas=""))
        assert e.value.code == "falta_proveedor_sistemas"

    def test_sin_actividad_del_emisor(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(actividad_emisor=""))
        assert e.value.code == "falta_actividad_emisor"

    def test_una_linea_sin_CABYS(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=(linea(cabys=""),)))
        assert (e.value.code, e.value.detail) == ("linea_sin_cabys", "1")

    def test_una_linea_sin_unidad_de_medida(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=(linea(unidad=""),)))
        assert (e.value.code, e.value.detail) == ("linea_sin_unidad", "1")

    def test_una_linea_sin_impuesto(self):
        """El XSD pide uno como mínimo, aunque sea de tarifa cero."""
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(lineas=(linea(impuestos=()),)))
        assert (e.value.code, e.value.detail) == ("linea_sin_impuestos", "1")

    def test_un_impuesto_que_no_dice_cuanto_es(self):
        """Sin tarifa hay que dar el monto: un específico no sale de un %."""
        with pytest.raises(ComprobanteInvalido) as e:
            Impuesto(codigo="02")
        assert (e.value.code, e.value.detail) == ("impuesto_sin_monto", "02")

    def test_el_motivo_viaja_con_su_detalle(self):
        e = ComprobanteInvalido("tipo_desconocido", "77")
        assert (e.code, e.detail) == ("tipo_desconocido", "77")
        assert "77" in str(e)

    def test_y_sin_detalle_tambien_sirve(self):
        assert str(ComprobanteInvalido("sin_lineas")) == "sin_lineas"


# ------------------------------------------------------------- la aritmética


class TestLaAritmetica:
    def test_la_venta_del_invariante(self):
        """`venta_arroz_cafe`: 5 700 de subtotal, 741 de IVA, 6 441 de total.

        Es la cifra de referencia de `progress.json`. Si el armador da otra
        cosa, lo que está mal es el armador.
        """
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(numero=1, precio_unitario=Decimal("1450"), cabys=MERCANCIA),
                    linea(numero=2, precio_unitario=Decimal("4250"), cabys=MERCANCIA),
                )
            )
        )
        assert valor(raiz, "TotalVentaNeta") == "5700.00000"
        assert valor(raiz, "TotalImpuesto") == "741.00000"
        assert valor(raiz, "TotalComprobante") == "6441.00000"

    def test_nueve_puntos_exonerados_dejan_pagando_cuatro(self):
        """RN-78. El caso que motivó todo esto.

        13 % con 9 puntos exonerados no es «tarifa del 4 %»: es 13 % de
        impuesto, 9 % de exoneración y 4 % de impuesto neto.
        """
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        precio_unitario=Decimal("100000"),
                        impuestos=(iva(exoneracion=EXONERACION),),
                    ),
                )
            )
        )
        assert valor(raiz, "Monto") == "13000.00000"
        assert valor(raiz, "MontoExoneracion") == "9000.00000"
        assert valor(raiz, "ImpuestoNeto") == "4000.00000"
        assert valor(raiz, "MontoTotalLinea") == "104000.00000"
        assert valor(raiz, "TotalComprobante") == "104000.00000"

    def test_una_exoneracion_parcial_reparte_la_linea_en_dos_baldes(self):
        """Anexo pp. 50-52: la proporción es exonerado / impuesto.

        Con 9 puntos de 13 se perdonó el 69.23 % de lo que se cobraba, así que
        de los 100 000 esa parte va al balde exonerado y el resto **sigue
        siendo gravado**. Mandar la línea entera al exonerado —que es lo que
        parece razonable— descuadra el resumen contra sí mismo.
        """
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        precio_unitario=Decimal("100000"),
                        impuestos=(iva(exoneracion=EXONERACION),),
                    ),
                )
            )
        )
        assert valor(raiz, "TotalServExonerado") == "69230.76923"
        assert valor(raiz, "TotalServGravados") == "30769.23077"
        assert valor(raiz, "TotalVenta") == "100000.00000"

    def test_una_exoneracion_total_se_lleva_la_linea_entera(self):
        exo = Exoneracion("03", "LEY", "99", "2023-01-13T00:00:00-06:00", Decimal("13"))
        raiz = arbol(comprobante(lineas=(linea(impuestos=(iva(exoneracion=exo),)),)))
        assert valor(raiz, "TotalServExonerado") == "1000.00000"
        assert valor(raiz, "TotalServGravados") is None
        # Declara el impuesto en cero y **no** se calla el desglose: la línea
        # estuvo gravada, el perdón va aparte. Es lo que hace la factura de
        # servicios médicos exonerada de `docs/…/protocolos/`.
        assert valor(raiz, "TotalMontoImpuesto") == "0.00000"
        assert valor(raiz, "TotalImpuesto") == "0.00000"

    def test_una_linea_exenta_no_tiene_desglose_que_declarar(self):
        """Y la diferencia con la exonerada es real: nunca estuvo gravada.

        La factura de exportación de `docs/` no trae el nodo; la de servicios
        médicos exonerada sí, en cero.
        """
        raiz = arbol(comprobante(lineas=(linea(impuestos=(iva("10", "0"),)),)))
        assert "TotalDesgloseImpuesto" not in etiquetas(raiz)
        assert "TotalImpuesto" not in etiquetas(raiz)

    def test_los_baldes_van_antes_del_descuento(self):
        """Dos comprobantes aceptados lo enseñan: 100 000 gravado, 97 500 neto.

        Llenarlos con el subtotal —que es lo que uno escribe primero— da
        `TotalGravado` 97 500 y un resumen que no cuadra contra `TotalVenta`.
        """
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        precio_unitario=Decimal("100000"),
                        descuentos=(Descuento(Decimal("2500"), naturaleza="Promoción"),),
                    ),
                )
            )
        )
        assert valor(raiz, "SubTotal") == "97500.00000"
        assert valor(raiz, "BaseImponible") == "97500.00000"
        assert valor(raiz, "TotalServGravados") == "100000.00000"
        assert valor(raiz, "TotalVenta") == "100000.00000"
        assert valor(raiz, "TotalDescuentos") == "2500.00000"
        assert valor(raiz, "TotalVentaNeta") == "97500.00000"
        assert valor(raiz, "NaturalezaDescuento") == "Promoción"

    def test_dos_descuentos_en_la_misma_linea_se_suman(self):
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        descuentos=(
                            Descuento(Decimal("100"), codigo="01"),
                            Descuento(Decimal("50"), codigo="99", codigo_otro="Convenio"),
                        ),
                    ),
                )
            )
        )
        assert valores(raiz, "MontoDescuento") == ["100.00000", "50.00000"]
        assert valor(raiz, "CodigoDescuentoOTRO") == "Convenio"
        assert valor(raiz, "SubTotal") == "850.00000"

    def test_un_descuento_sin_razon_no_la_inventa(self):
        raiz = arbol(comprobante(lineas=(linea(descuentos=(Descuento(Decimal("100")),)),)))
        assert "NaturalezaDescuento" not in etiquetas(raiz)

    def test_la_cantidad_multiplica(self):
        raiz = arbol(
            comprobante(lineas=(linea(cantidad=Decimal(3), precio_unitario=Decimal("1450")),))
        )
        assert valor(raiz, "Cantidad") == "3.000"
        assert valor(raiz, "MontoTotal") == "4350.00000"

    def test_dos_tarifas_dan_dos_renglones_de_desglose(self):
        raiz = arbol(
            comprobante(
                lineas=(linea(numero=1), linea(numero=2, impuestos=(iva("04", "4"),)))
            )
        )
        assert valores(raiz, "TotalMontoImpuesto") == ["130.00000", "40.00000"]
        assert valor(raiz, "TotalImpuesto") == "170.00000"

    def test_dos_lineas_con_la_misma_tarifa_dan_un_renglon(self):
        raiz = arbol(comprobante(lineas=(linea(numero=1), linea(numero=2))))
        assert valores(raiz, "TotalMontoImpuesto") == ["260.00000"]

    def test_los_montos_van_con_cinco_decimales_aunque_sobren(self):
        assert valor(arbol(comprobante()), "TotalComprobante") == "1130.00000"

    @pytest.mark.parametrize(
        "codigo, balde",
        [
            ("08", "TotalServGravados"),
            ("10", "TotalServExentos"),
            ("01", "TotalServNoSujeto"),
            ("11", "TotalServNoSujeto"),
        ],
    )
    def test_cada_tarifa_cae_en_su_balde(self, codigo, balde):
        """`01` y `11` son los dos 0 % y los dos son no sujetos acá.

        Lo que los distingue —el derecho a crédito— no se ve en el resumen sino
        en el código, que es justo por qué el código no se puede deducir del
        porcentaje (RN-76).
        """
        raiz = arbol(comprobante(lineas=(linea(impuestos=(iva(codigo, "0"),)),)))
        assert valor(raiz, balde) == "1000.00000"

    def test_el_CABYS_decide_si_es_servicio_o_mercancia(self):
        """Anexo pp. 50-52: 5 a 9 son servicios, 0 a 4 mercancías."""
        raiz = arbol(comprobante(lineas=(linea(cabys=MERCANCIA),)))
        assert valor(raiz, "TotalMercanciasGravadas") == "1000.00000"
        assert valor(raiz, "TotalServGravados") is None

    @pytest.mark.parametrize(
        "codigo, balde",
        [("10", "TotalMercanciasExentas"), ("01", "TotalMercNoSujeta")],
    )
    def test_y_las_mercancías_tienen_sus_propios_baldes(self, codigo, balde):
        raiz = arbol(
            comprobante(lineas=(linea(cabys=MERCANCIA, impuestos=(iva(codigo, "0"),)),))
        )
        assert valor(raiz, balde) == "1000.00000"

    def test_una_mercancia_exonerada_tambien(self):
        exo = Exoneracion("03", "LEY", "99", "2023-01-13T00:00:00-06:00", Decimal("13"))
        raiz = arbol(
            comprobante(
                lineas=(linea(cabys=MERCANCIA, impuestos=(iva(exoneracion=exo),)),)
            )
        )
        assert valor(raiz, "TotalMercExonerada") == "1000.00000"

    def test_un_balde_en_cero_no_se_emite(self):
        # Los comprobantes reales traen cuatro líneas de total, no dieciséis.
        raiz = arbol(comprobante())
        assert "TotalMercanciasGravadas" not in etiquetas(raiz)
        assert "TotalNoSujeto" not in etiquetas(raiz)

    def test_sin_impuesto_no_se_emite_el_total_de_impuesto(self):
        raiz = arbol(comprobante(lineas=(linea(impuestos=(iva("10", "0"),)),)))
        assert "TotalImpuesto" not in etiquetas(raiz)

    def test_dos_impuestos_en_la_misma_linea(self):
        """Una cerveza paga IVA y el específico a las bebidas alcohólicas."""
        especifico = Impuesto(
            codigo="04",
            monto=Decimal("250"),
            especifico=ImpuestoEspecifico(
                cantidad_unidad_medida=Decimal("1"),
                impuesto_unidad=Decimal("250"),
                volumen_unidad_consumo=Decimal("0.35"),
            ),
        )
        raiz = arbol(comprobante(lineas=(linea(impuestos=(IVA13, especifico)),)))
        assert valores(raiz, "Monto") == ["130.00000", "250.00000"]
        assert valor(raiz, "ImpuestoNeto") == "380.00000"
        assert valores(raiz, "TotalMontoImpuesto") == ["130.00000", "250.00000"]
        assert valor(raiz, "TotalImpuesto") == "380.00000"
        assert valor(raiz, "ImpuestoUnidad") == "250.00000"
        assert valor(raiz, "VolumenUnidadConsumo") == "0.35"

    def test_el_impuesto_asumido_en_fabrica_se_resta(self):
        """Anexo p. 47: el neto es el monto menos lo exonerado y lo asumido."""
        raiz = arbol(comprobante(lineas=(linea(impuesto_asumido=Decimal("30")),)))
        assert valor(raiz, "ImpuestoAsumidoEmisorFabrica") == "30.00000"
        assert valor(raiz, "ImpuestoNeto") == "100.00000"
        assert valor(raiz, "TotalMontoImpuesto") == "100.00000"
        assert valor(raiz, "TotalImpuesto") == "100.00000"
        assert valor(raiz, "TotalImpAsumEmisorFabrica") == "30.00000"
        assert valor(raiz, "TotalComprobante") == "1100.00000"

    def test_los_otros_cargos_suman_al_total(self):
        raiz = arbol(
            comprobante(
                otros_cargos=(
                    OtroCargo(
                        tipo_documento="04",
                        detalle="Servicio de un tercero",
                        monto=Decimal("500"),
                        identificacion_tercero=Identificacion("02", "3101999888"),
                        nombre_tercero="Transportes Unidos S.A.",
                        porcentaje=Decimal("5"),
                    ),
                )
            )
        )
        assert valor(raiz, "NombreTercero") == "Transportes Unidos S.A."
        assert valor(raiz, "PorcentajeOC") == "5.00000"
        assert valor(raiz, "MontoCargo") == "500.00000"
        assert valor(raiz, "TotalOtrosCargos") == "500.00000"
        assert valor(raiz, "TotalComprobante") == "1630.00000"

    def test_un_otro_cargo_pelado_es_tipo_detalle_y_monto(self):
        raiz = arbol(
            comprobante(otros_cargos=(OtroCargo("06", "Timbre de la Cruz Roja", Decimal("5")),))
        )
        cargo = next(e for e in raiz.iter() if e.tag.endswith("OtrosCargos"))
        assert etiquetas(cargo) == ["OtrosCargos", "TipoDocumentoOC", "Detalle", "MontoCargo"]
        assert valor(raiz, "TotalComprobante") == "1135.00000"

    def test_el_cargo_99_y_la_exoneracion_99_llevan_su_descripcion(self):
        exo = Exoneracion(
            tipo_documento="99",
            tipo_documento_otro="Resolución interna de la institución",
            numero_documento="RES-2026-88",
            nombre_institucion="99",
            nombre_institucion_otros="Municipalidad de Curridabat",
            fecha="2023-01-13T00:00:00-06:00",
            puntos=Decimal("13"),
        )
        raiz = arbol(
            comprobante(
                lineas=(linea(impuestos=(iva(exoneracion=exo),)),),
                otros_cargos=(
                    OtroCargo(
                        tipo_documento="99",
                        tipo_documento_otros="Cargo por conveniencia",
                        detalle="Recargo",
                        monto=Decimal("100"),
                    ),
                ),
            )
        )
        assert valor(raiz, "TipoDocumentoOTRO") == "Resolución interna de la institución"
        assert valor(raiz, "TipoDocumentoOTROS") == "Cargo por conveniencia"

    def test_un_impuesto_especifico_con_porcentaje_y_proporcion(self):
        """El de bebidas envasadas y jabón: sale de la unidad, no del precio."""
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        impuestos=(
                            Impuesto(
                                codigo="05",
                                monto=Decimal("18"),
                                especifico=ImpuestoEspecifico(
                                    cantidad_unidad_medida=Decimal("2"),
                                    impuesto_unidad=Decimal("9"),
                                    porcentaje=Decimal("10"),
                                    proporcion=Decimal("50"),
                                ),
                            ),
                        )
                    ),
                )
            )
        )
        assert valor(raiz, "CantidadUnidadMedida") == "2.00"
        assert valor(raiz, "Porcentaje") == "10.00"
        assert valor(raiz, "Proporcion") == "50.00"
        assert valor(raiz, "ImpuestoUnidad") == "9.00000"
        assert valor(raiz, "ImpuestoNeto") == "18.00000"

    def test_el_IVA_devuelto_se_resta_del_total(self):
        """Anexo p. 55, y es el término que se olvida.

        Se factura 100 000 de servicio médico con 4 % de IVA; como se pagó con
        tarjeta, el IVA se devuelve y el comprobante totaliza los 100 000.
        """
        raiz = arbol(
            comprobante(
                lineas=(linea(cabys="9310100000100", impuestos=(iva("04", "4"),)),),
                medios_pago=(MedioPago("02", Decimal("1000")),),
                iva_devuelto=Decimal("40"),
            )
        )
        assert valor(raiz, "TotalImpuesto") == "40.00000"
        assert valor(raiz, "TotalIVADevuelto") == "40.00000"
        assert valor(raiz, "TotalComprobante") == "1000.00000"


# ----------------------------------------------------------------- el formato


class TestElFormato:
    @pytest.mark.parametrize(
        "puntos, escrito",
        [("13", "13"), ("0.5", "0.5"), ("4.00", "4"), ("10", "10")],
    )
    def test_los_puntos_exonerados_van_como_numero(self, puntos, escrito):
        """El anexo: «la del 13 % como 13, la del 0.5 % como 0.5».

        El 10 está en la lista por algo: `Decimal("10.00").normalize()` vale
        `1E+1`, y diez puntos exonerados salían escritos «1E+1».
        """
        exo = Exoneracion("03", "L", "99", "2023-01-13T00:00:00-06:00", Decimal(puntos))
        raiz = arbol(comprobante(lineas=(linea(impuestos=(iva(exoneracion=exo),)),)))
        assert valor(raiz, "TarifaExonerada") == escrito

    def test_la_tarifa_va_con_dos_decimales(self):
        assert valor(arbol(comprobante()), "Tarifa") == "13.00"

    def test_el_tiquete_es_otra_raiz_y_otro_espacio_de_nombres(self):
        texto = construir(comprobante(tipo="04"))
        assert "TiqueteElectronico" in texto
        assert "v4.4/tiqueteElectronico" in texto

    def test_el_orden_del_encabezado_es_el_del_XSD(self):
        raiz = arbol(comprobante(actividad_receptor="4711.1"))
        cabeza = etiquetas(raiz)[1:8]
        assert cabeza == [
            "Clave",
            "ProveedorSistemas",
            "CodigoActividadEmisor",
            "CodigoActividadReceptor",
            "NumeroConsecutivo",
            "FechaEmision",
            "Emisor",
        ]

    def test_sin_actividad_del_receptor_no_se_emite(self):
        assert "CodigoActividadReceptor" not in etiquetas(arbol(comprobante()))

    def test_un_tiquete_puede_no_llevar_receptor(self):
        assert "Receptor" not in etiquetas(arbol(comprobante(tipo="04", receptor=None)))

    def test_el_plazo_de_credito_va_despues_de_la_condicion(self):
        raiz = arbol(comprobante(condicion_venta="02", plazo_credito=30))
        marcas = etiquetas(raiz)
        assert marcas.index("PlazoCredito") == marcas.index("CondicionVenta") + 1
        assert valor(raiz, "PlazoCredito") == "30"

    def test_la_condicion_99_lleva_su_detalle(self):
        raiz = arbol(
            comprobante(condicion_venta="99", condicion_venta_otros="Permuta parcial")
        )
        assert valor(raiz, "CondicionVentaOtros") == "Permuta parcial"

    def test_el_orden_de_la_linea_es_el_del_XSD(self):
        """Lo que el XSD no perdona: un campo bueno en el sitio equivocado."""
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        codigos_comerciales=(CodigoComercial("01", "SKU-1"),),
                        tipo_transaccion="01",
                        unidad_comercial="Caja",
                        series=("1G1YY22G975100001",),
                        registro_medicamento="ABC-123",
                        forma_farmaceutica="TAB",
                        descuentos=(Descuento(Decimal("10")),),
                    ),
                )
            )
        )
        dentro = etiquetas(next(e for e in raiz.iter() if e.tag.endswith("LineaDetalle")))
        assert dentro == [
            "LineaDetalle",
            "NumeroLinea",
            "CodigoCABYS",
            "CodigoComercial",
            "Tipo",
            "Codigo",
            "Cantidad",
            "UnidadMedida",
            "TipoTransaccion",
            "UnidadMedidaComercial",
            "Detalle",
            "NumeroVINoSerie",
            "RegistroMedicamento",
            "FormaFarmaceutica",
            "PrecioUnitario",
            "MontoTotal",
            "Descuento",
            "MontoDescuento",
            "CodigoDescuento",
            "SubTotal",
            "BaseImponible",
            "Impuesto",
            "Codigo",
            "CodigoTarifaIVA",
            "Tarifa",
            "Monto",
            "ImpuestoAsumidoEmisorFabrica",
            "ImpuestoNeto",
            "MontoTotalLinea",
        ]

    def test_un_surtido_detalla_de_qué_se_compone_la_linea(self):
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        detalle="Combo desayuno",
                        surtido=(
                            LineaSurtido(
                                cabys=MERCANCIA,
                                cantidad=Decimal(1),
                                unidad="Unid",
                                detalle="Café",
                                precio_unitario=Decimal("600"),
                                impuestos=(IVA13,),
                                codigos_comerciales=(CodigoComercial("01", "CAF"),),
                                unidad_comercial="Taza",
                                descuentos=(
                                    Descuento(Decimal("50"), codigo="99", codigo_otro="Combo"),
                                ),
                            ),
                            LineaSurtido(
                                cabys=MERCANCIA,
                                cantidad=Decimal(1),
                                unidad="Unid",
                                detalle="Pan",
                                precio_unitario=Decimal("400"),
                                impuestos=(IVA13,),
                                iva_cobrado_fabrica="02",
                            ),
                        ),
                    ),
                )
            )
        )
        # El primero vacío es el nodo que envuelve: Hacienda le puso el mismo
        # nombre al contenedor y al detalle de cada pedazo.
        assert valores(raiz, "DetalleSurtido") == ["", "Café", "Pan"]
        assert valores(raiz, "SubTotalSurtido") == ["550.00000", "400.00000"]
        assert valor(raiz, "DescuentoSurtidoOtros") == "Combo"
        assert valor(raiz, "IVACobradoFabricaSurtido") == "02"
        assert valores(raiz, "MontoImpuestoSurtido") == ["71.50000", "52.00000"]

    def test_el_codigo_de_impuesto_99_lleva_su_descripcion(self):
        raiz = arbol(
            comprobante(
                lineas=(
                    linea(
                        impuestos=(
                            Impuesto(
                                codigo="99",
                                codigo_otro="Impuesto municipal de patente",
                                monto=Decimal("15"),
                                factor_calculo_iva=Decimal("0.5"),
                            ),
                        )
                    ),
                )
            )
        )
        assert valor(raiz, "CodigoImpuestoOTRO") == "Impuesto municipal de patente"
        assert valor(raiz, "FactorCalculoIVA") == "0.50"
        assert "CodigoTarifaIVA" not in etiquetas(raiz)


class TestLasPartes:
    def test_lo_opcional_del_emisor_solo_sale_si_está(self):
        raiz = arbol(comprobante())
        for opcional in ("NombreComercial", "Telefono", "Registrofiscal8707"):
            assert opcional not in etiquetas(raiz)

    def test_el_emisor_sin_correo_no_se_arma(self):
        sin_correo = Parte(
            "X", Identificacion("02", "3101123456"), Ubicacion("1", "01", "07", "Centro")
        )
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(emisor=sin_correo))
        assert e.value.code == "falta_correo_emisor"

    def test_y_sale_completo_cuando_está(self):
        completo = Parte(
            nombre="La Esquina S.A.",
            identificacion=Identificacion("02", "3101123456"),
            nombre_comercial="La Esquina",
            ubicacion=Ubicacion("1", "01", "07", "Del parque 100 m sur", barrio="Amón"),
            telefono="22334455",
            correo="fe@laesquina.cr",
            registro_fiscal="8707-00123",
        )
        raiz = arbol(comprobante(emisor=completo))
        assert valor(raiz, "Registrofiscal8707") == "8707-00123"
        assert valor(raiz, "NombreComercial") == "La Esquina"
        assert valor(raiz, "Provincia") == "1"
        assert valor(raiz, "Barrio") == "Amón"
        assert valor(raiz, "OtrasSenas") == "Del parque 100 m sur"
        assert valor(raiz, "CodigoPais") == "506"
        assert valor(raiz, "NumTelefono") == "22334455"
        assert valor(raiz, "CorreoElectronico") == "fe@laesquina.cr"

    def test_el_receptor_puede_no_tener_ubicacion(self):
        """La asimetría del XSD: del receptor solo son obligatorios el
        nombre y la identificación. Se le factura a quien da su cédula y
        nada más, que es lo normal en un mostrador."""
        raiz = arbol(
            comprobante(receptor=Parte("Ana", Identificacion("01", "115670987")))
        )
        assert valores(raiz, "Provincia") == ["1"]  # solo la del emisor

    def test_una_ubicacion_sin_otras_señas_no_existe(self):
        """`OtrasSenas` es obligatorio y `Barrio` no, al revés de lo que parece.

        Con solo el barrio, el XSD contesta «Missing child element(s)» y el
        comprobante se cae después de firmado.
        """
        with pytest.raises(ComprobanteInvalido) as e:
            Ubicacion("1", "01", "07", barrio="Amón")
        assert e.value.code == "ubicacion_sin_senas"

    def test_el_emisor_sin_ubicacion_no_se_arma(self):
        pelado = Parte("X", Identificacion("02", "3101123456"), correo="x@y.cr")
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(emisor=pelado))
        assert e.value.code == "falta_ubicacion_emisor"

    def test_la_factura_exige_receptor(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(receptor=None))
        assert e.value.code == "falta_receptor"


class TestLoQueSeCopiaYNoSeInventa:
    """RN-80: los datos de protocolo se relevan tal cual."""

    def test_los_otros_van_con_su_codigo(self):
        raiz = arbol(
            comprobante(
                otros=(
                    Otro(codigo="BCCR_ORDEN_PEDIDO", texto="4200005460"),
                    Otro(codigo="OC", texto="L000298431"),
                )
            )
        )
        textos = [
            (e.get("codigo"), e.text)
            for e in raiz.iter()
            if e.tag.endswith("OtroTexto")
        ]
        assert textos == [("BCCR_ORDEN_PEDIDO", "4200005460"), ("OC", "L000298431")]

    def test_el_del_BNCR_no_lleva_codigo(self):
        """El 015 de SWS es un `OtroTexto` pelado: «Agrupamiento <código>»."""
        raiz = arbol(comprobante(otros=(Otro(texto="Agrupamiento FEBN-0001"),)))
        nodo = next(e for e in raiz.iter() if e.tag.endswith("OtroTexto"))
        assert nodo.get("codigo") is None
        assert nodo.text == "Agrupamiento FEBN-0001"

    def test_todos_los_OtroTexto_antes_de_cualquier_OtroContenido(self):
        # Lo exige la secuencia del XSD, y es de los errores que solo aparecen
        # al validar: el orden en que se declaran no es el orden en que van.
        raiz = arbol(
            comprobante(
                otros=(
                    Otro(elemento="OtroContenido", texto="segundo"),
                    Otro(elemento="OtroTexto", texto="primero"),
                )
            )
        )
        dentro = [t for t in etiquetas(raiz) if t.startswith("Otro")]
        assert dentro == ["Otros", "OtroTexto", "OtroContenido"]

    def test_sin_otros_no_se_emite_el_nodo(self):
        assert "Otros" not in etiquetas(arbol(comprobante()))


class TestElPagoYElIVADevuelto:
    def test_los_medios_de_pago_van_en_el_resumen(self):
        raiz = arbol(
            comprobante(
                medios_pago=(
                    MedioPago("01", Decimal("500")),
                    MedioPago("02", Decimal("630")),
                )
            )
        )
        assert valores(raiz, "TipoMedioPago") == ["01", "02"]
        assert valores(raiz, "TotalMedioPago") == ["500.00000", "630.00000"]

    def test_dos_medios_de_pago_tienen_que_sumar_el_total(self):
        """Anexo p. 55: con dos o más, Hacienda comprueba la suma.

        Con uno solo no lo comprueba —el monto es hasta opcional—, así que la
        guarda tampoco: negarse ahí sería inventar una regla.
        """
        with pytest.raises(ComprobanteInvalido) as e:
            construir(
                comprobante(
                    medios_pago=(
                        MedioPago("01", Decimal("500")),
                        MedioPago("02", Decimal("500")),
                    )
                )
            )
        assert (e.value.code, e.value.detail) == ("los_medios_no_suman_el_total", "1130.00000")

    def test_y_con_uno_solo_no_se_comprueba(self):
        raiz = arbol(comprobante(medios_pago=(MedioPago("01", Decimal("1")),)))
        assert valor(raiz, "TotalMedioPago") == "1.00000"

    def test_el_medio_99_lleva_su_detalle(self):
        raiz = arbol(
            comprobante(medios_pago=(MedioPago("99", Decimal("1130"), "Permuta"),))
        )
        assert valor(raiz, "MedioPagoOtros") == "Permuta"

    def test_sin_tarjeta_no_se_declara_IVA_devuelto(self):
        raiz = arbol(comprobante(medios_pago=(MedioPago("01", Decimal("1130")),)))
        assert "TotalIVADevuelto" not in etiquetas(raiz)

    def test_la_moneda_y_el_tipo_de_cambio(self):
        raiz = arbol(comprobante(moneda="USD", tipo_cambio=Decimal("512.5")))
        assert valor(raiz, "CodigoMoneda") == "USD"
        assert valor(raiz, "TipoCambio") == "512.50000"


# --------------------------------------------------- los siete comprobantes


def nota(**cambios) -> Comprobante:
    base = dict(
        tipo="03",
        referencias=(
            Referencia(
                tipo_documento="01",
                numero="5" * 50,
                fecha="2026-09-18T10:00:00-06:00",
                codigo="01",
                razon="Anulación por error en el monto",
            ),
        ),
    )
    return comprobante(**{**base, **cambios})


def recibo(**cambios) -> Comprobante:
    pelado = Parte("SWS Software S.A.", Identificacion("02", "3101702934"), correo="fe@sws.cr")
    base = dict(
        tipo="10",
        emisor=pelado,
        receptor=Parte("Ana Castro", Identificacion("01", "115670987")),
        actividad_emisor="",
        condicion_venta="11",
        medios_pago=(MedioPago("01", Decimal("1130")),),
        referencias=(
            Referencia("01", "2026-09-18T10:00:00-06:00", numero="5" * 50, codigo="04"),
        ),
        lineas=(
            Linea(numero=1, detalle="Abono a la factura", precio_unitario=Decimal("1000"),
                  impuestos=(IVA13,)),
        ),
    )
    return comprobante(**{**base, **cambios})


class TestCadaTipoLLevaLoSuyo:
    def test_son_siete(self):
        assert ARMABLES == ("01", "02", "03", "04", "08", "09", "10")
        assert set(ARMABLES) == set(PERFILES)

    def test_la_nota_de_credito_exige_referencia(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(nota(referencias=()))
        assert (e.value.code, e.value.detail) == ("falta_referencia", "03")

    def test_y_la_referencia_va_despues_del_resumen(self):
        marcas = etiquetas(arbol(nota()))
        assert marcas.index("InformacionReferencia") > marcas.index("ResumenFactura")
        assert valor(arbol(nota()), "Razon") == "Anulación por error en el monto"

    def test_la_referencia_con_todo_lo_opcional(self):
        raiz = arbol(
            nota(
                referencias=(
                    Referencia(
                        tipo_documento="99",
                        tipo_documento_otro="Acta de la junta directiva",
                        numero="ACTA-2026-14",
                        fecha="2026-09-18T10:00:00-06:00",
                        codigo="99",
                        codigo_otro="Corrección de la razón social",
                        razon="El receptor cambió de nombre",
                    ),
                )
            )
        )
        assert valor(raiz, "TipoDocRefOTRO") == "Acta de la junta directiva"
        assert valor(raiz, "CodigoReferenciaOTRO") == "Corrección de la razón social"

    def test_una_referencia_pelada_no_inventa_lo_que_no_le_dieron(self):
        """Solo el recibo de pago exige el número; los demás lo dejan opcional."""
        raiz = arbol(
            comprobante(referencias=(Referencia("08", "2026-09-18T10:00:00-06:00"),))
        )
        for suyo in ("Numero", "Codigo", "CodigoReferenciaOTRO", "Razon", "TipoDocRefOTRO"):
            assert suyo not in etiquetas(
                next(e for e in raiz.iter() if e.tag.endswith("InformacionReferencia"))
            )

    def test_el_recibo_de_pago_exige_el_numero_de_la_referencia(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(recibo(referencias=(Referencia("01", "2026-09-18T10:00:00-06:00"),)))
        assert e.value.code == "falta_numero_de_referencia"

    def test_el_recibo_de_pago_exige_medio_de_pago(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(recibo(medios_pago=()))
        assert e.value.code == "faltan_medios_de_pago"

    def test_la_linea_del_recibo_son_siete_campos(self):
        raiz = arbol(recibo())
        dentro = etiquetas(next(e for e in raiz.iter() if e.tag.endswith("LineaDetalle")))
        assert dentro == [
            "LineaDetalle",
            "NumeroLinea",
            "Detalle",
            "MontoTotal",
            "SubTotal",
            "Impuesto",
            "Codigo",
            "CodigoTarifaIVA",
            "Tarifa",
            "Monto",
            "ImpuestoNeto",
            "MontoTotalLinea",
        ]

    def test_y_su_resumen_no_lleva_baldes(self):
        raiz = arbol(recibo())
        for balde in ("TotalServGravados", "TotalGravado", "TotalDescuentos"):
            assert balde not in etiquetas(raiz)
        assert valor(raiz, "TotalVenta") == "1000.00000"
        assert valor(raiz, "TotalComprobante") == "1130.00000"

    def test_el_recibo_de_pago_solo_existe_para_pagar_un_credito(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(recibo(condicion_venta="01"))
        assert e.value.code == "condicion_venta_no_valida"

    def test_la_factura_de_compra_exige_la_actividad_del_receptor(self):
        with pytest.raises(ComprobanteInvalido) as e:
            construir(
                comprobante(
                    tipo="08",
                    referencias=(Referencia("14", "2026-09-18T10:00:00-06:00", numero="1"),),
                )
            )
        assert e.value.code == "falta_actividad_receptor"

    @pytest.mark.parametrize(
        "tipo, cambios, elemento",
        [
            ("10", {"otros": (Otro(texto="x"),)}, "Otros"),
            ("10", {"otros_cargos": (OtroCargo("01", "x", Decimal(1)),)}, "OtrosCargos"),
            ("10", {"plazo_credito": 30}, "PlazoCredito"),
            ("04", {"actividad_receptor": "4711.1"}, "CodigoActividadReceptor"),
        ],
    )
    def test_lo_que_ese_tipo_no_admite(self, tipo, cambios, elemento):
        armar = recibo if tipo == "10" else comprobante
        with pytest.raises(ComprobanteInvalido) as e:
            construir(armar(tipo=tipo, **cambios))
        assert (e.value.code, e.value.detail) == ("no_va_en_este_tipo", elemento)

    @pytest.mark.parametrize(
        "tipo, cambios, elemento",
        [
            ("01", {"partida_arancelaria": "010121000000"}, "PartidaArancelaria"),
            ("04", {"tipo_transaccion": "01"}, "TipoTransaccion"),
            ("09", {"impuestos": (iva(exoneracion=EXONERACION),)}, "Exoneracion"),
            ("09", {"impuesto_asumido": Decimal("10")}, "ImpuestoAsumidoEmisorFabrica"),
            ("08", {"surtido": (
                LineaSurtido(MERCANCIA, Decimal(1), "Unid", "Café", Decimal(10), (IVA13,)),
            )}, "DetalleSurtido"),
            ("08", {"iva_cobrado_fabrica": "01"}, "IVACobradoFabrica"),
            ("08", {"impuestos": (
                Impuesto(codigo="02", monto=Decimal(1), especifico=ImpuestoEspecifico(
                    Decimal(1), Decimal(1))),
            )}, "DatosImpuestoEspecifico"),
            ("01", {"impuestos": (iva(monto_exportacion=Decimal(1)),)}, "MontoExportacion"),
        ],
    )
    def test_lo_que_la_linea_no_admite(self, tipo, cambios, elemento):
        """La partida arancelaria es de las notas y la exportación; la
        exoneración no existe en una exportación, que ya sale sin IVA; y la
        factura de compra no tiene surtidos ni impuestos específicos."""
        extra = {}
        if tipo == "08":
            extra = dict(
                actividad_receptor="4741.0",
                referencias=(Referencia("14", "2026-09-18T10:00:00-06:00", numero="1"),),
            )
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(tipo=tipo, lineas=(linea(**cambios),), **extra))
        assert (e.value.code, e.value.detail) == ("no_va_en_este_tipo", elemento)

    def test_la_exportacion_no_tiene_balde_de_no_sujeto(self):
        """Si la línea desapareciera del resumen, `TotalVenta` no cuadraría."""
        with pytest.raises(ComprobanteInvalido) as e:
            construir(comprobante(tipo="09", lineas=(linea(impuestos=(iva("01", "0"),)),)))
        assert (e.value.code, e.value.detail) == ("no_va_en_este_tipo", "TotalNoSujeto")

    def test_la_exportacion_le_quita_la_ubicacion_al_receptor(self):
        raiz = arbol(
            comprobante(
                tipo="09",
                receptor=Parte(
                    "INTERMARKET CORPORATION",
                    Identificacion("05", "0"),
                    ubicacion=Ubicacion("1", "01", "01", "No aplica"),
                    otras_senas_extranjero="1201 Brickell Ave, Miami, FL",
                ),
                lineas=(linea(impuestos=(iva("10", "0"),), partida_arancelaria="010121000000"),),
            )
        )
        # La ubicación del emisor sí, la del receptor no: ese tipo no la tiene.
        assert valores(raiz, "Provincia") == ["1"]
        assert valor(raiz, "OtrasSenasExtranjero") == "1201 Brickell Ave, Miami, FL"
        assert "BaseImponible" not in etiquetas(raiz)
        assert "ImpuestoNeto" not in etiquetas(raiz)

    def test_la_exportacion_puede_declarar_el_monto_exportado(self):
        raiz = arbol(
            comprobante(
                tipo="09",
                lineas=(linea(impuestos=(iva("10", "0", monto_exportacion=Decimal("400")),)),),
            )
        )
        assert valor(raiz, "MontoExportacion") == "400.00000"


# ------------------------------------------------- la que de verdad decide


class TestContraElEsquemaDeHacienda:
    """El XSD oficial, no una aproximación.

    Se salta si falta `lxml` —no está en `requirements.txt` a propósito, el
    proyecto acota sus dependencias— pero está en `requirements-dev.txt`, así
    que en una máquina de desarrollo corre siempre.
    """

    ARCHIVOS = {
        "01": "FacturaElectronica_V4.4.xsd",
        "02": "NotaDebitoElectronica_V4.4.xsd",
        "03": "NotaCreditoElectronica_V4.4.xsd",
        "04": "TiqueteElectronico_V4.4.xsd",
        "08": "FacturaElectronicaCompra_V4.4.xsd",
        "09": "FacturaElectronicaExportacion_V4.4.xsd",
        "10": "ReciboElectronicoPago_V4.4.xsd",
    }

    #: El XSD exige `ds:Signature` y este módulo no firma —eso es del adaptador
    #: de Vault—. Sin una de mentira, todo saldría inválido por lo único que acá
    #: no se hace, y la validación no diría nada del cuerpo.
    FIRMA = """<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:SignedInfo>
        <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
        <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
        <ds:Reference URI="">
          <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
          <ds:DigestValue>AA==</ds:DigestValue>
        </ds:Reference>
      </ds:SignedInfo>
      <ds:SignatureValue>AA==</ds:SignatureValue>
    </ds:Signature>"""

    @staticmethod
    def _carpeta(tmp_path: Path) -> Path:
        import shutil

        # El XSD importa `../../xmldsig-core-schema.xsd`, que en el paquete
        # oficial vive dos carpetas más arriba. Se reproduce en un temporal en
        # vez de tocar los archivos de `docs/`, que son la copia tal cual.
        hondo = tmp_path / "v4" / "4"
        hondo.mkdir(parents=True, exist_ok=True)
        for archivo in ESQUEMAS.glob("*.xsd"):
            shutil.copy2(archivo, hondo / archivo.name)
        shutil.copy2(
            ESQUEMAS / "xmldsig-core-schema.xsd", tmp_path / "xmldsig-core-schema.xsd"
        )
        return hondo

    def _validar(self, tmp_path: Path, comp: Comprobante) -> None:
        etree = pytest.importorskip("lxml.etree", reason="lxml no está instalado")
        esquema = etree.XMLSchema(
            etree.parse(str(self._carpeta(tmp_path) / self.ARCHIVOS[comp.tipo]))
        )
        raiz = etree.fromstring(construir(comp).encode("utf-8"))
        raiz.append(etree.fromstring(self.FIRMA))
        esquema.assertValid(raiz)

    def test_una_venta_de_contado(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                medios_pago=(MedioPago("01", Decimal("1130")),),
                lineas=(
                    linea(numero=1, cabys=MERCANCIA),
                    linea(numero=2, cabys=MERCANCIA, precio_unitario=Decimal("4250")),
                ),
            ),
        )

    def test_un_servicio_medico_con_tarjeta(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                actividad_emisor="8690.9",
                medios_pago=(MedioPago("02", Decimal("100000")),),
                iva_devuelto=Decimal("4000"),
                lineas=(
                    linea(
                        cabys="9310100000100",
                        unidad="Os",
                        detalle="Consulta médica",
                        precio_unitario=Decimal("100000"),
                        impuestos=(iva("04", "4"),),
                    ),
                ),
            ),
        )

    def test_una_venta_a_credito_con_exoneracion_parcial(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                condicion_venta="02",
                plazo_credito=30,
                receptor=Parte(
                    "Zona Franca S.A.",
                    Identificacion("02", "3102511731"),
                    Ubicacion("4", "07", "01", "Belén, La Ribera"),
                ),
                otros=(Otro(codigo="OC", texto="L000298431"),),
                lineas=(
                    linea(
                        precio_unitario=Decimal("100000"),
                        impuestos=(iva(exoneracion=EXONERACION),),
                    ),
                ),
            ),
        )

    def test_una_venta_con_de_todo(self, tmp_path):
        """Todo lo opcional a la vez: si el orden estuviera mal, se cae acá."""
        self._validar(
            tmp_path,
            comprobante(
                actividad_receptor="4711.1",
                medios_pago=(MedioPago("01", Decimal("500")), MedioPago("02", Decimal("1007"))),
                otros_cargos=(
                    OtroCargo(
                        tipo_documento="04",
                        detalle="Servicio de un tercero",
                        monto=Decimal("500"),
                        identificacion_tercero=Identificacion("02", "3101999888"),
                        nombre_tercero="Transportes Unidos S.A.",
                        porcentaje=Decimal("5"),
                    ),
                ),
                referencias=(
                    Referencia("01", "2026-09-18T10:00:00-06:00", numero="5" * 50, codigo="05"),
                ),
                otros=(Otro(codigo="OC", texto="L000298431"),),
                lineas=(
                    linea(
                        codigos_comerciales=(CodigoComercial("01", "SKU-1"),),
                        unidad_comercial="Caja",
                        descuentos=(Descuento(Decimal("100"), naturaleza="Promoción"),),
                        iva_cobrado_fabrica="01",
                        impuesto_asumido=Decimal("10"),
                        surtido=(
                            LineaSurtido(
                                cabys=MERCANCIA,
                                cantidad=Decimal(1),
                                unidad="Unid",
                                detalle="Café",
                                precio_unitario=Decimal("600"),
                                impuestos=(IVA13,),
                            ),
                        ),
                    ),
                ),
            ),
        )

    def test_un_tiquete_sin_receptor(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                tipo="04",
                receptor=None,
                medios_pago=(MedioPago("01", Decimal("1130")),),
            ),
        )

    @pytest.mark.parametrize("tipo", ["02", "03"])
    def test_una_nota(self, tmp_path, tipo):
        self._validar(
            tmp_path,
            nota(
                tipo=tipo,
                medios_pago=(MedioPago("01", Decimal("1130")),),
                lineas=(linea(partida_arancelaria="010121000000"),),
            ),
        )

    def test_una_factura_de_compra_a_un_no_contribuyente(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                tipo="08",
                emisor=Parte(
                    "Vendedor No Contribuyente",
                    Identificacion("01", "108880777"),
                    Ubicacion("1", "01", "01", "Dirección del vendedor"),
                    correo="vendedor@ejemplo.cr",
                ),
                actividad_receptor="4741.0",
                medios_pago=(MedioPago("01", Decimal("1130")),),
                referencias=(
                    Referencia(
                        "14",
                        "2026-09-18T10:00:00-06:00",
                        numero="000000123",
                        codigo="04",
                        razon="Comprobante de respaldo del proveedor",
                    ),
                ),
            ),
        )

    def test_una_exportacion(self, tmp_path):
        self._validar(
            tmp_path,
            comprobante(
                tipo="09",
                moneda="USD",
                tipo_cambio=Decimal("520"),
                receptor=Parte(
                    "INTERMARKET CORPORATION",
                    Identificacion("05", "0"),
                    otras_senas_extranjero="1201 Brickell Ave, Miami, FL",
                ),
                medios_pago=(MedioPago("01", Decimal("400")),),
                lineas=(
                    linea(
                        cabys="8595400000000",
                        unidad="Os",
                        detalle="Retiro de guía aérea",
                        precio_unitario=Decimal("400"),
                        partida_arancelaria="010121000000",
                        impuestos=(iva("10", "0"),),
                    ),
                ),
            ),
        )

    def test_un_recibo_de_pago(self, tmp_path):
        self._validar(tmp_path, recibo())
