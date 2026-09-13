"""El enganche del libro (T-1105, RN-59).

Lo que se prueba acá no es la contabilidad —eso está en `tests/domain/`— sino el
cableado: que cada caso de uso le cuente al libro lo que pasó, con las cifras
correctas, **dentro de la transacción**, y que con el libro apagado no cambie
absolutamente nada.

El libro espía no calcula: anota lo que le cuentan. Si esta batería y las del
dominio dicen lo mismo, el asiento que se escribe en producción es el que las
pruebas del dominio verifican con las cifras de los invariantes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pytest

from app.application.ports.ledger import AccountingNotActive, NullLedger
from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    CloseCashSession,
)
from app.application.use_cases.register_return import (
    RegisterReturn,
    RequestedReturnLine,
    ReturnRequest,
)
from app.application.use_cases.register_sale import (
    RegisterSale,
    RequestedLine,
    SaleRequest,
)
from app.application.use_cases.stock_entry import (
    EntryRequest,
    RegisterStockEntry,
    RequestedEntryLine,
)
from app.application.use_cases.supplier_payment import PaymentRequest, PaySupplier
from app.domain.errors import DomainError
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock

from .fakes import (
    FakeCashRepository,
    FakeProduct,
    FakeProductRepository,
    FakeReturnRepository,
    FakeSaleRepository,
    FakeSettingsRepository,
    FakeStockEntryRepository,
    FakeSupplierPaymentRepository,
    FakeUnitOfWork,
)

AHORA = datetime(2026, 9, 12, 10, 30, 0)
HOY = date(2026, 9, 12)
CAJERO = 7
TRECE = TaxRate.percent(13)


@dataclass
class LibroEspia:
    """Anota lo que le cuentan, y cuándo.

    `confirmados` guarda cuántos hechos tenía anotados el libro en el momento del
    `commit`. Es lo que permite comprobar que el asiento se escribe **antes** de
    confirmar y no después: RN-59 no es «que exista el asiento», es que exista o
    no exista la venta.
    """

    hechos: list[tuple] = field(default_factory=list)

    def record_sale(self, sale, lines) -> None:
        self.hechos.append(("sale", sale, list(lines)))

    def record_return(self, ret, lines) -> None:
        self.hechos.append(("return", ret, list(lines)))

    def record_cash_close(self, session, *, expected, counted) -> None:
        self.hechos.append(("cash_close", session, expected, counted))

    def record_cash_movement(self, mov) -> None:
        self.hechos.append(("cash_movement", mov))

    def record_purchase(self, entry, lines) -> None:
        self.hechos.append(("purchase", entry, list(lines)))

    def record_supplier_payment(self, pay) -> None:
        self.hechos.append(("supplier_payment", pay))

    def de(self, tipo: str) -> list[tuple]:
        return [h for h in self.hechos if h[0] == tipo]


class UowQueMira(FakeUnitOfWork):
    """Una unidad de trabajo que anota qué había en el libro al confirmar."""

    def __init__(self, libro: LibroEspia) -> None:
        super().__init__()
        self._libro = libro
        self.anotados_al_confirmar: list[int] = []

    def commit(self) -> None:
        self.anotados_al_confirmar.append(len(self._libro.hechos))
        super().commit()


@pytest.fixture
def libro():
    return LibroEspia()


@pytest.fixture
def reloj():
    return FixedClock(AHORA)


# --------------------------------------------------------------------- ventas


def piezas_de_venta(libro, reloj, *, costo=Money(900)):
    productos = FakeProductRepository(
        [FakeProduct(1, "Arroz", Money(1450), stock=20, tax_rate=TRECE, cost=costo)]
    )
    ventas = FakeSaleRepository()
    uow = UowQueMira(libro)
    caso = RegisterSale(
        products=productos,
        sales=ventas,
        settings=FakeSettingsRepository(TRECE),
        uow=uow,
        clock=reloj,
        ledger=libro,
    )
    return caso, productos, ventas, uow


def peticion_de_venta(cantidad=3, metodo="Efectivo"):
    return SaleRequest(
        sale_number="F-1",
        client_id=None,
        user_id=CAJERO,
        subtotal=Money(1450 * cantidad),
        tax=Money(1450 * cantidad) * TRECE.value,
        total=Money(1450 * cantidad) + Money(1450 * cantidad) * TRECE.value,
        payment_method=metodo,
        cash_received=Money(10000),
        change_given=Money(0),
        lines=[RequestedLine(1, cantidad)],
    )


class TestLaVenta:
    def test_le_cuenta_al_libro_lo_que_se_vendio(self, libro, reloj):
        caso, _, _, _ = piezas_de_venta(libro, reloj)
        caso(peticion_de_venta())

        (_, venta, lineas) = libro.de("sale")[0]
        assert venta.payment_method == "Efectivo"
        assert venta.date == HOY
        assert (lineas[0].subtotal, lineas[0].tax) == (Money(4350), Money("565.50"))
        assert lineas[0].tax_rate == TRECE

    def test_con_el_id_de_la_venta_que_se_acaba_de_guardar(self, libro, reloj):
        caso, _, ventas, _ = piezas_de_venta(libro, reloj)
        resultado = caso(peticion_de_venta())

        assert libro.de("sale")[0][1].id == resultado.id_sale
        assert ventas.ventas[0].id_sale == resultado.id_sale

    def test_va_el_costo_congelado_y_no_el_del_catalogo(self, libro, reloj):
        # RN-63. Es lo que hace que comprar más caro mañana no reescriba la
        # utilidad de lo que ya se vendió.
        caso, productos, _, _ = piezas_de_venta(libro, reloj)
        caso(peticion_de_venta())
        productos.productos[1].cost = Money(1200)

        assert libro.de("sale")[0][2][0].unit_cost == Money(900)

    def test_un_producto_sin_costo_va_en_nulo_y_no_en_cero(self, libro, reloj):
        # Cero diría «fue gratis» y le inflaría el margen al negocio.
        caso, _, _, _ = piezas_de_venta(libro, reloj, costo=Money.zero())
        caso(peticion_de_venta())

        assert libro.de("sale")[0][2][0].unit_cost is None

    def test_el_asiento_va_antes_del_commit(self, libro, reloj):
        # RN-59: si el asiento no se puede escribir, la venta no se confirma.
        caso, _, _, uow = piezas_de_venta(libro, reloj)
        caso(peticion_de_venta())

        assert uow.anotados_al_confirmar == [1]

    def test_con_el_libro_apagado_la_venta_es_la_misma(self, reloj):
        # La prueba de que el enganche no toca el dinero.
        productos = FakeProductRepository(
            [FakeProduct(1, "Arroz", Money(1450), stock=20, tax_rate=TRECE)]
        )
        caso = RegisterSale(
            products=productos,
            sales=FakeSaleRepository(),
            settings=FakeSettingsRepository(TRECE),
            uow=FakeUnitOfWork(),
            clock=reloj,
            ledger=NullLedger(),
        )
        resultado = caso(peticion_de_venta())

        assert resultado.totals.total == Money("4915.50")
        assert productos.productos[1].stock == 17

    def test_sin_libro_declarado_tambien(self, reloj):
        # El argumento es opcional: las pruebas de lo que ya existía no tienen
        # que aprender un puerto nuevo, y el caso de uso no cambia de forma.
        productos = FakeProductRepository(
            [FakeProduct(1, "Arroz", Money(1450), stock=20, tax_rate=TRECE)]
        )
        caso = RegisterSale(
            products=productos,
            sales=FakeSaleRepository(),
            settings=FakeSettingsRepository(TRECE),
            uow=FakeUnitOfWork(),
            clock=reloj,
        )

        assert caso(peticion_de_venta()).totals.total == Money("4915.50")


# --------------------------------------------------------------- devoluciones


class TestLaDevolucion:
    def _piezas(self, libro, reloj):
        productos = FakeProductRepository(
            [FakeProduct(1, "Arroz", Money(1450), stock=17, tax_rate=TRECE, cost=Money(900))]
        )
        ventas = FakeSaleRepository()
        ventas.add(
            sale_number="F-1",
            client_id=None,
            user_id=CAJERO,
            subtotal=Money(4350),
            tax=Money("565.50"),
            total=Money("4915.50"),
            payment_method="Efectivo",
            cash_received=Money(5000),
            change_given=Money("84.50"),
            created_at=AHORA,
            lines=[
                _LineaVendida(
                    product_id=1,
                    unit_price=Money(1450),
                    quantity=3,
                    tax_rate=TRECE,
                    unit_cost=Money(900),
                )
            ],
        )
        caso = RegisterReturn(
            sales=ventas,
            returns=FakeReturnRepository(),
            products=productos,
            settings=FakeSettingsRepository(TRECE),
            uow=UowQueMira(libro),
            clock=reloj,
            ledger=libro,
        )
        return caso

    def test_le_cuenta_al_libro_lo_que_se_devolvio(self, libro, reloj):
        caso = self._piezas(libro, reloj)
        caso(ReturnRequest(1, CAJERO, "no servía", [RequestedReturnLine(1, 1)]))

        (_, devolucion, lineas) = libro.de("return")[0]
        assert devolucion.date == HOY
        assert lineas[0].subtotal == Money(1450)
        assert lineas[0].tax == Money("188.50")

    def test_repone_el_inventario_por_lo_que_costo_y_no_por_lo_de_hoy(self, libro, reloj):
        # RN-63 del otro lado: con el costo de hoy, devolver algo que después se
        # compró más caro inventaría utilidad de la nada.
        caso = self._piezas(libro, reloj)
        caso(ReturnRequest(1, CAJERO, "no servía", [RequestedReturnLine(1, 1)]))

        assert libro.de("return")[0][2][0].unit_cost == Money(900)


@dataclass
class _LineaVendida:
    """Una línea guardada, como la devuelve el repositorio de ventas."""

    product_id: int
    unit_price: Money
    quantity: int
    tax_rate: TaxRate | None = None
    unit_cost: Money | None = None


# ----------------------------------------------------------------------- caja


class TestLaCaja:
    def _piezas(self, libro, reloj):
        ventas, devoluciones, caja = (
            FakeSaleRepository(),
            FakeReturnRepository(),
            FakeCashRepository(),
        )
        reporte = BuildSessionReport(
            sales=ventas, returns=devoluciones, cash=caja, clock=reloj
        )
        caja.create_session(
            user_id=CAJERO, opening=Money(50000), opened_at=AHORA, notes=None
        )
        return caja, reporte

    def test_una_entrada_de_gaveta_se_le_cuenta(self, libro, reloj):
        caja, reporte = self._piezas(libro, reloj)
        caso = AddCashMovement(
            cash=caja, report=reporte, uow=FakeUnitOfWork(), clock=reloj, ledger=libro
        )
        caso(user_id=CAJERO, type_="entrada", amount=Money(5000), reason="vuelto")

        (_, movimiento) = libro.de("cash_movement")[0]
        assert (movimiento.type, movimiento.amount) == ("entrada", Money(5000))
        assert not movimiento.from_supplier_payment

    def test_el_cierre_le_cuenta_lo_esperado_y_lo_contado(self, libro, reloj):
        caja, reporte = self._piezas(libro, reloj)
        caso = CloseCashSession(
            cash=caja, uow=FakeUnitOfWork(), clock=reloj, report=reporte, ledger=libro
        )
        caso(user_id=CAJERO, counted=Money(49000), notes=None)

        (_, turno, esperado, contado) = libro.de("cash_close")[0]
        assert (esperado, contado) == (Money(50000), Money(49000))
        assert turno.date == HOY

    def test_sin_arqueo_no_hay_asiento_de_cierre(self, libro, reloj):
        # Los dos son opcionales juntos: el asiento del cierre **es** la
        # diferencia, y sin el arqueo no hay diferencia que asentar.
        caja, _ = self._piezas(libro, reloj)
        caso = CloseCashSession(cash=caja, uow=FakeUnitOfWork(), clock=reloj, ledger=libro)
        caso(user_id=CAJERO, counted=Money(49000), notes=None)

        assert libro.de("cash_close") == []


# -------------------------------------------------------------------- compras


class TestLaCompra:
    def _piezas(self, libro, reloj, *, con_pagador=True):
        productos = FakeProductRepository(
            [FakeProduct(1, "Arroz", Money(1450), stock=0)]
        )
        entradas = FakeStockEntryRepository()
        abonos = FakeSupplierPaymentRepository()
        caja = FakeCashRepository()
        caja.create_session(
            user_id=CAJERO, opening=Money(500000), opened_at=AHORA, notes=None
        )
        movimientos = AddCashMovement(
            cash=caja,
            report=BuildSessionReport(
                sales=FakeSaleRepository(),
                returns=FakeReturnRepository(),
                cash=caja,
                clock=reloj,
            ),
            uow=FakeUnitOfWork(),
            clock=reloj,
            ledger=libro,
        )
        pagador = PaySupplier(
            entries=entradas,
            payments=abonos,
            movements=movimientos,
            uow=FakeUnitOfWork(),
            clock=reloj,
            ledger=libro,
        )
        caso = RegisterStockEntry(
            products=productos,
            entries=entradas,
            uow=FakeUnitOfWork(),
            clock=reloj,
            suppliers=_ProveedoresFalsos(),
            payer=pagador if con_pagador else None,
            ledger=libro,
        )
        return caso, pagador, entradas

    def _peticion(self, **cambios):
        datos = dict(
            document_number="FE-900",
            supplier=None,
            source="manual",
            user_id=CAJERO,
            notes=None,
            lines=[
                RequestedEntryLine(
                    product_id=1,
                    quantity=100,
                    unit_cost=Money(1000),
                    tax_rate=TRECE,
                    tax_amount=Money(13000),
                )
            ],
            supplier_id=5,
            document_date=date(2026, 9, 10),
        )
        datos.update(cambios)
        return EntryRequest(**datos)

    def test_una_compra_se_le_cuenta_al_libro(self, libro, reloj):
        caso, _, _ = self._piezas(libro, reloj)
        caso(self._peticion())

        (_, compra, lineas) = libro.de("purchase")[0]
        assert lineas[0].subtotal == Money(100000)
        assert lineas[0].tax == Money(13000)
        assert lineas[0].tax_rate == TRECE

    def test_con_la_fecha_del_documento_del_proveedor(self, libro, reloj):
        # La misma que usa el reporte de compras por tarifa. Con fechas distintas
        # el D-104 no cuadraría con el libro justo en las facturas de fin de mes.
        caso, _, _ = self._piezas(libro, reloj)
        caso(self._peticion())

        assert libro.de("purchase")[0][1].date == date(2026, 9, 10)

    def test_sin_fecha_de_documento_usa_la_de_hoy(self, libro, reloj):
        caso, _, _ = self._piezas(libro, reloj)
        caso(self._peticion(document_date=None, document_number="FE-901"))

        assert libro.de("purchase")[0][1].date == HOY

    def test_una_entrada_sin_proveedor_no_deja_asiento(self, libro, reloj):
        # No genera cuenta por pagar ni crédito fiscal (RN-52): es un ajuste de
        # inventario, y de esos el sistema no sabe la contrapartida.
        caso, _, _ = self._piezas(libro, reloj)
        caso(self._peticion(supplier_id=None, document_number="AJ-1"))

        assert libro.de("purchase") == []

    def test_el_abono_se_le_cuenta_y_su_salida_de_caja_no(self, libro, reloj):
        # RN-56: las dos juntas sacarían de la gaveta el doble de lo que salió.
        caso, pagador, entradas = self._piezas(libro, reloj)
        caso(self._peticion())
        pagador(
            PaymentRequest(
                entry_id=entradas.entradas[0].id,
                amount=Money(50000),
                method="cash",
                user_id=CAJERO,
                reason="abono",
            )
        )

        (_, abono) = libro.de("supplier_payment")[0]
        assert (abono.amount, abono.method) == (Money(50000), "cash")
        assert libro.de("cash_movement")[0][1].from_supplier_payment


class _ProveedoresFalsos:
    def get(self, supplier_id: int):
        return _Proveedor(id=supplier_id, name="Mayorista", payment_terms_days=30)

    def find_by_identification(self, identification: str):  # pragma: no cover
        return None

    def create(self, **datos) -> int:  # pragma: no cover
        return 1


@dataclass
class _Proveedor:
    id: int
    name: str
    payment_terms_days: int
    is_active: bool = True


# ----------------------------------------------------------------- el nulo


class TestElLibroNulo:
    """No hace nada, y que no haga nada es lo que se comprueba.

    Es la implementación de producción de «este negocio no lleva libros acá»,
    que es el caso de casi todas las compañías.
    """

    def test_el_libro_sin_activar_es_un_no_del_negocio(self):
        # Lo levanta el adaptador cuando falta la cuenta «por clasificar», que es
        # la que sostiene RN-59. Que herede de `DomainError` es lo que permite
        # que el mismo `except` de los adaptadores lo convierta en código.
        assert issubclass(AccountingNotActive, DomainError)
        with pytest.raises(DomainError):
            raise AccountingNotActive()

    def test_los_seis_metodos_no_hacen_nada(self):
        nulo = NullLedger()

        assert nulo.record_sale(None, []) is None
        assert nulo.record_return(None, []) is None
        assert nulo.record_cash_close(None, expected=Money.zero(), counted=Money.zero()) is None
        assert nulo.record_cash_movement(None) is None
        assert nulo.record_purchase(None, []) is None
        assert nulo.record_supplier_payment(None) is None
