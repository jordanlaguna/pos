"""
El caso de uso de la venta, sin base de datos.

Estas pruebas corren en milisegundos y comprueban lo que antes solo se podía
verificar levantando MySQL: entre ellas, que un fallo por falta de existencias
no deje una venta guardada. Ese era el defecto 1.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.register_sale import (
    ProductNotFound,
    ProductWithoutPrice,
    RegisterSale,
    RequestedLine,
    SaleRequest,
)
from app.domain.errors import (
    DuplicateSaleNumber,
    EmptySale,
    InsufficientPayment,
    InsufficientStock,
    InvalidQuantity,
    TotalsMismatch,
)
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeProduct,
    FakeProductRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeUnitOfWork,
)

MOMENTO = datetime(2026, 8, 16, 22, 30, 0)
IVA = TaxRate("0.13")


@pytest.fixture
def catalogo():
    return FakeProductRepository(
        [
            FakeProduct(1, "Arroz 1 kg", Money(1450), stock=20),
            FakeProduct(2, "Café molido", Money(4250), stock=10),
            FakeProduct(3, "Sin precio", None, stock=5),
            FakeProduct(4, "Escaso", Money(1000), stock=2),
        ]
    )


@pytest.fixture
def escenario(catalogo):
    ventas = FakeSaleRepository()
    uow = FakeUnitOfWork()
    caso = RegisterSale(
        products=catalogo,
        sales=ventas,
        settings=FakeSettingsRepository(IVA),
        uow=uow,
        clock=FixedClock(MOMENTO),
    )
    return caso, catalogo, ventas, uow


def peticion(lineas, **cambios):
    """
    Una petición con los totales ya correctos.

    Se calculan acá con las mismas cifras que usaría el POS, de modo que cada
    prueba solo tenga que alterar lo que quiere probar.
    """
    precios = {1: 1450, 2: 4250, 3: 0, 4: 1000}
    subtotal = Money(sum(precios.get(pid, 0) * cant for pid, cant in lineas))
    impuesto = IVA.apply(subtotal)
    total = subtotal + impuesto

    base = dict(
        sale_number="20260816223000",
        client_id=None,
        user_id=1,
        subtotal=subtotal,
        tax=impuesto,
        total=total,
        payment_method="Efectivo",
        cash_received=total,
        change_given=Money(0),
        lines=[RequestedLine(pid, cant) for pid, cant in lineas],
    )
    base.update(cambios)
    return SaleRequest(**base)


class TestVentaBuena:
    def test_guarda_la_venta_y_devuelve_su_id(self, escenario):
        caso, _, ventas, _ = escenario
        resultado = caso(peticion([(1, 3)]))

        assert resultado.id_sale == 1
        assert len(ventas.ventas) == 1

    def test_descuenta_las_existencias(self, escenario):
        caso, catalogo, _, _ = escenario
        caso(peticion([(1, 3), (2, 1)]))

        assert catalogo.get(1).stock == 17
        assert catalogo.get(2).stock == 9

    def test_el_precio_lo_pone_el_catalogo_y_no_quien_llama(self, escenario):
        # La regla del proyecto: los precios se releen del backend.
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 3)]))

        linea = ventas.ventas[0].lines[0]
        assert linea.unit_price == Money(1450)
        assert linea.subtotal == Money(4350)

    def test_la_hora_la_pone_el_reloj_del_servidor(self, escenario):
        # Defecto 9: si la pusiera el cliente, bastarían unos segundos de
        # desfase para que la venta cayera fuera de su turno de caja.
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 1)]))

        assert ventas.ventas[0].created_at == MOMENTO

    def test_confirma_la_transaccion(self, escenario):
        caso, _, _, uow = escenario
        caso(peticion([(1, 1)]))

        assert uow.committed and not uow.rolled_back

    def test_bloquea_los_productos_antes_de_escribir(self, escenario):
        caso, catalogo, _, _ = escenario
        caso(peticion([(2, 1), (1, 1)]))

        # Todos de una sola vez: pedirlos uno por uno desde dos cajas en distinto
        # orden es como se fabrica un interbloqueo.
        assert catalogo.bloqueados == [[2, 1]]


class TestVentaRechazada:
    """Lo que importa de cada una: que NO quede nada escrito."""

    def test_sin_lineas(self, escenario):
        caso, _, ventas, uow = escenario
        with pytest.raises(EmptySale):
            caso(peticion([]))
        assert ventas.ventas == []
        # Ni siquiera se abrió la transacción.
        assert uow.entradas == 0

    def test_numero_de_factura_repetido(self, escenario):
        """
        Dos ventas con el mismo consecutivo son un problema de Hacienda. La
        comprobación estaba en el router; es una regla de la venta (T-110).
        """
        caso, _, ventas, uow = escenario
        caso(peticion([(1, 1)], cash_received=Money(5000)))

        with pytest.raises(DuplicateSaleNumber) as e:
            caso(peticion([(1, 1)], cash_received=Money(5000)))

        assert e.value.sale_number == "20260816223000"
        assert len(ventas.ventas) == 1
        assert uow.entradas == 1, "se abrió una transacción para nada"

    @pytest.mark.parametrize("linea", [(1, 0), (1, -2), (0, 3), (None, 3)])
    def test_cantidad_o_producto_no_validos(self, escenario, linea):
        caso, _, ventas, uow = escenario
        with pytest.raises(InvalidQuantity):
            caso(peticion([linea]))
        assert ventas.ventas == []
        assert uow.entradas == 0

    def test_producto_que_no_existe(self, escenario):
        caso, _, ventas, uow = escenario
        with pytest.raises(ProductNotFound) as e:
            caso(peticion([(99, 1)]))

        assert e.value.product_id == 99
        assert ventas.ventas == []
        assert uow.rolled_back

    def test_producto_sin_precio(self, escenario):
        caso, _, ventas, uow = escenario
        with pytest.raises(ProductWithoutPrice) as e:
            caso(peticion([(3, 1)]))

        assert e.value.product_id == 3
        assert ventas.ventas == []
        assert uow.rolled_back

    def test_sin_existencias_no_deja_factura_fantasma(self, escenario):
        """
        Defecto 1, ahora comprobado sin base de datos.

        La versión original confirmaba la cabecera ANTES de validar el stock, y
        su `except` solo atrapaba `SQLAlchemyError`: el error de existencias
        subía sin revertir y dejaba una venta guardada sin líneas y sin
        descontar inventario.
        """
        caso, catalogo, ventas, uow = escenario
        with pytest.raises(InsufficientStock) as e:
            caso(peticion([(4, 5)]))

        assert (e.value.available, e.value.requested) == (2, 5)
        assert ventas.ventas == [], "quedó una venta guardada pese al fallo"
        assert catalogo.get(4).stock == 2, "se tocó el inventario pese al fallo"
        assert uow.rolled_back and not uow.committed

    def test_si_falla_una_linea_no_entra_ninguna(self, escenario):
        # La primera línea es válida; la segunda no. O entra todo, o nada.
        caso, catalogo, ventas, _ = escenario
        with pytest.raises(InsufficientStock):
            caso(peticion([(1, 2), (4, 99)]))

        assert ventas.ventas == []
        assert catalogo.get(1).stock == 20, "se descontó de una línea de una venta que falló"


class TestLaPlataLaCalculaElServidor:
    """T-108b. Lo que se guarda es lo del servidor, siempre."""

    def test_guarda_los_totales_que_calcula_el_y_no_los_que_le_mandan(self, escenario):
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 3)], cash_received=Money(5000)))

        guardada = ventas.ventas[0]
        assert (guardada.subtotal, guardada.tax, guardada.total) == (
            Money(4350),
            Money("565.50"),
            Money("4915.50"),
        )
        assert guardada.lines[0].subtotal == Money(4350)

    def test_el_vuelto_lo_calcula_el_servidor(self, escenario):
        # Ni se recibe: se calcula. Así no puede ser negativo ni estar mal.
        caso, _, ventas, _ = escenario
        resultado = caso(
            peticion([(1, 3)], cash_received=Money(5000), change_given=Money(99999))
        )

        assert resultado.change_given == Money("84.50")
        assert ventas.ventas[0].change_given == Money("84.50")

    def test_usa_la_tasa_configurada_y_no_una_fija(self, catalogo):
        ventas = FakeSaleRepository()
        caso = RegisterSale(
            products=catalogo,
            sales=ventas,
            settings=FakeSettingsRepository(TaxRate("0.04")),
            uow=FakeUnitOfWork(),
            clock=FixedClock(MOMENTO),
        )
        caso(
            peticion(
                [(1, 1)],
                subtotal=Money(1450),
                tax=Money(58),
                total=Money(1508),
                cash_received=Money(1508),
            )
        )

        assert ventas.ventas[0].tax == Money(58)

    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("subtotal", Money(1)),
            ("tax", Money(1)),
            ("total", Money(1)),
            ("total", Money(999999)),
        ],
    )
    def test_rechaza_una_cabecera_que_no_cuadra(self, escenario, campo, valor):
        """
        Un catálogo viejo, un carrito desincronizado o un cliente alterado.
        Antes esto quedaba guardado tal cual: una venta cuyos totales no
        correspondían a sus propias líneas.
        """
        caso, _, ventas, _ = escenario
        with pytest.raises(TotalsMismatch):
            caso(peticion([(1, 3)], cash_received=Money(999999), **{campo: valor}))

        assert ventas.ventas == []

    def test_tolera_un_centimo_de_diferencia(self, escenario):
        """
        El POS calcula en coma flotante y el servidor en decimal exacto, y en
        los empates a medio céntimo difieren en 0,01. Con tolerancia cero, esa
        diferencia rechazaría ventas buenas. Lo que se guarda sigue siendo lo
        del servidor.
        """
        caso, _, ventas, _ = escenario
        caso(
            peticion(
                [(1, 3)],
                tax=Money("565.51"),
                total=Money("4915.51"),
                cash_received=Money(5000),
            )
        )

        assert ventas.ventas[0].total == Money("4915.50")

    def test_el_efectivo_tiene_que_alcanzar(self, escenario):
        caso, _, ventas, _ = escenario
        with pytest.raises(InsufficientPayment) as e:
            caso(peticion([(1, 3)], cash_received=Money(1000)))

        assert e.value.total == Money("4915.50")
        assert ventas.ventas == []

    def test_pagar_justo_alcanza(self, escenario):
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 3)], cash_received=Money("4915.50")))
        assert ventas.ventas[0].change_given == Money.zero()
