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
    ClientNotFound,
    ProductNotFound,
    ProductWithoutPrice,
    RegisterSale,
    RequestedLine,
    SaleRequest,
)
from app.domain.errors import (
    DocumentTypeNotEnabled,
    DuplicateSaleNumber,
    EmptySale,
    ExportLineNeedsTariffHeading,
    ExportNeedsForeignAddress,
    ExportNeedsForeignReceiver,
    ExportNeedsReceiver,
    ExportTariffNotAllowed,
    InsufficientPayment,
    InsufficientStock,
    InvalidQuantity,
    InvalidSaleDocumentType,
    InvoiceNeedsReceiver,
    InvoiceNeedsResident,
    TotalsMismatch,
)
from app.domain.fe_document_type import DEFAULT_ENABLED, EXPORT_INVOICE, INVOICE, TICKET
from app.domain.money import Money
from app.domain.tax import GENERAL_RATE, TaxRate
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeClient,
    FakeClientRepository,
    FakeProduct,
    FakeProductRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeUnitOfWork,
)

MOMENTO = datetime(2026, 8, 16, 22, 30, 0)
IVA = TaxRate("0.13")
#: El único cliente de la compañía de estas pruebas.
CLIENTE = 7


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
        clients=FakeClientRepository({CLIENTE}),
        settings=FakeSettingsRepository(),
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

    def test_sin_tarifa_propia_paga_la_general_del_iva(self, catalogo):
        """RN-9 desde QA-05: el respaldo es el 13 % de ley y ya no se configura."""
        ventas = FakeSaleRepository()
        caso = RegisterSale(
            products=catalogo,
            sales=ventas,
            clients=FakeClientRepository(),
            settings=FakeSettingsRepository(),
            uow=FakeUnitOfWork(),
            clock=FixedClock(MOMENTO),
        )
        caso(
            peticion(
                [(1, 1)],
                subtotal=Money(1450),
                tax=Money("188.50"),
                total=Money("1638.50"),
                cash_received=Money("1638.50"),
            )
        )

        assert ventas.ventas[0].tax == Money("188.50")
        assert ventas.ventas[0].lines[0].tax_rate == GENERAL_RATE

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


class TestElCliente:
    def test_el_cliente_de_la_compania_entra(self, escenario):
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 1)], client_id=CLIENTE))
        assert ventas.ventas[0].client_id == CLIENTE

    def test_el_de_otra_compania_no(self, escenario):
        """Antes pasaba derecho a la foránea, que no sabe de compañías."""
        caso, _, ventas, uow = escenario
        with pytest.raises(ClientNotFound) as e:
            caso(peticion([(1, 1)], client_id=99))

        assert e.value.client_id == 99
        assert ventas.ventas == []
        assert uow.entradas == 0, "se abrió una transacción para nada"


def con_facturacion(catalogo, *, activa: bool = True, encendidos=None):
    ventas = FakeSaleRepository()
    caso = RegisterSale(
        products=catalogo,
        sales=ventas,
        clients=FakeClientRepository({CLIENTE}),
        settings=FakeSettingsRepository(einvoicing=activa, document_types=encendidos),
        uow=FakeUnitOfWork(),
        clock=FixedClock(MOMENTO),
    )
    return caso, ventas


class TestElComprobante:
    """RN-85: el tipo se decide al vender y lo decide el receptor."""

    def test_sin_cliente_sale_tiquete(self, catalogo):
        # El supermercado: el cliente de contado no puede recibir una factura.
        caso, ventas = con_facturacion(catalogo)
        resultado = caso(peticion([(1, 1)]))

        assert ventas.ventas[0].document_type == TICKET
        assert resultado.document_type == TICKET

    def test_con_cliente_sale_factura(self, catalogo):
        caso, ventas = con_facturacion(catalogo)
        caso(peticion([(1, 1)], client_id=CLIENTE))
        assert ventas.ventas[0].document_type == INVOICE

    def test_el_cajero_puede_dejar_en_tiquete_a_un_cliente(self, catalogo):
        caso, ventas = con_facturacion(catalogo)
        caso(peticion([(1, 1)], client_id=CLIENTE, document_type=TICKET))
        assert ventas.ventas[0].document_type == TICKET

    def test_factura_sin_cliente_no_entra(self, catalogo):
        caso, ventas = con_facturacion(catalogo)
        with pytest.raises(InvoiceNeedsReceiver):
            caso(peticion([(1, 1)], document_type=INVOICE))
        assert ventas.ventas == []

    def test_un_tipo_desconocido_no_entra(self, catalogo):
        caso, ventas = con_facturacion(catalogo)
        with pytest.raises(InvalidSaleDocumentType):
            caso(peticion([(1, 1)], document_type="03"))
        assert ventas.ventas == []

    def test_con_la_facturacion_apagada_no_lleva_tipo(self, catalogo):
        """Aunque se lo pidan: el dueño pudo apagarla con la caja abierta."""
        caso, ventas = con_facturacion(catalogo, activa=False)
        caso(peticion([(1, 1)], client_id=CLIENTE, document_type=INVOICE))
        assert ventas.ventas[0].document_type is None


