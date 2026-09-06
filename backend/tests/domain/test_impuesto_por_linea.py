"""El impuesto es la suma de los de cada tarifa, no el subtotal por una tasa (RN-10).

Es el corazón de F5. Hay tres cosas que probar y son distintas entre sí:

1. Que **nada de lo ya cobrado cambia**. Con una sola tarifa el resultado tiene
   que ser idéntico al de antes, hasta el céntimo, o esta fase movería plata que
   ya se verificó.
2. Que con tarifas mezcladas el total cuadra y el desglose suma.
3. Que **una devolución parcial usa la tarifa de su línea** y no el promedio del
   encabezado, que es el defecto que F5 existe para hacer imposible.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import EmptySale
from app.domain.money import Money
from app.domain.returns import ReturnLine, refund_total, refund_totals
from app.domain.sale import SaleLine, group_by_rate, sale_totals
from app.domain.tax import TaxRate

IVA = TaxRate(Decimal("0.13"))
MEDICAMENTO = TaxRate(Decimal("0.02"))
EXENTO = TaxRate.zero()


def linea(precio, cantidad=1, tarifa=None):
    return SaleLine(
        product_id=1, unit_price=Money(precio), quantity=cantidad, tax_rate=tarifa
    )


class TestNadaDeLoYaCobradoCambia:
    """Los invariantes de `progress.json`, recalculados con el código nuevo.

    Si alguno se moviera, F5 estaría cambiando lo que se cobró antes de F5.
    """

    def test_tres_unidades_de_1450_siguen_dando_4915_50(self):
        t = sale_totals([linea(1450, 3)], IVA)
        assert t.subtotal == Money("4350.00")
        assert t.tax == Money("565.50")
        assert t.total == Money("4915.50")

    def test_una_unidad_de_1450_sigue_dando_1638_50(self):
        assert sale_totals([linea(1450)], IVA).total == Money("1638.50")

    def test_arroz_mas_cafe_siguen_dando_6441(self):
        t = sale_totals([linea(1450, 3), linea(1350)], IVA)
        assert t.total == Money("6441.00")

    def test_con_precios_en_colones_enteros_da_igual_por_linea_que_por_subtotal(self):
        """Por qué las cuatro de arriba no se movieron.

        El catálogo son colones enteros, y ahí `round(base × tasa)` sumado por
        línea y aplicado al subtotal entero coinciden. Difieren solo cuando hay
        céntimos, y en un céntimo (medido: ~39 % de las ventas con céntimos).
        """
        lineas = [linea(1450, 3), linea(950), linea(2730), linea(4250, 2)]
        t = sale_totals(lineas, IVA)
        assert t.tax == IVA.apply(t.subtotal)

    def test_el_impuesto_del_documento_es_la_suma_del_de_sus_lineas(self):
        """La propiedad que hace que la factura cuadre consigo misma.

        `sale_details.tax_amount` guarda el impuesto de cada línea; si no
        sumaran el del encabezado, un reporte que sume líneas contradiría la
        factura —y Hacienda valida justamente esa igualdad—.

        Se prueba con céntimos a propósito: es donde la otra forma de redondear
        se separaba.
        """
        lineas = [linea(333.33, 3), linea(0.335, 7), linea(1999.99)]
        t = sale_totals(lineas, IVA)
        assert Money.sum(l.tax_with(IVA) for l in lineas) == t.tax

    def test_la_tarifa_de_la_linea_gana_sobre_la_del_documento(self):
        """Y con `None` manda la del documento, que es el caso de RN-9."""
        assert sale_totals([linea(1000, 1, EXENTO)], IVA).tax == Money("0.00")
        assert sale_totals([linea(1000, 1, None)], IVA).tax == Money("130.00")


class TestTarifasMezcladas:
    def test_el_caso_del_spec_medicamento_al_2_y_arroz_al_13(self):
        t = sale_totals([linea(1000, 1, MEDICAMENTO), linea(1000, 1, IVA)], IVA)
        assert t.subtotal == Money("2000.00")
        assert t.tax == Money("150.00")  # 20 + 130
        assert t.total == Money("2150.00")

    def test_el_desglose_suma_el_impuesto(self):
        t = sale_totals(
            [linea(1000, 1, MEDICAMENTO), linea(1000, 1, IVA), linea(500, 2, EXENTO)],
            IVA,
        )
        assert Money.sum(g.tax for g in t.by_rate) == t.tax
        assert Money.sum(g.base for g in t.by_rate) == t.subtotal

    def test_hay_una_entrada_por_tarifa_presente_y_ni_una_mas(self):
        t = sale_totals(
            [linea(100, 1, IVA), linea(200, 1, IVA), linea(300, 1, EXENTO)], IVA
        )
        assert [g.rate for g in t.by_rate] == [EXENTO, IVA]
        assert [g.base for g in t.by_rate] == [Money("300.00"), Money("300.00")]

    def test_el_desglose_va_de_menor_a_mayor_tarifa(self):
        """En un documento impreso el orden no puede depender de en qué orden
        marcó el cajero: se imprime igual las dos veces."""
        uno = sale_totals([linea(100, 1, IVA), linea(100, 1, EXENTO)], IVA)
        otro = sale_totals([linea(100, 1, EXENTO), linea(100, 1, IVA)], IVA)
        assert [g.rate for g in uno.by_rate] == [EXENTO, IVA]
        assert uno.by_rate == otro.by_rate

    def test_el_desglose_viene_aunque_haya_una_sola_tarifa(self):
        """Quien imprime decide si lo muestra (RF-21); el cálculo siempre lo da."""
        t = sale_totals([linea(1000)], IVA)
        assert len(t.by_rate) == 1
        assert t.by_rate[0].base == t.subtotal

    def test_una_venta_sin_lineas_sigue_sin_ser_una_venta(self):
        with pytest.raises(EmptySale):
            sale_totals([], IVA)


class TestGroupByRate:
    def test_sin_lineas_no_hay_grupos(self):
        assert group_by_rate([], IVA) == ()

    def test_la_tarifa_nula_cae_en_el_grupo_de_la_del_documento(self):
        """Y se junta con las que la traen escrita: son la misma tarifa."""
        grupos = group_by_rate([(Money(100), None), (Money(100), IVA)], IVA)
        assert len(grupos) == 1
        assert grupos[0].base == Money("200.00")

    def test_el_impuesto_del_grupo_es_la_suma_y_no_el_producto(self):
        """Dos bases que redondean distinto sumadas que multiplicadas.

        0,05 al 13 % da 0,01 dos veces —0,0065 redondea a 0,01— o sea 0,02
        sumando; multiplicando la base entera, 0,10 × 0,13 = 0,013 → 0,01. Se
        elige sumar porque es lo que guardan las líneas.
        """
        grupos = group_by_rate([(Money("0.05"), IVA), (Money("0.05"), IVA)], IVA)
        assert grupos[0].tax == Money("0.02")
        assert IVA.apply(Money("0.10")) == Money("0.01")


class TestLaDevolucionUsaLaTarifaDeSuLinea:
    """El caso que F5 existe para hacer imposible (plan §6.3)."""

    def test_devolver_solo_el_medicamento_da_1020_y_no_1075(self):
        devuelto = refund_total(
            [ReturnLine(product_id=1, unit_price=Money(1000), quantity=1,
                        tax_rate=MEDICAMENTO)],
            IVA,
        )
        assert devuelto == Money("1020.00")

    def test_devolver_solo_el_arroz_da_1130_y_no_1075(self):
        devuelto = refund_total(
            [ReturnLine(product_id=2, unit_price=Money(1000), quantity=1,
                        tax_rate=IVA)],
            IVA,
        )
        assert devuelto == Money("1130.00")

    def test_devolver_las_dos_lineas_devuelve_la_venta_entera(self):
        """La suma de las dos parciales tiene que ser la venta completa: si no,
        el negocio gana o pierde plata por el orden en que se devuelve."""
        venta = sale_totals([linea(1000, 1, MEDICAMENTO), linea(1000, 1, IVA)], IVA)
        completa = refund_total(
            [
                ReturnLine(product_id=1, unit_price=Money(1000), quantity=1,
                           tax_rate=MEDICAMENTO),
                ReturnLine(product_id=2, unit_price=Money(1000), quantity=1,
                           tax_rate=IVA),
            ],
            IVA,
        )
        assert completa == venta.total
        assert completa == Money("1020.00") + Money("1130.00")

    def test_una_venta_vieja_sin_tarifa_en_la_linea_usa_la_del_encabezado(self):
        """Es el respaldo de RN-12 para lo cobrado antes de la migración: esas
        ventas llevan una sola tarifa, así que el cociente del encabezado la
        reconstruye exacta."""
        vieja = TaxRate(Decimal("0.13"))
        devuelto = refund_total(
            [ReturnLine(product_id=1, unit_price=Money(1450), quantity=1)], vieja
        )
        assert devuelto == Money("1638.50")

    def test_la_devolucion_tambien_trae_su_desglose(self):
        """`returns` guarda subtotal e impuesto desde F5, así que el caso de uso
        necesita las dos cifras y no solo el total."""
        t = refund_totals(
            [
                ReturnLine(product_id=1, unit_price=Money(1000), quantity=1,
                           tax_rate=MEDICAMENTO),
                ReturnLine(product_id=2, unit_price=Money(1000), quantity=1,
                           tax_rate=IVA),
            ],
            IVA,
        )
        assert t.subtotal == Money("2000.00")
        assert t.tax == Money("150.00")
        assert t.total == Money("2150.00")
        assert [g.rate for g in t.by_rate] == [MEDICAMENTO, IVA]

    def test_una_devolucion_sin_lineas_no_devuelve_nada(self):
        """A diferencia de una venta, no es un error: lo usa la comprobación de
        «¿queda algo por devolver?» antes de que el cajero marque nada."""
        assert refund_total([], IVA) == Money.zero()
