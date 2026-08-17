"""
El turno de caja, sin base de datos y sin esperar en tiempo real.

Con `FixedClock` se pueden probar cosas que antes eran imposibles de verificar:
que una venta de las 23:58 entre en el turno que abrió a las 22:00, y que una de
las 21:59 no. Con `datetime.now()` repartido por los servicios, eso exigía o
esperar dos horas o no probarlo.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    CloseCashSession,
    NoOpenSession,
    OpenCashSession,
    SessionAlreadyOpen,
)
from app.domain.errors import InsufficientCash, InvalidMovement
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import FakeCashRepository, FakeReturnRepository, FakeSaleRepository

APERTURA = datetime(2026, 8, 16, 22, 0, 0)
CAJERO = 7


@pytest.fixture
def reloj():
    return FixedClock(APERTURA)


@pytest.fixture
def piezas(reloj):
    return FakeSaleRepository(), FakeReturnRepository(), FakeCashRepository(), reloj


@pytest.fixture
def reporte(piezas):
    ventas, devoluciones, caja, reloj = piezas
    return BuildSessionReport(sales=ventas, returns=devoluciones, cash=caja, clock=reloj)


def vender(ventas, cuando, total, metodo="Efectivo", user_id=CAJERO):
    ventas.add(
        sale_number=str(cuando),
        client_id=None,
        user_id=user_id,
        subtotal=Money(total),
        tax=Money(0),
        total=Money(total),
        payment_method=metodo,
        cash_received=Money(total),
        change_given=Money(0),
        created_at=cuando,
        lines=[],
    )


class TestAbrir:
    def test_abre_con_su_fondo(self, piezas):
        _, _, caja, reloj = piezas
        caso = OpenCashSession(cash=caja, uow=_Uow(), clock=reloj)
        turno = caso(user_id=CAJERO, opening=Money(50000), notes="turno de la mañana")

        assert turno.opening_amount == Money(50000)
        assert turno.opened_at == APERTURA
        assert turno.status == "abierta"

    def test_no_se_abren_dos(self, piezas):
        _, _, caja, reloj = piezas
        caso = OpenCashSession(cash=caja, uow=_Uow(), clock=reloj)
        caso(user_id=CAJERO, opening=Money(50000), notes=None)

        with pytest.raises(SessionAlreadyOpen):
            caso(user_id=CAJERO, opening=Money(1000), notes=None)

    def test_el_fondo_puede_ser_cero_pero_no_negativo(self, piezas):
        _, _, caja, reloj = piezas
        caso = OpenCashSession(cash=caja, uow=_Uow(), clock=reloj)
        caso(user_id=1, opening=Money.zero(), notes=None)

        with pytest.raises(InvalidMovement):
            caso(user_id=2, opening=Money(-1), notes=None)


class TestArqueo:
    def test_el_invariante_de_progress_json(self, piezas, reporte):
        ventas, devoluciones, caja, reloj = piezas
        turno = caja.create_session(
            user_id=CAJERO, opening=Money(50000), opened_at=APERTURA, notes=None
        )

        reloj.advance(minutes=30)
        vender(ventas, reloj.now(), "4915.50")
        devoluciones.add(
            sale_id=1,
            user_id=CAJERO,
            reason="prueba",
            total=Money("1638.50"),
            created_at=reloj.now(),
            lines=[],
        )

        reloj.advance(minutes=10)
        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money(50000),
            opened_at=APERTURA,
            closed_at=None,
            counted=None,
        )

        assert cifras.cash_sales == Money("4915.50")
        assert cifras.returns_total == Money("1638.50")
        # 50 000 + 4 915,50 − 1 638,50
        assert cifras.expected == Money(53277)

    def test_contando_53000_falta_277(self, piezas, reporte):
        _, _, caja, _ = piezas
        turno = caja.create_session(
            user_id=CAJERO, opening=Money(53277), opened_at=APERTURA, notes=None
        )
        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money(53277),
            opened_at=APERTURA,
            closed_at=None,
            counted=Money(53000),
        )
        assert cifras.difference == Money(-277)

    def test_la_tarjeta_no_pasa_por_la_gaveta(self, piezas, reporte):
        """
        Sumarla haría que todo turno con datáfono cerrara con un faltante igual
        a lo cobrado con tarjeta.
        """
        ventas, _, caja, reloj = piezas
        turno = caja.create_session(
            user_id=CAJERO, opening=Money(10000), opened_at=APERTURA, notes=None
        )
        reloj.advance(minutes=5)
        vender(ventas, reloj.now(), 1000, "Efectivo")
        vender(ventas, reloj.now(), 5000, "Tarjeta")
        vender(ventas, reloj.now(), 2000, "Transferencia")

        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money(10000),
            opened_at=APERTURA,
            closed_at=None,
            counted=None,
        )

        assert cifras.sales_count == 3
        assert cifras.sales_total == Money(8000)
        assert cifras.cash_sales == Money(1000)
        assert cifras.expected == Money(11000)

    def test_desglosa_por_metodo_de_mayor_a_menor(self, piezas, reporte):
        ventas, _, caja, reloj = piezas
        turno = caja.create_session(
            user_id=CAJERO, opening=Money.zero(), opened_at=APERTURA, notes=None
        )
        reloj.advance(minutes=5)
        vender(ventas, reloj.now(), 1000, "Efectivo")
        vender(ventas, reloj.now(), 5000, "Tarjeta")
        vender(ventas, reloj.now(), 500, "Efectivo")

        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money.zero(),
            opened_at=APERTURA,
            closed_at=None,
            counted=None,
        )

        assert cifras.by_payment_method == [
            ("Tarjeta", 1, Money(5000)),
            ("Efectivo", 2, Money(1500)),
        ]

    def test_solo_entran_las_ventas_de_la_ventana(self, piezas, reporte):
        """Lo que hace falta el `DATETIME`: con solo la fecha, todas las del día
        caerían en el mismo instante y no habría forma de separar dos turnos."""
        ventas, _, caja, reloj = piezas

        vender(ventas, datetime(2026, 8, 16, 21, 59, 0), 9999)  # antes de abrir
        turno = caja.create_session(
            user_id=CAJERO, opening=Money.zero(), opened_at=APERTURA, notes=None
        )
        reloj.advance(hours=1, minutes=58)
        vender(ventas, reloj.now(), 1000)  # 23:58, dentro
        vender(ventas, datetime(2026, 8, 17, 0, 30, 0), 7777)  # después de cerrar

        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money.zero(),
            opened_at=APERTURA,
            closed_at=datetime(2026, 8, 17, 0, 0, 0),
            counted=None,
        )

        assert cifras.sales_count == 1
        assert cifras.cash_sales == Money(1000)

    def test_solo_entran_las_ventas_de_ese_cajero(self, piezas, reporte):
        ventas, _, caja, reloj = piezas
        turno = caja.create_session(
            user_id=CAJERO, opening=Money.zero(), opened_at=APERTURA, notes=None
        )
        reloj.advance(minutes=5)
        vender(ventas, reloj.now(), 1000, user_id=CAJERO)
        vender(ventas, reloj.now(), 8888, user_id=99)

        cifras = reporte(
            session_id=turno.id,
            user_id=CAJERO,
            opening=Money.zero(),
            opened_at=APERTURA,
            closed_at=None,
            counted=None,
        )
        assert cifras.cash_sales == Money(1000)


class TestMovimientos:
    def _abierta(self, caja):
        return caja.create_session(
            user_id=CAJERO, opening=Money(10000), opened_at=APERTURA, notes=None
        )

    def test_una_entrada(self, piezas, reporte):
        _, _, caja, reloj = piezas
        self._abierta(caja)
        caso = AddCashMovement(cash=caja, report=reporte, uow=_Uow(), clock=reloj)

        mov = caso(user_id=CAJERO, type_="entrada", amount=Money(500), reason="  fondo  ")
        assert mov.amount == Money(500)
        assert mov.reason == "fondo", "no se recortó el motivo"

    def test_una_salida_dentro_de_lo_disponible(self, piezas, reporte):
        _, _, caja, reloj = piezas
        self._abierta(caja)
        caso = AddCashMovement(cash=caja, report=reporte, uow=_Uow(), clock=reloj)
        caso(user_id=CAJERO, type_="salida", amount=Money(10000), reason="vaciar")

    def test_no_se_saca_mas_de_lo_que_hay(self, piezas, reporte):
        _, _, caja, reloj = piezas
        self._abierta(caja)
        caso = AddCashMovement(cash=caja, report=reporte, uow=_Uow(), clock=reloj)

        with pytest.raises(InsufficientCash):
            caso(user_id=CAJERO, type_="salida", amount=Money("10000.01"), reason="de más")
        assert caja.movimientos == []

    def test_las_salidas_anteriores_cuentan_para_la_siguiente(self, piezas, reporte):
        _, _, caja, reloj = piezas
        self._abierta(caja)
        caso = AddCashMovement(cash=caja, report=reporte, uow=_Uow(), clock=reloj)
        caso(user_id=CAJERO, type_="salida", amount=Money(6000), reason="proveedor")

        with pytest.raises(InsufficientCash):
            caso(user_id=CAJERO, type_="salida", amount=Money(5000), reason="otra")

    def test_sin_caja_abierta_no_hay_movimiento(self, piezas, reporte):
        _, _, caja, reloj = piezas
        caso = AddCashMovement(cash=caja, report=reporte, uow=_Uow(), clock=reloj)

        with pytest.raises(NoOpenSession):
            caso(user_id=CAJERO, type_="entrada", amount=Money(100), reason="x")


class TestCerrar:
    def test_cierra_con_lo_contado(self, piezas):
        _, _, caja, reloj = piezas
        caja.create_session(user_id=CAJERO, opening=Money(50000), opened_at=APERTURA, notes=None)
        caso = CloseCashSession(cash=caja, uow=_Uow(), clock=reloj)

        reloj.advance(hours=8)
        turno = caso(user_id=CAJERO, counted=Money(53000), notes="faltante")

        assert turno.status == "cerrada"
        assert turno.closing_amount == Money(53000)
        assert turno.closed_at == reloj.now()

    def test_no_se_cierra_lo_que_no_esta_abierto(self, piezas):
        _, _, caja, reloj = piezas
        caso = CloseCashSession(cash=caja, uow=_Uow(), clock=reloj)

        with pytest.raises(NoOpenSession):
            caso(user_id=CAJERO, counted=Money(0), notes=None)

    def test_contar_cero_vale_pero_negativo_no(self, piezas):
        _, _, caja, reloj = piezas
        caja.create_session(user_id=1, opening=Money.zero(), opened_at=APERTURA, notes=None)
        caja.create_session(user_id=2, opening=Money.zero(), opened_at=APERTURA, notes=None)
        caso = CloseCashSession(cash=caja, uow=_Uow(), clock=reloj)

        caso(user_id=1, counted=Money.zero(), notes=None)
        with pytest.raises(InvalidMovement):
            caso(user_id=2, counted=Money(-1), notes=None)


class _Uow:
    """Unidad de trabajo mínima para estas pruebas."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        pass

    def rollback(self):
        pass