class TestLoQueEmiteLaCompania:
    """RN-88: la venta respeta lo que la compañía tiene encendido."""

    SOLO_FACTURA = frozenset({INVOICE, "03"})
    SOLO_TIQUETE = frozenset({TICKET, "03"})

    def test_sin_tiquete_y_sin_cliente_no_hay_venta(self, catalogo):
        # La distribuidora que solo factura.
        caso, ventas = con_facturacion(catalogo, encendidos=self.SOLO_FACTURA)
        with pytest.raises(InvoiceNeedsReceiver):
            caso(peticion([(1, 1)]))
        assert ventas.ventas == []

    def test_sin_tiquete_con_cliente_sale_factura(self, catalogo):
        caso, ventas = con_facturacion(catalogo, encendidos=self.SOLO_FACTURA)
        caso(peticion([(1, 1)], client_id=CLIENTE))
        assert ventas.ventas[0].document_type == INVOICE

    def test_sin_factura_el_cliente_recibe_tiquete(self, catalogo):
        caso, ventas = con_facturacion(catalogo, encendidos=self.SOLO_TIQUETE)
        caso(peticion([(1, 1)], client_id=CLIENTE))
        assert ventas.ventas[0].document_type == TICKET

    def test_pedir_uno_apagado_no_entra(self, catalogo):
        caso, ventas = con_facturacion(catalogo, encendidos=self.SOLO_TIQUETE)
        with pytest.raises(DocumentTypeNotEnabled):
            caso(peticion([(1, 1)], client_id=CLIENTE, document_type=INVOICE))
        assert ventas.ventas == []


class TestLaLineaDiceConQueSeVendio:
    """RN-86, T-731: el CABYS y la unidad se congelan en la línea, como la tarifa."""

    def test_copia_el_cabys_y_la_unidad_del_producto(self):
        catalogo = FakeProductRepository(
            [
                FakeProduct(
                    1, "Arroz 1 kg", Money(1450), stock=20,
                    cabys_code="2316100000100", unit_of_measure="kg",
                ),
            ]
        )
        caso, _, ventas, _ = _escenario_con(catalogo)
        caso(peticion([(1, 2)]))

        linea = ventas.ventas[0].lines[0]
        assert linea.cabys_code == "2316100000100"
        assert linea.unit_of_measure == "kg"

    def test_un_producto_sin_clasificar_deja_la_linea_vacia(self, escenario):
        caso, _, ventas, _ = escenario
        caso(peticion([(1, 1)]))

        linea = ventas.ventas[0].lines[0]
        assert linea.cabys_code is None
        assert linea.unit_of_measure is None


def _escenario_con(catalogo):
    ventas = FakeSaleRepository()
    uow = FakeUnitOfWork()
    caso = RegisterSale(
        products=catalogo,
        sales=ventas,
        clients=FakeClientRepository({CLIENTE}),
        settings=FakeSettingsRepository(),
        uow=uow,
        clock=FixedClock(MOMENTO),
    )
    return caso, catalogo, ventas, uow


#: El cliente del extranjero de la compañía (identificación 05) y una partida.
EXTRANJERO = 8
PARTIDA = "090111000000"
MERCANCIA = "2316100000100"
SERVICIO = "8595400000000"
CON_EXPORTACION = DEFAULT_ENABLED | {EXPORT_INVOICE}


def catalogo_exportable(**cafe):
    """El café (1), una mercancía con partida y tarifa general, y una asesoría
    (2), un servicio sin partida. Los precios son los de `peticion`."""
    base = dict(tax_code="08", cabys_code=MERCANCIA, tariff_heading=PARTIDA)
    base.update(cafe)
    return FakeProductRepository(
        [
            FakeProduct(1, "Café de exportación", Money(1450), stock=20, **base),
            FakeProduct(2, "Asesoría", Money(4250), stock=10, tax_code="08", cabys_code=SERVICIO),
        ]
    )


def exportando(catalogo, *, direccion="12 Main St, Miami", encendidos=CON_EXPORTACION):
    ventas = FakeSaleRepository()
    uow = FakeUnitOfWork()
    caso = RegisterSale(
        products=catalogo,
        sales=ventas,
        clients=FakeClientRepository(
            {CLIENTE},
            [FakeClient(EXTRANJERO, identification_type="05", foreign_address=direccion)],
        ),
        settings=FakeSettingsRepository(einvoicing=True, document_types=encendidos),
        uow=uow,
        clock=FixedClock(MOMENTO),
    )
    return caso, ventas, uow


