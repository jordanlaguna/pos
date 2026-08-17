import pytest

from app.domain.errors import CannotCancel, InvalidQuantity, InvalidSource
from app.domain.money import Money
from app.domain.stock_entry import (
    SOURCES,
    EntryLine,
    check_cancellable,
    check_source,
    entry_total,
    entry_units,
)


def linea(cantidad=1, costo=1200, product_id=1):
    return EntryLine(product_id=product_id, quantity=cantidad, unit_cost=Money(costo))


class TestEntryLine:
    def test_el_subtotal_es_costo_por_cantidad(self):
        assert linea(24, 1200).subtotal == Money(28800)

    @pytest.mark.parametrize("mala", [0, -1, 1.5, "24", None, True])
    def test_rechaza_cantidades_que_no_tienen_sentido(self, mala):
        with pytest.raises(InvalidQuantity):
            linea(cantidad=mala)

    def test_rechaza_un_costo_negativo(self):
        with pytest.raises(InvalidQuantity):
            linea(costo=-1)

    def test_un_costo_de_cero_si_vale(self):
        # Mercadería de obsequio del proveedor.
        assert linea(5, 0).subtotal == Money.zero()


class TestOrigen:
    @pytest.mark.parametrize("origen", ["manual", "excel", "xml"])
    def test_los_tres_que_existen(self, origen):
        check_source(origen)

    @pytest.mark.parametrize("malo", ["whatsapp", "", None, "XML", 1])
    def test_cualquier_otro_no(self, malo):
        with pytest.raises(InvalidSource) as e:
            check_source(malo)
        assert e.value.source == malo

    def test_la_constante_dice_cuales_son(self):
        assert SOURCES == ("manual", "excel", "xml")


class TestTotales:
    def test_el_invariante_del_xml_de_hacienda(self):
        # 3 líneas de la factura de Distribuidora La Central: 42 unidades,
        # ₡79 800. El café va a 3 400 neto y no a 3 600 de lista, por el
        # descuento.
        lineas = [
            EntryLine(1, 24, Money(1200)),
            EntryLine(2, 15, Money(3400)),
            EntryLine(3, 3, Money(0)),
        ]
        assert entry_units(lineas) == 42
        assert entry_total(lineas) == Money(79800)

    def test_una_sola_linea(self):
        assert entry_total([linea(24, 1200)]) == Money(28800)

    def test_sin_lineas(self):
        assert entry_total([]) == Money.zero()
        assert entry_units([]) == 0

    def test_el_costo_unitario_ya_viene_redondeado(self):
        # `Money` redondea al construirse, así que 0,335 es 0,34 antes de
        # multiplicar: 3 × 0,34 = 1,02. Es lo mismo que hace la venta.
        assert Money("0.335") == Money("0.34")
        assert entry_total([EntryLine(1, 3, Money("0.335"))]) == Money("1.02")

    def test_redondea_linea_por_linea_y_no_al_final(self):
        lineas = [EntryLine(i, 1, Money("0.335")) for i in range(3)]
        assert entry_total(lineas) == Money("1.02")


class TestAnulable:
    def test_si_esta_todo_el_stock(self):
        check_cancellable(product_id=1, available=134, added=24)

    def test_si_queda_justo_lo_que_agrego(self):
        check_cancellable(product_id=1, available=24, added=24)

    def test_no_si_ya_se_vendio_parte(self):
        # Revertir dejaría el inventario en negativo.
        with pytest.raises(CannotCancel) as e:
            check_cancellable(product_id=7, available=5, added=24)
        assert (e.value.product_id, e.value.available, e.value.added) == (7, 5, 24)
