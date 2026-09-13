"""Abonar a una compra (T-1010, RN-55 y RN-56).

Lo que se prueba acá no es la resta —esa está en `tests/domain/test_purchases.py`
y no necesita ni un doble— sino **el orden y la atomicidad**: que un pago en
efectivo salga de la caja abierta, que salga antes de guardarse el abono, y que
un abono que no se puede hacer no deje nada escrito.

Con dobles y sin base, que es lo que permite pararse en un turno con un monto
concreto sin levantar MySQL.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    NoOpenSession,
)
from app.application.use_cases.supplier_payment import (
    PaymentRequest,
    PaySupplier,
    PurchaseCancelled,
    PurchaseNotFound,
)
from app.domain.errors import InsufficientCash, InvalidMovement, InvalidPayment, PaymentExceedsBalance
from app.domain.money import Money
from app.infrastructure.clock import FixedClock
from tests.application.fakes import (
    FakeCashRepository,
    FakeReturnRepository,
    FakeSaleRepository,
    FakeStockEntryRepository,
    FakeSupplierPaymentRepository,
    FakeUnitOfWork,
)

HOY = datetime(2026, 9, 12, 10, 0, 0)
ADMIN = 3
#: El motivo lo arma el POS y viaja en la petición (RN-30). En las pruebas es
#: una cadena cualquiera: lo que importa es que llegue al movimiento de caja.
MOTIVO = "Pago a Mayorista del Sur, factura F-001"


@pytest.fixture
def mundo():
    entradas = FakeStockEntryRepository()
    abonos = FakeSupplierPaymentRepository()
    caja = FakeCashRepository()
    uow = FakeUnitOfWork()
    reloj = FixedClock(HOY)

    movimientos = AddCashMovement(
        cash=caja,
        report=BuildSessionReport(
            sales=FakeSaleRepository(),
            returns=FakeReturnRepository(),
            cash=caja,
            clock=reloj,
        ),
        uow=uow,
        clock=reloj,
    )
    caso = PaySupplier(
        entries=entradas,
        payments=abonos,
        movements=movimientos,
        uow=uow,
        clock=reloj,
    )
    return caso, entradas, abonos, caja, uow


def compra(entradas, *, total=1000, supplier_id=7, status="aplicada") -> int:
    id_entry = entradas.add(
        document_number="F-001",
        supplier="Mayorista del Sur",
        source="xml",
        user_id=ADMIN,
        notes=None,
        total_cost=Money(total),
        created_at=HOY,
        lines=[],
        supplier_id=supplier_id,
        payment_terms="credit",
    )
    entradas.get(id_entry).status = status
    return id_entry


def abonar(caso, id_entry, *, monto=400, metodo="transfer", motivo=MOTIVO):
    return caso(
        PaymentRequest(
            entry_id=id_entry,
            amount=Money(monto),
            method=metodo,
            user_id=ADMIN,
            reference="TRF-99",
            reason=motivo,
        )
    )


def abrir_caja(caja, *, fondo=5000, user_id=ADMIN):
    return caja.create_session(
        user_id=user_id, opening=Money(fondo), opened_at=HOY, notes=None
    )


class TestElSaldo:
    def test_un_abono_baja_el_saldo_de_esa_compra(self, mundo):
        caso, entradas, abonos, _, _ = mundo
        id_entry = compra(entradas, total=1000)

        assert abonar(caso, id_entry, monto=400).balance == Money(600)
        assert abonar(caso, id_entry, monto=600).balance.is_zero
        assert len(abonos.abonos) == 2

    def test_abonar_de_mas_no_escribe_nada(self, mundo):
        caso, entradas, abonos, _, uow = mundo
        id_entry = compra(entradas, total=1000)

        with pytest.raises(PaymentExceedsBalance):
            abonar(caso, id_entry, monto=1001)
        assert abonos.abonos == []
        assert uow.rolled_back

    def test_el_saldo_cuenta_los_abonos_anteriores(self, mundo):
        # La trampa: sin leer lo ya abonado, dos abonos de 600 sobre 1 000
        # pasarían los dos y la compra quedaría pagada de más.
        caso, entradas, _, _, _ = mundo
        id_entry = compra(entradas, total=1000)
        abonar(caso, id_entry, monto=600)

        with pytest.raises(PaymentExceedsBalance):
            abonar(caso, id_entry, monto=600)

    def test_cada_compra_tiene_el_suyo(self, mundo):
        # RN-55: el abono es a UNA compra. El saldo del proveedor es la suma de
        # los de sus compras, no un número aparte que haya que mantener cuadrado.
        caso, entradas, _, _, _ = mundo
        primera = compra(entradas, total=1000)
        segunda = compra(entradas, total=500)
        abonar(caso, primera, monto=1000)

        assert abonar(caso, segunda, monto=500).balance.is_zero


class TestElEfectivoSaleDeLaCaja:
    """RN-56, que es la mitad de esta tarea."""

    def test_baja_el_esperado_del_turno_en_lo_que_se_pagó(self, mundo):
        caso, entradas, _, caja, _ = mundo
        turno = abrir_caja(caja, fondo=5000)
        id_entry = compra(entradas, total=1000)

        resultado = abonar(caso, id_entry, monto=400, metodo="cash")

        movimiento = caja.movements(turno.id)[0]
        assert (movimiento.type, movimiento.amount) == ("salida", Money(400))
        assert movimiento.reason == MOTIVO
        assert resultado.cash_movement_id == movimiento.id

    def test_sin_turno_abierto_no_hay_pago_en_efectivo(self, mundo):
        caso, entradas, abonos, _, uow = mundo
        id_entry = compra(entradas, total=1000)

        with pytest.raises(NoOpenSession):
            abonar(caso, id_entry, monto=400, metodo="cash")
        # Ni el abono: la compra sigue debiendo lo mismo.
        assert abonos.abonos == []
        assert uow.rolled_back

    def test_por_transferencia_no_hace_falta_caja(self, mundo):
        # El administrador que registra facturas en la oficina no tiene por qué
        # tener una gaveta abierta.
        caso, entradas, _, caja, _ = mundo
        id_entry = compra(entradas, total=1000)

        resultado = abonar(caso, id_entry, monto=400, metodo="transfer")

        assert resultado.cash_movement_id is None
        assert caja.movimientos == []

    def test_no_se_puede_sacar_mas_efectivo_del_que_hay(self, mundo):
        # La misma regla de cualquier salida de caja, porque es la misma plata:
        # sin ella el esperado del turno queda negativo y el arqueo deja de
        # significar nada.
        caso, entradas, abonos, caja, _ = mundo
        abrir_caja(caja, fondo=300)
        id_entry = compra(entradas, total=1000)

        with pytest.raises(InsufficientCash):
            abonar(caso, id_entry, monto=400, metodo="cash")
        assert abonos.abonos == []

    def test_el_efectivo_sale_del_turno_de_quien_paga(self, mundo):
        # No del de cualquiera que tenga una abierta: la gaveta que baja es la
        # que la persona tiene enfrente.
        caso, entradas, _, caja, _ = mundo
        abrir_caja(caja, user_id=99)
        id_entry = compra(entradas, total=1000)

        with pytest.raises(NoOpenSession):
            abonar(caso, id_entry, monto=400, metodo="cash")

    def test_sin_motivo_no_se_escribe_el_movimiento(self, mundo):
        # El motivo lo arma el POS (RN-30) y sin él la salida quedaría sin
        # explicación en el arqueo. Es la misma regla de cualquier movimiento.
        caso, entradas, abonos, caja, _ = mundo
        abrir_caja(caja)
        id_entry = compra(entradas, total=1000)

        with pytest.raises(InvalidMovement) as excepcion:
            abonar(caso, id_entry, monto=400, metodo="cash", motivo="  ")
        assert excepcion.value.code == "missing_reason"
        assert abonos.abonos == []


class TestLoQueNoSePuedeAbonar:
    def test_una_compra_que_no_existe(self, mundo):
        caso, _, _, _, _ = mundo
        with pytest.raises(PurchaseNotFound):
            abonar(caso, 999)

    def test_una_entrada_sin_proveedor_no_es_una_compra(self, mundo):
        # No genera cuenta por pagar (RN-52), así que desde cuentas por pagar no
        # existe. Es el mismo criterio del proveedor de otra compañía (RNF-1):
        # la respuesta se da desde donde se pregunta.
        caso, entradas, _, _, _ = mundo
        id_entry = compra(entradas, supplier_id=None)

        with pytest.raises(PurchaseNotFound):
            abonar(caso, id_entry)

    def test_una_compra_anulada(self, mundo):
        # Pasa de verdad: alguien la anula mientras otro tiene abierta la
        # pantalla de saldos. Por eso no alcanza con esconder el botón.
        caso, entradas, _, _, _ = mundo
        id_entry = compra(entradas, status="anulada")

        with pytest.raises(PurchaseCancelled):
            abonar(caso, id_entry)

    @pytest.mark.parametrize("malo", ["efectivo", "tarjeta"])
    def test_un_metodo_que_no_existe(self, mundo, malo):
        caso, entradas, _, _, _ = mundo
        id_entry = compra(entradas)

        with pytest.raises(InvalidPayment):
            abonar(caso, id_entry, metodo=malo)

    def test_un_abono_de_cero(self, mundo):
        caso, entradas, abonos, _, _ = mundo
        id_entry = compra(entradas)

        with pytest.raises(InvalidPayment):
            abonar(caso, id_entry, monto=0)
        assert abonos.abonos == []


class TestLoQueQuedaEscrito:
    def test_el_abono_guarda_con_qué_y_contra_qué(self, mundo):
        caso, entradas, abonos, caja, _ = mundo
        turno = abrir_caja(caja)
        id_entry = compra(entradas, total=1000)

        abonar(caso, id_entry, monto=400, metodo="cash")

        abono = abonos.abonos[0]
        assert abono.entry_id == id_entry
        assert abono.supplier_id == 7
        assert abono.method == "cash"
        assert abono.reference == "TRF-99"
        assert abono.user_id == ADMIN
        assert abono.paid_at == HOY
        # El enlace con la salida de caja: sin él, el asiento de F11 contaría dos
        # veces la misma plata.
        assert abono.cash_movement_id == caja.movements(turno.id)[0].id

    def test_el_proveedor_sale_de_la_compra_y_no_de_la_petición(self, mundo):
        # Quien paga dice cuánto y cómo; a quién lo dice la factura. Si viniera
        # en la petición, un abono podría quedar colgado del proveedor
        # equivocado y ninguno de los dos saldos sería el que se debe.
        caso, entradas, abonos, _, _ = mundo
        id_entry = entradas.add(
            document_number="F-002",
            supplier="Otro mayorista",
            source="manual",
            user_id=ADMIN,
            notes=None,
            total_cost=Money(500),
            created_at=HOY,
            lines=[],
            supplier_id=12,
        )

        abonar(caso, id_entry, monto=500)

        assert abonos.abonos[0].supplier_id == 12

    def test_se_confirma_una_sola_vez(self, mundo):
        # La salida de caja y el abono van en la misma transacción: una gaveta
        # que bajó por un abono que después falló es un descuadre que nadie va a
        # saber explicar.
        caso, entradas, _, caja, uow = mundo
        abrir_caja(caja)
        id_entry = compra(entradas)

        abonar(caso, id_entry, monto=400, metodo="cash")

        assert uow.committed
        assert uow.entradas == 1