class TestLaExportacion:
    """RF-78, RN-87, T-727: al cliente del extranjero se le exporta, y la
    exportación exige la partida de cada mercancía, una tarifa que la FEE
    admita y la dirección del cliente. Todo antes de escribir."""

    def test_al_extranjero_le_sale_exportacion_con_la_partida_congelada(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        resultado = caso(peticion([(1, 2)], client_id=EXTRANJERO))

        assert resultado.document_type == EXPORT_INVOICE
        assert ventas.ventas[0].document_type == EXPORT_INVOICE
        assert ventas.ventas[0].lines[0].tariff_heading == PARTIDA

    def test_un_servicio_sin_partida_tambien_se_exporta(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        caso(peticion([(2, 1)], client_id=EXTRANJERO))
        assert ventas.ventas[0].lines[0].tariff_heading is None

    def test_el_cajero_puede_dejar_al_extranjero_en_tiquete(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        caso(peticion([(1, 1)], client_id=EXTRANJERO, document_type=TICKET))
        assert ventas.ventas[0].document_type == TICKET
        # Y la partida no se congela: en un tiquete no significa nada.
        assert ventas.ventas[0].lines[0].tariff_heading is None

    def test_con_la_exportacion_apagada_el_extranjero_recibe_tiquete(self):
        caso, ventas, _ = exportando(catalogo_exportable(), encendidos=DEFAULT_ENABLED)
        caso(peticion([(1, 1)], client_id=EXTRANJERO))
        assert ventas.ventas[0].document_type == TICKET

    def test_facturarle_al_extranjero_no_entra_ni_abre_transaccion(self):
        caso, ventas, uow = exportando(catalogo_exportable())
        with pytest.raises(InvoiceNeedsResident):
            caso(peticion([(1, 1)], client_id=EXTRANJERO, document_type=INVOICE))
        assert ventas.ventas == []
        assert uow.entradas == 0

    def test_exportarle_a_uno_del_pais_no(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        with pytest.raises(ExportNeedsForeignReceiver):
            caso(peticion([(1, 1)], client_id=CLIENTE, document_type=EXPORT_INVOICE))
        assert ventas.ventas == []

    def test_exportar_sin_cliente_no(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        with pytest.raises(ExportNeedsReceiver):
            caso(peticion([(1, 1)], document_type=EXPORT_INVOICE))
        assert ventas.ventas == []

    @pytest.mark.parametrize("sin", [None, "   "])
    def test_sin_direccion_extranjera_no_entra_antes_de_la_transaccion(self, sin):
        caso, ventas, uow = exportando(catalogo_exportable(), direccion=sin)
        with pytest.raises(ExportNeedsForeignAddress) as e:
            caso(peticion([(1, 1)], client_id=EXTRANJERO))
        assert e.value.client_id == EXTRANJERO
        assert ventas.ventas == []
        assert uow.entradas == 0

    def test_una_mercancia_sin_partida_no_entra_y_dice_cual(self):
        catalogo = catalogo_exportable(tariff_heading=None)
        caso, ventas, _ = exportando(catalogo)
        with pytest.raises(ExportLineNeedsTariffHeading) as e:
            caso(peticion([(2, 1), (1, 1)], client_id=EXTRANJERO))
        assert e.value.product_id == 1
        assert ventas.ventas == []
        # Y no tocó existencias: se dijo que no antes de escribir.
        assert catalogo.get(1).stock == 20
        assert catalogo.get(2).stock == 10

    @pytest.mark.parametrize("codigo", ["01", "11"])
    def test_una_tarifa_que_la_exportacion_no_admite_no_entra(self, codigo):
        caso, ventas, _ = exportando(catalogo_exportable(tax_code=codigo))
        with pytest.raises(ExportTariffNotAllowed) as e:
            caso(peticion([(1, 1)], client_id=EXTRANJERO))
        assert (e.value.product_id, e.value.tax_code) == (1, codigo)
        assert ventas.ventas == []

    def test_a_uno_del_pais_la_partida_no_se_congela(self):
        caso, ventas, _ = exportando(catalogo_exportable())
        caso(peticion([(1, 1)], client_id=CLIENTE))
        assert ventas.ventas[0].document_type == INVOICE
        assert ventas.ventas[0].lines[0].tariff_heading is None


class TestElNumeroLoPoneElServidor:
    """T-706: `sale_number` deja de venir del navegador."""

    def test_sin_numero_sale_el_del_reloj_del_servidor(self, escenario):
        caso, _, ventas, _ = escenario
        hecha = caso(peticion([(1, 1)], sale_number=None))
        assert ventas.get(hecha.id_sale).sale_number == "20260816223000"

    def test_dos_ventas_en_el_mismo_segundo_no_chocan(self, escenario):
        caso, _, ventas, _ = escenario
        primera = caso(peticion([(1, 1)], sale_number=None))
        segunda = caso(peticion([(1, 1)], sale_number=None))
        tercera = caso(peticion([(1, 1)], sale_number=None))
        assert ventas.get(primera.id_sale).sale_number == "20260816223000"
        assert ventas.get(segunda.id_sale).sale_number == "20260816223000-2"
        assert ventas.get(tercera.id_sale).sale_number == "20260816223000-3"

    def test_un_cliente_viejo_que_lo_manda_sigue_pudiendo(self, escenario):
        caso, _, ventas, _ = escenario
        hecha = caso(peticion([(1, 1)], sale_number="A-1"))
        assert ventas.get(hecha.id_sale).sale_number == "A-1"
