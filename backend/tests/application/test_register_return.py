"""
El caso de uso de la devolución, sin base de datos.

Fija las dos reglas de plata: no se devuelve más de lo que se llevó —ni sumando
parciales— y se reembolsa con la tasa de SU venta, no con la de hoy.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.register_return import (
    EmptyReturn,
    MissingReason,
    RegisterReturn,
    RequestedReturnLine,
    ReturnRequest,
    SaleNotFound,
)
from app.domain.errors import ExcessiveReturn, InvalidQuantity, NotSoldInThisSale
from app.domain.money import Money
from app.domain.sale import SaleLine
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeProduct,
    FakeProductRepository,
    FakeReturnRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeUnitOfWork,
)

MOMENTO = datetime(2026, 8, 16, 22, 30, 0)
IVA = TaxRate("0.13")


def montar(tasa_configurada=IVA, tasa_de_la_venta=IVA):
    """Una venta de 3 arroces a 1450, cobrada con la tasa que se indique."""
    catalogo = FakeProductRepository(
        [
            FakeProduct(1, "Arroz 1 kg", Money(1450), stock=17),
            FakeProduct(2, "Café molido", Money(4250), stock=9),
        ]
    )
    ventas = FakeSaleRepository()
    subtotal = Money(4350)
    ventas.add(
        sale_number="20260816223000",
        client_id=None,
        user_id=1,
        subtotal=subtotal,
        tax=tasa_de_la_venta.apply(subtotal),
        total=tasa_de_la_venta.add_to(subtotal),
        payment_method="Efectivo",
        cash_received=Money(5000),
        change_given=Money(0),
        created_at=MOMENTO,
        lines=[SaleLine(1, Money(1450), 3)],
    )
    devoluciones = FakeReturnRepository()
    uow = FakeUnitOfWork()
    caso = RegisterReturn(
        sales=ventas,
        returns=devoluciones,
        products=catalogo,
        settings=FakeSettingsRepository(tasa_configurada),
        uow=uow,
        clock=FixedClock(MOMENTO),
    )
    return caso, catalogo, ventas, devoluciones, uow


def peticion(lineas, sale_id=1, motivo="producto dañado"):
    return ReturnRequest(
        sale_id=sale_id,
        user_id=1,
        reason=motivo,
        lines=[RequestedReturnLine(pid, cant) for pid, cant in lineas],
    )


class TestDevolucionBuena:
    def test_reembolsa_lo_que_se_cobro(self, ):
        caso, _, _, _, _ = montar()
        resultado = caso(peticion([(1, 1)]))
        assert resultado.total == Money("1638.50")

    def test_repone_las_existencias(self):
        """Lo que el sistema original no hacía."""
        caso, catalogo, _, _, _ = montar()
        caso(peticion([(1, 1)]))
        assert catalogo.get(1).stock == 18

    def test_usa_el_precio_de_la_linea_y_no_el_del_catalogo_de_hoy(self):
        caso, catalogo, _, devoluciones, _ = montar()
        catalogo.productos[1].price = Money(9999)  # subió el precio después

        caso(peticion([(1, 1)]))
        assert devoluciones.devoluciones[0].lines[0].unit_price == Money(1450)

    def test_una_parcial_deja_el_resto_por_devolver(self):
        caso, _, _, _, _ = montar()
        resultado = caso(peticion([(1, 1)]))
        assert not resultado.is_full

    def test_devolver_todo_la_marca_completa(self):
        caso, _, _, _, _ = montar()
        resultado = caso(peticion([(1, 3)]))
        assert resultado.is_full

    def test_dos_parciales_que_suman_todo_tambien(self):
        caso, _, _, _, _ = montar()
        caso(peticion([(1, 1)]))
        resultado = caso(peticion([(1, 2)]))
        assert resultado.is_full

    def test_la_hora_la_pone_el_servidor(self):
        caso, _, _, devoluciones, _ = montar()
        caso(peticion([(1, 1)]))
        assert devoluciones.devoluciones[0].created_at == MOMENTO

    def test_confirma_la_transaccion(self):
        caso, _, _, _, uow = montar()
        caso(peticion([(1, 1)]))
        assert uow.committed


class TestLaTasaEsLaDeSuVenta:
    def test_subir_el_iva_no_cambia_lo_que_se_reembolsa(self):
        # Se cobró al 13 % y hoy la configuración dice 25 %.
        caso, _, _, _, _ = montar(tasa_configurada=TaxRate("0.25"), tasa_de_la_venta=IVA)
        assert caso(peticion([(1, 1)])).total == Money("1638.50")

    def test_una_venta_exenta_se_devuelve_sin_impuesto(self):
        caso, _, _, _, _ = montar(tasa_configurada=IVA, tasa_de_la_venta=TaxRate.zero())
        assert caso(peticion([(1, 1)])).total == Money(1450)

    def test_una_venta_vieja_sin_desglose_usa_la_configurada(self):
        """
        Es el respaldo: las ventas del WinForms quedaron con subtotal en cero y
        no hay de dónde reconstruir la tasa.
        """
        caso, _, ventas, _, _ = montar()
        ventas.ventas[0].subtotal = Money.zero()
        ventas.ventas[0].tax = Money.zero()

        assert caso(peticion([(1, 1)])).total == Money("1638.50")


class TestDevolucionRechazada:
    """Lo que importa de cada una: que NO quede nada escrito ni repuesto."""

    def test_venta_que_no_existe(self):
        caso, _, _, devoluciones, _ = montar()
        with pytest.raises(SaleNotFound):
            caso(peticion([(1, 1)], sale_id=999))
        assert devoluciones.devoluciones == []

    def test_sin_lineas(self):
        caso, _, _, devoluciones, _ = montar()
        with pytest.raises(EmptyReturn):
            caso(peticion([]))
        assert devoluciones.devoluciones == []

    @pytest.mark.parametrize("motivo", ["", "   ", None])
    def test_sin_motivo(self, motivo):
        # Plata que salió de la gaveta y nadie sabe por qué.
        caso, _, _, devoluciones, _ = montar()
        with pytest.raises(MissingReason):
            caso(peticion([(1, 1)], motivo=motivo))
        assert devoluciones.devoluciones == []

    def test_un_producto_que_la_venta_no_llevaba(self):
        caso, catalogo, _, devoluciones, _ = montar()
        with pytest.raises(NotSoldInThisSale) as e:
            caso(peticion([(2, 1)]))

        assert e.value.product_id == 2
        assert devoluciones.devoluciones == []
        assert catalogo.get(2).stock == 9

    @pytest.mark.parametrize("cantidad", [0, -1])
    def test_cantidad_que_no_tiene_sentido(self, cantidad):
        caso, _, _, devoluciones, _ = montar()
        with pytest.raises(InvalidQuantity):
            caso(peticion([(1, cantidad)]))
        assert devoluciones.devoluciones == []

    def test_mas_unidades_de_las_que_se_llevo(self):
        caso, catalogo, _, devoluciones, _ = montar()
        with pytest.raises(ExcessiveReturn) as e:
            caso(peticion([(1, 4)]))

        assert (e.value.remaining, e.value.requested) == (3, 4)
        assert devoluciones.devoluciones == []
        assert catalogo.get(1).stock == 17, "se repuso stock de una devolución que falló"

    def test_ni_sumando_dos_parciales(self):
        """La regla que impide devolver la misma unidad dos veces."""
        caso, catalogo, _, devoluciones, _ = montar()
        caso(peticion([(1, 2)]))

        with pytest.raises(ExcessiveReturn) as e:
            caso(peticion([(1, 2)]))

        assert e.value.remaining == 1
        assert len(devoluciones.devoluciones) == 1
        assert catalogo.get(1).stock == 19, "se repuso de más"

    def test_si_falla_una_linea_no_entra_ninguna(self):
        caso, catalogo, _, devoluciones, _ = montar()
        with pytest.raises(NotSoldInThisSale):
            caso(peticion([(1, 1), (2, 1)]))

        assert devoluciones.devoluciones == []
        assert catalogo.get(1).stock == 17, "se repuso una línea de una devolución que falló"


class TestTarifasMezcladas:
    """El caso que F5 existe para hacer imposible (plan §6.3).

    Con una sola tarifa, `tax / subtotal` del encabezado la reconstruye exacta y
    todo cuadra. En cuanto se mezclan, ese cociente es un **promedio**, y
    devolver una sola línea con el promedio reembolsa de más o de menos.
    """

    MEDICAMENTO = TaxRate("0.02")

    def montar_mezclada(self):
        """Un medicamento al 2 % y un arroz al 13 %, ₡1 000 cada uno.

        Encabezado: subtotal ₡2 000, impuesto ₡150 → promedio 7,5 %.
        """
        catalogo = FakeProductRepository(
            [
                FakeProduct(1, "Medicamento", Money(1000), stock=10,
                            tax_rate=self.MEDICAMENTO),
                FakeProduct(2, "Arroz 1 kg", Money(1000), stock=10, tax_rate=IVA),
            ]
        )
        ventas = FakeSaleRepository()
        ventas.add(
            sale_number="20260905120000",
            client_id=None,
            user_id=1,
            subtotal=Money(2000),
            tax=Money(150),
            total=Money(2150),
            payment_method="Efectivo",
            cash_received=Money(2150),
            change_given=Money(0),
            created_at=MOMENTO,
            lines=[
                SaleLine(1, Money(1000), 1, tax_rate=self.MEDICAMENTO),
                SaleLine(2, Money(1000), 1, tax_rate=IVA),
            ],
        )
        devoluciones = FakeReturnRepository()
        caso = RegisterReturn(
            sales=ventas,
            returns=devoluciones,
            products=catalogo,
            settings=FakeSettingsRepository(IVA),
            uow=FakeUnitOfWork(),
            clock=FixedClock(MOMENTO),
        )
        return caso, devoluciones

    def test_devolver_solo_el_medicamento_da_1020_y_no_1075(self):
        caso, devoluciones = self.montar_mezclada()
        hecha = caso(peticion([(1, 1)]))

        assert hecha.total == Money("1020.00"), "usó el promedio del encabezado"
        assert devoluciones.devoluciones[0].tax == Money("20.00")
        assert devoluciones.devoluciones[0].subtotal == Money("1000.00")

    def test_devolver_solo_el_arroz_da_1130_y_no_1075(self):
        caso, _ = self.montar_mezclada()
        assert caso(peticion([(2, 1)])).total == Money("1130.00")

    def test_las_dos_parciales_suman_la_venta_entera(self):
        """Si no sumaran, el negocio ganaría o perdería según el orden en que se
        devuelva, que es la peor forma de perder plata: nadie la ve."""
        caso, _ = self.montar_mezclada()
        primera = caso(peticion([(1, 1)])).total
        segunda = caso(peticion([(2, 1)])).total
        assert primera + segunda == Money("2150.00")

    def test_una_venta_vieja_sin_tarifa_en_la_linea_usa_la_del_encabezado(self):
        """RN-12 para lo cobrado antes de la migración 006: esas ventas llevan
        una sola tarifa y el cociente la reconstruye exacta."""
        caso, _, _, devoluciones, _ = montar(
            tasa_configurada=TaxRate("0.25"), tasa_de_la_venta=IVA
        )
        hecha = caso(peticion([(1, 1)]))

        assert hecha.total == Money("1638.50"), "usó la tasa de hoy y no la de su venta"
        assert devoluciones.devoluciones[0].tax == Money("188.50")
