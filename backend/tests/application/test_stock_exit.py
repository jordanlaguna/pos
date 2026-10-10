"""
Salidas con motivo, sin base (T-1502, RN-99).

Lo que más importa: que una salida sin motivo válido no entre, que se valore al
promedio del momento, que la anulación reponga al costo de la salida y no al de
hoy, y que las dos dejen su fila en el kárdex y su asiento.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.application.use_cases.stock_exit import (
    CancelStockExit,
    EmptyExit,
    ExitCancelled,
    ExitNotFound,
    ExitRequest,
    MissingVoidReason,
    ProductNotFoundInExit,
    ReasonNotFound,
    RegisterStockExit,
    RequestedExitLine,
)
from app.domain.errors import InsufficientStock, InvalidQuantity, ReasonInactive, ReasonIsSystem
from app.domain.inventory import EXIT, EXIT_VOID
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import (
    SUCURSAL,
    FakeProduct,
    FakeProductRepository,
    FakeReason,
    FakeStockExitRepository,
    FakeStockReasonRepository,
    FakeUnitOfWork,
    mover,
)

MOMENTO = datetime(2026, 10, 10, 9, 0, 0)
MERMA, VENCIDO, APAGADO, TOMA = 1, 2, 3, 4
ARROZ, CAFE = 1, 2


class LibroQueAnota:
    """Un libro que solo recuerda lo que le contaron."""

    def __init__(self) -> None:
        self.salidas: list = []
        self.anulaciones: list = []

    def record_stock_exit(self, exit, cost):
        self.salidas.append((exit, cost))

    def record_stock_exit_void(self, exit, cost):
        self.anulaciones.append((exit, cost))


@pytest.fixture
def catalogo():
    return FakeProductRepository(
        [
            FakeProduct(ARROZ, "Arroz 1 kg", Money(1450), stock=10, cost=Money(900)),
            FakeProduct(CAFE, "Café molido", Money(4250), stock=5),
        ]
    )


@pytest.fixture
def motivos():
    return FakeStockReasonRepository(
        [
            FakeReason(MERMA, "shrinkage", "Merma"),
            FakeReason(VENCIDO, "expired", "Vencido"),
            FakeReason(APAGADO, "sample", "Muestra", is_active=False),
            FakeReason(TOMA, "count", "Toma física", is_system=True),
        ]
    )


@pytest.fixture
def mundo(catalogo, motivos):
    salidas = FakeStockExitRepository()
    mueve, niveles, kardex = mover(catalogo)
    libro = LibroQueAnota()
    uow = FakeUnitOfWork()
    registrar = RegisterStockExit(
        products=catalogo,
        reasons=motivos,
        exits=salidas,
        uow=uow,
        clock=FixedClock(MOMENTO),
        stock=mueve,
        ledger=libro,
    )
    anular = CancelStockExit(
        products=catalogo,
        exits=salidas,
        uow=uow,
        clock=FixedClock(MOMENTO),
        stock=mueve,
        ledger=libro,
    )
    return registrar, anular, catalogo, salidas, kardex, libro, uow


def salida(lineas, motivo=MERMA, **cambios):
    base = dict(
        reason_id=motivo,
        user_id=1,
        branch_id=SUCURSAL,
        notes=None,
        lines=[RequestedExitLine(pid, cant) for pid, cant in lineas],
    )
    base.update(cambios)
    return ExitRequest(**base)


class TestUnaSalidaBuena:
    def test_baja_las_existencias_al_promedio_del_momento(self, mundo):
        registrar, _, catalogo, salidas, kardex, _, uow = mundo
        hecha = registrar(salida([(ARROZ, 3), (CAFE, 1)]))

        assert catalogo.get(ARROZ).stock == 7 and catalogo.get(CAFE).stock == 4
        assert hecha.units == 4
        # 3 × 900 más 1 × 0: el café nunca se compró y sale sin plata.
        assert hecha.total_cost == Money(2700)
        assert [l.unit_cost for l in hecha.lines] == [Money(900), Money.zero()]
        assert salidas.get(hecha.id_exit).status == "applied"
        assert uow.committed

    def test_deja_una_fila_del_kardex_por_linea(self, mundo):
        registrar, _, _, _, kardex, _, _ = mundo
        hecha = registrar(salida([(ARROZ, 3), (CAFE, 1)]))

        filas = kardex.of_source("stock_exit", hecha.id_exit)
        assert [(f.kind, f.product_id, f.quantity, f.before_qty, f.after_qty, f.source_line) for f in filas] == [
            (EXIT, ARROZ, -3, 10, 7, 1),
            (EXIT, CAFE, -1, 5, 4, 2),
        ]
        assert filas[0].unit_cost == Money(900) and filas[0].moved_at == MOMENTO

    def test_le_cuenta_al_libro_el_costo_total(self, mundo):
        registrar, _, _, _, _, libro, _ = mundo
        hecha = registrar(salida([(ARROZ, 2)]))

        [(documento, costo)] = libro.salidas
        assert (documento.id, documento.date) == (hecha.id_exit, MOMENTO.date())
        assert costo == Money(1800)

    def test_bloquea_todos_los_productos_antes_de_tocar_ninguno(self, mundo):
        registrar, _, catalogo, _, _, _, _ = mundo
        registrar(salida([(CAFE, 1), (ARROZ, 1)]))
        assert catalogo.bloqueados[0] == [CAFE, ARROZ]

    def test_guarda_las_notas_y_la_hora_del_servidor(self, mundo):
        registrar, _, _, salidas, _, _, _ = mundo
        hecha = registrar(salida([(ARROZ, 1)], notes="se cayó una caja"))
        assert salidas.get(hecha.id_exit).notes == "se cayó una caja"
        assert salidas.get(hecha.id_exit).created_at == MOMENTO


class TestLoQueNoEntra:
    def test_sin_lineas(self, mundo):
        registrar, _, _, salidas, _, _, _ = mundo
        with pytest.raises(EmptyExit):
            registrar(salida([]))
        assert salidas.salidas == []

    @pytest.mark.parametrize("cantidad", [0, -2])
    def test_una_cantidad_sin_sentido(self, mundo, cantidad):
        registrar, _, _, _, _, _, _ = mundo
        with pytest.raises(InvalidQuantity):
            registrar(salida([(ARROZ, cantidad)]))

    def test_un_motivo_que_no_existe(self, mundo):
        registrar, _, _, _, _, _, _ = mundo
        with pytest.raises(ReasonNotFound) as error:
            registrar(salida([(ARROZ, 1)], motivo=99))
        assert error.value.reason_id == 99

    def test_un_motivo_apagado(self, mundo):
        registrar, _, _, _, _, _, _ = mundo
        with pytest.raises(ReasonInactive):
            registrar(salida([(ARROZ, 1)], motivo=APAGADO))

    def test_el_motivo_de_la_toma_no_se_elige(self, mundo):
        registrar, _, _, _, _, _, _ = mundo
        with pytest.raises(ReasonIsSystem):
            registrar(salida([(ARROZ, 1)], motivo=TOMA))

    def test_un_producto_que_no_existe(self, mundo):
        registrar, _, _, salidas, _, _, uow = mundo
        with pytest.raises(ProductNotFoundInExit) as error:
            registrar(salida([(ARROZ, 1), (99, 1)]))
        assert error.value.product_id == 99
        assert salidas.salidas == [] and uow.rolled_back

    def test_lo_que_no_hay_no_sale_y_se_revierte_todo(self, mundo):
        registrar, _, catalogo, _, kardex, libro, uow = mundo
        with pytest.raises(InsufficientStock):
            registrar(salida([(ARROZ, 1), (CAFE, 6)]))
        # La primera línea ya se había movido en memoria; la transacción
        # revierte, y el libro no alcanzó a enterarse.
        assert uow.rolled_back and not uow.committed
        assert libro.salidas == []


class TestAnularUnaSalida:
    def test_repone_al_costo_de_la_salida_y_no_al_de_hoy(self, mundo):
        registrar, anular, catalogo, salidas, kardex, libro, _ = mundo
        hecha = registrar(salida([(ARROZ, 3)]))
        # Después de la salida el promedio subió: una compra más cara.
        catalogo.update_cost(ARROZ, Money(1200))

        anulada = anular(hecha.id_exit, user_id=7, reason="se contó mal")

        assert catalogo.get(ARROZ).stock == 10
        assert anulada.units_returned == 3 and anulada.total_cost == Money(2700)
        fila = salidas.get(hecha.id_exit)
        assert (fila.status, fila.void_reason, fila.voided_at) == ("voided", "se contó mal", MOMENTO)
        [reversion] = [f for f in kardex.of_source("stock_exit", hecha.id_exit) if f.kind == EXIT_VOID]
        assert (reversion.quantity, reversion.before_qty, reversion.after_qty) == (3, 7, 10)
        assert reversion.unit_cost == Money(900), "repuso al promedio de hoy"
        assert reversion.avg_cost_after == Money(1200), "el promedio no se deshace"
        assert reversion.user_id == 7
        [(documento, costo)] = libro.anulaciones
        assert documento.id == hecha.id_exit and costo == Money(2700)

    def test_sin_motivo_no_se_anula(self, mundo):
        registrar, anular, catalogo, _, _, _, _ = mundo
        hecha = registrar(salida([(ARROZ, 3)]))
        for vacio in ("", "   "):
            with pytest.raises(MissingVoidReason):
                anular(hecha.id_exit, user_id=1, reason=vacio)
        assert catalogo.get(ARROZ).stock == 7

    def test_una_que_no_existe(self, mundo):
        _, anular, _, _, _, _, _ = mundo
        with pytest.raises(ExitNotFound):
            anular(99, user_id=1, reason="x")

    def test_no_se_anula_dos_veces(self, mundo):
        registrar, anular, catalogo, _, _, _, _ = mundo
        hecha = registrar(salida([(ARROZ, 3)]))
        anular(hecha.id_exit, user_id=1, reason="x")
        with pytest.raises(ExitCancelled):
            anular(hecha.id_exit, user_id=1, reason="otra vez")
        assert catalogo.get(ARROZ).stock == 10, "repuso dos veces"

    def test_sin_libro_tambien_funciona(self, catalogo, motivos):
        salidas = FakeStockExitRepository()
        mueve, _, _ = mover(catalogo)
        registrar = RegisterStockExit(
            products=catalogo, reasons=motivos, exits=salidas, uow=FakeUnitOfWork(),
            clock=FixedClock(MOMENTO), stock=mueve,
        )
        anular = CancelStockExit(
            products=catalogo, exits=salidas, uow=FakeUnitOfWork(),
            clock=FixedClock(MOMENTO), stock=mueve,
        )
        hecha = registrar(salida([(ARROZ, 1)]))
        anular(hecha.id_exit, user_id=1, reason="x")
        assert catalogo.get(ARROZ).stock == 10
