"""Registrar una compra (T-1009, RN-52 a RN-54).

Una compra **es** una entrada de mercadería con proveedor, documento y
condición de pago, así que todo esto corre sobre `RegisterStockEntry`. Lo que
se prueba acá es lo que la convierte en compra; lo que ya hacía como entrada
sigue en `test_stock_entry.py`, sin tocar.

Con dobles y sin base: es lo que exige RN-20 y lo que permite pararse en una
fecha concreta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pytest

from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    NoOpenSession,
)
from app.application.use_cases.stock_entry import (
    EntryRequest,
    RegisterStockEntry,
    RequestedEntryLine,
    SupplierInactive,
    SupplierNotFound,
)
from app.application.use_cases.supplier_payment import PaySupplier
from app.domain.errors import DuplicateDocument
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock
from tests.application.fakes import (
    FakeCashRepository,
    FakeProduct,
    FakeProductRepository,
    FakeReturnRepository,
    FakeSaleRepository,
    FakeStockEntryRepository,
    FakeSupplierPaymentRepository,
    FakeUnitOfWork,
)

HOY = datetime(2026, 9, 12, 10, 0, 0)
TRECE = TaxRate.percent(13)
UNO = TaxRate.percent(1)


@dataclass
class FakeSupplier:
    id: int
    name: str
    is_active: bool = True
    payment_terms_days: int = 0


class FakeSupplierRepository:
    def __init__(self, proveedores: list[FakeSupplier] | None = None) -> None:
        self.proveedores = {p.id: p for p in (proveedores or [])}

    def get(self, supplier_id: int) -> FakeSupplier | None:
        return self.proveedores.get(supplier_id)


@pytest.fixture
def mundo():
    productos = FakeProductRepository(
        [FakeProduct(1, "Arroz", Money(1500), stock=10, cost=Money(100))]
    )
    entradas = FakeStockEntryRepository()
    proveedores = FakeSupplierRepository(
        [FakeSupplier(7, "Mayorista del Sur", payment_terms_days=30)]
    )
    caso = RegisterStockEntry(
        products=productos,
        entries=entradas,
        uow=FakeUnitOfWork(),
        clock=FixedClock(HOY),
        suppliers=proveedores,
    )
    return caso, productos, entradas, proveedores


@pytest.fixture
def mundo_pagable():
    """El mismo mundo, pero sabiendo pagar (T-1010).

    Se arma aparte para que las pruebas de arriba sigan describiendo una compra
    **sin** `payer`: es lo que sigue siendo una entrada de mercadería, y es la
    prueba de que pagar es opcional y no un requisito nuevo de comprar.

    La transacción es una sola —la misma `uow` para la compra y para el abono—,
    que es lo que hace que la mercadería y el pago entren o no entren juntos.
    """
    productos = FakeProductRepository(
        [FakeProduct(1, "Arroz", Money(1500), stock=10, cost=Money(100))]
    )
    entradas = FakeStockEntryRepository()
    abonos = FakeSupplierPaymentRepository()
    caja = FakeCashRepository()
    uow = FakeUnitOfWork()
    reloj = FixedClock(HOY)

    caso = RegisterStockEntry(
        products=productos,
        entries=entradas,
        uow=uow,
        clock=reloj,
        suppliers=FakeSupplierRepository(
            [FakeSupplier(7, "Mayorista del Sur", payment_terms_days=30)]
        ),
        payer=PaySupplier(
            entries=entradas,
            payments=abonos,
            movements=AddCashMovement(
                cash=caja,
                report=BuildSessionReport(
                    sales=FakeSaleRepository(),
                    returns=FakeReturnRepository(),
                    cash=caja,
                    clock=reloj,
                ),
                uow=uow,
                clock=reloj,
            ),
            uow=uow,
            clock=reloj,
        ),
    )
    return caso, uow, abonos, caja


def compra(**cambios) -> EntryRequest:
    datos = {
        "document_number": "F-001",
        "supplier": None,
        "source": "xml",
        "user_id": 1,
        "notes": None,
        "supplier_id": 7,
        "document_date": date(2026, 9, 10),
        "payment_terms": "credit",
        "lines": [
            RequestedEntryLine(
                quantity=10, unit_cost=Money(120), product_id=1, tax_rate=TRECE,
                tax_amount=Money(156),
            )
        ],
    }
    datos.update(cambios)
    return EntryRequest(**datos)


class TestElCostoPromedio:
    def test_el_caso_del_plan(self, mundo):
        caso, productos, _, _ = mundo
        caso(compra())
        # 10 a 100 más 10 a 120 → 110, y las existencias suben a 20.
        assert productos.productos[1].cost == Money(110)
        assert productos.productos[1].stock == 20

    def test_el_primer_ingreso_fija_el_costo(self, mundo):
        caso, productos, _, _ = mundo
        productos.productos[1] = FakeProduct(1, "Arroz", Money(1500), stock=0, cost=Money.zero())
        caso(compra())
        assert productos.productos[1].cost == Money(120)

    def test_el_mismo_producto_dos_veces_promedia_en_cadena(self, mundo):
        """La trampa de esta regla.

        Si las dos líneas promediaran contra la existencia original, la segunda
        ignoraría lo que dejó la primera y el costo saldría mal. Acá:
        10 a 100 + 10 a 120 → 110 (20 unidades); después + 20 a 140 → 125.
        """
        caso, productos, _, _ = mundo
        caso(
            compra(
                lines=[
                    RequestedEntryLine(quantity=10, unit_cost=Money(120), product_id=1),
                    RequestedEntryLine(quantity=20, unit_cost=Money(140), product_id=1),
                ]
            )
        )
        assert productos.productos[1].cost == Money(125)
        assert productos.productos[1].stock == 40

    def test_una_entrada_sin_proveedor_tambien_actualiza_el_costo(self, mundo):
        # El costo es del inventario, no de la compra: mercadería que entra por
        # un ajuste cuesta lo que se declare igual que la que entra por factura.
        caso, productos, _, _ = mundo
        caso(compra(supplier_id=None, payment_terms="cash", source="manual"))
        assert productos.productos[1].cost == Money(110)


class TestElVencimiento:
    def test_se_cuenta_desde_la_fecha_del_documento(self, mundo):
        caso, _, entradas, _ = mundo
        resultado = caso(compra())
        # 10 de setiembre + 30 días, no 12 + 30: el proveedor cobra desde su
        # factura, no desde el día en que la digitamos.
        assert resultado.due_date == date(2026, 10, 10)
        assert entradas.entradas[0].payment_terms == "credit"

    def test_el_plazo_de_la_compra_manda_sobre_el_del_proveedor(self, mundo):
        caso, _, _, _ = mundo
        resultado = caso(compra(payment_terms_days=15))
        assert resultado.due_date == date(2026, 9, 25)

    def test_sin_plazo_propio_se_usa_el_habitual_del_proveedor(self, mundo):
        # Es lo que evita teclear «30» en cada factura del mismo mayorista.
        caso, _, _, _ = mundo
        assert caso(compra()).due_date == date(2026, 10, 10)

    def test_de_contado_no_vence(self, mundo):
        caso, _, entradas, _ = mundo
        resultado = caso(compra(payment_terms="cash"))
        assert resultado.due_date is None
        assert entradas.entradas[0].payment_terms == "cash"

    def test_credito_a_cero_dias_es_contado(self, mundo):
        # Una deuda que vence el mismo día no es una deuda.
        caso, _, entradas, _ = mundo
        resultado = caso(compra(payment_terms_days=0))
        assert resultado.due_date is None
        assert entradas.entradas[0].payment_terms == "cash"

    def test_sin_fecha_de_documento_se_cuenta_desde_hoy(self, mundo):
        caso, _, _, _ = mundo
        assert caso(compra(document_date=None)).due_date == date(2026, 10, 12)


class TestElCreditoFiscal:
    def test_el_impuesto_es_el_del_documento_y_no_el_del_producto(self, mundo):
        caso, _, entradas, _ = mundo
        resultado = caso(compra())
        assert resultado.subtotal == Money(1200)
        assert resultado.tax == Money(156)
        assert resultado.total_cost == Money(1356)
        assert entradas.entradas[0].tax == Money(156)

    def test_con_tarifas_mezcladas_suma_linea_por_linea(self, mundo):
        # Una factura de abarrotes: canasta básica al 1 % y el resto al 13 %. El
        # promedio no es ninguna de las dos.
        caso, _, _, _ = mundo
        resultado = caso(
            compra(
                lines=[
                    RequestedEntryLine(
                        quantity=1, unit_cost=Money(1000), product_id=1,
                        tax_rate=TRECE, tax_amount=Money(130),
                    ),
                    RequestedEntryLine(
                        quantity=1, unit_cost=Money(1000), product_id=1,
                        tax_rate=UNO, tax_amount=Money(10),
                    ),
                ]
            )
        )
        assert resultado.subtotal == Money(2000)
        assert resultado.tax == Money(140)

    def test_sin_impuesto_el_total_es_el_subtotal(self, mundo):
        # Es lo que sigue siendo una entrada manual: sin factura no hay crédito.
        caso, _, _, _ = mundo
        resultado = caso(
            compra(lines=[RequestedEntryLine(quantity=10, unit_cost=Money(120), product_id=1)])
        )
        assert resultado.tax.is_zero
        assert resultado.total_cost == resultado.subtotal == Money(1200)

    def test_el_documento_manda_aunque_no_cuadre_con_la_tarifa(self, mundo):
        # Si el emisor redondeó distinto, lo que se acredita es su número: el
        # crédito fiscal es lo que se pagó (RN-53). 13 % de 1 200 sería 156,00.
        caso, _, entradas, _ = mundo
        resultado = caso(
            compra(
                lines=[
                    RequestedEntryLine(
                        quantity=10, unit_cost=Money(120), product_id=1,
                        tax_rate=TRECE, tax_amount=Money("155.99"),
                    )
                ]
            )
        )
        assert resultado.tax == Money("155.99")


class TestElProveedor:
    def test_uno_que_no_existe(self, mundo):
        caso, _, _, _ = mundo
        with pytest.raises(SupplierNotFound):
            caso(compra(supplier_id=99))

    def test_uno_desactivado_no_recibe_compras(self, mundo):
        caso, _, _, proveedores = mundo
        proveedores.proveedores[7].is_active = False
        with pytest.raises(SupplierInactive) as excepcion:
            caso(compra())
        # El nombre viaja: quien lo lee tiene que saber a cuál se refiere.
        assert excepcion.value.name == "Mayorista del Sur"

    def test_el_nombre_se_copia_a_la_compra(self, mundo):
        # Para que la compra lo recuerde si después se desactiva al proveedor o
        # se le corrige la razón social.
        caso, _, entradas, _ = mundo
        caso(compra())
        assert entradas.entradas[0].supplier == "Mayorista del Sur"
        assert entradas.entradas[0].supplier_id == 7

    def test_el_nombre_explicito_gana(self, mundo):
        caso, _, entradas, _ = mundo
        caso(compra(supplier="Como vino en el XML"))
        assert entradas.entradas[0].supplier == "Como vino en el XML"


class TestLaFacturaRepetida:
    def test_la_misma_del_mismo_proveedor_no_entra(self, mundo):
        caso, _, _, _ = mundo
        caso(compra())
        with pytest.raises(DuplicateDocument):
            caso(compra())

    def test_el_mismo_numero_de_otro_proveedor_si(self, mundo):
        """Lo que F10 cambió, y lo que rechazaría una compra legítima si no.

        Dos mayoristas numeran sus facturas cada uno desde el uno: la 1234 de
        uno no tiene nada que ver con la 1234 del otro.
        """
        caso, _, _, proveedores = mundo
        proveedores.proveedores[8] = FakeSupplier(8, "Otro mayorista")
        caso(compra())
        caso(compra(supplier_id=8))  # no lanza

    def test_una_entrada_sin_proveedor_compara_contra_las_que_tampoco_tienen(self, mundo):
        caso, _, _, _ = mundo
        caso(compra(supplier_id=None, payment_terms="cash"))
        with pytest.raises(DuplicateDocument):
            caso(compra(supplier_id=None, payment_terms="cash"))


class TestElAbonoDeUnaCompraDeContado:
    """Lo que T-1009 dejó a propósito para T-1010.

    De contado quiere decir que ya se pagó, así que el abono entra en el mismo
    acto. La regla del efectivo no se repite acá: vive en `PaySupplier`, y estas
    pruebas comprueban que sube tal cual —sin turno abierto **la compra entera**
    no entra, porque la mercadería y el pago son el mismo hecho—.
    """

    def test_de_contado_con_metodo_queda_pagada(self, mundo_pagable):
        caso, _uow, abonos, _ = mundo_pagable
        resultado = caso(compra(payment_terms="cash", payment_method="transfer"))

        assert resultado.id_payment is not None
        # Por el total con impuesto, que es lo que se le entregó al proveedor.
        assert abonos.abonos[0].amount == Money(1356)
        assert abonos.abonos[0].method == "transfer"

    def test_sin_metodo_queda_con_saldo(self, mundo_pagable):
        # No se inventa de dónde salió la plata: si adivinara «efectivo»,
        # descuadraría un arqueo (RN-56). Se abona desde cuentas por pagar.
        caso, _, abonos, _ = mundo_pagable
        resultado = caso(compra(payment_terms="cash"))

        assert resultado.id_payment is None
        assert abonos.abonos == []

    def test_a_credito_no_se_paga_sola(self, mundo_pagable):
        caso, _, abonos, _ = mundo_pagable
        resultado = caso(compra(payment_method="transfer"))

        assert resultado.due_date == date(2026, 10, 10)
        assert resultado.id_payment is None
        assert abonos.abonos == []

    def test_una_entrada_sin_proveedor_no_paga_nada(self, mundo_pagable):
        # No genera cuenta por pagar (RN-52), así que tampoco tiene qué abonar.
        caso, _, abonos, _ = mundo_pagable
        resultado = caso(
            compra(supplier_id=None, payment_terms="cash", payment_method="transfer")
        )

        assert resultado.id_payment is None
        assert abonos.abonos == []

    def test_en_efectivo_sale_de_la_caja(self, mundo_pagable):
        caso, _, _, caja = mundo_pagable
        turno = caja.create_session(
            user_id=1, opening=Money(5000), opened_at=HOY, notes=None
        )
        caso(
            compra(
                payment_terms="cash", payment_method="cash", payment_reason="Factura F-001"
            )
        )

        movimiento = caja.movements(turno.id)[0]
        assert (movimiento.type, movimiento.amount) == ("salida", Money(1356))

    def test_en_efectivo_sin_caja_abierta_no_entra_ni_la_mercaderia(self, mundo_pagable):
        """La consecuencia que hay que mirar de frente.

        Podría parecer más amable registrar la compra y dejar el pago pendiente,
        pero eso convierte una compra de contado en una deuda que no existe. Y
        el «no» es accionable: se abre la caja, o se marca el pago como
        transferencia.
        """
        caso, uow, abonos, _ = mundo_pagable

        with pytest.raises(NoOpenSession):
            caso(
                compra(
                    payment_terms="cash",
                    payment_method="cash",
                    payment_reason="Factura F-001",
                )
            )

        assert abonos.abonos == []
        # Lo que se comprueba es que la transacción se revirtió, no que el stock
        # volvió: el repositorio de mentira escribe en un diccionario y no sabe
        # deshacer. Quien deshace de verdad es `SqlAlchemyUnitOfWork`, y eso se
        # mira contra MySQL en `tests/test_compras.py`.
        assert uow.rolled_back and not uow.committed


class TestSinProveedoresConfigurados:
    def test_una_entrada_de_siempre_no_necesita_el_puerto(self):
        """El caso de uso sigue sirviendo sin `suppliers`.

        Es lo que permite que las pruebas de lo que ya existía —y cualquier
        camino que no sea una compra— no tengan que aprender un puerto nuevo.
        """
        productos = FakeProductRepository([FakeProduct(1, "Arroz", Money(1500), stock=0)])
        caso = RegisterStockEntry(
            products=productos,
            entries=FakeStockEntryRepository(),
            uow=FakeUnitOfWork(),
            clock=FixedClock(HOY),
        )
        resultado = caso(
            compra(supplier_id=None, payment_terms="cash", source="manual")
        )
        assert resultado.units_added == 10
