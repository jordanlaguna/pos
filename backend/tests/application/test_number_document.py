"""
La numeración de los comprobantes, sin base de datos (T-704, T-705).

Lo que importa: que cada serie cuente por su lado —tipo y ambiente—, que la
clave lleve la fecha de la emisión y la cédula de la compañía, que un número
solo se consuma cuando el comprobante de verdad se guarda, y que la venta, la
devolución y la nota numeren dentro de su propia transacción.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.ports.numbering import Office
from app.application.use_cases.number_document import (
    SOURCE_NOTE,
    SOURCE_RETURN,
    SOURCE_SALE,
    NumberDocument,
)
from app.application.use_cases.register_note import RegisterAmountNote
from app.application.use_cases.register_return import (
    RegisterReturn,
    RequestedReturnLine,
    ReturnRequest,
)
from app.application.use_cases.register_sale import RegisterSale
from app.domain.errors import InsufficientStock, IssuerIdentificationRequired
from app.domain.fe_document_type import CREDIT_NOTE, DEBIT_NOTE, INVOICE, TICKET
from app.domain.fe_key import MAX_SEQUENCE, SITUATION_NORMAL
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeClientRepository,
    FakeDocumentNumbering,
    FakeIssuerRepository,
    FakeProduct,
    FakeProductRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeUnitOfWork,
    numerador,
)
from .test_register_note import AHORA, Mundo, pedir
from .test_register_sale import CLIENTE, IVA, MOMENTO, peticion


def numerar(caso: NumberDocument, tipo: str = TICKET, *, cuando: datetime = MOMENTO, origen=SOURCE_SALE, id_=1):
    emisor = caso.prepare()
    return caso.number(emisor, source_type=origen, source_id=id_, document_type=tipo, issued_at=cuando)


class TestLaClaveQueSeArma:
    def test_la_primera_de_la_serie(self):
        caso, _ = numerador()
        hecho = numerar(caso, TICKET, cuando=datetime(2026, 9, 24, 18, 19, 20))

        assert hecho.sequence == 1
        assert hecho.consecutive == "00100001040000000001"
        # País, 24/09/26, la jurídica con dos ceros, el consecutivo, normal y
        # el código de seguridad que dio el doble.
        assert hecho.clave == "506240926003101702934" + "00100001040000000001" + "1" + "00000001"
        assert hecho.situation == SITUATION_NORMAL

    def test_lleva_la_oficina_de_la_sesion(self):
        caso, _ = numerador(numbering=FakeDocumentNumbering(Office("3", "12")))
        assert numerar(caso).consecutive.startswith("00300012")

    def test_queda_registrado_con_su_origen_y_su_ambiente(self):
        caso, contador = numerador(FakeIssuerRepository(environment="production"))
        numerar(caso, INVOICE, origen=SOURCE_RETURN, id_=42)

        registrado = contador.comprobantes[0]
        assert (registrado.source_type, registrado.source_id) == (SOURCE_RETURN, 42)
        assert (registrado.document_type, registrado.environment) == (INVOICE, "production")
        assert registrado.economic_activity == "474100"
        assert registrado.issued_at == MOMENTO

    def test_sin_actividad_configurada_queda_nula_y_no_vacia(self):
        caso, contador = numerador(FakeIssuerRepository(economic_activity=""))
        numerar(caso)
        assert contador.comprobantes[0].economic_activity is None


class TestLasSeries:
    """Cinco dimensiones (plan §7.2): con menos, las series nacen con huecos."""

    def test_tiquete_factura_tiquete_no_se_saltan_numeros(self):
        caso, _ = numerador()
        uno, factura, dos = numerar(caso, TICKET), numerar(caso, INVOICE), numerar(caso, TICKET)

        # Un contador por caja daría tiquetes 1 y 3; por tipo, 1 y 2.
        assert (uno.sequence, dos.sequence) == (1, 2)
        assert factura.sequence == 1

    def test_pruebas_no_consume_numeros_de_produccion(self):
        # RN-34: cinco tiquetes de ensayo no se comen los cinco primeros reales.
        contador = FakeDocumentNumbering()
        pruebas, _ = numerador(FakeIssuerRepository(environment="sandbox"), contador)
        produccion, _ = numerador(FakeIssuerRepository(environment="production"), contador)
        for _ in range(5):
            numerar(pruebas)

        assert numerar(produccion).sequence == 1
        assert contador.series == {(TICKET, "sandbox"): 5, (TICKET, "production"): 1}

    def test_sigue_desde_donde_iba(self):
        # T-616: un negocio que viene de otro sistema arranca donde se quedó.
        caso, contador = numerador(numbering=FakeDocumentNumbering(series={(INVOICE, "sandbox"): 4200}))
        assert numerar(caso, INVOICE).sequence == 4201
        assert contador.series[(INVOICE, "sandbox")] == 4201

    def test_al_tope_vuelve_a_uno(self):
        caso, _ = numerador(numbering=FakeDocumentNumbering(series={(TICKET, "sandbox"): MAX_SEQUENCE}))
        assert numerar(caso).sequence == 1


class TestSinCedulaNoHayClave:
    @pytest.mark.parametrize("vacia", [None, "", "   "])
    def test_una_que_falta(self, vacia):
        caso, _ = numerador(FakeIssuerRepository(vacia))
        with pytest.raises(IssuerIdentificationRequired) as e:
            caso.prepare()
        assert e.value.reason == "missing"

    def test_una_que_no_cabe_en_la_clave(self):
        # Dice que no antes de la transacción, no a mitad de ella.
        caso, _ = numerador(FakeIssuerRepository("31017O2934"))
        with pytest.raises(IssuerIdentificationRequired) as e:
            caso.prepare()
        assert e.value.reason == "invalid"


# ------------------------------------------------------------ en los tres casos


def venta_con_numeracion(catalogo, issuer: FakeIssuerRepository | None = None, *, activa=True):
    numeracion, contador = numerador(issuer)
    ventas = FakeSaleRepository()
    uow = FakeUnitOfWork()
    caso = RegisterSale(
        products=catalogo,
        sales=ventas,
        clients=FakeClientRepository({CLIENTE}),
        settings=FakeSettingsRepository(IVA, einvoicing=activa),
        uow=uow,
        clock=FixedClock(MOMENTO),
        numbering=numeracion,
    )
    return caso, ventas, contador, uow


@pytest.fixture
def catalogo():
    # El mismo de `test_register_sale.py`: `peticion` calcula con estos precios.
    return FakeProductRepository(
        [
            FakeProduct(1, "Arroz 1 kg", Money(1450), stock=20),
            FakeProduct(2, "Café molido", Money(4250), stock=10),
            FakeProduct(4, "Escaso", Money(1000), stock=2),
        ]
    )


class TestLaVenta:
    def test_el_tiquete_sale_numerado_con_la_hora_de_la_venta(self, catalogo):
        caso, ventas, contador, _ = venta_con_numeracion(catalogo)
        hecha = caso(peticion([(1, 1)]))

        assert hecha.einvoice is not None
        assert hecha.einvoice.document_type == TICKET
        assert (hecha.einvoice.source_type, hecha.einvoice.source_id) == (SOURCE_SALE, hecha.id_sale)
        assert hecha.einvoice.issued_at == ventas.ventas[0].created_at == MOMENTO
        assert contador.comprobantes == [hecha.einvoice]

    def test_la_factura_en_su_serie(self, catalogo):
        caso, _, contador, _ = venta_con_numeracion(catalogo)
        caso(peticion([(1, 1)]))
        factura = caso(peticion([(1, 1)], client_id=CLIENTE, sale_number="2"))

        assert factura.einvoice.consecutive[8:10] == INVOICE
        assert factura.einvoice.sequence == 1

    def test_sin_facturacion_no_se_numera(self, catalogo):
        caso, _, contador, _ = venta_con_numeracion(catalogo, activa=False)
        hecha = caso(peticion([(1, 1)]))

        assert hecha.einvoice is None
        assert contador.bloqueadas == []

    def test_la_venta_que_falla_por_stock_no_consume_numero(self, catalogo):
        # El defecto 1 del lado del contador: el número se toma después de que
        # todo lo que podía decir que no, dijo que sí.
        caso, _, contador, _ = venta_con_numeracion(catalogo)
        with pytest.raises(InsufficientStock):
            caso(peticion([(4, 3)]))

        assert contador.bloqueadas == []
        assert contador.series == {}

    def test_sin_cedula_no_se_abre_la_transaccion(self, catalogo):
        caso, ventas, _, uow = venta_con_numeracion(catalogo, FakeIssuerRepository(None))
        with pytest.raises(IssuerIdentificationRequired):
            caso(peticion([(1, 1)]))

        assert ventas.ventas == []
        assert uow.entradas == 0


def mundo_con_numeracion(**opciones):
    mundo = Mundo(**opciones)
    numeracion, contador = numerador()
    return mundo, numeracion, contador


class TestLaDevolucion:
    def _devolucion(self, mundo, numeracion) -> RegisterReturn:
        return RegisterReturn(
            sales=mundo.ventas,
            returns=mundo.devoluciones,
            notes=mundo.notas,
            products=mundo.productos,
            settings=mundo.ajustes,
            uow=mundo.uow,
            clock=mundo.reloj,
            numbering=numeracion,
        )

    def _pedir(self, mundo, **cambios):
        base = dict(
            sale_id=mundo.id_venta,
            user_id=1,
            reason="venía dañado",
            lines=[RequestedReturnLine(1, 1)],
        )
        return ReturnRequest(**{**base, **cambios})

    def test_la_nota_de_credito_va_en_la_serie_03(self):
        mundo, numeracion, contador = mundo_con_numeracion()
        hecha = self._devolucion(mundo, numeracion)(self._pedir(mundo))

        assert hecha.einvoice.document_type == CREDIT_NOTE
        assert (hecha.einvoice.source_type, hecha.einvoice.source_id) == (SOURCE_RETURN, hecha.id_return)
        assert hecha.einvoice.issued_at == AHORA

    def test_sin_comprobante_original_no_hay_nota_ni_numero(self):
        mundo, numeracion, contador = mundo_con_numeracion(tipo=None)
        hecha = self._devolucion(mundo, numeracion)(self._pedir(mundo))

        assert hecha.einvoice is None
        assert contador.bloqueadas == []


class TestLaNotaPorMonto:
    def _nota(self, mundo, numeracion) -> RegisterAmountNote:
        return RegisterAmountNote(
            sales=mundo.ventas,
            returns=mundo.devoluciones,
            notes=mundo.notas,
            settings=mundo.ajustes,
            uow=mundo.uow,
            clock=mundo.reloj,
            numbering=numeracion,
        )

    def test_la_nd_en_la_02_y_la_nc_en_la_03(self):
        mundo, numeracion, contador = mundo_con_numeracion()
        debito = self._nota(mundo, numeracion)(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))
        credito = self._nota(mundo, numeracion)(pedir(mundo, CREDIT_NOTE, [(1, 500)]))

        assert debito.einvoice.consecutive[8:10] == DEBIT_NOTE
        assert credito.einvoice.consecutive[8:10] == CREDIT_NOTE
        assert (credito.einvoice.source_type, credito.einvoice.source_id) == (SOURCE_NOTE, credito.id_note)

    def test_la_nc_por_monto_y_la_de_devolucion_comparten_serie(self):
        # Las dos son notas de crédito: la serie es por tipo, no por flujo.
        mundo, numeracion, _ = mundo_con_numeracion()
        nota = self._nota(mundo, numeracion)(pedir(mundo, CREDIT_NOTE, [(1, 500)]))
        devolucion = TestLaDevolucion()._devolucion(mundo, numeracion)(
            TestLaDevolucion()._pedir(mundo, lines=[RequestedReturnLine(2, 1)])
        )

        assert (nota.einvoice.sequence, devolucion.einvoice.sequence) == (1, 2)

    def test_sin_cedula_la_nota_no_se_emite(self):
        mundo = Mundo()
        numeracion, _ = numerador(FakeIssuerRepository(None))
        with pytest.raises(IssuerIdentificationRequired):
            self._nota(mundo, numeracion)(pedir(mundo, DEBIT_NOTE, [(1, 1130)]))
        assert mundo.notas.notas == []


def test_sin_numeracion_conectada_la_venta_queda_pendiente(catalogo):
    # Es lo que pasaba antes de T-705 y lo que siguen haciendo las pruebas que
    # no son de esto: la venta con tipo y sin clave se imprime «pendiente».
    caso = RegisterSale(
        products=catalogo,
        sales=FakeSaleRepository(),
        clients=FakeClientRepository({CLIENTE}),
        settings=FakeSettingsRepository(IVA, einvoicing=True),
        uow=FakeUnitOfWork(),
        clock=FixedClock(MOMENTO),
    )
    hecha = caso(peticion([(1, 1)]))
    assert hecha.document_type == TICKET and hecha.einvoice is None


def test_la_venta_no_confunde_montos(catalogo):
    # Que numerar no toque la plata: los totales son los mismos con y sin clave.
    caso, _, _, _ = venta_con_numeracion(catalogo)
    assert caso(peticion([(2, 1)])).totals.total == Money("4802.50")
